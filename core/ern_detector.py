import numpy as np


class ERNDetector:
    def __init__(self, n_channels, sfreq=250):
        self.sfreq = sfreq
        self.n_channels = n_channels
        self.window_len = int(0.4 * sfreq)
        self.template = self._make_template()
        self.mu_correct = 0.0
        self.sigma_correct = 1.0
        self.mu_error = -1.5
        self.sigma_error = 1.5
        self.beta0 = 0.0
        self.beta1 = 1.0
        self._calibrated = False

    def _make_template(self):
        t = np.linspace(0, 0.4, self.window_len)
        template = -np.exp(-((t - 0.2) ** 2) / (2 * 0.05**2))
        template[:int(0.05 * self.sfreq)] = 0
        template[int(0.35 * self.sfreq):] = 0
        return template / np.linalg.norm(template)

    def calibrate(self, correct_signals, error_signals):
        correct_scores = np.array([self._score_window(s) for s in correct_signals])
        error_scores = np.array([self._score_window(s) for s in error_signals])
        self.mu_correct = np.mean(correct_scores)
        self.sigma_correct = np.std(correct_scores) + 1e-10
        self.mu_error = np.mean(error_scores)
        self.sigma_error = np.std(error_scores) + 1e-10
        self.beta1 = (self.mu_error - self.mu_correct) / (self.sigma_error ** 2 + 1e-10)
        self.beta0 = (self.mu_correct / self.sigma_correct ** 2 - self.mu_error / self.sigma_error ** 2) * self.beta1
        self._calibrated = True

    def _score_window(self, X_ern):
        fc = 0
        fc_idx = min(self.n_channels // 2, 2)
        for c in range(fc_idx):
            fc += np.correlate(X_ern[c], self.template, mode='valid')[0]
        return fc / fc_idx

    def predict_error_probability(self, X_ern):
        s = self._score_window(X_ern)
        logit = self.beta0 + self.beta1 * s
        p_error = 1.0 / (1.0 + np.exp(-logit))
        return p_error

    def get_update_weight(self, X_ern, epsilon=0.05):
        if not self._calibrated:
            return 1.0
        p_error = self.predict_error_probability(X_ern)
        return max(epsilon, 1.0 - p_error)
