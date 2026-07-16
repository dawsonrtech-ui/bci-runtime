"""Generate daemon_config.json and game_context.json with sensible defaults.

Usage:
    python tools/gen_daemon_config.py
    python tools/gen_daemon_config.py --output-dir /path/to/configs
    python tools/gen_daemon_config.py --game-context-only
"""

import json, os, argparse


DAEMON_CONFIG_DEFAULTS = {
    "board_id": None,
    "low_dim_channels": 8,
    "sample_rate": 250,
    "alpha": 0.05,
    "gamma": 0.05,
    "init_seconds": 10,
    "recovery_frames": 50,
    "enable_gateway": True,
    "gateway_port": 5555,
    "gateway_host": "127.0.0.1",
    "health_port": 5557,
    "amplitude_max": 5e-4,
    "profile_path": None,
    "csp_n_components": 4,
    "use_native_bridge": True,
    "enable_shm_gustation": True,
    "shm_gustation_name": "Local_BCI_GustationRing",
    "shm_signal_name": "Local_BCI_GustationWake",
}


GAME_CONTEXT_DEFAULTS = {
    "camera": {
        "x": 0.0,
        "y": 1.7,
        "z": 0.0,
        "fov": 90.0,
    },
    "audio": {
        "spatial_nodes": 64,
        "dsp_gain": 1.0,
        "dsp_pan": 0.0,
        "dsp_occlusion": 0.0,
    },
    "somatosensory": {
        "collision_impulse": 0.0,
        "thermal_target_c": 22.0,
        "motor_gating_active": True,
    },
    "olfactory": {
        "intensity": 0.5,
        "bulb_address": 0,
    },
    "gustation": {
        "mix_matrix": [
            [1.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 1.0],
        ],
        "channel_count": 5,
    },
    "in_high_stimulus": False,
}


def write_json(path: str, data: dict):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  wrote {path} ({os.path.getsize(path)} bytes)")


def main():
    parser = argparse.ArgumentParser(description="Generate BCI daemon config files")
    parser.add_argument("--output-dir", default=".",
                        help="Output directory (default: current dir)")
    parser.add_argument("--daemon-only", action="store_true",
                        help="Only generate daemon_config.json")
    parser.add_argument("--game-context-only", action="store_true",
                        help="Only generate game_context.json")
    parser.add_argument("--daemon-config", default="daemon_config.json",
                        help="Daemon config filename (default: daemon_config.json)")
    parser.add_argument("--game-context", default="game_context.json",
                        help="Game context filename (default: game_context.json)")
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output_dir)

    print(f"Generating BCI configs in {output_dir}")

    if not args.game_context_only:
        daemon_path = os.path.join(output_dir, args.daemon_config)
        write_json(daemon_path, DAEMON_CONFIG_DEFAULTS)

    if not args.daemon_only:
        game_path = os.path.join(output_dir, args.game_context)
        write_json(game_path, GAME_CONTEXT_DEFAULTS)

    print("Done.")


if __name__ == "__main__":
    main()
