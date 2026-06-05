from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class AIConfig:
    provider: str
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int = 120
    max_retries: int = 3
    temperature: float = 0.1


class AIClientError(RuntimeError):
    pass


def run_ai_cli(main: Callable[[], int]) -> int:
    try:
        return main()
    except AIClientError as exc:
        print(f"AI error: {exc}", file=sys.stderr)
        return 2


PLACEHOLDER_VALUES = {
    "https://api.example.com/v1",
    "PUT_YOUR_API_KEY_HERE",
    "PUT_MODEL_NAME_HERE",
}


def _is_placeholder(value: str) -> bool:
    return value.strip() in PLACEHOLDER_VALUES


def load_ai_config(root: Path, config_path: Path | None = None) -> AIConfig:
    path = config_path or root / "config" / "ai.local.json"
    data: dict[str, Any] = {}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))

    base_url = os.environ.get("DOCDECOMP_AI_BASE_URL") or data.get("base_url") or ""
    api_key = os.environ.get("DOCDECOMP_AI_API_KEY") or data.get("api_key") or ""
    model = os.environ.get("DOCDECOMP_AI_MODEL") or data.get("model") or ""

    if not base_url:
        raise AIClientError(f"Missing base_url. Create {path} or set DOCDECOMP_AI_BASE_URL.")
    if not api_key:
        raise AIClientError(f"Missing api_key. Create {path} or set DOCDECOMP_AI_API_KEY.")
    if not model:
        raise AIClientError(f"Missing model. Create {path} or set DOCDECOMP_AI_MODEL.")
    if _is_placeholder(base_url):
        raise AIClientError(f"base_url is still a placeholder. Update {path} or set DOCDECOMP_AI_BASE_URL.")
    if _is_placeholder(api_key):
        raise AIClientError(f"api_key is still a placeholder. Update {path} or set DOCDECOMP_AI_API_KEY.")
    if _is_placeholder(model):
        raise AIClientError(f"model is still a placeholder. Update {path} or set DOCDECOMP_AI_MODEL.")

    return AIConfig(
        provider=data.get("provider", "openai_compatible"),
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        model=model,
        timeout_seconds=int(data.get("timeout_seconds", 120)),
        max_retries=int(data.get("max_retries", 3)),
        temperature=float(data.get("temperature", 0.1)),
    )


class OpenAICompatibleClient:
    def __init__(self, config: AIConfig):
        self.config = config

    def chat_json(self, messages: list[dict[str, str]], response_schema_hint: str) -> dict[str, Any]:
        content = self.chat_text(messages + [{"role": "system", "content": response_schema_hint}])
        return parse_json_response(content)

    def chat_text(self, messages: list[dict[str, str]]) -> str:
        url = f"{self.config.base_url}/chat/completions"
        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            request = urllib.request.Request(url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                    data = json.loads(response.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
                last_error = exc
                if isinstance(exc, urllib.error.HTTPError) and exc.code not in {408, 409, 429, 500, 502, 503, 504}:
                    detail = exc.read().decode("utf-8", errors="replace")
                    raise AIClientError(f"AI request failed with HTTP {exc.code}: {detail}") from exc
                if attempt < self.config.max_retries:
                    time.sleep(min(2 ** attempt, 10))
        raise AIClientError(f"AI request failed after {self.config.max_retries} attempts: {last_error}") from last_error


def parse_json_response(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIClientError(f"AI response was not valid JSON: {exc}\n{text[:1000]}") from exc
    if not isinstance(value, dict):
        raise AIClientError("AI response JSON must be an object.")
    return value
