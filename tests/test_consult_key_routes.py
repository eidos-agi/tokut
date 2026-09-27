from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tokut.keys import KeyStore
from tokut.store import TokenBurnStore
from tokut.tenants import TenantDirectory

NOW = datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)
SECRET = "sk-or-v1-supersecret9999"
HANDLE = "knox:eidos-or-handle"
INJECT = {
    "dsh_credentials": "~/.dsh/.credentials.yaml",
    "paseo_prims": "paseo-prims",
}


def _keys(tmp_path: Path) -> KeyStore:
    directory = TenantDirectory(
        cache_path=tmp_path / "tenants-cache.json",
        live_loader=lambda: {"items": [{"id": "reeves", "name": "reeves"}, {"id": "eidos", "name": "eidos"}]},
    )
    return KeyStore(
        path=tmp_path / "keys.json",
        hermes_env=tmp_path / "hermes.env",
        tenants=directory,
        hermes_tenant="reeves",
    )


def _burn(tmp_path: Path, key_routes=None) -> TokenBurnStore:
    return TokenBurnStore(
        codex_home=tmp_path / ".codex",
        codex_roots=[],
        claude_roots=[],
        gemini_roots=[],
        grok_roots=[],
        max_files=20,
        key_routes=key_routes,
    )


def test_consult_key_routes_lists_slots_without_secrets(tmp_path: Path) -> None:
    keys = _keys(tmp_path)
    keys.set_ref(
        tenant="eidos",
        provider="openrouter",
        ref=HANDLE,
        openrouter_project="eidos-mgmt",
        openrouter_tag="eidos",
        spend_alias="reeves",
        inject=INJECT,
    )
    keys.put(tenant="reeves", provider="deepseek", secret=SECRET)

    consult = _burn(tmp_path, keys.consult_routes).consult(events=[], now=NOW)
    payload = consult["key_routes"]
    assert payload["count"] == 2
    assert payload["knox_count"] == 1
    routes = {f"{row['tenant']}/{row['provider']}": row for row in payload["routes"]}

    eidos = routes["eidos/openrouter"]
    assert eidos["backend"] == "knox"
    assert eidos["is_knox"] is True
    assert eidos["has_openrouter_project"] is True
    assert eidos["has_openrouter_tag"] is True
    assert eidos["has_spend_alias"] is True
    assert eidos["has_inject"] is True
    assert eidos["openrouter_project"] == "eidos-mgmt"
    assert eidos["spend_alias"] == "reeves"
    assert eidos["inject_planes"] == ["dsh_credentials", "paseo_prims"]

    reeves = routes["reeves/deepseek"]
    assert reeves["backend"] == "inline"
    assert reeves["is_knox"] is False
    assert reeves["has_inject"] is False

    dumped = json.dumps(payload)
    assert SECRET not in dumped
    assert HANDLE not in dumped
    assert "eidos-mgmt" in dumped  # safe public value, not a secret
    assert '"secret"' not in dumped
    # Keys must not invent dollar amounts; consult dollars come from logs only.
    assert "usd" not in dumped.lower()


def test_consult_key_routes_empty_when_not_wired(tmp_path: Path) -> None:
    payload = _burn(tmp_path).consult(events=[], now=NOW)["key_routes"]
    assert payload["routes"] == []
    assert payload["count"] == 0
    assert payload["knox_count"] == 0
    assert "not wired" in str(payload["note"])


def test_consult_key_routes_reports_hermes_drift_without_values(tmp_path: Path) -> None:
    keys = _keys(tmp_path)
    keys.put(tenant="reeves", provider="deepseek", secret=SECRET)
    keys.hermes_env.write_text("DEEPSEEK_API_KEY=sk-ds-different0000\n", encoding="utf-8")

    payload = _burn(tmp_path, keys.consult_routes).consult(events=[], now=NOW)["key_routes"]
    route = payload["routes"][0]
    assert route["hermes_status"] == "drift"
    assert payload["hermes_drift"] == ["reeves/deepseek"]
    assert "drift" in str(payload["note"]).lower()
    dumped = json.dumps(payload)
    assert SECRET not in dumped
    assert "different0000" not in dumped


def test_consult_key_routes_provider_error_is_safe(tmp_path: Path) -> None:
    def boom() -> dict:
        raise RuntimeError("key route failure sk-or-v1-providerboom0000")

    payload = _burn(tmp_path, boom).consult(events=[], now=NOW)["key_routes"]
    assert payload["routes"] == []
    assert "RuntimeError" in str(payload["note"])
    assert "providerboom0000" not in json.dumps(payload)


def test_cli_consult_includes_key_routes_without_secrets(tmp_path: Path) -> None:
    keys = _keys(tmp_path)
    keys.set_ref(
        tenant="eidos",
        provider="openrouter",
        ref=HANDLE,
        openrouter_project="eidos-mgmt",
        openrouter_tag="eidos",
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "run.py"),
            "consult",
            "--config",
            str(tmp_path / "config.json"),
            "--codex-home",
            str(tmp_path / "codex"),
            "--codex-root",
            str(tmp_path / "empty"),
            "--claude-root",
            str(tmp_path / "empty"),
            "--gemini-root",
            str(tmp_path / "empty"),
            "--grok-root",
            str(tmp_path / "empty"),
            "--keys-file",
            str(tmp_path / "keys.json"),
            "--hermes-env",
            str(tmp_path / "hermes.env"),
            "--pricing-file",
            str(tmp_path / "pricing.json"),
            "--subscriptions-file",
            str(tmp_path / "subscriptions.json"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["key_routes"]["count"] == 1
    assert payload["key_routes"]["routes"][0]["backend"] == "knox"
    assert HANDLE not in proc.stdout
    assert "secret" not in proc.stdout
