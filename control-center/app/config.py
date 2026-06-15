"""Load and validate the Control Center configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class BotConfig:
    id: str
    name: str
    command: list[str] | str
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    group: str = "other"
    autorestart: bool = False
    shell: bool = False
    description: str = ""


@dataclass
class AppConfig:
    log_dir: Path
    host: str
    port: int
    bots: list[BotConfig]
    source_path: Path


def _coerce_bot(raw: dict[str, Any]) -> BotConfig:
    missing = [k for k in ("id", "name", "command") if k not in raw]
    if missing:
        raise ValueError(f"bot entry missing required key(s): {', '.join(missing)} -> {raw!r}")
    return BotConfig(
        id=str(raw["id"]),
        name=str(raw["name"]),
        command=raw["command"],
        cwd=raw.get("cwd"),
        env={str(k): str(v) for k, v in (raw.get("env") or {}).items()},
        group=str(raw.get("group", "other")),
        autorestart=bool(raw.get("autorestart", False)),
        shell=bool(raw.get("shell", False)),
        description=str(raw.get("description", "")),
    )


def find_config_path() -> Path:
    """Resolve which config file to load.

    Priority: $CC_CONFIG, then ./config.yaml, then ./config.example.yaml
    (relative to the control-center project root).
    """
    env_path = os.environ.get("CC_CONFIG")
    if env_path:
        return Path(env_path).expanduser().resolve()

    root = Path(__file__).resolve().parent.parent
    for name in ("config.yaml", "config.example.yaml"):
        candidate = root / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "No config found. Create control-center/config.yaml "
        "(copy config.example.yaml) or set $CC_CONFIG."
    )


def load_config(path: Path | None = None) -> AppConfig:
    path = path or find_config_path()
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    bots = [_coerce_bot(b) for b in (data.get("bots") or [])]

    ids = [b.id for b in bots]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate bot id(s) in config: {', '.join(sorted(dupes))}")

    log_dir = Path(data.get("log_dir", "./logs"))
    if not log_dir.is_absolute():
        log_dir = (path.parent / log_dir).resolve()

    return AppConfig(
        log_dir=log_dir,
        host=str(data.get("host", "127.0.0.1")),
        port=int(data.get("port", 8765)),
        bots=bots,
        source_path=path,
    )
