"""OpenAI-compatible AI provider adapter used by the autonomous controller."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from core import METRICS, PROVIDER, GovernanceError, load_json, save_json


class AIProvider:
    def __init__(self) -> None:
        self.config = load_json(PROVIDER)
        self.metrics = load_json(METRICS)
        key_env = self.config.get("api_key_env", "AI_API_KEY")
        base_env = self.config.get("base_url_env", "AI_BASE_URL")
        self.api_key = os.environ.get(key_env)
        if not self.api_key:
            raise GovernanceError(f"missing AI API key: {key_env}")
        self.base_url = os.environ.get(
            base_env, self.config["default_base_url"]
        ).rstrip("/")

    def ask_json(
        self,
        role: str,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int = 3000,
    ) -> dict[str, Any]:
        model = self.config["models"][role]
        request_config = self.config.get("request", {})
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": request_config.get("temperature", 0.2),
            "max_completion_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        if "gpt-oss" in model:
            payload["reasoning_effort"] = request_config.get(
                "reasoning_effort", "medium"
            )

        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "My_Website-Autonomy/1.0",
            },
            method="POST",
        )

        retries = int(request_config.get("retry_429", 4))
        minimum_wait = int(request_config.get("minimum_retry_seconds", 10))
        timeout = int(request_config.get("timeout_seconds", 120))

        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    data = json.loads(response.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                result = json.loads(content)
                if not isinstance(result, dict):
                    raise GovernanceError("AI response must be a JSON object")
                self._record(role, model, data.get("usage", {}))
                return result
            except urllib.error.HTTPError as exc:
                if exc.code != 429 or attempt >= retries:
                    details = exc.read().decode("utf-8", errors="replace")
                    raise GovernanceError(
                        f"AI provider HTTP {exc.code}: {details[:1200]}"
                    ) from exc
                raw_retry = exc.headers.get("retry-after")
                wait = (
                    max(minimum_wait, int(float(raw_retry)))
                    if raw_retry
                    else minimum_wait * (attempt + 1)
                )
                time.sleep(wait)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
                if attempt >= retries:
                    raise GovernanceError(f"AI provider failure: {exc}") from exc
                time.sleep(minimum_wait * (attempt + 1))

        raise GovernanceError("AI provider exhausted retries")

    def _record(self, role: str, model: str, usage: dict[str, Any]) -> None:
        self.metrics["ai_calls"] = int(self.metrics.get("ai_calls", 0)) + 1
        by_role = self.metrics.setdefault("ai_calls_by_role", {})
        by_role[role] = int(by_role.get(role, 0)) + 1
        models = self.metrics.setdefault("models_used", {})
        models[model] = int(models.get(model, 0)) + 1
        self.metrics["reported_input_tokens"] = int(
            self.metrics.get("reported_input_tokens", 0)
        ) + int(usage.get("prompt_tokens", 0) or 0)
        self.metrics["reported_output_tokens"] = int(
            self.metrics.get("reported_output_tokens", 0)
        ) + int(usage.get("completion_tokens", 0) or 0)
        save_json(METRICS, self.metrics)
