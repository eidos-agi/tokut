"""Optional slot metadata for the tenant AI-keys system of record.

Refs and these fields are not secrets. Inject values are plane-path
placeholders. This module does not read Knox or write credential files.
"""

from __future__ import annotations

import re
from typing import Any, Callable

_SECRET_PREFIXES = (
    "sk-or-v1-",
    "sk-or-",
    "sk-ant-",
    "nvapi-",
    "xai-",
    "sk-",
)
_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,80}$")
_TENANT_RE = re.compile(r"^[a-z][a-z0-9_-]{1,40}$")
_INJECT_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
_INJECT_VALUE_RE = re.compile(r"^[A-Za-z0-9_~./:@+-]{1,160}$")

SLOT_META_FIELDS = ("openrouter_project", "openrouter_tag", "spend_alias")

# Documented paths only. KeyStore does not create or write these files.
INJECT_PLANE_PLACEHOLDERS = {
    "dsh_credentials": "~/.dsh/.credentials.yaml",
    "paseo_prims": "paseo-prims",
}

# Not kai tenants and not secret stores. Drop a row once kai lists that id.
PLANNED_INJECT_PLANES: tuple[dict[str, Any], ...] = (
    {
        "id": "prims",
        "name": "Prim Foundation",
        "status": "planned",
        "spend_alias": "eidos",
        "note": "Piggybacks the eidos OpenRouter spend plane. Not a secret store.",
    },
    {
        "id": "ridge",
        "name": "ridge",
        "status": "planned",
        "spend_alias": None,
        "note": "No spend plane until one is named. Not a secret store.",
    },
)


class _UnsetType:
    """Missing CLI/API field. Distinct from null, which clears."""


UNSET = _UnsetType()


def looks_like_secret(value: str) -> bool:
    text = str(value or "")
    if len(text) > 200 or "\n" in text or "\r" in text:
        return True
    for token in re.split(r"[\s=]+", text):
        lowered = token.strip().strip("'\"").lower()
        if not lowered:
            continue
        for prefix in _SECRET_PREFIXES:
            if lowered.startswith(prefix):
                return True
    return False


def safe_slot_meta(record: dict[str, Any]) -> dict[str, Any]:
    """Metadata safe to persist and to return from list, API, and CLI."""
    provider = str(record.get("provider") or "")
    out: dict[str, Any] = {}
    for field in SLOT_META_FIELDS:
        cleaned = _safe_label(record.get(field), field=field, provider=provider)
        if cleaned:
            out[field] = cleaned
    inject = _safe_inject(record.get("inject"))
    if inject:
        out["inject"] = inject
    return out


def slot_metadata(
    *,
    provider: str,
    tenant: str,
    existing: dict[str, Any],
    require_tenant: Callable[[str], str],
    openrouter_project: Any = UNSET,
    openrouter_tag: Any = UNSET,
    spend_alias: Any = UNSET,
    inject: Any = UNSET,
) -> dict[str, Any]:
    record = existing if isinstance(existing, dict) else {}
    current = safe_slot_meta(record)
    project = _overlay(current, "openrouter_project", openrouter_project)
    tag = _overlay(current, "openrouter_tag", openrouter_tag)
    alias = _overlay(current, "spend_alias", spend_alias)
    fields = _openrouter_fields(provider, project, tag, alias, tenant, require_tenant)
    return {**fields, **_inject_field(record, inject)}


def _safe_label(raw: Any, *, field: str, provider: str) -> str | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value or looks_like_secret(value):
        return None
    if provider != "openrouter":
        return None
    pattern = _TENANT_RE if field == "spend_alias" else _LABEL_RE
    if not pattern.match(value):
        return None
    return value


def _safe_inject(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    out: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not _INJECT_KEY_RE.match(key):
            continue
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not text or looks_like_secret(text) or not _INJECT_VALUE_RE.match(text):
            continue
        out[key] = text
    return out or None


def _overlay(current: dict[str, Any], field: str, incoming: Any) -> str | None:
    value = current.get(field) if incoming is UNSET else incoming
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    text = value.strip()
    return text or None


def _openrouter_fields(
    provider: str,
    project: str | None,
    tag: str | None,
    alias: str | None,
    tenant: str,
    require_tenant: Callable[[str], str],
) -> dict[str, str]:
    out: dict[str, str] = {}
    if project:
        _require_openrouter(provider, "openrouter_project")
        out["openrouter_project"] = _require_label(project, "openrouter_project")
    if tag:
        _require_openrouter(provider, "openrouter_tag")
        out["openrouter_tag"] = _require_label(tag, "openrouter_tag")
    if alias:
        _require_openrouter(provider, "spend_alias")
        out["spend_alias"] = _require_alias(alias, tenant, require_tenant)
    return out


def _require_openrouter(provider: str, field: str) -> None:
    if provider != "openrouter":
        raise ValueError(f"{field} belongs on an openrouter slot")


def _require_label(value: str, field: str) -> str:
    if looks_like_secret(value) or not _LABEL_RE.match(value):
        raise ValueError(f"{field} must be a short id, not a secret")
    return value


def _require_alias(value: str, tenant: str, require_tenant: Callable[[str], str]) -> str:
    if looks_like_secret(value) or not _TENANT_RE.match(value):
        raise ValueError("spend_alias must be a kai tenant id, not a secret")
    if value == tenant:
        raise ValueError("spend_alias must name a different kai tenant")
    return require_tenant(value)


def _inject_field(existing: dict[str, Any], inject: Any) -> dict[str, Any]:
    if inject is UNSET:
        kept = _safe_inject(existing.get("inject"))
        return {"inject": kept} if kept else {}
    if inject is None or inject == {}:
        return {}
    return {"inject": _require_inject(inject)}


def _require_inject(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise ValueError("inject must be a JSON object of plane paths")
    out: dict[str, str] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or not _INJECT_KEY_RE.match(key):
            raise ValueError("inject plane names are short lowercase ids")
        if not isinstance(raw, str):
            raise ValueError("inject values are path placeholders, not objects")
        text = raw.strip()
        if looks_like_secret(text) or not _INJECT_VALUE_RE.match(text):
            raise ValueError("inject values must be plane paths, not secrets")
        out[key] = text
    return out
