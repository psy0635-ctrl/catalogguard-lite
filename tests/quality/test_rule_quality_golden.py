"""Synthetic golden-fixture regression test for the complete rule engine.

The counts produced here describe only this fixed synthetic fixture.  They are
not production precision, recall, accuracy, or any other service-quality claim.
"""

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from core.inspection_service import inspect_uploaded_csv
from core.models import ValidationIssue


QUALITY_DIR = Path(__file__).resolve().parent
GOLDEN_CATALOG_PATH = QUALITY_DIR / "golden_catalog.csv"
GOLDEN_EXPECTED_ISSUES_PATH = QUALITY_DIR / "golden_expected_issues.json"

CURRENT_ISSUE_CODES = frozenset(
    {
        "category_price_anomaly",
        "duplicate_product_content",
        "duplicate_product_id",
        "duplicate_product_name",
        "duplicate_variant_combination",
        "email_address",
        "inconsistent_group_category",
        "inconsistent_group_size_system",
        "invalid_category",
        "invalid_non_positive_price",
        "invalid_non_positive_sale_price",
        "invalid_price",
        "invalid_sale_price",
        "invalid_stock",
        "missing_required_field",
        "non_standard_color",
        "non_standard_size",
        "out_of_stock",
        "phone_number",
        "product_category_mismatch",
        "prohibited_term",
        "resident_registration_number",
        "sale_price_greater_than_price",
        "suspected_bank_account",
    }
)

FIXED_RULE_FIELDS = {
    "category_price_anomaly": "price",
    "duplicate_product_content": "product",
    "duplicate_product_id": "product_id",
    "duplicate_product_name": "product_name",
    "duplicate_variant_combination": "color,size",
    "inconsistent_group_category": "category",
    "inconsistent_group_size_system": "size",
    "invalid_category": "category",
    "invalid_non_positive_price": "price",
    "invalid_non_positive_sale_price": "sale_price",
    "invalid_price": "price",
    "invalid_sale_price": "sale_price",
    "invalid_stock": "stock",
    "non_standard_color": "color",
    "non_standard_size": "size",
    "out_of_stock": "stock",
    "product_category_mismatch": "category",
    "sale_price_greater_than_price": "sale_price",
}

CONTENT_FIELD_RULES = frozenset(
    {
        "email_address",
        "phone_number",
        "prohibited_term",
        "resident_registration_number",
        "suspected_bank_account",
    }
)


@dataclass(frozen=True, order=True)
class IssueIdentity:
    source_row_number: int
    rule: str
    field: str
    severity: str


@dataclass(frozen=True)
class GoldenIssue:
    case: str
    identity: IssueIdentity
    related_source_rows: tuple[int, ...]


@dataclass(frozen=True)
class ActualIssue:
    identity: IssueIdentity
    related_source_rows: tuple[int, ...]
    relationship_error: str | None = None


@dataclass(frozen=True)
class RelationshipMismatch:
    identity: IssueIdentity
    expected_related_source_rows: tuple[int, ...]
    actual_related_source_rows: tuple[int, ...]
    actual_error: str | None = None


@dataclass(frozen=True)
class RuleSummary:
    expected: int
    matched: int
    false_positives: int
    false_negatives: int


@dataclass(frozen=True)
class EvaluationResult:
    matched: Counter[IssueIdentity]
    false_positives: Counter[IssueIdentity]
    false_negatives: Counter[IssueIdentity]
    relationship_mismatches: tuple[RelationshipMismatch, ...]
    rule_summary: dict[str, RuleSummary]

    @property
    def is_clean(self) -> bool:
        return not (
            self.false_positives
            or self.false_negatives
            or self.relationship_mismatches
        )


def _canonical_field(issue: ValidationIssue) -> str:
    fixed_field = FIXED_RULE_FIELDS.get(issue.rule)
    if fixed_field is not None:
        return fixed_field

    if issue.rule == "missing_required_field":
        match = re.fullmatch(r"'([^']+)' is missing", issue.message)
    elif issue.rule in CONTENT_FIELD_RULES:
        match = re.fullmatch(r"field '([^']+)' contains .+", issue.message)
    else:
        raise AssertionError(f"No test-only canonical field mapping for rule {issue.rule!r}")

    if match is None:
        raise AssertionError(
            f"Cannot extract canonical field for {issue.rule!r} from {issue.message!r}"
        )
    return match.group(1)


