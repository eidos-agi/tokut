from __future__ import annotations

import json
import sys
import threading
from http.client import HTTPConnection
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tokut.server import build_server


def _server(tmp_path: Path):
    server = build_server(
        host="127.0.0.1",
        port=0,
        codex_home=tmp_path / "codex",
        codex_roots=[],
        claude_roots=[],
        gemini_roots=[],
        grok_roots=[],
        max_files=1,
        max_events=1,
        initial_tail_bytes=1024,
        poll_seconds=30,
        keys_file=tmp_path / "keys.json",
        hermes_env=tmp_path / "hermes.env",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _request(server, method: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
    conn = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if payload else {}
    conn.request(method, path, body=payload, headers=headers)
    response = conn.getresponse()
    raw = response.read().decode("utf-8")
    conn.close()
    if (response.headers.get("Content-Type") or "").startswith("application/json"):
        return response.status, json.loads(raw)
    return response.status, raw


def test_keys_page_and_masked_crud(tmp_path: Path) -> None:
    server = _server(tmp_path)
    try:
        status, html = _request(server, "GET", "/keys")
        assert status == 200
        assert "Tokut Keys" in html
        assert "Add a key" in html
        assert "For agents" in html

        status, data = _request(
            server,
            "POST",
            "/api/keys",
            {"tenant": "reeves", "provider": "openrouter", "secret": "sk-or-v1-supersecret9999", "source": "keys-page"},
        )
        assert status == 200
        assert data["ok"] is True
        assert data["key"]["last4"] == "9999"
        assert data["key"]["tenant"] == "reeves"
        assert data["key"]["fp"]
        dumped = json.dumps(data)
        assert "supersecret9999" not in dumped
        assert "secret" not in data["key"]

        status, listed = _request(server, "GET", "/api/keys")
        assert status == 200
        assert listed["keys"][0]["provider"] == "openrouter"
        assert listed["tenants"]["items"]
        assert "agent_instructions" in listed
        assert "supersecret9999" not in json.dumps(listed)

        status, deleted = _request(server, "DELETE", "/api/keys/reeves/openrouter")
        assert status == 200
        assert deleted["ok"] is True
        assert deleted["keys"] == []
    finally:
        server.shutdown()
        server.server_close()


def test_keys_api_accepts_knox_ref_and_never_returns_secret(tmp_path: Path) -> None:
    server = _server(tmp_path)
    try:
        status, data = _request(
            server,
            "POST",
            "/api/keys",
            {
                "tenant": "eidos",
                "provider": "deepseek",
                "backend": "knox",
                "ref": "knox:bc3fdbe01f704a72",
                "source": "api",
            },
        )
        assert status == 200
        assert data["ok"] is True
        assert data["key"]["backend"] == "knox"
        assert data["key"]["ref"] == "knox:…4a72"
        assert data["key"]["last4"] == "4a72"
        assert "secret" not in data["key"]
        assert "bc3fdbe01f704a72" not in json.dumps(data)

        status, listed = _request(server, "GET", "/api/keys")
        assert status == 200
        assert listed["keys"][0]["backend"] == "knox"
        dumped = json.dumps(listed)
        assert "secret" not in listed["keys"][0]
        assert all("secret" not in row for row in listed["keys"])
        assert "bc3fdbe01f704a72" not in dumped

        keys_file = tmp_path / "keys.json"
        on_disk = json.loads(keys_file.read_text(encoding="utf-8"))
        assert on_disk["version"] == 3
        assert on_disk["keys"]["eidos/deepseek"]["ref"] == "knox:bc3fdbe01f704a72"
        assert "secret" not in on_disk["keys"]["eidos/deepseek"]
    finally:
        server.shutdown()
        server.server_close()
