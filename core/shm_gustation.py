import os
import sys
import mmap
import ctypes
import atexit
import weakref
from ctypes import c_uint8, c_uint32, c_uint64, c_float, c_int, c_bool, c_void_p, c_wchar_p, Structure, POINTER
from typing import Optional, List

from .shm_config import load_config

_cfg = load_config()
SHM_NAME = _cfg["shm_name"]
SIGNAL_NAME = "Local_BCI_GustationWake"
RING_BUFFER_SIZE = _cfg["ring_buffer_size"]
MAX_CHANNELS_PER_FRAME = _cfg["max_channels"]
SLOT_MASK = RING_BUFFER_SIZE - 1


class GustationChannel(Structure):
    _pack_ = 4
    _layout_ = "ms"
    _fields_ = [
        ("channel_id",       c_uint32),
        ("intensity",        c_float),
        ("duration_ms",      c_float),
        ("chemical_profile", c_uint8),
        ("padding",          c_uint8 * 3),
    ]

    def __bytes__(self):
        return bytes(self)

    def __repr__(self):
        return (f"GustationChannel(id={self.channel_id}, "
                f"intensity={self.intensity:.3f}, "
                f"chemical=#{self.chemical_profile})")


class ShmSlot(Structure):
    _pack_ = 4
    _layout_ = "ms"
    _fields_ = [
        ("packet_id",     c_uint32),
        ("channel_count", c_uint32),
        ("channels",      GustationChannel * MAX_CHANNELS_PER_FRAME),
    ]


# ── Heartbeat ────────────────────────────────────────────────
# 8-byte rolling counter at offset 0.  Producer increments on every
# write_frame; consumer checks stall >2 frames to detect dead producer
# without waiting for signal timeout.
HEARTBEAT_SLOP_FRAMES = 3

class SharedRingBuffer(Structure):
    _fields_ = [
        ("producer_heartbeat", c_uint64),
        ("head",  c_uint64),
        ("tail",  c_uint64),
        ("slots", ShmSlot * RING_BUFFER_SIZE),
    ]


SHM_TOTAL_SIZE = ctypes.sizeof(SharedRingBuffer)
HEADER_SIZE = ctypes.sizeof(c_uint64) * 3  # heartbeat + head + tail = 24
WAIT_TIMEOUT_MS = 5000

# ── Cleanup registry (atexit safety net) ──────────────────────
# Holds weak references so close() is called on abnormal exit.
_ACTIVE_INSTANCES = weakref.WeakSet()


def _cleanup_all():
    for inst in list(_ACTIVE_INSTANCES):
        try:
            inst.close()
        except Exception:
            pass


atexit.register(_cleanup_all)

# ── OS Signal helpers ─────────────────────────────────────────
# Priority: native bridge DLL > Win32 kernel32 API (pure ctypes)

_SIG_LIB = None


class _Win32SignalWrapper:
    """Windows signal via kernel32 ctypes — no native bridge DLL needed."""

    def __init__(self):
        k32 = ctypes.windll.kernel32

        k32.CreateEventW.argtypes = [c_void_p, c_bool, c_bool, c_wchar_p]
        k32.CreateEventW.restype = c_void_p

        k32.OpenEventW.argtypes = [c_uint32, c_bool, c_wchar_p]
        k32.OpenEventW.restype = c_void_p

        k32.SetEvent.argtypes = [c_void_p]
        k32.SetEvent.restype = c_bool

        k32.WaitForSingleObject.argtypes = [c_void_p, c_uint32]
        k32.WaitForSingleObject.restype = c_uint32

        k32.CloseHandle.argtypes = [c_void_p]
        k32.CloseHandle.restype = c_bool

        self._k32 = k32

    def create_os_signal(self, name: bytes) -> int:
        return self._k32.CreateEventW(None, False, False, name.decode("utf-8"))

    def open_os_signal(self, name: bytes) -> int:
        EVENT_MODIFY_STATE = 0x0002
        SYNCHRONIZE = 0x00100000
        return self._k32.OpenEventW(EVENT_MODIFY_STATE | SYNCHRONIZE, False,
                                    name.decode("utf-8"))

    def trigger_os_signal(self, sig) -> None:
        self._k32.SetEvent(sig)

    def wait_os_signal(self, sig, timeout_ms: int) -> int:
        ms = 0xFFFFFFFF if timeout_ms < 0 else c_uint32(timeout_ms).value
        res = self._k32.WaitForSingleObject(sig, ms)
        return 0 if res == 0 else -1

    def close_os_signal(self, sig, name: bytes) -> None:
        if sig:
            self._k32.CloseHandle(sig)


