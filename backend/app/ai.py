"""AI provider layer. Swap providers here without touching the rest of the app.

Supported: Google Gemini (GEMINI_API_KEY) and any OpenAI-compatible chat endpoint (AI_API_KEY/AI_BASE_URL/AI_MODEL).
With no key configured, get_provider() returns None and the app uses the clearly labelled demo verifier.
"""
from __future__ import annotations

import json
import re

import httpx


class AIError(Exception):
    """The AI provider failed or returned something unusable."""


def _extract_json(text: str):
    text = (text or "").strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except ValueError:
                pass
    raise AIError("The model did not return valid JSON.")


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout: float, http: httpx.Client | None = None):
        self.api_key, self.model = api_key, model
        self._http = http or httpx.Client(timeout=timeout)

    def complete_json(self, system: str, user: str) -> dict:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        }
        try:
            resp = self._http.post(url, json=body, headers={"x-goog-api-key": self.api_key})
        except httpx.HTTPError as exc:
            raise AIError(f"Could not reach Gemini ({exc.__class__.__name__}).") from exc
        if resp.status_code != 200:
            detail = ""
            try:
                detail = str(resp.json().get("error", {}).get("message", ""))[:160]
            except (ValueError, AttributeError):
                pass
            raise AIError(f"Gemini returned HTTP {resp.status_code}" + (f" ({detail})." if detail else "."))
        try:
            parts = resp.json()["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise AIError("Gemini returned an unexpected response.") from exc
        return _extract_json(text)


class OpenAICompatProvider:
    name = "openai-compatible"

    def __init__(self, api_key: str, base_url: str, model: str, timeout: float, http: httpx.Client | None = None):
        self.api_key, self.base_url, self.model = api_key, base_url.rstrip("/"), model
        self._http = http or httpx.Client(timeout=timeout)

    def complete_json(self, system: str, user: str) -> dict:
        body = {
            "model": self.model, "temperature": 0.1,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
        }
        try:
            resp = self._http.post(f"{self.base_url}/chat/completions", json=body,
                                   headers={"Authorization": f"Bearer {self.api_key}"})
        except httpx.HTTPError as exc:
            raise AIError(f"Could not reach the AI provider ({exc.__class__.__name__}).") from exc
        if resp.status_code != 200:
            raise AIError(f"The AI provider returned HTTP {resp.status_code}.")
        try:
            text = resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise AIError("The AI provider returned an unexpected response.") from exc
        return _extract_json(text)


def get_provider(settings, http: httpx.Client | None = None):
    if settings.gemini_api_key:
        return GeminiProvider(settings.gemini_api_key, settings.gemini_model, settings.ai_timeout_seconds, http)
    if settings.ai_api_key and settings.ai_base_url and settings.ai_model:
        return OpenAICompatProvider(settings.ai_api_key, settings.ai_base_url, settings.ai_model,
                                    settings.ai_timeout_seconds, http)
    return None
