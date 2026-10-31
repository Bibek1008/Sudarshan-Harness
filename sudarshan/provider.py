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
from urllib.parse import quote
from urllib.request import Request, urlopen

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-3.1-pro-preview"

def api_key() -> str:
    """Return the configured API key, preferring the harness-specific name."""
    key = os.environ.get("ODYSSEUS_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(
            "Set ODYSSEUS_API_KEY or GEMINI_API_KEY before calling a provider."
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

    url = f"{API_ROOT}/{model}:generateContent?key={quote(api_key(), safe='')}"
    response = _post(url, body)
    parts = response.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text: list[str] = []
    calls: list[dict[str, Any]] = []
    for part in parts:
        if "text" in part and not part.get("thought"):
            text.append(part["text"])
        if "functionCall" in part:
            call = part["functionCall"]
            calls.append({"name": call["name"], "args": call.get("args", {}),
                          "signature": part.get("thoughtSignature")})

    metadata = response.get("usageMetadata", {})
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
    data = json.dumps(body).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json"})
    for attempt in range(retries):
        try:
            with urlopen(request, timeout=600) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:400]
            if error.code not in {429, 500, 502, 503}:
                raise RuntimeError(f"HTTP {error.code}: {detail}") from error
            failure: Exception = RuntimeError(f"HTTP {error.code}: {detail}")
        except (URLError, TimeoutError) as error:
            failure = error
        if attempt == retries - 1:
            raise RuntimeError(f"Request failed after {retries} attempts: {failure}") from failure
        time.sleep(2**attempt * 2)

    raise AssertionError("retry loop must either return or raise")
