from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tokut.parser import parse_grok_line, parse_session_id, parse_token_count_line


def test_parse_session_id_from_codex_rollout_path() -> None:
    path = Path(
        "/Users/example/.codex/sessions/2026/06/11/"
        "rollout-2026-06-11T09-40-42-019eb720-d2aa-7930-8fd2-fe02116f0798.jsonl"
    )

    assert parse_session_id(path) == "019eb720-d2aa-7930-8fd2-fe02116f0798"


def test_parse_token_count_line_extracts_usage_and_limits() -> None:
    line = json.dumps(
        {
            "timestamp": "2026-06-11T14:42:42.322Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": 226325,
                        "cached_input_tokens": 150016,
                        "output_tokens": 2511,
                        "reasoning_output_tokens": 838,
                        "total_tokens": 228836,
                    },
                    "last_token_usage": {
                        "input_tokens": 78893,
                        "cached_input_tokens": 63872,
                        "output_tokens": 650,
                        "reasoning_output_tokens": 254,
                        "total_tokens": 79543,
                    },
                    "model_context_window": 258400,
                },
                "rate_limits": {
                    "primary": {
                        "used_percent": 37.0,
                        "window_minutes": 300,
                        "resets_at": 1781192510,
                    },
                    "secondary": {
                        "used_percent": 21.0,
                        "window_minutes": 10080,
                        "resets_at": 1781742546,
                    },
                    "plan_type": "pro",
                },
            },
        }
    )

    snapshot = parse_token_count_line(line, Path("rollout-2026-06-11T09-40-42-019eb720-d2aa-7930-8fd2-fe02116f0798.jsonl"))

    assert snapshot is not None
    assert snapshot.provider == "codex"
    assert snapshot.account == "default"
    assert snapshot.session_id == "019eb720-d2aa-7930-8fd2-fe02116f0798"
    assert snapshot.timestamp.isoformat() == "2026-06-11T14:42:42.322000+00:00"
    assert snapshot.total.total_tokens == 228836
    assert snapshot.last.total_tokens == 79543
    assert snapshot.last.uncached_input_tokens == 15021
    assert snapshot.model_context_window == 258400
    assert snapshot.rate_limits["primary"]["used_percent"] == 37.0


def test_parse_non_token_count_line_returns_none() -> None:
    line = json.dumps({"timestamp": "2026-06-11T14:42:42.322Z", "type": "response_item"})

    assert parse_token_count_line(line, Path("sample.jsonl")) is None


def test_parse_grok_line_prefers_cost_ticks() -> None:
    line = json.dumps(
        {
            "timestamp": 1784912869,
            "method": "_x.ai/session/update",
            "params": {
                "sessionId": "019f9518-f6de-7a43-9049-20d83586b8b2",
                "update": {
                    "sessionUpdate": "turn_completed",
                    "prompt_id": "019f9511-a679-71f3-b478-7363d24a13b1",
                    "usage": {
                        "inputTokens": 27943,
                        "outputTokens": 564,
                        "totalTokens": 28507,
                        "cachedReadTokens": 13312,
                        "reasoningTokens": 398,
                        "modelCalls": 2,
                        "costUsdTicks": 366396000,
                        "modelUsage": {
                            "grok-4.5-build": {
                                "inputTokens": 27943,
                                "outputTokens": 564,
                                "costUsdTicks": 366396000,
                                "modelCalls": 2,
                            }
                        },
                    },
                },
            },
        }
    )
    path = Path(
        "/Users/example/.grok/sessions/%2FUsers%2Fexample%2Frepos%2Fapp/"
        "019f9518-f6de-7a43-9049-20d83586b8b2/updates.jsonl"
    )

    snapshot = parse_grok_line(line, path)

    assert snapshot is not None
    assert snapshot.provider == "grok"
    assert snapshot.session_id == "019f9518-f6de-7a43-9049-20d83586b8b2"
    assert snapshot.model == "grok-4.5-build"
    assert snapshot.last.input_tokens == 27943
    assert snapshot.last.cached_input_tokens == 13312
    assert snapshot.last.output_tokens == 564
    assert snapshot.server_cost_usd == 0.0366396
    assert snapshot.cost_source == "server_cost_ticks"
    assert snapshot.total_is_cumulative is False
