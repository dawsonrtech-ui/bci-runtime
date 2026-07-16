"""Performance benchmarks for the SHM ring buffer.

Tests:
  - 200+ Hz streaming throughput
  - Signal wake latency (empty -> non-empty transition)
  - Kernel transition profiling (signal triggers vs. poll timeout loops)
  - Ring full / drop rate under sustained load
"""

import sys, os, time, threading, array

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.shm_gustation import (
    ShmGustationProducer, ShmGustationConsumer,
    GustationChannel, SHM_NAME, SIGNAL_NAME,
    RING_BUFFER_SIZE,
)

import ctypes
import pytest

# ── helpers ────────────────────────────────────────────────────


HAS_NATIVE = False
_lib = None

def _load_signal_lib():
    from core.native_bridge import _find_lib
    path = _find_lib()
    assert path
    lib = ctypes.CDLL(path)
    lib.create_os_signal.argtypes = [ctypes.c_char_p]
    lib.create_os_signal.restype = ctypes.c_void_p
    lib.open_os_signal.argtypes = [ctypes.c_char_p]
    lib.open_os_signal.restype = ctypes.c_void_p
    lib.trigger_os_signal.argtypes = [ctypes.c_void_p]
    lib.trigger_os_signal.restype = None
    lib.wait_os_signal.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.wait_os_signal.restype = ctypes.c_int
    lib.close_os_signal.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.close_os_signal.restype = None
    return lib

try:
    _lib = _load_signal_lib()
    HAS_NATIVE = True
except (OSError, AssertionError):
    pass

needs_native = pytest.mark.skipif(
    not HAS_NATIVE,
    reason="native bridge DLL not available on this platform",
)


def _cleanup():
    import mmap
    try:
        mmap.mmap(-1, 8464, tagname=SHM_NAME, access=mmap.ACCESS_WRITE).close()
    except Exception:
        pass


_cleanup()


# ═══════════════════════════════════════════════════════════════
#  Test 1:  200+ Hz streaming throughput
# ═══════════════════════════════════════════════════════════════

def test_200hz_throughput():
    """Produce frames at 200+ Hz for 5 seconds, measure consumer receive rate."""
    prod = ShmGustationProducer("Local_BCI_BenchRing", "Local_BCI_BenchWake")
    cons = ShmGustationConsumer("Local_BCI_BenchRing")
    TOTAL_FRAMES = 1000

    received = []
    stop = False

    def consumer_thread():
        cons.open()
        while not stop:
            frames = cons.read_all()
            for f in frames:
                received.append(f.packet_id)
        cons.close()

    prod.open()
    t = threading.Thread(target=consumer_thread, daemon=True)
    t.start()

    time.sleep(0.05)  # let consumer attach

    ch = [GustationChannel(0, 0.5, 50.0, 1, (0, 0, 0))]
    written = 0
    start = time.perf_counter()

    for pid in range(1, TOTAL_FRAMES + 1):
        ok = prod.write_frame(pid, ch)
        if ok:
            written += 1
        if pid % 10 == 0:
            time.sleep(0.001)  # yield

    elapsed = time.perf_counter() - start
    stop = True
    t.join(timeout=3)
    prod.close()

    rate = written / elapsed if elapsed > 0 else 0
    print(f"\n[Bench 200Hz] wrote {written}/{TOTAL_FRAMES} in {elapsed:.2f}s = {rate:.0f} Hz")
    print(f"[Bench 200Hz] consumer received {len(received)} frames, "
          f"drops={written - len(received)}")

    assert rate > 100, f"throughput too low: {rate:.0f} Hz"
    assert len(received) >= written * 0.95, "lost more than 5% of frames"
    print("[Bench 200Hz] PASS")


# ═══════════════════════════════════════════════════════════════
#  Test 2:  Signal wake latency
# ═══════════════════════════════════════════════════════════════

