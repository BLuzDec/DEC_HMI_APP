"""
Check available Gemini models and max output tokens for your API key.
Run from project root: py block_station_generator/check_models.py
"""
import os
import sys

# Load .env from block_station_generator/
_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_root)))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_root, ".env"))
except ImportError:
    pass

api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if not api_key:
    print("ERROR: Set GEMINI_API_KEY or GOOGLE_API_KEY in block_station_generator/.env")
    sys.exit(1)

try:
    from google import genai
except ImportError:
    print("ERROR: pip install google-genai")
    sys.exit(1)

client = genai.Client(api_key=api_key)

def _get_attrs(obj, *names):
    for n in names:
        v = getattr(obj, n, None)
        if v is not None:
            return v
    return None

print("=" * 60)
print("1. List available models (client.models.list)...")
print("=" * 60)

try:
    models = list(client.models.list())
    print(f"Found {len(models)} model(s)\n")
    for model in models:
        name = _get_attrs(model, "name", "display_name") or str(model)
        short = name.replace("models/", "") if "models/" in str(name) else name
        supported = _get_attrs(model, "supported_generation_methods", "supportedGenerationMethods") or []
        supported_str = [str(s).lower() for s in supported]
        if supported and "generatecontent" not in "".join(supported_str):
            continue
        out_tok = _get_attrs(model, "output_token_limit", "outputTokenLimit")
        in_tok = _get_attrs(model, "input_token_limit", "inputTokenLimit")
        print(f"  {short}")
        if out_tok is not None:
            print(f"    max output tokens: {out_tok}")
        if in_tok is not None:
            print(f"    max input tokens:  {in_tok}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 60)
print("2. get_model for specific models (max output tokens)...")
print("=" * 60)

for model_name in ["gemini-2.0-flash", "gemini-1.5-flash-8b", "gemini-pro", "gemini-1.5-flash", "gemini-1.5-pro"]:
    try:
        info = client.models.get(model=model_name)
        out_tok = _get_attrs(info, "output_token_limit", "outputTokenLimit")
        in_tok = _get_attrs(info, "input_token_limit", "inputTokenLimit")
        print(f"\n  {model_name}:")
        print(f"    max output tokens: {out_tok or 'N/A'}")
        print(f"    max input tokens:  {in_tok or 'N/A'}")
    except Exception as e:
        print(f"\n  {model_name}: ERROR - {e}")

print("\nDone.")
