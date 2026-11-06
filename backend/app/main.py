from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import event as sa_event
from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from .agents.catalog import build_orchestrator
from .api.core_routes import router as core_router
from .api.daemon_routes import router as daemon_router
from .api.control_routes import router as control_router
from .api.hyper_routes import router as hyper_router
from .api.flare_routes import router as flare_router
from .api.routes import router
from .api.streaming import STREAM_HEADERS
from .config import get_settings
from .db import SessionLocal, init_db
from .governance.core import bus
from .models import Task
from .security.auth import decode_token

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if s.env == "production" and s.secret_key == "dev-insecure-change-me":  # noqa: S105 - guard against the dev default
        raise RuntimeError("SECRET_KEY must be set in production")
    init_db()
    db = SessionLocal()
    orch = build_orchestrator()
    try:
        orch.sync_agents(db)
        from .daemon import library, prompts, registry_seed

        library.ensure_rows(db)
        prompts.seed(db)
        registry_seed.seed(db)
        from .governance.tool_gateway import ensure_default_grants

        ensure_default_grants(db)
        db.commit()
        rec = orch.recover_interrupted(db)
        queued = db.scalar(select(func.count(Task.id)).where(Task.status == "queued"))
    finally:
        db.close()
    from .daemon import residency, telemetry

    telemetry.start()
    residency.prewarm()
    if queued and os.getenv("RESUME_TASKS_ON_START", "true").lower() == "true":
        logging.getLogger(__name__).info("resuming %s queued task(s) after start (recovered: %s)", queued, rec)
        threading.Thread(target=orch.drain, args=(200,), daemon=True).start()
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
app.include_router(daemon_router)
app.include_router(control_router)
app.include_router(hyper_router)

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
    from .daemon import telemetry
    from .security.ratelimit import api_requests

    if request.url.path.startswith("/api/"):
        ip = request.client.host if request.client else "unknown"
        ok, retry = api_requests.hit(f"ip:{ip}", get_settings().api_rate_per_min, 60)
        if not ok:
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429, headers={"Retry-After": str(retry), **SECURITY_HEADERS})
    counter = [0]
    token = telemetry.sql_count.set(counter)
    t0 = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        telemetry.sql_count.reset(token)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    route = request.scope.get("route")
    # CORS preflights are not application work; the live stream's "latency" is its connection lifetime
    if request.url.path.startswith("/api/") and request.method != "OPTIONS" and request.url.path != "/api/events/stream":
        telemetry.record_request(f"{request.method} {getattr(route, 'path', request.url.path)}", (time.perf_counter() - t0) * 1000,
                                 response.status_code, counter[0], int(response.headers.get("content-length") or 0))
    return response


@sa_event.listens_for(Engine, "before_cursor_execute")
def _count_sql(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001 - SQLAlchemy hook signature
    from .daemon import telemetry

    c = telemetry.sql_count.get()
    if c is not None:
        c[0] += 1


@app.get("/health")
def health():
    return {"ok": True}


def _live_user(token: str) -> bool:
    """Live events need the same checks as every API call: valid signature, user exists and is enabled, token not
    revoked (token_version). A short-lived session — a long-lived stream must not hold a pooled DB connection."""
    from .models import User

    try:
        body = decode_token(token)
    except ValueError:
        return False
    with SessionLocal() as db:
        u = db.get(User, body.get("sub"))
        return bool(u and not u.disabled and body.get("tv", 0) == (u.token_version or 0))


LIVE_KEEPALIVE_S = 15


@app.get("/api/events/stream")
async def events_stream(request: Request):
    """Live agent/system events as a text/event-stream over plain HTTP (works through any HTTP proxy, incl. the web
    server's same-origin proxy and phones on the LAN). The token travels in the Authorization header, not the URL."""
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else ""
    if not token or not await asyncio.to_thread(_live_user, token):
        return JSONResponse({"detail": "invalid or revoked token"}, status_code=401)
    q = bus.subscribe()

    async def gen():
        import json

        try:
            yield "retry: 3000\n: connected\n\n"
            while not await request.is_disconnected():
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=LIVE_KEEPALIVE_S)
                except TimeoutError:
                    yield ": keepalive\n\n"  # keeps proxies and mobile networks from closing an idle connection
                    continue
                yield f"data: {json.dumps(ev, default=str)}\n\n"
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers=STREAM_HEADERS)


@app.websocket("/ws/events")
async def events(ws: WebSocket):
    """Kept for existing clients; the web app uses /api/events/stream (WebSocket upgrades do not pass every proxy)."""
    token = ws.query_params.get("token", "")
    if not await asyncio.to_thread(_live_user, token):
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
