import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

api_key = os.environ.get("GEMINI_API_KEY", "").strip()
if not api_key or api_key == "paste-your-key-here":
    print("ERROR: GEMINI_API_KEY is missing in the .env file.")
    sys.exit(1)

# Skip models for images, audio, embeddings and other things we do not need.
SKIP_WORDS = (
    "image", "tts", "live", "audio", "embedding", "native",
    "computer", "robotics", "imagen", "veo", "learnlm", "aqa",
)
MAX_MODELS = 10

client = genai.Client(
    api_key=api_key,
    http_options=types.HttpOptions(timeout=30_000),
)

try:
    candidates = []
    for model in client.models.list():
        short_name = (model.name or "").replace("models/", "")
        actions = getattr(model, "supported_actions", None) or []
        if "generateContent" not in actions:
            continue
        if "flash" not in short_name.lower():
            continue
        if any(word in short_name.lower() for word in SKIP_WORDS):
            continue
        candidates.append(short_name)
except Exception as error:
    print("Could not list models:", type(error).__name__, str(error)[:300])
    sys.exit(1)

candidates = sorted(set(candidates), reverse=True)[:MAX_MODELS]
print(f"Testing {len(candidates)} model(s) with a tiny prompt...\n")

for name in candidates:
    started = time.time()
    try:
        client.models.generate_content(
            model=name,
            contents="Reply with the single word: ok",
        )
        print(f"{name}: OK in {time.time() - started:.1f}s")
    except errors.APIError as error:
        print(f"{name}: FAILED {error.code} {error.status} after {time.time() - started:.1f}s")
    except Exception as error:
        print(f"{name}: FAILED {type(error).__name__}")