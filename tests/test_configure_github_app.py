import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.configure_github_app import (
    ConfigurationError,
    _parse_remote,
    build_shadow_config,
    configure_actions,
    load_credentials,
    main,
    normalize_checks,
    prepare_config,
)


PEM = "-----BEGIN PRIVATE KEY-----\n" + ("x" * 80) + "\n-----END PRIVATE KEY-----\n"


def credentials(**overrides):
    value = {
        "schema_version": 1,
        "app_id": 1234,
        "slug": "jev-review",
        "client_id": "Iv1.public-client-id",
        "pem": PEM,
        "webhook_secret": "ignored",
    }
    value.update(overrides)
    return value


class CredentialTests(unittest.TestCase):
    def test_registration_export_is_normalized_without_secret_in_public_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "github-app"
            path.write_text(json.dumps(credentials()), encoding="utf-8")
            loaded = load_credentials(path)
        self.assertEqual(loaded["app_id"], 1234)
        self.assertEqual(loaded["app_slug"], "jev-review")
        self.assertEqual(loaded["client_id"], "Iv1.public-client-id")
        self.assertEqual(loaded["private_key"], PEM)

    def test_registration_export_requires_exact_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "github-app"
            path.write_text(json.dumps({"app_id": 1, "slug": "my-app", "client_id": "Iv1.id", "pem": PEM}), encoding="utf-8")
            loaded = load_credentials(path)
        self.assertEqual(loaded["app_id"], 1)
        self.assertEqual(loaded["client_id"], "Iv1.id")

    def test_invalid_credentials_fail_without_echoing_private_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "github-app"
            path.write_text(json.dumps({"app_id": 1, "app_slug": "app", "private_key": "bad"}), encoding="utf-8")
            with self.assertRaises(ConfigurationError) as error:
                load_credentials(path)
        self.assertNotIn("bad", str(error.exception))


class ConfigTests(unittest.TestCase):
    def test_shadow_config_has_explicit_allowlist_fallback_and_no_calibration_requirement(self):
        app = {"app_slug": "jev-review"}
        config = build_shadow_config("owner/project", ["@alice", "org/reviewers"], {}, app)
        self.assertEqual(config["allowlisted_repositories"], ["owner/project"])
        self.assertEqual(config["fallback_reviewers"], ["alice", "org/reviewers"])
        self.assertEqual(config["trusted_reviewers"], config["fallback_reviewers"])
        self.assertEqual(config["trusted_checks"], {})
        self.assertEqual(config["bot_login"], "jev-review[bot]")
        self.assertEqual(config["mode"], "shadow")
        self.assertNotIn("calibration", config)

    def test_existing_unrelated_fields_survive_and_conflicting_identity_is_refused(self):
        app = {"app_slug": "jev-review"}
        existing = {"custom": {"retention_days": 30}, "allowlisted_repositories": ["owner/project"]}
        config = build_shadow_config("owner/project", ["alice"], {}, app, existing=existing)
        self.assertEqual(config["custom"], {"retention_days": 30})
        with self.assertRaisesRegex(ConfigurationError, "refusing overwrite"):
            build_shadow_config("other/repo", ["alice"], {}, app, existing=existing)

    def test_prepare_writes_config_and_does_not_require_calibration_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config" / "production.json"
            result = prepare_config(path, "owner/project", ["alice"], {}, {"app_slug": "jev-review"})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), result)
            self.assertFalse((path.parent / "calibration.json").exists())

    def test_check_parser_is_fail_closed_when_no_checks_are_supplied(self):
        self.assertEqual(normalize_checks([]), {})
        self.assertEqual(normalize_checks(["ci/test:7", "ci/test:7", "ci/test:8"]), {"ci/test": [7, 8]})
        with self.assertRaises(ConfigurationError):
            normalize_checks(["ci/test:not-an-id"])


