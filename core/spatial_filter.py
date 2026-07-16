import numpy as np
import scipy.linalg


class CSP:
    def __init__(self, n_components=4):
        self.n_components = n_components
        self.filters_ = None
        self.patterns_ = None

    def fit(self, X, y):
        classes = np.unique(y)
        if len(classes) != 2:
            raise ValueError("CSP requires exactly 2 classes")
        covs = []
        for c in classes:
            trials = X[y == c]
            n_trials = trials.shape[0]
            sigma = np.zeros((trials.shape[1], trials.shape[1]), dtype=np.float64)
            for t in range(n_trials):
                trial = trials[t]
                sigma += trial @ trial.T / trial.shape[1]
            covs.append(sigma / n_trials)
        eigenvalues, eigenvectors = scipy.linalg.eigh(covs[0], covs[0] + covs[1])
        n = self.n_components // 2
        idx = np.concatenate([np.arange(n), np.arange(len(eigenvalues) - n, len(eigenvalues))])
        self.filters_ = eigenvectors[:, idx].T
        inv_filters = np.linalg.pinv(eigenvectors)
        self.patterns_ = inv_filters[:, idx].T

    def transform(self, X, n_components=None):
        W = self.filters_
        if n_components is not None:
            W = W[:n_components]
        X_csp = np.tensordot(X, W.T, axes=1)
        features = np.log(np.maximum(np.var(X_csp, axis=2), 1e-10))
        return features

    def project(self, X):
        return self.filters_ @ X

    def compute_inverse_topography(self, composite_covariance):
        if self.filters_ is None:
            raise ValueError("Train CSP before computing topography")
        W_sig_WT = self.filters_ @ composite_covariance @ self.filters_.T
        inv_proj = np.linalg.inv(W_sig_WT)
        A = composite_covariance @ self.filters_.T @ inv_proj
        return A


def generate_component_scalp_map(A, component_index=0):
    raw = A[:, component_index]
    peak = np.max(np.abs(raw))
    if peak > 1e-8:
        return raw / peak
    return raw


class CommonSpatialPatterns:
    def __init__(self, n_components=4):
        self.n_components = n_components
        self.W = None

    def fit(self, init_buffer, labels):
        X = np.array(init_buffer)
        if X.ndim == 3 and X.shape[2] < X.shape[1]:
            X = X.transpose(0, 2, 1)
        labels = np.array(labels)
        class_0 = X[labels == 0]
        class_1 = X[labels == 1]
        cov_0 = np.mean([np.cov(trial) for trial in class_0], axis=0)
        cov_1 = np.mean([np.cov(trial) for trial in class_1], axis=0)
        eigenvalues, eigenvectors = scipy.linalg.eigh(cov_0, cov_0 + cov_1)
        sort_idx = np.argsort(eigenvalues)[::-1]
        eigenvectors = eigenvectors[:, sort_idx]
        half = self.n_components // 2
        selected = np.hstack((
            eigenvectors[:, :half],
            eigenvectors[:, -half:]
        ))
        self.W = selected.T

    def transform(self, x_raw):
        if self.W is None:
            raise ValueError("CSP not calibrated")
        return self.W @ x_raw

    def compute_inverse_topography(self, composite_covariance):
        if self.W is None:
            raise ValueError("Train CSP before computing topography")
        W_sig_WT = self.W @ composite_covariance @ self.W.T
        inv_proj = np.linalg.inv(W_sig_WT)
        A = composite_covariance @ self.W.T @ inv_proj
        return A
