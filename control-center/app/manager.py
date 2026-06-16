"""Process supervisor: starts, stops, monitors, and tails logs for the
configured bots. Each bot runs in its own session (process group) so we can
cleanly signal it and any children it spawns."""
from __future__ import annotations

import os
import shlex
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

import psutil

from .config import AppConfig, BotConfig

# Statuses surfaced to the UI.
RUNNING = "running"
STOPPED = "stopped"
EXITED = "exited"   # ended on its own (non-manual)
CRASHED = "crashed"  # ended with a non-zero code


class ManagedProcess:
    def __init__(self, popen: subprocess.Popen, log_path: Path, log_fh):
        self.popen = popen
        self.log_path = log_path
        self.log_fh = log_fh
        self.started_at = time.time()
        self.manual_stop = False
        self.restarts = 0
        self.last_exit_code: int | None = None
        self.handled = False  # whether the supervisor processed this proc's exit
        # psutil handle for resource sampling (primed lazily).
        self._ps: psutil.Process | None = None

    def is_running(self) -> bool:
        return self.popen.poll() is None

    def ps(self) -> psutil.Process | None:
        if self._ps is None and self.is_running():
            try:
                self._ps = psutil.Process(self.popen.pid)
                self._ps.cpu_percent(None)  # prime; first real read comes later
            except psutil.Error:
                self._ps = None
        return self._ps


