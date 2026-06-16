"""FastAPI app: serves the dashboard UI and the control/monitoring API."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import auth as auth_mod
from .config import load_config
from .manager import ProcessManager
from .monitoring import system_metrics

STATIC_DIR = Path(__file__).resolve().parent / "static"

config = load_config()
manager = ProcessManager(config)

# Paths reachable without a session (the login page and its assets).
PUBLIC_PATHS = {"/login.html", "/style.css", "/api/login", "/api/logout", "/favicon.ico"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    if config.auth.enabled and auth_mod.configured_password_hash(config.auth) is None:
        raise RuntimeError(
            "auth.enabled is true but no password is set. Set the "
            f"${config.auth.password_env} env var or auth.password_sha256 in config."
        )
    yield
    manager.shutdown()


app = FastAPI(title="Control Center", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def require_auth(request: Request, call_next):
    if not config.auth.enabled:
        return await call_next(request)
    path = request.url.path
    if path in PUBLIC_PATHS:
        return await call_next(request)
    token = request.cookies.get(auth_mod.COOKIE_NAME)
    if auth_mod.check_token(config.auth, token):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": "authentication required"}, status_code=401)
    return RedirectResponse("/login.html", status_code=302)


@app.post("/api/login")
async def login(request: Request):
    body = await request.json()
    password = str(body.get("password", ""))
    if not auth_mod.verify_password(config.auth, password):
        return JSONResponse({"detail": "invalid password"}, status_code=401)
    token = auth_mod.make_token(config.auth)
    resp = JSONResponse({"ok": True})
    resp.set_cookie(
        auth_mod.COOKIE_NAME,
        token,
        max_age=config.auth.session_hours * 3600,
        httponly=True,
        samesite="strict",
        secure=config.tls.enabled,
    )
    return resp


@app.post("/api/logout")
def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth_mod.COOKIE_NAME)
    return resp


@app.get("/api/auth")
def auth_info() -> dict:
    return {"enabled": config.auth.enabled}


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
