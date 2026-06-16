"""Send alerts when bots crash/stop. Channels: macOS desktop notification,
Slack incoming webhook, and email (SMTP). Each channel is best-effort and
isolated — one failing channel never blocks the others or the supervisor.
Delivery happens on a background thread so the supervisor loop never stalls."""
from __future__ import annotations

import json
import os
import shutil
import smtplib
import subprocess
import threading
import urllib.request
from email.message import EmailMessage

from .config import AlertsConfig

_EVENT_EMOJI = {"crash": "🔴", "exit": "⚪️", "restart": "🔁", "test": "🛰️"}


class Notifier:
    def __init__(self, cfg: AlertsConfig):
        self.cfg = cfg

    def event_enabled(self, event: str) -> bool:
        if not self.cfg.enabled:
            return False
        return {
            "crash": self.cfg.on_crash,
            "exit": self.cfg.on_exit,
            "restart": self.cfg.on_restart,
            "test": True,
        }.get(event, False)

    def notify_event(self, event: str, status: dict) -> None:
        """Entry point wired to ProcessManager. Filters by config, then sends."""
        if not self.event_enabled(event):
            return
        emoji = _EVENT_EMOJI.get(event, "•")
        name = status.get("name", status.get("id", "bot"))
        subject = f"{emoji} {name}: {event}"
        lines = [f"Bot: {name} ({status.get('id')})", f"Event: {event}"]
        code = status.get("crash_code")
        if code is not None:
            lines.append(f"Exit code: {code}")
        if status.get("restarts"):
            lines.append(f"Restarts: {status['restarts']}")
        if status.get("error"):
            lines.append(f"Error: {status['error']}")
        self.send(subject, "\n".join(lines))

    def send(self, subject: str, body: str) -> None:
        """Fire-and-forget dispatch across all configured channels."""
        if not self.cfg.enabled:
            return
        threading.Thread(
            target=self._dispatch, args=(subject, body), name="cc-notify", daemon=True
        ).start()

    # -- channels ------------------------------------------------------------

    def _dispatch(self, subject: str, body: str) -> None:
        for channel in (self._desktop, self._slack, self._email):
            try:
                channel(subject, body)
            except Exception as exc:  # never let one channel break the others
                print(f"[notifier] {channel.__name__} failed: {exc}")

    def _desktop(self, subject: str, body: str) -> None:
        if not self.cfg.desktop:
            return
        osa = shutil.which("osascript")
        if osa:  # macOS
            first_line = body.splitlines()[0] if body else ""
            script = (
                f'display notification {json.dumps(first_line)} '
                f'with title "Control Center" subtitle {json.dumps(subject)}'
            )
            subprocess.run([osa, "-e", script], check=False, timeout=10)
            return
        notify = shutil.which("notify-send")  # Linux fallback
        if notify:
            subprocess.run([notify, subject, body], check=False, timeout=10)

    def _slack(self, subject: str, body: str) -> None:
        url = self.cfg.slack_webhook or os.environ.get(self.cfg.slack_webhook_env)
        if not url:
            return
        payload = json.dumps({"text": f"*{subject}*\n```{body}```"}).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=10).close()

    def _email(self, subject: str, body: str) -> None:
        ecfg = self.cfg.email
        if not ecfg or not ecfg.recipients:
            return
        user = os.environ.get(ecfg.username_env)
        password = os.environ.get(ecfg.password_env)
        msg = EmailMessage()
        msg["Subject"] = f"[Control Center] {subject}"
        msg["From"] = ecfg.sender or user or "control-center@localhost"
        msg["To"] = ", ".join(ecfg.recipients)
        msg.set_content(body)
        with smtplib.SMTP(ecfg.smtp_host, ecfg.smtp_port, timeout=15) as smtp:
            if ecfg.use_tls:
                smtp.starttls()
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)
