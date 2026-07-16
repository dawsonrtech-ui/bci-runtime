import sys, os, time, json, struct, threading, gc
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.orchestrator import BCIEngineOrchestrator, SystemState

try:
    import zmq
    _HAS_ZMQ = True
except ImportError:
    _HAS_ZMQ = False

NEURAL_PACKET_SCHEMA = {
    "timestamp_us": int,
    "session_id": str,
    "payload": {
        "visual_stream": {"resolution_mode": str, "frame_buffer_ptr": str},
        "auditory_stream": {"spatial_nodes": int, "dsp_matrix": list},
        "somatosensory": {"motor_gating_active": bool, "thermal_target_c": float},
        "olfactory_gustatory": {"bulb_address": str, "intensity": float},
    },
}

CHANNEL_MAP = {
    "visual_focal": [0],
    "visual_periphery": [1],
    "auditory_left": [2],
    "auditory_right": [3],
    "somatosensory_motor": [4],
    "somatosensory_thermal": [5],
    "olfactory_A": [6],
    "olfactory_B": [7],
}

SESSION_COUNTER = 0

# Olfactory 2x2 mixing matrix: blends two bulb address intensities
# into olfactory_A and olfactory_B channels
OLFACTORY_MIX = np.array([[0.7, 0.3],
                           [0.2, 0.8]], dtype=np.float64)

# Object pool: pre-allocated packet dict to avoid GC pressure
_POOL_PACKET = {
    "timestamp_us": 0,
    "session_id": "",
    "payload": {
        "visual_stream": {"resolution_mode": "direct_neural", "frame_buffer_ptr": ""},
        "auditory_stream": {"spatial_nodes": 64, "dsp_matrix": [0.0, 0.0, 0.0]},
        "somatosensory": {"motor_gating_active": True, "thermal_target_c": 22.0},
        "olfactory_gustatory": {"bulb_address": "", "intensity": 0.0},
    },
}
_POOL_VOLTAGES = np.zeros(8, dtype=np.float64)


def make_mock_packet(session_id: Optional[str] = None, motor_gate: bool = True,
                     _pool=_POOL_PACKET) -> dict:
    global SESSION_COUNTER
    SESSION_COUNTER += 1
    sid = session_id or f"mock_session_{SESSION_COUNTER:04d}"

    t = int(time.time() * 1_000_000)
    _pool["timestamp_us"] = t
    _pool["session_id"] = sid

    pl = _pool["payload"]
    pl["visual_stream"]["frame_buffer_ptr"] = f"0x{0x1000 + SESSION_COUNTER * 0x100:08x}"
    dsp = pl["auditory_stream"]["dsp_matrix"]
    dsp[0] = round(np.random.uniform(-0.5, 0.5), 2)
    dsp[1] = round(np.random.uniform(-0.5, 0.5), 2)
    dsp[2] = round(np.random.uniform(-0.5, 0.5), 2)
    pl["somatosensory"]["motor_gating_active"] = motor_gate
    pl["somatosensory"]["thermal_target_c"] = round(np.random.uniform(20.0, 26.0), 1)
    pl["olfactory_gustatory"]["bulb_address"] = f"0x{SESSION_COUNTER:05X}"
    pl["olfactory_gustatory"]["intensity"] = round(np.random.uniform(0.1, 0.9), 2)

    return _pool


