import sys
import os
import time
import platform
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.streaming_covariance import StableStreamingCovariance
from core.riemannian import project_to_tangent_space, vectorize_tangent_space
from core.cect import MultiHeadSelfAttentionNumPy


def run_ci_profiling_matrix():
    print("=" * 70)
    print(f"RUNNING CROSS-PLATFORM BCI RUNTIME PROFILING MATRIX")
    print(f"OS: {platform.system()} | Release: {platform.release()} | Arch: {platform.machine()}")
    print("=" * 70)

    TARGET_CHOLESKY_US = 100.0
    TARGET_RIEMANNIAN_US = 120.0
    TARGET_CECT_ATTN_US = 250.0

    n_channels = 8
    seq_len = 4
    d_model = 32
    iterations = 5000

    x_test = np.random.randn(n_channels)
    Sigma_test = np.cov(np.random.randn(n_channels, 100))
    Sigma_ref_test = np.cov(np.random.randn(n_channels, 100))
    token_block_test = np.random.randn(seq_len, d_model)

    failures = 0

    # --- 1. Numba Cholesky ---
    cov_engine = StableStreamingCovariance(n_channels=n_channels)
    _ = cov_engine.update(x_test, weight=1.0)

    t_start = time.perf_counter()
    for _ in range(iterations):
        _ = cov_engine.update(x_test, weight=1.0)
    t_end = time.perf_counter()

    cholesky_avg_us = ((t_end - t_start) / iterations) * 1_000_000
    print(f"  Numba Cholesky Update Speed : {cholesky_avg_us:7.2f} us | Limit: {TARGET_CHOLESKY_US} us")
    if cholesky_avg_us > TARGET_CHOLESKY_US:
        print("  FAILURE: Cholesky exceeds platform latency target.")
        failures += 1

    # --- 2. Riemannian Projection ---
    t_start = time.perf_counter()
    for _ in range(iterations):
        T = project_to_tangent_space(Sigma_test, Sigma_ref_test)
        _ = vectorize_tangent_space(T)
    t_end = time.perf_counter()

    riemannian_avg_us = ((t_end - t_start) / iterations) * 1_000_000
    print(f"  Riemannian Tangent Mapping  : {riemannian_avg_us:7.2f} us | Limit: {TARGET_RIEMANNIAN_US} us")
    if riemannian_avg_us > TARGET_RIEMANNIAN_US:
        print("  FAILURE: Riemannian matrix math degradation detected.")
        failures += 1

    # --- 3. CECT Attention ---
    attn_module = MultiHeadSelfAttentionNumPy(d_model=d_model, n_heads=2)
    t_start = time.perf_counter()
    for _ in range(iterations):
        _ = attn_module.forward(token_block_test)
    t_end = time.perf_counter()

    attn_avg_us = ((t_end - t_start) / iterations) * 1_000_000
    print(f"  CECT Multi-Head Attention   : {attn_avg_us:7.2f} us | Limit: {TARGET_CECT_ATTN_US} us")
    if attn_avg_us > TARGET_CECT_ATTN_US:
        print("  FAILURE: Transformer core attention layer allocation leak.")
        failures += 1

    # --- Result ---
    print("=" * 70)
    if failures == 0:
        total_frame_latency = cholesky_avg_us + riemannian_avg_us + attn_avg_us
        max_theoretical_hz = 1 / (total_frame_latency / 1_000_000)
        print(f"SUCCESS: All runtime performance metrics pass.")
        print(f"Total frame latency: {total_frame_latency:.1f} us")
        print(f"Theoretical Max Engine Throughput: {max_theoretical_hz:.1f} Hz")
        print("=" * 70)
        sys.exit(0)
    else:
        print(f"CRITICAL REGRESSION DETECTED: {failures} modules failed requirements bounds check.")
        print("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    run_ci_profiling_matrix()
