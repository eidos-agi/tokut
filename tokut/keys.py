from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .tenants import DEFAULT_HERMES_TENANT, UNSCOPED, TenantDirectory

DEFAULT_KEYS_FILE = Path("~/.config/tokut/keys.json").expanduser()
DEFAULT_HERMES_ENV = Path("~/.hermes/.env").expanduser()

PROVIDER_CATALOG: list[dict[str, str]] = [
    {"id": "openrouter", "label": "OpenRouter", "env_var": "OPENROUTER_API_KEY", "hint": "sk-or-…"},
    {"id": "deepseek", "label": "DeepSeek", "env_var": "DEEPSEEK_API_KEY", "hint": "sk-…"},
    {"id": "anthropic", "label": "Anthropic", "env_var": "ANTHROPIC_API_KEY", "hint": "sk-ant-…"},
    {"id": "openai", "label": "OpenAI", "env_var": "OPENAI_API_KEY", "hint": "sk-…"},
    {"id": "xai", "label": "xAI", "env_var": "XAI_API_KEY", "hint": "xai-…"},
    {"id": "nvidia", "label": "NVIDIA", "env_var": "NVIDIA_API_KEY", "hint": "nvapi-…"},
]

_PROVIDER_INDEX = {row["id"]: row for row in PROVIDER_CATALOG}
_ENV_TO_PROVIDER = {row["env_var"]: row["id"] for row in PROVIDER_CATALOG}
_PROVIDER_RE = re.compile(r"^[a-z][a-z0-9_-]{1,40}$")
_ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_HISTORY_LIMIT = 8
_WRITE_SOURCES = {
    "keys-page",
    "import-hermes",
    "cli-from-env",
    "cli-secret-file",
    "cli-ref",
    "api",
    "inferred-hermes-env",
    "unknown",
}
_VENDOR_PREFIXES = (
    "sk-or-v1-",
    "sk-or-",
    "sk-ant-",
    "nvapi-",
    "xai-",
    "sk-",
)

BACKEND_INLINE = "inline"
BACKEND_KNOX = "knox"
KNOWN_BACKENDS = frozenset({BACKEND_INLINE, BACKEND_KNOX, "env", "file", "keeper"})
KEYS_FILE_V2 = 2
KEYS_FILE_V3 = 3
_KNOX_REF_RE = re.compile(r"^knox:[A-Za-z0-9._/-]{1,256}$")


def keys_path(raw: str | Path | None = None) -> Path:
    if raw:
        return Path(raw).expanduser()
    env = os.environ.get("TOKUT_KEYS_FILE")
    if env:
        return Path(env).expanduser()
    return DEFAULT_KEYS_FILE


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def mask_secret(secret: str) -> dict[str, Any]:
    value = secret or ""
    last4 = value[-4:] if len(value) >= 4 else "····"
    return {
        "last4": last4,
        "length": len(value),
        "present": bool(value),
        "prefix": vendor_prefix(value),
        "fp": fingerprint(value) if value else None,
    }


def fingerprint(secret: str) -> str:
    digest = hashlib.sha256((secret or "").encode("utf-8")).hexdigest()
    return f"sha256:{digest[:12]}"


def vendor_prefix(secret: str) -> str:
    value = secret or ""
    for prefix in _VENDOR_PREFIXES:
        if value.startswith(prefix):
            return prefix.rstrip("-")
    return ""


class KnoxNeedsUnlock(Exception):
    """Knox CLI missing, locked, or otherwise unable to unwrap a handle."""


def slot_has_material(record: dict[str, Any]) -> bool:
    secret = str(record.get("secret") or "").strip()
    ref = str(record.get("ref") or "").strip()
    return bool(secret or ref)


def infer_backend(record: dict[str, Any]) -> str:
    raw = str(record.get("backend") or "").strip().lower()
    if raw:
        return raw
    ref = str(record.get("ref") or "").strip()
    secret = str(record.get("secret") or "").strip()
    if ref and not secret:
        scheme = ref.split(":", 1)[0].lower() if ":" in ref else ""
        if scheme in KNOWN_BACKENDS and scheme != BACKEND_INLINE:
            return scheme
        if ref.startswith("knox:"):
            return BACKEND_KNOX
        return BACKEND_KNOX
    return BACKEND_INLINE


