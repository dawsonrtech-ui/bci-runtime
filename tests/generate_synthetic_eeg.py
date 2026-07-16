import numpy as np


def pink_noise(n_samples, n_channels, alpha=1.0, seed=42):
    rng = np.random.default_rng(seed)
    white = rng.standard_normal((n_channels, n_samples))
    freqs = np.fft.rfftfreq(n_samples)
    freqs[0] = 1e-10
    scaling = 1.0 / (freqs ** (alpha / 2.0))
    spectrum = np.fft.rfft(white)
    spectrum *= scaling[np.newaxis, :]
    colored = np.fft.irfft(spectrum, n=n_samples, axis=1)
    colored /= np.std(colored, axis=1, keepdims=True)
    return colored * 1e-6


def make_channel_locations(n_channels, sfreq=250, duration=60.0):
    rng = np.random.default_rng(42)
    n = int(sfreq * duration)
    eeg = pink_noise(n, n_channels, alpha=1.0, seed=42)
    for ch in range(min(3, n_channels)):
        for _ in range(rng.poisson(2)):
            peak_time = rng.integers(0, n)
            width = int(0.1 * sfreq)
            alpha_osc = 10e-6 * np.sin(2 * np.pi * 10 * np.arange(-width, width) / sfreq)
            window = np.exp(-np.arange(-width, width) ** 2 / (2 * (width / 4) ** 2))
            to_add = np.zeros(n)
            start = max(0, peak_time - width)
            end = min(n, peak_time + width)
            to_add[start:end] = (alpha_osc * window)[:end - start]
            eeg[ch] += to_add[:n]
    return eeg


def generate_calibration_data(
    n_channels=8, sfreq=250, duration_per_class=30.0, seed=43
):
    rng = np.random.default_rng(seed)
    n_per_class = int(sfreq * duration_per_class)
    rest = make_channel_locations(n_channels, sfreq, duration_per_class)
    mu_power = np.mean(np.std(rest, axis=1))
    action = make_channel_locations(n_channels, sfreq, duration_per_class)
    for ch in range(n_channels):
        attenuation = 0.3 + 0.4 * rng.random()
        mu_beta = rng.uniform(13, 25)
        osc = 5e-6 * np.sin(2 * np.pi * mu_beta * np.arange(n_per_class) / sfreq)
        action[ch] = action[ch] * attenuation + osc
    for _ in range(int(sfreq * 0.5 / duration_per_class * 2)):
        t = rng.integers(0, n_per_class)
        w = int(0.15 * sfreq)
        if t + w < n_per_class:
            stim = 15e-6 * np.sin(2 * np.pi * 15 * np.arange(w) / sfreq)
            action[:, t:t+w] += stim
    X = np.concatenate([rest, action], axis=1)
    y = np.array([0] * n_per_class + [1] * n_per_class)
    return X, y


def generate_online_stream(
    n_channels=8, sfreq=250, duration=120.0, seed=44, event_interval=5.0
):
    rng = np.random.default_rng(seed)
    n = int(sfreq * duration)
    eeg = make_channel_locations(n_channels, sfreq, duration)
    events = []
    current = event_interval
    while current < duration:
        t = int(current * sfreq)
        w = int(0.5 * sfreq)
        if t + w < n:
            eeg[:, t:t+w] *= 0.4
            stim = 15e-6 * np.sin(2 * np.pi * 15 * np.arange(w) / sfreq)
            eeg[:, t:t+w] += stim
            events.append((current, 1))
        current += event_interval + rng.uniform(-1.0, 1.0)
    for _ in range(rng.poisson(duration / 3)):
        t = rng.integers(0, n)
        w = int(0.2 * sfreq)
        if t + w < n:
            blink = 200e-6 * np.exp(-np.arange(w) ** 2 / (2 * (w / 8) ** 2))
            for c in range(min(3, n_channels)):
                eeg[c, t:t+w] += blink * (1.0 - c * 0.3)
    return eeg, events


def generate_ern_segments(n_channels=8, sfreq=250, seed=45):
    rng = np.random.default_rng(seed)
    correct = []
    errors = []
    t = np.linspace(0, 0.4, int(0.4 * sfreq))
    for _ in range(50):
        seg = 2e-6 * rng.standard_normal((n_channels, len(t)))
        correct.append(seg)
    for _ in range(50):
        seg = 2e-6 * rng.standard_normal((n_channels, len(t)))
        fc_idx = min(n_channels // 2, 2)
        ern = -8e-6 * np.exp(-((t - 0.2) ** 2) / (2 * 0.04**2))
        for c in range(fc_idx):
            seg[c] += ern
        errors.append(seg)
    return correct, errors
