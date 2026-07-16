import os
import numpy as np
import time
from enum import Enum

from core.streaming_covariance import (
    StableStreamingCovariance,
    MultiClassCovariance,
    _HAS_NUMBA,
)
from core.riemannian import (
    project_to_tangent_space,
    vectorize_tangent_space,
    geodesic_update,
    matrix_power,
    matrix_exp,
    frechet_mean,
)
from core.artifact_rejection import RunningStatistics
from core.cect import CECTTransformerIntegration
from core.profile_manager import BCIProfileManager
from core.voting_ensemble import TemporalVotingEnsemble
from core.motor_gate import MotorGateController


class SystemState(Enum):
    INITIALIZING = 1
    NORMAL = 2
    COASTING = 3
    DEGRADED = 4


def _default_check_signal_integrity(x, norm_low=1e-7, norm_high=1e6, voltage=150e-6, z_threshold=4.5, running_stats=None):
    x = np.asarray(x, dtype=np.float64).flatten()
    norm = np.linalg.norm(x)
    if norm > norm_high or norm < norm_low or np.any(np.isnan(x)) or np.any(np.isinf(x)):
        return SystemState.DEGRADED, 0.0
    if np.any(np.abs(x) > voltage):
        return SystemState.COASTING, 0.0
    if running_stats is not None and running_stats.filled:
        z = running_stats.z_score(x)
        if np.any(np.abs(z) > z_threshold):
            return SystemState.COASTING, 0.0
    return SystemState.NORMAL, 1.0


