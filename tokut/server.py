from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__
from .config import config_path, config_path_list, load_config
from .keys import DEFAULT_HERMES_ENV, DEFAULT_KEYS_FILE, KeyStore, PROVIDER_CATALOG
from .store import TokenBurnStore

ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = Path(__file__).resolve().parent / "site"


class TokenBurnHandler(BaseHTTPRequestHandler):
    store: TokenBurnStore
    keys: KeyStore
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
        if parsed.path == "/api/keys":
            tenant = (_filters_from_query(parsed.query).get("tenant") or [None])[0]
            self._json(self.keys.payload(tenant))
            return
        if parsed.path == "/api/tenants":
            self._json(self.keys.tenants.snapshot())
            return
        if parsed.path == "/events":
            self._events(filters=_filters_from_query(parsed.query))
            return
        if parsed.path in ("/keys", "/keys/"):
            self._static("/keys.html")
            return
        self._static(parsed.path)

    def do_POST(self) -> None:
        self._mutate("POST")

    def do_PUT(self) -> None:
        self._mutate("PUT")

    def do_DELETE(self) -> None:
        self._mutate("DELETE")

    def _mutate(self, method: str) -> None:
        if not _is_loopback(self.client_address[0]):
            self._json({"ok": False, "error": "keys only accept localhost"}, status=403)
            return
        parsed = urlparse(self.path)
        try:
            body = self._read_json_body()
        except ValueError as exc:
            self._json({"ok": False, "error": str(exc)}, status=400)
            return
        if parsed.path in ("/api/keys", "/api/keys/") and method in {"POST", "PUT"}:
            try:
                public = self.keys.put(
                    provider=str(body.get("provider") or ""),
                    tenant=str(body.get("tenant") or ""),
                    secret=body.get("secret"),
                    label=body.get("label"),
                    env_var=body.get("env_var"),
                    source=str(body.get("source") or "keys-page"),
                )
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
                return
            self._json({"ok": True, "key": public})
            return
        if parsed.path == "/api/keys/import-hermes" and method == "POST":
            result = self.keys.import_env_file()
            self._json({"ok": True, **result, "keys": self.keys.list_public()})
            return
        if parsed.path.startswith("/api/keys/") and method == "DELETE":
            rest = unquote(parsed.path[len("/api/keys/") :].strip("/"))
            if "/" in rest:
                tenant, provider = rest.split("/", 1)
            else:
                tenant = (_filters_from_query(parsed.query).get("tenant") or [""])[0]
                provider = rest
            if not self.keys.delete(provider, tenant=tenant):
                self._json({"ok": False, "error": "key not found"}, status=404)
                return
            self._json({"ok": True, "deleted": f"{tenant}/{provider}", "keys": self.keys.list_public()})
            return
        self._json({"ok": False, "error": "not found"}, status=404)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 65536:
            raise ValueError("body too large")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("invalid JSON") from exc
        if not isinstance(data, dict):
            raise ValueError("JSON object required")
        return data

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
    keys_file: Path | None = None,
    hermes_env: Path | None = None,
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
    Handler.keys = KeyStore(path=keys_file or DEFAULT_KEYS_FILE, hermes_env=hermes_env)
    Handler.poll_seconds = poll_seconds
    return ThreadingHTTPServer((host, port), Handler)


def _is_loopback(host: str) -> bool:
    return host in {"127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1"}


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
    keys_file = args.keys_file.expanduser() if getattr(args, "keys_file", None) else config_path(config.get("keys_file")) or DEFAULT_KEYS_FILE
    hermes_env = args.hermes_env.expanduser() if getattr(args, "hermes_env", None) else config_path(config.get("hermes_env")) or DEFAULT_HERMES_ENV
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
        "keys_file": keys_file,
        "hermes_env": hermes_env,
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
        choices=["serve", "consult", "keys"],
        help="serve dashboard (default), print cost consult JSON, or manage local API keys",
    )
    parser.add_argument("keys_action", nargs="?", default=None, help="keys list | put | delete | import-hermes")
    parser.add_argument("keys_provider", nargs="?", default=None, help="provider id for keys put/delete")
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
    parser.add_argument("--keys-file", type=Path, default=None)
    parser.add_argument("--hermes-env", type=Path, default=None)
    parser.add_argument("--from-env", action="store_true", help="keys put: read secret from the process environment")
    parser.add_argument("--secret-file", type=Path, default=None, help="keys put: read secret from a file (use - for stdin)")
    parser.add_argument("--env-file", type=Path, default=None, help="keys import-hermes: env file to copy from")
    parser.add_argument("--tenant", default=None, help="kai tenant id for keys put/delete/import")
    parser.add_argument("--local-user", default=None)
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--max-events", type=int, default=None)
    parser.add_argument("--initial-tail-mb", type=int, default=None)
    parser.add_argument("--poll-seconds", type=float, default=None)
    args = parser.parse_args()
    runtime = _resolve_runtime(args)

    if args.command == "keys":
        _run_keys_command(args, runtime)
        return

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
        keys_file=runtime["keys_file"],
        hermes_env=runtime["hermes_env"],
    )
    url = f"http://{runtime['host']}:{runtime['port']}"
    print(f"Tokut dashboard: {url}")
    print(f"Keys page:       {url}/keys")
    print(f"Consult API:     {url}/api/consult")
    print("Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _run_keys_command(args: argparse.Namespace, runtime: dict) -> None:
    store = KeyStore(path=runtime["keys_file"], hermes_env=runtime["hermes_env"])
    action = (args.keys_action or "list").strip().lower()
    if action in {"list", "ls"}:
        print(json.dumps(store.payload(), indent=2))
        return
    if action in {"put", "add", "set"}:
        provider = (args.keys_provider or "").strip()
        secret = _secret_from_cli(args, provider)
        public = store.put(
            provider=provider,
            tenant=args.tenant or store.hermes_tenant,
            secret=secret,
            source="cli-from-env" if args.from_env else "cli-secret-file",
        )
        print(json.dumps({"ok": True, "key": public}, indent=2))
        return
    if action in {"delete", "rm", "remove"}:
        provider = (args.keys_provider or "").strip()
        tenant = args.tenant or store.hermes_tenant
        if not store.delete(provider, tenant=tenant):
            raise SystemExit(f"no key stored for {tenant}/{provider}")
        print(json.dumps({"ok": True, "deleted": f"{tenant}/{provider}"}, indent=2))
        return
    if action in {"import-hermes", "import"}:
        result = store.import_env_file(args.env_file, tenant=args.tenant)
        print(json.dumps({"ok": True, **result, "keys": store.list_public()}, indent=2))
        return
    raise SystemExit("keys actions: list | put | delete | import-hermes")


def _secret_from_cli(args: argparse.Namespace, provider: str) -> str:
    if args.secret_file:
        if str(args.secret_file) == "-":
            return sys.stdin.read()
        return Path(args.secret_file).expanduser().read_text(encoding="utf-8")
    if args.from_env:
        catalog = {row["id"]: row["env_var"] for row in PROVIDER_CATALOG}
        env_var = catalog.get(provider.strip().lower())
        if not env_var:
            raise SystemExit("unknown provider; pass --secret-file instead of --from-env")
        value = os.environ.get(env_var, "")
        if not value.strip():
            raise SystemExit(f"{env_var} is not set")
        return value
    raise SystemExit("keys put needs --from-env or --secret-file (do not pass the secret on the command line)")


if __name__ == "__main__":
    main()