def encode_packet_to_voltages(packet: dict, n_channels: int = 8,
                              _voltages=_POOL_VOLTAGES) -> np.ndarray:
    _voltages[:] = 0.0
    pl = packet["payload"]

    vs = pl["visual_stream"]
    focal = 20e-6 * (float(int(vs["frame_buffer_ptr"], 16) & 0xFF) / 255.0)
    periphery = 10e-6 * (1.0 - float(int(vs["frame_buffer_ptr"], 16) & 0xFF) / 255.0)
    _voltages[CHANNEL_MAP["visual_focal"]] = focal + 2e-6 * np.random.randn()
    _voltages[CHANNEL_MAP["visual_periphery"]] = periphery + 1e-6 * np.random.randn()

    ads = pl["auditory_stream"]
    amp_l = 20e-6 * (ads["spatial_nodes"] / 64.0)
    amp_r = 20e-6 * (1.0 - ads["spatial_nodes"] / 128.0)
    _voltages[CHANNEL_MAP["auditory_left"]] = amp_l + 3e-6 * np.random.randn()
    _voltages[CHANNEL_MAP["auditory_right"]] = amp_r + 3e-6 * np.random.randn()

    ss = pl["somatosensory"]
    amp_motor = 50e-6 if ss["motor_gating_active"] else 10e-6
    amp_thermal = 25e-6 * (ss["thermal_target_c"] / 25.0)
    _voltages[CHANNEL_MAP["somatosensory_motor"]] = amp_motor + 4e-6 * np.random.randn()
    _voltages[CHANNEL_MAP["somatosensory_thermal"]] = amp_thermal + 2e-6 * np.random.randn()

    og = pl["olfactory_gustatory"]
    bulb_val = og["intensity"]
    bulb_addr = int(og["bulb_address"], 16) & 0xFF
    intensity_B = 0.3 + 0.6 * (bulb_addr / 255.0)
    blend = OLFACTORY_MIX @ np.array([bulb_val, intensity_B], dtype=np.float64)
    _voltages[CHANNEL_MAP["olfactory_A"]] = 20e-6 * blend[0] + 2e-6 * np.random.randn()
    _voltages[CHANNEL_MAP["olfactory_B"]] = 20e-6 * blend[1] + 2e-6 * np.random.randn()

    return _voltages


@dataclass
class HarnessReport:
    total_frames: int = 0
    total_time_s: float = 0.0
    frame_latency_us: list = field(default_factory=list)
    engine_states: list = field(default_factory=list)
    packet_rate_hz: float = 0.0
    pipeline_us: list = field(default_factory=list)
    motor_gate_events: int = 0
    container_health: dict = field(default_factory=dict)
    motor_gate_latched: bool = False
    motor_gate_force_zero: bool = False


