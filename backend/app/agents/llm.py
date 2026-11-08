"""Thin Gemini wrapper. Returns None when no API key is set so the app still runs offline."""
from app.config import settings

_client = None


def generate(prompt: str, system: str | None = None) -> str | None:
    global _client
    if not settings.gemini_api_key:
        return None
    from google import genai
    from google.genai import types

    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    resp = _client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=system, temperature=0.2),
    )
    return (resp.text or "").strip() or None
