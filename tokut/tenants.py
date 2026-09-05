from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# kai ADR 0001 — locked five stores. Not a sixth. Used only when the live
# kai door cannot be read. Source of truth is still kai.
KAI_ADR_TENANTS = (
    {"id": "eidos", "name": "eidos"},
    {"id": "aic", "name": "aic"},
    {"id": "arp", "name": "arp"},
    {"id": "gmw", "name": "gmw"},
    {"id": "reeves", "name": "reeves"},
)

DEFAULT_CACHE_FILE = Path("~/.config/tokut/tenants-cache.json").expanduser()
DEFAULT_HERMES_TENANT = "reeves"
UNSCOPED = "unscoped"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_kai_tenants(payload: Any) -> list[dict[str, str]]:
    if isinstance(payload, dict):
        items = payload.get("items") or payload.get("tenants") or payload.get("data") or []
    elif isinstance(payload, list):
        items = payload
    else:
        items = []
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, str):
            tid = item.strip().lower()
            name = tid
        elif isinstance(item, dict):
            tid = str(item.get("id") or item.get("slug") or item.get("name") or "").strip().lower()
            name = str(item.get("name") or tid).strip() or tid
        else:
            continue
        if not tid or tid in seen or tid == UNSCOPED:
            continue
        seen.add(tid)
        rows.append({"id": tid, "name": name})
    return rows


class TenantDirectory:
    def __init__(
        self,
        *,
        cache_path: Path | None = None,
        live_loader: Any | None = None,
    ) -> None:
        self.cache_path = Path(cache_path).expanduser() if cache_path else DEFAULT_CACHE_FILE
        self.live_loader = live_loader or load_kai_tenants_live

    def snapshot(self) -> dict[str, Any]:
        live_error = None
        try:
            items = parse_kai_tenants(self.live_loader())
            if items:
                snap = {"source": "kai", "fetched_at": utc_now(), "items": items}
                self._write_cache(snap)
                return snap
        except Exception as exc:
            live_error = str(exc)
        cached = self._read_cache()
        if cached.get("items"):
            cached["live_error"] = live_error
            cached["source"] = cached.get("source") or "kai-cache"
            return cached
        return {
            "source": "kai-adr-0001-fallback",
            "fetched_at": None,
            "live_error": live_error,
            "items": [dict(row) for row in KAI_ADR_TENANTS],
        }

    def ids(self) -> set[str]:
        return {row["id"] for row in self.snapshot()["items"]}

    def require(self, tenant: str) -> str:
        tid = str(tenant or "").strip().lower()
        if tid == UNSCOPED:
            raise ValueError("unscoped is not a kai tenant — pick one kai defines")
        if tid not in self.ids():
            raise ValueError(f"unknown tenant {tid!r}; tenants come from kai")
        return tid

    def _read_cache(self) -> dict[str, Any]:
        if not self.cache_path.exists():
            return {}
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _write_cache(self, snap: dict[str, Any]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
        try:
            os.chmod(self.cache_path, 0o600)
        except OSError:
            pass


def load_kai_tenants_live() -> Any:
    env = os.environ.copy()
    result = subprocess.run(
        ["kai", "tenants", "--json"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=12,
    )
    raw = (result.stdout or "").strip()
    if result.returncode != 0 or not raw:
        err = (result.stderr or result.stdout or "kai tenants failed").strip()
        raise RuntimeError(err)
    return json.loads(raw)
