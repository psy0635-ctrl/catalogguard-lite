"""Resolve the Git commit associated with a newly produced ETL batch."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path


_APPLICATION_COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_EXPLICIT_ENVIRONMENT_KEYS = (
    "CATALOGGUARD_APPLICATION_COMMIT_SHA",
    "RAILWAY_GIT_COMMIT_SHA",
)


class ApplicationCommitLineageError(ValueError):
    """Raised when an explicitly configured application commit SHA is unsafe."""


def _validate_explicit_sha(value: object) -> str:
    if not isinstance(value, str) or _APPLICATION_COMMIT_SHA_PATTERN.fullmatch(value) is None:
        raise ApplicationCommitLineageError("Application commit SHA configuration is invalid")
    return value


def resolve_application_commit_sha(
    *,
    environ: Mapping[str, str] | None = None,
    repository_path: Path | None = None,
) -> str | None:
    """Return the configured/deployed Git SHA, or ``None`` when it is unknown.

    An environment variable being present is an assertion made by the deployer;
    malformed assertions fail safely instead of silently falling through to a
    different source. Missing Git metadata/executable is a normal unknown case.
    """
    environment = os.environ if environ is None else environ
    for key in _EXPLICIT_ENVIRONMENT_KEYS:
        if key in environment:
            return _validate_explicit_sha(environment[key])

    repo = repository_path or Path(__file__).resolve().parents[1]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha if _APPLICATION_COMMIT_SHA_PATTERN.fullmatch(sha) else None