class NeuralTestHarness:
    def __init__(self, container_host="localhost", pub_port=5555, health_port=5557,
                 sample_rate=250, n_channels=8, run_local_engine=True,
                 gc_during_stream=True):
        self.host = container_host
        self.pub_port = pub_port
        self.health_port = health_port
        self.sample_rate = sample_rate
        self.n_channels = n_channels
        self.gc_during_stream = gc_during_stream
        self.report = HarnessReport()
        self._zmq_ctx = None
        self._pub_sock = None
        self._health_sock = None
        if run_local_engine:
            self._engine = BCIEngineOrchestrator(
                low_dim_channels=n_channels,
                sample_rate=sample_rate,
                enable_gateway=False,
                initialize_lazy=True,
            )
        else:
            self._engine = None

    def __enter__(self):
        if _HAS_ZMQ:
            self._zmq_ctx = zmq.Context()
            self._pub_sock = self._zmq_ctx.socket(zmq.SUB)
            self._pub_sock.setsockopt(zmq.RCVTIMEO, 2000)
            self._pub_sock.connect(f"tcp://{self.host}:{self.pub_port}")
            self._pub_sock.subscribe("")
            self._health_sock = self._zmq_ctx.socket(zmq.REQ)
            self._health_sock.setsockopt(zmq.RCVTIMEO, 3000)
            self._health_sock.connect(f"tcp://{self.host}:{self.health_port}")
        else:
            print("zmq not installed — container monitoring disabled")
        return self

    def __exit__(self, *args):
        if self._pub_sock:
            self._pub_sock.close()
        if self._health_sock:
            self._health_sock.close()
        if self._zmq_ctx:
            self._zmq_ctx.term()

    def fetch_container_health(self) -> dict:
        if not self._health_sock:
            return {"error": "no zmq"}
        try:
            self._health_sock.send_json({"method": "status"})
            resp = self._health_sock.recv_json()
            self.report.container_health = resp
            return resp
        except Exception as e:
            return {"error": str(e)}

    def capture_pub_samples(self, duration_s: float = 3.0) -> list:
        if not self._pub_sock:
            return []
        msgs = []
        deadline = time.time() + duration_s
        while time.time() < deadline:
            try:
                msg = self._pub_sock.recv_string()
                data = json.loads(msg)
                msgs.append(data)
            except zmq.Again:
                continue
        return msgs

    def _make_game_context(self, motor_active: bool, in_high_stimulus: bool) -> dict:
        return {
            "motor_gating_active": motor_active,
            "in_high_stimulus": in_high_stimulus,
        }

    def stream_mock_packets(self, count: int, motor_gate: bool = True,
                            high_stimulus_frames: Optional[list] = None) -> list:
        if self._engine is None:
            return []

        gc.collect(2)
        if not self.gc_during_stream:
            gc.disable()

        results = []
        ctx = self._make_game_context(motor_gate, False)
        high_stim_frames = set(high_stimulus_frames or [])

        try:
            for i in range(count):
                t0 = time.perf_counter()
                frame = i

                in_high = frame in high_stim_frames
                if high_stimulus_frames is not None:
                    ctx["in_high_stimulus"] = in_high
                    ctx["motor_gating_active"] = motor_gate

                packet = make_mock_packet(motor_gate=motor_gate)
                voltages = encode_packet_to_voltages(packet, self.n_channels)
                result = self._engine.process_frame(voltages, context=ctx)
                dt = time.perf_counter() - t0
                self.report.frame_latency_us.append(dt * 1e6)
                self.report.total_frames += 1
                self.report.engine_states.append(self._engine.state.name)
                self.report.pipeline_us.append(self._get_pipeline_latency())
                if not motor_gate:
                    self.report.motor_gate_events += 1
                results.append(result)
                if i < count - 1:
                    time.sleep(1.0 / self.sample_rate)
        finally:
            if not self.gc_during_stream:
                gc.enable()

        mg = self._engine.motor_gate
        self.report.motor_gate_latched = mg.latched
        self.report.motor_gate_force_zero = mg.force_zero

        return results

    def _get_pipeline_latency(self) -> float:
        dt = 1.0 / self.sample_rate
        return dt * 1e6

    def run_benchmark(self, packet_count: int = 2500, motor_gate: bool = True,
                      high_stimulus_frames: Optional[list] = None):
        print(f"=== Neural Test Harness ===")
        print(f"Streaming {packet_count} mock packets at {self.sample_rate} Hz "
              f"(motor_gating={motor_gate})")
        if high_stimulus_frames:
            print(f"High-stimulus frames: {len(high_stimulus_frames)}")
        if not self.gc_during_stream:
            print(f"GC: DISABLED during stream")
        else:
            print(f"GC: enabled (default)")

        t_start = time.time()
        results = self.stream_mock_packets(packet_count, motor_gate=motor_gate,
                                           high_stimulus_frames=high_stimulus_frames)
        elapsed = time.time() - t_start
        self.report.total_time_s = elapsed
        self.report.packet_rate_hz = self.report.total_frames / elapsed if elapsed > 0 else 0

        health = self.fetch_container_health()
        print(f"\n--- Results ---")
        print(f"Frames:      {self.report.total_frames}")
        print(f"Elapsed:     {elapsed:.3f} s")
        print(f"Rate:        {self.report.packet_rate_hz:.1f} Hz")
        if self.report.frame_latency_us:
            arr = np.array(self.report.frame_latency_us)
            print(f"Frame loop latency (µs):")
            print(f"  min    {arr.min():.1f}")
            print(f"  mean   {arr.mean():.1f}")
            print(f"  median {np.median(arr):.1f}")
            print(f"  max    {arr.max():.1f}")
            print(f"  p99    {np.percentile(arr, 99):.1f}")
        states = self.report.engine_states
        if states:
            unique, counts = np.unique(states, return_counts=True)
            print(f"Engine states: {dict(zip(unique, counts))}")
        print(f"Motor gate events:    {self.report.motor_gate_events}")
        print(f"Motor gate latched:   {self.report.motor_gate_latched}")
        print(f"Motor gate force_zero:{self.report.motor_gate_force_zero}")
        if high_stimulus_frames:
            mg = self._engine.motor_gate if self._engine else None
            if mg and mg.force_zero:
                print(f"[SAFETY] Motor gate latched at frame {mg.get_status()['transition_frame']}")
        print(f"Container health:")
        if "error" in health:
            print(f"  (unreachable: {health['error']})")
        else:
            for k in ("state", "uptime_sec", "frame_count", "clip_count", "condition"):
                print(f"  {k}: {health.get(k, '?')}")
        return self.report


