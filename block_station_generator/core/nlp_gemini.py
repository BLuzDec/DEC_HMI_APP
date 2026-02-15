"""
NLP via Gemini API for Grafcet generation.
API key from environment: GEMINI_API_KEY or GOOGLE_API_KEY (set in venv/.env).
Returns structured JSON only - no conversational text.
"""
import os
import json
import re
import time
from datetime import datetime
from typing import Optional, Callable

from .grafcet_model import GrafcetModel, GrafcetStep

# Debug log: set GRAFCET_NLP_DEBUG=1 to write to block_station_generator/grafcet_nlp_debug.log
_DEBUG_LOG_PATH = None
if os.environ.get("GRAFCET_NLP_DEBUG"):
    _DEBUG_LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "grafcet_nlp_debug.log")

# Load .env from block_station_generator/ (next to core/)
_env_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_env_dir, ".env"))
except ImportError:
    pass


def _get_api_key() -> Optional[str]:
    """API key from env - user provides in venv/local only."""
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def _build_system_prompt() -> str:
    return """You are a GRAFCET/stepper designer for industrial PLC (Siemens SCL).
Output ONLY valid JSON. No explanations, no markdown, no extra text.
Schema: {"steps": [{"id": "S10", "name": "INIT", "value": 10, "transition": "condition", "next_steps": ["S20"], "actions": "action list"}]}
- id: step id like S10, S20 (S + number)
- name: short UPPER_SNAKE_CASE name
- value: integer (10, 20, 30...)
- transition: SCL condition (e.g. "#ton.Q" or "TRUE")
- next_steps: list of step ids to transition to (empty = goes to IDLE)
- actions: comma-separated actions performed in this step (e.g. "Open valve, Start timer")
"""


def generate_grafcet_from_prompt(
    prompt: str,
    status_callback: Optional[Callable[[str], None]] = None,
) -> tuple[Optional[GrafcetModel], Optional[str]]:
    """
    Call Gemini API with prompt, parse structured JSON into GrafcetModel.
    status_callback(msg) is called with progress messages for debugging.
    Returns (model, error_message). error_message is set if API key missing or parse fails.
    """
    def _status(msg: str):
        if status_callback:
            status_callback(msg)
        if _DEBUG_LOG_PATH:
            try:
                with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now().isoformat()}] {msg}\n")
            except Exception:
                pass

    api_key = _get_api_key()
    if not api_key:
        return None, "Set GEMINI_API_KEY or GOOGLE_API_KEY in your environment (e.g. venv .env)"

    _status("Loading google-genai...")
    try:
        import google.genai as genai
        from google.genai.types import GenerateContentConfig
    except ImportError:
        return None, "Install google-genai: pip install google-genai"

    _status("Creating API client (20s timeout)...")
    try:
        from google.genai.types import HttpOptions
        http_opts = HttpOptions(timeout=20000)  # 20 seconds in milliseconds
    except ImportError:
        http_opts = None
    client = genai.Client(api_key=api_key, http_options=http_opts) if http_opts else genai.Client(api_key=api_key)

    full_prompt = f"{_build_system_prompt()}\n\nUser request:\n{prompt.strip()}"

    def _call_api(model_name: str = "gemini-2.0-flash"):
        try:
            config = GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
                http_options=http_opts,
            ) if http_opts else GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            )
        except TypeError:
            config = GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            )
        return client.models.generate_content(
            model=model_name,
            contents=full_prompt,
            config=config,
        )

    # Model: use GEMINI_MODEL from .env if set, else try available models (run check_models.py to list yours)
    env_model = os.environ.get("GEMINI_MODEL", "").strip()
    if env_model:
        models_to_try = [env_model]
    else:
        models_to_try = [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-flash-latest",
            "gemini-flash-lite-latest",
            "gemini-pro-latest",
            "gemini-3-flash-preview",
            "gemini-3-pro-preview",
            "gemma-3-1b-it",
        ]
    last_err = None
    for model_name in models_to_try:
        _status(f"Trying model: {model_name}...")
        for attempt in range(2):  # initial + 1 retry on 429
            try:
                _status(f"Calling API ({model_name}, attempt {attempt + 1})...")
                response = _call_api(model_name)
                text = getattr(response, "text", None) or (response.candidates[0].content.parts[0].text if response.candidates else "")
                text = (text or "").strip()
                if text.startswith("```"):
                    lines = text.split("\n")
                    text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else text
                _status("Parsing response...")
                data = json.loads(text)
                _status(f"Success with {model_name}")
                break
            except json.JSONDecodeError as e:
                return None, f"Invalid JSON from API: {e}"
            except Exception as e:
                last_err = e
                err_str = str(e)
                _status(f"Error: {err_str[:80]}...")
                if "404" in err_str or "NOT_FOUND" in err_str:
                    _status(f"Model {model_name} not found, trying next...")
                    break  # try next model
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                    match = re.search(r"retry[^\d]*(\d+(?:\.\d+)?)\s*s", err_str, re.I)
                    delay = int(float(match.group(1))) + 2 if match else 36
                    if attempt == 0:
                        _status(f"Quota exceeded. Waiting {delay}s before retry...")
                        time.sleep(delay)
                        continue
                    return None, (
                        f"API quota exceeded. Wait ~{delay}s and try again, or check billing: "
                        "https://ai.google.dev/gemini-api/docs/rate-limits"
                    )
                return None, err_str
        else:
            continue  # next model
        break  # success
    else:
        return None, str(last_err) if last_err else "Unknown error"

    _status("Building grafcet model...")
    steps_data = data.get("steps", [])
    if not isinstance(steps_data, list):
        return None, "Expected 'steps' array in response"

    model = GrafcetModel()
    for i, s in enumerate(steps_data):
        step_id = str(s.get("id", f"S{(i+1)*10}"))
        name = str(s.get("name", f"STEP_{step_id}"))
        value = int(s.get("value", (i + 1) * 10))
        transition = str(s.get("transition", ""))
        next_steps = s.get("next_steps", [])
        if isinstance(next_steps, str):
            next_steps = [x.strip() for x in next_steps.split(",") if x.strip()]
        next_steps = [str(x) for x in next_steps]
        actions = str(s.get("actions", ""))
        step = GrafcetStep(id=step_id, name=name, value=value, order=i, transition=transition, next_steps=next_steps, actions=actions)
        model.add_step(step)

    return model, None