def normalize_ref(ref: str, backend: str) -> str:
    value = str(ref or "").strip()
    if not value:
        raise ValueError("ref is empty")
    if backend == BACKEND_KNOX:
        if ":" not in value:
            value = f"knox:{value}"
        if not _KNOX_REF_RE.match(value):
            raise ValueError("knox ref must look like knox:<handle>")
        return value
    if ":" not in value:
        value = f"{backend}:{value}"
    return value


def mask_ref_handle(ref: str) -> dict[str, str]:
    value = str(ref or "").strip()
    if not value:
        return {"last4": "····", "display": "", "scheme": ""}
    scheme, _, rest = value.partition(":")
    if not rest:
        rest = scheme
        scheme = ""
    tail = rest.rsplit("/", 1)[-1]
    last4 = tail[-4:] if len(tail) >= 4 else (tail or "····")
    display = f"{scheme}:…{last4}" if scheme else f"…{last4}"
    return {"last4": last4, "display": display, "scheme": scheme}


def default_knox_get(ref: str) -> str:
    knox = shutil.which("knox")
    if not knox:
        raise KnoxNeedsUnlock("knox CLI not available")
    result = subprocess.run(
        [knox, "get", ref],
        check=False,
        capture_output=True,
        text=True,
        timeout=12,
    )
    secret = (result.stdout or "").strip()
    err = (result.stderr or result.stdout or "knox get failed").strip()
    if result.returncode != 0 or not secret:
        raise KnoxNeedsUnlock(err)
    return secret


def display_path(path: str | Path | None) -> str | None:
    if not path:
        return None
    raw = str(path)
    home = str(Path.home())
    if raw.startswith(home + "/") or raw == home:
        return "~" + raw[len(home) :]
    return raw


def public_history(history: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(history, list):
        return rows
    for item in history[-_HISTORY_LIMIT:]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "at": item.get("at"),
                "event": item.get("event"),
                "source": item.get("source"),
                "source_path": display_path(item.get("source_path")),
                "fp": item.get("fp"),
                "last4": item.get("last4"),
                "prefix": item.get("prefix"),
            }
        )
    return rows


AGENT_INSTRUCTIONS = """\
Tokut keys are tenant-scoped vault adapters. Tenants come from kai (`kai tenants` / GET /tenants/api).
Do not invent a sixth tenant. Do not copy secrets across tenants.
- List: GET /api/keys  (optional ?tenant=eidos)
- Add: POST /api/keys  {tenant, provider, secret, label?}  OR  {tenant, provider, backend, ref}
- Delete: DELETE /api/keys/{tenant}/{provider}
- GET never returns the secret. Identity is tenant + provider + backend + masked handle/last4 (+ fingerprint for inline).
- Backends: inline (migrate-only plaintext) and knox (handle only). Knox resolve never writes the secret into keys.json.
- Hermes .env is mirrored only for the laptop tenant (reeves) on inline puts. Other tenants stay in keys.json.
- Provenance: source, source_path, created_at, rotated_at, history, hermes match/drift.
"""


def slot_id(tenant: str, provider: str) -> str:
    return f"{tenant}/{provider}"