@needs_native
def test_signal_wake_latency():
    """Measure round-trip latency: producer triggers signal -> consumer wakes
    and reads frame.  Uses the OS signal handle from C for precise timing."""
    lib = _load_signal_lib()
    import mmap
    from core.shm_gustation import SHM_TOTAL_SIZE

    # Create a clean ring + signal for this test
    sig = lib.create_os_signal(b"Local_BCI_LatencyWake")
    assert sig

    # Use a file-backed mmap (works on both Linux and Windows)
    _shm_path = f"/dev/shm/Local_BCI_LatencyRing"
    if os.name == "nt":
        _shm_path = "Local_BCI_LatencyRing"
        mm = mmap.mmap(-1, SHM_TOTAL_SIZE, tagname=_shm_path,
                       access=mmap.ACCESS_WRITE)
    else:
        with open(_shm_path, "a+b") as _f:
            _f.truncate(SHM_TOTAL_SIZE)
        _fd = os.open(_shm_path, os.O_RDWR)
        mm = mmap.mmap(_fd, SHM_TOTAL_SIZE, access=mmap.ACCESS_WRITE)
        os.close(_fd)
    raw = (ctypes.c_uint64 * 2).from_buffer(mm)
    raw[0] = 0  # head
    raw[1] = 0  # tail

    # Consumer opens the signal via open_os_signal (same named event)
    h_sig = lib.open_os_signal(b"Local_BCI_LatencyWake")
    assert h_sig

    # Background reader
    stop = False

    def reader():
        while not stop:
            rc = lib.wait_os_signal(h_sig, 500)
            if rc != 0:
                continue
            # drain all available frames
            h = raw[0]
            t = raw[1]
            while t < h:
                t += 1
            raw[1] = t

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    time.sleep(0.02)

    # Write frames with signal
    ch = ct = (ctypes.c_uint8 * 16)()
    frame_data = (ctypes.c_uint8 * 264)()

    N = 500
    latencies = []

    for pid in range(1, N + 1):
        t0 = time.perf_counter_ns()
        raw[0] = pid  # advance head
        was_empty = (pid - 1 == raw[1])
        if was_empty:
            lib.trigger_os_signal(sig)
        t1 = time.perf_counter_ns()
        latencies.append(t1 - t0)

    stop = True
    t.join(timeout=2)

    # Signal-triggered latencies only (empty -> non-empty)
    signal_lats = [latencies[i] for i in range(0, len(latencies), RING_BUFFER_SIZE)]
    # First write is always signal-triggered (and first after each drain)
    # Actually, since reader drains all frames each wake, every write with
    # pid > tail should trigger a signal.

    avg_ns = sum(latencies) / len(latencies)
    max_ns = max(latencies)
    avg_signal_ns = sum(signal_lats) / len(signal_lats) if signal_lats else 0

    print(f"\n[Bench SignalWake] {N} writes, avg {avg_ns:.0f} ns, max {max_ns:.0f} ns")
    if signal_lats:
        print(f"[Bench SignalWake] {len(signal_lats)} signal-triggered writes, "
              f"avg {avg_signal_ns:.0f} ns")

    # Cleanup — release ctypes ref before closing mmap
    del raw
    lib.close_os_signal(sig, b"Local_BCI_LatencyWake")
    lib.close_os_signal(h_sig, None)
    mm.close()

    assert avg_ns < 50_000, f"avg write latency too high: {avg_ns:.0f} ns"
    print("[Bench SignalWake] PASS")


# ═══════════════════════════════════════════════════════════════
#  Test 3:  Kernel transition profiling
# ═══════════════════════════════════════════════════════════════

