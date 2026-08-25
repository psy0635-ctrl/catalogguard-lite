"""Canonical fingerprints for the semantic portion of an ETL profile."""

from __future__ import annotations

import hashlib
import json

from etl.models import ETLProfile


def _target_columns(targets: object) -> list[str]:
    return [targets] if isinstance(targets, str) else list(targets)


def build_profile_semantic_payload(profile: ETLProfile) -> dict[str, object]:
    """Return mapping, required-column, and default semantics only."""
    return {
        "source_columns": {
            source: _target_columns(targets)
            for source, targets in profile.source_columns.items()
        },
        "required_source_columns": list(profile.required_source_columns),
        "defaults": dict(profile.defaults),
    }


def compute_profile_definition_sha256(profile: ETLProfile) -> str:
    """Hash canonical profile semantics, not profile JSON bytes or runtime code."""
    canonical_json = json.dumps(
        build_profile_semantic_payload(profile),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
