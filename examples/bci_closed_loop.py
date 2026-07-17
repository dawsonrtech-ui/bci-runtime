#!/usr/bin/env python3
"""Closed-loop BCI mock data stream with Unity command response.

Generates mock 8-channel EEG/EMG data, streams to SHM ring buffer.
Listens on the return channel for Unity commands:
  SET_FREQ <hz>  — change simulation frequency
  RESET          — reset frame counter
  STOP           — gracefully stop

Usage:
    python examples/bci_closed_loop.py             # 250 Hz, 10 s
    python examples/bci_closed_loop.py --hz 100    # 100 Hz
    python examples/bci_closed_loop.py --duration 30
    python examples/bci_closed_loop.py --visualise
"""
import sys, os, time, math, argparse, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.shm_gustation import (
    ShmGustationProducer, GustationChannel,
    SHM_NAME, SIGNAL_NAME, RING_BUFFER_SIZE,
    ShmReturnConsumer, RETURN_SHM_NAME, RETURN_SIGNAL_NAME,
)

N_CHANNELS = 8
FREQ_MAP = [1.0, 6.0, 10.0, 20.0, 40.0, 60.0, 15.0, 50.0]
BASE_AMPS = [0.3, 0.2, 0.5, 0.15, 0.08, 0.05, 0.12, 0.02]
_cmd_freq_override = None
_cmd_stop = False


def mock_eeg_sample(t: float, channel: int) -> float:
    freq = FREQ_MAP[channel]
    base = BASE_AMPS[channel]
    raw = (base
           + 0.3 * base * math.sin(2 * math.pi * freq * t)
           + 0.1 * base * math.sin(2 * math.pi * freq * 2 * t)
           + 0.05 * base * math.sin(2 * math.pi * freq * 0.5 * t)
           + 0.02 * (hash((channel, round(t, 3))) & 0xFFFF) / 65535)
    return max(0.0, min(1.0, raw))


def run_command_listener():
    global _cmd_freq_override, _cmd_stop
    try:
        consumer = ShmReturnConsumer()
        consumer.open()
        while not _cmd_stop:
            msgs = consumer.read_all()
            for m in msgs:
                cmd = m.get("command", "").strip()
                if cmd.startswith("SET_FREQ"):
                    try:
                        _cmd_freq_override = int(cmd.split()[-1])
                        print(f"\n[CMD] Frequency set to {_cmd_freq_override} Hz")
                    except ValueError:
                        pass
                elif cmd == "RESET":
                    print("\n[CMD] Reset requested")
                elif cmd == "STOP":
                    print("\n[CMD] Stop requested — shutting down")
                    _cmd_stop = True
                    return
            if not msgs:
                consumer.wait(200)
            else:
                time.sleep(0.01)
    except Exception as e:
        print(f"\n[CMD] Listener error: {e}")
    finally:
        try:
            consumer.close()
        except Exception:
            pass


def run_closed_loop(hz: int = 250, duration_s: float = 10.0,
                    visualise: bool = False):
    global _cmd_freq_override, _cmd_stop

    producer = ShmGustationProducer()
    producer.open()

    cmd_thread = threading.Thread(target=run_command_listener, daemon=True)
    cmd_thread.start()

    actual_hz = hz
    period = 1.0 / actual_hz
    t0 = time.perf_counter()
    frame_id = 0
    total_frames = int(duration_s * actual_hz)

    print(f"[BCI] Running at {actual_hz} Hz for {duration_s}s "
          f"({total_frames} frames)")

    try:
        while frame_id < total_frames and not _cmd_stop:
            # Check for frequency override from commands
            if _cmd_freq_override is not None and _cmd_freq_override != actual_hz:
                actual_hz = _cmd_freq_override
                period = 1.0 / actual_hz
                total_frames = int(duration_s * actual_hz)
                print(f"[BCI] Re-tuned to {actual_hz} Hz")

            now = time.perf_counter()
            elapsed = now - t0
            t = elapsed if not _cmd_stop else 0

            channels = []
            for ch in range(N_CHANNELS):
                intensity = mock_eeg_sample(t, ch)
                channels.append(GustationChannel(
                    channel_id=ch,
                    intensity=intensity,
                    duration_ms=1000.0 / actual_hz,
                    chemical_profile=ch,
                ))

            producer.write_frame(frame_id, channels)
            frame_id += 1

            if visualise:
                metrics = producer.get_metrics()
                occ = metrics.get("buffer_occupancy", 0)
                sys.stdout.write(
                    f"\r[{frame_id:5d}/{total_frames}]  "
                    f"occ={occ:2d}  hb={producer.get_heartbeat():6d}  "
                    f"@{actual_hz}Hz  "
                )
                for ch in channels:
                    sys.stdout.write(f"{ch.intensity:.2f} ")
                sys.stdout.flush()

            # Adaptive sleep to maintain target rate
            next_target = t0 + frame_id * period
            sleep_time = next_target - time.perf_counter()
            if sleep_time > 0:
                time.sleep(sleep_time)
    except KeyboardInterrupt:
        pass
    finally:
        _cmd_stop = True
        metrics = producer.get_metrics()
        elapsed = time.perf_counter() - t0
        print(f"\n[BCI] Done: {metrics['frames_written']} frames, "
              f"{metrics['frames_dropped']} dropped, "
              f"{metrics['signal_triggers']} signals, "
              f"{elapsed:.2f}s ({metrics['frames_written'] / elapsed:.0f} fps)")
        producer.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Closed-loop BCI with Unity command response")
    p.add_argument("--hz", type=int, default=250, help="Simulation frequency")
    p.add_argument("--duration", type=float, default=60.0, help="Duration in seconds")
    p.add_argument("--visualise", action="store_true", help="Live bandpower dashboard")
    args = p.parse_args()
    run_closed_loop(hz=args.hz, duration_s=args.duration,
                    visualise=args.visualise)
