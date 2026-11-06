"""Cross-platform access: live events over plain HTTP (works through the web server's proxy and from phones),
the same authorisation as every API call (revoked tokens get nothing), and a health endpoint for clients."""
import json
import threading

import pytest
from starlette.websockets import WebSocketDisconnect

import app.main as main


def _admin_token(client) -> str:
    return client.headers["Authorization"].split(" ", 1)[1]


def test_event_stream_requires_a_valid_token(client):
    from fastapi.testclient import TestClient

    anon = TestClient(main.app)
    assert anon.get("/api/events/stream").status_code == 401
    assert anon.get("/api/events/stream", headers={"Authorization": "Bearer not.a-token"}).status_code == 401


@pytest.fixture
def live_server(client):
    """A real HTTP server: TestClient buffers whole responses, so an endless event stream needs a socket."""
    import socket
    import time

    import uvicorn

    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        port = sk.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    th.join(timeout=10)


def test_event_stream_delivers_events(client, live_server, monkeypatch):
    import httpx

    monkeypatch.setattr(main, "LIVE_KEEPALIVE_S", 0.2)
    got: list[dict] = []
    h = {"Authorization": client.headers["Authorization"]}

    def trigger():
        httpx.post(f"{live_server}/api/system/kill-switch", json={"engaged": True, "reason": "stream test"}, headers=h, timeout=10)
        httpx.post(f"{live_server}/api/system/kill-switch", json={"engaged": False, "reason": ""}, headers=h, timeout=10)

    with httpx.stream("GET", f"{live_server}/api/events/stream", headers=h, timeout=10) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        t = None
        for line in r.iter_lines():
            if line.startswith(": connected") and t is None:
                t = threading.Thread(target=trigger)
                t.start()
            if line.startswith("data: "):
                got.append(json.loads(line[6:]))
                if any(e.get("type") == "kill_switch" for e in got):
                    break
    t.join()
    assert any(e.get("type") == "kill_switch" for e in got)


def test_revoked_token_gets_no_live_events(client):
    tok = _admin_token(client)
    from fastapi.testclient import TestClient

    other = TestClient(main.app)
    other.headers["Authorization"] = f"Bearer {tok}"
    # a password change revokes every existing session (token_version bump): the old token must get NOTHING live
    r = client.post("/api/auth/password", json={"current_password": "correct-horse-battery", "new_password": "another-horse-battery-9"})
    assert r.status_code == 200, r.text
    assert other.get("/api/events/stream").status_code == 401
    with pytest.raises(WebSocketDisconnect) as e, other.websocket_connect(f"/ws/events?token={tok}") as ws:
        ws.receive_json()
    assert e.value.code == 4401


def test_live_streams_forbid_proxy_transforms(client, live_server):
    """Compression by a proxy buffers a stream until it ends (measured: a 44 s reply arrived in one piece)."""
    import httpx

    h = {"Authorization": client.headers["Authorization"]}
    with httpx.stream("GET", f"{live_server}/api/events/stream", headers=h, timeout=10) as r:
        assert "no-transform" in r.headers["cache-control"]
    from app.ai import llm

    class StreamingFake:
        name = "fake"

        def stream(self, *, system, prompt, tier="standard", max_tokens=16000):
            yield from ["Ex ", "nihilo"]

    llm.set_provider(StreamingFake())
    try:
        with httpx.stream("POST", f"{live_server}/api/gsus/chat/stream", json={"message": "hello", "use_archive": False}, headers=h, timeout=30) as r:
            assert r.status_code == 200 and "no-transform" in r.headers["cache-control"]
            assert "nihilo" in "".join(r.iter_text())
    finally:
        llm.set_provider(None)
