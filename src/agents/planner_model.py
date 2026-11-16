"""Gemini adapter for JSON Planner turns; no key is needed for unit tests."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from google import genai
from google.genai import types


class PlannerModel(Protocol):
    def generate(self, system_prompt: str, context: str) -> str: ...


def _read_api_key(env_path: str | Path = ".env") -> str | None:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if key:
        return key
    path = Path(env_path)
    if not path.exists():
        return None
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if line.startswith("export "):
            line = line[7:].lstrip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() in {"GEMINI_API_KEY", "GOOGLE_API_KEY"}:
            return value.strip().strip('"\'') or None
    return None


def _gemini_client(api_key: str, env_path: str | Path):
    path = Path(env_path)
    if path.exists():
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if line.startswith("export "):
                line = line[7:].lstrip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            name = name.strip()
            if name in {"LANGSMITH_TRACING", "LANGSMITH_API_KEY", "LANGSMITH_ENDPOINT",
                        "LANGSMITH_AGENT_ID", "LANGSMITH_AGENT_ENVIRONMENT",
                        "LANGSMITH_PROJECT", "LANGSMITH_WORKSPACE_ID"}:
                value = value.strip().strip('"\'')
                if value:
                    os.environ.setdefault(name, value)

    client = genai.Client(api_key=api_key)
    if os.environ.get("LANGSMITH_TRACING", "").lower() == "true":
        from langsmith.wrappers import wrap_gemini
        return wrap_gemini(client)
    return client


class GeminiPlannerModel:
    def __init__(self, api_key: str | None = None, env_path: str | Path = ".env",
                 client=None):
        key = api_key or _read_api_key(env_path)
        if client is None and not key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY is required")
        self.client = client if client is not None else _gemini_client(key, env_path)
        self.last_usage: dict[str, int] = {}

    def generate(self, system_prompt: str, context: str) -> str:
        response = self.client.models.generate_content(
            model="gemini-3.8-flash",
            contents=context,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(thinking_level="MEDIUM"),
            ),
        )
        usage = getattr(response, "usage_metadata", None)
        self.last_usage = ({key: int(value) for key, value in {
            "input_tokens": getattr(usage, "prompt_token_count", None),
            "output_tokens": getattr(usage, "candidates_token_count", None),
            "thinking_tokens": getattr(usage, "thoughts_token_count", None),
            "total_tokens": getattr(usage, "total_token_count", None),
        }.items() if value is not None} if usage is not None else {})
        if not response.text:
            raise ValueError("Gemini returned no Planner JSON")
        return response.text