def _load_signal_lib():
    global _SIG_LIB
    if _SIG_LIB is not None:
        return True
    # Try native bridge DLL first (works on both Linux and Windows)
    try:
        from core.native_bridge import _find_lib
        path = _find_lib()
        if path:
            lib = ctypes.CDLL(path)
            lib.create_os_signal.argtypes = [ctypes.c_char_p]
            lib.create_os_signal.restype = ctypes.c_void_p
            lib.open_os_signal.argtypes = [ctypes.c_char_p]
            lib.open_os_signal.restype = ctypes.c_void_p
            lib.trigger_os_signal.argtypes = [ctypes.c_void_p]
            lib.trigger_os_signal.restype = None
            lib.wait_os_signal.argtypes = [ctypes.c_void_p, ctypes.c_int]
            lib.wait_os_signal.restype = ctypes.c_int
            lib.close_os_signal.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            lib.close_os_signal.restype = None
            _SIG_LIB = lib
            return True
    except Exception:
        pass
    # Fall back to Win32 kernel32 API (pure ctypes, no DLL needed)
    if os.name == "nt":
        try:
            _SIG_LIB = _Win32SignalWrapper()
            return True
        except Exception:
            pass
    return False


class _ShmBase:
    def __init__(self, shm_name: str):
        self._shm_name = shm_name
        self._mmap: Optional[mmap.mmap] = None
        self._ring: Optional[SharedRingBuffer] = None
        self._closed = False
        _ACTIVE_INSTANCES.add(self)

    def open(self, access: int):
        if os.name == "nt":
            self._mmap = mmap.mmap(-1, SHM_TOTAL_SIZE,
                                   tagname=self._shm_name,
                                   access=access)
        else:
            shm_path = f"/dev/shm/{self._shm_name}"
            with open(shm_path, "a+b") as f:
                f.truncate(SHM_TOTAL_SIZE)
            fd = os.open(shm_path, os.O_RDWR)
            self._mmap = mmap.mmap(fd, SHM_TOTAL_SIZE, access=access)
            os.close(fd)

        raw = (ctypes.c_uint8 * SHM_TOTAL_SIZE).from_buffer(self._mmap)
        ptr = ctypes.cast(raw, ctypes.POINTER(SharedRingBuffer))
        self._ring = ptr.contents

    def close(self):
        if self._closed:
            return
        self._closed = True
        _ACTIVE_INSTANCES.discard(self)
        if self._mmap is not None:
            try:
                self._mmap.close()
            except BufferError:
                pass
            self._mmap = None
            self._ring = None

    @property
    def is_open(self) -> bool:
        return self._mmap is not None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class ShmGustationProducer(_ShmBase):
    def __init__(self, shm_name: str = SHM_NAME, signal_name: str = SIGNAL_NAME):
        super().__init__(shm_name)
        self._signal_name = signal_name
        self._shm_signal = None
        self._metrics = {
            "frames_written": 0,
            "frames_dropped": 0,
            "signal_triggers": 0,
        }

    def open(self):
        super().open(mmap.ACCESS_WRITE)
        self._ring.head = 0
        self._ring.tail = 0
        if _load_signal_lib():
            self._shm_signal = _SIG_LIB.create_os_signal(
                self._signal_name.encode("utf-8")
            )
        print(f"[SHM] Producer open: {self._shm_name} "
              f"(signal={self._signal_name}, handle={self._shm_signal})")

    def close(self):
        if self._shm_signal is not None and _SIG_LIB is not None:
            _SIG_LIB.close_os_signal(
                self._shm_signal, self._signal_name.encode("utf-8")
            )
            self._shm_signal = None
        super().close()

    def write_frame(
        self,
        packet_id: int,
        channels: List[GustationChannel],
    ) -> bool:
        if self._ring is None:
            return False

        head = self._ring.head
        tail = self._ring.tail

        if (head - tail) >= RING_BUFFER_SIZE:
            self._metrics["frames_dropped"] += 1
            return False

        slot_idx = head & SLOT_MASK
        slot = self._ring.slots[slot_idx]

        slot.packet_id = packet_id
        slot.channel_count = min(len(channels), MAX_CHANNELS_PER_FRAME)

        for i in range(slot.channel_count):
            slot.channels[i] = channels[i]

        self._ring.producer_heartbeat += 1
        was_empty = (head == tail)
        self._ring.head = head + 1
        self._metrics["frames_written"] += 1

        # Reactive signal: only wake consumer when transitioning empty→non-empty
        if was_empty and self._shm_signal is not None and _SIG_LIB is not None:
            _SIG_LIB.trigger_os_signal(self._shm_signal)
            self._metrics["signal_triggers"] += 1

        return True

    def get_heartbeat(self) -> int:
        return self._ring.producer_heartbeat if self._ring is not None else 0

    def get_metrics(self) -> dict:
        tail = self._ring.tail if self._ring is not None else 0
        head = self._ring.head if self._ring is not None else 0
        self._metrics["buffer_occupancy"] = head - tail
        self._metrics["head"] = head
        self._metrics["tail"] = tail
        self._metrics["producer_heartbeat"] = self.get_heartbeat()
        return dict(self._metrics)


