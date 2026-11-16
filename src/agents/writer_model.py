"""Gemini JSON adapter for section-scoped Writer requests."""
from __future__ import annotations

import json
from pathlib import Path

from google.genai import types

from src.agents.planner_model import _gemini_client, _read_api_key
from src.agents.writer_contract import WriterRequest, WriterResponse


class GeminiWriterModel:
    def __init__(self, api_key: str | None = None, env_path: str | Path = ".env",
                 client=None):
        key = api_key or _read_api_key(env_path)
        if client is None and not key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY is required")
        self.client = client if client is not None else _gemini_client(key, env_path)

    def generate(self, request: WriterRequest) -> WriterResponse:
        response = self.client.models.generate_content(
            model="gemini-3.8-flash",
            contents=json.dumps({"section_view": json.loads(request.section_view),
                                 "validation_feedback": request.feedback},
                                ensure_ascii=False),
            config=types.GenerateContentConfig(
                system_instruction=request.system,
                response_mime_type="application/json",
                response_json_schema=request.response_schema,
                temperature=0,
                thinking_config=types.ThinkingConfig(thinking_level="LOW"),
            ),
        )
        if not response.text:
            raise ValueError("Gemini returned no Writer JSON")
        usage = getattr(response, "usage_metadata", None)
        token_usage = ({key: int(value) for key, value in {
            "input_tokens": getattr(usage, "prompt_token_count", None),
            "output_tokens": getattr(usage, "candidates_token_count", None),
            "thinking_tokens": getattr(usage, "thoughts_token_count", None),
            "total_tokens": getattr(usage, "total_token_count", None),
        }.items() if value is not None} if usage is not None else {})
        return WriterResponse(text=response.text, token_usage=token_usage)
