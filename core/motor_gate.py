import numpy as np


class MotorGateController:
    def __init__(self, default_active=True, n_sensory_channels=6):
        self._active = default_active
        self._prev_active = default_active
        self._in_high_stimulus = False
        self._force_zero = False
        self._transition_frame = -1
        self._n_sensory = n_sensory_channels
        self._latched = False

    @property
    def active(self):
        return self._active and not self._force_zero

    @property
    def force_zero(self):
        return self._force_zero

    @property
    def latched(self):
        return self._latched

    def update(self, motor_gating_active: bool, in_high_stimulus: bool, frame_count: int):
        self._prev_active = self._active
        self._active = motor_gating_active

        if in_high_stimulus:
            self._in_high_stimulus = True

        if not self._active and self._in_high_stimulus and not self._force_zero:
            self._force_zero = True
            self._transition_frame = frame_count
            self._latched = True
            print(
                "[MOTOR-GATE SAFETY] Gate dropped in high-stimulus state. "
                f"Sensory output forced to 0 µV at frame {frame_count}."
            )

        if self._active and not in_high_stimulus:
            if self._force_zero:
                print(
                    f"[MOTOR-GATE] Gate restored. Sensory output un-muted "
                    f"at frame {frame_count}."
                )
            self._force_zero = False

    def apply_gate(self, sensory_voltages: np.ndarray, motor_idx: slice) -> np.ndarray:
        if self._force_zero:
            sensory_voltages = sensory_voltages.copy()
            sensory_voltages[:] = 0.0
        elif not self._active:
            sensory_voltages = sensory_voltages.copy()
            sensory_voltages[motor_idx] *= 0.2
        return sensory_voltages

    def reset(self):
        self._active = True
        self._prev_active = True
        self._in_high_stimulus = False
        self._force_zero = False
        self._transition_frame = -1
        self._latched = False

    def get_status(self) -> dict:
        return {
            "motor_gate_active": self._active,
            "force_zero": self._force_zero,
            "latched": self._latched,
            "in_high_stimulus": self._in_high_stimulus,
            "transition_frame": self._transition_frame,
        }