def _normalize_related_rows(
    value: object,
    *,
    source_row_number: int,
) -> tuple[tuple[int, ...], tuple[str, ...]]:
    if not isinstance(value, list):
        return (), ("related_source_rows is not a list",)

    errors = []
    valid_rows = []
    for row in value:
        if type(row) is not int or row < 2:
            errors.append(f"invalid related row {row!r}")
            continue
        valid_rows.append(row)

    if source_row_number in valid_rows:
        errors.append("related_source_rows contains its own source row")
    if len(valid_rows) != len(set(valid_rows)):
        errors.append("related_source_rows contains duplicates")

    normalized = tuple(sorted(set(valid_rows) - {source_row_number}))
    return normalized, tuple(errors)


def _load_expected_issues() -> list[GoldenIssue]:
    document = json.loads(GOLDEN_EXPECTED_ISSUES_PATH.read_text(encoding="utf-8"))
    assert set(document) == {"issues"}
    assert isinstance(document["issues"], list)

    expected_issues = []
    for index, item in enumerate(document["issues"]):
        assert isinstance(item, dict), f"issues[{index}] must be an object"
        required_fields = {"case", "source_row_number", "rule", "field", "severity"}
        optional_fields = {"related_source_rows"}
        assert required_fields <= item.keys(), f"issues[{index}] is missing required fields"
        assert item.keys() <= required_fields | optional_fields, (
            f"issues[{index}] has unexpected fields"
        )
        assert isinstance(item["case"], str) and item["case"].strip()
        assert type(item["source_row_number"]) is int and item["source_row_number"] >= 2
        assert isinstance(item["rule"], str) and item["rule"]
        assert isinstance(item["field"], str) and item["field"]
        assert item["severity"] in {"error", "warning"}

        related_rows, relationship_errors = _normalize_related_rows(
            item.get("related_source_rows", []),
            source_row_number=item["source_row_number"],
        )
        assert not relationship_errors, (
            f"issues[{index}] has invalid expected relationships: "
            + "; ".join(relationship_errors)
        )
        expected_issues.append(
            GoldenIssue(
                case=item["case"],
                identity=IssueIdentity(
                    source_row_number=item["source_row_number"],
                    rule=item["rule"],
                    field=item["field"],
                    severity=item["severity"],
                ),
                related_source_rows=related_rows,
            )
        )
    return expected_issues


def _adapt_actual_issue(issue: ValidationIssue) -> ActualIssue:
    assert type(issue.source_row_number) is int and issue.source_row_number >= 2
    identity = IssueIdentity(
        source_row_number=issue.source_row_number,
        rule=issue.rule,
        field=_canonical_field(issue),
        severity=issue.severity,
    )
    related_rows, relationship_errors = _normalize_related_rows(
        issue.related_source_rows,
        source_row_number=identity.source_row_number,
    )
    return ActualIssue(
        identity=identity,
        related_source_rows=related_rows,
        relationship_error="; ".join(relationship_errors) or None,
    )


def _build_rule_summary(
    expected: Counter[IssueIdentity],
    matched: Counter[IssueIdentity],
    false_positives: Counter[IssueIdentity],
    false_negatives: Counter[IssueIdentity],
) -> dict[str, RuleSummary]:
    rules = sorted(
        {
            identity.rule
            for counts in (expected, matched, false_positives, false_negatives)
            for identity in counts
        }
    )

    def count_rule(counts: Counter[IssueIdentity], rule: str) -> int:
        return sum(count for identity, count in counts.items() if identity.rule == rule)

    return {
        rule: RuleSummary(
            expected=count_rule(expected, rule),
            matched=count_rule(matched, rule),
            false_positives=count_rule(false_positives, rule),
            false_negatives=count_rule(false_negatives, rule),
        )
        for rule in rules
    }


