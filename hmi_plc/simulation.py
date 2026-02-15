"""
Simulation types for HMI feedback variables (i*).
Multiple types selectable via dropdown; each has its own parameters.
"""
import math
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


# ── Simulation type registry: id -> (label, var_types, param_specs) ──
# param_specs: [(name, type, default, label)]
SIMULATION_TYPES = {
    "first_order": {
        "label": "First-order (Real)",
        "var_types": ["Real"],
        "params": [
            ("tau_seconds", "float", 0.7, "Time constant τ [s]"),
        ],
        "desc": "y(t) = target + (y0 - target) * exp(-t/τ)",
    },
    "bool_delay": {
        "label": "Boolean delay",
        "var_types": ["Bool"],
        "params": [
            ("delay_seconds", "float", 0.1, "Delay [s]"),
            ("trigger_variable", "str", "", "Trigger variable (output name)"),
        ],
        "desc": "Output becomes True delay_seconds after trigger_variable becomes True",
    },
    "instant": {
        "label": "Instant (no simulation)",
        "var_types": ["Bool", "Real", "Int"],
        "params": [],
        "desc": "Output = setpoint immediately",
    },
}


def get_simulation_types_for_var(var_type: str) -> List[Tuple[str, str]]:
    """Return [(id, label)] for types that support this var_type."""
    return [
        (tid, info["label"])
        for tid, info in SIMULATION_TYPES.items()
        if var_type in info["var_types"]
    ]


def get_params_for_type(type_id: str) -> List[Tuple[str, str, Any, str]]:
    """Return [(name, ptype, default, label)] for a simulation type."""
    info = SIMULATION_TYPES.get(type_id, {})
    return info.get("params", [])


class FirstOrderSimulator:
    """
    First-order regulation: output follows setpoint with time constant tau.
    y_new = y_target + (y_old - y_target) * exp(-dt/tau)
    """

    def __init__(self, tau_seconds: float = 0.7, initial: float = 0.0):
        """
        tau_seconds: time constant (e.g. 0.7 = 700 ms)
        initial: initial value
        """
        self.tau = max(0.001, tau_seconds)
        self.value = initial
        self.target = initial
        self._last_time: Optional[float] = None

    def set_target(self, target: float):
        self.target = float(target)

    def step(self, dt: Optional[float] = None) -> float:
        """Advance simulation by dt seconds. Returns current value."""
        now = time.monotonic()
        if self._last_time is None:
            self._last_time = now
            return self.value
        delta = dt if dt is not None else (now - self._last_time)
        self._last_time = now
        if delta <= 0:
            return self.value
        # First-order: y = target + (y0 - target) * exp(-dt/tau)
        self.value = self.target + (self.value - self.target) * math.exp(-delta / self.tau)
        return self.value

    def get_value(self) -> float:
        return self.value


class BoolDelaySimulator:
    """
    Boolean delay: output becomes True delay_seconds after trigger_variable becomes True.
    Output becomes False immediately when trigger becomes False.
    """

    def __init__(self, delay_seconds: float = 0.1, trigger_variable: str = ""):
        self.delay = max(0.0, delay_seconds)
        self.trigger_var = trigger_variable
        self.value = False
        self._triggered_at: Optional[float] = None
        self._last_trigger: bool = False
        self._last_time: Optional[float] = None

    def set_trigger(self, trigger_value: bool):
        self._last_trigger = trigger_value

    def step(self, dt: Optional[float] = None) -> bool:
        now = time.monotonic()
        if self._last_time is None:
            self._last_time = now
        delta = dt if dt is not None else (now - self._last_time)
        self._last_time = now
        if self._last_trigger:
            if self._triggered_at is None:
                self._triggered_at = now
            elapsed = now - self._triggered_at
            if elapsed >= self.delay:
                self.value = True
        else:
            self.value = False
            self._triggered_at = None
        return self.value

    def get_value(self) -> bool:
        return self.value


class InstantSimulator:
    """No simulation: output = setpoint immediately."""

    def __init__(self, initial: Any = False):
        self.value = initial

    def set_target(self, target: Any):
        self.value = target

    def step(self, dt: Optional[float] = None) -> Any:
        return self.value

    def get_value(self) -> Any:
        return self.value


class FeedbackSimulator:
    """
    Manages simulators for i* variables.
    Each variable has: type_id, setpoint_var, params.
    Supports first_order, bool_delay, instant.
    """

    DEFAULT_MAPPING = {
        "iChamberPressure": ("oChamberValvePR", "first_order", {"tau_seconds": 0.7}),
        "iInletValvePressure": ("oInletValvePR", "first_order", {"tau_seconds": 0.7}),
        "iOutletValvePressure": ("oOutletValvePR", "first_order", {"tau_seconds": 0.7}),
    }

    def __init__(self, config: Optional[Dict[str, Tuple[str, str, Dict]]] = None):
        """
        config: feedback_var -> (setpoint_var, type_id, params)
        """
        self.config = config or {
            k: (v[0], v[1], v[2].copy()) for k, v in self.DEFAULT_MAPPING.items()
        }
        self._sims: Dict[str, Any] = {}
        self._build_sims()

    def _build_sims(self):
        for fb_var, (sp_var, type_id, params) in self.config.items():
            if type_id == "first_order":
                tau = params.get("tau_seconds", 0.7)
                self._sims[fb_var] = FirstOrderSimulator(tau_seconds=tau, initial=0.0)
            elif type_id == "bool_delay":
                delay = params.get("delay_seconds", 0.1)
                trigger = params.get("trigger_variable", sp_var)
                self._sims[fb_var] = BoolDelaySimulator(delay_seconds=delay, trigger_variable=trigger)
            else:
                self._sims[fb_var] = InstantSimulator(initial=0.0)

    def set_config(self, feedback_var: str, setpoint_var: str, type_id: str, params: Dict):
        """Update config for one variable and rebuild its simulator."""
        self.config[feedback_var] = (setpoint_var, type_id, params)
        sp_var, _, p = self.config[feedback_var]
        if type_id == "first_order":
            self._sims[feedback_var] = FirstOrderSimulator(
                tau_seconds=p.get("tau_seconds", 0.7), initial=0.0
            )
        elif type_id == "bool_delay":
            self._sims[feedback_var] = BoolDelaySimulator(
                delay_seconds=p.get("delay_seconds", 0.1),
                trigger_variable=p.get("trigger_variable", setpoint_var),
            )
        else:
            self._sims[feedback_var] = InstantSimulator(initial=False)

    def update_setpoints(self, outputs: Dict[str, Any]):
        """Update targets from PLC outputs (setpoints)."""
        for fb_var, (sp_var, type_id, params) in self.config.items():
            sim = self._sims.get(fb_var)
            if sim is None:
                continue
            if type_id == "first_order" and sp_var in outputs:
                sim.set_target(outputs[sp_var])
            elif type_id == "bool_delay":
                trigger = params.get("trigger_variable", sp_var)
                if trigger in outputs:
                    sim.set_trigger(bool(outputs[trigger]))
            elif type_id == "instant" and sp_var in outputs:
                sim.set_target(outputs[sp_var])

    def step(self, dt: Optional[float] = None) -> Dict[str, Any]:
        """Advance all simulators. Returns simulated feedback values."""
        result = {}
        for name, sim in self._sims.items():
            result[name] = sim.step(dt)
        return result

    def get_feedbacks(self) -> Dict[str, Any]:
        """Current simulated values."""
        return {name: sim.get_value() for name, sim in self._sims.items()}
