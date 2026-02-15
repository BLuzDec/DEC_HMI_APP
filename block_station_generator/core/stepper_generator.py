"""
Generates SCL stepper logic from GrafcetModel.
Outputs {STEPPER_LOGIC} and {STATE_CONSTANTS} for FB_Template.scl.
"""
from .grafcet_model import GrafcetModel, GrafcetStep


def generate_state_constants(model: GrafcetModel) -> str:
    """Generate VAR CONSTANT section for state numbers."""
    lines = []
    for s in model.steps:
        const_name = f"S{s.value}_{s.name}"
        lines.append(f"      {const_name} : Int := {s.value};")
    return "\n".join(lines)


def _resolve_next_step(model: GrafcetModel, next_id: str) -> str:
    """Resolve next step id to full constant name."""
    step = model.get_step(next_id)
    if step:
        return f"#S{step.value}_{step.name}"
    return f"#{next_id}"  # Fallback


def generate_stepper_logic(model: GrafcetModel) -> str:
    """
    Generate CASE steps for {STEPPER_LOGIC}.
    Follows FB_MPTS pattern: bFirstStepCycle for init, transition for next step.
    """
    lines = []
    for s in model.steps:
        transition = s.transition.strip() if s.transition else "TRUE"
        next_ids = s.next_steps
        if not next_ids:
            next_step = "#S100_IDLE"  # Default to IDLE
        else:
            next_step = _resolve_next_step(model, next_ids[0])
        const_name = f"S{s.value}_{s.name}"
        lines.append(f"	    #{const_name}:")
        lines.append(f"	        IF #bFirstStepCycle THEN")
        lines.append(f"	            // Init: set outputs, etc.")
        lines.append(f"	        ELSE")
        lines.append(f"	            IF {transition} THEN")
        lines.append(f"	                #_Step := {next_step};")
        lines.append(f"	            END_IF;")
        lines.append(f"	        END_IF;")
        lines.append("	    // ---------------------------------------------------------------------------------")
    return "\n".join(lines)
