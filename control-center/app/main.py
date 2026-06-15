"""FastAPI app: serves the dashboard UI and the control/monitoring API."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .config import load_config
from .manager import ProcessManager
from .monitoring import system_metrics

STATIC_DIR = Path(__file__).resolve().parent / "static"

config = load_config()
manager = ProcessManager(config)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    manager.shutdown()


app = FastAPI(title="Control Center", version="0.1.0", lifespan=lifespan)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "config": str(config.source_path), "bots": len(config.bots)}


@app.get("/api/system")
def system() -> dict:
    return system_metrics()


@app.get("/api/bots")
def list_bots() -> dict:
    bots = manager.status_all()
    groups = sorted({b["group"] for b in bots})
    return {"bots": bots, "groups": groups}


@app.get("/api/bots/{bot_id}")
def bot_status(bot_id: str) -> dict:
    try:
        return manager.status(bot_id)
    except KeyError:
        raise HTTPException(404, f"unknown bot: {bot_id}")


@app.post("/api/bots/{bot_id}/start")
def start_bot(bot_id: str) -> dict:
    return _do(manager.start, bot_id)


@app.post("/api/bots/{bot_id}/stop")
def stop_bot(bot_id: str) -> dict:
    return _do(manager.stop, bot_id)


@app.post("/api/bots/{bot_id}/restart")
def restart_bot(bot_id: str) -> dict:
    return _do(manager.restart, bot_id)


@app.post("/api/groups/{group}/start")
def start_group(group: str) -> dict:
    return {"results": manager.start_group(group)}


@app.post("/api/groups/{group}/stop")
def stop_group(group: str) -> dict:
    return {"results": manager.stop_group(group)}


@app.get("/api/bots/{bot_id}/logs", response_class=PlainTextResponse)
def bot_logs(bot_id: str, lines: int = 200) -> str:
    try:
        return manager.tail_log(bot_id, lines=max(1, min(lines, 5000)))
    except KeyError:
        raise HTTPException(404, f"unknown bot: {bot_id}")


def _do(fn, bot_id: str) -> dict:
    try:
        return fn(bot_id)
    except KeyError:
        raise HTTPException(404, f"unknown bot: {bot_id}")
    except Exception as exc:  # surface spawn errors (bad cwd/command) to the UI
        raise HTTPException(500, str(exc))


# Serve the dashboard at "/". Mounted last so /api routes take precedence.
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