class BCIEngineOrchestrator:
    def __init__(self, board_id=None, low_dim_channels=8, sample_rate=250,
                 alpha=0.05, gamma=0.05, n_classes=4, init_seconds=10,
                 recovery_frames=50, entropy_threshold=0.8, entropy_window_sec=2.0,
                 enable_gateway=False, gateway_port=5555, gateway_host="127.0.0.1",
                 health_port=5557, amplitude_max=500e-6,
                 enable_tve=True, tve_window=12, tve_confidence=0.75, tve_entropy_floor=0.4,
                 initialize_lazy=False):

        self.n_channels = low_dim_channels
        self.sample_rate = sample_rate
        self.alpha = alpha
        self.gamma = gamma
        self.n_classes = n_classes
        self.recovery_frames = recovery_frames
        self.entropy_threshold = entropy_threshold
        self.entropy_window = int(sample_rate * entropy_window_sec)
        self._engine_dim = low_dim_channels

        self.state = SystemState.INITIALIZING
        self.state_history = []
        self.frame_count = 0

        self.init_required_samples = int(sample_rate * init_seconds)
        self.init_buffer = []
        self.consecutive_clean = 0
        self.default_action = 0
        self.entropy_buffer = []
        self._csp_filter = None

        self.cov_engine = StableStreamingCovariance(self._engine_dim, self.alpha, self.gamma)
        self.multi_cov = MultiClassCovariance(self._engine_dim, self.n_classes, self.alpha, self.gamma)
        self.running_stats = RunningStatistics(self.n_channels, int(self.sample_rate))
        self.Sigma_ref = None
        self.cect_transformer = None
        self.sigmas = []
        self.tangent_features = []
        self.last_action = 0
        self.last_confidence = 0.0
        self.last_p_error = 0.0
        self.amplitude_max = amplitude_max
        self._clip_count = 0
        self._start_time = time.time()

        # Network gateway
        self.gateway = None
        if enable_gateway:
            from core.network_gateway import BCIZmqGateway
            self.gateway = BCIZmqGateway(port=gateway_port, host=gateway_host, health_port=health_port)

        # Temporal Voting Ensemble
        self.tve = None
        if enable_tve:
            self.tve = TemporalVotingEnsemble(
                window_size=tve_window,
                confidence_threshold=tve_confidence,
                entropy_floor=tve_entropy_floor,
            )

        # Hardware board
        self.board = None
        if board_id is not None:
            self._init_board(board_id)

        # Motor gate fail-safe
        self.motor_gate = MotorGateController()

        # Lazy init: skip calibration for cluster worker nodes
        if initialize_lazy:
            self.init_required_samples = 0
            self.state = SystemState.NORMAL

    def initialize_session_profile(self, profile_path=None, user_id="Player1"):
        if profile_path and os.path.exists(profile_path):
            csp_w, s_ref = BCIProfileManager.load_user_profile(profile_path)
            if self._csp_filter is not None:
                self._csp_filter.W = csp_w
            self.Sigma_ref = s_ref
            self.state = SystemState.NORMAL
            print(f"Profile injected. Bypassing calibration for {user_id}.")
        else:
            self.state = SystemState.INITIALIZING
            print("No profile found. Starting baseline calibration.")

    @property
    def csp_filter(self):
        return self._csp_filter

    @property
    def d_tangent(self):
        d = self._engine_dim
        return d * (d + 1) // 2

    @csp_filter.setter
    def csp_filter(self, value):
        self._csp_filter = value
        if value is not None and hasattr(value, 'W'):
            n_csp = value.W.shape[0]
            if n_csp != self._engine_dim:
                self._engine_dim = n_csp
                self.cov_engine = StableStreamingCovariance(n_csp, self.alpha, self.gamma)
                self.multi_cov = MultiClassCovariance(n_csp, self.n_classes, self.alpha, self.gamma)

    def _init_board(self, board_id):
        try:
            from brainflow.board_shim import BoardShim, BrainFlowInputParams
            from brainflow.board_ids import BoardIds
            params = BrainFlowInputParams()
            try:
                board_id_val = board_id.value if hasattr(board_id, 'value') else board_id
            except AttributeError:
                board_id_val = board_id
            try:
                bf_id = BoardIds(board_id_val)
            except Exception:
                bf_id = board_id_val
            self.board = BoardShim(bf_id, params)
        except Exception:
            print("BrainFlow not available. Use SimulatedBoard for testing.")
            self.board = None

    def check_signal_integrity(self, x):
        return _default_check_signal_integrity(x, running_stats=self.running_stats)

    def build_initial_reference_mean(self):
        X_init = np.array(self.init_buffer)
        n_dim = X_init.shape[1]
        window = int(self.sample_rate)
        n_chunks = len(X_init) // window
        covs = []
        for c in range(n_chunks):
            chunk = X_init[c * window: (c + 1) * window].T
            P = np.cov(chunk)
            P = 0.95 * P + 0.05 * (np.trace(P) / n_dim) * np.eye(n_dim)
            covs.append(P)
        self.Sigma_ref = frechet_mean(covs, max_iter=10, tol=1e-5)
        self.state = SystemState.NORMAL

    def project_to_tangent_space(self, Sigma_t, Sigma_ref):
        return project_to_tangent_space(Sigma_t, Sigma_ref)

    def vectorize_tangent_space(self, T):
        return vectorize_tangent_space(T)

    def update_geodesic_reference_mean(self, Sigma_t, eta_t):
        T = project_to_tangent_space(Sigma_t, self.Sigma_ref)
        scaled_step = eta_t * T
        self.Sigma_ref = geodesic_update(self.Sigma_ref, Sigma_t, eta=eta_t)

    def _running_mean_entropy(self):
        if len(self.entropy_buffer) < self.entropy_window // 2:
            return 0.0
        return float(np.mean(self.entropy_buffer[-self.entropy_window:]))

    def process_frame(self, raw_sample, context=None):
        self.frame_count += 1
        raw = np.asarray(raw_sample, dtype=np.float64).flatten()
        clipped = np.clip(raw, -self.amplitude_max, self.amplitude_max)
        if self._clip_count < 10 and np.any(np.abs(raw) > self.amplitude_max * 0.9999):
            self._clip_count += 1
            if self._clip_count == 1:
                print(f"[WARN] Amplitude clipped at ±{self.amplitude_max*1e6:.0f} µV")
        raw = clipped
        self.running_stats.update(raw)

        frame_state, w_t = self.check_signal_integrity(raw)

        if self.state == SystemState.INITIALIZING:
            if self._csp_filter is not None:
                x_proj = self._csp_filter.transform(raw)
            else:
                x_proj = raw[:self._engine_dim]
            self.init_buffer.append(x_proj)
            if len(self.init_buffer) >= self.init_required_samples:
                self.build_initial_reference_mean()
            return None, self.state

        prev = self.state
        if frame_state == SystemState.DEGRADED:
            self.state = SystemState.DEGRADED
            self.consecutive_clean = 0
        elif frame_state == SystemState.COASTING:
            if self.state == SystemState.NORMAL:
                self.state = SystemState.COASTING
            self.consecutive_clean = 0
        else:
            self.consecutive_clean += 1
            if self.state == SystemState.DEGRADED and self.consecutive_clean >= self.recovery_frames:
                self.state = SystemState.NORMAL
            elif self.state == SystemState.COASTING:
                self.state = SystemState.NORMAL
        if prev != self.state:
            self.state_history.append((self.frame_count, prev, self.state))

        if self.state == SystemState.DEGRADED:
            if self.tve is not None:
                self.tve.reset()
            return self.default_action, self.state

        weight = w_t if self.state == SystemState.NORMAL else 0.0
        if self.csp_filter is not None:
            x = self.csp_filter.transform(raw)
        else:
            x = raw[:self.n_channels]

        Sigma_t = self.cov_engine.update(x, weight=weight)
        self.sigmas.append(Sigma_t)

        if self.Sigma_ref is not None:
            v_t = vectorize_tangent_space(project_to_tangent_space(Sigma_t, self.Sigma_ref))
            self.tangent_features.append(v_t)
        else:
            v_t = None

        if self.cect_transformer is not None and v_t is not None:
            ctx = np.zeros(4, dtype=np.float64)
            action, conf, p_err = self.cect_transformer.forward(v_t, ctx)
        else:
            action, conf, p_err = 0, 0.0, 0.0

        # Temporal Voting Ensemble gate: only active in NORMAL
        if self.tve is not None and v_t is not None:
            if self.state == SystemState.NORMAL:
                n_actions = max(4, action + 1)
                probs = np.full(n_actions, (1.0 - conf) / (n_actions - 1))
                probs[action] = conf
                tve_action, tve_ok = self.tve.evaluate_intent(action, probs)
                if not tve_ok:
                    action = 0
                    conf = 0.0
            else:
                self.tve.reset()
                action = self.default_action
                conf = 0.0

        # Motor gate fail-safe interlock
        if context is not None:
            motor_active = context.get("motor_gating_active", True)
            in_high_stim = context.get("in_high_stimulus", False)
            self.motor_gate.update(motor_active, in_high_stim, self.frame_count)
            if self.motor_gate.force_zero:
                action = 0
                conf = 0.0
                v_t = np.zeros_like(v_t) if v_t is not None else v_t

        self.entropy_buffer.append(conf)
        rolling_entropy = self._running_mean_entropy()

        if self.state == SystemState.NORMAL:
            eta_t = 0.005 * max(0.0, 1.0 - rolling_entropy)
            if eta_t > 0 and self.Sigma_ref is not None:
                self.update_geodesic_reference_mean(Sigma_t, eta_t)

        self.last_action = action
        self.last_confidence = conf
        self.last_p_error = p_err

        if self.gateway is not None and v_t is not None:
            self.gateway.publish_frame(
                self.frame_count, self.state.name, v_t, action, conf
            )

        return v_t, self.state

    def step(self, raw_sample, game_context=None):
        self.process_frame(raw_sample, context=game_context)
        return self.last_action, self.last_confidence, self.last_p_error

    def get_health_status(self):
        return {
            "status": "ok",
            "version": "0.1.0",
            "state": self.state.name,
            "uptime_sec": time.time() - self._start_time,
            "frame_count": self.frame_count,
            "clip_count": self._clip_count,
            "n_sigmas": len(self.sigmas),
            "n_tangent": len(self.tangent_features),
            "condition": float(np.linalg.cond(self.sigmas[-1])) if self.sigmas else 0.0,
            "gateway": self.gateway is not None,
            "board_attached": self.board is not None,
            "motor_gate": self.motor_gate.get_status(),
        }

    def get_metrics(self):
        cond = np.linalg.cond(self.sigmas[-1]) if self.sigmas else 0.0
        return {
            "frames": self.frame_count,
            "state": self.state.name,
            "n_sigmas": len(self.sigmas),
            "n_tangent": len(self.tangent_features),
            "condition": float(cond),
            "transitions": len(self.state_history),
            "init_buffer": len(self.init_buffer),
        }
