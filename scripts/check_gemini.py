import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

api_key = os.environ.get("GEMINI_API_KEY", "").strip()
model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()

if not api_key or api_key == "paste-your-key-here":
    print("ERROR: GEMINI_API_KEY is missing. Open the .env file and paste your key.")
    sys.exit(1)

print(f"Using model: {model}")

try:
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents="In one short sentence, give a tip for reducing food waste at home.",
    )
    print("SUCCESS. Gemini replied:")
    print(response.text)
except Exception as error:
    print("The call failed.")
    print(type(error).__name__ + ":", str(error)[:500])
    sys.exit(1)