def public_record(record: dict[str, Any], *, hermes_env: Path | None = None) -> dict[str, Any]:
    backend = infer_backend(record)
    secret = str(record.get("secret") or "")
    ref = str(record.get("ref") or "")
    env_var = record.get("env_var")
    tenant = record.get("tenant") or UNSCOPED
    extra: dict[str, Any] = {}
    if backend == BACKEND_INLINE:
        masked = mask_secret(secret)
        hermes = hermes_mirror_status(secret, env_var, hermes_env)
    else:
        handle = mask_ref_handle(ref)
        masked = {
            "last4": handle["last4"],
            "length": 0,
            "present": True,
            "prefix": handle["scheme"] or backend,
            "fp": None,
        }
        hermes = {
            "status": "not-synced",
            "env_var": str(env_var or "").strip(),
            "path": display_path(hermes_env),
        }
        extra["ref"] = handle["display"]
    payload = {
        "id": slot_id(str(tenant), str(record.get("provider") or "")),
        "tenant": tenant,
        "provider": record.get("provider"),
        "label": record.get("label") or record.get("provider"),
        "env_var": env_var,
        "backend": backend,
        "created_at": record.get("created_at") or record.get("updated_at"),
        "updated_at": record.get("updated_at"),
        "rotated_at": record.get("rotated_at"),
        "source": record.get("source") or "unknown",
        "source_path": display_path(record.get("source_path")),
        "last_event": record.get("last_event") or "stored",
        "history": public_history(record.get("history")),
        "hermes": hermes,
        **masked,
        **extra,
    }
    if record.get("inject") is not None:
        payload["inject"] = record.get("inject")
    return payload


def hermes_mirror_status(secret: str, env_var: Any, hermes_env: Path | None) -> dict[str, Any]:
    path = display_path(hermes_env)
    var = str(env_var or "").strip()
    if not hermes_env:
        return {"status": "not-synced", "env_var": var, "path": path}
    if not hermes_env.exists() or not var:
        return {"status": "missing", "env_var": var, "path": path}
    values = parse_env_file(hermes_env)
    if var not in values:
        return {"status": "missing", "env_var": var, "path": path}
    if values[var] == secret:
        return {"status": "match", "env_var": var, "path": path}
    return {"status": "drift", "env_var": var, "path": path}


