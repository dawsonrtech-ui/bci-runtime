#!/usr/bin/env python3
"""BCI Runtime CLI — one tool to manage the whole stack.

Usage:
    bci start          Start the mock producer (default 100 Hz)
    bci start --hz 250
    bci relay          Start WebSocket relay for web dashboard
    bci dashboard      Start producer + relay, then open browser
    bci benchmark      Run throughput/latency benchmark
    bci replay FILE    Replay a CSV recording through SHM
    bci monitor        Show real-time return-channel latency
    bci inspect        Show SHM ring buffer state (head/tail/heartbeat)
"""
import sys, os, subprocess, time, shutil, signal, json, argparse

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from core.shm_config import load_config


def find_tool(name):
    path = os.path.join(ROOT, "tools", name)
    if os.path.exists(path): return path
    path = os.path.join(ROOT, "tools", name + ".py")
    if os.path.exists(path): return path
    path = os.path.join(ROOT, name)
    if os.path.exists(path): return path
    return None


def cmd_start(args):
    """Start the mock BCI producer."""
    producer = os.path.join(ROOT, "examples", "bci_closed_loop.py")
    if not os.path.exists(producer):
        print(f"[BCI] Producer not found: {producer}"); return 1
    hz = args.hz
    duration = args.duration
    print(f"[BCI] Starting producer @ {hz} Hz for {duration}s")
    subprocess.run([sys.executable, producer, "--hz", str(hz), "--duration", str(duration)])


def cmd_relay(args):
    """Start WebSocket relay for the web dashboard."""
    relay = find_tool("bci_websocket_relay")
    if not relay:
        print("[BCI] Relay tool not found. Install websockets: pip install websockets"); return 1
    print(f"[BCI] Starting WebSocket relay on port {args.port}")
    env = {**os.environ, "BCI_WS_PORT": str(args.port)}
    subprocess.run([sys.executable, relay], env=env)


def cmd_dashboard(args):
    """Start producer + relay + open browser."""
    import threading, webbrowser
    hz = args.hz

    def run_producer():
        producer = os.path.join(ROOT, "examples", "bci_closed_loop.py")
        subprocess.run([sys.executable, producer, "--hz", str(hz), "--duration", "86400"])

    def run_relay():
        relay = find_tool("bci_websocket_relay")
        if relay:
            env = {**os.environ, "BCI_WS_PORT": str(args.port)}
            subprocess.run([sys.executable, relay], env=env)

    print(f"[BCI] Starting dashboard stack (producer @ {hz}Hz, relay :{args.port})")
    threading.Thread(target=run_producer, daemon=True).start()
    time.sleep(1)
    threading.Thread(target=run_relay, daemon=True).start()
    time.sleep(2)

    html = os.path.join(ROOT, "tools", "web_dashboard", "index.html")
    if os.path.exists(html):
        print(f"[BCI] Opening {html}")
        webbrowser.open(f"file://{html}")
    else:
        print(f"[BCI] Dashboard HTML not found at {html}")

    print("[BCI] Running. Ctrl+C to stop.")
    try:
        signal.pause()
    except AttributeError:
        while True: time.sleep(1)


def cmd_benchmark(args):
    """Run throughput/latency benchmark."""
    bench = find_tool("bci_benchmark")
    if not bench:
        print("[BCI] Benchmark tool not found"); return 1
    subprocess.run([sys.executable, bench, "--duration", str(args.duration)])


def cmd_replay(args):
    """Replay a CSV recording through SHM."""
    replay = find_tool("bci_replay")
    if not replay:
        print("[BCI] Replay tool not found"); return 1
    cmd = [sys.executable, replay, args.file]
    if args.hz: cmd += ["--hz", str(args.hz)]
    if args.loop: cmd += ["--loop"]
    subprocess.run(cmd)


def cmd_monitor(args):
    """Show real-time return-channel latency."""
    monitor = find_tool("bci_return_monitor")
    if not monitor:
        print("[BCI] Monitor tool not found"); return 1
    subprocess.run([sys.executable, monitor])


def cmd_inspect(args):
    """Inspect SHM ring buffer state."""
    from core.shm_gustation import ShmGustationConsumer
    import struct
    try:
        c = ShmGustationConsumer()
        c.open()
        hb = struct.unpack("q", c._mmap[:8])[0]
        head = struct.unpack("q", c._mmap[8:16])[0]
        tail = struct.unpack("q", c._mmap[16:24])[0]
        c.close()
        cfg = load_config()
        print(f"SHM Name:      {cfg['shm_name']}")
        print(f"Ring Size:     {cfg['ring_buffer_size']}")
        print(f"Heartbeat:     {hb}")
        print(f"Head:          {head}")
        print(f"Tail:          {tail}")
        print(f"Occupancy:     {head - tail}")
    except Exception as e:
        print(f"[BCI] Inspect failed: {e}"); return 1


def main():
    parser = argparse.ArgumentParser(prog="bci", description="BCI Runtime CLI")
    sub = parser.add_subparsers(dest="command")

    p_start = sub.add_parser("start", help="Start mock producer")
    p_start.add_argument("--hz", type=int, default=100, help="Frequency in Hz")
    p_start.add_argument("--duration", type=int, default=86400, help="Duration in seconds")

    p_relay = sub.add_parser("relay", help="Start WebSocket relay")
    p_relay.add_argument("--port", type=int, default=8765, help="WebSocket port")

    p_dash = sub.add_parser("dashboard", help="Start full dashboard stack")
    p_dash.add_argument("--hz", type=int, default=100, help="Producer frequency")
    p_dash.add_argument("--port", type=int, default=8765, help="WebSocket port")

    p_bench = sub.add_parser("benchmark", help="Run throughput/latency benchmark")
    p_bench.add_argument("--duration", type=int, default=5, help="Test duration per Hz")

    p_replay = sub.add_parser("replay", help="Replay CSV recording")
    p_replay.add_argument("file", help="Path to recording CSV")
    p_replay.add_argument("--hz", type=int, default=100, help="Replay frequency")
    p_replay.add_argument("--loop", action="store_true", help="Loop playback")

    sub.add_parser("monitor", help="Show return-channel latency")
    sub.add_parser("inspect", help="Inspect SHM buffer state")

    args = parser.parse_args()

    if args.command == "start":      return cmd_start(args)
    elif args.command == "relay":    return cmd_relay(args)
    elif args.command == "dashboard": return cmd_dashboard(args)
    elif args.command == "benchmark": return cmd_benchmark(args)
    elif args.command == "replay":   return cmd_replay(args)
    elif args.command == "monitor":  return cmd_monitor(args)
    elif args.command == "inspect":  return cmd_inspect(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
