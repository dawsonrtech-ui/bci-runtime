import numpy as np


class RunningStatistics:
    def __init__(self, n_channels, window=256):
        self.n = n_channels
        self.window = window
        self.buffer = np.zeros((window, n_channels), dtype=np.float64)
        self.mean = np.zeros(n_channels, dtype=np.float64)
        self.var = np.ones(n_channels, dtype=np.float64)
        self.idx = 0
        self.filled = False

    def update(self, x):
        self.buffer[self.idx] = x
        self.idx = (self.idx + 1) % self.window
        if not self.filled and self.idx == 0:
            self.filled = True
        if self.filled:
            self.mean = np.mean(self.buffer, axis=0)
            self.var = np.var(self.buffer, axis=0) + 1e-10

    def z_score(self, x):
        return (x - self.mean) / np.sqrt(self.var)

    def is_artifact(self, x, threshold=3.0):
        z = self.z_score(x)
        return np.any(np.abs(z) > threshold)


def detect_blinks(x, threshold=150e-6):
    frontal_channels = x[:2]
    return np.any(np.abs(frontal_channels) > threshold)
