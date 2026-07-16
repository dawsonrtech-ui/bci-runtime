import sys, os, time, signal, json
import numpy as np

from core.orchestrator import BCIEngineOrchestrator, SystemState
from core.spatial_filter import CommonSpatialPatterns
from core.cect import CECTTransformerIntegration

try:
    from core.shm_gustation import ShmGustationProducer, GustationChannel
    _HAS_SHM = True
except ImportError:
    _HAS_SHM = False

try:
    from core.bridge_game_context import (
        GameContext, CameraRig, AudioGeometry,
        SomatosensoryState, OlfactoryState,
        make_game_context_for_harness, pack_to_bridge_frame,
    )
    _HAS_GAME_CONTEXT = True
except ImportError:
    _HAS_GAME_CONTEXT = False

CONFIG_PATH = os.environ.get(
    "BCI_DAEMON_CONFIG",
    os.path.join(os.path.dirname(__file__), "daemon_config.json"),
)

GAME_CONTEXT_PATH = os.environ.get(
    "BCI_GAME_CONTEXT",
    os.path.join(os.path.dirname(__file__), "game_context.json"),
)


def load_config(path):
    defaults = {
        "board_id": None,
        "low_dim_channels": 8,
        "sample_rate": 250,
        "alpha": 0.05,
        "gamma": 0.05,
        "init_seconds": 10,
        "recovery_frames": 50,
        "enable_gateway": True,
        "gateway_port": 5555,
        "gateway_host": os.environ.get("BCI_BIND_HOST", "127.0.0.1"),
        "health_port": 5557,
        "amplitude_max": 500e-6,
        "profile_path": None,
        "csp_n_components": 4,
        "use_native_bridge": False,
    }
    if os.path.exists(path):
        with open(path) as f:
            user_cfg = json.load(f)
        defaults.update(user_cfg)
    return defaults


def load_game_context(path):
    if not os.path.exists(path) or not _HAS_GAME_CONTEXT:
        return make_game_context_for_harness() if _HAS_GAME_CONTEXT else None
    with open(path) as f:
        data = json.load(f)
    return make_game_context_for_harness(
        pos_x=data.get("camera", {}).get("x", 0.0),
        pos_y=data.get("camera", {}).get("y", 0.0),
        pos_z=data.get("camera", {}).get("z", 0.0),
        fov=data.get("camera", {}).get("fov", 90.0),
        spatial_nodes=data.get("audio", {}).get("spatial_nodes", 64),
        dsp_gain=data.get("audio", {}).get("dsp_gain", 1.0),
        dsp_pan=data.get("audio", {}).get("dsp_pan", 0.0),
        dsp_occlusion=data.get("audio", {}).get("dsp_occlusion", 0.0),
        collision_impulse=data.get("somatosensory", {}).get("collision_impulse", 0.0),
        thermal_target_c=data.get("somatosensory", {}).get("thermal_target_c", 22.0),
        motor_gating_active=data.get("somatosensory", {}).get("motor_gating_active", True),
        intensity=data.get("olfactory", {}).get("intensity", 0.5),
        bulb_address=data.get("olfactory", {}).get("bulb_address", 0),
        in_high_stimulus=data.get("in_high_stimulus", False),
    )


