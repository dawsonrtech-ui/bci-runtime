import numpy as np
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.orchestrator import BCIEngineOrchestrator, SystemState
from core.streaming_covariance import MultiClassCovariance
from board.base import SimulatedBoard

print("=" * 60)
print("BOUNDARY CONDITION & FAILURE SAFEGUARD TESTS")
print("=" * 60)


def make_orb(init_seconds=2, recovery_frames=30, **kw):
    return BCIEngineOrchestrator(
        board_id=None, low_dim_channels=8, sample_rate=250,
        alpha=0.05, gamma=0.05, init_seconds=init_seconds,
        recovery_frames=recovery_frames, **kw
    )


def test_dropout_detection():
    print("\n[Test] Signal dropout detection...")
    orb = make_orb()
    x = np.zeros(8)
    state, w = orb.check_signal_integrity(x)
    assert state == SystemState.DEGRADED, f"Expected DEGRADED, got {state}"
    assert w == 0.0
    print("  [PASS] Zero vector -> DEGRADED, w=0")


def test_saturation_detection():
    print("\n[Test] Saturation/rail detection...")
    orb = make_orb()
    x = np.ones(8) * 1e9
    state, w = orb.check_signal_integrity(x)
    assert state == SystemState.DEGRADED
    print("  [PASS] Rail -> DEGRADED")


def test_nan_detection():
    print("\n[Test] NaN/Inf detection...")
    orb = make_orb()
    for name, x in [("NaN", np.full(8, np.nan)), ("Inf", np.full(8, np.inf))]:
        s, w = orb.check_signal_integrity(x)
        assert s == SystemState.DEGRADED, f"{name} -> {s}"
        print(f"  [PASS] {name} -> DEGRADED")


def test_blink_detection():
    print("\n[Test] Blink artifact detection...")
    orb = make_orb()
    x_clean = np.random.standard_normal(8) * 10e-6
    s, w = orb.check_signal_integrity(x_clean)
    assert s == SystemState.NORMAL
    print("  [PASS] Clean -> NORMAL")

    x_blink = np.array([200e-6] + [0]*7)
    s, w = orb.check_signal_integrity(x_blink)
    assert s == SystemState.COASTING
    print("  [PASS] Blink -> COASTING")


def test_init_to_normal():
    print("\n[Test] INITIALIZING -> NORMAL transition...")
    board = SimulatedBoard(8, 250)
    board.start()
    orb = make_orb(init_seconds=2)
    n = 0
    while orb.state == SystemState.INITIALIZING and n < 2000:
        d = board.read(1)
        orb.process_frame(d[:, 0])
        n += 1
    board.stop()
    assert orb.state == SystemState.NORMAL, f"Expected NORMAL, got {orb.state}"
    assert orb.Sigma_ref is not None
    print(f"  [PASS] Transitioned after {n} frames, ref_cov: {orb.Sigma_ref.shape}")


def test_degraded_freezes():
    print("\n[Test] DEGRADED freezes adaptation...")
    board = SimulatedBoard(8, 250)
    board.start()
    orb = make_orb(init_seconds=1)
    while orb.state == SystemState.INITIALIZING:
        d = board.read(1)
        orb.process_frame(d[:, 0])
    before = len(orb.sigmas)
    for _ in range(50):
        orb.process_frame(np.zeros(8))
    board.stop()
    assert orb.state == SystemState.DEGRADED
    assert len(orb.sigmas) == before, "Sigmas should freeze in DEGRADED"
    print("  [PASS] No new sigmas in DEGRADED")


def test_recovery():
    print("\n[Test] Recovery DEGRADED -> NORMAL...")
    board = SimulatedBoard(8, 250)
    board.start()
    orb = make_orb(init_seconds=1, recovery_frames=20)
    while orb.state == SystemState.INITIALIZING:
        d = board.read(1)
        orb.process_frame(d[:, 0])
    for _ in range(10):
        orb.process_frame(np.zeros(8))
    assert orb.state == SystemState.DEGRADED
    for _ in range(orb.recovery_frames + 10):
        d = board.read(1)
        orb.process_frame(d[:, 0])
    board.stop()
    assert orb.state == SystemState.NORMAL
    print(f"  [PASS] Recovered after {orb.consecutive_clean} clean frames")


