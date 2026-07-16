"""Profile context-switching overhead under artificial CPU load.

Runs the IPC latency benchmark with and without `stress-ng` saturating
all CPU cores, then reports how p99 latency shifts.

Usage:
    python tests/test_context_switch_overhead.py
    python tests/test_context_switch_overhead.py --load-cores 2
    python tests/test_context_switch_overhead.py --no-stress  (skip stress)
"""

import sys, os, time, subprocess, statistics, json, argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_ipc_latency_benchmark import (
    bench_signal_wake_latency,
    bench_write_read_roundtrip,
    bench_throughput,
)

LOAD_CORES = 0  # 0 = all available


def _has_stress_ng():
    try:
        r = subprocess.run(["stress-ng", "--version"], capture_output=True, timeout=5)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _start_stress(cores: int = 0):
    """Start stress-ng CPU loaders. Returns Popen handle."""
    if cores == 0:
        cores = os.cpu_count() or 4
    cmd = ["stress-ng", "--cpu", str(cores), "--cpu-method", "matrixprod",
           "--timeout", "120s", "--quiet"]
    print(f"[STRESS] Starting {cores} CPU loaders (matrixprod)...")
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _run_bench(label: str) -> dict:
    print(f"\n{'=' * 50}")
    print(f"  {label}")
    print(f"{'=' * 50}")

    results = {}

    for bench_fn in [bench_signal_wake_latency, bench_write_read_roundtrip]:
        name = bench_fn.__name__
        print(f"  {name}...", end=" ", flush=True)
        r = bench_fn()
        results[name] = r
        print(f"mean={r['mean_us']:.2f}us  p99={r['p99_us']:.2f}us")

    print(f"  bench_throughput...", end=" ", flush=True)
    tr = bench_throughput()
    results["throughput"] = tr
    for sub in tr["results"]:
        print(f"{sub['name']}={sub['fps']:.0f}fps  ", end="")
    print()

    return results


def _compare(baseline: dict, loaded: dict):
    print(f"\n{'=' * 50}")
    print(f"  COMPARISON: Loaded vs Baseline")
    print(f"{'=' * 50}")

    for key in ["signal_wake_latency", "write_read_roundtrip"]:
        b = baseline[key]
        l = loaded.get(key, {})
        if not l:
            continue
        print(f"\n  {key}:")
        print(f"    {'':>12s}  {'Baseline':>8s}  {'Loaded':>8s}  {'Ratio':>8s}")
        for stat in ["mean_us", "p99_us", "max_us"]:
            bv = b.get(stat, 0)
            lv = l.get(stat, 0)
            ratio = lv / bv if bv else float('inf')
            print(f"    {stat:10s}:  {bv:8.2f}  {lv:8.2f}  {ratio:7.2f}x")

    print(f"\n  throughput (fps):")
    b_through = baseline.get("throughput", {}).get("results", [])
    l_through = loaded.get("throughput", {}).get("results", [])
    for b_sub, l_sub in zip(b_through, l_through):
        ratio = l_sub["fps"] / b_sub["fps"] if b_sub["fps"] else float('inf')
        print(f"    {b_sub['name']:20s}:  {b_sub['fps']:>8.1f}  {l_sub['fps']:>8.1f}  {ratio:7.2f}x")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Context-switch overhead profiler")
    p.add_argument("--load-cores", type=int, default=0,
                   help="CPU cores to saturate (0 = all)")
    p.add_argument("--no-stress", action="store_true",
                   help="Skip stress-ng, just run baseline")
    args = p.parse_args()

    print("CONTEXT-SWITCH OVERHEAD PROFILE")
    print(f"  Host: {os.uname().nodename}  CPUs: {os.cpu_count()}")

    # Baseline
    baseline = _run_bench("BASELINE (idle system)")

    if args.no_stress:
        print("\nSkipping load test (--no-stress)")
        sys.exit(0)

    if not _has_stress_ng():
        print("\n[WARN] stress-ng not found. Install with:")
        print("  sudo apt-get install stress-ng")
        print("Skipping load test.")
        sys.exit(1)

    # Under load
    stress_proc = _start_stress(args.load_cores)
    time.sleep(3)  # let load settle
    loaded = _run_bench("UNDER CPU LOAD")
    stress_proc.terminate()
    try:
        stress_proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        stress_proc.kill()

    _compare(baseline, loaded)
