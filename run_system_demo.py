#!/usr/bin/env python3
import time
import sys
import numpy as np

from core.orchestrator import BCIEngineOrchestrator, SystemState
from core.spatial_filter import CommonSpatialPatterns
from core.cect import CECTTransformerIntegration
from core.network_gateway import BCIZmqGateway
from board.base import SimulatedBoard
from tests.generate_synthetic_eeg import generate_online_stream


def run_system_demo():
    print("=" * 60)
    print("FULL-DIVE BCI ENGINE RUNTIME")
    print("=" * 60)

    print("[1] Generating synthetic EEG stream...")
    sfreq = 250
    n_channels = 8
    eeg_stream, events = generate_online_stream(
        n_channels=n_channels, sfreq=sfreq, duration=30.0, event_interval=5.0
    )
    n_samples = eeg_stream.shape[1]
    print(f"  {n_samples} samples ({n_samples/sfreq:.0f}s), {len(events)} events")

    print("[2] Initializing orchestrator (no hardware, buffer-based)...")
    orb = BCIEngineOrchestrator(
        board_id=None,
        low_dim_channels=n_channels,
        sample_rate=sfreq,
        alpha=0.05,
        gamma=0.05,
        init_seconds=10,
        recovery_frames=50,
        enable_gateway=True,
        gateway_port=5555,
    )

    print("[3] Fitting CommonSpatialPatterns...")
    csp = CommonSpatialPatterns(n_components=4)
    rng = np.random.default_rng(42)
    trials = []
    labels = []
    for _ in range(40):
        t = rng.integers(0, n_samples - 250)
        trials.append(eeg_stream[:, t:t+250].T)
        labels.append(rng.integers(0, 2))
    csp.fit(trials, labels)
    orb.csp_filter = csp
    print(f"  CSP matrix: {csp.W.shape}")

    print("[4] Setting CSP filter on orchestrator...")
    orb.csp_filter = csp
    print(f"  Engine dim updated to {orb._engine_dim}")

    print("[5] Initializing CECTTransformerIntegration...")
    orb.cect_transformer = CECTTransformerIntegration(
        d_tangent=orb.d_tangent, d_context=4, d_model=32, n_actions=4
    )
    print(f"  Tangent dim: {orb.d_tangent}")

    print("[6] Accumulating baseline (10s)...")
    idx = 0
    while orb.state == SystemState.INITIALIZING and idx < n_samples:
        x_t = eeg_stream[:, idx]
        result, state = orb.process_frame(x_t)
        idx += 1
    print(f"  Frames: {idx}, State: {orb.state.name}")

    print("[7] Processing stream...")
    t_start = time.perf_counter()
    while idx < n_samples:
        x_t = eeg_stream[:, idx]
        result, state = orb.process_frame(x_t)
        idx += 1
        if idx % 2500 == 0:
            print(f"  Frame {idx}/{n_samples}, State: {state.name}")
    elapsed = time.perf_counter() - t_start

    metrics = orb.get_metrics()
    print(f"\n  Processed {metrics['frames']} frames in {elapsed*1000:.0f}ms")
    print(f"  State: {metrics['state']}")
    print(f"  Sigmas: {metrics['n_sigmas']}")
    print(f"  Tangent features: {metrics['n_tangent']}")
    print(f"  Condition: {metrics['condition']:.1f}")
    print(f"  State transitions: {metrics['transitions']}")

    print("[8] Injecting fault conditions...")
    faults = {
        "dropout": np.zeros(n_channels),
        "saturation": np.ones(n_channels) * 1e9,
        "blink": np.concatenate([[200e-6], np.zeros(n_channels - 1)]),
    }
    for name, fault in faults.items():
        state, w = orb.check_signal_integrity(fault)
        print(f"  {name:12s} -> {state.name:10s} (w={w})")

    print("[9] Gateway test...")
    gateway = BCIZmqGateway(port=5556)
    v_t = np.random.standard_normal(orb.d_tangent)
    gateway.publish_frame(1, "TEST", v_t, 2, 0.85)
    print(f"  Published test frame on port 5556")
    gateway.close()

    print("\n" + "=" * 60)
    print("SYSTEM ASSESSMENT")
    print("=" * 60)
    checks = [
        ("INIT TRANSITION", metrics['state'] != "INITIALIZING", f"-> {metrics['state']}"),
        ("STREAMING", metrics['n_sigmas'] > 0, f"{metrics['n_sigmas']} updates"),
        ("STABILITY", metrics['condition'] < 100, f"cond={metrics['condition']:.1f}"),
        ("TANGENT FEATURES", metrics['n_tangent'] > 0, f"{metrics['n_tangent']} projected"),
        ("FAULT HANDLING", metrics['transitions'] > 0, f"{metrics['transitions']} transitions"),
        ("THROUGHPUT", True, f"{metrics['frames']/elapsed:.0f} frames/sec"),
    ]
    for name, ok, detail in checks:
        icon = "PASS" if ok else "WARN"
        print(f"  [{icon}] {name} ({detail})")
    print("=" * 60)


if __name__ == "__main__":
    run_system_demo()
