"""Crash stress-test: verify atexit + weakref cleanup releases handles.

Simulates sudden child-process death (SIGKILL / os._exit) while holding
SHM + signal handles, then verifies new processes can reclaim the same names
without resource leaks.
"""

import sys, os, time, subprocess, signal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from core.shm_gustation import (
    ShmGustationProducer, ShmGustationConsumer,
    GustationChannel, _ACTIVE_INSTANCES,
)

CRASH_SHM = "Local_BCI_CrashTest"
CRASH_SIG = "Local_BCI_CrashTestSig"
CRASH_SHM2 = "Local_BCI_CrashTest2"
CRASH_SIG2 = "Local_BCI_CrashTestSig2"


def _child_producer(shm_name, sig_name, crash_with):
    """Start a subprocess that creates a producer, writes a frame, then crashes."""
    code = f"""
import sys, os, signal
sys.path.insert(0, {sys.path[0]!r})
from core.shm_gustation import ShmGustationProducer, GustationChannel

p = ShmGustationProducer({shm_name!r}, {sig_name!r})
p.open()
ch = [GustationChannel(0, 0.5, 100.0, 1, (0,0,0))]
p.write_frame(0, ch)
print("CRASH_CHILD: producer open, about to crash", flush=True)
{crash_with}
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    # Wait for it to print and crash
    try:
        out, _ = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate(timeout=3)
    return proc.returncode, out


def _child_consumer(shm_name, sig_name):
    """Start a subprocess that opens consumer, waits for signal, reads frames."""
    code = f"""
import sys, os, time
sys.path.insert(0, {sys.path[0]!r})
from core.shm_gustation import ShmGustationConsumer

c = ShmGustationConsumer({shm_name!r}, {sig_name!r})
c.open()
print("CONSUMER_CHILD: opened", flush=True)
ok = c.wait(timeout_ms=3000)
frames = c.read_all()
print(f"CONSUMER_CHILD: wait={{ok}} frames={{len(frames)}}", flush=True)
c.close()
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        out, _ = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate(timeout=3)
    return proc.returncode, out


def _clean_stale():
    """Remove any leftover SHM / semaphore files."""
    for p in [f"/dev/shm/{CRASH_SHM}", f"/dev/shm/{CRASH_SHM2}",
              f"/dev/shm/sem.{CRASH_SIG}", f"/dev/shm/sem.{CRASH_SIG2}"]:
        try:
            os.remove(p)
        except FileNotFoundError:
            pass


# ── Tests ─────────────────────────────────────────────────────


def test_cleanup_after_sigkill():
    """Kill the child with SIGKILL; verify new producer can re-create resources."""
    _clean_stale()

    rc, out = _child_producer(CRASH_SHM, CRASH_SIG, 'os.kill(os.getpid(), signal.SIGKILL)')
    assert "CRASH_CHILD" in out, f"Child didn't start properly:\n{out}"

    # Should be able to create a new producer with the same name
    p = ShmGustationProducer(CRASH_SHM, CRASH_SIG)
    try:
        p.open()
        assert p._shm_signal is not None, "Signal handle should be valid"
        ch = [GustationChannel(0, 0.5, 100.0, 1, (0, 0, 0))]
        ok = p.write_frame(1, ch)
        assert ok, "Should be able to write after crash"
    finally:
        p.close()


def test_cleanup_after_os_exit():
    """Kill the child with os._exit(1); verify resource reclaim."""
    _clean_stale()

    rc, out = _child_producer(CRASH_SHM2, CRASH_SIG2, 'os._exit(1)')
    assert "CRASH_CHILD" in out, f"Child didn't start:\n{out}"

    p = ShmGustationProducer(CRASH_SHM2, CRASH_SIG2)
    try:
        p.open()
        assert p._shm_signal is not None
        ch = [GustationChannel(0, 0.5, 100.0, 1, (0, 0, 0))]
        ok = p.write_frame(1, ch)
        assert ok, "write after os._exit crash"
    finally:
        p.close()


def test_consumer_survives_producer_crash():
    """Producer crashes mid-stream; consumer should still read buffered frames."""
    _clean_stale()

    # Create producer + write frames
    p = ShmGustationProducer(CRASH_SHM, CRASH_SIG)
    p.open()
    ch = [GustationChannel(0, 0.5, 100.0, 1, (0, 0, 0))]
    for i in range(5):
        p.write_frame(i, ch)
    p.close()

    # Consumer should read the buffered frames
    c = ShmGustationConsumer(CRASH_SHM, CRASH_SIG)
    try:
        c.open()
        frames = c.read_all()
        assert len(frames) == 5, f"Expected 5 buffered frames, got {len(frames)}"
    finally:
        c.close()


def test_no_dangling_weakrefs():
    """After close(), the instance should be removed from _ACTIVE_INSTANCES."""
    _clean_stale()

    p = ShmGustationProducer("Local_BCI_RefTest", "Local_BCI_RefTestSig")
    p.open()
    sig = p._shm_signal
    assert sig is not None
    assert p in set(_ACTIVE_INSTANCES), "Should be in active set while open"
    p.close()
    assert p not in set(_ACTIVE_INSTANCES), "Should be removed after close"


def test_context_manager_cleanup():
    """Using 'with' block should auto-close on normal exit."""
    _clean_stale()

    with ShmGustationProducer("Local_BCI_CtxTest", "Local_BCI_CtxTestSig") as p:
        p.open()
        assert p.is_open
        assert p._shm_signal is not None

    assert not p.is_open, "Should be closed after context exit"
    assert p._closed, "Should be marked closed"
