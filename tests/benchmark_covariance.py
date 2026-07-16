import numpy as np
import time
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.streaming_covariance import (
    StableStreamingCovariance,
    MultiClassCovariance,
    _rank1_givens_python,
    _HAS_NUMBA,
)


def benchmark_givens_impl(name, givens_fn, n_runs=50000, n_dims=[4, 8, 16, 32]):
    print(f"\n  {name}:")
    for n in n_dims:
        total_time = 0.0
        for _ in range(min(1000, n_runs)):
            L = np.eye(n, dtype=np.float64)
            v = np.random.standard_normal(n).astype(np.float64)
            t0 = time.perf_counter_ns()
            givens_fn(L, v)
            total_time += time.perf_counter_ns() - t0
        avg_ns = total_time / min(1000, n_runs)
        print(f"    n={n:2d}: {avg_ns:8.1f} ns  ({avg_ns/1000:.2f} us)")


def benchmark_full_update(name, cls, n_runs=50000, n_dims=[4, 8, 16, 32]):
    print(f"\n  {name}:")
    for n in n_dims:
        total_time = 0.0
        cov = cls(n, alpha=0.05, gamma=0.05)
        for _ in range(min(5000, n_runs)):
            x = np.random.standard_normal(n)
            t0 = time.perf_counter_ns()
            cov.update(x)
            total_time += time.perf_counter_ns() - t0
        avg_ns = total_time / min(5000, n_runs)
        samples_per_sec = 1e9 / avg_ns
        print(f"    n={n:2d}: {avg_ns:8.1f} ns  ({avg_ns/1000:.2f} us)  ~{samples_per_sec/1000:.0f}K samples/s")


def benchmark_streaming(duration_sec=60, n_channels=8, sfreq=250):
    print(f"\n  Streaming ({duration_sec}s @ {sfreq}Hz, {n_channels}ch):")
    n_samples = duration_sec * sfreq
    x = np.random.standard_normal((n_samples, n_channels))
    cov = StableStreamingCovariance(n_channels, alpha=0.05, gamma=0.05)
    t0 = time.perf_counter()
    for i in range(n_samples):
        cov.update(x[i])
    total = time.perf_counter() - t0
    print(f"    Processed {n_samples} samples in {total*1000:.1f}ms")
    print(f"    Rate: {n_samples/total/1000:.0f}K samples/s")
    print(f"    Latency per update: {total/n_samples*1e6:.1f}us")


def benchmark_multi_class(n_classes=4, n_channels=8, n_samples=15000):
    print(f"\n  MultiClass ({n_classes} classes, {n_channels}ch, {n_samples} samples):")
    mc = MultiClassCovariance(n_channels, n_classes, alpha=0.05, gamma=0.05)
    labels = np.random.randint(0, n_classes, n_samples)
    x = np.random.standard_normal((n_samples, n_channels))
    t0 = time.perf_counter()
    for i in range(n_samples):
        mc.update(x[i], labels[i])
    total = time.perf_counter() - t0
    print(f"    {n_samples} updates in {total*1000:.1f}ms")
    print(f"    Per-update: {total/n_samples*1e6:.1f}us")
    print(f"    Class counts: {mc.counts}")
    conds = [np.linalg.cond(c.get_covariance(shrunk=True))
             for c in mc.covs]
    print(f"    Condition numbers: {[f'{c:.1f}' for c in conds]}")


def benchmark_convergence(n_channels=4, n_steps=5000):
    print(f"\n  Convergence test ({n_channels}ch, {n_steps} steps):")
    cov = StableStreamingCovariance(n_channels, alpha=0.05, gamma=0.05)
    true_cov = np.array([[4.0, 0.5, 0.0, 0.2],
                         [0.5, 3.0, 0.1, 0.0],
                         [0.0, 0.1, 5.0, 0.3],
                         [0.2, 0.0, 0.3, 2.0]], dtype=np.float64)[:n_channels, :n_channels]
    L_true = np.linalg.cholesky(true_cov)
    errors = []
    for i in range(n_steps):
        z = np.random.standard_normal(n_channels)
        x = L_true @ z
        Sigma_est = cov.update(x)
        if i > 100 and i % 500 == 0:
            err = np.linalg.norm(Sigma_est - true_cov, ord='fro') / np.linalg.norm(true_cov, ord='fro')
            errors.append((i, err))
    print(f"    Convergence: {errors[:5]}")
    print(f"    Final rel error: {errors[-1][1]:.4f}" if errors else "    N/A")


def benchmark_riemannian(n_dims=[4, 8, 16]):
    print(f"\n  Riemannian Tangent Projection:")
    from core.riemannian import project_to_tangent_space, vectorize_tangent_space
    n_runs = 2000
    for n in n_dims:
        total_pt = 0.0
        total_vt = 0.0
        S_ref = np.eye(n, dtype=np.float64)
        for _ in range(n_runs):
            A = np.random.standard_normal((n, n))
            S_t = A @ A.T + 0.1 * np.eye(n)
            t0 = time.perf_counter_ns()
            T = project_to_tangent_space(S_t, S_ref)
            total_pt += time.perf_counter_ns() - t0
            t0 = time.perf_counter_ns()
            v = vectorize_tangent_space(T)
            total_vt += time.perf_counter_ns() - t0
        avg_pt = total_pt / n_runs
        avg_vt = total_vt / n_runs
        print(f"    n={n:2d}: tangent={avg_pt/1000:.1f}us, vectorize={avg_vt/1000:.1f}us")


if __name__ == "__main__":
    print("=" * 60)
    print("BCI RUNTIME - COVARIANCE PIPELINE BENCHMARKS")
    print(f"Numba available: {_HAS_NUMBA}")
    print("=" * 60)

    print("\n--- Givens Rotation Sweep ---")
    benchmark_givens_impl("Python loop", _rank1_givens_python)
    if _HAS_NUMBA:
        from core.streaming_covariance import _rank1_givens_numba
        benchmark_givens_impl("Numba JIT", _rank1_givens_numba)
    else:
        print("  (Numba not installed - install with `pip install numba` for 50-100x speedup)")

    print("\n--- Full Update Pipeline (centering + Mahalanobis + Givens + shrinkage) ---")
    benchmark_full_update("StableStreamingCovariance", StableStreamingCovariance)

    print("\n--- Multi-Class Covariance ---")
    benchmark_multi_class()

    print("\n--- Riemannian Geometry ---")
    benchmark_riemannian()

    print("\n--- Streaming Simulation ---")
    benchmark_streaming(duration_sec=30)

    print("\n--- Convergence ---")
    benchmark_convergence()

    print("\n" + "=" * 60)
    print("Benchmarks complete.")
    print("=" * 60)
