from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tokut.parser import parse_claude_line, parse_gemini_line


def test_parse_claude_usage_line() -> None:
    line = json.dumps(
        {
            "timestamp": "2026-06-11T14:06:22.416Z",
            "sessionId": "618f8590-385b-4aaa-8c41-20301edcc493",
            "cwd": "/Users/example/repo",
            "message": {
                "model": "claude-fable-5",
                "usage": {
                    "input_tokens": 6808,
                    "cache_creation_input_tokens": 30427,
                    "cache_read_input_tokens": 17456,
                    "output_tokens": 363,
                },
            },
        }
    )

    snapshot = parse_claude_line(line, Path("/tmp/618f8590-385b-4aaa-8c41-20301edcc493.jsonl"), account="work")

    assert snapshot is not None
    assert snapshot.provider == "claude"
    assert snapshot.account == "work"
    assert snapshot.model == "claude-fable-5"
    assert snapshot.session_id == "618f8590-385b-4aaa-8c41-20301edcc493"
    assert snapshot.last.input_tokens == 54691
    assert snapshot.last.cached_input_tokens == 17456
    assert snapshot.last.output_tokens == 363
    assert snapshot.last.total_tokens == 55054
    assert snapshot.total_is_cumulative is False


def test_parse_gemini_usage_line() -> None:
    line = json.dumps(
        {
            "id": "a9df6549-c954-4b19-963e-dc63f2bfad9c",
            "timestamp": "2026-05-06T17:43:52.205Z",
            "type": "gemini",
            "tokens": {
                "input": 11731,
                "output": 203,
                "cached": 7807,
                "thoughts": 452,
                "tool": 12,
                "total": 12410,
            },
            "model": "gemini-3-flash-preview",
        }
    )

    snapshot = parse_gemini_line(line, Path("/tmp/project/chats/session.jsonl"), account="personal")

    assert snapshot is not None
    assert snapshot.provider == "gemini"
    assert snapshot.account == "personal"
    assert snapshot.model == "gemini-3-flash-preview"
    assert snapshot.last.input_tokens == 11731
    assert snapshot.last.cached_input_tokens == 7807
    assert snapshot.last.output_tokens == 203
    assert snapshot.last.reasoning_output_tokens == 452
    assert snapshot.last.tool_tokens == 12
    assert snapshot.last.total_tokens == 12410
    assert snapshot.total_is_cumulative is False