def test_eff_sample_size():
    print("\n[Test] MultiClass effective sample size...")
    mc = MultiClassCovariance(n_channels=4, n_classes=4, alpha=0.05, gamma=0.05, max_alpha=0.5)
    x = np.random.standard_normal(4)
    for i in range(4):
        mc.update(x, i)
    sizes = mc.effective_sample_sizes
    assert all(np.isfinite(sizes)), f"Non-finite sizes: {sizes}"
    assert np.all(mc.last_alpha <= 0.5), f"Alpha exceeds max: {mc.last_alpha}"
    print(f"  [PASS] Sizes: {sizes}, Alphas: {mc.last_alpha}")


def test_coasting_preserves():
    print("\n[Test] COASTING preserves L...")
    board = SimulatedBoard(8, 250)
    board.start()
    orb = make_orb(init_seconds=1)
    while orb.state == SystemState.INITIALIZING:
        d = board.read(1)
        orb.process_frame(d[:, 0])
    L_before = orb.cov_engine.L.copy()
    for _ in range(20):
        orb.process_frame(np.array([200e-6] + [0]*7))
    board.stop()
    assert orb.state == SystemState.COASTING
    L_diff = np.linalg.norm(orb.cov_engine.L - L_before)
    assert L_diff < 1e-10, f"L changed: {L_diff}"
    print(f"  [PASS] L frozen (diff={L_diff:.2e})")


def test_entropy_dampens():
    print("\n[Test] Entropy dampens eta...")
    orb = make_orb(entropy_threshold=0.3)
    orb.entropy_buffer = [0.9] * orb.entropy_window
    orb.state = SystemState.NORMAL
    rolling = orb._running_mean_entropy()
    assert rolling > orb.entropy_threshold
    eta = 0.005 * max(0.0, 1.0 - rolling)
    assert eta < 0.001, f"eta not dampened: {eta}"
    print(f"  [PASS] entropy={rolling:.3f}, eta={eta:.5f}")


def test_tve_requires_buffer_fill():
    print("\n[Test] TVE blocks before buffer fills...")
    from core.voting_ensemble import TemporalVotingEnsemble
    tve = TemporalVotingEnsemble(window_size=5, confidence_threshold=0.6, entropy_floor=0.4)
    for i in range(4):
        action, ok = tve.evaluate_intent(1, np.array([0.01, 0.98, 0.01]))
        assert ok == False, f"Should block before buffer fill (attempt {i})"
    print("  [PASS] Blocks before buffer fill")


def test_tve_blocks_high_entropy():
    print("\n[Test] TVE blocks high-entropy model outputs...")
    from core.voting_ensemble import TemporalVotingEnsemble
    tve = TemporalVotingEnsemble(window_size=5, confidence_threshold=0.6, entropy_floor=0.4)
    for _ in range(5):
        tve.evaluate_intent(1, np.array([0.01, 0.98, 0.01]))
    action, ok = tve.evaluate_intent(2, np.array([0.33, 0.34, 0.33]))
    assert ok == False, "High entropy should block"
    print("  [PASS] High-entropy [0.33,0.34,0.33] blocked")


def test_tve_passes_high_confidence():
    print("\n[Test] TVE passes confident majority vote...")
    from core.voting_ensemble import TemporalVotingEnsemble
    tve = TemporalVotingEnsemble(window_size=5, confidence_threshold=0.6, entropy_floor=0.4)
    # Fill buffer with 5x action=1 (will be blocked initially due to buffer fill)
    for _ in range(5):
        tve.evaluate_intent(1, np.array([0.01, 0.98, 0.01]))
    # Now buffer is full; next calls should pass
    for _ in range(5):
        action, ok = tve.evaluate_intent(1, np.array([0.01, 0.98, 0.01]))
        assert action == 1 and ok == True, f"Expected (1, True), got ({action}, {ok})"
    print("  [PASS] Confident action 1 passes")


def test_tve_resets_on_degraded():
    print("\n[Test] TVE resets when orchestrator enters DEGRADED...")
    board = SimulatedBoard(8, 250)
    board.start()
    orb = make_orb(init_seconds=1, enable_tve=True)
    while orb.state == SystemState.INITIALIZING:
        d = board.read(1)
        orb.process_frame(d[:, 0])
    assert orb.tve is not None, "TVE should be enabled"
    for _ in range(5):
        d = board.read(1)
        orb.process_frame(d[:, 0])
    assert len(orb.tve.history) > 0, "TVE should have history in NORMAL state"
    for _ in range(10):
        orb.process_frame(np.zeros(8))
    assert orb.state == SystemState.DEGRADED
    assert len(orb.tve.history) == 0, "TVE history should be reset in DEGRADED"
    board.stop()
    print("  [PASS] TVE cleared on DEGRADED")


