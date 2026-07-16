"""IPC latency benchmarks: signal wake, write->read round-trip, throughput."""

import sys, os, time, statistics, uuid, threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.shm_gustation import (
    ShmGustationProducer, ShmGustationConsumer,
    GustationChannel, WAIT_TIMEOUT_MS,
)

SAMPLES = 500
WARMUP = 50
BURST = 32  # matches ring size; drain between bursts


def _tag():
    """Unique suffix to isolate concurrent/sequential runs."""
    return uuid.uuid4().hex[:8]


def bench_signal_wake_latency() -> dict:
    """Measure time from producer.trigger -> consumer.wait return."""
    tag = _tag()
    prod = ShmGustationProducer(f"Local_BCI_Wake_{tag}", f"Local_BCI_WakeSig_{tag}")
    cons = ShmGustationConsumer(f"Local_BCI_Wake_{tag}", f"Local_BCI_WakeSig_{tag}")
    prod.open()
    cons.open()

    ch = [GustationChannel(0, 0.5, 100.0, 1, (0, 0, 0))]
    latencies = []

    for i in range(WARMUP + SAMPLES):
        t0 = time.perf_counter_ns()
        prod.write_frame(i, ch)
        cons.wait(timeout_ms=WAIT_TIMEOUT_MS)
        cons.read_all()
        dt = time.perf_counter_ns() - t0
        if i >= WARMUP:
            latencies.append(dt)

    prod.close()
    cons.close()

    us = [x / 1000 for x in latencies]
    return {
        "name": "signal_wake_latency",
        "samples": len(us),
        "mean_us": statistics.mean(us),
        "median_us": statistics.median(us),
        "min_us": min(us),
        "max_us": max(us),
        "stdev_us": statistics.stdev(us) if len(us) > 1 else 0,
        "p99_us": sorted(us)[int(len(us) * 0.99)],
    }


def bench_write_read_roundtrip() -> dict:
    """Measure producer.write -> consumer.read_all (no signal wait)."""
    tag = _tag()
    prod = ShmGustationProducer(f"Local_BCI_RT_{tag}", f"Local_BCI_RTSig_{tag}")
    cons = ShmGustationConsumer(f"Local_BCI_RT_{tag}", f"Local_BCI_RTSig_{tag}")
    prod.open()
    cons.open()

    ch = [GustationChannel(0, 0.5, 100.0, 1, (0, 0, 0))]
    latencies = []

    for i in range(WARMUP + SAMPLES):
        t0 = time.perf_counter_ns()
        prod.write_frame(i, ch)
        frames = cons.read_all()
        dt = time.perf_counter_ns() - t0
        if i >= WARMUP and len(frames) > 0:
            latencies.append(dt)

    prod.close()
    cons.close()

    us = [x / 1000 for x in latencies]
    return {
        "name": "write_read_roundtrip",
        "samples": len(us),
        "mean_us": statistics.mean(us),
        "median_us": statistics.median(us),
        "min_us": min(us),
        "max_us": max(us),
        "stdev_us": statistics.stdev(us) if len(us) > 1 else 0,
        "p99_us": sorted(us)[int(len(us) * 0.99)],
    }


def bench_throughput() -> dict:
    """Measure frames/sec at various channel payload sizes.

    Consumer drains in a background thread so the ring buffer never fills.
    """
    tag = _tag()
    prod = ShmGustationProducer(f"Local_BCI_Thr_{tag}", f"Local_BCI_ThrSig_{tag}")
    cons = ShmGustationConsumer(f"Local_BCI_Thr_{tag}", f"Local_BCI_ThrSig_{tag}")
    prod.open()
    cons.open()

    results = []
    for n_ch in [1, 4, 16]:
        ch = [GustationChannel(i % 4, 0.5, 100.0, i & 0xFF, (0, 0, 0))
              for i in range(n_ch)]

        # Background drain thread
        drained = []
        stop = threading.Event()

        def drainer():
            while not stop.is_set():
                frames = cons.read_all()
                if frames:
                    drained.extend(frames)
                cons.wait(timeout_ms=5)

        dt = threading.Thread(target=drainer, daemon=True)
        dt.start()

        t0 = time.perf_counter()
        for pid in range(SAMPLES):
            while not prod.write_frame(pid, ch):
                cons.wait(timeout_ms=1)
        elapsed = time.perf_counter() - t0

        stop.set()
        dt.join(timeout=3)
        # Drain any remaining
        drained.extend(cons.read_all())

        results.append({
            "name": f"throughput_{n_ch}ch",
            "frames": len(drained),
            "elapsed_s": round(elapsed, 3),
            "fps": round(SAMPLES / elapsed, 1),
        })

    prod.close()
    cons.close()
    return {"name": "throughput", "results": results}


def run_all():
    results = []
    for bench in [
        bench_signal_wake_latency,
        bench_write_read_roundtrip,
        bench_throughput,
    ]:
        name = bench.__name__
        print(f"[BENCH] {name}...", end=" ", flush=True)
        r = bench()
        results.append(r)
        print("done")

    print()
    print("=" * 60)
    print("IPC LATENCY BENCHMARKS")
    print("=" * 60)

    for r in results:
        if r["name"] == "throughput":
            print(f"\n  Throughput ({SAMPLES} frames each):")
            for sub in r["results"]:
                print(f"    {sub['name']:20s}  {sub['fps']:>8.1f} fps  "
                      f"({sub['elapsed_s']:.2f}s)")
        else:
            print(f"\n  {r['name']} ({r['samples']} samples):")
            print(f"    mean={r['mean_us']:8.2f}us  median={r['median_us']:8.2f}us")
            print(f"    min={r['min_us']:8.2f}us   max={r['max_us']:8.2f}us  "
                  f"p99={r['p99_us']:8.2f}us")
            print(f"    stdev={r['stdev_us']:8.2f}us")

    print("\n" + "=" * 60)
    return results


if __name__ == "__main__":
    run_all()
