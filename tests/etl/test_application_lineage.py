from __future__ import annotations

import subprocess

import pytest

from etl.application_lineage import (
    ApplicationCommitLineageError,
    resolve_application_commit_sha,
)


SHA = "a" * 40


def test_custom_environment_sha_has_highest_precedence(monkeypatch) -> None:
    monkeypatch.setattr(
        "etl.application_lineage.subprocess.run",
        lambda *args, **kwargs: pytest.fail("git fallback must not run"),
    )

    assert resolve_application_commit_sha(
        environ={
            "CATALOGGUARD_APPLICATION_COMMIT_SHA": SHA,
            "RAILWAY_GIT_COMMIT_SHA": "b" * 40,
        }
    ) == SHA


def test_railway_sha_is_used_when_custom_environment_is_absent() -> None:
    assert resolve_application_commit_sha(
        environ={"RAILWAY_GIT_COMMIT_SHA": "b" * 40}
    ) == "b" * 40


def test_local_git_fallback_returns_a_canonical_sha(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "etl.application_lineage.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, f"{SHA}\n", ""),
    )

    assert resolve_application_commit_sha(environ={}, repository_path=tmp_path) == SHA


def test_git_unavailable_is_a_normal_unknown_value(monkeypatch, tmp_path) -> None:
    def no_git(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr("etl.application_lineage.subprocess.run", no_git)

    assert resolve_application_commit_sha(environ={}, repository_path=tmp_path) is None


@pytest.mark.parametrize("value", ["", "A" * 40, "a" * 39, "a" * 41, "g" * 40])
def test_malformed_explicit_environment_sha_is_rejected(value) -> None:
    with pytest.raises(ApplicationCommitLineageError, match="configuration is invalid"):
        resolve_application_commit_sha(
            environ={"CATALOGGUARD_APPLICATION_COMMIT_SHA": value}
        )
