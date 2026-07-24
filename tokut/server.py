from __future__ import annotations

import argparse
import json
import mimetypes
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__
from .config import config_path, config_path_list, load_config
from .store import TokenBurnStore

ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = Path(__file__).resolve().parent / "site"


class TokenBurnHandler(BaseHTTPRequestHandler):
    store: TokenBurnStore
    poll_seconds: float

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._json({"ok": True, "version": __version__})
            return
        if parsed.path == "/api/snapshot":
            self.store.refresh()
            self._json(self.store.dashboard(filters=_filters_from_query(parsed.query)))
            return
        if parsed.path == "/api/consult":
            self.store.refresh()
            self._json(self.store.consult(filters=_filters_from_query(parsed.query)))
            return
        if parsed.path == "/events":
            self._events(filters=_filters_from_query(parsed.query))
            return
        self._static(parsed.path)

    def _events(self, *, filters: dict[str, list[str]]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        last_version = -1
        try:
            while True:
                self.store.refresh()
                dashboard = self.store.dashboard(filters=filters)
                if dashboard["version"] != last_version:
                    data = json.dumps(dashboard, separators=(",", ":"))
                    self.wfile.write(f"event: snapshot\ndata: {data}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    last_version = dashboard["version"]
                else:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                time.sleep(self.poll_seconds)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _static(self, request_path: str) -> None:
        rel = "index.html" if request_path in ("", "/") else request_path.lstrip("/")
        path = (SITE_DIR / rel).resolve()
        if SITE_DIR.resolve() not in path.parents and path != SITE_DIR.resolve():
            self.send_error(404)
            return
        if not path.exists() or not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def build_server(
    *,
    host: str,
    port: int,
    codex_home: Path,
    codex_roots: list[Path] | None,
    claude_roots: list[Path] | None,
    gemini_roots: list[Path] | None,
    grok_roots: list[Path] | None = None,
    max_files: int,
    max_events: int,
    initial_tail_bytes: int,
    poll_seconds: float,
    local_user: str | None = None,
    pricing_file: Path | None = None,
    subscriptions_file: Path | None = None,
) -> ThreadingHTTPServer:
    store = TokenBurnStore(
        codex_home=codex_home,
        codex_roots=codex_roots,
        claude_roots=claude_roots,
        gemini_roots=gemini_roots,
        grok_roots=grok_roots,
        max_files=max_files,
        max_events=max_events,
        initial_tail_bytes=initial_tail_bytes,
        local_user=local_user,
        pricing_file=pricing_file,
        subscriptions_file=subscriptions_file,
    )
    store.refresh()

    class Handler(TokenBurnHandler):
        pass

    Handler.store = store
    Handler.poll_seconds = poll_seconds
    return ThreadingHTTPServer((host, port), Handler)


def _filters_from_query(query: str) -> dict[str, list[str]]:
    parsed = parse_qs(query, keep_blank_values=False)
    return {key: values for key, values in parsed.items()}


def _resolve_runtime(args: argparse.Namespace) -> dict:
    config = load_config(args.config)
    roots = config.get("roots") if isinstance(config.get("roots"), dict) else {}
    codex_home = args.codex_home.expanduser() if args.codex_home else config_path(config.get("codex_home")) or Path("~/.codex").expanduser()
    codex_roots = [path.expanduser() for path in args.codex_root] if args.codex_root else config_path_list(roots.get("codex"))
    claude_roots = [path.expanduser() for path in args.claude_root] if args.claude_root else config_path_list(roots.get("claude"))
    gemini_roots = [path.expanduser() for path in args.gemini_root] if args.gemini_root else config_path_list(roots.get("gemini"))
    grok_roots = [path.expanduser() for path in args.grok_root] if args.grok_root else config_path_list(roots.get("grok"))
    pricing_file = args.pricing_file.expanduser() if args.pricing_file else config_path(config.get("pricing_file"))
    subscriptions_file = args.subscriptions_file.expanduser() if args.subscriptions_file else config_path(config.get("subscriptions_file"))
    local_user = args.local_user or config.get("local_user")
    max_files = args.max_files if args.max_files is not None else int(config.get("max_files") or 500)
    max_events = args.max_events if args.max_events is not None else int(config.get("max_events") or 10000)
    initial_tail_mb = args.initial_tail_mb if args.initial_tail_mb is not None else int(config.get("initial_tail_mb") or 8)
    poll_seconds = args.poll_seconds if args.poll_seconds is not None else float(config.get("poll_seconds") or 1.0)
    host = args.host or str(config.get("host") or "127.0.0.1")
    port = args.port if args.port is not None else int(config.get("port") or 8765)
    return {
        "host": host,
        "port": port,
        "codex_home": codex_home,
        "codex_roots": codex_roots,
        "claude_roots": claude_roots,
        "gemini_roots": gemini_roots,
        "grok_roots": grok_roots,
        "pricing_file": pricing_file,
        "subscriptions_file": subscriptions_file,
        "local_user": str(local_user) if local_user else None,
        "max_files": max_files,
        "max_events": max_events,
        "initial_tail_bytes": initial_tail_mb * 1024 * 1024,
        "poll_seconds": poll_seconds,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Tokut — local AI burn dashboard and cost consultant.")
    parser.add_argument(
        "command",
        nargs="?",
        default="serve",
        choices=["serve", "consult"],
        help="serve dashboard (default) or print one-shot cost consult JSON",
    )
    parser.add_argument("--config", type=Path, default=None, help="Path to a local Tokut JSON config file.")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--codex-home", type=Path, default=None)
    parser.add_argument("--codex-root", action="append", type=Path, default=None)
    parser.add_argument("--claude-root", action="append", type=Path, default=None)
    parser.add_argument("--gemini-root", action="append", type=Path, default=None)
    parser.add_argument("--grok-root", action="append", type=Path, default=None)
    parser.add_argument("--pricing-file", type=Path, default=None)
    parser.add_argument("--subscriptions-file", type=Path, default=None)
    parser.add_argument("--local-user", default=None)
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--max-events", type=int, default=None)
    parser.add_argument("--initial-tail-mb", type=int, default=None)
    parser.add_argument("--poll-seconds", type=float, default=None)
    args = parser.parse_args()
    runtime = _resolve_runtime(args)

    if args.command == "consult":
        store = TokenBurnStore(
            codex_home=runtime["codex_home"],
            codex_roots=runtime["codex_roots"],
            claude_roots=runtime["claude_roots"],
            gemini_roots=runtime["gemini_roots"],
            grok_roots=runtime["grok_roots"],
            max_files=runtime["max_files"],
            max_events=runtime["max_events"],
            initial_tail_bytes=runtime["initial_tail_bytes"],
            local_user=runtime["local_user"],
            pricing_file=runtime["pricing_file"],
            subscriptions_file=runtime["subscriptions_file"],
        )
        store.refresh()
        print(json.dumps(store.consult(), indent=2))
        return

    server = build_server(
        host=runtime["host"],
        port=runtime["port"],
        codex_home=runtime["codex_home"],
        codex_roots=runtime["codex_roots"],
        claude_roots=runtime["claude_roots"],
        gemini_roots=runtime["gemini_roots"],
        grok_roots=runtime["grok_roots"],
        max_files=runtime["max_files"],
        max_events=runtime["max_events"],
        initial_tail_bytes=runtime["initial_tail_bytes"],
        poll_seconds=runtime["poll_seconds"],
        local_user=runtime["local_user"],
        pricing_file=runtime["pricing_file"],
        subscriptions_file=runtime["subscriptions_file"],
    )
    url = f"http://{runtime['host']}:{runtime['port']}"
    print(f"Tokut dashboard: {url}")
    print(f"Consult API:     {url}/api/consult")
    print("Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
