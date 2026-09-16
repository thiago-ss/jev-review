"""Conservative reviewer routing from trusted repository configuration."""
from __future__ import annotations

from dataclasses import dataclass
import fnmatch
from typing import Iterable, Mapping, Optional, Sequence, Tuple

from .models import ValidationError


@dataclass(frozen=True)
class OwnerRule:
    pattern: str
    owners: Tuple[str, ...]


def parse_codeowners(text: str, trusted_owners: Iterable[str] = ()) -> Tuple[OwnerRule, ...]:
    if not isinstance(text, str):
        raise ValidationError("CODEOWNERS must be text")
    allowed = frozenset(trusted_owners)
    rules = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) < 1:
            continue
        pattern, owners = fields[0], tuple(o for o in fields[1:] if o in allowed)
        # Keep empty rules: an explicit no-owner rule must clear an earlier broad rule.
        rules.append(OwnerRule(pattern, owners))
    return tuple(rules)


def route_files(paths: Iterable[str], codeowners: Sequence[OwnerRule] = (), trusted_config: Optional[Mapping[str, Sequence[str]]] = None, fallback: Sequence[str] = ()) -> Tuple[str, ...]:
    """Return trusted owners only; last matching CODEOWNERS rule wins per path."""
    trusted_config = trusted_config or {}
    result = []
    for path in paths:
        matches = []
        codeowner_match = False
        for rule in codeowners:
            if _matches(path, rule.pattern):
                codeowner_match = True
                matches = list(rule.owners)
        if not matches and not codeowner_match:
            for pattern, owners in trusted_config.items():
                if _matches(path, pattern):
                    matches = [owner for owner in owners if isinstance(owner, str) and owner.strip()]
        for owner in matches:
            if owner not in result:
                result.append(owner)
        if not matches:
            for owner in fallback:
                if isinstance(owner, str) and owner.strip() and owner not in result:
                    result.append(owner)
    return tuple(result)


def _matches(path: str, pattern: str) -> bool:
    """Small documented CODEOWNERS subset: globs plus directory-prefix rules."""
    clean_path, clean_pattern = path.lstrip("/"), pattern.lstrip("/")
    if clean_pattern.endswith("/"):
        return clean_path.startswith(clean_pattern)
    return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(clean_path, clean_pattern)


def owners_for_files(paths: Iterable[str], codeowners: Sequence[OwnerRule] = (), trusted_config: Optional[Mapping[str, Sequence[str]]] = None, fallback: Sequence[str] = ()) -> Tuple[str, ...]:
    return route_files(paths, codeowners, trusted_config, fallback)


def parse_and_route(paths: Iterable[str], codeowners_text: str, trusted_owners: Iterable[str], fallback: Sequence[str] = ()) -> Tuple[str, ...]:
    return route_files(paths, parse_codeowners(codeowners_text, trusted_owners), fallback=fallback)
