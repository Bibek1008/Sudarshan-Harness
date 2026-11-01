"""Day 1: a neutral conversation adapter for the Gemini REST API.

The provider isolates vendor-shaped JSON at the boundary: the harness keeps a
small, stable message format while this module owns wire conversion, retries,
and response parsing.  It uses only the Python standard library and preserves
model thought signatures exactly, so later tool turns remain valid.
"""

import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-3.1-pro-preview"

def api_key() -> str:
    """Return the configured API key, preferring the harness-specific name."""
    key = (os.environ.get("SUDARSHAN_API_KEY") or os.environ.get("ODYSSEUS_API_KEY")
           or os.environ.get("GEMINI_API_KEY"))
    if not key:
        raise RuntimeError(
            "Set SUDARSHAN_API_KEY (or legacy ODYSSEUS_API_KEY / GEMINI_API_KEY) before calling Gemini."
        )
    return key

def complete(
    model: str,
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> dict[str, Any]:
    """Complete a neutral conversation and return text, calls, and token usage."""
    body: dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": _to_wire(messages),
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 65536},
    }
    if tools:
        body["tools"] = [{"functionDeclarations": [tool["schema"] for tool in tools]}]

    if not isinstance(model, str) or not model or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for c in model):
        raise ValueError("Invalid Gemini model name")
    url = f"{API_ROOT}/{model}:generateContent"
    response = _post(url, body)
    if not isinstance(response, dict):
        raise RuntimeError("Gemini returned an invalid response object")
    candidates = response.get('candidates') or []
    candidate = candidates[0] if isinstance(candidates, list) and candidates else {}
    candidate = candidate if isinstance(candidate, dict) else {}
    content = candidate.get('content')
    parts = content.get('parts') if isinstance(content, dict) else []
    parts = parts if isinstance(parts, list) else []
    text: list[str] = []
    calls: list[dict[str, Any]] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        if isinstance(part.get("text"), str) and not part.get("thought"):
            text.append(part["text"])
        if (isinstance(part.get("functionCall"), dict)
                and isinstance(part["functionCall"].get("name"), str)
                and part["functionCall"]["name"].strip()
                and isinstance(part["functionCall"].get("args", {}), dict)):
            call = part["functionCall"]
            calls.append({"name": call["name"], "args": call.get("args", {}),
                          "signature": part.get("thoughtSignature")})

    if not ''.join(text).strip() and not calls:
        # Only known feedback enums are safe to surface; free-form feedback may echo input.
        feedback = response.get('promptFeedback')
        reason = feedback.get('blockReason') if isinstance(feedback, dict) else None
        safe_reason = reason if isinstance(reason, str) and reason in {'SAFETY', 'BLOCKLIST', 'PROHIBITED_CONTENT', 'OTHER'} else 'empty or unusable response'
        raise RuntimeError(f'Gemini returned no usable candidate: {safe_reason}')
    metadata = response.get("usageMetadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    return {"text": "".join(text), "tool_calls": calls,
            "usage": {"input": metadata.get("promptTokenCount", 0),
                      "output": metadata.get("candidatesTokenCount", 0)}}

def _to_wire(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate neutral harness messages into Gemini ``contents`` entries."""
    contents: list[dict[str, Any]] = []
    for message in messages:
        role = message["role"]
        if role == "user":
            contents.append({"role": "user", "parts": [{"text": message["text"]}]})
        elif role == "assistant":
            parts: list[dict[str, Any]] = []
            if message.get("text"):
                parts.append({"text": message["text"]})
            for call in message.get("tool_calls", []):
                # Gemini 3 requires each returned call's thought signature verbatim.
                parts.append({"functionCall": {"name": call["name"],
                              "args": call["args"]},
                              "thoughtSignature": call.get("signature")})
            contents.append({"role": "model", "parts": parts})
        elif role == "tool":
            contents.append({"role": "user", "parts": [{"functionResponse": {
                "name": message["name"], "response": {"result": message["text"]}
            }}]})
        else:
            raise ValueError(f"Unknown neutral message role: {role}")
    return contents

def _post(url: str, body: dict[str, Any], retries: int = 5) -> dict[str, Any]:
    """POST JSON, retrying transient API and network failures with backoff."""
    if retries < 1:
        raise ValueError("retries must be positive")
    data = json.dumps(body).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json", "x-goog-api-key": api_key()})
    for attempt in range(retries):
        try:
            with urlopen(request, timeout=600) as response:
                try:
                    result = json.loads(response.read().decode("utf-8"))
                except (ValueError, UnicodeError):
                    raise RuntimeError("Gemini returned malformed JSON") from None
                if not isinstance(result, dict):
                    raise RuntimeError("Gemini returned an invalid response object")
                return result
        except HTTPError as error:
            # Error bodies can echo credentials or request URLs. Never surface them.
            error.close()
            if error.code not in {429, 500, 502, 503}:
                raise RuntimeError(f"Gemini HTTP {error.code}") from None
            failure = f"HTTP {error.code}"
        except (URLError, TimeoutError) as error:
            failure = "network or timeout error"
        if attempt == retries - 1:
            raise RuntimeError(f"Gemini request failed after {retries} attempts: {failure}") from None
        time.sleep(2**attempt * 2)

    raise AssertionError("retry loop must either return or raise")
