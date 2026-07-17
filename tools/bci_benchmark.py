#!/usr/bin/env python3
"""Performance benchmark for the SHM ring buffer.

Measures:
  - Write throughput with active consumer (frames/s)
  - Read throughput with active producer (frames/s)
  - End-to-end latency (min/avg/max/p99)
  - Buffer occupancy under load
  - Dropped frames

Usage:
    python tools/bci_benchmark.py --duration 10
"""
import sys, os, time, statistics, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.shm_gustation import (
    ShmGustationProducer, ShmGustationConsumer, GustationChannel,
    RING_BUFFER_SIZE,
)

N_CH = 8
BENCH_DURATION = 5.0


def _make_frame(fid: int) -> list:
    t = time.monotonic()
    return [
        GustationChannel(channel_id=i, intensity=0.5+0.5*(i/N_CH),
                         duration_ms=float(t), chemical_profile=i)
        for i in range(N_CH)
    ]


def bench_write(hz: int = 500) -> dict:
    prod = ShmGustationProducer()
    prod.open()
    period = 1.0 / hz
    total = int(BENCH_DURATION * hz)
    t0 = time.perf_counter()

    stop = threading.Event()
    read_count = 0

    def consumer():
        nonlocal read_count
        cons = ShmGustationConsumer()
        cons.open()
        while not stop.is_set():
            frames = cons.read_all()
            read_count += len(frames)
            if not frames:
                cons.wait(1)
        cons.close()

    c = threading.Thread(target=consumer, daemon=True)
    c.start()
    time.sleep(0.05)  # let consumer attach

    for i in range(total):
        prod.write_frame(i, _make_frame(i))
        elapsed = time.perf_counter() - t0
        next_t = t0 + (i + 1) * period
        sleep = next_t - time.perf_counter()
        if sleep > 0:
            time.sleep(sleep)

    stop.set()
    c.join(timeout=2)

    elapsed = time.perf_counter() - t0
    metrics = prod.get_metrics()
    prod.close()
    return {
        "target_hz": hz,
        "duration": elapsed,
        "frames_written": metrics["frames_written"],
        "frames_dropped": metrics["frames_dropped"],
        "frames_read": read_count,
        "write_fps": metrics["frames_written"] / elapsed,
        "buffer_occupancy": metrics["buffer_occupancy"],
    }


def bench_read(hz: int = 500) -> dict:
    cons = ShmGustationConsumer()
    cons.open()

    period = 1.0 / hz
    latencies = []
    read_count = 0
    write_count = 0
    t0 = time.perf_counter()
    stop = threading.Event()

    def writer():
        nonlocal write_count
        prod = ShmGustationProducer()
        prod.open()
        target_t = time.perf_counter()
        while not stop.is_set():
            prod.write_frame(write_count, _make_frame(write_count))
            write_count += 1
            target_t += period
            sleep = target_t - time.perf_counter()
            if sleep > 0:
                time.sleep(sleep)
        prod.close()

    w = threading.Thread(target=writer, daemon=True)
    w.start()
    time.sleep(0.05)

    deadline = time.perf_counter() + BENCH_DURATION
    while time.perf_counter() < deadline:
        frames = cons.read_all()
        now = time.monotonic()
        for f in frames:
            t_sent = f.channels[0].duration_ms
            lat = max(0, (now - t_sent) * 1000)
            latencies.append(lat)
            read_count += 1
        if not frames:
            cons.wait(1)

    stop.set()
    w.join(timeout=2)

    elapsed = time.perf_counter() - t0
    cons.close()

    latencies.sort() if latencies else None
    return {
        "target_hz": hz,
        "duration": elapsed,
        "frames_written": write_count,
        "frames_read": read_count,
        "read_fps": read_count / elapsed,
        "latency": {
            "min": latencies[0] if latencies else 0,
            "avg": statistics.mean(latencies) if latencies else 0,
            "max": latencies[-1] if latencies else 0,
            "p99": latencies[int(len(latencies) * 0.99)] if latencies else 0,
        },
    }


def main():
    print("=" * 50)
    print("BCI SHM Ring Buffer Benchmark")
    print("=" * 50)

    for hz in [100, 250, 500, 1000]:
        print(f"\n--- Write @ {hz} Hz (with consumer) ---")
        r = bench_write(hz)
        print(f"  Written: {r['frames_written']}  Read: {r['frames_read']}  Dropped: {r['frames_dropped']}")
        print(f"  Write throughput: {r['write_fps']:.0f} fps  Occupancy: {r['buffer_occupancy']}")

        print(f"--- Read @ {hz} Hz (with producer) ---")
        r2 = bench_read(hz)
        print(f"  Written: {r2['frames_written']}  Read: {r2['frames_read']}")
        print(f"  Read throughput: {r2['read_fps']:.0f} fps")
        lat = r2['latency']
        print(f"  Latency: min={lat['min']:.3f}ms  avg={lat['avg']:.3f}ms  "
              f"max={lat['max']:.3f}ms  p99={lat['p99']:.3f}ms")

    print("\nDone.")


if __name__ == "__main__":
    main()
