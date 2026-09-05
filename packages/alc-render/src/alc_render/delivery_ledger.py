"""Versioned, publication-owned accounting for explicit Reader degradation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

DELIVERY_LEDGER_SCHEMA = "alc.companion.delivery_ledger.v1"
DELIVERY_GRADES = frozenset({"complete", "degraded", "source_only"})
STAGE_STATUSES = frozenset({"complete", "degraded", "source_only", "skipped"})
DELIVERY_STAGES = (
    "source",
    "translation",
    "guides",
    "glossary",
    "editorial",
    "resources",
    "render",
)
ISSUE_FIELDS = frozenset(
    {
        "issue_id",
        "category",
        "scope",
        "fallback",
        "affected_count",
        "source_preserved",
        "retry",
        "evidence",
    }
)
STAGE_FIELDS = frozenset({"stage", "status", "expected", "produced", "accounted"})
LEDGER_FIELDS = frozenset(
    {
        "schema_version",
        "delivery_grade",
        "stages",
        "issues",
        "unaccounted_source_units",
    }
)


class DeliveryLedgerError(ValueError):
    """A delivery report is absent, tampered, or silently incomplete."""


def validate_delivery_ledger(
    value: Mapping[str, Any],
    *,
    source_unit_count: int | None = None,
) -> dict[str, Any]:
    """Validate the small public contract without trusting display text."""

    if not isinstance(value, Mapping) or set(value) != LEDGER_FIELDS:
        raise DeliveryLedgerError("delivery ledger has invalid fields")
    if value.get("schema_version") != DELIVERY_LEDGER_SCHEMA:
        raise DeliveryLedgerError("delivery ledger has an unsupported schema")
    grade = value.get("delivery_grade")
    if grade not in DELIVERY_GRADES:
        raise DeliveryLedgerError("delivery ledger has an invalid delivery grade")
    stages = value.get("stages")
    issues = value.get("issues")
    unaccounted = value.get("unaccounted_source_units")
    if not isinstance(stages, Sequence) or isinstance(stages, (str, bytes)) or not stages:
        raise DeliveryLedgerError("delivery ledger must account for stages")
    if not isinstance(issues, Sequence) or isinstance(issues, (str, bytes)):
        raise DeliveryLedgerError("delivery ledger issues must be an array")
    if type(unaccounted) is not int or unaccounted < 0:
        raise DeliveryLedgerError("delivery ledger source accounting is invalid")
    if unaccounted:
        raise DeliveryLedgerError("delivery ledger has unaccounted source units")

    normalized_stages: list[dict[str, Any]] = []
    for item in stages:
        if not isinstance(item, Mapping) or set(item) != STAGE_FIELDS:
            raise DeliveryLedgerError("delivery ledger stage has invalid fields")
        name = item.get("stage")
        status = item.get("status")
        if not isinstance(name, str) or not name:
            raise DeliveryLedgerError("delivery ledger stage name is invalid")
        if status not in STAGE_STATUSES:
            raise DeliveryLedgerError("delivery ledger stage has an invalid status")
        counts = tuple(
            item.get(key) for key in ("expected", "produced", "accounted")
        )
        if any(type(count) is not int or count < 0 for count in counts):
            raise DeliveryLedgerError("delivery ledger stage counts are invalid")
        expected, produced, accounted = counts
        if accounted != expected or produced > expected:
            raise DeliveryLedgerError("delivery ledger stage is not fully accounted")
        if status == "complete" and produced != expected:
            raise DeliveryLedgerError("complete delivery ledger stage is incomplete")
        if status == "skipped" and (expected or produced or accounted):
            raise DeliveryLedgerError("skipped delivery ledger stage has content")
        normalized_stages.append(dict(item))
    if tuple(item["stage"] for item in normalized_stages) != DELIVERY_STAGES:
        raise DeliveryLedgerError("delivery ledger stage set is incomplete")
    source_stage = next(
        (item for item in normalized_stages if item["stage"] == "source"),
        None,
    )
    if source_stage is None:
        raise DeliveryLedgerError("delivery ledger lacks source accounting")
    if (
        source_unit_count is not None
        and source_stage["expected"] != source_unit_count
    ):
        raise DeliveryLedgerError("delivery ledger source count differs from publication")
    if source_stage["produced"] != source_stage["expected"]:
        raise DeliveryLedgerError("delivery ledger does not preserve every source unit")

    normalized_issues: list[dict[str, Any]] = []
    issue_ids: set[str] = set()
    for item in issues:
        if not isinstance(item, Mapping) or set(item) != ISSUE_FIELDS:
            raise DeliveryLedgerError("delivery ledger issue has invalid fields")
        issue_id = item.get("issue_id")
        if not isinstance(issue_id, str) or not issue_id or issue_id in issue_ids:
            raise DeliveryLedgerError("delivery ledger issue IDs must be unique")
        if any(
            not isinstance(item.get(key), str) or not item[key]
            for key in ("category", "scope", "fallback", "retry", "evidence")
        ) or (
            type(item.get("affected_count")) is not int
            or item["affected_count"] <= 0
        ) or not isinstance(item.get("source_preserved"), bool):
            raise DeliveryLedgerError("delivery ledger issue is malformed")
        issue_ids.add(issue_id)
        normalized_issues.append(dict(item))

    issues_by_stage = {stage: [] for stage in DELIVERY_STAGES}
    deficit_issues_by_stage = {stage: [] for stage in DELIVERY_STAGES}
    for issue in normalized_issues:
        stage = _issue_stage(issue["category"])
        if stage is not None:
            issues_by_stage[stage].append(issue)
        deficit_stage = _deficit_issue_stage(issue["category"])
        if deficit_stage is not None:
            deficit_issues_by_stage[deficit_stage].append(issue)
    for stage in normalized_stages:
        deficit = stage["expected"] - stage["produced"]
        related = issues_by_stage[stage["stage"]]
        affected = sum(
            item["affected_count"]
            for item in deficit_issues_by_stage[stage["stage"]]
        )
        if deficit and affected != deficit:
            raise DeliveryLedgerError(
                "delivery ledger stage deficit does not match scoped issues"
            )
        if (
            stage["stage"] != "source"
            and stage["status"] in {"degraded", "source_only"}
            and not related
        ):
            raise DeliveryLedgerError(
                "degraded delivery ledger stage lacks scoped issues"
            )

    has_degradation = bool(normalized_issues) or any(
        item["status"] in {"degraded", "source_only"}
        for item in normalized_stages
    )
    if grade == "complete" and has_degradation:
        raise DeliveryLedgerError("delivery ledger hides degradation as complete")
    if grade != "complete" and not has_degradation:
        raise DeliveryLedgerError(
            "delivery ledger claims degradation without evidence"
        )
    if grade == "source_only" and source_stage["status"] != "source_only":
        raise DeliveryLedgerError(
            "source-only delivery ledger lacks a source-only stage"
        )
    return {
        "schema_version": DELIVERY_LEDGER_SCHEMA,
        "delivery_grade": grade,
        "stages": normalized_stages,
        "issues": normalized_issues,
        "unaccounted_source_units": unaccounted,
    }


def _deficit_issue_stage(category: str) -> str | None:
    if category == "resource_unavailable":
        return "resources"
    if category == "editorial_unavailable":
        return "editorial"
    if category.endswith("_source_only"):
        prefix = category.removesuffix("_source_only")
        return {"guide": "guides", "resource": "resources"}.get(
            prefix, prefix
        )
    if category.endswith("_omitted"):
        prefix = category.removesuffix("_omitted")
        if prefix.startswith("guide_"):
            return "guides"
        return {"resource": "resources"}.get(prefix, prefix)
    return None


def _issue_stage(category: str) -> str | None:
    if category.startswith("translation_"):
        return "translation"
    if category.startswith("guide_"):
        return "guides"
    if category.startswith("glossary_"):
        return "glossary"
    if category.startswith("editorial_"):
        return "editorial"
    if category.startswith("resource_"):
        return "resources"
    if category.startswith("render_"):
        return "render"
    return None


def delivery_ledger_from_profile(
    profile: Mapping[str, Any], *, source_unit_count: int
) -> dict[str, Any] | None:
    """Return a validated optional ledger stored in a Reader profile."""

    value = profile.get("delivery_ledger")
    if value is None:
        return None
    return validate_delivery_ledger(value, source_unit_count=source_unit_count)


__all__ = [
    "DELIVERY_GRADES",
    "DELIVERY_LEDGER_SCHEMA",
    "DELIVERY_STAGES",
    "DeliveryLedgerError",
    "delivery_ledger_from_profile",
    "validate_delivery_ledger",
]
