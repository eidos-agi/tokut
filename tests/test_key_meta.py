from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tokut.key_meta import INJECT_PLANE_PLACEHOLDERS
from tokut.keys import KeyStore
from tokut.tenants import TenantDirectory

DEEPSEEK_REF = "knox:bc3fdbe01f704a72"
OPENROUTER_REF = "knox:eidos-or-handle"
INJECT = {
    "dsh_credentials": "~/.dsh/.credentials.yaml",
    "paseo_prims": "paseo-prims",
}


def _store(tmp_path: Path, items: list[dict[str, str]] | None = None) -> KeyStore:
    directory = TenantDirectory(
        cache_path=tmp_path / "tenants-cache.json",
        live_loader=lambda: {
            "items": items
            or [
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


def test_openrouter_metadata_and_knox_ref_round_trip(tmp_path: Path, monkeypatch: object) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("knox must not be called")

    monkeypatch.setattr(subprocess, "run", boom)
    store = _store(tmp_path)
    public = store.set_ref(
        tenant="eidos",
        provider="openrouter",
        ref=OPENROUTER_REF,
        openrouter_project="eidos-mgmt",
        openrouter_tag="eidos",
        spend_alias="reeves",
        inject=INJECT,
    )
    assert public["backend"] == "knox"
    assert public["ref"] == "knox:…ndle"
    assert public["openrouter_project"] == "eidos-mgmt"
    assert public["openrouter_tag"] == "eidos"
    assert public["spend_alias"] == "reeves"
    assert public["inject"] == INJECT
    assert "secret" not in public
    listed = json.dumps(store.payload())
    assert "eidos-mgmt" in listed
    assert OPENROUTER_REF not in listed
    assert "secret" not in json.loads(listed)["keys"][0]

    kept = store.set_ref(tenant="eidos", provider="openrouter", ref=OPENROUTER_REF)
    assert kept["openrouter_project"] == "eidos-mgmt"
    assert kept["inject"]["paseo_prims"] == "paseo-prims"

    reloaded = KeyStore(path=store.path, hermes_env=store.hermes_env, tenants=store.tenants, hermes_tenant="reeves")
    on_disk = json.loads(reloaded.path.read_text(encoding="utf-8"))
    slot = on_disk["keys"]["eidos/openrouter"]
    assert on_disk["version"] == 3
    assert slot["ref"] == OPENROUTER_REF
    assert slot["spend_alias"] == "reeves"
    assert slot["inject"] == INJECT
    assert "secret" not in slot
    assert store.hermes_env.exists() is False


def test_deepseek_slot_carries_inject_recipe_not_openrouter_fields(tmp_path: Path) -> None:
    store = _store(tmp_path)
    public = store.set_ref(tenant="eidos", provider="deepseek", ref=DEEPSEEK_REF, inject=INJECT)
    assert public["inject"] == INJECT
    resolved = store.resolve("deepseek", tenant="eidos")
    dumped = json.dumps(resolved)
    assert resolved["error"] == "use_invoke"
    assert resolved["inject"] == INJECT
    assert "secret" not in resolved
    assert DEEPSEEK_REF not in dumped
    assert INJECT_PLANE_PLACEHOLDERS["dsh_credentials"] in dumped
    for field, value in (
        ("openrouter_project", "eidos-mgmt"),
        ("spend_alias", "reeves"),
    ):
        try:
            store.set_ref(tenant="eidos", provider="deepseek", ref=DEEPSEEK_REF, **{field: value})
            raise AssertionError(field)
        except ValueError as exc:
            assert "openrouter" in str(exc)


def test_planned_planes_are_not_slots_until_kai_lists_them(tmp_path: Path) -> None:
    store = _store(tmp_path)
    planes = {row["id"]: row for row in store.payload()["planned_inject_planes"]}
    assert planes["prims"]["spend_alias"] == "eidos"
    assert planes["prims"]["status"] == "planned"
    assert planes["ridge"]["spend_alias"] is None
    tenant_ids = {row["id"] for row in store.payload()["tenants"]["items"]}
    assert "prims" not in tenant_ids and "ridge" not in tenant_ids
    try:
        store.set_ref(tenant="prims", provider="deepseek", ref=DEEPSEEK_REF, inject=INJECT)
        raise AssertionError("prims slot")
    except ValueError as exc:
        assert "kai" in str(exc)
    try:
        store.set_ref(
            tenant="eidos",
            provider="openrouter",
            ref=OPENROUTER_REF,
            spend_alias="prims",
            openrouter_project="eidos-mgmt",
        )
        raise AssertionError("prims alias")
    except ValueError as exc:
        assert "prims" in str(exc)


def test_kai_prims_slot_uses_spend_alias_and_drops_planned_row(tmp_path: Path) -> None:
    store = _store(
        tmp_path,
        items=[
            {"id": "prims", "name": "Prim Foundation"},
            {"id": "eidos", "name": "eidos"},
            {"id": "reeves", "name": "reeves"},
        ],
    )
    planned = {row["id"] for row in store.payload()["planned_inject_planes"]}
    assert "prims" not in planned
    assert "ridge" in planned
    public = store.set_ref(
        tenant="prims",
        provider="openrouter",
        ref=OPENROUTER_REF,
        openrouter_project="eidos-mgmt",
        openrouter_tag="prims",
        spend_alias="eidos",
        inject={"paseo_prims": "paseo-prims"},
    )
    assert public["tenant"] == "prims"
    assert public["spend_alias"] == "eidos"
    assert "secret" not in public
    on_disk = json.loads(store.path.read_text(encoding="utf-8"))
    assert "secret" not in on_disk["keys"]["prims/openrouter"]


def test_secret_shaped_metadata_is_rejected_and_redacted(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.set_ref(
            tenant="eidos",
            provider="openrouter",
            ref=OPENROUTER_REF,
            openrouter_project="sk-test-blockedmeta",
        )
        raise AssertionError("secret-shaped project")
    except ValueError:
        pass
    assert not store.path.exists()
    store.path.write_text(
        json.dumps(
            {
                "version": 3,
                "keys": {
                    "eidos/deepseek": {
                        "tenant": "eidos",
                        "provider": "deepseek",
                        "backend": "knox",
                        "ref": DEEPSEEK_REF,
                        "inject": {
                            "dsh_credentials": "~/.dsh/.credentials.yaml",
                            "note": "sk-test-redactme0000",
                        },
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    listed = json.dumps(store.list_public())
    assert "sk-test-redactme0000" not in listed
    assert listed.count("dsh_credentials") == 1
    store.set_ref(tenant="eidos", provider="deepseek", ref=DEEPSEEK_REF)
    raw = store.path.read_text(encoding="utf-8")
    assert "sk-test-redactme0000" not in raw
    assert "dsh_credentials" in raw


def test_public_resolve_surfaces_metadata_without_secrets(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set_ref(
        tenant="eidos",
        provider="openrouter",
        ref=OPENROUTER_REF,
        openrouter_project="eidos-mgmt",
        openrouter_tag="eidos",
        spend_alias="reeves",
        inject=INJECT,
    )
    report = store.public_resolve("openrouter", tenant="eidos")
    dumped = json.dumps(report)
    assert report["error"] == "use_invoke"
    assert report["openrouter_project"] == "eidos-mgmt"
    assert report["openrouter_tag"] == "eidos"
    assert report["spend_alias"] == "reeves"
    assert report["inject"] == INJECT
    assert report["ref"] == "knox:…ndle"
    assert "secret" not in report
    assert OPENROUTER_REF not in dumped
    assert store.slot_check_ok(report) is True

    inline = store.put(
        tenant="reeves",
        provider="openrouter",
        secret="sk-or-v1-supersecret9999",
        openrouter_project="reeves-mgmt",
        openrouter_tag="reeves",
    )
    assert "secret" not in inline
    public = store.public_resolve("openrouter", tenant="reeves")
    assert public["ok"] is True
    assert public["last4"] == "9999"
    assert public["openrouter_project"] == "reeves-mgmt"
    assert public["openrouter_tag"] == "reeves"
    assert "secret" not in public
    assert "supersecret9999" not in json.dumps(public)


def test_cli_resolve_prints_metadata_not_the_ref_or_a_secret(tmp_path: Path) -> None:
    keys = tmp_path / "keys.json"
    hermes = tmp_path / "hermes.env"
    _store(tmp_path).set_ref(
        tenant="eidos",
        provider="openrouter",
        ref=OPENROUTER_REF,
        openrouter_project="eidos-mgmt",
        openrouter_tag="eidos",
        spend_alias="reeves",
        inject=INJECT,
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "run.py"),
            "keys",
            "resolve",
            "openrouter",
            "--tenant",
            "eidos",
            "--keys-file",
            str(keys),
            "--hermes-env",
            str(hermes),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert OPENROUTER_REF not in proc.stdout
    assert report["openrouter_project"] == "eidos-mgmt"
    assert report["spend_alias"] == "reeves"
    assert report["inject"]["paseo_prims"] == "paseo-prims"
    assert "secret" not in report
    assert "sk-" not in proc.stdout


def test_cli_put_prints_metadata_not_the_ref_or_a_secret(tmp_path: Path) -> None:
    keys = tmp_path / "keys.json"
    hermes = tmp_path / "hermes.env"
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "run.py"),
            "keys",
            "put",
            "deepseek",
            "--tenant",
            "eidos",
            "--backend",
            "knox",
            "--ref",
            DEEPSEEK_REF,
            "--inject",
            json.dumps(INJECT),
            "--keys-file",
            str(keys),
            "--hermes-env",
            str(hermes),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert DEEPSEEK_REF not in proc.stdout
    assert "paseo-prims" in proc.stdout
    assert "sk-" not in proc.stdout
    assert hermes.exists() is False
    on_disk = json.loads(keys.read_text(encoding="utf-8"))
    assert on_disk["keys"]["eidos/deepseek"]["ref"] == DEEPSEEK_REF
    assert "secret" not in on_disk["keys"]["eidos/deepseek"]


def test_doc_matches_placeholders_and_has_no_secret_material() -> None:
    text = (ROOT / "docs" / "tenant-ai-keys.md").read_text(encoding="utf-8")
    for key, path in INJECT_PLANE_PLACEHOLDERS.items():
        assert key in text
        assert path in text
    assert "knox:bc3fdbe01f704a72" in text
    assert "spend_alias" in text
    assert "SafePaste" in text
    assert "sk-" not in text
    source = (ROOT / "tokut" / "key_meta.py").read_text(encoding="utf-8")
    assert "subprocess" not in source
    assert "SafePaste" not in source