def _compare_relationships(
    expected_issues: list[GoldenIssue],
    actual_issues: list[ActualIssue],
    matched: Counter[IssueIdentity],
) -> tuple[RelationshipMismatch, ...]:
    expected_by_identity = defaultdict(list)
    actual_by_identity = defaultdict(list)
    for issue in expected_issues:
        expected_by_identity[issue.identity].append(issue.related_source_rows)
    for issue in actual_issues:
        actual_by_identity[issue.identity].append(
            (issue.related_source_rows, issue.relationship_error)
        )

    mismatches = []
    for identity in sorted(matched):
        comparison_count = matched[identity]
        expected_relationships = sorted(expected_by_identity[identity])[:comparison_count]
        actual_relationships = sorted(
            actual_by_identity[identity],
            key=lambda value: (value[0], value[1] or ""),
        )[:comparison_count]

        unmatched_actual = list(actual_relationships)
        unmatched_expected = []
        for expected_rows in expected_relationships:
            exact_index = next(
                (
                    index
                    for index, (actual_rows, actual_error) in enumerate(unmatched_actual)
                    if actual_error is None and actual_rows == expected_rows
                ),
                None,
            )
            if exact_index is None:
                unmatched_expected.append(expected_rows)
            else:
                unmatched_actual.pop(exact_index)

        for expected_rows, (actual_rows, actual_error) in zip(
            unmatched_expected,
            unmatched_actual,
            strict=True,
        ):
            mismatches.append(
                RelationshipMismatch(
                    identity=identity,
                    expected_related_source_rows=expected_rows,
                    actual_related_source_rows=actual_rows,
                    actual_error=actual_error,
                )
            )

    return tuple(sorted(mismatches, key=lambda mismatch: mismatch.identity))


def evaluate_golden_issues(
    expected_issues: list[GoldenIssue],
    issues: list[ValidationIssue],
) -> EvaluationResult:
    actual_issues = [_adapt_actual_issue(issue) for issue in issues]
    expected_counter = Counter(issue.identity for issue in expected_issues)
    actual_counter = Counter(issue.identity for issue in actual_issues)
    matched = expected_counter & actual_counter
    false_negatives = expected_counter - actual_counter
    false_positives = actual_counter - expected_counter

    return EvaluationResult(
        matched=matched,
        false_positives=false_positives,
        false_negatives=false_negatives,
        relationship_mismatches=_compare_relationships(
            expected_issues,
            actual_issues,
            matched,
        ),
        rule_summary=_build_rule_summary(
            expected_counter,
            matched,
            false_positives,
            false_negatives,
        ),
    )


def _format_identity(identity: IssueIdentity, count: int = 1) -> str:
    suffix = f" (x{count})" if count > 1 else ""
    return (
        f"  row {identity.source_row_number} / {identity.rule} / "
        f"{identity.field} / {identity.severity}{suffix}"
    )


def format_evaluation_failure(result: EvaluationResult) -> str:
    lines = [
        "Synthetic golden fixture rule-quality regression failed.",
        f"Matched: {sum(result.matched.values())}",
        f"False positives: {sum(result.false_positives.values())}",
        f"False negatives: {sum(result.false_negatives.values())}",
        f"Relationship mismatches: {len(result.relationship_mismatches)}",
        "",
        "False negatives:",
    ]
    lines.extend(
        _format_identity(identity, count)
        for identity, count in sorted(result.false_negatives.items())
    )
    if not result.false_negatives:
        lines.append("  none")

    lines.extend(["", "False positives:"])
    lines.extend(
        _format_identity(identity, count)
        for identity, count in sorted(result.false_positives.items())
    )
    if not result.false_positives:
        lines.append("  none")

    lines.extend(["", "Relationship mismatches:"])
    for mismatch in result.relationship_mismatches:
        lines.append(_format_identity(mismatch.identity))
        lines.append(
            "    expected related rows: "
            f"{list(mismatch.expected_related_source_rows)}"
        )
        lines.append(
            f"    actual related rows:   {list(mismatch.actual_related_source_rows)}"
        )
        if mismatch.actual_error:
            lines.append(f"    invalid actual metadata: {mismatch.actual_error}")
    if not result.relationship_mismatches:
        lines.append("  none")

    lines.extend(["", "Rule summary:", "  rule expected matched fp fn"])
    for rule, summary in result.rule_summary.items():
        lines.append(
            f"  {rule} {summary.expected} {summary.matched} "
            f"{summary.false_positives} {summary.false_negatives}"
        )
    return "\n".join(lines)


def test_golden_manifest_covers_current_issue_codes():
    expected_issues = _load_expected_issues()

    assert {issue.identity.rule for issue in expected_issues} == CURRENT_ISSUE_CODES


def test_golden_rule_quality_matches_expected_issues():
    expected_issues = _load_expected_issues()
    report = inspect_uploaded_csv(
        GOLDEN_CATALOG_PATH.name,
        GOLDEN_CATALOG_PATH.read_bytes(),
    )

    result = evaluate_golden_issues(expected_issues, report.issues)

    assert result.is_clean, format_evaluation_failure(result)
