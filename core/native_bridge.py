import os
import ctypes
from ctypes import (
    c_int, c_double, c_char, c_char_p, c_uint, POINTER, Structure, CDLL
)
from typing import Optional

_LIB: Optional[CDLL] = None


def _find_lib() -> Optional[str]:
    os_name = os.uname().sysname if hasattr(os, "uname") else os.name
    if os_name == "Linux":
        exts = [".so", ".dll", ".dylib"]
    elif os_name == "Darwin":
        exts = [".dylib", ".so", ".dll"]
    else:
        exts = [".dll", ".so", ".dylib"]
    candidates = [
        os.path.join(
            os.path.dirname(__file__),
            "..", "native", "build", f"libbci_bridge{ext}",
        )
        for ext in exts
    ]
    for p in candidates:
        absp = os.path.abspath(p)
        if os.path.isfile(absp):
            return absp
    return None


_NATIVE_LOAD_ERROR = None


def bridge_available() -> bool:
    try:
        _ensure_lib()
        return True
    except RuntimeError:
        return False


def _ensure_lib():
    global _LIB, _NATIVE_LOAD_ERROR
    if _LIB is not None:
        return
    if _NATIVE_LOAD_ERROR:
        raise _NATIVE_LOAD_ERROR
    path = _find_lib()
    if path is None:
        _NATIVE_LOAD_ERROR = RuntimeError(
            "bci_bridge native library not found. "
            "Run: cd native && make host"
        )
        raise _NATIVE_LOAD_ERROR
    try:
        _LIB = CDLL(path)
    except OSError as e:
        _NATIVE_LOAD_ERROR = RuntimeError(f"Failed to load native library: {e}")
        raise _NATIVE_LOAD_ERROR
    _LIB.bci_serialize_frame.argtypes = [
        POINTER(BciBridgeFrame),
        c_char_p,
        c_int,
    ]
    _LIB.bci_serialize_frame.restype = c_int

    _LIB.bci_build_frame.argtypes = [
        POINTER(BciBridgeFrame),
        c_int,
        POINTER(c_double),
        c_int,
        c_int,
        c_double,
        c_char_p,
    ]
    _LIB.bci_build_frame.restype = c_int

    _LIB.bci_validate_frame.argtypes = [POINTER(BciBridgeFrame)]
    _LIB.bci_validate_frame.restype = c_int

    _LIB.bci_bridge_version.restype = c_char_p


BCI_TANGENT_DIM = 136
BCI_GUSTATION_NUM = 5


class BciBridgeFrame(Structure):
    _fields_ = [
        ("version",            c_int),
        ("frame_count",        c_int),
        ("n_tangent",          c_int),
        ("tangent",            c_double * BCI_TANGENT_DIM),
        ("predicted_action",   c_int),
        ("confidence",         c_double),
        ("engine_state",       c_char * 16),

        ("camera_pos_x",       c_double),
        ("camera_pos_y",       c_double),
        ("camera_pos_z",       c_double),
        ("camera_fov",         c_double),

        ("spatial_nodes",      c_int),
        ("dsp_gain",           c_double),
        ("dsp_pan",            c_double),
        ("dsp_occlusion",      c_double),

        ("collision_impulse",  c_double),
        ("thermal_target_c",   c_double),

        ("intensity",          c_double),
        ("bulb_address",       c_uint),

        ("gustation",          c_double * BCI_GUSTATION_NUM),

        ("motor_gating_active", c_int),
        ("in_high_stimulus",    c_int),
        ("force_zero",          c_int),
    ]


def serialize_frame(frame: BciBridgeFrame) -> Optional[str]:
    _ensure_lib()
    buf = ctypes.create_string_buffer(4096)
    n = _LIB.bci_serialize_frame(ctypes.byref(frame), buf, 4096)
    if n < 0:
        return None
    return buf.value.decode("utf-8")


def build_frame(
    frame_count: int,
    tangent: list,
    predicted_action: int,
    confidence: float,
    engine_state: str,
) -> BciBridgeFrame:
    _ensure_lib()
    n_tangent = len(tangent)
    tangent_arr = (c_double * n_tangent)(*tangent)
    frame = BciBridgeFrame()
    rc = _LIB.bci_build_frame(
        ctypes.byref(frame),
        c_int(frame_count),
        tangent_arr,
        c_int(n_tangent),
        c_int(predicted_action),
        c_double(confidence),
        engine_state.encode("utf-8"),
    )
    if rc != 0:
        raise RuntimeError("bci_build_frame failed")
    return frame


def validate_frame(frame: BciBridgeFrame) -> bool:
    _ensure_lib()
    return _LIB.bci_validate_frame(ctypes.byref(frame)) == 0


def bridge_version() -> str:
    _ensure_lib()
    return _LIB.bci_bridge_version().decode("utf-8")


__all__ = [
    "BciBridgeFrame",
    "BCI_TANGENT_DIM",
    "BCI_GUSTATION_NUM",
    "serialize_frame",
    "build_frame",
    "validate_frame",
    "bridge_version",
    "bridge_available",
]
