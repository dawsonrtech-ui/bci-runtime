import numpy as np
import scipy.linalg

try:
    from numba import njit
    _HAS_NUMBA = True
except ImportError:
    _HAS_NUMBA = False


def _rank1_givens_python(L, v):
    n = L.shape[0]
    for i in range(n):
        r = np.hypot(L[i, i], v[i])
        c = L[i, i] / r if r > 1e-15 else 0.0
        s = v[i] / r if r > 1e-15 else 0.0
        L[i, i] = r
        if i + 1 < n:
            L_i = L[i+1:, i].copy()
            v_i = v[i+1:].copy()
            L[i+1:, i] = c * L_i + s * v_i
            v[i+1:] = -s * L_i + c * v_i


if _HAS_NUMBA:
    @njit(cache=True)
    def _rank1_givens_numba(L, v):
        n = L.shape[0]
        for i in range(n):
            r = np.sqrt(L[i, i]**2 + v[i]**2)
            c = L[i, i] / r if r > 1e-15 else 0.0
            s = v[i] / r if r > 1e-15 else 0.0
            L[i, i] = r
            if i + 1 < n:
                for j in range(i + 1, n):
                    L_j = L[j, i]
                    v_j = v[j]
                    L[j, i] = c * L_j + s * v_j
                    v[j] = -s * L_j + c * v_j
    _rank1_givens = _rank1_givens_numba
else:
    _rank1_givens = _rank1_givens_python


class StableStreamingCovariance:
    def __init__(self, n_channels, alpha=0.05, gamma=0.05):
        self.n = n_channels
        self.alpha = alpha
        self.gamma = gamma
        self.reset()

    @property
    def effective_sample_size(self):
        return 1.0 / max(self.alpha, 1e-10)

    def _mahalanobis_scale(self, x):
        if self.t < 2:
            return x
        y = scipy.linalg.solve_triangular(self.L, x, lower=True)
        d2 = y @ y
        if d2 > 9.0:
            return x * (3.0 / np.sqrt(d2))
        return x

    def update(self, x, weight=1.0):
        x = np.asarray(x, dtype=np.float64).flatten()
        if x.shape[0] != self.n:
            raise ValueError(f"Expected {self.n} channels, got {x.shape[0]}")
        self.t += 1
        delta = x - self.x_mean
        self.x_mean += delta / self.t
        x_centered = x - self.x_mean
        x_scaled = self._mahalanobis_scale(x_centered)
        a = min(self.alpha * weight, 0.5)
        sqrt_one_minus_a = np.sqrt(1.0 - a)
        sqrt_a = np.sqrt(a)
        self.L *= sqrt_one_minus_a
        v = sqrt_a * x_scaled.copy()
        _rank1_givens(self.L, v)
        Sigma = self.L @ self.L.T
        trace_scaled = (np.trace(Sigma) / self.n) * np.eye(self.n)
        return (1.0 - self.gamma) * Sigma + self.gamma * trace_scaled

    def reset(self):
        self.L = np.eye(self.n, dtype=np.float64)
        self.t = 0
        self.x_mean = np.zeros(self.n, dtype=np.float64)

    def get_covariance(self, shrunk=True):
        Sigma = self.L @ self.L.T
        if shrunk:
            trace_scaled = (np.trace(Sigma) / self.n) * np.eye(self.n)
            return (1.0 - self.gamma) * Sigma + self.gamma * trace_scaled
        return Sigma


class MultiClassCovariance:
    def __init__(self, n_channels, n_classes, alpha=0.05, gamma=0.05, max_alpha=0.5):
        self.n_classes = n_classes
        self.alpha_base = alpha
        self.gamma = gamma
        self.max_alpha = max_alpha
        self.n_channels = n_channels
        self.reset()

    def update(self, x, class_id, weight=1.0):
        if class_id < 0 or class_id >= self.n_classes:
            raise ValueError(f"class_id must be 0-{self.n_classes - 1}")
        self.counts[class_id] += 1.0
        total = max(self.counts.sum(), 1.0)
        freq = self.counts[class_id] / total
        alpha_boost = (2.0 - freq)
        alpha_eff = min(self.alpha_base * alpha_boost, self.max_alpha)
        self.last_alpha[class_id] = alpha_eff
        balanced_weight = weight * alpha_boost
        return self.covs[class_id].update(x, balanced_weight)

    @property
    def effective_sample_sizes(self):
        return np.array([1.0 / max(a, 1e-10) for a in self.last_alpha])

    def get_covariance(self, class_id, shrunk=True):
        return self.covs[class_id].get_covariance(shrunk)

    def all_covariances(self, shrunk=True):
        return [c.get_covariance(shrunk) for c in self.covs]

    def reset(self):
        self.covs = [StableStreamingCovariance(self.n_channels, self.alpha_base, self.gamma)
                     for _ in range(self.n_classes)]
        self.counts = np.zeros(self.n_classes, dtype=np.float64)
        self.last_alpha = np.full(self.n_classes, self.alpha_base)

    def reset_class(self, class_id):
        self.covs[class_id] = StableStreamingCovariance(self.n_channels, self.alpha_base, self.gamma)
        self.counts[class_id] = 0.0
        self.last_alpha[class_id] = self.alpha_base
