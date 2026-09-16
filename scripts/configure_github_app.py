#!/usr/bin/env python3
"""Prepare Jev's GitHub App deployment configuration.

This helper deliberately does not register or install a GitHub App.  App
registration and repository installation are account-owner actions in GitHub.
It consumes the owner-only credential export produced after those actions,
writes a non-secret shadow configuration, and can explicitly stage repository
secrets and variables through ``gh``.

The credential file accepts this small contract::

    {
      "app_id": 123,
      "slug": "jev-review",
      "client_id": "Iv1.public-client-id",
      "pem": "-----BEGIN PRIVATE KEY-----..."
    }

The private key is never placed in production.json, command arguments, or
output.
The command is preparation-only by default.  Even ``--configure-actions``
sets ``JEV_ENABLED=false`` and ``JEV_EXECUTE=false``; enabling the workflow is
a separate, deliberate operator action after configuration is pushed and
reviewed.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Callable, Mapping, Optional, Sequence


DEFAULT_WORKFLOW_REPO = "thiago-ss/jev-review"
DEFAULT_CREDENTIALS_PATH = ".local/github-app/credentials.json"
DEFAULT_CONFIG_PATH = "config/production.json"
PRIVATE_KEY_SECRET = "JEV_APP_PRIVATE_KEY"
API_KEY_SECRET = "TYPESAFE_API_KEY"
MANAGED_CONFIG_FIELDS = (
    "allowlisted_repositories",
    "trusted_checks",
    "bot_login",
    "trusted_reviewers",
    "fallback_reviewers",
    "mode",
    "policy_version",
)

_REPOSITORY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
_LOGIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")
_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
_PEM_BEGIN = "-----BEGIN "
_PEM_END = "-----"


class ConfigurationError(ValueError):
    """Safe operator-facing configuration error (never includes secrets)."""


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigurationError(label + " must be an object")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigurationError(label + " must be a positive integer")
    return value


def load_credentials(path: Path) -> dict[str, Any]:
    """Read and validate an owner-only app credential export.

    Returned mapping contains only fields required by this helper.  Callers
    must treat ``private_key`` as secret and must not serialize this mapping.
    """

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError("invalid GitHub App credential file") from exc
    root = _mapping(raw, "GitHub App credentials")

    app_id = _positive_int(root.get("app_id"), "app_id")
    slug_value = root.get("slug")
    if not isinstance(slug_value, str) or not _SLUG.fullmatch(slug_value.strip()):
        raise ConfigurationError("app_slug must be a valid GitHub App slug")
    app_slug = slug_value.strip()

    client_id_value = root.get("client_id")
    if (
        not isinstance(client_id_value, str)
        or not client_id_value.strip()
        or len(client_id_value) > 512
        or any(character.isspace() for character in client_id_value)
    ):
        raise ConfigurationError("client_id must be a bounded GitHub App client ID")

    private_key = root.get("pem")
    if not isinstance(private_key, str) or not private_key.startswith(_PEM_BEGIN) or not private_key.rstrip().endswith(_PEM_END) or "PRIVATE KEY" not in private_key:
        raise ConfigurationError("private_key must be a PEM private key")
    if "\x00" in private_key:
        raise ConfigurationError("private_key contains invalid data")

    return {
        "app_id": app_id,
        "app_slug": app_slug,
        "client_id": None if client_id_value is None else client_id_value.strip(),
        "private_key": private_key,
    }


def normalize_repository(value: str, label: str = "repository") -> str:
    if not isinstance(value, str) or not _REPOSITORY.fullmatch(value.strip()):
        raise ConfigurationError(label + " must be OWNER/REPO")
    return value.strip()


def normalize_reviewer(value: str) -> str:
    if not isinstance(value, str):
        raise ConfigurationError("reviewer must be a GitHub login or ORG/TEAM")
    clean = value.strip()
    if clean.startswith("@"):
        clean = clean[1:]
    parts = clean.split("/")
    if len(parts) == 1 and _LOGIN.fullmatch(parts[0]):
        return parts[0]
    if len(parts) == 2 and _LOGIN.fullmatch(parts[0]) and _LOGIN.fullmatch(parts[1]):
        return clean
    raise ConfigurationError("reviewer must be a GitHub login or ORG/TEAM")


def parse_check(value: str) -> tuple[str, int]:
    if not isinstance(value, str):
        raise ConfigurationError("check must be NAME:APP_ID")
    name, separator, app_id_text = value.strip().rpartition(":")
    if not separator or not name or "\n" in name or "\r" in name or len(name) > 200 or not app_id_text.isdigit():
        raise ConfigurationError("check must be NAME:APP_ID")
    app_id = _positive_int(int(app_id_text), "check app ID")
    return name, app_id


def normalize_checks(values: Sequence[str]) -> dict[str, list[int]]:
    checks: dict[str, list[int]] = {}
    for value in values:
        name, app_id = parse_check(value)
        existing = checks.setdefault(name, [])
        if app_id not in existing:
            existing.append(app_id)
    return checks


def bot_login(app_slug: str) -> str:
    if not isinstance(app_slug, str) or not _SLUG.fullmatch(app_slug):
        raise ConfigurationError("app_slug must be a valid GitHub App slug")
    return app_slug if app_slug.endswith("[bot]") else app_slug + "[bot]"


def build_shadow_config(
    repository: str,
    reviewers: Sequence[str],
    checks: Mapping[str, Sequence[int]],
    app: Mapping[str, Any],
    *,
    existing: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Build config while preserving unrelated existing keys.

    Existing managed fields must agree with requested deployment identity.  A
    mismatch is refused rather than silently widening an allowlist or routing
    to a different owner.
    """

    repository = normalize_repository(repository)
    normalized_reviewers = tuple(dict.fromkeys(normalize_reviewer(v) for v in reviewers))
    if not normalized_reviewers:
        raise ConfigurationError("at least one --reviewer is required as fallback")
    app_slug = str(app["app_slug"])
    generated: dict[str, Any] = {
        "allowlisted_repositories": [repository],
        "trusted_checks": {str(name): [int(v) for v in values] for name, values in checks.items()},
        "bot_login": bot_login(app_slug),
        "trusted_reviewers": list(normalized_reviewers),
        "fallback_reviewers": list(normalized_reviewers),
        "mode": "shadow",
        "policy_version": "v1",
    }
    result = dict(existing or {})
    for key, value in generated.items():
        if key in result and result[key] != value:
            raise ConfigurationError("existing config " + key + " conflicts; refusing overwrite")
        result[key] = value
    # Never create an absent calibration reference.  Shadow mode with no
    # calibration is a valid fail-closed state and should not require a file.
    return result


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), prefix=".production.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
        os.replace(str(temporary), str(path))
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except (UnboundLocalError, OSError):
            pass
        raise ConfigurationError("could not write deployment config") from exc


