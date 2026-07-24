from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_FILE = Path("~/.config/tokut/config.json").expanduser()
DEFAULT_SUBSCRIPTIONS_FILE = Path("~/.config/tokut/subscriptions.json").expanduser()
DEFAULT_PRICING_FILE = Path("~/.config/tokut/pricing.json").expanduser()


def load_config(path: Path | None = None) -> dict[str, Any]:
    raw = str(path) if path is not None else os.environ.get("TOKUT_CONFIG_FILE")
    config_path = Path(raw).expanduser() if raw else DEFAULT_CONFIG_FILE
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid Tokut config JSON: {config_path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Tokut config must be a JSON object: {config_path}")
    return data


def config_path(value: Any) -> Path | None:
    if value in (None, ""):
        return None
    return Path(str(value)).expanduser()


def config_path_list(value: Any) -> list[Path] | None:
    if value in (None, ""):
        return None
    if not isinstance(value, list):
        value = [value]
    paths = [Path(str(item)).expanduser() for item in value if str(item).strip()]
    return paths or None
