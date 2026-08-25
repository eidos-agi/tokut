from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from getpass import getuser
from pathlib import Path
from typing import Any

from .config import DEFAULT_PRICING_FILE, DEFAULT_SUBSCRIPTIONS_FILE
from .parser import (
    TokenSnapshot,
    TokenUsage,
    parse_claude_line,
    parse_gemini_line,
    parse_grok_line,
    parse_token_count_line,
)

WINDOWS: tuple[tuple[str, timedelta], ...] = (
    ("5m", timedelta(minutes=5)),
    ("30m", timedelta(minutes=30)),
    ("1h", timedelta(hours=1)),
    ("5h", timedelta(hours=5)),
    ("7d", timedelta(days=7)),
)

FILTER_KEYS = ("provider", "account", "company", "project", "model", "user", "day", "hour")
MILLION = 1_000_000
MINUTE_ROW_LIMIT = 720
API_ENV_MARKERS = (
    "ANTHROPIC_API_KEY",
    "CLAUDE_API_KEY",
    "OPENAI_API_KEY",
    "CODEX_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "XAI_API_KEY",
    "GROK_API_KEY",
)

DEFAULT_PRICING_RATES: list[dict[str, Any]] = [
    {
        "provider": "claude",
        "model_prefix": "claude-fable",
        "input_per_million": 10.0,
        "cached_input_per_million": 1.0,
        "output_per_million": 50.0,
        "source": "anthropic_fable_2026_06",
    },
    {
        "provider": "claude",
        "model_prefix": "claude-mythos",
        "input_per_million": 10.0,
        "cached_input_per_million": 1.0,
        "output_per_million": 50.0,
        "source": "anthropic_mythos_2026_06",
    },
    {
        "provider": "claude",
        "model_prefix": "claude-opus",
        "input_per_million": 5.0,
        "cached_input_per_million": 0.5,
        "output_per_million": 25.0,
        "source": "anthropic_opus_2026_06",
    },
    {
        "provider": "claude",
        "model_prefix": "claude-sonnet",
        "input_per_million": 3.0,
        "cached_input_per_million": 0.3,
        "output_per_million": 15.0,
        "source": "anthropic_sonnet_2026_06",
    },
    {
        "provider": "claude",
        "model_prefix": "claude-haiku",
        "input_per_million": 0.8,
        "cached_input_per_million": 0.08,
        "output_per_million": 4.0,
        "source": "anthropic_haiku_estimate",
    },
    {
        "provider": "gemini",
        "model_prefix": "gemini-3-flash",
        "input_per_million": 0.5,
        "cached_input_per_million": 0.05,
        "output_per_million": 3.0,
        "source": "google_gemini_flash_2026_06",
    },
    {
        "provider": "gemini",
        "model_prefix": "gemini-3.5-flash",
        "input_per_million": 1.5,
        "cached_input_per_million": 0.15,
        "output_per_million": 9.0,
        "source": "google_gemini_flash_2026_06",
    },
    {
        "provider": "gemini",
        "model_prefix": "gemini-3-flash-lite",
        "input_per_million": 0.25,
        "cached_input_per_million": 0.025,
        "output_per_million": 1.5,
        "source": "google_gemini_flash_lite_2026_06",
    },
    {
        "provider": "openai",
        "model_prefix": "gpt-5.5",
        "input_per_million": 5.0,
        "cached_input_per_million": 0.5,
        "output_per_million": 30.0,
        "source": "openai_gpt55_standard_short_context_2026_06_11",
    },
    {
        "provider": "openai",
        "model_prefix": "gpt-5.5-pro",
        "input_per_million": 30.0,
        "cached_input_per_million": 30.0,
        "output_per_million": 180.0,
        "source": "openai_gpt55_pro_standard_short_context_2026_06_11",
    },
    {
        "provider": "openai",
        "model_prefix": "gpt-5.4",
        "input_per_million": 2.5,
        "cached_input_per_million": 0.25,
        "output_per_million": 15.0,
        "source": "openai_gpt54_standard_short_context_2026_06_11",
    },
    {
        "provider": "openai",
        "model_prefix": "gpt-5.4-mini",
        "input_per_million": 0.75,
        "cached_input_per_million": 0.075,
        "output_per_million": 4.5,
        "source": "openai_gpt54_mini_standard_2026_06_11",
    },
    {
        "provider": "openai",
        "model_prefix": "gpt-5.4-nano",
        "input_per_million": 0.2,
        "cached_input_per_million": 0.02,
        "output_per_million": 1.25,
        "source": "openai_gpt54_nano_standard_2026_06_11",
    },
    {
        "provider": "openai",
        "model_prefix": "gpt-5.3-codex",
        "input_per_million": 1.75,
        "cached_input_per_million": 0.175,
        "output_per_million": 14.0,
        "source": "openai_gpt53_codex_standard_2026_06_11",
    },
    {
        "provider": "grok",
        "model_prefix": "grok-4.5",
        "input_per_million": 0.6,
        "cached_input_per_million": 0.15,
        "output_per_million": 3.0,
        "source": "grok_list_price_fallback_2026_07",
    },
    {
        "provider": "grok",
        "model_prefix": "grok-",
        "input_per_million": 0.6,
        "cached_input_per_million": 0.15,
        "output_per_million": 3.0,
        "source": "grok_list_price_fallback_2026_07",
    },
]


