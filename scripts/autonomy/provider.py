"""OpenAI-compatible AI provider adapter used by the autonomous controller."""
from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.request
from typing import Any

from core import METRICS, PROVIDER, GovernanceError, load_json, save_json

_EXECUTOR_CONTEXT_MARKERS = ("\nREPOSITORY CONTEXT:\n", "\nEXTENDED CONTEXT:\n")


def _compact_text(text: str, limit: int, *, label: str) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    if limit <= 0:
        return "", bool(text)
    marker = f"\n...[{label}: omitted by capacity guard]...\n"
    if limit <= len(marker) + 32:
        return text[:limit], True
    available = limit - len(marker)
    head = (available * 3) // 5
    tail = available - head
    return text[:head] + marker + text[-tail:], True


def _fit_executor_user(user_prompt: str, limit: int, minimum_context: int) -> tuple[str, bool]:
    """Preserve Frozen Plan + SMART Objective and compact repository context only."""
    for marker in _EXECUTOR_CONTEXT_MARKERS:
        if marker not in user_prompt:
            continue
        protected, repository_context = user_prompt.split(marker, 1)
        protected = protected + marker
        remaining = limit - len(protected)
        if remaining < minimum_context:
            raise GovernanceError(
                "provider capacity cannot preserve the complete Frozen Plan and SMART Objective "
                f"while retaining the required repository-context floor ({remaining} < {minimum_context})"
            )
        fitted_context, compacted = _compact_text(
            repository_context,
            remaining,
            label="executor repository context",
        )
        return protected + fitted_context, compacted
    raise GovernanceError(
        "executor prompt lacks an explicit repository-context marker; refusing unsafe generic compaction"
    )


