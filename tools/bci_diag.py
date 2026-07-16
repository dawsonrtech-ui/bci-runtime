#!/usr/bin/env python3
"""BCI SHM Diagnostic Tool — inspect the live shared-memory ring buffer.

Usage:
    python tools/bci_diag.py                         # default SHM name
    python tools/bci_diag.py --shm CustomRingName    # custom SHM
    python tools/bci_diag.py --watch                 # poll every 500ms
    python tools/bci_diag.py --json                  # JSON output for scripts

Mounts the shared memory file in read-only mode and prints:
  - Layout signature and total size
  - Producer heartbeat (current + velocity)
  - Head / tail positions and buffer occupancy
  - Frame slot inspection (latest N frames)
  - Signal handle status (orphaned / alive)
  - Consumer liveliness estimate
"""

import sys, os, time, argparse, json, struct, ctypes

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.shm_gustation import (
    SharedRingBuffer, ShmSlot, GustationChannel,
    SHM_NAME, SIGNAL_NAME, SHM_TOTAL_SIZE, HEADER_SIZE,
    RING_BUFFER_SIZE, SLOT_MASK, _load_signal_lib, _SIG_LIB,
)


def _map_ring(shm_name: str):
    """Map the shared memory ring buffer.

    Uses write-mode access so ctypes.from_buffer() can create typed views
    (requires a writable buffer in Python 3.12+).  The caller only reads.
    """
    import mmap
    access = mmap.ACCESS_WRITE

    if os.name == "nt":
        mm = mmap.mmap(-1, SHM_TOTAL_SIZE, tagname=shm_name, access=access)
    else:
        shm_path = f"/dev/shm/{shm_name}"
        if not os.path.isfile(shm_path):
            return None, None
        fd = os.open(shm_path, os.O_RDWR)
        mm = mmap.mmap(fd, SHM_TOTAL_SIZE, access=access)
        os.close(fd)

    raw = (ctypes.c_uint8 * SHM_TOTAL_SIZE).from_buffer(mm)
    ptr = ctypes.cast(raw, ctypes.POINTER(SharedRingBuffer))
    return mm, ptr.contents


def _try_signal(name: str):
    """Try to open the signal; return handle or None."""
    if not _load_signal_lib():
        return None
    try:
        h = _SIG_LIB.open_os_signal(name.encode("utf-8"))
        if h:
            return h
    except Exception:
        pass
    return None


def _format_slot(slot, idx: int) -> dict:
    chs = []
    for i in range(slot.channel_count):
        ch = slot.channels[i]
        chs.append({
            "ch": ch.channel_id,
            "intensity": round(ch.intensity, 4),
            "duration_ms": round(ch.duration_ms, 2),
            "chem": ch.chemical_profile,
        })
    return {
        "slot": idx,
        "packet_id": slot.packet_id,
        "n_channels": slot.channel_count,
        "channels": chs,
    }


def diag(shm_name: str, sig_name: str, watch: bool = False,
         json_out: bool = False, samples: int = 3):
    prev_hb = 0
    prev_time = time.monotonic()

    while True:
        mm, ring = _map_ring(shm_name)
        if mm is None:
            result = {"status": "NOT_FOUND", "shm_name": shm_name}
            if json_out:
                print(json.dumps(result))
            else:
                print(f"[DIAG] SHM '{shm_name}' not found — producer not running?")
            if not watch:
                return result
            time.sleep(1)
            continue

        now = time.monotonic()
        hb = ring.producer_heartbeat
        head = ring.head
        tail = ring.tail
        occupancy = head - tail

        # Heartbeat velocity
        if prev_hb and hb > prev_hb:
            hb_vel = (hb - prev_hb) / (now - prev_time)
        else:
            hb_vel = 0.0

        prev_hb = hb
        prev_time = now

        # Signal status
        sig_handle = _try_signal(sig_name)
        sig_ok = sig_handle is not None

        # Collect latest slots
        latest_slots = []
        for i in range(max(0, occupancy - samples), occupancy):
            slot_idx = (tail + i) & SLOT_MASK
            slot = ring.slots[slot_idx]
            latest_slots.append(_format_slot(slot, slot_idx))

        result = {
            "status": "OK",
            "shm_name": shm_name,
            "total_size": SHM_TOTAL_SIZE,
            "header_size": HEADER_SIZE,
            "ring_size": RING_BUFFER_SIZE,
            "producer_heartbeat": hb,
            "heartbeat_velocity_hz": round(hb_vel, 1),
            "head": head,
            "tail": tail,
            "buffer_occupancy": occupancy,
            "buffer_full_pct": round(100 * occupancy / RING_BUFFER_SIZE, 1),
            "producer_alive": hb > 0 or occupancy > 0,
            "signal_available": sig_ok,
            "latest_slots": latest_slots,
        }

        if sig_handle is not None:
            _SIG_LIB.close_os_signal(sig_handle, None)

        if json_out:
            print(json.dumps(result, indent=2))
        else:
            _print_diag(result)

        del ptr, raw
        mm.close()

        if not watch:
            return result

        time.sleep(0.5)


def _print_diag(r: dict):
    print("═" * 50)
    print(f"  SHM:          {r['shm_name']}  ({r['total_size']} bytes)")
    print(f"  Header:       {r['header_size']} B  |  Ring slots: {r['ring_size']}")
    print(f"  Heartbeat:    {r['producer_heartbeat']}  "
          f"(vel: {r['heartbeat_velocity_hz']} Hz)")
    print(f"  Head/Tail:    {r['head']} / {r['tail']}  "
          f"(occ: {r['buffer_occupancy']} = {r['buffer_full_pct']}%)")
    print(f"  Producer:     {'ALIVE' if r['producer_alive'] else 'DEAD / IDLE'}")
    print(f"  Signal:       {'AVAILABLE' if r['signal_available'] else 'NOT FOUND'}")
    if r['latest_slots']:
        print(f"  Latest slots ({len(r['latest_slots'])}):")
        for s in r['latest_slots']:
            chs = ", ".join(f"ch{c['ch']}={c['intensity']}" for c in s['channels'][:4])
            print(f"    [{s['slot']:2d}]  pid={s['packet_id']:5d}  "
                  f"nch={s['n_channels']}  {chs}")
    print()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="BCI SHM diagnostic tool")
    p.add_argument("--shm", default=SHM_NAME, help="SHM name")
    p.add_argument("--signal", default=SIGNAL_NAME, help="Signal name")
    p.add_argument("--watch", action="store_true", help="Poll every 500ms")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--samples", type=int, default=3, help="Number of latest slots to show")
    args = p.parse_args()
    diag(args.shm, args.signal, watch=args.watch, json_out=args.json, samples=args.samples)