class KeyStore:
    def __init__(
        self,
        path: Path | None = None,
        hermes_env: Path | None = None,
        *,
        tenants: TenantDirectory | None = None,
        hermes_tenant: str = DEFAULT_HERMES_TENANT,
        knox_runner: Callable[[str], str] | None = None,
    ) -> None:
        self.path = keys_path(path)
        self.hermes_env = Path(hermes_env).expanduser() if hermes_env else DEFAULT_HERMES_ENV
        self.tenants = tenants or TenantDirectory()
        self.hermes_tenant = hermes_tenant
        self._knox_runner = knox_runner or default_knox_get

    def list_public(self, tenant: str | None = None) -> list[dict[str, Any]]:
        data = self._load()
        rows = [public_record(item, hermes_env=self.hermes_env) for item in data["keys"].values()]
        if tenant:
            rows = [row for row in rows if row.get("tenant") == tenant]
        rows.sort(key=lambda row: (str(row.get("tenant") or ""), str(row.get("provider") or "")))
        return rows

    def catalog(self, tenant: str | None = None) -> list[dict[str, str]]:
        stored = self._load()["keys"]
        rows = []
        for item in PROVIDER_CATALOG:
            row = dict(item)
            if tenant:
                row["stored"] = slot_id(tenant, item["id"]) in stored
            else:
                row["stored"] = any(
                    rec.get("provider") == item["id"] for rec in stored.values()
                )
            rows.append(row)
        return rows

    def get_secret(self, provider: str, tenant: str | None = None) -> str | None:
        record = self._get_record(provider, tenant=tenant)
        if not record or infer_backend(record) != BACKEND_INLINE:
            return None
        secret = str(record.get("secret") or "").strip()
        return secret or None

    def _get_record(self, provider: str, tenant: str | None = None) -> dict[str, Any] | None:
        pid = _normalize_provider(provider)
        data = self._load()
        tid = tenant or self.hermes_tenant
        record = data["keys"].get(slot_id(tid, pid)) or data["keys"].get(pid)
        return record if isinstance(record, dict) else None

    def set_ref(
        self,
        *,
        provider: str,
        tenant: str,
        ref: str,
        backend: str = BACKEND_KNOX,
        label: str | None = None,
        env_var: str | None = None,
        inject: Any | None = None,
        source: str = "api",
        source_path: str | Path | None = None,
    ) -> dict[str, Any]:
        return self.put(
            provider=provider,
            secret=None,
            tenant=tenant,
            label=label,
            env_var=env_var,
            sync_hermes=False,
            source=source,
            source_path=source_path,
            backend=backend,
            ref=ref,
            inject=inject,
        )

    def resolve(
        self,
        provider: str,
        tenant: str | None = None,
        *,
        allow_cli: bool = True,
    ) -> dict[str, Any]:
        pid = _normalize_provider(provider)
        tid = tenant or self.hermes_tenant
        record = self._get_record(pid, tenant=tid)
        if not record:
            return {"ok": False, "error": "not_found", "tenant": tid, "provider": pid}
        backend = infer_backend(record)
        if backend == BACKEND_INLINE:
            secret = str(record.get("secret") or "").strip()
            if not secret:
                return {"ok": False, "error": "missing_secret", "backend": backend, "tenant": tid, "provider": pid}
            return {"ok": True, "backend": backend, "tenant": tid, "provider": pid, "secret": secret}
        if backend == BACKEND_KNOX:
            return self._resolve_knox(record, tenant=tid, provider=pid, allow_cli=allow_cli)
        return {
            "ok": False,
            "error": "not_implemented_for_daemon",
            "backend": backend,
            "tenant": tid,
            "provider": pid,
        }

    def _resolve_knox(
        self,
        record: dict[str, Any],
        *,
        tenant: str,
        provider: str,
        allow_cli: bool,
    ) -> dict[str, Any]:
        ref = str(record.get("ref") or "").strip()
        handle = mask_ref_handle(ref)["display"]
        base: dict[str, Any] = {
            "ok": False,
            "backend": BACKEND_KNOX,
            "tenant": tenant,
            "provider": provider,
            "ref": handle,
        }
        if not ref:
            return {**base, "error": "missing_ref"}
        if not allow_cli:
            return {**base, "error": "not_implemented_for_daemon"}
        try:
            secret = self._knox_runner(ref)
        except KnoxNeedsUnlock as exc:
            return {**base, "error": "needs_unlock", "detail": str(exc)}
        except Exception as exc:
            return {**base, "error": "needs_unlock", "detail": str(exc)}
        cleaned = str(secret or "").strip()
        if not cleaned:
            return {**base, "error": "needs_unlock", "detail": "knox returned an empty secret"}
        return {
            "ok": True,
            "backend": BACKEND_KNOX,
            "tenant": tenant,
            "provider": provider,
            "ref": handle,
            "secret": cleaned,
        }

    def put(
        self,
        *,
        provider: str,
        secret: str | None,
        tenant: str,
        label: str | None = None,
        env_var: str | None = None,
        sync_hermes: bool | None = None,
        source: str = "api",
        source_path: str | Path | None = None,
        backend: str | None = None,
        ref: str | None = None,
        inject: Any | None = None,
    ) -> dict[str, Any]:
        pid = _normalize_provider(provider)
        tid = self.tenants.require(tenant)
        sid = slot_id(tid, pid)
        data = self._load()
        existing = data["keys"].get(sid, {})
        known = _PROVIDER_INDEX.get(pid)
        resolved_env = (env_var or existing.get("env_var") or (known["env_var"] if known else "")).strip()
        if not known and not resolved_env:
            raise ValueError("Unknown provider needs env_var")
        if resolved_env and not _ENV_RE.match(resolved_env):
            raise ValueError("env_var must look like OPENROUTER_API_KEY")

        incoming_secret = "" if secret is None else str(secret).strip()
        incoming_ref = str(ref or "").strip()
        requested = str(backend or "").strip().lower() or None
        if requested is None:
            if incoming_ref and not incoming_secret:
                requested = infer_backend({"ref": incoming_ref})
            else:
                requested = BACKEND_INLINE
        if requested not in KNOWN_BACKENDS:
            raise ValueError(f"unknown backend {requested!r}")

        now = utc_now()
        origin = _normalize_source(source)
        origin_path = str(source_path) if source_path else existing.get("source_path")
        history = list(existing.get("history") or []) if isinstance(existing.get("history"), list) else []
        resolved_inject = existing.get("inject") if inject is None else inject
        label_value = (label or existing.get("label") or (known["label"] if known else pid)).strip()
        env_value = resolved_env or f"{pid.upper().replace('-', '_')}_API_KEY"

        if requested == BACKEND_INLINE:
            cleaned_secret = incoming_secret or str(existing.get("secret") or "").strip()
            if not cleaned_secret:
                raise ValueError("API key is empty")
            old_secret = str(existing.get("secret") or "").strip()
            created = not old_secret
            rotated = bool(old_secret) and old_secret != cleaned_secret
            event = "created" if created else ("rotated" if rotated else "updated")
            history.append(
                {
                    "at": now,
                    "event": event,
                    "source": origin,
                    "source_path": origin_path,
                    "tenant": tid,
                    "fp": fingerprint(cleaned_secret),
                    "last4": mask_secret(cleaned_secret)["last4"],
                    "prefix": vendor_prefix(cleaned_secret),
                }
            )
            record = {
                "tenant": tid,
                "provider": pid,
                "label": label_value,
                "env_var": env_value,
                "backend": BACKEND_INLINE,
                "secret": cleaned_secret,
                "created_at": existing.get("created_at") or now,
                "updated_at": now,
                "rotated_at": now if rotated else existing.get("rotated_at"),
                "source": origin if created or rotated or not existing.get("source") else existing.get("source"),
                "source_path": origin_path,
                "last_event": event,
                "history": history[-_HISTORY_LIMIT:],
            }
            if resolved_inject is not None:
                record["inject"] = resolved_inject
            data["keys"][sid] = record
            data["updated_at"] = now
            self._save(data)
            should_sync = self.hermes_tenant == tid if sync_hermes is None else sync_hermes
            if should_sync:
                upsert_env_var(self.hermes_env, record["env_var"], cleaned_secret)
            return public_record(record, hermes_env=self.hermes_env)

        cleaned_ref = normalize_ref(incoming_ref or str(existing.get("ref") or ""), requested)
        old_ref = str(existing.get("ref") or "").strip()
        existed = bool(existing)
        rotated = existed and (infer_backend(existing) != requested or old_ref != cleaned_ref)
        event = "created" if not existed else ("rotated" if rotated else "updated")
        handle = mask_ref_handle(cleaned_ref)
        history.append(
            {
                "at": now,
                "event": event,
                "source": origin,
                "source_path": origin_path,
                "tenant": tid,
                "fp": None,
                "last4": handle["last4"],
                "prefix": handle["scheme"] or requested,
            }
        )
        record = {
            "tenant": tid,
            "provider": pid,
            "label": label_value,
            "env_var": env_value,
            "backend": requested,
            "ref": cleaned_ref,
            "created_at": existing.get("created_at") or now,
            "updated_at": now,
            "rotated_at": now if rotated else existing.get("rotated_at"),
            "source": origin if (not existed) or rotated or not existing.get("source") else existing.get("source"),
            "source_path": origin_path,
            "last_event": event,
            "history": history[-_HISTORY_LIMIT:],
        }
        if resolved_inject is not None:
            record["inject"] = resolved_inject
        data["keys"][sid] = record
        data["updated_at"] = now
        self._save(data)
        return public_record(record, hermes_env=self.hermes_env)

    def delete(self, provider: str, tenant: str, *, sync_hermes: bool | None = None) -> bool:
        pid = _normalize_provider(provider)
        tid = str(tenant or "").strip().lower() or UNSCOPED
        sid = slot_id(tid, pid)
        data = self._load()
        record = data["keys"].pop(sid, None)
        if record is None and "/" not in provider:
            record = data["keys"].pop(pid, None)
        if record is None:
            return False
        data["updated_at"] = utc_now()
        self._save(data)
        should_sync = (record.get("tenant") == self.hermes_tenant) if sync_hermes is None else sync_hermes
        if should_sync:
            env_var = str(record.get("env_var") or "").strip()
            if env_var:
                remove_env_var(self.hermes_env, env_var)
        return True

    def import_env_file(self, path: Path | None = None, *, tenant: str | None = None) -> dict[str, Any]:
        env_path = Path(path).expanduser() if path else self.hermes_env
        tid = self.tenants.require(tenant or self.hermes_tenant)
        imported: list[str] = []
        skipped: list[str] = []
        if not env_path.exists():
            return {"imported": imported, "skipped": skipped, "source": str(env_path), "tenant": tid, "missing": True}
        for name, value in parse_env_file(env_path).items():
            provider = _ENV_TO_PROVIDER.get(name)
            if not provider or not value.strip():
                continue
            existing = self._get_record(provider, tenant=tid)
            if existing and infer_backend(existing) != BACKEND_INLINE:
                skipped.append(provider)
                continue
            if self.get_secret(provider, tenant=tid) == value.strip():
                self._stamp_if_unknown(provider, tenant=tid, source="import-hermes", source_path=env_path)
                skipped.append(provider)
                continue
            self.put(
                provider=provider,
                tenant=tid,
                secret=value,
                env_var=name,
                sync_hermes=False,
                source="import-hermes",
                source_path=env_path,
            )
            imported.append(provider)
        return {"imported": imported, "skipped": skipped, "source": str(env_path), "tenant": tid, "missing": False}

    def payload(self, tenant: str | None = None) -> dict[str, Any]:
        self._reconcile_unprovenanced()
        tenants = self.tenants.snapshot()
        return {
            "keys": self.list_public(tenant),
            "providers": self.catalog(tenant),
            "tenants": tenants,
            "hermes_tenant": self.hermes_tenant,
            "path": display_path(self.path),
            "hermes_env": display_path(self.hermes_env),
            "agent_instructions": AGENT_INSTRUCTIONS.strip(),
        }

    def _stamp_if_unknown(self, provider: str, *, tenant: str, source: str, source_path: Path | None) -> None:
        sid = slot_id(tenant, _normalize_provider(provider))
        data = self._load()
        record = data["keys"].get(sid)
        if not record or record.get("source") not in {None, "", "unknown"}:
            return
        now = utc_now()
        record["source"] = _normalize_source(source)
        record["source_path"] = str(source_path) if source_path else record.get("source_path")
        record["created_at"] = record.get("created_at") or record.get("updated_at") or now
        record["last_event"] = record.get("last_event") or "stored"
        record["tenant"] = tenant
        data["updated_at"] = now
        self._save(data)

    def _reconcile_unprovenanced(self) -> None:
        data = self._load()
        changed = False
        env_values = parse_env_file(self.hermes_env) if self.hermes_env.exists() else {}
        now = utc_now()
        for record in data["keys"].values():
            if record.get("created_at"):
                continue
            secret = str(record.get("secret") or "")
            env_var = str(record.get("env_var") or "")
            record["created_at"] = record.get("updated_at") or now
            record["last_event"] = record.get("last_event") or "stored"
            if not record.get("source"):
                if infer_backend(record) == BACKEND_INLINE and env_var and env_values.get(env_var) == secret:
                    record["source"] = "inferred-hermes-env"
                    record["source_path"] = str(self.hermes_env)
                else:
                    record["source"] = "unknown"
            changed = True
        if changed:
            data["updated_at"] = now
            self._save(data)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": KEYS_FILE_V2, "updated_at": None, "keys": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid Tokut keys JSON: {self.path}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"Tokut keys file must be a JSON object: {self.path}")
        raw_keys = data.get("keys") or {}
        keys: dict[str, dict[str, Any]] = {}
        records: list[tuple[str, dict[str, Any]]] = []
        if isinstance(raw_keys, dict):
            records = list(raw_keys.items())
        elif isinstance(raw_keys, list):
            records = [(str(item.get("provider") or ""), item) for item in raw_keys if isinstance(item, dict)]
        for raw_id, record in records:
            if not isinstance(record, dict) or not slot_has_material(record):
                continue
            provider = str(record.get("provider") or raw_id.split("/")[-1] or "").strip()
            tenant = str(record.get("tenant") or "").strip().lower()
            if not tenant:
                if "/" in str(raw_id) and not str(raw_id).startswith("/"):
                    tenant = str(raw_id).split("/", 1)[0]
                else:
                    tenant = self.hermes_tenant
            record = dict(record)
            record["tenant"] = tenant
            record["provider"] = provider
            record["backend"] = infer_backend(record)
            if record["backend"] != BACKEND_INLINE and not str(record.get("secret") or "").strip():
                record.pop("secret", None)
            keys[slot_id(tenant, provider)] = record
        version = _coerce_keys_version(data.get("version"))
        if any(infer_backend(item) != BACKEND_INLINE or item.get("ref") for item in keys.values()):
            version = max(version, KEYS_FILE_V3)
        return {"version": version, "updated_at": data.get("updated_at"), "keys": keys}

    def _save(self, data: dict[str, Any]) -> None:
        persist_keys = {
            sid: _persist_record(record) for sid, record in (data.get("keys") or {}).items()
        }
        has_refs = any(
            infer_backend(record) != BACKEND_INLINE or record.get("ref") for record in persist_keys.values()
        )
        version = KEYS_FILE_V3 if has_refs else KEYS_FILE_V2
        payload = json.dumps(
            {"version": version, "updated_at": data.get("updated_at"), "keys": persist_keys},
            indent=2,
            sort_keys=True,
        )
        _atomic_write(self.path, payload + "\n")


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip("'").strip('"')
        if name:
            values[name] = value
    return values


