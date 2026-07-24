from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tokut.parser import TokenSnapshot, TokenUsage
from tokut.store import TokenBurnStore


def _event(ts: str, *, total: int, last: int, session_id: str) -> str:
    return json.dumps(
        {
            "timestamp": ts,
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {"total_tokens": total},
                    "last_token_usage": {"total_tokens": last},
                },
                "rate_limits": {"primary": {"used_percent": 10.0}},
            },
        }
    )


def test_store_reads_session_index_and_rolls_window_totals(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    sessions_dir = codex_home / "sessions" / "2026" / "06" / "11"
    sessions_dir.mkdir(parents=True)
    session_id = "019eb720-d2aa-7930-8fd2-fe02116f0798"
    (codex_home / "session_index.jsonl").write_text(
        json.dumps({"id": session_id, "thread_name": "Build live token burn dashboard"}) + "\n",
        encoding="utf-8",
    )
    session_file = sessions_dir / f"rollout-2026-06-11T09-40-42-{session_id}.jsonl"
    session_file.write_text(
        "\n".join(
            [
                _event("2026-06-11T14:00:00.000Z", total=100, last=100, session_id=session_id),
                _event("2026-06-11T14:20:00.000Z", total=175, last=75, session_id=session_id),
                _event("2026-06-11T14:40:00.000Z", total=225, last=50, session_id=session_id),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    store = TokenBurnStore(codex_home=codex_home, claude_roots=[], gemini_roots=[], grok_roots=[], max_files=20)
    store.refresh()
    dashboard = store.dashboard(now=datetime(2026, 6, 11, 14, 45, tzinfo=timezone.utc))

    assert dashboard["current"]["thread_name"] == "Build live token burn dashboard"
    assert dashboard["current"]["total"]["total_tokens"] == 225
    assert dashboard["windows"]["30m"]["total_tokens"] == 125
    assert dashboard["windows"]["1h"]["total_tokens"] == 225
    assert dashboard["providers"][0]["provider"] == "codex"
    assert dashboard["accounts"][0]["account"] == "default"
    assert dashboard["sessions"][0]["thread_name"] == "Build live token burn dashboard"
    assert dashboard["sessions"][0]["burn_1h"] == 225


def test_store_tails_only_new_lines_on_refresh(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    sessions_dir = codex_home / "sessions" / "2026" / "06" / "11"
    sessions_dir.mkdir(parents=True)
    session_id = "019eb720-d2aa-7930-8fd2-fe02116f0798"
    session_file = sessions_dir / f"rollout-2026-06-11T09-40-42-{session_id}.jsonl"
    session_file.write_text(
        _event("2026-06-11T14:00:00.000Z", total=100, last=100, session_id=session_id) + "\n",
        encoding="utf-8",
    )
    store = TokenBurnStore(codex_home=codex_home, claude_roots=[], gemini_roots=[], grok_roots=[], max_files=20)
    store.refresh()

    with session_file.open("a", encoding="utf-8") as handle:
        handle.write(_event("2026-06-11T14:01:00.000Z", total=150, last=50, session_id=session_id) + "\n")
    store.refresh()
    dashboard = store.dashboard(now=datetime(2026, 6, 11, 14, 2, tzinfo=timezone.utc))

    assert dashboard["event_count"] == 2
    assert dashboard["current"]["total"]["total_tokens"] == 150
    assert dashboard["windows"]["5m"]["total_tokens"] == 150


def test_dashboard_filters_and_breakdowns_by_usage_dimensions(tmp_path: Path) -> None:
    store = TokenBurnStore(
        codex_home=tmp_path / ".codex",
        codex_roots=[],
        claude_roots=[],
        gemini_roots=[],
        grok_roots=[],
        max_files=20,
    )
    store._subscriptions = {
        ("claude", "work"): {
            "provider": "claude",
            "account": "work",
            "company": "Example Org",
            "subscription": "Claude Max",
            "plan": "Max",
            "billing_mode": "subscription",
            "actual_cost_policy": "zero_actual",
            "configured": True,
            "notes": "",
        },
        ("gemini", "personal"): {
            "provider": "gemini",
            "account": "personal",
            "company": "Example API Account",
            "subscription": "Gemini API",
            "plan": "API",
            "billing_mode": "api_billed",
            "actual_cost_policy": "theoretical_until_reconciled",
            "configured": True,
            "notes": "",
        },
    }
    store._events = [
        _snapshot(
            "2026-06-11T13:15:00+00:00",
            provider="claude",
            account="work",
            project="cerebro",
            user="local-user",
            session_id="claude-a",
            total=100,
        ),
        _snapshot(
            "2026-06-11T14:05:00+00:00",
            provider="gemini",
            account="personal",
            project="budget",
            user="local-user",
            session_id="gemini-a",
            total=250,
        ),
    ]

    dashboard = store.dashboard(now=datetime(2026, 6, 11, 14, 30, tzinfo=timezone.utc))
    filtered = store.dashboard(
        now=datetime(2026, 6, 11, 14, 30, tzinfo=timezone.utc),
        filters={"provider": "claude", "project": "cerebro", "hour": "13:00"},
    )

    assert dashboard["filters"]["provider"] == ["claude", "gemini"]
    assert dashboard["filters"]["project"] == ["budget", "cerebro"]
    assert dashboard["filters"]["model"] == ["unknown"]
    assert dashboard["filters"]["day"] == ["2026-06-11"]
    assert dashboard["filters"]["hour"] == ["13:00", "14:00"]
    assert dashboard["breakdowns"]["project"][0]["label"] == "budget"
    assert filtered["event_count"] == 1
    assert filtered["total_event_count"] == 2
    assert filtered["windows"]["5h"]["total_tokens"] == 100
    assert filtered["sessions"][0]["account"] == "work"
    assert filtered["sessions"][0]["project"] == "cerebro"
    assert filtered["sessions"][0]["hour"] == "13:00"


def test_dashboard_estimates_cost_by_model_and_minute(tmp_path: Path) -> None:
    store = TokenBurnStore(
        codex_home=tmp_path / ".codex",
        codex_roots=[],
        claude_roots=[],
        gemini_roots=[],
        grok_roots=[],
        max_files=20,
    )
    store._subscriptions = {
        ("claude", "work"): {
            "provider": "claude",
            "account": "work",
            "company": "Example Org",
            "subscription": "Claude Max",
            "plan": "Max",
            "billing_mode": "subscription",
            "actual_cost_policy": "zero_actual",
            "configured": True,
            "notes": "",
        },
        ("gemini", "personal"): {
            "provider": "gemini",
            "account": "personal",
            "company": "Example API Account",
            "subscription": "Gemini API",
            "plan": "API",
            "billing_mode": "api_billed",
            "actual_cost_policy": "theoretical_until_reconciled",
            "configured": True,
            "notes": "",
        },
    }
    store._events = [
        _snapshot(
            "2026-06-11T14:00:05+00:00",
            provider="claude",
            account="work",
            project="cerebro",
            user="local-user",
            session_id="claude-a",
            model="claude-fable-5",
            input_tokens=1_000_000,
            output_tokens=100_000,
        ),
        _snapshot(
            "2026-06-11T14:00:45+00:00",
            provider="claude",
            account="work",
            project="cerebro",
            user="local-user",
            session_id="claude-a",
            model="claude-fable-5",
            input_tokens=500_000,
            output_tokens=50_000,
        ),
        _snapshot(
            "2026-06-11T14:01:05+00:00",
            provider="gemini",
            account="personal",
            project="budget",
            user="local-user",
            session_id="gemini-a",
            model="gemini-3-flash-preview",
            input_tokens=1_000_000,
            output_tokens=100_000,
        ),
    ]

    dashboard = store.dashboard(now=datetime(2026, 6, 11, 14, 2, tzinfo=timezone.utc))
    filtered = store.dashboard(
        now=datetime(2026, 6, 11, 14, 2, tzinfo=timezone.utc),
        filters={"model": "claude-fable-5"},
    )

    assert dashboard["filters"]["model"] == ["claude-fable-5", "gemini-3-flash-preview"]
    assert dashboard["filters"]["company"] == ["Example API Account", "Example Org"]
    assert dashboard["costs"]["estimated_total_usd"] == 23.3
    assert dashboard["costs"]["estimate_basis"] == "api_list_price_equivalent"
    assert dashboard["costs"]["actual_charge_confidence"] == "unverified"
    assert dashboard["billing"]["estimate_basis"] == "api_list_price_equivalent_or_server_ticks"
    assert dashboard["billing"]["actual_charge_confidence"] == "unverified"
    assert dashboard["billing"]["actual_charge_usd"] == 0.8
    assert dashboard["billing"]["paid_api_or_overage_usd"] == 0.8
    assert dashboard["billing"]["subscription_theoretical_usd"] == 22.5
    assert dashboard["billing"]["would_pay_without_subscriptions_usd"] == 23.3
    assert dashboard["billing"]["theoretical_api_equivalent_usd"] == 23.3
    assert dashboard["billing"]["theoretical_minus_actual_usd"] == 22.5
    actual_by_company = {row["company"]: row["actual_charge_usd"] for row in dashboard["subscriptions"]}
    assert actual_by_company["Example Org"] == 0.0
    assert actual_by_company["Example API Account"] == 0.8
    assert dashboard["models"][0]["model"] == "claude-fable-5"
    assert dashboard["models"][0]["estimated_cost_usd"] == 22.5
    actual_by_model = {row["model"]: row["actual_charge_usd"] for row in dashboard["models"]}
    assert actual_by_model["claude-fable-5"] == 0.0
    assert actual_by_model["gemini-3-flash-preview"] == 0.8
    assert dashboard["minute_costs"][0]["minute"] == "2026-06-11T14:01:00+00:00"
    assert dashboard["minute_costs"][0]["estimated_cost_usd"] == 0.8
    assert dashboard["minute_costs"][1]["minute"] == "2026-06-11T14:00:00+00:00"
    assert dashboard["minute_costs"][1]["estimated_cost_usd"] == 22.5
    assert dashboard["minute_model_costs"][0]["model"] == "gemini-3-flash-preview"
    assert [row["minute"] for row in dashboard["mtd_spend"]] == [
        "2026-06-11T14:00:00+00:00",
        "2026-06-11T14:01:00+00:00",
    ]
    assert dashboard["mtd_spend"][0]["mtd_actual_usd"] == 0.0
    assert dashboard["mtd_spend"][0]["mtd_api_equivalent_usd"] == 22.5
    assert dashboard["mtd_spend"][1]["mtd_actual_usd"] == 0.8
    assert dashboard["mtd_spend"][1]["mtd_api_equivalent_usd"] == 23.3
    assert filtered["event_count"] == 2
    assert filtered["breakdowns"]["model"][0]["label"] == "claude / claude-fable-5"
    assert filtered["costs"]["estimated_1h_usd"] == 22.5


def test_store_loads_external_subscription_file(tmp_path: Path) -> None:
    subscriptions_file = tmp_path / "subscriptions.local.json"
    subscriptions_file.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "provider": "claude",
                        "account": "work",
                        "company": "External Example Org",
                        "subscription": "Claude Max",
                        "plan": "Max",
                        "billing_mode": "subscription",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    store = TokenBurnStore(
        codex_home=tmp_path / ".codex",
        codex_roots=[],
        claude_roots=[],
        gemini_roots=[],
        grok_roots=[],
        subscriptions_file=subscriptions_file,
    )
    store._events = [
        _snapshot(
            "2026-06-11T14:00:00+00:00",
            provider="claude",
            account="work",
            project="example",
            user="local-user",
            session_id="claude-a",
            model="claude-fable-5",
            input_tokens=1_000_000,
            output_tokens=100_000,
        )
    ]

    dashboard = store.dashboard(now=datetime(2026, 6, 11, 14, 2, tzinfo=timezone.utc))

    assert dashboard["filters"]["company"] == ["External Example Org"]
    assert dashboard["subscriptions"][0]["actual_charge_usd"] == 0.0
    assert dashboard["models"][0]["actual_charge_usd"] == 0.0


def test_store_loads_external_pricing_file_before_builtin_rates(tmp_path: Path) -> None:
    pricing_file = tmp_path / "pricing.local.json"
    pricing_file.write_text(
        json.dumps(
            {
                "rates": [
                    {
                        "provider": "claude",
                        "model_prefix": "claude-fable",
                        "input_per_million": 1.0,
                        "cached_input_per_million": 0.1,
                        "output_per_million": 2.0,
                        "source": "external_test_rate",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    store = TokenBurnStore(
        codex_home=tmp_path / ".codex",
        codex_roots=[],
        claude_roots=[],
        gemini_roots=[],
        grok_roots=[],
        pricing_file=pricing_file,
    )
    event = _snapshot(
        "2026-06-11T14:00:00+00:00",
        provider="claude",
        account="work",
        project="example",
        user="local-user",
        session_id="claude-a",
        model="claude-fable-5",
        input_tokens=1_000_000,
        output_tokens=100_000,
    )

    cost = store._event_cost(event)

    assert cost["estimated_cost_usd"] == 1.2
    assert cost["pricing_source"] == "external_test_rate"


def test_codex_model_context_drives_openai_pricing(tmp_path: Path) -> None:
    store = TokenBurnStore(
        codex_home=tmp_path / ".codex",
        codex_roots=[],
        claude_roots=[],
        gemini_roots=[],
        grok_roots=[],
        max_files=20,
    )
    path = tmp_path / ".codex" / "sessions" / "2026" / "06" / "11" / "rollout-2026-06-11T10-00-00-019eb720-d2aa-7930-8fd2-fe02116f0798.jsonl"
    store._file_kinds[path] = ("codex", "default")
    store._parse_line(
        json.dumps(
            {
                "timestamp": "2026-06-11T14:00:00Z",
                "type": "turn_context",
                "payload": {"model": "gpt-5.5"},
            }
        ),
        path,
    )
    snapshot = store._parse_line(
        json.dumps(
            {
                "timestamp": "2026-06-11T14:01:00Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {"input_tokens": 1_000_000, "output_tokens": 100_000, "total_tokens": 1_100_000},
                        "last_token_usage": {"input_tokens": 1_000_000, "output_tokens": 100_000, "total_tokens": 1_100_000},
                    },
                },
            }
        ),
        path,
    )

    assert snapshot is not None
    assert snapshot.provider == "codex"
    assert snapshot.model == "gpt-5.5"
    assert store._event_cost(snapshot)["estimated_cost_usd"] == 8.0
    assert store._event_cost(snapshot)["pricing_source"] == "openai_gpt55_standard_short_context_2026_06_11"


def test_codex_openai_pricing_uses_longest_model_prefix(tmp_path: Path) -> None:
    store = TokenBurnStore(
        codex_home=tmp_path / ".codex",
        codex_roots=[],
        claude_roots=[],
        gemini_roots=[],
        grok_roots=[],
        max_files=20,
    )
    event = _snapshot(
        "2026-06-11T14:00:00+00:00",
        provider="codex",
        account="default",
        project="tokut",
        user="local-user",
        session_id="codex-pro",
        model="gpt-5.5-pro",
        input_tokens=1_000_000,
        output_tokens=100_000,
    )

    cost = store._event_cost(event)

    assert cost["estimated_cost_usd"] == 48.0
    assert cost["pricing_source"] == "openai_gpt55_pro_standard_short_context_2026_06_11"


def test_event_cost_uses_server_stamp_over_list_price(tmp_path: Path) -> None:
    store = TokenBurnStore(
        codex_home=tmp_path / ".codex",
        codex_roots=[],
        claude_roots=[],
        gemini_roots=[],
       grok_roots=[],
        max_files=20,
    )
    event = _snapshot(
        "2026-07-24T12:00:00+00:00",
        provider="grok",
        account="default",
        project="app",
        user="local-user",
        session_id="grok-a",
        model="grok-4.5-build",
        input_tokens=1_000_000,
        output_tokens=10_000,
        server_cost_usd=1.25,
        cost_source="server_cost_ticks",
    )

    cost = store._event_cost(event)

    assert cost["estimated_cost_usd"] == 1.25
    assert cost["pricing_source"] == "server_cost_ticks"
    assert cost["priced"] is True


def test_subscription_overage_cap_does_not_inflate_meter(tmp_path: Path) -> None:
    store = TokenBurnStore(
        codex_home=tmp_path / ".codex",
        codex_roots=[],
        claude_roots=[],
        gemini_roots=[],
        grok_roots=[],
        max_files=20,
    )
    store._subscriptions = {
        ("grok", "default"): {
            "provider": "grok",
            "account": "default",
            "company": "Personal",
            "subscription": "SuperGrok",
            "plan": "SuperGrok",
            "billing_mode": "subscription",
            "included": {"allowance_usd": 0.0, "period": "week"},
            "overage": {"mode": "auto_topup", "monthly_cap_usd": 50.0},
            "actual_cost_policy": "zero_actual",
            "configured": True,
            "notes": "",
        }
    }
    store._events = [
        _snapshot(
            "2026-07-10T12:00:00+00:00",
            provider="grok",
            account="default",
            project="app",
            user="local-user",
            session_id="grok-heavy",
            model="grok-4.5-build",
            server_cost_usd=563.0,
            cost_source="server_cost_ticks",
            input_tokens=1000,
            output_tokens=100,
        )
    ]

    dashboard = store.dashboard(now=datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc))
    billing = dashboard["billing"]
    consult = dashboard["consult"]

    assert billing["theoretical_api_equivalent_usd"] == 563.0
    assert billing["plan_credits_usd"] == 563.0
    assert billing["discounted_usage_usd"] == 563.0
    assert billing["metered_usd"] == 0.0
    assert billing["subscription_theoretical_usd"] == 563.0
    assert billing["paid_api_or_overage_usd"] == 0.0
    assert billing["actual_charge_usd"] == 0.0
    assert billing["overage_cap_usd"] == 50.0
    assert billing["cash_exposure_max_usd"] == 50.0
    assert consult["ledgers"]["meter_usd"] == 563.0
    assert consult["ledgers"]["plan_credits_usd"] == 563.0
    assert consult["ledgers"]["cash_exposure_max_usd"] == 50.0
    assert consult["ledgers"]["paid_api_or_overage_usd"] == 0.0
    assert "DR-001" in consult["domain_rules"]
    assert "DR-007" in consult["domain_rules"]


def test_plan_credits_then_metered_overage(tmp_path: Path) -> None:
    """Included allowance is plan credits; burn above is metered cash (capped)."""
    store = TokenBurnStore(
        codex_home=tmp_path / ".codex",
        codex_roots=[],
        claude_roots=[],
        gemini_roots=[],
        grok_roots=[],
        max_files=20,
    )
    store._subscriptions = {
        ("grok", "default"): {
            "provider": "grok",
            "account": "default",
            "company": "Personal",
            "subscription": "SuperGrok",
            "plan": "SuperGrok",
            "billing_mode": "subscription",
            "included": {"allowance_usd": 200.0, "period": "week"},
            "overage": {"mode": "auto_topup", "monthly_cap_usd": 50.0},
            "actual_cost_policy": "zero_actual",
            "configured": True,
            "notes": "",
        }
    }
    store._events = [
        _snapshot(
            "2026-07-10T12:00:00+00:00",
            provider="grok",
            account="default",
            project="app",
            user="local-user",
            session_id="grok-heavy",
            model="grok-4.5-build",
            server_cost_usd=563.0,
            cost_source="server_cost_ticks",
            input_tokens=1000,
            output_tokens=100,
        )
    ]

    billing = store.dashboard(now=datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc))["billing"]

    assert billing["plan_credits_usd"] == 200.0
    assert billing["discounted_usage_usd"] == 200.0
    assert billing["metered_usd"] == 363.0
    assert billing["paid_api_or_overage_usd"] == 50.0
    assert billing["cash_exposure_max_usd"] == 50.0
    assert billing["included_allowance_usd"] == 200.0


def _snapshot(
    ts: str,
    *,
    provider: str,
    account: str,
    project: str,
    user: str,
    session_id: str,
    total: int = 0,
    model: str = "",
    input_tokens: int | None = None,
    output_tokens: int = 0,
    server_cost_usd: float | None = None,
    cost_source: str = "",
) -> TokenSnapshot:
    input_tokens = total if input_tokens is None else input_tokens
    usage = TokenUsage(total_tokens=input_tokens + output_tokens, input_tokens=input_tokens, output_tokens=output_tokens)
    return TokenSnapshot(
        timestamp=datetime.fromisoformat(ts),
        session_id=session_id,
        file_path=f"/tmp/{provider}/{session_id}.jsonl",
        total=usage,
        last=usage,
        model_context_window=None,
        rate_limits={},
        provider=provider,
        account=account,
        project=project,
        user=user,
        model=model,
        total_is_cumulative=False,
        server_cost_usd=server_cost_usd,
        cost_source=cost_source,
    )
