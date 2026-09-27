from __future__ import annotations

import inspect
import json
import re
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import tokut.keys as keys_mod
from tokut.keys import KeyStore, fingerprint, parse_env_file, safe_error_detail
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
    assert public["backend"] == "inline"
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


def test_v2_plaintext_loads_as_inline_and_resolve_returns_secret(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.path.write_text(
        json.dumps(
            {
                "version": 2,
                "keys": {
                    "reeves/deepseek": {
                        "tenant": "reeves",
                        "provider": "deepseek",
                        "secret": "sk-ds-legacy-aaaa1111",
                        "env_var": "DEEPSEEK_API_KEY",
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    public = store.list_public()[0]
    assert public["backend"] == "inline"
    assert public["last4"] == "1111"
    assert "secret" not in public
    assert store.get_secret("deepseek", tenant="reeves") == "sk-ds-legacy-aaaa1111"
    resolved = store.resolve("deepseek", tenant="reeves")
    assert resolved["ok"] is True
    assert resolved["backend"] == "inline"
    assert resolved["secret"] == "sk-ds-legacy-aaaa1111"
    assert json.loads(store.path.read_text(encoding="utf-8"))["version"] == 2


def test_knox_ref_only_round_trips_without_vanishing(tmp_path: Path) -> None:
    store = _store(tmp_path)
    handle = "knox:bc3fdbe01f704a72"
    store.path.write_text(
        json.dumps(
            {
                "version": 3,
                "keys": {
                    "eidos/deepseek": {
                        "tenant": "eidos",
                        "provider": "deepseek",
                        "backend": "knox",
                        "ref": handle,
                        "env_var": "DEEPSEEK_API_KEY",
                        "label": "DeepSeek",
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    first = store.list_public()
    assert len(first) == 1
    assert first[0]["backend"] == "knox"
    assert first[0]["ref"] == "knox:…4a72"
    assert first[0]["last4"] == "4a72"
    assert first[0]["present"] is True
    assert "secret" not in first[0]
    assert handle not in json.dumps(first)
    assert store.get_secret("deepseek", tenant="eidos") is None

    store.put(tenant="reeves", provider="openrouter", secret="sk-or-v1-testdeadbeef")
    reloaded = KeyStore(
        path=store.path,
        hermes_env=store.hermes_env,
        tenants=store.tenants,
        hermes_tenant=store.hermes_tenant,
    )
    ids = {row["id"] for row in reloaded.list_public()}
    assert ids == {"eidos/deepseek", "reeves/openrouter"}
    on_disk = json.loads(store.path.read_text(encoding="utf-8"))
    assert on_disk["version"] == 3
    knox = on_disk["keys"]["eidos/deepseek"]
    assert knox["backend"] == "knox"
    assert knox["ref"] == handle
    assert "secret" not in knox
    assert "sk-or-v1-testdeadbeef" not in json.dumps(reloaded.payload())


def test_set_ref_stores_knox_handle_without_secret(tmp_path: Path) -> None:
    store = _store(tmp_path)
    public = store.set_ref(
        tenant="eidos",
        provider="deepseek",
        ref="knox:bc3fdbe01f704a72",
        inject={"via": "env"},
    )
    assert public["backend"] == "knox"
    assert public["ref"] == "knox:…4a72"
    assert public["inject"] == {"via": "env"}
    assert "secret" not in public
    payload = store.payload()
    dumped = json.dumps(payload)
    assert all("secret" not in row for row in payload["keys"])
    assert "bc3fdbe01f704a72" not in dumped
    on_disk = json.loads(store.path.read_text(encoding="utf-8"))
    assert on_disk["version"] == 3
    assert "secret" not in on_disk["keys"]["eidos/deepseek"]
    assert on_disk["keys"]["eidos/deepseek"]["ref"] == "knox:bc3fdbe01f704a72"
    assert store.hermes_env.exists() is False


def test_knox_resolve_injected_runner_never_writes_secret_back(tmp_path: Path) -> None:
    def runner(ref: str) -> str:
        assert ref == "knox:bc3fdbe01f704a72"
        return "sk-fake-knox-zzzz9999"

    store = KeyStore(
        path=tmp_path / "keys.json",
        hermes_env=tmp_path / "hermes.env",
        tenants=_store(tmp_path).tenants,
        hermes_tenant="reeves",
        knox_runner=runner,
    )
    store.set_ref(tenant="reeves", provider="nvidia", ref="knox:bc3fdbe01f704a72")
    resolved = store.resolve("nvidia", tenant="reeves")
    assert resolved["ok"] is True
    assert resolved["secret"] == "sk-fake-knox-zzzz9999"
    on_disk = json.loads(store.path.read_text(encoding="utf-8"))
    raw = store.path.read_text(encoding="utf-8")
    assert "secret" not in on_disk["keys"]["reeves/nvidia"]
    assert "sk-fake-knox-zzzz9999" not in raw
    assert store.get_secret("nvidia", tenant="reeves") is None
    denied = store.resolve("nvidia", tenant="reeves", allow_cli=False)
    assert denied["ok"] is False
    assert denied["error"] == "not_implemented_for_daemon"
    assert "sk-fake-knox-zzzz9999" not in store.path.read_text(encoding="utf-8")


def test_knox_resolve_without_runner_returns_use_invoke_recipe(
    tmp_path: Path, monkeypatch: object
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"subprocess must not run: {args}")

    monkeypatch.setattr(subprocess, "run", boom)
    store = _store(tmp_path)
    assert store._knox_runner is None
    store.set_ref(tenant="eidos", provider="deepseek", ref="knox:bc3fdbe01f704a72")
    result = store.resolve("deepseek", tenant="eidos")
    dumped = json.dumps(result)
    assert result["ok"] is False
    assert result["usable"] is False
    assert result["error"] == "use_invoke"
    assert "secret" not in result
    assert result["ref"] == "knox:…4a72"
    assert "knox request" in dumped
    assert "knox approve" in dumped
    assert "knox invoke" in dumped
    assert "--env-var DEEPSEEK_API_KEY" in dumped
    assert "<grant-id>" in dumped
    assert "<record-id>" in dumped
    assert "knox get" not in dumped
    assert "bc3fdbe01f704a72" not in dumped
    source = inspect.getsource(keys_mod)
    assert "subprocess" not in source
    assert "knox get" not in source
    assert not hasattr(keys_mod, "default_knox_get")
    on_disk = json.loads(store.path.read_text(encoding="utf-8"))
    assert "secret" not in on_disk["keys"]["eidos/deepseek"]


def test_public_resolve_inline_masks_secret(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.put(tenant="reeves", provider="openrouter", secret="sk-or-v1-supersecret9999")
    library = store.resolve("openrouter", tenant="reeves")
    assert library["secret"] == "sk-or-v1-supersecret9999"
    report = store.public_resolve("openrouter", tenant="reeves")
    dumped = json.dumps(report)
    assert report["ok"] is True
    assert report["usable"] is True
    assert report["backend"] == "inline"
    assert report["last4"] == "9999"
    assert report["fp"] == fingerprint("sk-or-v1-supersecret9999")
    assert report["present"] is True
    assert report["length"] == len("sk-or-v1-supersecret9999")
    assert "secret" not in report
    assert "supersecret9999" not in dumped
    assert store.slot_check_ok(report) is True


def test_public_resolve_knox_is_use_invoke_even_with_runner(tmp_path: Path) -> None:
    def runner(ref: str) -> str:
        raise AssertionError(f"public_resolve must not unwrap {ref}")

    store = KeyStore(
        path=tmp_path / "keys.json",
        hermes_env=tmp_path / "hermes.env",
        tenants=_store(tmp_path).tenants,
        hermes_tenant="reeves",
        knox_runner=runner,
    )
    store.set_ref(tenant="eidos", provider="deepseek", ref="knox:bc3fdbe01f704a72")
    report = store.public_resolve("deepseek", tenant="eidos")
    dumped = json.dumps(report)
    assert report["ok"] is False
    assert report["usable"] is False
    assert report["error"] == "use_invoke"
    assert report["backend"] == "knox"
    assert report["ref"] == "knox:…4a72"
    assert report["env_var"] == "DEEPSEEK_API_KEY"
    assert report["recipe"]
    assert "secret" not in report
    assert "bc3fdbe01f704a72" not in dumped
    assert "knox get" not in dumped
    assert store.slot_check_ok(report) is True
    missing = store.public_resolve("nvidia", tenant="eidos")
    assert missing["error"] == "not_found"
    assert store.slot_check_ok(missing) is False


def test_import_hermes_does_not_clobber_knox_ref(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=sk-ds-imported8888\n", encoding="utf-8")
    store = _store(tmp_path)
    store.set_ref(tenant="reeves", provider="deepseek", ref="knox:bc3fdbe01f704a72")
    result = store.import_env_file(env_file, tenant="reeves")
    assert result["imported"] == []
    assert result["skipped"] == ["deepseek"]
    on_disk = json.loads(store.path.read_text(encoding="utf-8"))
    assert on_disk["keys"]["reeves/deepseek"]["backend"] == "knox"
    assert "secret" not in on_disk["keys"]["reeves/deepseek"]
    assert store.get_secret("deepseek", tenant="reeves") is None


def test_safe_error_detail_passthrough_and_redaction() -> None:
    assert safe_error_detail(RuntimeError("knox not warm")) == "RuntimeError: knox not warm"
    redacted = safe_error_detail(RuntimeError("token sk-or-v1-secretvalue0000"))
    assert "secretvalue0000" not in redacted
    assert "withheld" in redacted
    handle_redacted = safe_error_detail(RuntimeError("locked knox:bc3fdbe01f704a72"))
    assert "bc3fdbe01f704a72" not in handle_redacted


def test_knox_runner_error_detail_withholds_secret_and_handle(tmp_path: Path) -> None:
    def runner(ref: str) -> str:
        raise RuntimeError(f"unlock failed for {ref} near sk-ant-leakleak0000")

    store = KeyStore(
        path=tmp_path / "keys.json",
        hermes_env=tmp_path / "hermes.env",
        tenants=_store(tmp_path).tenants,
        hermes_tenant="reeves",
        knox_runner=runner,
    )
    store.set_ref(tenant="eidos", provider="deepseek", ref="knox:bc3fdbe01f704a72")
    result = store.resolve("deepseek", tenant="eidos")
    dumped = json.dumps(result)
    assert result["ok"] is False
    assert result["error"] == "needs_unlock"
    assert result["detail"]
    assert "leakleak0000" not in dumped
    assert "bc3fdbe01f704a72" not in dumped
    assert "knox:" not in result["detail"]
    # The public/CLI view never consults the runner at all.
    assert store.public_resolve("deepseek", tenant="eidos")["error"] == "use_invoke"


def test_knox_runner_empty_result_is_needs_unlock_without_secret(tmp_path: Path) -> None:
    store = KeyStore(
        path=tmp_path / "keys.json",
        hermes_env=tmp_path / "hermes.env",
        tenants=_store(tmp_path).tenants,
        hermes_tenant="reeves",
        knox_runner=lambda ref: "   ",
    )
    store.set_ref(tenant="eidos", provider="deepseek", ref="knox:bc3fdbe01f704a72")
    result = store.resolve("deepseek", tenant="eidos")
    assert result["error"] == "needs_unlock"
    assert result["detail"]
    assert result["ok"] is False
    assert "secret" not in result


def test_knox_missing_ref_public_view_never_leaks_stored_secret(tmp_path: Path) -> None:
    """A hand-edited file may keep a secret on a knox slot. Public paths must not."""
    store = _store(tmp_path)
    store.path.write_text(
        json.dumps(
            {
                "version": 3,
                "keys": {
                    "eidos/nvidia": {
                        "tenant": "eidos",
                        "provider": "nvidia",
                        "backend": "knox",
                        "secret": "nvapi-hand-edited-secret0000",
                        "env_var": "NVIDIA_API_KEY",
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    report = store.public_resolve("nvidia", tenant="eidos")
    dumped = json.dumps(report)
    assert report["backend"] == "knox"
    assert report["error"] == "missing_ref"
    assert report["ref"] == ""
    assert "secret" not in report
    assert "hand-edited-secret0000" not in dumped
    assert store.slot_check_ok(report) is False
    assert "hand-edited-secret0000" not in json.dumps(store.list_public())
    assert store.get_secret("nvidia", tenant="eidos") is None
    # The library knox resolve path stays use_invoke/missing_ref too.
    assert store.resolve("nvidia", tenant="eidos")["error"] == "missing_ref"


def test_production_server_never_injects_knox_runner() -> None:
    source = (ROOT / "tokut" / "server.py").read_text(encoding="utf-8")
    assert "knox_runner" not in source
    assert re.search(r"store\.resolve\(", source) is None
    assert "public_resolve" in source