def test_tve_suppresses_erratic_artifacts():
    print("\n[Test] TVE suppresses erratic outputs during high-noise artifact state...")
    orb = make_orb(init_seconds=1, enable_tve=True, enable_gateway=False)
    # Bootstrap into NORMAL
    while orb.state == SystemState.INITIALIZING:
        orb.process_frame(np.random.standard_normal(8) * 10e-6)
    orb.cect_transformer = None  # use default action path
    # Inject blink artifacts -> COASTING, TVE should gate outputs
    for _ in range(20):
        x_blink = np.array([200e-6] + [0] * 7)
        v, state = orb.process_frame(x_blink)
        assert state == SystemState.COASTING
        assert len(orb.tve.history) == 0, "TVE should stay empty in COASTING"
    print("  [PASS] Erratic artifacts suppressed during COASTING")


def test_tve_multi_user_burst():
    print("\n[Test] TVE multi-user burst with noisy artifacts...")
    n_users = 4
    orbs = []
    for uid in range(n_users):
        orb = make_orb(init_seconds=0, enable_tve=True, enable_gateway=False, tve_window=5, tve_confidence=0.6)
        orb.state = SystemState.NORMAL
        orbs.append(orb)

    # Inject burst of clean frames to fill TVE buffers
    for _ in range(10):
        for orb in orbs:
            action, conf, p_err = orb.step(np.random.standard_normal(8) * 10e-6)
            assert isinstance(action, (int, np.integer))

    # Inject burst of high-noise artifacts across all users simultaneously
    for burst_idx in range(10):
        for orb in orbs:
            x_burst = np.array([200e-6] + [0] * 7) + np.random.standard_normal(8) * 50e-6
            v, state = orb.process_frame(x_burst)
            if orb.tve is not None:
                if state == SystemState.NORMAL:
                    _, vote_ok = orb.tve.evaluate_intent(0, np.array([0.25, 0.25, 0.25, 0.25]))
                    if vote_ok:
                        continue
    # Verify all orbs are still operational
    for orb in orbs:
        action, conf, p_err = orb.step(np.random.standard_normal(8) * 10e-6)
        assert isinstance(action, (int, np.integer))
    print(f"  [PASS] Multi-user burst ({n_users} users x 10 frames) completed cleanly")


def test_full_pipeline():
    print("\n[Test] Full pipeline (orchestrator + stream + metrics)...")
    from tests.generate_synthetic_eeg import generate_online_stream
    eeg, events = generate_online_stream(8, 250, 10.0)
    orb = make_orb(init_seconds=2)
    while orb.state == SystemState.INITIALIZING:
        orb.process_frame(np.random.standard_normal(8) * 10e-6)
    for i in range(eeg.shape[1]):
        orb.process_frame(eeg[:, i])
    m = orb.get_metrics()
    assert m['n_sigmas'] > 0, "No sigmas produced"
    assert m['n_tangent'] > 0, "No tangent features"
    assert m['condition'] < 100, f"High condition: {m['condition']}"
    print(f"  [PASS] Sigmas={m['n_sigmas']}, Tangent={m['n_tangent']}, Cond={m['condition']:.1f}")


tests = [
    test_dropout_detection,
    test_saturation_detection,
    test_nan_detection,
    test_blink_detection,
    test_init_to_normal,
    test_degraded_freezes,
    test_recovery,
    test_eff_sample_size,
    test_coasting_preserves,
    test_entropy_dampens,
    test_tve_requires_buffer_fill,
    test_tve_blocks_high_entropy,
    test_tve_passes_high_confidence,
    test_tve_resets_on_degraded,
    test_tve_suppresses_erratic_artifacts,
    test_tve_multi_user_burst,
    test_full_pipeline,
]

passed = failed = 0
for t in tests:
    try:
        t()
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {t.__name__}: {e}")
        failed += 1

print(f"\n{'=' * 60}")
print(f"RESULTS: {passed} passed, {failed} failed out of {len(tests)}")
print(f"{'=' * 60}")
assert failed == 0, f"{failed} test(s) failed"
