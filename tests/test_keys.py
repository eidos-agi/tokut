from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tokut.keys import KeyStore, fingerprint, parse_env_file
from tokut.tenants import TenantDirectory, parse_kai_tenants


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


def test_parse_kai_tenants_uses_desk_items() -> None:
    rows = parse_kai_tenants({"ok": True, "source": "live", "items": [{"id": "eidos", "name": "eidos"}, {"id": "gmw"}]})
    assert [row["id"] for row in rows] == ["eidos", "gmw"]


def test_put_list_masks_secret_and_writes_0600(tmp_path: Path) -> None:
    store = _store(tmp_path)
    public = store.put(tenant="reeves", provider="openrouter", secret="sk-or-v1-testdeadbeef")

    assert public["tenant"] == "reeves"
    assert public["provider"] == "openrouter"
    assert public["last4"] == "beef"
    assert public["prefix"] == "sk-or-v1"
    assert public["fp"] == fingerprint("sk-or-v1-testdeadbeef")
    assert public["source"] == "api"
    assert public["present"] is True
    assert "secret" not in public
    payload = json.dumps(store.payload())
    assert "sk-or-v1-testdeadbeef" not in payload
    assert "agent_instructions" in json.loads(payload)

    mode = stat.S_IMODE(store.path.stat().st_mode)
    assert mode == 0o600
    on_disk = json.loads(store.path.read_text(encoding="utf-8"))
    assert on_disk["keys"]["reeves/openrouter"]["secret"] == "sk-or-v1-testdeadbeef"
    assert parse_env_file(store.hermes_env)["OPENROUTER_API_KEY"] == "sk-or-v1-testdeadbeef"


def test_refuses_unknown_tenant_and_does_not_cross_copy(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.put(tenant="reeves", provider="openrouter", secret="sk-or-reeves-1111")
    try:
        store.put(tenant="acme", provider="openrouter", secret="sk-or-acme-2222")
        raise AssertionError("invented tenant")
    except ValueError:
        pass
    store.put(tenant="eidos", provider="openrouter", secret="sk-or-eidos-3333")
    assert store.get_secret("openrouter", tenant="reeves") == "sk-or-reeves-1111"
    assert store.get_secret("openrouter", tenant="eidos") == "sk-or-eidos-3333"
    assert parse_env_file(store.hermes_env)["OPENROUTER_API_KEY"] == "sk-or-reeves-1111"


def test_delete_removes_key_and_hermes_env_line(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.put(tenant="reeves", provider="deepseek", secret="sk-deepseek-aaaa1111")
    store.put(tenant="reeves", provider="openrouter", secret="sk-or-bbbb2222")
    assert store.delete("deepseek", tenant="reeves") is True
    providers = [row["provider"] for row in store.list_public(tenant="reeves")]
    assert providers == ["openrouter"]
    env = parse_env_file(store.hermes_env)
    assert "DEEPSEEK_API_KEY" not in env
    assert env["OPENROUTER_API_KEY"] == "sk-or-bbbb2222"


def test_import_env_copies_known_vars_without_clobbering_same_secret(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENROUTER_API_KEY=sk-or-imported9999\n"
        "DEEPSEEK_API_KEY=sk-ds-imported8888\n"
        "UNRELATED=nope\n",
        encoding="utf-8",
    )
    store = _store(tmp_path)
    first = store.import_env_file(env_file, tenant="reeves")
    assert sorted(first["imported"]) == ["deepseek", "openrouter"]
    assert first["tenant"] == "reeves"
    second = store.import_env_file(env_file, tenant="reeves")
    assert second["imported"] == []
    assert sorted(second["skipped"]) == ["deepseek", "openrouter"]
    assert store.get_secret("openrouter", tenant="reeves") == "sk-or-imported9999"


def test_put_rejects_empty_and_bad_provider(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.put(tenant="reeves", provider="Open Router", secret="abc")
        raise AssertionError("expected bad provider")
    except ValueError:
        pass
    try:
        store.put(tenant="reeves", provider="openrouter", secret="   ")
        raise AssertionError("expected empty secret")
    except ValueError:
        pass


def test_rotation_records_history_without_secret(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.put(tenant="reeves", provider="openrouter", secret="sk-or-old-xxxx1111", source="keys-page")
    public = store.put(tenant="reeves", provider="openrouter", secret="sk-or-new-yyyy2222", source="keys-page")
    assert public["last_event"] == "rotated"
    assert public["rotated_at"]
    assert [row["event"] for row in public["history"]] == ["created", "rotated"]
    assert "sk-or-old" not in json.dumps(public)
    assert "sk-or-new" not in json.dumps(public)