def prepare_config(path: Path, repository: str, reviewers: Sequence[str], checks: Mapping[str, Sequence[int]], app: Mapping[str, Any]) -> dict[str, Any]:
    existing: Optional[Mapping[str, Any]] = None
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError("existing deployment config is invalid; refusing overwrite") from exc
        existing = _mapping(loaded, "existing deployment config")
    result = build_shadow_config(repository, reviewers, checks, app, existing=existing)
    _write_json(path, result)
    return result


def _origin_repository() -> Optional[str]:
    """Return normalized GitHub origin, without exposing command output."""

    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return _parse_remote(result.stdout.strip())


def _parse_remote(value: str) -> Optional[str]:
    if value.startswith("git@github.com:"):
        value = value[len("git@github.com:") :]
    elif value.startswith("https://github.com/"):
        value = value[len("https://github.com/") :]
    elif value.startswith("http://github.com/"):
        value = value[len("http://github.com/") :]
    else:
        return None
    value = value.removesuffix(".git")
    return value if _REPOSITORY.fullmatch(value) else None


def validate_origin(workflow_repository: str, *, require: bool = False) -> None:
    origin = _origin_repository()
    if origin is None:
        if require:
            raise ConfigurationError("workflow repository origin is missing or not GitHub")
        return
    if origin != workflow_repository:
        raise ConfigurationError("workflow repository does not match git origin; refusing actions write")


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _run_gh(args: Sequence[str], *, secret: Optional[str] = None, runner: Optional[Runner] = None) -> None:
    """Run gh without putting secret material in argv or error output."""

    run = runner or subprocess.run
    try:
        result = run(
            ["gh", *args],
            input=secret,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise ConfigurationError("GitHub CLI unavailable") from exc
    if result.returncode != 0:
        # Do not include stderr: gh or a proxy could echo sensitive input.
        raise ConfigurationError("GitHub CLI command failed")


def configure_actions(
    target_repository: str,
    workflow_repository: str,
    app: Mapping[str, Any],
    *,
    api_key: str,
    runner: Optional[Runner] = None,
) -> None:
    """Stage secrets and disabled variables in workflow repository."""

    target_repository = normalize_repository(target_repository)
    workflow_repository = normalize_repository(workflow_repository, "workflow repository")
    if not isinstance(api_key, str) or not api_key.strip():
        raise ConfigurationError("TYPESAFE_API_KEY environment variable is required")
    private_key = app.get("private_key")
    if not isinstance(private_key, str) or not private_key:
        raise ConfigurationError("validated app private key unavailable")

    client_id = app.get("client_id")
    if not isinstance(client_id, str) or not client_id.strip():
        raise ConfigurationError("credential file missing client_id; cannot mint App token")
    owner, target_name = target_repository.split("/", 1)

    # Disable both execution switches first.  This ordering prevents a
    # partially staged deployment from starting while remaining fields or
    # secrets are being changed.
    variables = {
        "JEV_ENABLED": "false",
        "JEV_EXECUTE": "false",
        "JEV_REPOSITORY": str(target_repository),
        "JEV_APP_CLIENT_ID": client_id.strip(),
        "JEV_APP_INSTALLATION_OWNER": owner,
        "JEV_APP_INSTALLATION_REPOSITORY": target_name,
    }
    for name, value in variables.items():
        _run_gh(["variable", "set", name, "--repo", workflow_repository, "--body", value], runner=runner)

    # Secret values travel only through stdin.  They never appear in argv.
    # Variables above disable both workflow switches before any secret or
    # target credential mutation occurs.
    _run_gh(["secret", "set", PRIVATE_KEY_SECRET, "--repo", workflow_repository], secret=private_key, runner=runner)
    _run_gh(["secret", "set", API_KEY_SECRET, "--repo", workflow_repository], secret=api_key, runner=runner)


def _read_api_key() -> str:
    # Deliberately do not parse .env: environment injection is auditable and
    # avoids accidentally copying a local secret into a subprocess context.
    value = os.environ.get(API_KEY_SECRET, "")
    if not value.strip():
        raise ConfigurationError("TYPESAFE_API_KEY environment variable is required for --configure-actions")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare Jev GitHub App shadow deployment")
    parser.add_argument("--credentials", default=DEFAULT_CREDENTIALS_PATH, help="owner-only credential JSON (default: .local/github-app/credentials.json)")
    parser.add_argument("--repo", required=True, help="target repository OWNER/REPO")
    parser.add_argument("--reviewer", action="append", required=True, help="trusted fallback login or ORG/TEAM; repeatable")
    parser.add_argument("--check", action="append", default=[], metavar="NAME:APP_ID", help="trusted check identity; repeatable")
    parser.add_argument("--workflow-repo", default=DEFAULT_WORKFLOW_REPO, help="repository holding workflow/secrets/config")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="local production config path")
    parser.add_argument("--configure-actions", action="store_true", help="explicitly upload secrets and disabled variables using gh")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        repository = normalize_repository(args.repo)
        workflow_repository = normalize_repository(args.workflow_repo, "workflow repository")
        app = load_credentials(Path(args.credentials))
        checks = normalize_checks(args.check)
        config = prepare_config(Path(args.config), repository, args.reviewer, checks, app)
        if args.configure_actions:
            validate_origin(workflow_repository, require=True)
            configure_actions(repository, workflow_repository, app, api_key=_read_api_key())
        output = {
            "config": str(Path(args.config)),
            "repository": repository,
            "workflow_repository": workflow_repository,
            "bot_login": config["bot_login"],
            "reviewers": config["fallback_reviewers"],
            "trusted_checks": config["trusted_checks"],
            "calibration_configured": "calibration" in config,
            "actions_configured": bool(args.configure_actions),
            "jev_enabled": False,
            "jev_execute": False,
        }
        print(json.dumps(output, sort_keys=True, indent=2))
        return 0
    except (ConfigurationError, OSError) as exc:
        print("jev configure: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