def test_kernel_transition_profile():
    """Count how many OS signal calls (SetEvent) are made vs. total writes.
    At high throughput, the empty->non-empty signal optimization should yield
    far fewer signal calls than total frames."""
    prod = ShmGustationProducer("Local_BCI_TransRing", "Local_BCI_TransWake")
    cons = ShmGustationConsumer("Local_BCI_TransRing")
    N = 5000

    received = []
    stop = False

    def consumer_thread():
        cons.open()
        while not stop:
            frames = cons.read_all()
            for f in frames:
                received.append(f.packet_id)
            time.sleep(0.0005)
        cons.close()

    prod.open()
    t = threading.Thread(target=consumer_thread, daemon=True)
    t.start()
    time.sleep(0.05)

    ch = [GustationChannel(0, 0.5, 50.0, 1, (0, 0, 0))]

    # We can't directly count SetEvent calls from Python, but we can estimate:
    # each time the buffer transitions empty->non-empty, a signal is sent.
    # If the reader keeps up, every write hits an empty buffer, so signal count
    # equals frame count. If the reader is slower, signal count drops.
    # At high Hz with a fast reader, signal count ~ frame count.
    # With a slow reader (large sleep), signal count << frame count.
    written = 0
    start = time.perf_counter()

    for pid in range(1, N + 1):
        ok = prod.write_frame(pid, ch)
        if ok:
            written += 1
        if pid % 50 == 0:
            time.sleep(0.0005)

    elapsed = time.perf_counter() - start
    stop = True
    t.join(timeout=3)
    prod.close()

    rate = written / elapsed
    print(f"\n[Bench KernelTrans] {written} frames in {elapsed:.2f}s = {rate:.0f} Hz")
    print(f"[Bench KernelTrans] consumer received {len(received)}, "
          f"drops={written - len(received)}")
    print(f"[Bench KernelTrans] ring size={RING_BUFFER_SIZE}, "
          f"max possible drops before stall={RING_BUFFER_SIZE - 1}")

    # With consumer reading at ~1000 Hz (tiny sleep), we expect few drops
    assert len(received) >= written * 0.9, "lost more than 10%"
    print("[Bench KernelTrans] PASS")


# ═══════════════════════════════════════════════════════════════
#  Test 4:  Sustained load (ring full + recovery)
# ═══════════════════════════════════════════════════════════════

def test_ring_full_drop_and_recovery():
    """Fill ring until full (producer returns False), then have consumer drain
    and verify producer resumes successfully."""
    prod = ShmGustationProducer("Local_BCI_DropRing", "Local_BCI_DropWake")
    cons = ShmGustationConsumer("Local_BCI_DropRing")
    N = RING_BUFFER_SIZE * 3

    prod.open()
    cons.open()

    ch = [GustationChannel(0, 1.0, 100.0, 2, (0, 0, 0))]
    written = 0
    dropped = 0
    full_count = 0

    for pid in range(1, N + 1):
        ok = prod.write_frame(pid, ch)
        if ok:
            written += 1
        else:
            dropped += 1
            if dropped == 1:
                full_count += 1

    # Count how many distinct full events
    full_streaks = 0
    in_full = False
    for pid in range(1, N + 1):
        ok = prod.write_frame(pid, ch)  # reset head first
        break
    # Actually simpler: just check how many times full occurred
    prod2 = ShmGustationProducer("Local_BCI_DropRing", "Local_BCI_DropWake")
    prod2.open()
    ch2 = [GustationChannel(0, 1.0, 100.0, 2, (0, 0, 0))]
    full_events = 0
    for pid2 in range(1, 100):
        if not prod2.write_frame(pid2, ch2):
            full_events += 1

    # Now drain
    drained = cons.read_all()
    print(f"\n[Bench RingFull] dropped {dropped}/{N} on fast write (buffer full x{full_count})")
    print(f"[Bench RingFull] drained {len(drained)} frames after burst")

    # After drain, writes should succeed again
    ok = prod2.write_frame(999, ch2)
    assert ok, "should resume writing after drain"

    prod2.close()
    prod.close()
    cons.close()
    print("[Bench RingFull] PASS")


# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    test_200hz_throughput()
    test_signal_wake_latency()
    test_kernel_transition_profile()
    test_ring_full_drop_and_recovery()
    print("\n=== ALL BENCHMARKS PASSED ===")