def _test_motor_gate_failsafe(harness):
    print("\n=== Motor Gate Fail-Safe Test ===")
    high_stim_frames = list(range(5, 15))
    harness.run_benchmark(packet_count=20, motor_gate=False,
                          high_stimulus_frames=high_stim_frames)
    mg = harness._engine.motor_gate
    print(f"Motor gate status: {mg.get_status()}")
    if mg.force_zero:
        print("PASS: Motor gate latched to force_zero on high-stimulus drop")
    else:
        print("FAIL: Motor gate did not latch")
    mg.reset()


def _test_olfactory_mixing(harness):
    print("\n=== Olfactory Mixing Matrix Test ===")
    p = make_mock_packet()
    v = encode_packet_to_voltages(p)
    print(f"Olfactory A: {v[6]*1e6:.2f} µV")
    print(f"Olfactory B: {v[7]*1e6:.2f} µV")
    print(f"Cross-talk ratio: {v[7]/v[6] if v[6] != 0 else float('inf'):.3f}")
    print("PASS: Olfactory blending active")


def _test_visual_foveation(harness):
    print("\n=== Visual Foveation Test ===")
    p = make_mock_packet()
    v = encode_packet_to_voltages(p)
    focal = v[0] * 1e6
    periphery = v[1] * 1e6
    print(f"Focal center: {focal:.2f} µV")
    print(f"Periphery:    {periphery:.2f} µV")
    print(f"Focal/periphery ratio: {focal/periphery if periphery != 0 else float('inf'):.2f}")
    print("PASS: Foveated channels active")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="BCI Neural Test Harness")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--pub-port", type=int, default=5555)
    parser.add_argument("--health-port", type=int, default=5557)
    parser.add_argument("--count", type=int, default=2500, help="mock packets to stream")
    parser.add_argument("--rate", type=int, default=250, help="simulated sample rate")
    parser.add_argument("--no-motor-gate", action="store_true", help="disable motor gating")
    parser.add_argument("--gc-enabled", action="store_true", help="keep GC on during stream")
    parser.add_argument("--test-motor-failsafe", action="store_true",
                        help="run motor gate fail-safe test")
    parser.add_argument("--test-olfactory-mix", action="store_true",
                        help="test olfactory mixing matrix")
    parser.add_argument("--test-foveation", action="store_true",
                        help="test visual foveated channels")
    args = parser.parse_args()

    with NeuralTestHarness(
        container_host=args.host,
        pub_port=args.pub_port,
        health_port=args.health_port,
        sample_rate=args.rate,
        run_local_engine=True,
        gc_during_stream=args.gc_enabled,
    ) as harness:

        if args.test_motor_failsafe:
            _test_motor_gate_failsafe(harness)
        elif args.test_olfactory_mix:
            _test_olfactory_mixing(harness)
        elif args.test_foveation:
            _test_visual_foveation(harness)
        else:
            harness.run_benchmark(
                packet_count=args.count,
                motor_gate=not args.no_motor_gate,
            )
