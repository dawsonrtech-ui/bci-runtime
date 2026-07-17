#!/usr/bin/env python3
"""WebSocket relay: reads SHM ring buffer and pushes frames to browser clients.

Usage:
    python tools/bci_websocket_relay.py --port 8765

Then open tools/web_dashboard/index.html in your browser.
"""
import sys, os, time, json, argparse, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.shm_gustation import ShmGustationConsumer, RING_BUFFER_SIZE, MAX_CHANNELS_PER_FRAME

try:
    import websockets
except ImportError:
    print("Install websockets: pip install websockets")
    sys.exit(1)


async def broadcast(connected, data):
    if not connected:
        return
    msg = json.dumps(data)
    dead = set()
    for ws in connected:
        try:
            await ws.send(msg)
        except Exception:
            dead.add(ws)
    connected -= dead


async def handler(ws):
    connected.add(ws)
    try:
        async for _ in ws:
            pass
    finally:
        connected.discard(ws)


async def shm_reader(consumer, connected, hz: int):
    consumer.open()
    period = 1.0 / hz
    while True:
        frames = consumer.read_all()
        for slot in frames:
            data = {
                "packet_id": slot.packet_id,
                "channel_count": slot.channel_count,
                "channels": [
                    {
                        "id": slot.channels[i].channel_id,
                        "intensity": slot.channels[i].intensity,
                    }
                    for i in range(slot.channel_count)
                ],
                "heartbeat": consumer.get_heartbeat(),
                "t": time.time(),
            }
            await broadcast(connected, data)
        if not frames:
            consumer.wait(50)
        await asyncio.sleep(period)


async def main():
    p = argparse.ArgumentParser(description="SHM WebSocket relay")
    p.add_argument("--port", type=int, default=8765, help="WebSocket port")
    p.add_argument("--hz", type=int, default=60, help="Push frequency")
    args = p.parse_args()

    consumer = ShmGustationConsumer()
    print(f"[WS] Relay starting on ws://localhost:{args.port}")
    async with websockets.serve(handler, "0.0.0.0", args.port):
        await shm_reader(consumer, connected, args.hz)


if __name__ == "__main__":
    connected = set()
    asyncio.run(main())