class ActionsTests(unittest.TestCase):
    def test_actions_use_stdin_for_secrets_and_always_disable_workflow(self):
        calls = []

        def runner(argv, **kwargs):
            calls.append((list(argv), kwargs))
            class Result:
                returncode = 0
                stdout = ""
                stderr = ""
            return Result()

        api_key = "typesafe-secret-value"
        configure_actions(
            "owner/project",
            "owner/jev-review",
            {"app_id": 1234, "app_slug": "jev-review", "client_id": "Iv1.public-client-id", "private_key": PEM},
            api_key=api_key,
            runner=runner,
        )
        self.assertEqual(len(calls), 8)
        argv_text = " ".join(arg for call, _ in calls for arg in call)
        self.assertNotIn(api_key, argv_text)
        self.assertNotIn(PEM, argv_text)
        self.assertEqual(calls[0][0][0:3], ["gh", "variable", "set"])
        self.assertEqual(calls[0][0][2], "set")
        variables = {call[3]: call[-1] for call, _ in calls[:6]}
        self.assertEqual(variables["JEV_REPOSITORY"], "owner/project")
        self.assertEqual(variables["JEV_ENABLED"], "false")
        self.assertEqual(variables["JEV_EXECUTE"], "false")
        self.assertEqual(variables["JEV_APP_CLIENT_ID"], "Iv1.public-client-id")
        self.assertEqual(variables["JEV_APP_INSTALLATION_OWNER"], "owner")
        self.assertEqual(variables["JEV_APP_INSTALLATION_REPOSITORY"], "project")
        self.assertEqual(calls[6][1]["input"], PEM)
        self.assertEqual(calls[7][1]["input"], api_key)
        self.assertEqual([calls[0][0][3], calls[1][0][3]], ["JEV_ENABLED", "JEV_EXECUTE"])

    def test_gh_failure_has_no_command_output_or_secret(self):
        def runner(argv, **kwargs):
            class Result:
                returncode = 1
                stdout = "private key echoed"
                stderr = "private key echoed"
            return Result()

        with self.assertRaisesRegex(ConfigurationError, "GitHub CLI command failed") as error:
            configure_actions("owner/project", "owner/jev-review", {"app_id": 1, "app_slug": "app", "client_id": "Iv1.app", "private_key": PEM}, api_key="secret", runner=runner)
        self.assertNotIn("private key", str(error.exception))


class SafetyTests(unittest.TestCase):
    def test_origin_parser_accepts_https_and_ssh_only(self):
        self.assertEqual(_parse_remote("https://github.com/owner/project.git"), "owner/project")
        self.assertEqual(_parse_remote("git@github.com:owner/project"), "owner/project")
        self.assertIsNone(_parse_remote("https://evil.example/owner/project.git"))

    def test_configure_actions_requires_api_key(self):
        with self.assertRaisesRegex(ConfigurationError, "TYPESAFE_API_KEY"):
            configure_actions("owner/project", "owner/jev-review", {"app_id": 1, "app_slug": "app", "private_key": PEM}, api_key="")

    def test_missing_client_id_fails_before_any_gh_mutation(self):
        calls = []

        def runner(argv, **kwargs):
            calls.append(argv)
            raise AssertionError("runner must not be called")

        with self.assertRaisesRegex(ConfigurationError, "client_id"):
            configure_actions("owner/project", "owner/jev-review", {"app_id": 1, "app_slug": "app", "private_key": PEM}, api_key="secret", runner=runner)
        self.assertEqual(calls, [])

    def test_default_main_prepare_does_not_call_gh(self):
        with tempfile.TemporaryDirectory() as directory:
            cred = Path(directory) / "github-app"
            config = Path(directory) / "production.json"
            cred.write_text(json.dumps(credentials()), encoding="utf-8")
            with patch("scripts.configure_github_app.subprocess.run") as run:
                status = main(["--credentials", str(cred), "--repo", "owner/project", "--reviewer", "alice", "--config", str(config)])
            self.assertEqual(status, 0)
            run.assert_not_called()
            output = json.loads(config.read_text(encoding="utf-8"))
            self.assertFalse(output.get("calibration", False))


if __name__ == "__main__":
    unittest.main()
