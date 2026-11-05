from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .agents.catalog import build_orchestrator
from .api.core_routes import router as core_router
from .api.flare_routes import router as flare_router
from .api.routes import router
from .config import get_settings
from .db import SessionLocal, init_db
from .governance.core import bus
from .security.auth import decode_token

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if s.env == "production" and s.secret_key == "dev-insecure-change-me":  # noqa: S105 - guard against the dev default
        raise RuntimeError("SECRET_KEY must be set in production")
    init_db()
    db = SessionLocal()
    try:
        build_orchestrator().sync_agents(db)
    finally:
        db.close()
    loop_task = None
    if s.scheduler_enabled:
        from .services.scheduler import loop

        loop_task = asyncio.create_task(loop(s.scheduler_tick_s))
    yield
    if loop_task:
        loop_task.cancel()


app = FastAPI(title=f"{get_settings().company_name} — {get_settings().platform_name} Commerce Intelligence", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=list(get_settings().cors_origins), allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.include_router(flare_router)
app.include_router(core_router)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",  # the API serves JSON, never active content
    "Cache-Control": "no-store",
}


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    from .security.ratelimit import api_requests

    if request.url.path.startswith("/api/"):
        ip = request.client.host if request.client else "unknown"
        ok, retry = api_requests.hit(f"ip:{ip}", get_settings().api_rate_per_min, 60)
        if not ok:
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429, headers={"Retry-After": str(retry), **SECURITY_HEADERS})
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    return response


@app.get("/health")
def health():
    return {"ok": True}


@app.websocket("/ws/events")
async def events(ws: WebSocket):
    token = ws.query_params.get("token", "")
    try:
        decode_token(token)
    except ValueError:
        await ws.close(code=4401)
        return
    await ws.accept()
    q = bus.subscribe()
    try:
        while True:
            ev = await q.get()
            await ws.send_json(ev)
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(q)