class ShmGustationConsumer(_ShmBase):
    def __init__(self, shm_name: str = SHM_NAME, signal_name: str = SIGNAL_NAME):
        super().__init__(shm_name)
        self._signal_name = signal_name
        self._shm_signal = None
        self._metrics = {
            "frames_read": 0,
            "read_calls": 0,
            "signal_waits": 0,
            "signal_timeouts": 0,
        }

    def open(self):
        super().open(mmap.ACCESS_WRITE)
        if _load_signal_lib():
            self._shm_signal = _SIG_LIB.open_os_signal(
                self._signal_name.encode("utf-8")
            )
        print(f"[SHM] Consumer attached: {self._shm_name} "
              f"(signal={'ok' if self._shm_signal else 'unavailable'})")

    def close(self):
        if self._shm_signal is not None and _SIG_LIB is not None:
            _SIG_LIB.close_os_signal(
                self._shm_signal, self._signal_name.encode("utf-8")
            )
            self._shm_signal = None
        super().close()

    def wait(self, timeout_ms: int = WAIT_TIMEOUT_MS) -> bool:
        if self._shm_signal is None or _SIG_LIB is None:
            return False
        rc = _SIG_LIB.wait_os_signal(self._shm_signal, timeout_ms)
        if rc == 0:
            self._metrics["signal_waits"] += 1
            return True
        self._metrics["signal_timeouts"] += 1
        return False

    def read_all(self) -> List[ShmSlot]:
        if self._ring is None:
            return []

        head = self._ring.head
        tail = self._ring.tail
        frames = []
        self._metrics["read_calls"] += 1

        while tail < head:
            slot_idx = tail & SLOT_MASK
            slot = self._ring.slots[slot_idx]
            frames.append(slot)
            tail += 1

        self._ring.tail = tail
        self._metrics["frames_read"] += len(frames)
        return frames

    def get_heartbeat(self) -> int:
        return self._ring.producer_heartbeat if self._ring is not None else 0

    def producer_alive(self, last_known_heartbeat: int = 0) -> bool:
        """Return False if heartbeat hasn't advanced after HEARTBEAT_SLOP_FRAMES."""
        current = self.get_heartbeat()
        return current > last_known_heartbeat or (current == 0 and last_known_heartbeat == 0)

    def get_metrics(self) -> dict:
        head = self._ring.head if self._ring is not None else 0
        tail = self._ring.tail if self._ring is not None else 0
        self._metrics["buffer_occupancy"] = head - tail
        self._metrics["head"] = head
        self._metrics["tail"] = tail
        self._metrics["drain_pending"] = max(0, head - tail)
        self._metrics["producer_heartbeat"] = self.get_heartbeat()
        return dict(self._metrics)


__all__ = [
    "GustationChannel",
    "ShmSlot",
    "SharedRingBuffer",
    "ShmGustationProducer",
    "ShmGustationConsumer",
    "SHM_NAME",
    "SIGNAL_NAME",
    "RING_BUFFER_SIZE",
    "MAX_CHANNELS_PER_FRAME",
    "SHM_TOTAL_SIZE",
    "HEADER_SIZE",
    "HEARTBEAT_SLOP_FRAMES",
]