class ProcessManager:
    def __init__(
        self,
        config: AppConfig,
        on_event: Callable[[str, dict], None] | None = None,
    ):
        self.config = config
        self.bots: dict[str, BotConfig] = {b.id: b for b in config.bots}
        self.procs: dict[str, ManagedProcess] = {}
        self.log_dir = config.log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        # Called with (event, status_dict) on "crash"/"exit"/"restart" transitions.
        self._on_event = on_event
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._supervisor = threading.Thread(
            target=self._supervise, name="cc-supervisor", daemon=True
        )
        self._supervisor.start()

    # -- lifecycle -----------------------------------------------------------

    def start(self, bot_id: str) -> dict:
        with self._lock:
            cfg = self._require(bot_id)
            existing = self.procs.get(bot_id)
            if existing and existing.is_running():
                return self.status(bot_id)

            log_path = self.log_dir / f"{bot_id}.log"
            log_fh = open(log_path, "ab", buffering=0)
            header = f"\n===== started {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n"
            log_fh.write(header.encode())

            env = os.environ.copy()
            env.update(cfg.env)

            if cfg.shell:
                args: list[str] | str = (
                    cfg.command if isinstance(cfg.command, str) else " ".join(cfg.command)
                )
            else:
                args = cfg.command if isinstance(cfg.command, list) else shlex.split(cfg.command)

            popen = subprocess.Popen(
                args,
                cwd=cfg.cwd or None,
                env=env,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                shell=cfg.shell,
                start_new_session=True,  # own process group for clean signaling
            )
            self.procs[bot_id] = ManagedProcess(popen, log_path, log_fh)
            return self.status(bot_id)

    def stop(self, bot_id: str, timeout: float = 10.0) -> dict:
        with self._lock:
            self._require(bot_id)
            mp = self.procs.get(bot_id)
            if not mp or not mp.is_running():
                return self.status(bot_id)
            mp.manual_stop = True
            pid = mp.popen.pid

        self._signal_group(pid, signal.SIGTERM)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if mp.popen.poll() is not None:
                break
            time.sleep(0.2)
        if mp.popen.poll() is None:
            self._signal_group(pid, signal.SIGKILL)
            try:
                mp.popen.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        with self._lock:
            self._reap(bot_id)
        return self.status(bot_id)

    def restart(self, bot_id: str) -> dict:
        self.stop(bot_id)
        return self.start(bot_id)

    def start_group(self, group: str) -> list[dict]:
        return [self.start(b.id) for b in self.config.bots if b.group == group]

    def stop_group(self, group: str) -> list[dict]:
        return [self.stop(b.id) for b in self.config.bots if b.group == group]

    def shutdown(self) -> None:
        """Stop the supervisor and all running children (used on app exit)."""
        self._stop_event.set()
        for bot_id in list(self.procs):
            try:
                self.stop(bot_id, timeout=5)
            except Exception:
                pass

    # -- introspection -------------------------------------------------------

    def status(self, bot_id: str) -> dict:
        cfg = self._require(bot_id)
        mp = self.procs.get(bot_id)
        base = {
            "id": cfg.id,
            "name": cfg.name,
            "group": cfg.group,
            "description": cfg.description,
            "autorestart": cfg.autorestart,
            "command": cfg.command if isinstance(cfg.command, str) else " ".join(cfg.command),
            "cwd": cfg.cwd,
            "status": STOPPED,
            "pid": None,
            "uptime": None,
            "cpu": None,
            "mem_mb": None,
            "restarts": 0,
            "exit_code": None,
        }
        if mp is None:
            return base

        base["restarts"] = mp.restarts
        base["exit_code"] = mp.last_exit_code
        if mp.is_running():
            base["status"] = RUNNING
            base["pid"] = mp.popen.pid
            base["uptime"] = round(time.time() - mp.started_at, 1)
            ps = mp.ps()
            if ps is not None:
                try:
                    base["cpu"] = round(ps.cpu_percent(None), 1)
                    base["mem_mb"] = round(ps.memory_info().rss / (1024 * 1024), 1)
                except psutil.Error:
                    pass
        else:
            code = mp.last_exit_code
            if mp.manual_stop:
                base["status"] = STOPPED
            elif code in (0, None):
                base["status"] = EXITED
            else:
                base["status"] = CRASHED
        return base

    def status_all(self) -> list[dict]:
        return [self.status(b.id) for b in self.config.bots]

    def tail_log(self, bot_id: str, lines: int = 200) -> str:
        self._require(bot_id)
        log_path = self.log_dir / f"{bot_id}.log"
        if not log_path.exists():
            return ""
        # Read the tail without loading the whole file for big logs.
        with open(log_path, "rb") as fh:
            return "".join(_tail(fh, lines))

    # -- internals -----------------------------------------------------------

    def _require(self, bot_id: str) -> BotConfig:
        cfg = self.bots.get(bot_id)
        if cfg is None:
            raise KeyError(bot_id)
        return cfg

    def _reap(self, bot_id: str) -> None:
        mp = self.procs.get(bot_id)
        if mp is None:
            return
        if mp.popen.poll() is not None:
            mp.last_exit_code = mp.popen.returncode
            try:
                mp.log_fh.close()
            except Exception:
                pass

    @staticmethod
    def _signal_group(pid: int, sig: int) -> None:
        try:
            os.killpg(os.getpgid(pid), sig)
        except (ProcessLookupError, PermissionError):
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass

    def _supervise(self) -> None:
        """Reap dead children and auto-restart those configured for it."""
        while not self._stop_event.is_set():
            with self._lock:
                for bot_id, mp in list(self.procs.items()):
                    if mp.is_running():
                        continue
                    if mp.last_exit_code is None:
                        self._reap(bot_id)
                    # Process each exit exactly once; skip deliberate stops.
                    if mp.manual_stop or mp.handled:
                        continue
                    mp.handled = True
                    code = mp.last_exit_code
                    cfg = self.bots.get(bot_id)
                    if cfg and cfg.autorestart:
                        prev_restarts = mp.restarts
                        try:
                            self.start(bot_id)  # re-registers a fresh proc
                            restarted = self.procs.get(bot_id)
                            if restarted is not None:
                                restarted.restarts = prev_restarts + 1
                            self._emit("restart", bot_id, code)
                        except Exception as exc:
                            # Bad command/cwd: don't let it kill the supervisor.
                            self._emit("crash", bot_id, code, error=str(exc))
                    else:
                        event = "crash" if code not in (0, None) else "exit"
                        self._emit(event, bot_id, code)
            self._stop_event.wait(2.0)

    def _emit(self, event: str, bot_id: str, code: int | None, error: str | None = None) -> None:
        if self._on_event is None:
            return
        try:
            payload = self.status(bot_id)
            payload["event"] = event
            payload["crash_code"] = code
            payload["error"] = error
            self._on_event(event, payload)
        except Exception:
            pass


def _tail(fh, lines: int) -> list[str]:
    """Return the last `lines` lines of a binary file handle as decoded str."""
    block = 4096
    fh.seek(0, os.SEEK_END)
    size = fh.tell()
    data = b""
    while size > 0 and data.count(b"\n") <= lines:
        step = min(block, size)
        size -= step
        fh.seek(size)
        data = fh.read(step) + data
    text = data.decode("utf-8", errors="replace")
    return [l + "\n" for l in text.splitlines()[-lines:]]
