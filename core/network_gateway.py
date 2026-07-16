import json
import numpy as np

try:
    import zmq
    _HAS_ZMQ = True
except ImportError:
    _HAS_ZMQ = False

_NATIVE_BRIDGE = None


def _try_load_native_bridge():
    global _NATIVE_BRIDGE
    if _NATIVE_BRIDGE is not None:
        return _NATIVE_BRIDGE
    try:
        from core.native_bridge import serialize_frame, build_frame, BciBridgeFrame
        _NATIVE_BRIDGE = {
            "serialize": serialize_frame,
            "build": build_frame,
            "frame_type": BciBridgeFrame,
        }
        return _NATIVE_BRIDGE
    except Exception:
        _NATIVE_BRIDGE = False
        return None


class BCIZmqGateway:
    def __init__(self, port=5555, host="127.0.0.1", health_port=5557,
                 use_native_bridge=False):
        if not _HAS_ZMQ:
            print("pyzmq not installed. Install with `pip install pyzmq`.")
            self._enabled = False
            return
        self._enabled = True
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.set_hwm(10)
        self.socket.bind(f"tcp://{host}:{port}")
        print(f"ZeroMQ gateway active on {host}:{port} (PUB)")
        self.health_socket = self.context.socket(zmq.REP)
        self.health_socket.bind(f"tcp://{host}:{health_port}")
        print(f"Health REP active on {host}:{health_port}")

        self.use_native_bridge = use_native_bridge
        if use_native_bridge:
            nb = _try_load_native_bridge()
            if nb:
                print("Native bridge loaded for frame serialization")
            else:
                print("Native bridge not available, falling back to Python")
                self.use_native_bridge = False

    def _serialize_via_native(self, sample_id, state_name, v_t,
                               action_id, confidence) -> str:
        nb = _try_load_native_bridge()
        if nb is None:
            return None
        if isinstance(v_t, np.ndarray):
            v_list = v_t.flatten().tolist()
        else:
            v_list = list(v_t)
        frame = nb["build"](
            sample_id, v_list, action_id, confidence, state_name,
        )
        return nb["serialize"](frame)

    def publish_frame(self, sample_id, state_name, v_t, action_id, confidence):
        if not self._enabled:
            return

        if self.use_native_bridge:
            payload_str = self._serialize_via_native(
                sample_id, state_name, v_t, action_id, confidence,
            )
            if payload_str is not None:
                try:
                    self.socket.send_string(payload_str, zmq.NOBLOCK)
                    return
                except zmq.Again:
                    pass

        payload = {
            "type": "frame",
            "sample_id": int(sample_id),
            "engine_state": state_name,
            "tangent_vector": v_t.tolist() if isinstance(v_t, np.ndarray) else v_t,
            "predicted_action": int(action_id),
            "confidence": float(confidence),
        }
        try:
            self.socket.send_string(json.dumps(payload), zmq.NOBLOCK)
        except zmq.Again:
            pass

    def publish_heartbeat(self, state_name, uptime_sec, frame_count):
        if not self._enabled:
            return
        payload = {
            "type": "heartbeat",
            "engine_state": state_name,
            "uptime_sec": uptime_sec,
            "frame_count": frame_count,
        }
        try:
            self.socket.send_string(json.dumps(payload), zmq.NOBLOCK)
        except zmq.Again:
            pass

    def publish_game_frame(self, bridge_frame, state_name, uptime_sec):
        if not self._enabled:
            return
        nb = _try_load_native_bridge()
        if nb is not None:
            payload_str = nb["serialize"](bridge_frame)
            if payload_str is not None:
                try:
                    self.socket.send_string(payload_str, zmq.NOBLOCK)
                    return
                except zmq.Again:
                    pass

        payload = {
            "type": "game_frame",
            "state": state_name,
            "uptime_sec": uptime_sec,
            "frame_count": bridge_frame.frame_count,
            "action": bridge_frame.predicted_action,
            "confidence": bridge_frame.confidence,
            "camera": [
                bridge_frame.camera_pos_x,
                bridge_frame.camera_pos_y,
                bridge_frame.camera_pos_z,
                bridge_frame.camera_fov,
            ],
            "audio": {
                "nodes": bridge_frame.spatial_nodes,
                "occlusion": bridge_frame.dsp_occlusion,
            },
            "impact": bridge_frame.collision_impulse,
            "thermal": bridge_frame.thermal_target_c,
            "motor_gate": bridge_frame.motor_gating_active,
        }
        try:
            self.socket.send_string(json.dumps(payload), zmq.NOBLOCK)
        except zmq.Again:
            pass

    def try_recv_health_request(self):
        if not self._enabled:
            return None
        try:
            return self.health_socket.recv_json(zmq.NOBLOCK)
        except zmq.Again:
            return None

    def send_health_response(self, data):
        if self._enabled:
            self.health_socket.send_json(data)

    def close(self):
        if self._enabled:
            self.health_socket.close()
            self.socket.close()
            self.context.term()