# -- Return channel (Unity ? Python ack/output/command) ------
RETURN_SHM_NAME = _cfg.get("return_shm_name", "Local_BCI_GustationRing_Return")
RETURN_SIGNAL_NAME = "Local_BCI_GustationReturn_Wake"
RETURN_RING_SIZE = _cfg.get("return_ring_buffer_size", 8)
RETURN_SLOT_MASK = RETURN_RING_SIZE - 1

class ReturnMessageType:
    FRAME_ACK = 0
    PROCESSED_OUTPUT = 1
    COMMAND = 2

class ShmReturnSlot(Structure):
    _pack_ = 4
    _fields_ = [
        ("ack_frame_id",  c_uint64),
        ("msg_type",      c_uint32),
        ("channel_count", c_uint32),
        ("values",        c_float * 16),
        ("command",       c_uint8 * 32),
    ]

class SharedReturnBuffer(Structure):
    _fields_ = [
        ("head",  c_uint64),
        ("tail",  c_uint64),
        ("slots", ShmReturnSlot * RETURN_RING_SIZE),
    ]

RETURN_TOTAL_SIZE = ctypes.sizeof(SharedReturnBuffer)

class ShmReturnConsumer:
    """Python consumer for the return channel (reads what Unity wrote)."""
    def __init__(self, shm_name: str = RETURN_SHM_NAME, signal_name: str = RETURN_SIGNAL_NAME):
        self._shm_name = shm_name
        self._signal_name = signal_name
        self._mmap = None
        self._ring = None
        self._shm_signal = None

    def open(self):
        if os.name == "nt":
            self._mmap = mmap.mmap(-1, RETURN_TOTAL_SIZE, tagname=self._shm_name, access=mmap.ACCESS_WRITE)
        else:
            shm_path = f"/dev/shm/{self._shm_name}"
            with open(shm_path, "a+b") as f:
                f.truncate(RETURN_TOTAL_SIZE)
            fd = os.open(shm_path, os.O_RDWR)
            self._mmap = mmap.mmap(fd, RETURN_TOTAL_SIZE, access=mmap.ACCESS_WRITE)
            os.close(fd)

        raw = (ctypes.c_uint8 * RETURN_TOTAL_SIZE).from_buffer(self._mmap)
        ptr = ctypes.cast(raw, ctypes.POINTER(SharedReturnBuffer))
        self._ring = ptr.contents

        _load_signal_lib()
        if _SIG_LIB:
            self._shm_signal = _SIG_LIB.open_os_signal(self._signal_name.encode("utf-8"))
        print(f"[SHM-RETURN] Consumer open: {self._shm_name}")
        return self

    def close(self):
        if self._shm_signal is not None and _SIG_LIB is not None:
            _SIG_LIB.close_os_signal(self._shm_signal, self._signal_name.encode("utf-8"))
        if self._mmap:
            self._mmap.close()
        self._ring = None

    def wait(self, timeout_ms: int = 1000) -> bool:
        if self._shm_signal is None or _SIG_LIB is None:
            return False
        return _SIG_LIB.wait_os_signal(self._shm_signal, timeout_ms) == 0

    def read_all(self):
        if self._ring is None:
            return []
        head = self._ring.head
        tail = self._ring.tail
        msgs = []
        while tail < head:
            slot_idx = tail & RETURN_SLOT_MASK
            slot = self._ring.slots[slot_idx]
            cmd_bytes = bytes(b for b in slot.command if b != 0)
            msgs.append({
                "ack_frame_id": slot.ack_frame_id,
                "msg_type": slot.msg_type,
                "channel_count": slot.channel_count,
                "values": [slot.values[i] for i in range(slot.channel_count)],
                "command": cmd_bytes.decode("utf-8", errors="replace") if cmd_bytes else "",
            })
            tail += 1
        self._ring.tail = tail
        return msgs

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

__all__ += [
    "RETURN_SHM_NAME",
    "RETURN_SIGNAL_NAME",
    "RETURN_RING_SIZE",
    "ShmReturnSlot",
    "SharedReturnBuffer",
    "ShmReturnConsumer",
]
