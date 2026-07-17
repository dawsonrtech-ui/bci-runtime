#!/usr/bin/env python3
"""Simple viewer for Unity-recorded BCI frame CSV files.

Usage:
    python tools/bci_view_recording.py recordings/bci_rec_20260717_120000.csv
"""
import sys, os, argparse
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np

def main():
    p = argparse.ArgumentParser(description="View BCI recording CSV")
    p.add_argument("file", help="Path to recording CSV")
    p.add_argument("--window", type=int, default=200, help="Samples shown")
    args = p.parse_args()

    data = {"frames": {}, "max_frame": 0}
    with open(args.file) as f:
        header = next(f)
        for line in f:
            line = line.strip()
            if not line: continue
            parts = line.split(",")
            if len(parts) < 3: continue
            fn, ch, val = int(parts[0]), int(parts[1]), float(parts[2])
            if fn not in data["frames"]:
                data["frames"][fn] = {}
            data["frames"][fn][ch] = val
            data["max_frame"] = max(data["max_frame"], fn)

    if not data["frames"]:
        print("No data found")
        return

    n_channels = max(max(chs.keys()) for chs in data["frames"].values()) + 1
    sorted_frames = sorted(data["frames"].keys())
    print(f"Loaded {len(sorted_frames)} frames, {n_channels} channels")

    fig, axes = plt.subplots(n_channels, 1, figsize=(10, 6), sharex=True)
    if n_channels == 1:
        axes = [axes]

    lines = []
    for i in range(n_channels):
        line, = axes[i].plot([], [], lw=1)
        lines.append(line)
        axes[i].set_ylabel(f"Ch{i}")
        axes[i].set_ylim(-0.1, 1.1)
        axes[i].grid(True, alpha=0.3)

    axes[-1].set_xlabel("Frame")

    def update(frame_idx):
        window = args.window
        start = max(0, frame_idx - window)
        n = min(window, len(sorted_frames))
        x = list(range(start, start + n))
        for i in range(n_channels):
            y = [data["frames"].get(f, {}).get(i, 0) for f in sorted_frames[start:start+n]]
            lines[i].set_data(x, y)
            axes[i].relim()
            axes[i].autoscale_view(scalex=False)
        return lines

    ani = animation.FuncAnimation(fig, update, frames=sorted_frames,
                                  interval=50, blit=False, cache_frame_data=False)
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()
