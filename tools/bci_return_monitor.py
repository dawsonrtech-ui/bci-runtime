#!/usr/bin/env python3
"""Read Unity ack/processed/command messages from the return SHM channel.

Run alongside bci_closed_loop.py:
    python examples/bci_closed_loop.py --hz 100
    python tools/bci_return_monitor.py
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.shm_gustation import ShmReturnConsumer

def main():
    consumer = ShmReturnConsumer()
    consumer.open()
    print("[RETURN] Listening for Unity messages...")
    try:
        while True:
            msgs = consumer.read_all()
            for m in msgs:
                t = {0: "ACK", 1: "PROCESSED", 2: "CMD"}
                print(f"[RETURN] {t.get(m['msg_type'], '?')} "
                      f"frame={m['ack_frame_id']} "
                      f"ch={m['channel_count']} "
                      f"cmd='{m['command']}'")
            if not msgs:
                consumer.wait(200)
            else:
                time.sleep(0.01)
    except KeyboardInterrupt:
        print("\n[RETURN] Stopped")
    finally:
        consumer.close()

if __name__ == "__main__":
    main()