class TokenBurnStore:
    """Budgeted read-only tailer for local AI session logs (Codex, Claude, Gemini, Grok)."""

    def __init__(
        self,
        *,
        codex_home: Path | None = None,
        codex_roots: list[Path] | None = None,
        claude_roots: list[Path] | None = None,
        gemini_roots: list[Path] | None = None,
        grok_roots: list[Path] | None = None,
        max_files: int = 500,
        max_events: int = 10000,
        initial_tail_bytes: int = 8 * 1024 * 1024,
        local_user: str | None = None,
        pricing_file: Path | None = None,
        subscriptions_file: Path | None = None,
    ) -> None:
        self.codex_home = Path(codex_home or os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
        self.codex_roots = codex_roots if codex_roots is not None else _roots_from_env("CODEX_TOKEN_BURN_ROOTS", self.codex_home)
        self.claude_roots = claude_roots if claude_roots is not None else _roots_from_env("CLAUDE_TOKEN_BURN_ROOTS", Path("~/.claude").expanduser())
        self.gemini_roots = gemini_roots if gemini_roots is not None else _roots_from_env("GEMINI_TOKEN_BURN_ROOTS", Path("~/.gemini").expanduser())
        self.grok_roots = grok_roots if grok_roots is not None else _roots_from_env(
            "GROK_TOKEN_BURN_ROOTS",
            Path(os.environ.get("GROK_HOME", "~/.grok")).expanduser(),
        )
        self.max_files = max_files
        self.max_events = max_events
        self.initial_tail_bytes = initial_tail_bytes
        self._offsets: dict[Path, int] = {}
        self._file_kinds: dict[Path, tuple[str, str]] = {}
        self._events: list[TokenSnapshot] = []
        self._thread_names: dict[str, str] = {}
        self._codex_models: dict[Path, str] = {}
        self._local_user = local_user or os.environ.get("TOKUT_LOCAL_USER") or os.environ.get("CODEX_TOKEN_BURN_USER") or getuser()
        self._pricing_rates = _load_pricing_rates(pricing_file)
        self._subscriptions = _load_subscriptions(subscriptions_file)
        self._version = 0
        self._last_discovery = 0.0
        self._files: list[Path] = []

    @property
    def version(self) -> int:
        return self._version

    def refresh(self) -> int:
        self._load_session_index()
        self._discover_files()

        added = 0
        for path in self._files:
            added += self._read_new(path)
        if added:
            self._events.sort(key=lambda event: event.timestamp)
            if len(self._events) > self.max_events:
                self._events = self._events[-self.max_events :]
            self._version += 1
        return added

    def dashboard(self, *, now: datetime | None = None, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        all_events = list(self._events)
        active_filters = _normalize_filters(filters)
        events = self._filtered_events(all_events, active_filters)
        latest = events[-1] if events else None
        windows: dict[str, dict[str, Any]] = {}
        for name, span in WINDOWS:
            window_events = [event for event in events if event.timestamp >= now - span]
            window_row = self._window_usage(window_events, now, span).to_dict()
            window_row["estimated_cost_usd"] = self._events_cost(window_events)["estimated_cost_usd"]
            windows[name] = window_row
        sessions = self._session_rows(events, now)
        costs = self._cost_summary(events, now)

        return {
            "generated_at": now.isoformat(),
            "codex_home": str(self.codex_home),
            "roots": {
                "codex": [str(root) for root in self.codex_roots],
                "claude": [str(root) for root in self.claude_roots],
                "gemini": [str(root) for root in self.gemini_roots],
                "grok": [str(root) for root in self.grok_roots],
            },
            "event_count": len(events),
            "total_event_count": len(all_events),
            "watched_files": len(self._files),
            "version": self._version,
            "active_filters": {key: sorted(value) for key, value in active_filters.items()},
            "filters": self._filter_facets(all_events),
            "current": self._snapshot_dict(latest) if latest else None,
            "windows": windows,
            "costs": costs,
            "billing": self._billing_summary(events, costs),
            "consult": self.consult(events=events, now=now),
            "subscriptions": self._subscription_rows(events),
            "providers": self._group_rows(events, now, key="provider"),
            "accounts": self._group_rows(events, now, key="account", provider_key=True),
            "models": self._model_rows(events, now),
            "minute_costs": self._minute_cost_rows(events),
            "minute_model_costs": self._minute_model_cost_rows(events),
            "mtd_spend": self._mtd_spend_rows(events, now),
            "breakdowns": {
                "project": self._breakdown_rows(events, now, "project"),
                "account": self._breakdown_rows(events, now, "account"),
                "model": self._breakdown_rows(events, now, "model"),
                "user": self._breakdown_rows(events, now, "user"),
                "day": self._breakdown_rows(events, now, "day"),
                "hour": self._breakdown_rows(events, now, "hour"),
            },
            "sessions": sessions,
            "latest_rate_limits": latest.rate_limits if latest else {},
        }

    def consult(
        self,
        *,
        events: list[TokenSnapshot] | None = None,
        now: datetime | None = None,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Deterministic cost-consultant briefing (meter vs cash; no LLM)."""
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if events is None:
            active_filters = _normalize_filters(filters)
            events = self._filtered_events(list(self._events), active_filters)
        costs = self._cost_summary(events, now)
        billing = self._billing_summary(events, costs)
        sessions = self._session_rows(events, now)
        top_sessions = sorted(
            sessions,
            key=lambda row: float(row.get("estimated_cost_usd") or 0),
            reverse=True,
        )[:10]
        top_models = self._model_rows(events, now)[:10]
        actions: list[str] = []
        if billing.get("unknown_theoretical_usd", 0) > 0:
            actions.append("Map unassigned provider/accounts in ~/.config/tokut/subscriptions.json (billing_mode).")
        if billing.get("overage_cap_usd", 0) > 0:
            actions.append(
                f"Overage auto top-up cash ceiling configured at ${billing['overage_cap_usd']:.2f}/mo — "
                "meter can exceed this; cash should not via auto top-up alone."
            )
        if billing.get("included_allowance_usd", 0) > 0:
            actions.append(
                f"Plan included allowance ${billing['included_allowance_usd']:.2f} list-$ is discounted plan credits; "
                f"metered above that is ${billing.get('metered_usd', 0):.2f}."
            )
        elif any(
            (self._subscription_for(e.provider, e.account).get("billing_mode") == "subscription")
            for e in events
        ):
            actions.append(
                "Set included.allowance_usd on subscription accounts to split plan credits vs metered overage "
                "(otherwise all sub burn is treated as plan credits)."
            )
        if any(e.provider == "grok" for e in events):
            actions.append("Grok meter may use server costUsdTicks; reconcile cash on grok.com billing / Settings → Usage.")
        live_pools = _live_pool_rows(self._subscriptions)
        for pool in live_pools:
            used = pool.get("percent_used")
            resets = pool.get("resets_at") or "unknown reset"
            label = f"{pool.get('subscription') or pool.get('provider')} weekly pool"
            if used is not None:
                actions.append(
                    f"{label} observed {used:g}% used (resets {resets})"
                    + ("; Extra Credits in use after the included week" if used >= 100 else "")
                    + ". Human snapshot, not a live xAI scrape."
                )
            if pool.get("not_this_pool"):
                actions.append(
                    f"{label} does not include: " + "; ".join(pool["not_this_pool"][:2])
                )
        extra_credits = _extra_credit_rows(self._subscriptions)
        for credit in extra_credits:
            actions.append(
                f"{credit.get('subscription') or credit.get('provider')} Extra Usage Credits "
                f"${credit['balance_usd']:.2f}"
                + (" currently in use" if credit.get("in_use") else "")
                + f" (observed {credit.get('observed_at') or 'unknown'})."
            )
        if not actions:
            actions.append("No urgent mapping gaps. Reconcile cash against provider invoices before treating estimates as spend.")

        meter = float(billing.get("theoretical_api_equivalent_usd") or costs.get("estimated_total_usd") or 0)
        paid = float(billing.get("paid_api_or_overage_usd") or 0)
        plan_credits = float(billing.get("plan_credits_usd") or billing.get("subscription_theoretical_usd") or 0)
        metered = float(billing.get("metered_usd") or 0)
        cap = float(billing.get("overage_cap_usd") or 0)
        cash_max = float(billing.get("cash_exposure_max_usd") or (paid + cap))

        headline = (
            f"Meter ${meter:.2f} · "
            f"plan credits (discounted) ${plan_credits:.2f} · "
            f"metered above plan ${metered:.2f} · "
            f"cash ${paid:.2f} (max ${cash_max:.2f}) · "
            f"confidence={billing.get('actual_charge_confidence', 'unverified')}"
        )

        return {
            "generated_at": now.isoformat(),
            "headline": headline,
            "ledgers": {
                "meter_usd": round(meter, 8),
                "plan_credits_usd": round(plan_credits, 8),
                "discounted_usage_usd": round(plan_credits, 8),
                "subscription_covered_usd": round(plan_credits, 8),
                "metered_usd": round(metered, 8),
                "paid_api_or_overage_usd": round(paid, 8),
                "unknown_meter_usd": round(float(billing.get("unknown_theoretical_usd") or 0), 8),
                "included_allowance_usd": round(float(billing.get("included_allowance_usd") or 0), 8),
                "overage_cap_usd": round(cap, 8),
                "cash_exposure_max_usd": cash_max,
                "recorded_cash_usd": None,
            },
            "confidence": {
                "meter": "server_ticks_or_list_price",
                "cash": billing.get("actual_charge_confidence") or "unverified",
                "recorded_cash": "none_imported",
            },
            "live_pools": live_pools,
            "extra_credits": extra_credits,
            "domain_rules": ["DR-001", "DR-002", "DR-003", "DR-004", "DR-005", "DR-006", "DR-007"],
            "top_sessions": [
                {
                    "provider": row["provider"],
                    "project": row.get("project"),
                    "session_id": row["session_id"],
                    "thread_name": row.get("thread_name"),
                    "meter_usd": row.get("estimated_cost_usd"),
                    "tokens": row.get("total_tokens"),
                }
                for row in top_sessions
            ],
            "top_models": [
                {
                    "provider": row["provider"],
                    "model": row["model"],
                    "meter_usd": row.get("estimated_cost_usd"),
                    "actual_charge_usd": row.get("actual_charge_usd"),
                    "tokens": row.get("total_tokens"),
                }
                for row in top_models
            ],
            "actions": actions,
            "warning": billing.get("warning"),
        }

    def _discover_files(self) -> None:
        now = time.monotonic()
        if self._files and now - self._last_discovery < 5.0:
            return
        paths: list[Path] = []
        kinds: dict[Path, tuple[str, str]] = {}

        for root in self.codex_roots:
            account = _account_label(root, "codex")
            for path in _recent_files(root / "sessions", ("*.jsonl",)):
                paths.append(path)
                kinds[path] = ("codex", account)

        for root in self.claude_roots:
            account = _account_label(root, "claude")
            for path in _recent_files(root / "projects", ("*.jsonl",)):
                paths.append(path)
                kinds[path] = ("claude", account)

        for root in self.gemini_roots:
            account = _account_label(root, "gemini")
            for path in _recent_files(root / "tmp", ("*.jsonl", "*.json")):
                if "/chats/" not in str(path):
                    continue
                paths.append(path)
                kinds[path] = ("gemini", account)

        for root in self.grok_roots:
            account = _account_label(root, "grok")
            # Grok Build: ~/.grok/sessions/<cwd-encoded>/<session-id>/updates.jsonl
            for path in _recent_files(root / "sessions", ("updates.jsonl",)):
                paths.append(path)
                kinds[path] = ("grok", account)

        paths.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)
        self._files = paths[: self.max_files]
        self._file_kinds = {path: kinds[path] for path in self._files if path in kinds}
        self._last_discovery = now

    def _read_new(self, path: Path) -> int:
        try:
            size = path.stat().st_size
        except OSError:
            return 0

        skip_partial_line = False
        offset = self._offsets.get(path)
        if offset is None:
            offset = 0
            if size > self.initial_tail_bytes:
                offset = max(size - self.initial_tail_bytes, 0)
                skip_partial_line = True
        if offset > size:
            offset = 0

        added = 0
        try:
            with path.open("r", encoding="utf-8") as handle:
                handle.seek(offset)
                if skip_partial_line:
                    handle.readline()
                for line in handle:
                    snapshot = self._parse_line(line, path)
                    if snapshot is not None:
                        self._events.append(snapshot)
                        added += 1
                self._offsets[path] = handle.tell()
        except OSError:
            return 0
        return added

    def _parse_line(self, line: str, path: Path) -> TokenSnapshot | None:
        kind, account = self._file_kinds.get(path, ("codex", "default"))
        if kind == "claude":
            snapshot = parse_claude_line(line, path, account=account)
            return self._enrich_snapshot(snapshot, path, account)
        if kind == "gemini":
            snapshot = parse_gemini_line(line, path, account=account)
            return self._enrich_snapshot(snapshot, path, account)
        if kind == "grok":
            snapshot = parse_grok_line(line, path, account=account)
            return self._enrich_snapshot(snapshot, path, account)
        self._capture_codex_model(line, path)
        snapshot = parse_token_count_line(line, path)
        if snapshot is None:
            return None
        if not snapshot.model and self._codex_models.get(path):
            snapshot = TokenSnapshot(
                timestamp=snapshot.timestamp,
                session_id=snapshot.session_id,
                file_path=snapshot.file_path,
                total=snapshot.total,
                last=snapshot.last,
                model_context_window=snapshot.model_context_window,
                rate_limits=snapshot.rate_limits,
                provider=snapshot.provider,
                account=snapshot.account,
                project=snapshot.project,
                user=snapshot.user,
                model=self._codex_models[path],
                total_is_cumulative=snapshot.total_is_cumulative,
                server_cost_usd=snapshot.server_cost_usd,
                cost_source=snapshot.cost_source,
            )
        return self._enrich_snapshot(snapshot, path, account)

    def _capture_codex_model(self, line: str, path: Path) -> None:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return
        payload = event.get("payload") if isinstance(event, dict) else None
        if not isinstance(payload, dict):
            return
        model = ""
        if event.get("type") == "turn_context":
            model = str(payload.get("model") or "")
        elif event.get("type") == "session_meta":
            model = str(payload.get("model") or payload.get("model_slug") or "")
        if model:
            self._codex_models[path] = model

    def _enrich_snapshot(self, snapshot: TokenSnapshot | None, path: Path, account: str) -> TokenSnapshot | None:
        if snapshot is None:
            return None
        return TokenSnapshot(
            timestamp=snapshot.timestamp,
            session_id=snapshot.session_id,
            file_path=snapshot.file_path,
            total=snapshot.total,
            last=snapshot.last,
            model_context_window=snapshot.model_context_window,
            rate_limits=snapshot.rate_limits,
            provider=snapshot.provider,
            account=account,
            project=self._project_label(snapshot, path),
            user=snapshot.user or self._local_user,
            model=snapshot.model,
            total_is_cumulative=snapshot.total_is_cumulative,
            server_cost_usd=snapshot.server_cost_usd,
            cost_source=snapshot.cost_source,
        )

    def _load_session_index(self) -> None:
        path = self.codex_home / "session_index.jsonl"
        if not path.exists():
            return
        names: dict[str, str] = {}
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    session_id = row.get("id")
                    thread_name = row.get("thread_name")
                    if session_id and thread_name:
                        names[str(session_id)] = str(thread_name)
        except OSError:
            return
        self._thread_names = names

    def _window_usage(self, events: list[TokenSnapshot], now: datetime, span: timedelta) -> TokenUsage:
        cutoff = now - span
        total = TokenUsage()
        for event in events:
            if event.timestamp >= cutoff:
                total = _add_usage(total, event.last)
        return total

    def _filtered_events(self, events: list[TokenSnapshot], filters: dict[str, set[str]]) -> list[TokenSnapshot]:
        if not filters:
            return events
        return [event for event in events if self._matches_filters(event, filters)]

    def _matches_filters(self, event: TokenSnapshot, filters: dict[str, set[str]]) -> bool:
        dimensions = self._event_dimensions(event)
        for key, values in filters.items():
            if values and str(dimensions.get(key, "")) not in values:
                return False
        return True

    def _filter_facets(self, events: list[TokenSnapshot]) -> dict[str, list[str]]:
        facets: dict[str, set[str]] = {key: set() for key in FILTER_KEYS}
        for event in events:
            dimensions = self._event_dimensions(event)
            for key in FILTER_KEYS:
                value = str(dimensions.get(key, "")).strip()
                if value:
                    facets[key].add(value)
        return {
            "provider": sorted(facets["provider"]),
            "account": sorted(facets["account"]),
            "company": sorted(facets["company"]),
            "project": sorted(facets["project"]),
            "model": sorted(facets["model"]),
            "user": sorted(facets["user"]),
            "day": sorted(facets["day"], reverse=True),
            "hour": sorted(facets["hour"]),
        }

    def _event_dimensions(self, event: TokenSnapshot) -> dict[str, str]:
        subscription = self._subscription_for(event.provider, event.account)
        return {
            "provider": event.provider or "unknown",
            "account": event.account or "default",
            "company": subscription["company"],
            "project": event.project or "unknown",
            "model": event.model or "unknown",
            "user": event.user or self._local_user,
            "day": event.timestamp.astimezone(timezone.utc).date().isoformat(),
            "hour": event.timestamp.astimezone(timezone.utc).strftime("%H:00"),
        }

    def _session_rows(self, events: list[TokenSnapshot], now: datetime) -> list[dict[str, Any]]:
        by_session: dict[str, list[TokenSnapshot]] = defaultdict(list)
        for event in events:
            by_session[f"{event.provider}:{event.account}:{event.session_id}"].append(event)

        rows = []
        for _, session_events in by_session.items():
            latest = session_events[-1]
            total_usage = _session_total(session_events)
            dimensions = self._event_dimensions(latest)
            subscription = self._subscription_for(latest.provider, latest.account)
            total_cost = self._events_cost(session_events)
            rows.append(
                {
                    "provider": latest.provider,
                    "account": latest.account,
                    "company": subscription["company"],
                    "subscription": subscription,
                    "project": dimensions["project"],
                    "model": dimensions["model"],
                    "user": dimensions["user"],
                    "day": dimensions["day"],
                    "hour": dimensions["hour"],
                    "session_id": latest.session_id,
                    "thread_name": self._thread_names.get(latest.session_id, ""),
                    "model": latest.model,
                    "latest_at": latest.timestamp.isoformat(),
                    "total_tokens": total_usage.total_tokens,
                    "last_tokens": latest.last.total_tokens,
                    "burn_1h": self._window_usage(session_events, now, timedelta(hours=1)).total_tokens,
                    "burn_5h": self._window_usage(session_events, now, timedelta(hours=5)).total_tokens,
                    "estimated_cost_usd": total_cost["estimated_cost_usd"],
                    "cost_1h_usd": self._window_cost(session_events, now, timedelta(hours=1))["estimated_cost_usd"],
                    "cost_5h_usd": self._window_cost(session_events, now, timedelta(hours=5))["estimated_cost_usd"],
                    "pricing_source": total_cost["pricing_source"],
                    "event_count": len(session_events),
                    "file_path": latest.file_path,
                }
            )
        rows.sort(key=lambda row: row["latest_at"], reverse=True)
        return rows

    def _group_rows(self, events: list[TokenSnapshot], now: datetime, *, key: str, provider_key: bool = False) -> list[dict[str, Any]]:
        groups: dict[str, list[TokenSnapshot]] = defaultdict(list)
        for event in events:
            group_key = getattr(event, key)
            if provider_key:
                group_key = f"{event.provider}:{group_key}"
            groups[group_key].append(event)

        rows = []
        for group_key, group_events in groups.items():
            latest = group_events[-1]
            total_usage = _total_last_usage(group_events)
            total_cost = self._events_cost(group_events)
            subscription = self._subscription_for(latest.provider, latest.account)
            row = {
                "provider": latest.provider,
                "company": subscription["company"],
                "subscription": subscription,
                "latest_at": latest.timestamp.isoformat(),
                "event_count": len(group_events),
                "total_tokens": total_usage.total_tokens,
                "burn_1h": self._window_usage(group_events, now, timedelta(hours=1)).total_tokens,
                "burn_5h": self._window_usage(group_events, now, timedelta(hours=5)).total_tokens,
                "estimated_cost_usd": total_cost["estimated_cost_usd"],
                "cost_1h_usd": self._window_cost(group_events, now, timedelta(hours=1))["estimated_cost_usd"],
                "cost_5h_usd": self._window_cost(group_events, now, timedelta(hours=5))["estimated_cost_usd"],
            }
            if key == "provider":
                row["provider"] = group_key
            else:
                row["account"] = latest.account
            rows.append(row)
        rows.sort(key=lambda row: row["burn_1h"], reverse=True)
        return rows

    def _model_rows(self, events: list[TokenSnapshot], now: datetime) -> list[dict[str, Any]]:
        groups: dict[str, list[TokenSnapshot]] = defaultdict(list)
        for event in events:
            groups[f"{event.provider}:{event.model or 'unknown'}"].append(event)

        rows = []
        for _, group_events in groups.items():
            latest = group_events[-1]
            total_usage = _total_last_usage(group_events)
            total_cost = self._events_cost(group_events)
            actual_cost = self._actual_charge_for_events(group_events, _api_env_markers())
            subscription = self._subscription_for(latest.provider, latest.account)
            rows.append(
                {
                    "provider": latest.provider,
                    "company": subscription["company"],
                    "subscription": subscription,
                    "model": latest.model or "unknown",
                    "label": f"{latest.provider} / {latest.model or 'unknown'}",
                    "latest_at": latest.timestamp.isoformat(),
                    "event_count": len(group_events),
                    "total_tokens": total_usage.total_tokens,
                    "input_tokens": total_usage.input_tokens,
                    "cached_input_tokens": total_usage.cached_input_tokens,
                    "output_tokens": total_usage.output_tokens + total_usage.reasoning_output_tokens + total_usage.tool_tokens,
                    "burn_1h": self._window_usage(group_events, now, timedelta(hours=1)).total_tokens,
                    "burn_5h": self._window_usage(group_events, now, timedelta(hours=5)).total_tokens,
                    "estimated_cost_usd": total_cost["estimated_cost_usd"],
                    "actual_charge_usd": actual_cost,
                    "cost_1h_usd": self._window_cost(group_events, now, timedelta(hours=1))["estimated_cost_usd"],
                    "cost_5h_usd": self._window_cost(group_events, now, timedelta(hours=5))["estimated_cost_usd"],
                    "pricing_source": total_cost["pricing_source"],
                    "priced_event_count": total_cost["priced_event_count"],
                    "unpriced_event_count": total_cost["unpriced_event_count"],
                }
            )
        rows.sort(key=lambda row: (row["cost_1h_usd"], row["estimated_cost_usd"], row["burn_1h"]), reverse=True)
        return rows

    def _breakdown_rows(self, events: list[TokenSnapshot], now: datetime, dimension: str) -> list[dict[str, Any]]:
        groups: dict[str, list[TokenSnapshot]] = defaultdict(list)
        for event in events:
            dimensions = self._event_dimensions(event)
            key = str(dimensions.get(dimension, "unknown"))
            if dimension == "account":
                key = f"{event.provider}:{key}"
            groups[key].append(event)

        total_seen = max(1, _total_last_usage(events).total_tokens)
        total_cost_seen = max(0.00000001, self._events_cost(events)["estimated_cost_usd"])
        rows = []
        for group_key, group_events in groups.items():
            latest = group_events[-1]
            total_usage = _total_last_usage(group_events)
            total_cost = self._events_cost(group_events)
            dimensions = self._event_dimensions(latest)
            subscription = self._subscription_for(latest.provider, latest.account)
            label = group_key
            if dimension == "account":
                label = f"{latest.provider} / {latest.account}"
            if dimension == "model":
                label = f"{latest.provider} / {latest.model or 'unknown'}"
            rows.append(
                {
                    "dimension": dimension,
                    "label": label,
                    "value": dimensions.get(dimension, group_key),
                    "provider": latest.provider,
                    "account": latest.account,
                    "company": subscription["company"],
                    "subscription": subscription,
                    "latest_at": latest.timestamp.isoformat(),
                    "event_count": len(group_events),
                    "total_tokens": total_usage.total_tokens,
                    "share_percent": round((total_usage.total_tokens / total_seen) * 100, 2),
                    "estimated_cost_usd": total_cost["estimated_cost_usd"],
                    "cost_share_percent": round((total_cost["estimated_cost_usd"] / total_cost_seen) * 100, 2),
                    "cost_1h_usd": self._window_cost(group_events, now, timedelta(hours=1))["estimated_cost_usd"],
                    "cost_5h_usd": self._window_cost(group_events, now, timedelta(hours=5))["estimated_cost_usd"],
                    "burn_1h": self._window_usage(group_events, now, timedelta(hours=1)).total_tokens,
                    "burn_5h": self._window_usage(group_events, now, timedelta(hours=5)).total_tokens,
                }
            )
        rows.sort(key=lambda row: (row["estimated_cost_usd"], row["total_tokens"]), reverse=True)
        return rows

    def _snapshot_dict(self, snapshot: TokenSnapshot | None) -> dict[str, Any] | None:
        if snapshot is None:
            return None
        data = snapshot.to_dict(thread_name=self._thread_names.get(snapshot.session_id, ""))
        data.update(self._event_dimensions(snapshot))
        data["estimated_cost"] = self._event_cost(snapshot)
        return data

    def _cost_summary(self, events: list[TokenSnapshot], now: datetime) -> dict[str, Any]:
        total = self._events_cost(events)
        window_5m = self._window_cost(events, now, timedelta(minutes=5))
        window_1h = self._window_cost(events, now, timedelta(hours=1))
        window_5h = self._window_cost(events, now, timedelta(hours=5))
        current_minute = self._minute_floor(now)
        current_minute_events = [event for event in events if self._minute_floor(event.timestamp) == current_minute]
        current = self._events_cost(current_minute_events)
        unpriced_models = sorted(
            {
                f"{event.provider}/{event.model or 'unknown'}"
                for event in events
                if not self._event_cost(event)["priced"]
            }
        )
        return {
            "estimated_total_usd": total["estimated_cost_usd"],
            "estimated_5m_usd": window_5m["estimated_cost_usd"],
            "estimated_1h_usd": window_1h["estimated_cost_usd"],
            "estimated_5h_usd": window_5h["estimated_cost_usd"],
            "estimated_current_minute_usd": current["estimated_cost_usd"],
            "estimated_per_minute_5m_usd": round(window_5m["estimated_cost_usd"] / 5, 8),
            "priced_event_count": total["priced_event_count"],
            "unpriced_event_count": total["unpriced_event_count"],
            "unpriced_models": unpriced_models,
            "estimate_basis": "api_list_price_equivalent",
            "actual_charge_confidence": "unverified",
            "pricing_source": "built_in_estimates_or_CODEX_TOKEN_BURN_PRICING_FILE",
        }

    def _billing_summary(self, events: list[TokenSnapshot], costs: dict[str, Any]) -> dict[str, Any]:
        providers = sorted({event.provider for event in events})
        env_markers = _api_env_markers()
        provider_confidence = {}
        plan_credits_total = 0.0
        metered_total = 0.0
        unknown_theoretical = 0.0
        cash_total = 0.0
        overage_cap = 0.0
        cash_exposure_max = 0.0
        included_allowance_total = 0.0

        for (provider, account), account_events in _events_by_account(events).items():
            subscription = self._subscription_for(provider, account)
            meter = self._events_cost(account_events)["estimated_cost_usd"]
            alloc = _account_cost_allocation(subscription, meter, env_markers)
            plan_credits_total += alloc["plan_credits_usd"]
            metered_total += alloc["metered_usd"]
            unknown_theoretical += alloc.get("unknown_usd") or 0.0
            cash_total += alloc["cash_exposure_usd"]
            overage_cap += alloc.get("overage_cap_usd") or 0.0
            cash_exposure_max += alloc["cash_exposure_max_usd"]
            included_allowance_total += alloc.get("included_allowance_usd") or 0.0

        for provider in providers:
            provider_events = [event for event in events if event.provider == provider]
            provider_cost = self._events_cost(provider_events)
            actual_charge = 0.0
            for account_events in _events_by_account(provider_events).values():
                subscription = self._subscription_for(account_events[0].provider, account_events[0].account)
                meter = self._events_cost(account_events)["estimated_cost_usd"]
                actual_charge += _account_cost_allocation(subscription, meter, env_markers)["cash_exposure_usd"]
            provider_confidence[provider] = {
                "actual_charge_confidence": _provider_charge_confidence(provider, env_markers),
                "actual_charge_usd": round(actual_charge, 8),
                "estimated_api_equivalent_usd": provider_cost["estimated_cost_usd"],
                "theoretical_api_equivalent_usd": provider_cost["estimated_cost_usd"],
                "event_count": len(provider_events),
                "note": _provider_charge_note(provider, env_markers),
            }

        actual_charge_total = round(cash_total, 8)
        theoretical_total = costs["estimated_total_usd"]
        plan_credits_total = round(plan_credits_total, 8)
        metered_total = round(metered_total, 8)
        overage_cap = round(overage_cap, 8)
        cash_exposure_max = round(cash_exposure_max, 8)
        # Discounted usage = list/server value covered by plan credits (not cash).
        discount_usd = plan_credits_total
        return {
            "actual_charge_confidence": "unverified",
            "estimate_basis": "api_list_price_equivalent_or_server_ticks",
            "actual_charge_usd": actual_charge_total,
            "confirmed_charge_usd": actual_charge_total,
            "paid_api_or_overage_usd": actual_charge_total,
            "subscription_theoretical_usd": plan_credits_total,
            "plan_credits_usd": plan_credits_total,
            "discounted_usage_usd": discount_usd,
            "metered_usd": metered_total,
            "unknown_theoretical_usd": round(unknown_theoretical, 8),
            "included_allowance_usd": round(included_allowance_total, 8),
            "overage_cap_usd": overage_cap,
            "cash_exposure_max_usd": cash_exposure_max,
            "estimated_api_equivalent_usd": costs["estimated_total_usd"],
            "theoretical_api_equivalent_usd": theoretical_total,
            "theoretical_minus_actual_usd": round(theoretical_total - actual_charge_total, 8),
            "would_pay_without_subscriptions_usd": theoretical_total,
            "observed_api_env_markers": env_markers,
            "provider_confidence": provider_confidence,
            "warning": (
                "Local token logs prove token burn / server cost ticks (meter), not invoice charges (cash). "
                "Plan credits = discounted included usage (list-price value covered by the plan). "
                "Burn above included.allowance_usd is metered (cash-eligible), subject to overage caps. "
                "See DOMAIN_RULES.md DR-001..DR-007."
            ),
        }

    def _estimated_actual_charge(self, events: list[TokenSnapshot], env_markers: list[str]) -> float:
        return self._actual_charge_for_events(events, env_markers)

    def _actual_charge_for_events(self, events: list[TokenSnapshot], env_markers: list[str] | None = None) -> float:
        env_markers = env_markers or []
        total = 0.0
        for (provider, account), account_events in _events_by_account(events).items():
            subscription = self._subscription_for(provider, account)
            meter = self._events_cost(account_events)["estimated_cost_usd"]
            total += _account_cost_allocation(subscription, meter, env_markers)["cash_exposure_usd"]
        return round(total, 8)

    def _subscription_rows(self, events: list[TokenSnapshot]) -> list[dict[str, Any]]:
        groups: dict[tuple[str, str], list[TokenSnapshot]] = defaultdict(list)
        for event in events:
            groups[(event.provider, event.account)].append(event)
        env_markers = _api_env_markers()
        rows = []
        for (provider, account), account_events in groups.items():
            subscription = self._subscription_for(provider, account)
            total_usage = _total_last_usage(account_events)
            theoretical = self._events_cost(account_events)["estimated_cost_usd"]
            alloc = _account_cost_allocation(subscription, theoretical, env_markers)
            rows.append(
                {
                    **subscription,
                    "provider": provider,
                    "account": account,
                    "event_count": len(account_events),
                    "total_tokens": total_usage.total_tokens,
                    "theoretical_api_equivalent_usd": theoretical,
                    "plan_credits_usd": alloc["plan_credits_usd"],
                    "discounted_usage_usd": alloc["plan_credits_usd"],
                    "metered_usd": alloc["metered_usd"],
                    "actual_charge_usd": round(alloc["cash_exposure_usd"], 8),
                    "cash_exposure_max_usd": alloc["cash_exposure_max_usd"],
                }
            )
        rows.sort(key=lambda row: (row["company"], row["provider"], row["account"]))
        return rows

    def _subscription_for(self, provider: str, account: str) -> dict[str, Any]:
        exact = self._subscriptions.get((provider, account))
        provider_default = self._subscriptions.get((provider, "*"))
        row = exact or provider_default
        if row:
            return row
        return {
            "provider": provider,
            "account": account,
            "company": "Unassigned",
            "subscription": "Unconfigured",
            "plan": "Unknown",
            "billing_mode": "unknown",
            "included": {"allowance_usd": 0.0, "period": "month"},
            "overage": {"mode": "none", "monthly_cap_usd": 0.0},
            "actual_cost_policy": "zero_until_configured",
            "configured": False,
            "notes": "Add this provider/account to the subscription config to assign a company and billing mode.",
        }

    def _minute_cost_rows(self, events: list[TokenSnapshot]) -> list[dict[str, Any]]:
        groups: dict[datetime, list[TokenSnapshot]] = defaultdict(list)
        for event in events:
            groups[self._minute_floor(event.timestamp)].append(event)
        rows = [self._minute_row(minute, minute_events) for minute, minute_events in groups.items()]
        rows.sort(key=lambda row: row["minute"], reverse=True)
        return rows[:MINUTE_ROW_LIMIT]

    def _minute_model_cost_rows(self, events: list[TokenSnapshot]) -> list[dict[str, Any]]:
        groups: dict[tuple[datetime, str, str], list[TokenSnapshot]] = defaultdict(list)
        for event in events:
            groups[(self._minute_floor(event.timestamp), event.provider, event.model or "unknown")].append(event)
        rows = []
        for (minute, provider, model), group_events in groups.items():
            row = self._minute_row(minute, group_events)
            row.update({"provider": provider, "model": model, "label": f"{provider} / {model}"})
            rows.append(row)
        rows.sort(key=lambda row: (row["minute"], row["estimated_cost_usd"]), reverse=True)
        return rows[:MINUTE_ROW_LIMIT]

    def _mtd_spend_rows(self, events: list[TokenSnapshot], now: datetime) -> list[dict[str, Any]]:
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        env_markers = _api_env_markers()
        groups: dict[datetime, list[TokenSnapshot]] = defaultdict(list)
        for event in events:
            if month_start <= event.timestamp <= now:
                groups[self._minute_floor(event.timestamp)].append(event)

        rows = []
        cumulative_actual = 0.0
        cumulative_api = 0.0
        cumulative_tokens = 0
        cumulative_events = 0
        for minute in sorted(groups):
            minute_events = groups[minute]
            minute_row = self._minute_row(minute, minute_events)
            actual = self._actual_charge_for_events(minute_events, env_markers)
            cumulative_actual += actual
            cumulative_api += minute_row["estimated_cost_usd"]
            cumulative_tokens += minute_row["total_tokens"]
            cumulative_events += minute_row["event_count"]
            rows.append(
                {
                    "minute": minute.isoformat(),
                    "actual_charge_usd": actual,
                    "api_equivalent_usd": minute_row["estimated_cost_usd"],
                    "mtd_actual_usd": round(cumulative_actual, 8),
                    "mtd_api_equivalent_usd": round(cumulative_api, 8),
                    "mtd_tokens": cumulative_tokens,
                    "mtd_events": cumulative_events,
                    "event_count": minute_row["event_count"],
                    "total_tokens": minute_row["total_tokens"],
                    "priced_event_count": minute_row["priced_event_count"],
                    "unpriced_event_count": minute_row["unpriced_event_count"],
                }
            )
        return rows

    def _minute_row(self, minute: datetime, events: list[TokenSnapshot]) -> dict[str, Any]:
        total_usage = _total_last_usage(events)
        total_cost = self._events_cost(events)
        return {
            "minute": minute.isoformat(),
            "event_count": len(events),
            "total_tokens": total_usage.total_tokens,
            "input_tokens": total_usage.input_tokens,
            "cached_input_tokens": total_usage.cached_input_tokens,
            "output_tokens": total_usage.output_tokens + total_usage.reasoning_output_tokens + total_usage.tool_tokens,
            "estimated_cost_usd": total_cost["estimated_cost_usd"],
            "priced_event_count": total_cost["priced_event_count"],
            "unpriced_event_count": total_cost["unpriced_event_count"],
        }

    def _minute_floor(self, value: datetime) -> datetime:
        return value.astimezone(timezone.utc).replace(second=0, microsecond=0)

    def _window_cost(self, events: list[TokenSnapshot], now: datetime, span: timedelta) -> dict[str, Any]:
        cutoff = now - span
        return self._events_cost([event for event in events if event.timestamp >= cutoff])

    def _events_cost(self, events: list[TokenSnapshot]) -> dict[str, Any]:
        total = 0.0
        priced = 0
        unpriced = 0
        sources: set[str] = set()
        for event in events:
            event_cost = self._event_cost(event)
            total += event_cost["estimated_cost_usd"]
            if event_cost["priced"]:
                priced += 1
            else:
                unpriced += 1
            sources.add(event_cost["pricing_source"])
        return {
            "estimated_cost_usd": round(total, 8),
            "priced_event_count": priced,
            "unpriced_event_count": unpriced,
            "pricing_source": ",".join(sorted(sources)) if sources else "none",
        }

    def _event_cost(self, event: TokenSnapshot) -> dict[str, Any]:
        # DR-003: server cost stamps beat local list-price multiplication.
        if event.server_cost_usd is not None:
            return {
                "estimated_cost_usd": round(float(event.server_cost_usd), 8),
                "input_cost_usd": 0.0,
                "cached_input_cost_usd": 0.0,
                "output_cost_usd": 0.0,
                "pricing_source": event.cost_source or "server_cost_ticks",
                "priced": True,
            }
        rate = self._pricing_rate(event)
        if rate is None:
            return {
                "estimated_cost_usd": 0.0,
                "input_cost_usd": 0.0,
                "cached_input_cost_usd": 0.0,
                "output_cost_usd": 0.0,
                "pricing_source": "unpriced",
                "priced": False,
            }
        usage = event.last
        output_tokens = usage.output_tokens + usage.reasoning_output_tokens + usage.tool_tokens
        input_cost = usage.uncached_input_tokens * float(rate["input_per_million"]) / MILLION
        cached_cost = usage.cached_input_tokens * float(rate["cached_input_per_million"]) / MILLION
        output_cost = output_tokens * float(rate["output_per_million"]) / MILLION
        return {
            "estimated_cost_usd": round(input_cost + cached_cost + output_cost, 8),
            "input_cost_usd": round(input_cost, 8),
            "cached_input_cost_usd": round(cached_cost, 8),
            "output_cost_usd": round(output_cost, 8),
            "pricing_source": str(rate.get("source") or "custom"),
            "priced": True,
        }

    def _pricing_rate(self, event: TokenSnapshot) -> dict[str, Any] | None:
        provider = event.provider.lower()
        model = (event.model or "").lower()
        matched: dict[str, Any] | None = None
        matched_prefix_len = -1
        for rate in self._pricing_rates:
            rate_provider = str(rate.get("provider", "")).lower()
            if provider != rate_provider and not (provider == "codex" and rate_provider == "openai"):
                continue
            exact = str(rate.get("model") or "").lower()
            if exact and model == exact:
                return rate
            prefix = str(rate.get("model_prefix") or "").lower()
            if prefix and model.startswith(prefix) and len(prefix) > matched_prefix_len:
                matched = rate
                matched_prefix_len = len(prefix)
        return matched

    def _project_label(self, snapshot: TokenSnapshot, path: Path) -> str:
        if snapshot.provider == "claude":
            label = _path_child_after(path, "projects")
            return _decode_project_label(label) if label else "unknown"
        if snapshot.provider == "gemini":
            label = _path_child_after(path, "tmp", before="chats")
            return _decode_project_label(label) if label else "unknown"
        if snapshot.provider == "codex":
            return self._thread_names.get(snapshot.session_id) or "codex"
        if snapshot.provider == "grok":
            # ~/.grok/sessions/<cwd-encoded>/<session-id>/updates.jsonl
            label = _path_child_after(path, "sessions")
            if label:
                try:
                    from urllib.parse import unquote

                    decoded = unquote(label)
                    return Path(decoded).name or decoded
                except Exception:
                    return label
            return "grok"
        return "unknown"


def _add_usage(a: TokenUsage, b: TokenUsage) -> TokenUsage:
    return TokenUsage(
        input_tokens=a.input_tokens + b.input_tokens,
        cached_input_tokens=a.cached_input_tokens + b.cached_input_tokens,
        output_tokens=a.output_tokens + b.output_tokens,
        reasoning_output_tokens=a.reasoning_output_tokens + b.reasoning_output_tokens,
        tool_tokens=a.tool_tokens + b.tool_tokens,
        total_tokens=a.total_tokens + b.total_tokens,
    )


def _total_last_usage(events: list[TokenSnapshot]) -> TokenUsage:
    total = TokenUsage()
    for event in events:
        total = _add_usage(total, event.last)
    return total


def _session_total(events: list[TokenSnapshot]) -> TokenUsage:
    latest = events[-1]
    if latest.total_is_cumulative:
        return latest.total
    return _total_last_usage(events)


def _events_by_account(events: list[TokenSnapshot]) -> dict[tuple[str, str], list[TokenSnapshot]]:
    by_account: dict[tuple[str, str], list[TokenSnapshot]] = defaultdict(list)
    for event in events:
        by_account[(event.provider, event.account)].append(event)
    return by_account


def _recent_files(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    if not root.exists():
        return []
    out: list[Path] = []
    for pattern in patterns:
        out.extend(path for path in root.glob(f"**/{pattern}") if path.is_file())
    return out


def _roots_from_env(name: str, default: Path) -> list[Path]:
    raw = os.environ.get(name)
    if not raw:
        return [default]
    return [Path(part).expanduser() for part in raw.split(os.pathsep) if part.strip()]


def _account_label(root: Path, provider: str) -> str:
    expanded = root.expanduser()
    if expanded == Path.home() / f".{provider}" or (provider == "codex" and expanded.name == ".codex"):
        return "default"
    if provider == "grok" and expanded.name in {".grok", "grok"}:
        return "default"
    return expanded.name or "default"


def _normalize_filters(filters: dict[str, Any] | None) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for key, value in (filters or {}).items():
        if key not in FILTER_KEYS:
            continue
        raw_values = value if isinstance(value, list | tuple | set) else [value]
        values = {str(item).strip() for item in raw_values if str(item).strip() and str(item).strip().lower() != "all"}
        if values:
            out[key] = values
    return out


def _load_pricing_rates(path: Path | None = None) -> list[dict[str, Any]]:
    rates = list(DEFAULT_PRICING_RATES)
    path_raw = str(path) if path is not None else os.environ.get("TOKUT_PRICING_FILE") or os.environ.get("CODEX_TOKEN_BURN_PRICING_FILE")
    price_path = Path(path_raw).expanduser() if path_raw else DEFAULT_PRICING_FILE
    if not price_path.exists():
        return rates
    try:
        data = json.loads(price_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return rates
    custom_rates = data.get("rates") if isinstance(data, dict) else data
    if not isinstance(custom_rates, list):
        return rates
    normalized = []
    for rate in custom_rates:
        if not isinstance(rate, dict):
            continue
        if "provider" not in rate or ("model_prefix" not in rate and "model" not in rate):
            continue
        if "input_per_million" not in rate or "output_per_million" not in rate:
            continue
        normalized.append(
            {
                "provider": str(rate["provider"]),
                "model_prefix": str(rate.get("model_prefix") or ""),
                "model": str(rate.get("model") or ""),
                "input_per_million": float(rate["input_per_million"]),
                "cached_input_per_million": float(rate.get("cached_input_per_million", rate["input_per_million"])),
                "output_per_million": float(rate["output_per_million"]),
                "source": str(rate.get("source") or f"custom:{price_path}"),
            }
        )
    return normalized + rates


def _api_env_markers() -> list[str]:
    return sorted(name for name in API_ENV_MARKERS if os.environ.get(name))


def _account_cost_allocation(
    subscription: dict[str, Any],
    meter_usd: float,
    env_markers: list[str] | None = None,
) -> dict[str, Any]:
    """Split account meter into plan credits (discounted) vs metered cash.

    DR-007:
    - included.allowance_usd → plan credits (discounted included usage) at list/server $
    - burn above that allowance → metered (cash-eligible), then limited by overage cap
    - allowance unset/0 → all subscription burn counts as plan credits (pool size unknown);
      overage cap still bounds max cash risk
    """
    env_markers = env_markers or []
    meter_usd = max(float(meter_usd or 0), 0.0)
    mode = str(subscription.get("billing_mode") or "unknown")
    provider = str(subscription.get("provider") or "")
    overage = subscription.get("overage") if isinstance(subscription.get("overage"), dict) else {}
    overage_mode = str(overage.get("mode") or "none")
    try:
        cap = float(overage.get("monthly_cap_usd") or 0)
    except (TypeError, ValueError):
        cap = 0.0
    included = subscription.get("included") if isinstance(subscription.get("included"), dict) else {}
    try:
        allowance = float(included.get("allowance_usd") or 0)
    except (TypeError, ValueError):
        allowance = 0.0
    period = str(included.get("period") or "month")

    # Treat env-marker API keys like api_billed when mode is not subscription/unknown.
    treat_as_api = mode == "api_billed" or (
        mode not in {"subscription", "unknown"}
        and _provider_charge_confidence(provider, env_markers) != "unverified"
    )
    if treat_as_api or mode == "api_billed":
        return {
            "meter_usd": round(meter_usd, 8),
            "plan_credits_usd": 0.0,
            "metered_usd": round(meter_usd, 8),
            "cash_exposure_usd": round(meter_usd, 8),
            "cash_exposure_max_usd": round(meter_usd, 8),
            "discounted_usage_usd": 0.0,
            "included_allowance_usd": 0.0,
            "included_period": period,
            "overage_cap_usd": 0.0,
            "unknown_usd": 0.0,
        }

    if mode != "subscription":
        return {
            "meter_usd": round(meter_usd, 8),
            "plan_credits_usd": 0.0,
            "metered_usd": 0.0,
            "cash_exposure_usd": 0.0,
            "cash_exposure_max_usd": 0.0,
            "discounted_usage_usd": 0.0,
            "included_allowance_usd": 0.0,
            "included_period": period,
            "overage_cap_usd": 0.0,
            "unknown_usd": round(meter_usd, 8),
        }

    if allowance > 0:
        plan_credits = min(meter_usd, allowance)
        metered = max(0.0, meter_usd - allowance)
    else:
        plan_credits = meter_usd
        metered = 0.0

    if overage_mode in {"auto_topup", "extra_credits"} and cap > 0:
        cash = min(metered, cap)
        # Max cash this period: known metered overage, or full cap if pool size unknown.
        cash_max = cap if allowance <= 0 else min(max(0.0, meter_usd - allowance), cap)
    elif overage_mode == "uncapped":
        cash = metered
        cash_max = max(0.0, meter_usd - allowance) if allowance > 0 else 0.0
    else:
        cash = 0.0
        cash_max = 0.0

    return {
        "meter_usd": round(meter_usd, 8),
        "plan_credits_usd": round(plan_credits, 8),
        "metered_usd": round(metered, 8),
        "cash_exposure_usd": round(cash, 8),
        "cash_exposure_max_usd": round(cash_max, 8),
        "discounted_usage_usd": round(plan_credits, 8),
        "included_allowance_usd": round(allowance, 8),
        "included_period": period,
        "overage_cap_usd": round(cap if overage_mode in {"auto_topup", "extra_credits"} else 0.0, 8),
        "unknown_usd": 0.0,
    }


def _load_subscriptions(path: Path | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    path_raw = str(path) if path is not None else os.environ.get("TOKUT_SUBSCRIPTIONS_FILE") or os.environ.get("CODEX_TOKEN_BURN_SUBSCRIPTIONS_FILE")
    subscription_path = Path(path_raw).expanduser() if path_raw else DEFAULT_SUBSCRIPTIONS_FILE
    try:
        data = json.loads(subscription_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    accounts = data.get("accounts") if isinstance(data, dict) else data
    if not isinstance(accounts, list):
        return {}
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for account in accounts:
        if not isinstance(account, dict):
            continue
        provider = str(account.get("provider") or "").strip().lower()
        account_name = str(account.get("account") or "default").strip() or "default"
        if not provider:
            continue
        billing_mode = str(account.get("billing_mode") or "unknown").strip().lower()
        if billing_mode not in {"subscription", "api_billed", "unknown"}:
            billing_mode = "unknown"
        overage_raw = account.get("overage") if isinstance(account.get("overage"), dict) else {}
        overage_mode = str(overage_raw.get("mode") or "none").strip().lower()
        if overage_mode not in {"none", "auto_topup", "extra_credits", "uncapped"}:
            overage_mode = "none"
        try:
            monthly_cap = float(overage_raw.get("monthly_cap_usd") or 0)
        except (TypeError, ValueError):
            monthly_cap = 0.0
        overage = {
            "mode": overage_mode,
            "monthly_cap_usd": monthly_cap,
        }
        for extra_key in ("topup_amount_usd", "trigger_below_usd"):
            try:
                extra_val = float(overage_raw.get(extra_key) or 0)
            except (TypeError, ValueError):
                extra_val = 0.0
            if extra_val > 0:
                overage[extra_key] = extra_val
        included_raw = account.get("included") if isinstance(account.get("included"), dict) else {}
        try:
            allowance_usd = float(included_raw.get("allowance_usd") or 0)
        except (TypeError, ValueError):
            allowance_usd = 0.0
        included_period = str(included_raw.get("period") or "month").strip().lower()
        if included_period not in {"day", "week", "month"}:
            included_period = "month"
        included = {
            "allowance_usd": allowance_usd,
            "period": included_period,
        }
        row = {
            "provider": provider,
            "account": account_name,
            "company": str(account.get("company") or "Unassigned"),
            "subscription": str(account.get("subscription") or account.get("plan") or "Unknown"),
            "plan": str(account.get("plan") or account.get("subscription") or "Unknown"),
            "billing_mode": billing_mode,
            "included": included,
            "overage": overage,
            "actual_cost_policy": "zero_actual" if billing_mode == "subscription" else "theoretical_until_reconciled" if billing_mode == "api_billed" else "zero_until_configured",
            "configured": True,
            "notes": str(account.get("notes") or ""),
        }
        extra_credits = _observation_money(account.get("extra_credits"))
        if extra_credits:
            row["extra_credits"] = extra_credits
        live_pool = _observation_live_pool(account.get("live_pool"))
        if live_pool:
            row["live_pool"] = live_pool
        not_this_pool = account.get("not_this_pool")
        if isinstance(not_this_pool, list):
            row["not_this_pool"] = [str(item) for item in not_this_pool if str(item).strip()]
        out[(provider, account_name)] = row
    return out


def _observation_money(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    try:
        balance = float(raw.get("balance_usd") or 0)
    except (TypeError, ValueError):
        return None
    out: dict[str, Any] = {"balance_usd": round(balance, 8)}
    if "in_use" in raw:
        out["in_use"] = bool(raw.get("in_use"))
    observed = str(raw.get("observed_at") or "").strip()
    if observed:
        out["observed_at"] = observed
    return out


def _observation_live_pool(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    out: dict[str, Any] = {}
    try:
        if raw.get("percent_used") is not None:
            out["percent_used"] = float(raw.get("percent_used"))
    except (TypeError, ValueError):
        pass
    for key in ("resets_at", "timezone", "observed_at", "source"):
        value = str(raw.get(key) or "").strip()
        if value:
            out[key] = value
    products = raw.get("products")
    if isinstance(products, dict):
        cleaned: dict[str, float] = {}
        for name, pct in products.items():
            try:
                cleaned[str(name)] = float(pct)
            except (TypeError, ValueError):
                continue
        if cleaned:
            out["products"] = cleaned
    return out or None


def _live_pool_rows(subscriptions: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (provider, account), sub in subscriptions.items():
        pool = sub.get("live_pool")
        if not isinstance(pool, dict) or not pool:
            continue
        row = {
            "provider": provider,
            "account": account,
            "subscription": sub.get("subscription") or sub.get("plan"),
            **pool,
        }
        not_this = sub.get("not_this_pool")
        if isinstance(not_this, list) and not_this:
            row["not_this_pool"] = not_this
        rows.append(row)
    return rows


def _extra_credit_rows(subscriptions: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (provider, account), sub in subscriptions.items():
        credits = sub.get("extra_credits")
        if not isinstance(credits, dict) or credits.get("balance_usd") is None:
            continue
        rows.append(
            {
                "provider": provider,
                "account": account,
                "subscription": sub.get("subscription") or sub.get("plan"),
                **credits,
            }
        )
    return rows


def _provider_charge_confidence(provider: str, env_markers: list[str]) -> str:
    provider = provider.lower()
    if provider == "claude" and any(
        marker in env_markers
        for marker in ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX")
    ):
        return "api_key_or_cloud_billing_marker_seen"
    if provider == "gemini" and any(
        marker in env_markers for marker in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS")
    ):
        return "api_key_or_cloud_billing_marker_seen"
    if provider in ("codex", "openai") and any(marker in env_markers for marker in ("OPENAI_API_KEY", "CODEX_API_KEY")):
        return "api_key_marker_seen"
    if provider == "grok" and any(marker in env_markers for marker in ("XAI_API_KEY", "GROK_API_KEY")):
        return "api_key_marker_seen"
    return "unverified"


def _provider_charge_note(provider: str, env_markers: list[str]) -> str:
    confidence = _provider_charge_confidence(provider, env_markers)
    if confidence != "unverified":
        return "API or cloud billing environment marker was present in the dashboard daemon environment."
    if provider == "codex":
        return "Codex logs are token burn and plan-limit evidence; API charge status is not inferred."
    if provider == "claude":
        return "Claude logs expose token usage but no actual invoice field; subscription and API-credit billing must be checked in Anthropic."
    if provider == "gemini":
        return "Gemini logs expose token usage; billing depends on the project/API key used."
    if provider == "grok":
        return (
            "Grok Build may stamp costUsdTicks (meter). SuperGrok pool/overage cash is on grok.com "
            "Settings → Usage and billing — not proven by local logs alone."
        )
    return "No billing authority was found in local logs."


def _path_child_after(path: Path, marker: str, *, before: str | None = None) -> str:
    parts = path.parts
    try:
        index = parts.index(marker)
    except ValueError:
        return ""
    child_index = index + 1
    if child_index >= len(parts):
        return ""
    if before and before in parts and child_index >= parts.index(before):
        return ""
    return parts[child_index]


def _decode_project_label(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return "unknown"
    if cleaned.startswith("-"):
        cleaned = cleaned[1:]
    cleaned = cleaned.replace("---", "/").replace("--", "/").replace("-", "/")
    parts = [part for part in cleaned.split("/") if part]
    return parts[-1] if parts else value
