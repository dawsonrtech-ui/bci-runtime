#!/usr/bin/env python3
"""Performance benchmark for the SHM ring buffer.

Measures:
  - Write throughput (frames/s)
  - Read throughput (frames/s)
  - Round-trip latency (min/avg/max)
  - Buffer occupancy
  - Dropped frames

Usage:
    python tools/bci_benchmark.py --duration 10
"""
import sys, os, time, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.shm_gustation import (
    ShmGustationProducer, ShmGustationConsumer, GustationChannel,
    RING_BUFFER_SIZE,
)

N_CH = 8
BENCH_DURATION = 5.0


def _make_frame(fid: int) -> list:
    t = time.time()
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
    written = 0

    for i in range(total):
        ok = prod.write_frame(i, _make_frame(i))
        if ok:
            written += 1
        time.sleep(max(0, t0 + (i+1)*period - time.perf_counter()))

    elapsed = time.perf_counter() - t0
    metrics = prod.get_metrics()
    prod.close()
    return {
        "target_hz": hz,
        "duration": elapsed,
        "frames_written": metrics["frames_written"],
        "frames_dropped": metrics["frames_dropped"],
        "fps": metrics["frames_written"] / elapsed,
        "buffer_occupancy": metrics["buffer_occupancy"],
    }


def bench_read(hz: int = 500) -> dict:
    # Pre-fill the ring buffer
    prod = ShmGustationProducer()
    prod.open()
    for i in range(RING_BUFFER_SIZE):
        prod.write_frame(i, _make_frame(i))
    prod.close()

    cons = ShmGustationConsumer()
    cons.open()
    t0 = time.perf_counter()
    total = int(BENCH_DURATION * hz)
    read = 0
    latencies = []

    for _ in range(total):
        frames = cons.read_all()
        for f in frames:
            t_sent = f.channels[0].duration_ms
            lat = (time.time() - t_sent) * 1000
            latencies.append(lat)
            read += 1
        if not frames:
            cons.wait(1)
        else:
            time.sleep(0.001)

    elapsed = time.perf_counter() - t0
    cons.close()
    return {
        "target_hz": hz,
        "duration": elapsed,
        "frames_read": read,
        "fps": read / elapsed,
        "latency": {
            "min": min(latencies) if latencies else 0,
            "avg": statistics.mean(latencies) if latencies else 0,
            "max": max(latencies) if latencies else 0,
            "p99": sorted(latencies)[int(len(latencies)*0.99)] if latencies else 0,
        },
    }


def main():
    print("=" * 50)
    print("BCI SHM Ring Buffer Benchmark")
    print("=" * 50)

    for hz in [100, 250, 500, 1000]:
        print(f"\n--- Write @ {hz} Hz ---")
        r = bench_write(hz)
        print(f"  Written: {r['frames_written']}  Dropped: {r['frames_dropped']}")
        print(f"  Throughput: {r['fps']:.0f} fps  Occupancy: {r['buffer_occupancy']}")

        print(f"  Read @ {hz} Hz ---")
        r2 = bench_read(hz)
        print(f"  Read: {r2['frames_read']}  Throughput: {r2['fps']:.0f} fps")
        lat = r2['latency']
        print(f"  Latency: min={lat['min']:.3f}ms  avg={lat['avg']:.3f}ms  "
              f"max={lat['max']:.3f}ms  p99={lat['p99']:.3f}ms")

    print("\nDone.")


if __name__ == "__main__":
    main()
