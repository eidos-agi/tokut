from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tokut.keys import KeyStore, fingerprint
from tokut.tenants import TenantDirectory


def _store(tmp_path: Path) -> KeyStore:
    directory = TenantDirectory(
        cache_path=tmp_path / "tenants-cache.json",
        live_loader=lambda: {
            "items": [
                {"id": "reeves", "name": "reeves"},
                {"id": "eidos", "name": "eidos"},
            ]
        },
    )
    return KeyStore(
        path=tmp_path / "keys.json",
        hermes_env=tmp_path / "hermes.env",
        tenants=directory,
        hermes_tenant="reeves",
    )


def _run_keys(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "run.py"),
            "keys",
            *args,
            "--keys-file",
            str(tmp_path / "keys.json"),
            "--hermes-env",
            str(tmp_path / "hermes.env"),
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        check=False,
    )


def test_cli_resolve_inline_prints_last4_not_secret(tmp_path: Path) -> None:
    secret = "sk-or-v1-supersecret9999"
    _store(tmp_path).put(tenant="reeves", provider="openrouter", secret=secret)
    result = _run_keys(tmp_path, "resolve", "openrouter", "--tenant", "reeves")
    assert result.returncode == 0, result.stderr
    assert secret not in result.stdout
    assert secret not in result.stderr
    assert "supersecret9999" not in result.stdout
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["usable"] is True
    assert report["backend"] == "inline"
    assert report["last4"] == "9999"
    assert report["fp"] == fingerprint(secret)
    assert "secret" not in report


def test_cli_resolve_knox_is_use_invoke_without_handle(tmp_path: Path) -> None:
    handle = "knox:bc3fdbe01f704a72"
    _store(tmp_path).set_ref(tenant="eidos", provider="deepseek", ref=handle)
    result = _run_keys(tmp_path, "resolve", "deepseek", "--tenant", "eidos")
    assert result.returncode == 0, result.stderr
    assert handle not in result.stdout
    assert "bc3fdbe01f704a72" not in result.stdout
    assert "knox get" not in result.stdout
    report = json.loads(result.stdout)
    assert report["error"] == "use_invoke"
    assert report["backend"] == "knox"
    assert report["usable"] is False
    assert report["ref"] == "knox:…4a72"
    assert report["env_var"] == "DEEPSEEK_API_KEY"
    assert "knox invoke" in json.dumps(report)
    assert "secret" not in report


def test_cli_resolve_check_and_keys_check_exit_codes(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.put(tenant="reeves", provider="openrouter", secret="sk-or-v1-testdeadbeef")
    store.set_ref(tenant="eidos", provider="deepseek", ref="knox:bc3fdbe01f704a72")

    missing = _run_keys(tmp_path, "resolve", "nvidia", "--tenant", "eidos", "--check")
    assert missing.returncode != 0
    assert "sk-or-v1-testdeadbeef" not in missing.stdout
    assert json.loads(missing.stdout)["error"] == "not_found"

    alias_missing = _run_keys(tmp_path, "check", "nvidia", "--tenant", "eidos")
    assert alias_missing.returncode != 0

    inline_ok = _run_keys(tmp_path, "resolve", "openrouter", "--tenant", "reeves", "--check")
    assert inline_ok.returncode == 0, inline_ok.stderr
    assert "testdeadbeef" not in inline_ok.stdout
    assert "secret" not in json.loads(inline_ok.stdout)

    knox_ok = _run_keys(tmp_path, "check", "deepseek", "--tenant", "eidos")
    assert knox_ok.returncode == 0, knox_ok.stderr
    knox_report = json.loads(knox_ok.stdout)
    assert knox_report["error"] == "use_invoke"
    assert knox_report["recipe"]
    assert "bc3fdbe01f704a72" not in knox_ok.stdout
    assert "secret" not in knox_report


def test_cli_resolve_missing_slot_exits_nonzero(tmp_path: Path) -> None:
    result = _run_keys(tmp_path, "resolve", "deepseek", "--tenant", "eidos")
    assert result.returncode != 0
    report = json.loads(result.stdout)
    assert report["error"] == "not_found"
    assert "secret" not in report
