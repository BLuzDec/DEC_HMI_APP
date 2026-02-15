"""
Grafcet data model for steps and transitions.
Used to build the stepper logic for Siemens SCL function blocks.
JSON is the portable format (export/import, version control).
"""
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GrafcetStep:
    """A single step in the GRAFCET."""
    id: str  # e.g. "S10", "S20"
    name: str  # e.g. "INIT_CLOSE_OUTLET"
    value: int  # Numeric value for SCL constant, e.g. 10, 20
    order: int  # Display/editing order (for move up/down)
    transition: str = ""  # Condition to go to next step(s), e.g. "#ton_S10.Q"
    next_steps: list[str] = field(default_factory=list)  # Step IDs to transition to
    actions: str = ""  # Actions performed in this step, e.g. "Open valve, Start timer"


@dataclass
class GrafcetModel:
    """Complete GRAFCET model with steps and transitions."""
    steps: list[GrafcetStep] = field(default_factory=list)

    def add_step(self, step: GrafcetStep) -> None:
        step.order = len(self.steps)
        self.steps.append(step)

    def remove_step(self, step_id: str) -> bool:
        for i, s in enumerate(self.steps):
            if s.id == step_id:
                self.steps.pop(i)
                self._reorder()
                return True
        return False

    def move_step_up(self, step_id: str) -> bool:
        for i, s in enumerate(self.steps):
            if s.id == step_id and i > 0:
                self.steps[i], self.steps[i - 1] = self.steps[i - 1], self.steps[i]
                self._reorder()
                return True
        return False

    def move_step_down(self, step_id: str) -> bool:
        for i, s in enumerate(self.steps):
            if s.id == step_id and i < len(self.steps) - 1:
                self.steps[i], self.steps[i + 1] = self.steps[i + 1], self.steps[i]
                self._reorder()
                return True
        return False

    def _reorder(self) -> None:
        for i, s in enumerate(self.steps):
            s.order = i

    def get_step(self, step_id: str) -> Optional[GrafcetStep]:
        for s in self.steps:
            if s.id == step_id:
                return s
        return None

    def to_json(self, indent: int = 2) -> str:
        """Export to JSON (portable format, markdown equivalent)."""
        data = {
            "steps": [
                {
                    "id": s.id,
                    "name": s.name,
                    "value": s.value,
                    "order": s.order,
                    "transition": s.transition,
                    "next_steps": s.next_steps,
                    "actions": getattr(s, "actions", "") or "",
                }
                for s in self.steps
            ]
        }
        return json.dumps(data, indent=indent)

    @classmethod
    def from_json(cls, text: str) -> "GrafcetModel":
        """Import from JSON."""
        data = json.loads(text)
        model = cls()
        for i, s in enumerate(data.get("steps", [])):
            next_steps = s.get("next_steps", [])
            if isinstance(next_steps, str):
                next_steps = [x.strip() for x in next_steps.split(",") if x.strip()]
            next_steps = [str(x) for x in next_steps]
            step = GrafcetStep(
                id=str(s.get("id", f"S{(i+1)*10}")),
                name=str(s.get("name", f"STEP_{s.get('id', '')}")),
                value=int(s.get("value", (i + 1) * 10)),
                order=int(s.get("order", i)),
                transition=str(s.get("transition", "")),
                next_steps=next_steps,
                actions=str(s.get("actions", "")),
            )
            model.add_step(step)
        return model
