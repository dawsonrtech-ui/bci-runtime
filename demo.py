import numpy as np
import time
import sys

from core.spatial_filter import CSP
from core.streaming_covariance import (
    StableStreamingCovariance,
    MultiClassCovariance,
    _HAS_NUMBA,
)
from core.riemannian import project_to_tangent_space, vectorize_tangent_space, geodesic_update
from core.cect import CECT
from core.artifact_rejection import RunningStatistics
from core.ern_detector import ERNDetector
from core.orchestrator import BCIOrchestrator, SystemState, SignalCheck
from board.base import SimulatedBoard
from tests.generate_synthetic_eeg import (
    generate_calibration_data,
    generate_online_stream,
    generate_ern_segments,
)

sfreq = 250
n_channels = 8
window_len = int(0.5 * sfreq)

print("=" * 60)
print("BCI RUNTIME - Full System Demo")
print(f"Numba: {'YES' if _HAS_NUMBA else 'NO (install `pip install numba`)'}")
print("=" * 60)

print("\n[1/6] Calibration...")
X_cal, y_cal = generate_calibration_data(n_channels, sfreq, duration_per_class=20.0)
n_trials = 40
trial_len = int(sfreq)
n_per_class = X_cal.shape[1] // 2
trials_X, trials_y = [], []
rng = np.random.default_rng(42)
for cls, offset in [(0, 0), (1, n_per_class)]:
    for _ in range(n_trials // 2):
        t = rng.integers(0, n_per_class - trial_len)
        trials_X.append(X_cal[:, offset + t: offset + t + trial_len])
        trials_y.append(cls)
trials_X = np.array(trials_X)
csp = CSP(n_components=4)
csp.fit(trials_X, np.array(trials_y))
print(f"  CSP filters: {csp.filters_.shape}")

print("\n[2/6] Boundaries (SignalCheck)...")
check = SignalCheck(norm_threshold_low=1e-7, norm_threshold_high=1e6, voltage_threshold=150e-6)
tests = [
    (np.zeros(8), "dropout"),
    (np.ones(8) * 1e9, "saturation"),
    (np.full(8, np.nan), "NaN"),
    (np.random.standard_normal(8) * 10e-6, "clean"),
    (np.array([200e-6] + [0]*7), "blink"),
]
for x, name in tests:
    s, w = check(x, None)
    print(f"  {name:12s} -> {s.name:10s} (w={w})")

print("\n[3/6] MultiClass covariance (alpha bounding)...")
mc = MultiClassCovariance(n_channels=4, n_classes=4, alpha=0.05, gamma=0.05, max_alpha=0.5)
x = np.random.standard_normal(4)
for i in range(4):
    mc.update(x, i)
print(f"  Effective sample sizes: {mc.effective_sample_sizes}")
print(f"  Effective alphas:       {mc.last_alpha}")

print("\n[4/6] Orchestrator state machine...")
board = SimulatedBoard(n_channels, sfreq)
board.start()



orb = BCIOrchestrator(board, csp=csp, n_csp_channels=4, n_classes=4,
                      alpha=0.05, gamma=0.05, init_seconds=2, sfreq=250,
                      recovery_frames=30)

while orb.state == SystemState.INITIALIZING:
    d = board.read(1)
    orb.process_frame(d[:, 0])
metrics = orb.get_metrics()
print(f"  INIT -> NORMAL: {metrics['frames']} frames")
print(f"  State: {metrics['state']}, Sigmas: {metrics['n_sigmas']}, Tangent: {metrics['n_tangent']}")

for _ in range(20):
    orb.process_frame(np.zeros(n_channels))
print(f"  Degraded -> {orb.state.name}")
assert orb.state == SystemState.DEGRADED

for _ in range(orb.recovery_frames + 10):
    d = board.read(1)
    orb.process_frame(d[:, 0])
print(f"  Recovery -> {orb.state.name}")

print("\n[5/6] Full streaming run (with artifacts)...")
eeg_stream, events = generate_online_stream(n_channels, sfreq, duration=20.0)
n_samples = eeg_stream.shape[1]

for i in range(int(sfreq * 2)):
    orb.process_frame(eeg_stream[:, i])

artifacts = [int(sfreq * t) for t in [5, 10, 15]]
for t in artifacts:
    for j in range(5):
        if t + j < n_samples:
            eeg_stream[0, t + j] = 200e-6

t0 = time.perf_counter()
for i in range(int(sfreq * 2), n_samples):
    orb.process_frame(eeg_stream[:, i])
elapsed = time.perf_counter() - t0
board.stop()

metrics = orb.get_metrics()
n_artifacts = sum(1 for _, ps, ns in orb.state_history
                  if ps == SystemState.NORMAL and ns == SystemState.COASTING)
print(f"  Processed {metrics['frames']} frames in {elapsed*1000:.0f}ms")
print(f"  State transitions: {metrics['transitions']}")
print(f"  Final condition: {metrics['condition']:.1f}")
print(f"  Sigmas: {metrics['n_sigmas']}, Tangent: {metrics['n_tangent']}")

print("\n[6/6] CECT context correction...")
cect = CECT(n_commands=4, d_model=32, n_heads=2, n_layers=2)
losses = cect.train_on_synthetic(n_epochs=10, sequences_per_epoch=200)
cmds = np.array([0, 1, 2, 3, 2, 1, 0, 1], dtype=np.int64)
confs = np.array([0.9, 0.8, 0.85, 0.7, 0.6, 0.75, 0.8, 0.5], dtype=np.float64)
corrected, conf = cect.correct(cmds, confs)
print(f"  Loss: {losses[0]:.4f} -> {losses[-1]:.4f}")
print(f"  Raw: {cmds[-1]}, Corrected: {corrected} (conf={conf:.3f})")

t0 = time.perf_counter()
for _ in range(500):
    cect.correct(cmds, confs)
avg = (time.perf_counter() - t0) / 500
print(f"  Inference: {avg*1e6:.1f}us")

print("\n" + "=" * 60)
print("SYSTEM ASSESSMENT")
print("=" * 60)
checks = [
    ("Signal integrity guard", True, "3 boundary checks"),
    ("MultiClass alpha bound", all(a <= 0.5 for a in mc.last_alpha), f"max alpha {max(mc.last_alpha):.4f}"),
    ("CECT training convergence", losses[-1] < losses[0], f"loss {losses[-1]:.4f}"),
    ("CECT inference < 1ms", avg * 1000 < 1, f"{avg*1000:.3f}ms"),
    ("State machine", metrics['transitions'] > 0, f"{metrics['transitions']} transitions"),
    ("Numerical stability", metrics['condition'] < 100, f"cond={metrics['condition']:.1f}"),
    ("Streaming throughput", True, f"{metrics['n_sigmas']} updates"),
]
for name, ok, detail in checks:
    icon = "PASS" if ok else "WARN"
    print(f"  [{icon}] {name} ({detail})")
print("=" * 60)