def upsert_env_var(path: Path, name: str, value: str) -> None:
    if not _ENV_RE.match(name):
        raise ValueError("invalid env var name")
    lines: list[str] = []
    if path.exists():
        replaced = False
        for raw in path.read_text(encoding="utf-8").splitlines():
            stripped = raw.strip()
            check = stripped[7:].strip() if stripped.startswith("export ") else stripped
            if check.startswith(f"{name}="):
                lines.append(f"{name}={value}")
                replaced = True
            else:
                lines.append(raw.rstrip("\n"))
        if not replaced:
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(f"{name}={value}")
    else:
        lines = [f"{name}={value}"]
    _atomic_write(path, "\n".join(lines).rstrip() + "\n")


def remove_env_var(path: Path, name: str) -> None:
    if not path.exists():
        return
    kept: list[str] = []
    changed = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        check = stripped[7:].strip() if stripped.startswith("export ") else stripped
        if check.startswith(f"{name}="):
            changed = True
            continue
        kept.append(raw.rstrip("\n"))
    if changed:
        _atomic_write(path, ("\n".join(kept).rstrip() + "\n") if kept else "")


def _coerce_keys_version(raw: Any) -> int:
    try:
        version = int(raw)
    except (TypeError, ValueError):
        return KEYS_FILE_V2
    return version if version >= KEYS_FILE_V2 else KEYS_FILE_V2


def _persist_record(record: dict[str, Any]) -> dict[str, Any]:
    backend = infer_backend(record)
    out: dict[str, Any] = {
        "backend": backend,
        "created_at": record.get("created_at"),
        "env_var": record.get("env_var"),
        "history": record.get("history"),
        "label": record.get("label"),
        "last_event": record.get("last_event"),
        "provider": record.get("provider"),
        "rotated_at": record.get("rotated_at"),
        "source": record.get("source"),
        "source_path": record.get("source_path"),
        "tenant": record.get("tenant"),
        "updated_at": record.get("updated_at"),
    }
    if record.get("inject") is not None:
        out["inject"] = record.get("inject")
    if backend == BACKEND_INLINE:
        out["secret"] = record.get("secret")
    else:
        out["ref"] = record.get("ref")
    return out


def _normalize_provider(provider: str) -> str:
    pid = str(provider or "").strip().lower()
    if not _PROVIDER_RE.match(pid):
        raise ValueError("provider must be a short lowercase id")
    return pid


def _normalize_source(source: str | None) -> str:
    value = str(source or "unknown").strip().lower()
    if value not in _WRITE_SOURCES:
        return "api"
    return value


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    fd, tmp = tempfile.mkstemp(prefix=".tokut-keys-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
