#!/usr/bin/env python3
"""Replay a recorded BCI CSV through the SHM ring buffer.

Enables visualising past recording sessions without a live producer.

Usage:
    python tools/bci_replay.py recordings/bci_rec_20260717_120000.csv --hz 100

Run alongside any SHM consumer (Unity, web dashboard, etc.).
"""
import sys, os, time, argparse, csv
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.shm_gustation import ShmGustationProducer, GustationChannel


def main():
    p = argparse.ArgumentParser(description="Replay BCI recording CSV")
    p.add_argument("file", help="Path to recording CSV")
    p.add_argument("--hz", type=int, default=100, help="Replay frequency")
    p.add_argument("--loop", action="store_true", help="Loop playback")
    p.add_argument("--scale", type=float, default=1.0, help="Speed multiplier")
    args = p.parse_args()

    print(f"[REPLAY] Loading {args.file} ...")
    frames = {}
    ch_names = set()
    with open(args.file) as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            if len(row) < 3: continue
            fn, ch, val = int(row[0]), int(row[1]), float(row[2])
            if fn not in frames:
                frames[fn] = {}
            frames[fn][ch] = val
            ch_names.add(ch)

    n_channels = max(ch_names) + 1
    sorted_frames = sorted(frames.keys())
    print(f"[REPLAY] {len(sorted_frames)} frames, {n_channels} channels")

    producer = ShmGustationProducer()
    producer.open()
    print(f"[REPLAY] Playing at {args.hz} Hz (x{args.scale})")
    period = 1.0 / (args.hz * args.scale)
    t0 = time.perf_counter()

    try:
        while True:
            for idx, fn in enumerate(sorted_frames):
                ch_data = frames[fn]
                channels = []
                for ch in range(n_channels):
                    intensity = ch_data.get(ch, 0.0)
                    channels.append(GustationChannel(
                        channel_id=ch,
                        intensity=intensity,
                        duration_ms=time.monotonic(),
                        chemical_profile=ch,
                    ))
                producer.write_frame(fn, channels)

                elapsed = time.perf_counter() - t0
                next_t = t0 + (idx + 1) * period
                sleep = next_t - time.perf_counter()
                if sleep > 0:
                    time.sleep(sleep)

            sys.stdout.write(f"\r[REPLAY] Played {len(sorted_frames)} frames, looping..." if args.loop else "\n[REPLAY] Done\n")
            sys.stdout.flush()
            if not args.loop:
                break
    except KeyboardInterrupt:
        print("\n[REPLAY] Stopped")
    finally:
        producer.close()


if __name__ == "__main__":
    main()
