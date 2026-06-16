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
class AuthConfig:
    enabled: bool = False
    # Plaintext password is read from this env var (preferred — keeps it out of
    # the file). Alternatively store a sha256 hex digest of the password here.
    password_env: str = "CC_PASSWORD"
    password_sha256: str | None = None
    # Cookie-signing secret. If unset, read from $CC_SECRET, else a random one
    # is generated per process (restarts then invalidate existing sessions).
    secret: str | None = None
    session_hours: int = 12


@dataclass
class TLSConfig:
    certfile: str | None = None
    keyfile: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.certfile and self.keyfile)


@dataclass
class EmailConfig:
    smtp_host: str
    smtp_port: int = 587
    username_env: str = "CC_SMTP_USER"
    password_env: str = "CC_SMTP_PASS"
    use_tls: bool = True
    sender: str | None = None
    recipients: list[str] = field(default_factory=list)


@dataclass
class AlertsConfig:
    enabled: bool = False
    # Which transitions raise an alert.
    on_crash: bool = True    # exited with a non-zero code (and not stopped by you)
    on_exit: bool = False    # exited cleanly (code 0) on its own
    on_restart: bool = False  # auto-restart kicked in after a death
    # Channels.
    desktop: bool = False                       # macOS notification via osascript
    slack_webhook: str | None = None            # incoming-webhook URL (inline)
    slack_webhook_env: str = "CC_SLACK_WEBHOOK"  # or read it from this env var
    email: EmailConfig | None = None


@dataclass
class AppConfig:
    log_dir: Path
    host: str
    port: int
    bots: list[BotConfig]
    source_path: Path
    auth: AuthConfig
    tls: TLSConfig
    alerts: AlertsConfig


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

    auth_raw = data.get("auth") or {}
    auth = AuthConfig(
        enabled=bool(auth_raw.get("enabled", False)),
        password_env=str(auth_raw.get("password_env", "CC_PASSWORD")),
        password_sha256=(str(auth_raw["password_sha256"]) if auth_raw.get("password_sha256") else None),
        secret=(str(auth_raw["secret"]) if auth_raw.get("secret") else None),
        session_hours=int(auth_raw.get("session_hours", 12)),
    )

    tls_raw = data.get("tls") or {}
    tls = TLSConfig(
        certfile=(str(tls_raw["certfile"]) if tls_raw.get("certfile") else None),
        keyfile=(str(tls_raw["keyfile"]) if tls_raw.get("keyfile") else None),
    )

    alerts_raw = data.get("alerts") or {}
    email_raw = alerts_raw.get("email") or {}
    email = None
    if email_raw.get("smtp_host"):
        email = EmailConfig(
            smtp_host=str(email_raw["smtp_host"]),
            smtp_port=int(email_raw.get("smtp_port", 587)),
            username_env=str(email_raw.get("username_env", "CC_SMTP_USER")),
            password_env=str(email_raw.get("password_env", "CC_SMTP_PASS")),
            use_tls=bool(email_raw.get("use_tls", True)),
            sender=(str(email_raw["sender"]) if email_raw.get("sender") else None),
            recipients=[str(r) for r in (email_raw.get("recipients") or [])],
        )
    alerts = AlertsConfig(
        enabled=bool(alerts_raw.get("enabled", False)),
        on_crash=bool(alerts_raw.get("on_crash", True)),
        on_exit=bool(alerts_raw.get("on_exit", False)),
        on_restart=bool(alerts_raw.get("on_restart", False)),
        desktop=bool(alerts_raw.get("desktop", False)),
        slack_webhook=(str(alerts_raw["slack_webhook"]) if alerts_raw.get("slack_webhook") else None),
        slack_webhook_env=str(alerts_raw.get("slack_webhook_env", "CC_SLACK_WEBHOOK")),
        email=email,
    )

    return AppConfig(
        log_dir=log_dir,
        host=str(data.get("host", "127.0.0.1")),
        port=int(data.get("port", 8765)),
        bots=bots,
        source_path=path,
        auth=auth,
        tls=tls,
        alerts=alerts,
    )
