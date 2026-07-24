from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_UUID_RE = re.compile(
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    tool_tokens: int = 0
    total_tokens: int = 0

    @property
    def uncached_input_tokens(self) -> int:
        return max(self.input_tokens - self.cached_input_tokens, 0)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TokenUsage":
        data = data or {}
        return cls(
            input_tokens=_int(data.get("input_tokens")),
            cached_input_tokens=_int(data.get("cached_input_tokens")),
            output_tokens=_int(data.get("output_tokens")),
            reasoning_output_tokens=_int(data.get("reasoning_output_tokens")),
            tool_tokens=_int(data.get("tool_tokens")),
            total_tokens=_int(data.get("total_tokens")),
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "uncached_input_tokens": self.uncached_input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_output_tokens": self.reasoning_output_tokens,
            "tool_tokens": self.tool_tokens,
            "total_tokens": self.total_tokens,
        }


# Server-stamped cost ticks: 1 USD = 10^10 ticks (Grok / xAI usage export).
COST_USD_TICKS_PER_DOLLAR = 10_000_000_000


@dataclass(frozen=True)
class TokenSnapshot:
    timestamp: datetime
    session_id: str
    file_path: str
    total: TokenUsage
    last: TokenUsage
    model_context_window: int | None
    rate_limits: dict[str, Any]
    provider: str = "codex"
    account: str = "default"
    project: str = ""
    user: str = ""
    model: str = ""
    total_is_cumulative: bool = True
    # When set, meter uses this USD amount instead of token × list price.
    server_cost_usd: float | None = None
    cost_source: str = ""

    def to_dict(self, *, thread_name: str = "") -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "provider": self.provider,
            "account": self.account,
            "project": self.project,
            "user": self.user,
            "session_id": self.session_id,
            "thread_name": thread_name,
            "model": self.model,
            "file_path": self.file_path,
            "total": self.total.to_dict(),
            "last": self.last.to_dict(),
            "model_context_window": self.model_context_window,
            "rate_limits": self.rate_limits,
            "total_is_cumulative": self.total_is_cumulative,
            "server_cost_usd": self.server_cost_usd,
            "cost_source": self.cost_source,
        }


def parse_session_id(path: Path) -> str:
    match = _UUID_RE.search(path.name)
    return match.group(1) if match else path.stem


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def parse_token_count_line(line: str, path: Path) -> TokenSnapshot | None:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None

    if event.get("type") != "event_msg":
        return None
    payload = event.get("payload") or {}
    if payload.get("type") != "token_count":
        return None

    timestamp = parse_timestamp(event.get("timestamp"))
    if timestamp is None:
        return None

    info = payload.get("info") or {}
    return TokenSnapshot(
        timestamp=timestamp,
        session_id=parse_session_id(path),
        file_path=str(path),
        total=TokenUsage.from_dict(info.get("total_token_usage")),
        last=TokenUsage.from_dict(info.get("last_token_usage")),
        model_context_window=info.get("model_context_window"),
        rate_limits=payload.get("rate_limits") or {},
        provider="codex",
        account="default",
        model=info.get("model") or "",
        total_is_cumulative=True,
    )


def parse_claude_line(line: str, path: Path, *, account: str = "default") -> TokenSnapshot | None:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None

    message = event.get("message") if isinstance(event, dict) else None
    usage = event.get("usage") if isinstance(event, dict) else None
    if isinstance(message, dict) and not usage:
        usage = message.get("usage")
    if not isinstance(usage, dict):
        return None

    timestamp = parse_timestamp(event.get("timestamp"))
    if timestamp is None:
        return None

    cache_creation = _int(usage.get("cache_creation_input_tokens"))
    cache_read = _int(usage.get("cache_read_input_tokens"))
    direct_input = _int(usage.get("input_tokens"))
    input_tokens = direct_input + cache_creation + cache_read
    output_tokens = _int(usage.get("output_tokens"))
    total_tokens = input_tokens + output_tokens
    usage_obj = TokenUsage(
        input_tokens=input_tokens,
        cached_input_tokens=cache_read,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )
    return TokenSnapshot(
        timestamp=timestamp,
        session_id=str(event.get("sessionId") or parse_session_id(path)),
        file_path=str(path),
        total=usage_obj,
        last=usage_obj,
        model_context_window=None,
        rate_limits={},
        provider="claude",
        account=account,
        model=str(event.get("model") or (message or {}).get("model") or ""),
        total_is_cumulative=False,
    )


