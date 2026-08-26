#!/usr/bin/env python3
"""Preflight the configured AI provider without changing experiment metrics."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

from core import PROVIDER, load_json


def main() -> int:
    cfg = load_json(PROVIDER)
    key = os.environ.get(cfg.get("api_key_env", "AI_API_KEY"))
    if not key:
        print("AI provider probe: missing API key", file=sys.stderr)
        return 2
    base_env = cfg.get("base_url_env", "AI_BASE_URL")
    base = (os.environ.get(base_env) or cfg["default_base_url"]).rstrip("/")
    model = cfg["models"]["collector"]
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "Return JSON only: {\"status\":\"ok\"}",
            }
        ],
        "temperature": 0,
        "max_completion_tokens": 80,
        "response_format": {"type": "json_object"},
    }
    if "qwen/qwen3.6" in model:
        payload["reasoning_format"] = "hidden"
        payload["reasoning_effort"] = "none"
    elif "gpt-oss" in model:
        payload["reasoning_effort"] = "low"

    request = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "My_Website-Bootstrap-Probe/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        result = json.loads(content)
        if result.get("status") != "ok":
            print(f"AI provider probe: unexpected response {result!r}", file=sys.stderr)
            return 3
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        print(
            f"AI provider probe failed: HTTP {exc.code}: {details[:1200]}",
            file=sys.stderr,
        )
        return 4
    except (urllib.error.URLError, KeyError, json.JSONDecodeError) as exc:
        print(f"AI provider probe failed: {exc}", file=sys.stderr)
        return 4
    print(f"AI provider probe: PASS ({model})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
