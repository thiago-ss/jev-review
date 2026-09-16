import http.client
import html
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
import unittest
from urllib.parse import quote


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("register_github_app", ROOT / "scripts" / "register_github_app.py")
assert SPEC is not None and SPEC.loader is not None
registration = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = registration
SPEC.loader.exec_module(registration)


class FakeTransport:
    def __init__(self, status=201, payload=None):
        self.status = status
        self.payload = payload or {
            "id": 12345,
            "slug": "jev-review-thiago-ss",
            "pem": "-----BEGIN PRIVATE KEY-----\nSECRET-PEM\n-----END PRIVATE KEY-----",
            "webhook_secret": "WEBHOOK-SECRET",
            "client_id": "Iv1.public",
            "client_secret": "CLIENT-SECRET",
            "untrusted_extra": "should-not-be-persisted",
        }
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        return self.status, {}, json.dumps(self.payload).encode("utf-8")


class GitHubAppRegistrationTests(unittest.TestCase):
    def test_manifest_is_private_least_privilege_and_polling_only(self):
        manifest = registration.build_manifest(port=4567)
        self.assertEqual(manifest["name"], "jev-review-thiago-ss")
        self.assertFalse(manifest["public"])
        self.assertNotIn("hook_attributes", manifest)
        self.assertEqual(manifest["default_events"], [])
        self.assertEqual(
            manifest["default_permissions"],
            {"contents": "read", "checks": "read", "pull_requests": "write"},
        )
        self.assertEqual(manifest["redirect_url"], "http://127.0.0.1:4567/callback")

    def test_conversion_uses_official_endpoint_once_and_preserves_secrets_in_result_only(self):
        transport = FakeTransport()
        payload = registration.convert_manifest("temporary-code", transport=transport)
        self.assertEqual(len(transport.requests), 1)
        request, timeout = transport.requests[0]
        self.assertEqual(request.full_url, "https://api.github.com/app-manifests/temporary-code/conversions")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Accept"), "application/vnd.github+json")
        self.assertEqual(timeout, 15.0)
        self.assertEqual(payload["app_id"], 12345)
        self.assertEqual(payload["install_url"], "https://github.com/apps/jev-review-thiago-ss/installations/new")
        self.assertNotIn("untrusted_extra", payload)
        self.assertIn("pem", payload)

    def test_redirect_response_fails_without_exposing_response_body(self):
        transport = FakeTransport(status=302, payload={"message": "PRIVATE-DETAIL"})
        with self.assertRaises(registration.RegistrationError) as caught:
            registration.convert_manifest("temporary-code", transport=transport)
        self.assertNotIn("PRIVATE-DETAIL", str(caught.exception))
        self.assertIn("HTTP 302", str(caught.exception))

    def test_credentials_are_atomic_private_and_public_result_excludes_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            record, install_url = registration._credential_record(FakeTransport().payload)
            path = registration.save_credentials(record, Path(directory) / "nested")
            self.assertEqual(stat.S_IMODE(os.stat(path.parent).st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored["webhook_secret"], "WEBHOOK-SECRET")
            self.assertEqual(stored["install_url"], install_url)
            self.assertNotIn("untrusted_extra", stored)
            app = registration.RegisteredApp(12345, stored["slug"], stored["install_url"], path)
            public = registration._public_result(app)
            self.assertEqual(set(public), {"app_id", "slug", "install_url"})
            self.assertNotIn("WEBHOOK-SECRET", json.dumps(public))

    def test_existing_destination_is_rejected_before_exchange(self):
        transport = FakeTransport()
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            (destination / "credentials.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(registration.RegistrationError):
                registration.RegistrationSession(output_dir=destination, transport=transport)
        self.assertEqual(transport.requests, [])

    def test_loopback_form_and_callback_enforce_host_origin_and_state(self):
        transport = FakeTransport()
        with tempfile.TemporaryDirectory() as directory:
            session = registration.RegistrationSession(
                output_dir=Path(directory),
                transport=transport,
                state="state-value-that-is-long-enough-1234",
                timeout=2,
            )
            thread = threading.Thread(target=lambda: session.run(timeout=5), daemon=True)
            thread.start()
            port = session.server.server_address[1]

            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            connection.request("GET", "/", headers={"Host": "attacker.invalid:{}".format(port)})
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            response.read()

            connection.request("GET", "/", headers={"Origin": "http://attacker.invalid:{}".format(port)})
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            response.read()

            connection.request("GET", "/")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            form = html.unescape(response.read().decode("utf-8"))
            self.assertIn("https://github.com/settings/apps/new", form)
            self.assertNotIn('"hook_attributes"', form)
            self.assertNotIn("WEBHOOK-SECRET", form)

            connection.request("GET", "/callback?code=temporary-code&state=wrong-state")
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
            self.assertEqual(transport.requests, [])

            connection.request(
                "GET",
                "/callback?code={}&state={}".format(quote("temporary-code"), quote(session.state)),
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
            connection.close()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            self.assertIsNotNone(session.result)
            self.assertEqual(session.result.app_id, 12345)
            self.assertEqual(len(transport.requests), 1)

    def test_callback_state_is_one_shot_and_expiry_is_fail_closed(self):
        session = registration.RegistrationSession(state="state-value-that-is-long-enough-1234", clock=lambda: 100.0)
        self.assertTrue(session._consume_state(session.state, "code"))
        self.assertFalse(session._consume_state(session.state, "code"))
        unicode_state = registration.RegistrationSession(state="state-value-that-is-long-enough-1234")
        self.assertFalse(unicode_state._consume_state("é", "code"))
        expired = registration.RegistrationSession(
            state="state-value-that-is-long-enough-1234", clock=lambda: 10_000.0
        )
        expired.created_at = 0.0
        self.assertFalse(expired._consume_state(expired.state, "code"))
        session.server.server_close()
        unicode_state.server.server_close()
        expired.server.server_close()

    def test_cli_help_and_no_browser_flag_are_available(self):
        parser = registration._parser()
        args = parser.parse_args(["--no-browser"])
        self.assertFalse(args.open_browser)
        self.assertEqual(parser.parse_args(["--name", "custom-jev"]).name, "custom-jev")
        self.assertIn("Register private Jev GitHub App", parser.format_help())


if __name__ == "__main__":
    unittest.main()
