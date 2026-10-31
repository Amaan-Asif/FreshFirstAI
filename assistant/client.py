import logging

from django.conf import settings
from google import genai
from google.genai import errors, types

logger = logging.getLogger(__name__)

# HTTP codes that mean "this model is busy or unavailable right now": try the next one.
TRY_NEXT_CODES = {400, 404, 429, 500, 503, 504}

# How long to wait for ONE model before giving up on it (milliseconds).
REQUEST_TIMEOUT_MS = 20_000


class AIServiceError(Exception):
    """Raised with a message that is safe to show to the user."""


def _get_client():
    if not settings.GEMINI_API_KEY or not settings.GEMINI_MODELS:
        raise AIServiceError(
            "The AI service is not configured yet. Please contact the site owner."
        )
    return genai.Client(
        api_key=settings.GEMINI_API_KEY,
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
    )


def generate_json(prompt, schema):
    """Ask Gemini for an answer and return it as a validated `schema` object.

    `schema` is a Pydantic model class that describes the JSON we expect.
    Each model in settings.GEMINI_MODELS is tried in order until one answers.
    """
    client = _get_client()
    last_code = None

    for model_name in settings.GEMINI_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0.7,
                    # Low thinking keeps answers fast.
                    thinking_config=types.ThinkingConfig(thinking_level="low"),
                ),
            )
        except errors.APIError as exc:
            last_code = exc.code
            logger.warning("Gemini model %s failed with %s: %s", model_name, exc.code, exc)
            if exc.code in TRY_NEXT_CODES:
                continue
            raise AIServiceError(
                "The AI service is not available right now because of a "
                "configuration problem. Please try again later."
            ) from exc
        except Exception as exc:
            last_code = None
            logger.warning("No answer from %s: %s", model_name, exc)
            continue

        text = response.text
        if not text:
            last_code = None
            logger.warning("Model %s returned an empty answer", model_name)
            continue

        try:
            return schema.model_validate_json(text)
        except ValueError as exc:
            last_code = None
            logger.warning("Model %s returned an unexpected format: %s", model_name, exc)
            continue

    # Every model failed.
    if last_code == 429:
        raise AIServiceError(
            "The AI service is busy or its free daily quota is used up. "
            "Please try again in a few minutes."
        )
    if last_code in (400, 404):
        raise AIServiceError(
            "The AI service is not available right now because of a "
            "configuration problem. Please try again later."
        )
    raise AIServiceError(
        "The AI service is busy right now. Please try again in a moment."
    )