def parse_gemini_line(line: str, path: Path, *, account: str = "default") -> TokenSnapshot | None:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None

    if not isinstance(event, dict):
        return None
    tokens = event.get("tokens")
    if not isinstance(tokens, dict):
        return None

    timestamp = parse_timestamp(event.get("timestamp") or event.get("lastUpdated") or event.get("startTime"))
    if timestamp is None:
        return None

    input_tokens = _int(tokens.get("input"))
    output_tokens = _int(tokens.get("output"))
    reasoning_tokens = _int(tokens.get("thoughts"))
    tool_tokens = _int(tokens.get("tool"))
    total_tokens = _int(tokens.get("total")) or input_tokens + output_tokens + reasoning_tokens + tool_tokens
    usage_obj = TokenUsage(
        input_tokens=input_tokens,
        cached_input_tokens=_int(tokens.get("cached")),
        output_tokens=output_tokens,
        reasoning_output_tokens=reasoning_tokens,
        tool_tokens=tool_tokens,
        total_tokens=total_tokens,
    )
    return TokenSnapshot(
        timestamp=timestamp,
        session_id=str(event.get("id") or event.get("sessionId") or parse_session_id(path)),
        file_path=str(path),
        total=usage_obj,
        last=usage_obj,
        model_context_window=None,
        rate_limits={},
        provider="gemini",
        account=account,
        model=str(event.get("model") or ""),
        total_is_cumulative=False,
    )


def parse_grok_line(line: str, path: Path, *, account: str = "default") -> TokenSnapshot | None:
    """Parse Grok Build session updates.jsonl turn_completed usage events."""
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(event, dict):
        return None

    params = event.get("params") if isinstance(event.get("params"), dict) else {}
    update = params.get("update") if isinstance(params.get("update"), dict) else {}
    if update.get("sessionUpdate") != "turn_completed":
        return None
    usage = update.get("usage")
    if not isinstance(usage, dict):
        return None
    if usage.get("usageIsIncomplete") and usage.get("costUsdTicks") is None and not usage.get("inputTokens"):
        return None

    timestamp = _parse_flexible_timestamp(event.get("timestamp"))
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    input_tokens = _int(usage.get("inputTokens") or usage.get("input_tokens"))
    output_tokens = _int(usage.get("outputTokens") or usage.get("output_tokens"))
    cached = _int(
        usage.get("cachedReadTokens")
        or usage.get("cacheReadInputTokens")
        or usage.get("cache_read_input_tokens")
    )
    reasoning = _int(usage.get("reasoningTokens") or usage.get("reasoning_tokens") or usage.get("thoughtTokens"))
    total_tokens = _int(usage.get("totalTokens") or usage.get("total_tokens")) or (
        input_tokens + output_tokens
    )
    usage_obj = TokenUsage(
        input_tokens=input_tokens,
        cached_input_tokens=cached,
        output_tokens=output_tokens,
        reasoning_output_tokens=reasoning,
        total_tokens=total_tokens,
    )

    model = ""
    model_usage = usage.get("modelUsage") if isinstance(usage.get("modelUsage"), dict) else {}
    if model_usage:
        # Prefer the model with the most modelCalls / cost.
        best_key = ""
        best_score = -1
        for key, row in model_usage.items():
            row = row or {}
            score = _int(row.get("modelCalls")) + _int(row.get("costUsdTicks"))
            if score >= best_score:
                best_score = score
                best_key = str(key)
        model = best_key

    server_cost_usd = None
    cost_source = ""
    ticks = usage.get("costUsdTicks")
    if ticks is not None:
        try:
            server_cost_usd = round(int(ticks) / COST_USD_TICKS_PER_DOLLAR, 8)
            cost_source = "server_cost_ticks"
        except (TypeError, ValueError):
            server_cost_usd = None

    session_id = str(
        params.get("sessionId")
        or update.get("sessionId")
        or parse_session_id(path.parent if path.name == "updates.jsonl" else path)
    )

    return TokenSnapshot(
        timestamp=timestamp,
        session_id=session_id,
        file_path=str(path),
        total=usage_obj,
        last=usage_obj,
        model_context_window=None,
        rate_limits={},
        provider="grok",
        account=account,
        model=model,
        total_is_cumulative=False,
        server_cost_usd=server_cost_usd,
        cost_source=cost_source,
    )


def _parse_flexible_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        return parse_timestamp(value)
    if isinstance(value, (int, float)):
        for divisor in (1, 1000):
            try:
                dt = datetime.fromtimestamp(value / divisor, tz=timezone.utc)
                if 2020 <= dt.year <= 2035:
                    return dt
            except (OverflowError, OSError, ValueError):
                continue
    return None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