def fit_prompt_to_capacity(
    config: dict[str, Any],
    role: str,
    system_prompt: str,
    user_prompt: str,
    requested_max_tokens: int,
) -> tuple[str, str, int, dict[str, Any]]:
    capacity = config.get("capacity", {})
    role_caps = capacity.get("role_completion_caps", {})
    if role not in role_caps:
        raise GovernanceError(f"missing provider completion cap for role: {role}")

    organization_tpm = int(capacity.get("organization_tpm_limit", 0))
    admitted = int(capacity.get("max_admitted_request_tokens", 0))
    margin = int(capacity.get("safety_margin_tokens", 0))
    chars_per_token = float(capacity.get("conservative_chars_per_token", 0))
    overhead = int(capacity.get("message_overhead_tokens", 0))
    minimum_context = int(capacity.get("minimum_context_characters", 800))
    if organization_tpm <= 0 or admitted <= 0 or chars_per_token <= 0:
        raise GovernanceError("invalid provider capacity configuration")
    if admitted + margin > organization_tpm:
        raise GovernanceError("provider admission envelope exceeds configured TPM limit")

    completion = max(1, min(int(requested_max_tokens), int(role_caps[role])))
    input_budget = admitted - completion - overhead
    if input_budget <= 0:
        raise GovernanceError(f"no input-token budget remains for role {role}")
    character_budget = max(1, int(math.floor(input_budget * chars_per_token)))

    # System prompts are small governance contracts and should remain intact whenever
    # possible. If one alone is oversized, retain deterministic head/tail evidence.
    system_limit = min(len(system_prompt), max(600, character_budget // 4))
    fitted_system, system_compacted = _compact_text(
        system_prompt, system_limit, label="system prompt"
    )
    user_limit = character_budget - len(fitted_system)
    if user_limit <= 0:
        raise GovernanceError(f"capacity envelope leaves no user-prompt space for role {role}")

    if role == "executor" and len(user_prompt) > user_limit:
        fitted_user, user_compacted = _fit_executor_user(
            user_prompt, user_limit, minimum_context
        )
    else:
        fitted_user, user_compacted = _compact_text(
            user_prompt, user_limit, label=f"{role} user prompt"
        )

    estimated_input = int(
        math.ceil((len(fitted_system) + len(fitted_user)) / chars_per_token)
    ) + overhead
    estimated_total = estimated_input + completion
    if estimated_total > admitted:
        overshoot_chars = int(math.ceil((estimated_total - admitted) * chars_per_token)) + 8
        revised_user_limit = max(1, len(fitted_user) - overshoot_chars)
        if role == "executor":
            fitted_user, forced = _fit_executor_user(
                user_prompt, revised_user_limit, minimum_context
            )
        else:
            fitted_user, forced = _compact_text(
                fitted_user, revised_user_limit, label=f"{role} forced compaction"
            )
        user_compacted = user_compacted or forced
        estimated_input = int(
            math.ceil((len(fitted_system) + len(fitted_user)) / chars_per_token)
        ) + overhead
        estimated_total = estimated_input + completion
    if estimated_total > admitted:
        raise GovernanceError(
            f"provider request cannot fit admission envelope: estimated={estimated_total}, admitted={admitted}"
        )

    diagnostics = {
        "role": role,
        "organization_tpm_limit": organization_tpm,
        "max_admitted_request_tokens": admitted,
        "safety_margin_tokens": margin,
        "requested_completion_tokens": int(requested_max_tokens),
        "admitted_completion_tokens": completion,
        "original_system_characters": len(system_prompt),
        "original_user_characters": len(user_prompt),
        "admitted_system_characters": len(fitted_system),
        "admitted_user_characters": len(fitted_user),
        "estimated_admitted_tokens": estimated_total,
        "compacted": bool(system_compacted or user_compacted),
        "executor_frozen_prefix_preserved": role != "executor" or not user_compacted or any(
            marker in fitted_user for marker in _EXECUTOR_CONTEXT_MARKERS
        ),
    }
    return fitted_system, fitted_user, completion, diagnostics


class AIProvider:
    def __init__(self, metrics: dict[str, Any]) -> None:
        self.config = load_json(PROVIDER)
        self.metrics = metrics
        key_env = self.config.get("api_key_env", "AI_API_KEY")
        base_env = self.config.get("base_url_env", "AI_BASE_URL")
        self.api_key = os.environ.get(key_env)
        if not self.api_key:
            raise GovernanceError(f"missing AI API key: {key_env}")
        base_override = os.environ.get(base_env)
        self.base_url = (base_override or self.config["default_base_url"]).rstrip("/")

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
        fitted_system, fitted_user, completion_tokens, admission = fit_prompt_to_capacity(
            self.config, role, system_prompt, user_prompt, max_tokens
        )
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": fitted_system},
                {"role": "user", "content": fitted_user},
            ],
            "temperature": request_config.get("temperature", 0.2),
            "max_completion_tokens": completion_tokens,
            "response_format": {"type": "json_object"},
        }

        if "qwen/qwen3.6" in model:
            payload["reasoning_format"] = "hidden"
            payload["reasoning_effort"] = "none"
        elif "gpt-oss" in model:
            payload["reasoning_effort"] = request_config.get(
                "reasoning_effort", "low"
            )

        retries = int(request_config.get("retry_429", 4))
        minimum_wait = int(request_config.get("minimum_retry_seconds", 10))
        timeout = int(request_config.get("timeout_seconds", 180))

        for attempt in range(retries + 1):
            request = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "My_Website-Autonomy/2.0",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    data = json.loads(response.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                result = json.loads(content)
                if not isinstance(result, dict):
                    raise GovernanceError("AI response must be a JSON object")
                self._record(role, model, data.get("usage", {}), admission)
                return result
            except urllib.error.HTTPError as exc:
                details = exc.read().decode("utf-8", errors="replace")
                retryable_json = exc.code == 400 and "json_validate_failed" in details
                retryable_rate = exc.code == 429
                if not (retryable_json or retryable_rate) or attempt >= retries:
                    raise GovernanceError(
                        f"AI provider HTTP {exc.code}: {details[:1200]}"
                    ) from exc
                if retryable_json:
                    time.sleep(minimum_wait)
                    continue
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

    def _record(
        self,
        role: str,
        model: str,
        usage: dict[str, Any],
        admission: dict[str, Any],
    ) -> None:
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
        if admission.get("compacted"):
            self.metrics["request_compactions"] = int(
                self.metrics.get("request_compactions", 0)
            ) + 1
        self.metrics["max_estimated_admitted_tokens"] = max(
            int(self.metrics.get("max_estimated_admitted_tokens", 0)),
            int(admission.get("estimated_admitted_tokens", 0)),
        )
        self.metrics["last_admission"] = {
            "role": role,
            "model": model,
            "estimated_admitted_tokens": admission.get("estimated_admitted_tokens"),
            "admitted_completion_tokens": admission.get("admitted_completion_tokens"),
            "compacted": admission.get("compacted"),
            "executor_frozen_prefix_preserved": admission.get("executor_frozen_prefix_preserved"),
        }
        save_json(METRICS, self.metrics)
