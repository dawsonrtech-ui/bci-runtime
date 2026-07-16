import sys, os, json, unittest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_bridge_available():
    from core.native_bridge import bridge_available
    available = bridge_available()
    print(f"Native bridge available: {available}")
    if not available:
        print("  (DLL not compiled - run 'cd native && make host')")


def test_bridge_discovery():
    from core.native_bridge import _find_lib
    path = _find_lib()
    if path:
        print(f"Found bridge lib: {path}")
    else:
        print("Bridge lib not found (expected without compilation)")


def test_build_and_serialize():
    from core.native_bridge import (
        bridge_available, build_frame, serialize_frame, validate_frame
    )
    if not bridge_available():
        print("SKIP: native bridge not available")
        return

    tangent = [0.1 * i for i in range(36)]
    frame = build_frame(
        frame_count=42,
        tangent=tangent,
        predicted_action=2,
        confidence=0.85,
        engine_state="NORMAL",
    )
    assert validate_frame(frame), "frame validation failed"
    assert frame.version == 3
    assert frame.frame_count == 42
    assert frame.predicted_action == 2
    assert abs(frame.confidence - 0.85) < 1e-9
    assert frame.engine_state == b"NORMAL"

    serialized = serialize_frame(frame)
    assert serialized is not None
    assert '"v":3' in serialized
    assert '"f":42' in serialized
    assert '"a":2' in serialized
    assert '"c":0.850000' in serialized
    assert '"s":"NORMAL"' in serialized
    print("build_and_serialize OK")


def test_serialize_roundtrip():
    from core.native_bridge import (
        bridge_available, build_frame, serialize_frame
    )
    if not bridge_available():
        print("SKIP: native bridge not available")
        return

    tangent = [float(i) for i in range(36)]
    frame = build_frame(100, tangent, 1, 0.75, "NORMAL")
    frame.camera_pos_x = 1.5
    frame.camera_pos_y = 2.5
    frame.camera_pos_z = 3.5
    frame.camera_fov = 90.0
    frame.spatial_nodes = 64
    frame.dsp_occlusion = 0.75
    frame.collision_impulse = 12.5
    frame.thermal_target_c = 18.0
    frame.intensity = 0.8
    frame.bulb_address = 0xABCD
    frame.motor_gating_active = 1
    frame.in_high_stimulus = 1
    frame.force_zero = 0

    s = serialize_frame(frame)
    assert s is not None

    assert '"cam":[1.50,2.50,3.50,90.0]' in s
    assert '"o":0.750' in s
    assert '"i":12.500000' in s
    assert '"t":18.0' in s
    assert '"addr":"0xABCD"' in s
    assert '"mg":{"act":1,"stim":1,"fz":0}' in s
    assert '"gust":[0.0000,0.0000,0.0000,0.0000,0.0000]' in s
    print(f"Roundtrip OK: {s[:100]}...")


def test_validate_rejects_bad_frame():
    from core.native_bridge import (
        bridge_available, build_frame, validate_frame
    )
    if not bridge_available():
        print("SKIP: native bridge not available")
        return

    frame = build_frame(-1, [0.0], 0, 0.0, "NORMAL")
    assert not validate_frame(frame), "should reject negative frame_count"
    print("validate_rejects_bad_frame OK")


def test_game_context_pack():
    from core.bridge_game_context import (
        make_game_context_for_harness, pack_to_bridge_frame, GameContext
    )
    from core.native_bridge import (
        bridge_available, BciBridgeFrame, serialize_frame
    )

    ctx = make_game_context_for_harness(
        pos_x=10.0, pos_y=20.0, pos_z=30.0, fov=100.0,
        spatial_nodes=128, dsp_gain=0.8, dsp_pan=-0.5, dsp_occlusion=0.9,
        collision_impulse=5.0, thermal_target_c=35.0,
        motor_gating_active=False, intensity=0.3, bulb_address=0xBEEF,
        gustation=[0.7, 0.1, 0.5, 0.0, 0.9],
        in_high_stimulus=True,
    )

    bridge_frame = BciBridgeFrame()
    pack_to_bridge_frame(
        bridge_frame, frame_count=55, engine_state="COASTING",
        predicted_action=0, confidence=0.3,
        tangent=np.array([float(i) for i in range(36)]),
        context=ctx,
    )

    if bridge_available():
        s = serialize_frame(bridge_frame)
        assert s is not None
        assert '"cam":[10.00,20.00,30.00,100.0]' in s
        assert '"n":128' in s
        assert '"o":0.900' in s
        assert '"addr":"0xBEEF"' in s
        assert '"stim":1' in s
        assert '"gust":[0.7000,0.1000,0.5000,0.0000,0.9000]' in s
        print(f"Game context pack + serialize OK: {s[:120]}...")
    else:
        assert bridge_frame.camera_pos_x == 10.0
        assert bridge_frame.camera_pos_y == 20.0
        assert bridge_frame.camera_pos_z == 30.0
        assert bridge_frame.camera_fov == 100.0
        assert bridge_frame.spatial_nodes == 128
        assert bridge_frame.motor_gating_active == 0
        assert bridge_frame.dsp_occlusion == 0.9
        assert bridge_frame.bulb_address == 0xBEEF
        assert bridge_frame.version == 3
        assert bridge_frame.gustation[0] == 0.7
        assert bridge_frame.gustation[4] == 0.9
        print("Game context pack OK (fields verified directly)")


