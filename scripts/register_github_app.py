#!/usr/bin/env python3
"""Register Jev as a private GitHub App through GitHub's manifest flow.

This helper is intentionally local and one-shot.  It starts a loopback HTTP
server, serves a form whose only external action is the user's click on
GitHub's app-registration page, and exchanges GitHub's short-lived callback
code for app credentials.  It never prints or stores the callback code,
manifest state, private key, webhook secret, or client secret in logs.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hmac
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import webbrowser


GITHUB_API = "https://api.github.com"
GITHUB_APP_REGISTRATION = "https://github.com/settings/apps/new"
DEFAULT_APP_NAME = "jev-review-thiago-ss"
DEFAULT_OUTPUT_DIR = Path(".local/github-app")
MAX_RESPONSE_BYTES = 2_000_000
MAX_CALLBACK_VALUE = 512
STATE_TTL_SECONDS = 3_600.0
_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?$")
_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{1,512}$")

Transport = Callable[[Request, float], Tuple[int, Mapping[str, str], bytes]]


class RegistrationError(RuntimeError):
    """Safe, user-facing registration failure without response-body secrets."""


@dataclass(frozen=True)
class RegisteredApp:
    app_id: int
    slug: str
    install_url: str
    credentials_path: Path


def build_manifest(*, port: int, name: str = DEFAULT_APP_NAME) -> Dict[str, Any]:
    """Return least-privilege manifest for polling-based PR review."""
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    if not isinstance(name, str) or not name or len(name) > 100:
        raise ValueError("app name must be a non-empty string of at most 100 characters")
    return {
        "name": name,
        "url": "https://github.com/thiago-ss/jev-review",
        "description": "Fail-closed autonomous Jev pull-request review bot",
        "public": False,
        # API-only polling app: omit optional webhook configuration entirely.
        # GitHub rejects loopback webhook URLs even when active is false.
        "redirect_url": "http://127.0.0.1:{}/callback".format(port),
        "default_events": [],
        "default_permissions": {
            "contents": "read",
            "checks": "read",
            "pull_requests": "write",
        },
        "request_oauth_on_install": False,
    }


def _no_redirect_transport(request: Request, timeout: float) -> Tuple[int, Mapping[str, str], bytes]:
    """Perform one bounded HTTPS request; redirects are never followed."""
    opener = build_opener(_NoRedirect())
    try:
        response = opener.open(request, timeout=timeout)
        try:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            headers = dict(response.headers.items())
            status = int(response.status)
        finally:
            response.close()
    except HTTPError as exc:
        # Do not read or expose GitHub's body: it can contain request details.
        raise RegistrationError("GitHub app conversion failed (HTTP {})".format(exc.code)) from None
    except (URLError, OSError, TimeoutError):
        raise RegistrationError("GitHub app conversion request failed") from None
    if len(body) > MAX_RESPONSE_BYTES:
        raise RegistrationError("GitHub app conversion response too large")
    return status, headers, body


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Optional[Request]:
        return None


def _json_object(body: bytes) -> Mapping[str, Any]:
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RegistrationError("GitHub app conversion returned invalid JSON") from None
    if not isinstance(value, Mapping):
        raise RegistrationError("GitHub app conversion returned an invalid object")
    return value


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or len(value) > MAX_CALLBACK_VALUE * 8:
        raise RegistrationError("GitHub app conversion response missing {}".format(field))
    return value


def _credential_record(payload: Mapping[str, Any]) -> Tuple[Dict[str, Any], str]:
    app_id = payload.get("id")
    if isinstance(app_id, bool) or not isinstance(app_id, int) or app_id <= 0:
        raise RegistrationError("GitHub app conversion response has invalid app id")
    slug = _required_string(payload.get("slug"), "app slug").lower()
    if not _SLUG_RE.fullmatch(slug):
        raise RegistrationError("GitHub app conversion response has invalid app slug")
    pem = _required_string(payload.get("pem"), "private key")
    if not pem.startswith("-----BEGIN ") or "PRIVATE KEY" not in pem.split("\n", 1)[0] or not pem.rstrip().endswith("-----"):
        raise RegistrationError("GitHub app conversion response has invalid private key")
    # Keep only fields needed by the runtime.  Unknown response fields never
    # become durable credentials or get echoed to the terminal.
    record: Dict[str, Any] = {
        "schema_version": 1,
        "app_id": app_id,
        "slug": slug,
        "app_url": "https://github.com/apps/{}".format(slug),
        "install_url": "https://github.com/apps/{}/installations/new".format(slug),
        "pem": pem,
    }
    for key in ("client_id", "client_secret", "webhook_secret"):
        value = payload.get(key)
        if value is not None:
            record[key] = _required_string(value, key)
    return record, record["install_url"]


def save_credentials(record: Mapping[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR, *, force: bool = False) -> Path:
    """Atomically save credentials in a private directory and file."""
    output_dir = Path(output_dir)
    if output_dir.exists() and output_dir.is_symlink():
        raise RegistrationError("credential directory may not be a symlink")
    if output_dir.exists() and not output_dir.is_dir():
        raise RegistrationError("credential path is not a directory")
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(str(output_dir), 0o700)
    except OSError:
        raise RegistrationError("cannot create private credential directory") from None
    path = output_dir / "credentials.json"
    if path.is_symlink():
        raise RegistrationError("credential file may not be a symlink")
    if path.exists():
        if not path.is_file():
            raise RegistrationError("credential file path is not a regular file")
        if not force:
            raise RegistrationError("credentials already exist; use --force to replace")
    try:
        fd, temporary = tempfile.mkstemp(prefix=".credentials-", suffix=".tmp", dir=str(output_dir))
        try:
            os.fchmod(fd, 0o600)
            data = json.dumps(dict(record), sort_keys=True, separators=(",", ":")) + "\n"
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, str(path))
            os.chmod(str(path), 0o600)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
    except OSError:
        raise RegistrationError("cannot save private app credentials") from None
    return path


def _preflight_credentials(output_dir: Path, *, force: bool) -> None:
    """Reject an occupied or unsafe destination before any GitHub request."""
    output_dir = Path(output_dir)
    if output_dir.exists() and output_dir.is_symlink():
        raise RegistrationError("credential directory may not be a symlink")
    if output_dir.exists() and not output_dir.is_dir():
        raise RegistrationError("credential path is not a directory")
    path = output_dir / "credentials.json"
    if path.is_symlink():
        raise RegistrationError("credential file may not be a symlink")
    if path.exists():
        if not path.is_file():
            raise RegistrationError("credential file path is not a regular file")
        if not force:
            raise RegistrationError("credentials already exist; use --force to replace")


def convert_manifest(code: str, *, transport: Transport = _no_redirect_transport, timeout: float = 15.0) -> Mapping[str, Any]:
    """Exchange one GitHub manifest code and return validated public/secret data."""
    if not isinstance(code, str) or not _CODE_RE.fullmatch(code):
        raise RegistrationError("invalid GitHub manifest callback code")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        raise ValueError("timeout must be positive")
    path = "/app-manifests/{}/conversions".format(quote(code, safe=""))
    request = Request(
        GITHUB_API + path,
        data=b"",
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "jev-review-github-app-registration",
        },
    )
    status, _headers, body = transport(request, float(timeout))
    if not isinstance(body, bytes) or len(body) > MAX_RESPONSE_BYTES:
        raise RegistrationError("GitHub app conversion response too large")
    if status not in (200, 201):
        raise RegistrationError("GitHub app conversion failed (HTTP {})".format(status))
    payload = _json_object(body)
    record, install_url = _credential_record(payload)
    record["install_url"] = install_url
    return record


class RegistrationSession:
    """Loopback form/callback session with CSRF and origin protections."""

    def __init__(
        self,
        *,
        output_dir: Path = DEFAULT_OUTPUT_DIR,
        force: bool = False,
        transport: Transport = _no_redirect_transport,
        timeout: float = 15.0,
        state_ttl: float = STATE_TTL_SECONDS,
        name: str = DEFAULT_APP_NAME,
        state: Optional[str] = None,
        clock: Callable[[], float] = time.time,
        port: int = 0,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.force = force
        _preflight_credentials(self.output_dir, force=force)
        self.transport = transport
        self.timeout = timeout
        self.state_ttl = state_ttl
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
            raise ValueError("timeout must be positive")
        if not isinstance(state_ttl, (int, float)) or isinstance(state_ttl, bool) or state_ttl <= 0:
            raise ValueError("state_ttl must be positive")
        self.clock = clock
        self.state = state or secrets.token_urlsafe(32)
        if not isinstance(self.state, str) or not 16 <= len(self.state) <= MAX_CALLBACK_VALUE:
            raise ValueError("state must be an unpredictable bounded string")
        self.created_at = clock()
        self.consumed = False
        self._state_lock = threading.Lock()
        self.result: Optional[RegisteredApp] = None
        self.error: Optional[RegistrationError] = None
        if not isinstance(port, int) or isinstance(port, bool) or not 0 <= port <= 65535:
            raise ValueError("port must be between 0 and 65535")
        self.server = ThreadingHTTPServer(("127.0.0.1", port), self._handler_type())
        self.server.daemon_threads = True
        self.server.session = self  # type: ignore[attr-defined]
        port = int(self.server.server_address[1])
        self.manifest = build_manifest(port=port, name=name)
        self.form_url = "http://127.0.0.1:{}/".format(port)
        self._allowed_hosts = {"127.0.0.1:{}".format(port), "localhost:{}".format(port)}
        self._allowed_origins = {"http://127.0.0.1:{}".format(port), "http://localhost:{}".format(port)}

    def _handler_type(self) -> type:
        session = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:
                # Request paths contain callback code and state; never log them.
                return

            def _headers_ok(self) -> bool:
                host = self.headers.get("Host", "")
                origin = self.headers.get("Origin")
                return host in session._allowed_hosts and (origin is None or origin in session._allowed_origins)

            def _send(self, status: int, body: bytes, content_type: str = "text/plain; charset=utf-8") -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Content-Security-Policy", "default-src 'none'; form-action https://github.com; base-uri 'none'; frame-ancestors 'none'")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                if not self._headers_ok():
                    self._send(403, b"forbidden\n")
                    return
                parsed = urlparse(self.path)
                if parsed.path == "/":
                    manifest = html.escape(json.dumps(session.manifest, sort_keys=True, separators=(",", ":")), quote=True)
                    action = html.escape(GITHUB_APP_REGISTRATION + "?" + urlencode({"state": session.state}), quote=True)
                    body = (
                        "<!doctype html><meta charset=utf-8><title>Register Jev GitHub App</title>"
                        "<h1>Register Jev GitHub App</h1>"
                        "<p>Private app. Polling only; webhook delivery is inactive.</p>"
                        "<ul><li>Contents: read</li><li>Checks: read</li>"
                        "<li>Pull requests: write</li></ul>"
                        "<p>Review settings, then continue on GitHub.</p>"
                        '<form method="post" action="{}">'
                        '<input type="hidden" name="manifest" value="{}">'
                        '<button type="submit">Continue to GitHub</button></form>'
                    ).format(action, manifest).encode("utf-8")
                    self._send(200, body, "text/html; charset=utf-8")
                    return
                if parsed.path == "/callback":
                    try:
                        params = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
                    except ValueError:
                        self._send(403, b"invalid callback\n")
                        return
                    codes = params.get("code", [])
                    states = params.get("state", [])
                    code = codes[0] if len(codes) == 1 else ""
                    callback_state = states[0] if len(states) == 1 else ""
                    if len(code) > MAX_CALLBACK_VALUE or len(callback_state) > MAX_CALLBACK_VALUE:
                        self._send(403, b"invalid callback\n")
                        return
                    if not session._consume_state(callback_state, code):
                        self._send(403, b"invalid callback\n")
                        return
                    try:
                        payload = convert_manifest(code, transport=session.transport, timeout=session.timeout)
                        path = save_credentials(payload, session.output_dir, force=session.force)
                        app_id = int(payload["app_id"])
                        slug = str(payload["slug"])
                        session.result = RegisteredApp(app_id, slug, str(payload["install_url"]), path)
                        success = (
                            "GitHub App registered. "
                            '<a href="{}">Install it on a repository</a>. You may close this window.\n'
                        ).format(html.escape(session.result.install_url, quote=True)).encode("utf-8")
                        self._send(200, success, "text/html; charset=utf-8")
                    except RegistrationError as exc:
                        session.error = exc
                        self._send(502, b"GitHub App registration failed. See terminal.\n")
                    finally:
                        # handle_request loop can finish after response is flushed.
                        session.stop_requested = True
                    return
                self._send(404, b"not found\n")

        return Handler

    def _consume_state(self, callback_state: str, code: str) -> bool:
        with self._state_lock:
            if self.consumed or self.clock() - self.created_at > self.state_ttl:
                return False
            if not isinstance(callback_state, str) or not callback_state.isascii() or not isinstance(code, str) or not code.isascii():
                return False
            if not code or not hmac.compare_digest(self.state, callback_state):
                return False
            self.consumed = True
            return True

    def run(self, *, timeout: Optional[float] = None) -> Optional[RegisteredApp]:
        """Serve until successful callback, failure, timeout, or interruption."""
        self.stop_requested = False
        deadline = None if timeout is None else self.clock() + timeout
        self.server.timeout = 0.25
        try:
            while not self.stop_requested:
                if deadline is not None and self.clock() >= deadline:
                    raise RegistrationError("registration timed out")
                self.server.handle_request()
        finally:
            self.server.server_close()
        if self.error is not None:
            raise self.error
        return self.result


def _public_result(app: RegisteredApp) -> Mapping[str, Any]:
    return {"app_id": app.app_id, "slug": app.slug, "install_url": app.install_url}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Register private Jev GitHub App via local manifest flow")
    parser.add_argument("--port", type=int, default=0, help="loopback port (default: choose free port)")
    parser.add_argument("--timeout", type=float, default=STATE_TTL_SECONDS, help="registration wait seconds (default: 3600)")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="private credential directory")
    parser.add_argument("--name", default=DEFAULT_APP_NAME, help="GitHub App name (default: jev-review-thiago-ss)")
    parser.add_argument("--force", action="store_true", help="replace existing credentials.json")
    browser = parser.add_mutually_exclusive_group()
    browser.add_argument("--open", action="store_true", dest="open_browser", help="open local form in default browser")
    browser.add_argument("--no-browser", action="store_false", dest="open_browser", help="print local form URL only (default)")
    parser.set_defaults(open_browser=False)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        session = RegistrationSession(output_dir=args.output_dir, force=args.force, port=args.port, name=args.name)
        print("Open {} to review preset permissions and click Continue to GitHub.".format(session.form_url), file=sys.stderr)
        if args.open_browser:
            webbrowser.open(session.form_url)
        app = session.run(timeout=args.timeout)
        if app is None:
            raise RegistrationError("registration ended without an app")
        print(json.dumps(_public_result(app), sort_keys=True))
        return 0
    except (RegistrationError, OSError, ValueError) as exc:
        print("error: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
