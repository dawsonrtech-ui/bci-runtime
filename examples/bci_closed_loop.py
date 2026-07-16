#!/usr/bin/env python3
"""Closed-loop BCI reference implementation.

Generates mock 8-channel EEG/EMG data and streams it to the SHM ring buffer
at 250 Hz.  Each channel is mapped to a frequency band (chemical_profile):

    channel  →  band       dominant freq
    0           delta       1.0 Hz
    1           theta       6.0 Hz
    2           alpha      10.0 Hz
    3           beta       20.0 Hz
    4           gamma      40.0 Hz
    5           EMG high   60.0 Hz  (muscle activity)
    6           EMG low    15.0 Hz  (mixed)
    7           ambient    50.0 Hz  (noise floor)

The intensity field represents instantaneous bandpower (0-1 range).

Usage:
    python examples/bci_closed_loop.py             # default (250 Hz, 10 s)
    python examples/bci_closed_loop.py --hz 128    # 128 Hz
    python examples/bci_closed_loop.py --duration 30  # 30 seconds
    python examples/bci_closed_loop.py --visualise # print live bandpower table
"""

import sys, os, time, math, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.shm_gustation import (
    ShmGustationProducer, GustationChannel,
    SHM_NAME, SIGNAL_NAME, RING_BUFFER_SIZE,
)

N_CHANNELS = 8
FREQ_MAP = [1.0, 6.0, 10.0, 20.0, 40.0, 60.0, 15.0, 50.0]
BASE_AMPS = [0.3, 0.2, 0.5, 0.15, 0.08, 0.05, 0.12, 0.02]


def mock_eeg_sample(t: float, channel: int) -> float:
    """Return a normalised amplitude (0-1) for one channel at time t."""
    freq = FREQ_MAP[channel]
    base = BASE_AMPS[channel]
    # Dominant sine + harmonics + noise
    raw = (base
           + 0.3 * base * math.sin(2 * math.pi * freq * t)
           + 0.1 * base * math.sin(2 * math.pi * freq * 2 * t)
           + 0.05 * base * math.sin(2 * math.pi * freq * 0.5 * t)
           + 0.02 * (hash((channel, round(t, 3))) & 0xFFFF) / 65535)
    return max(0.0, min(1.0, raw))  # clamp


def run_closed_loop(hz: int = 250, duration_s: float = 10.0,
                    visualise: bool = False):
    period = 1.0 / hz
    n_frames = int(hz * duration_s)

    with ShmGustationProducer(SHM_NAME, SIGNAL_NAME) as producer:
        producer.open()
        print(f"[BCI] Simulating {n_frames} frames at {hz} Hz "
              f"({duration_s}s)")

        t0 = time.perf_counter()
        last_print = 0.0

        for frame_id in range(n_frames):
            t = frame_id / hz
            channels = [
                GustationChannel(
                    channel_id=i,
                    intensity=round(mock_eeg_sample(t, i), 4),
                    duration_ms=round(1000 / hz, 2),
                    chemical_profile=i,
                )
                for i in range(N_CHANNELS)
            ]

            producer.write_frame(frame_id, channels)

            # Maintain precise timing
            next_t = t0 + (frame_id + 1) * period
            slip = next_t - time.perf_counter()
            if slip > 0:
                time.sleep(slip)

            # Live visualisation
            if visualise and time.perf_counter() - last_print >= 0.5:
                last_print = time.perf_counter()
                metrics = producer.get_metrics()
                _print_dashboard(frame_id, n_frames, metrics, channels)

        elapsed = time.perf_counter() - t0
        metrics = producer.get_metrics()

        print()
        print(f"[BCI] Done: {metrics['frames_written']} written, "
              f"{metrics['frames_dropped']} dropped, "
              f"{metrics['signal_triggers']} signal triggers")
        print(f"[BCI] Heartbeat: {metrics.get('producer_heartbeat', 'N/A')}")
        print(f"[BCI] Wall clock: {elapsed:.2f}s  "
              f"({metrics['frames_written'] / elapsed:.0f} fps)")


def _print_dashboard(frame_id, total, metrics, channels):
    occ = metrics.get("buffer_occupancy", 0)
    pct = 100 * frame_id / total
    sys.stdout.write(
        f"\r[{frame_id:5d}/{total} ({pct:5.1f}%)]  "
        f"occ={occ:2d}  hb={metrics.get('producer_heartbeat', 0):6d}  "
        f"sig={metrics.get('signal_triggers', 0):4d}  "
        f"bands: "
    )
    for ch in channels:
        sys.stdout.write(f"{ch.chemical_profile}:{ch.intensity:.2f} ")
    sys.stdout.flush()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Closed-loop BCI mock data stream")
    p.add_argument("--hz", type=int, default=250, help="Simulation frequency")
    p.add_argument("--duration", type=float, default=10.0, help="Duration in seconds")
    p.add_argument("--visualise", action="store_true", help="Live bandpower dashboard")
    args = p.parse_args()
    run_closed_loop(hz=args.hz, duration_s=args.duration,
                    visualise=args.visualise)
