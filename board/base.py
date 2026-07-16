import numpy as np
from abc import ABC, abstractmethod


class Board(ABC):
    @abstractmethod
    def start(self):
        pass

    @abstractmethod
    def read(self, n_samples=1):
        pass

    @abstractmethod
    def stop(self):
        pass

    @property
    @abstractmethod
    def n_channels(self):
        pass

    @property
    @abstractmethod
    def sfreq(self):
        pass

    @property
    @abstractmethod
    def channel_names(self):
        pass


class SimulatedBoard(Board):
    def __init__(self, n_channels=8, sfreq=250):
        self._n_channels = n_channels
        self._sfreq = sfreq
        self._t = 0
        self._running = False
        self._noise_floor = 10e-6

    def start(self):
        self._running = True
        self._t = 0

    def read(self, n_samples=1):
        if not self._running:
            raise RuntimeError("Board not started")
        rng = np.random.default_rng(int(self._t * 1000))
        eeg = rng.standard_normal((n_samples, self._n_channels)) * self._noise_floor
        t_sec = self._t / self._sfreq
        eeg[:, 0] += 15e-6 * np.sin(2 * np.pi * 10 * t_sec)
        eeg[:, 1] += 12e-6 * np.sin(2 * np.pi * 10 * t_sec + 0.5)
        eeg[:, 3] += 8e-6 * np.sin(2 * np.pi * 20 * t_sec)
        self._t += n_samples
        return eeg.T

    def stop(self):
        self._running = False

    @property
    def n_channels(self):
        return self._n_channels

    @property
    def sfreq(self):
        return self._sfreq

    @property
    def channel_names(self):
        return [f"CH{i+1}" for i in range(self._n_channels)]
