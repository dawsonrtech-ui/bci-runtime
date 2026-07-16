from dataclasses import dataclass, field
from typing import Optional, List
import numpy as np


@dataclass
class CameraRig:
    pos_x: float = 0.0
    pos_y: float = 0.0
    pos_z: float = 0.0
    fov: float = 90.0

    def update_from_unity(self, x: float, y: float, z: float, fov: float):
        self.pos_x, self.pos_y, self.pos_z = x, y, z
        self.fov = fov


@dataclass
class AudioGeometry:
    spatial_nodes: int = 64
    dsp_gain: float = 1.0
    dsp_pan: float = 0.0
    dsp_occlusion: float = 0.0


@dataclass
class SomatosensoryState:
    collision_impulse: float = 0.0
    thermal_target_c: float = 22.0
    motor_gating_active: bool = True


@dataclass
class OlfactoryState:
    intensity: float = 0.5
    bulb_address: int = 0


@dataclass
class GustationState:
    sweet: float = 0.0
    salty: float = 0.0
    sour: float = 0.0
    bitter: float = 0.0
    umami: float = 0.0

    def as_list(self) -> List[float]:
        return [self.sweet, self.salty, self.sour, self.bitter, self.umami]

    @staticmethod
    def apply_mixing(raw: List[float]) -> "GustationState":
        m = np.array([
            [0.8, 0.1, 0.0, 0.0, 0.1],
            [0.1, 0.7, 0.1, 0.0, 0.1],
            [0.0, 0.1, 0.8, 0.1, 0.0],
            [0.0, 0.0, 0.1, 0.9, 0.0],
            [0.1, 0.1, 0.0, 0.0, 0.8],
        ], dtype=np.float64)
        mixed = m @ np.array(raw[:5], dtype=np.float64)
        return GustationState(
            sweet=float(mixed[0]),
            salty=float(mixed[1]),
            sour=float(mixed[2]),
            bitter=float(mixed[3]),
            umami=float(mixed[4]),
        )


@dataclass
class GameContext:
    camera: CameraRig = field(default_factory=CameraRig)
    audio: AudioGeometry = field(default_factory=AudioGeometry)
    somatosensory: SomatosensoryState = field(default_factory=SomatosensoryState)
    olfactory: OlfactoryState = field(default_factory=OlfactoryState)
    gustation: GustationState = field(default_factory=GustationState)
    in_high_stimulus: bool = False


def pack_to_bridge_frame(
    bridge_frame,
    frame_count: int,
    engine_state: str,
    predicted_action: int,
    confidence: float,
    tangent: np.ndarray,
    context: GameContext,
):
    if isinstance(tangent, np.ndarray):
        tangent_list = tangent.flatten().tolist()
    else:
        tangent_list = list(tangent)

    bridge_frame.version = 3
    bridge_frame.frame_count = frame_count
    bridge_frame.n_tangent = len(tangent_list)
    for i, v in enumerate(tangent_list):
        if i >= 136:
            break
        bridge_frame.tangent[i] = v
    bridge_frame.predicted_action = predicted_action
    bridge_frame.confidence = confidence
    bridge_frame.engine_state = engine_state.encode("utf-8")

    bridge_frame.camera_pos_x = context.camera.pos_x
    bridge_frame.camera_pos_y = context.camera.pos_y
    bridge_frame.camera_pos_z = context.camera.pos_z
    bridge_frame.camera_fov = context.camera.fov

    bridge_frame.spatial_nodes = context.audio.spatial_nodes
    bridge_frame.dsp_gain = context.audio.dsp_gain
    bridge_frame.dsp_pan = context.audio.dsp_pan
    bridge_frame.dsp_occlusion = context.audio.dsp_occlusion

    bridge_frame.collision_impulse = context.somatosensory.collision_impulse
    bridge_frame.thermal_target_c = context.somatosensory.thermal_target_c
    bridge_frame.motor_gating_active = int(context.somatosensory.motor_gating_active)
    bridge_frame.in_high_stimulus = int(context.in_high_stimulus)

    bridge_frame.intensity = context.olfactory.intensity
    bridge_frame.bulb_address = context.olfactory.bulb_address

    for i, v in enumerate(context.gustation.as_list()):
        if i < 5:
            bridge_frame.gustation[i] = v


def make_game_context_for_harness(
    pos_x=0.0, pos_y=0.0, pos_z=0.0, fov=90.0,
    spatial_nodes=64, dsp_gain=1.0, dsp_pan=0.0, dsp_occlusion=0.0,
    collision_impulse=0.0, thermal_target_c=22.0,
    motor_gating_active=True, intensity=0.5, bulb_address=0,
    gustation: Optional[List[float]] = None,
    in_high_stimulus=False,
) -> GameContext:
    if gustation and len(gustation) >= 5:
        gs = GustationState(*gustation[:5])
    else:
        gs = GustationState()
    return GameContext(
        camera=CameraRig(pos_x, pos_y, pos_z, fov),
        audio=AudioGeometry(spatial_nodes, dsp_gain, dsp_pan, dsp_occlusion),
        somatosensory=SomatosensoryState(
            collision_impulse, thermal_target_c, motor_gating_active
        ),
        olfactory=OlfactoryState(intensity, bulb_address),
        gustation=gs,
        in_high_stimulus=in_high_stimulus,
    )


__all__ = [
    "CameraRig",
    "AudioGeometry",
    "SomatosensoryState",
    "OlfactoryState",
    "GustationState",
    "GameContext",
    "pack_to_bridge_frame",
    "make_game_context_for_harness",
]
