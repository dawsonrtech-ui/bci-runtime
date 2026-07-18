"""Load SHM configuration from shm_config.json.

Shared between Python tools and C# runtime (via Resources).
Looks for the config file relative to the project root or the calling script.
"""
import json, os
from pathlib import Path

DEFAULT_CONFIG = {
    "shm_name": "Local_BCI_GustationRing",
    "return_shm_name": "Local_BCI_GustationRing_Return",
    "ring_buffer_size": 32,
    "slot_header_size": 8,
    "channel_header_size": 8,
    "channel_stride": 16,
    "max_channels": 8,
    "header_size": 24,
    "poll_interval_ms": 4,
    "heartbeat_timeout_sec": 3.0,
    "return_ring_buffer_size": 8,
}

_config = None


def load_config(path=None):
    global _config
    if _config is not None:
        return _config

    if path is None:
        candidates = [
            Path(os.getcwd()) / "shm_config.json",
            Path(__file__).parent.parent / "shm_config.json",
            Path(__file__).parent.parent.parent / "shm_config.json",
        ]
        for c in candidates:
            if c.exists():
                path = str(c)
                break

    if path and os.path.exists(path):
        with open(path) as f:
            cfg = json.load(f)
            _config = {**DEFAULT_CONFIG, **cfg}
            return _config
    _config = dict(DEFAULT_CONFIG)
    return _config


def get(key, default=None):
    cfg = load_config()
    return cfg.get(key, default)