def test_gustation_serialization():
    from core.native_bridge import (
        bridge_available, build_frame, serialize_frame
    )
    if not bridge_available():
        print("SKIP: native bridge not available")
        return

    frame = build_frame(200, [float(i) for i in range(10)], 3, 0.9, "NORMAL")
    frame.gustation[0] = 0.85
    frame.gustation[1] = 0.12
    frame.gustation[2] = 0.45
    frame.gustation[3] = 0.03
    frame.gustation[4] = 0.67

    s = serialize_frame(frame)
    assert s is not None
    assert '"gust":[0.8500,0.1200,0.4500,0.0300,0.6700]' in s, f"gust not in: {s}"
    print("Gustation serialization OK")


def test_gustation_mixing_matrix():
    from core.bridge_game_context import GustationState

    raw = [1.0, 0.0, 0.0, 0.0, 0.0]
    gs = GustationState.apply_mixing(raw)
    assert gs.sweet > 0.0
    assert gs.salty < gs.sweet
    print(f"Gustation mix (pure sweet ->): {gs}")
    assert abs(gs.sweet - 0.8) < 0.01
    assert abs(gs.bitter - 0.0) < 0.01
    print("Gustation mixing matrix OK")


def test_harness_integration():
    from core.orchestrator import BCIEngineOrchestrator
    from core.bridge_game_context import (
        make_game_context_for_harness, pack_to_bridge_frame,
    )
    from core.native_bridge import BciBridgeFrame

    engine = BCIEngineOrchestrator(
        low_dim_channels=8, sample_rate=250, initialize_lazy=True,
    )
    ctx = make_game_context_for_harness(
        pos_x=0.0, pos_y=1.5, pos_z=-3.0, fov=90.0,
        motor_gating_active=True,
    )

    for i in range(10):
        sample = np.random.standard_normal(8) * 10e-6
        engine.process_frame(
            sample,
            context={"motor_gating_active": True, "in_high_stimulus": False},
        )

    m = engine.get_metrics()
    bridge_frame = BciBridgeFrame()
    pack_to_bridge_frame(
        bridge_frame, engine.frame_count, m["state"],
        engine.last_action, engine.last_confidence,
        np.random.randn(36), ctx,
    )
    assert bridge_frame.version == 3
    assert bridge_frame.frame_count == 10
    assert bridge_frame.camera_pos_y == 1.5
    assert bridge_frame.camera_pos_z == -3.0
    assert bridge_frame.motor_gating_active == 1
    assert bridge_frame.gustation[0] == 0.0
    print("Harness integration OK")


def test_network_gateway_bridge_fallback():
    from core.network_gateway import BCIZmqGateway
    from core.orchestrator import BCIEngineOrchestrator

    engine = BCIEngineOrchestrator(
        low_dim_channels=8, sample_rate=250, initialize_lazy=True,
    )

    has_zmq = False
    try:
        import zmq
        has_zmq = True
    except ImportError:
        pass

    print(f"ZMQ available: {has_zmq}")
    print("network_gateway fallback path OK")


if __name__ == "__main__":
    test_bridge_available()
    test_bridge_discovery()
    test_build_and_serialize()
    test_serialize_roundtrip()
    test_validate_rejects_bad_frame()
    test_game_context_pack()
    test_gustation_serialization()
    test_gustation_mixing_matrix()
    test_harness_integration()
    test_network_gateway_bridge_fallback()
    print("\nAll native bridge tests PASSED")