def main():
    cfg = load_config(CONFIG_PATH)
    running = True

    def shutdown(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"[BCI Daemon] Starting (pub={cfg['gateway_port']}, health={cfg['health_port']})...")
    use_nb = cfg.get("use_native_bridge", False)
    if use_nb:
        try:
            from core.native_bridge import bridge_version
            print(f"[BCI Daemon] Native bridge: {bridge_version()}")
        except Exception as e:
            print(f"[BCI Daemon] Native bridge unavailable: {e}")
            use_nb = False

    orb = BCIEngineOrchestrator(
        board_id=cfg["board_id"],
        low_dim_channels=cfg["low_dim_channels"],
        sample_rate=cfg["sample_rate"],
        alpha=cfg["alpha"],
        gamma=cfg["gamma"],
        init_seconds=cfg["init_seconds"],
        recovery_frames=cfg["recovery_frames"],
        enable_gateway=cfg["enable_gateway"],
        gateway_port=cfg["gateway_port"],
        gateway_host=cfg["gateway_host"],
        health_port=cfg["health_port"],
        amplitude_max=cfg["amplitude_max"],
    )

    if cfg["profile_path"]:
        orb.initialize_session_profile(
            profile_path=cfg["profile_path"], user_id="Player1"
        )

    print(f"[BCI Daemon] Initial state: {orb.state.name}")
    print(f"[BCI Daemon] Ready on tcp://127.0.0.1:{cfg['gateway_port']}")

    shm_gustation = None
    if _HAS_SHM and cfg.get("enable_shm_gustation", False):
        shm_gustation = ShmGustationProducer(
            shm_name=cfg.get("shm_gustation_name", "Local_BCI_GustationRing"),
            signal_name=cfg.get("shm_signal_name", "Local_BCI_GustationWake"),
        )
        shm_gustation.open()

    if cfg["board_id"] is not None and orb.board is not None:
        orb.board.prepare_session()
        orb.board.start_stream(45000)

    game_ctx = load_game_context(GAME_CONTEXT_PATH)

    frames = 0
    _start = time.time()
    while running:
        if orb.board is not None:
            data = orb.board.get_board_data()
            if data.shape[1] > 0:
                for col in range(data.shape[1]):
                    sample = data[1: 1 + cfg["low_dim_channels"], col]
                    orb.process_frame(sample, context=_ctx_dict(game_ctx))
                    frames += 1
            else:
                time.sleep(0.001)
        else:
            sample = np.random.standard_normal(cfg["low_dim_channels"]) * 10e-6
            ctx = _ctx_dict(game_ctx)
            orb.process_frame(sample, context=ctx)
            frames += 1
            if shm_gustation is not None and frames % 4 == 0:
                ch = GustationChannel(
                    channel_id=0,
                    intensity=float(0.5 + 0.3 * np.sin(frames * 0.01)),
                    duration_ms=100.0,
                    chemical_profile=frames % 5,
                )
                shm_gustation.write_frame(frames, [ch])
            if frames % 2500 == 0:
                m = orb.get_metrics()
                extra = ""
                if shm_gustation is not None:
                    sm = shm_gustation.get_metrics()
                    extra = (f" shm_w={sm['frames_written']}"
                             f" d={sm['frames_dropped']}"
                             f" sig={sm['signal_triggers']}"
                             f" occ={sm['buffer_occupancy']}")
                print(
                    f"  [{frames:6d}] {m['state']:12s} sigmas={m['n_sigmas']} "
                    f"tangent={m['n_tangent']} cond={m['condition']:.1f}{extra}"
                )

        if orb.gateway is not None and frames % 250 == 0:
            orb.gateway.publish_heartbeat(
                orb.state.name, time.time() - _start, orb.frame_count
            )

        if orb.gateway is not None:
            req = orb.gateway.try_recv_health_request()
            if req is not None:
                method = req.get("method", "")
                if method == "ping":
                    orb.gateway.send_health_response({"status": "ok", "msg": "pong"})
                elif method == "status":
                    status = orb.get_health_status()
                    if shm_gustation is not None:
                        status["shm_gustation"] = shm_gustation.get_metrics()
                    orb.gateway.send_health_response(status)
                else:
                    orb.gateway.send_health_response(
                        {"status": "error", "msg": f"unknown method: {method}"}
                    )

        time.sleep(0.004)

    print(f"[BCI Daemon] Shutting down after {frames} frames ({orb._clip_count} clips).")
    if shm_gustation is not None:
        shm_gustation.close()
    if orb.gateway is not None:
        orb.gateway.close()
    if orb.board is not None:
        orb.board.stop_stream()
        orb.board.release_session()


def _ctx_dict(game_ctx):
    if game_ctx is None:
        return None
    return {
        "motor_gating_active": game_ctx.somatosensory.motor_gating_active,
        "in_high_stimulus": game_ctx.in_high_stimulus,
    }


if __name__ == "__main__":
    main()
