"""Companion's closed identity projection for an acquired HTML source."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


HTML_SOURCE_BUNDLE_SCHEMA = "ac.document.html_source_bundle.v1"
HTML_SOURCE_EXPORT_SCHEMA = "ac.document.html_source_export.v1"
HTML_SOURCE_BINDING_SCHEMA = "alc.companion.html_source_binding.v1"
_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class HTMLSourceBundleBinding:
    """Stable ALC identity projected from an ACF HTML-source export."""

    bundle_digest: str
    primary_artifact_digest: str
    materialized_source_digest: str
    requested_url: str
    final_url: str
    schema_version: str = HTML_SOURCE_BINDING_SCHEMA
    bundle_schema_version: str = HTML_SOURCE_BUNDLE_SCHEMA
    export_schema_version: str = HTML_SOURCE_EXPORT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != HTML_SOURCE_BINDING_SCHEMA:
            raise ValueError("unsupported HTML source binding schema")
        if self.bundle_schema_version != HTML_SOURCE_BUNDLE_SCHEMA:
            raise ValueError("unsupported HTML source bundle schema")
        if self.export_schema_version != HTML_SOURCE_EXPORT_SCHEMA:
            raise ValueError("unsupported HTML source export schema")
        for key in (
            "bundle_digest",
            "primary_artifact_digest",
            "materialized_source_digest",
        ):
            if _SHA256.fullmatch(getattr(self, key)) is None:
                raise ValueError(f"{key} must be a SHA-256 digest")
        for key in ("requested_url", "final_url"):
            value = getattr(self, key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} must be a non-empty string")
            object.__setattr__(self, key, value.strip())


def encode_html_source_bundle_binding(
    value: HTMLSourceBundleBinding,
) -> dict[str, str]:
    if not isinstance(value, HTMLSourceBundleBinding):
        raise ValueError("source_bundle must be an HTMLSourceBundleBinding")
    return {
        "schema_version": value.schema_version,
        "bundle_schema_version": value.bundle_schema_version,
        "export_schema_version": value.export_schema_version,
        "bundle_digest": value.bundle_digest,
        "primary_artifact_digest": value.primary_artifact_digest,
        "materialized_source_digest": value.materialized_source_digest,
        "requested_url": value.requested_url,
        "final_url": value.final_url,
    }


def decode_html_source_bundle_binding(
    value: Mapping[str, Any],
) -> HTMLSourceBundleBinding:
    fields = {
        "schema_version",
        "bundle_schema_version",
        "export_schema_version",
        "bundle_digest",
        "primary_artifact_digest",
        "materialized_source_digest",
        "requested_url",
        "final_url",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("HTML source bundle binding has invalid fields")
    values = dict(value)
    if any(not isinstance(values[key], str) for key in fields):
        raise ValueError("HTML source bundle binding fields must be strings")
    return HTMLSourceBundleBinding(**values)


@dataclass(frozen=True)
class HTMLSourceManifest:
    """Validated ACF materialized export and its Companion-facing details."""

    binding: HTMLSourceBundleBinding
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.binding, HTMLSourceBundleBinding):
            raise ValueError("binding must be an HTMLSourceBundleBinding")
        if any(not isinstance(item, str) or not item for item in self.warnings):
            raise ValueError("warnings must contain non-empty strings")


def load_html_source_manifest(
    manifest_path: str | Path,
    *,
    source_path: str | Path,
) -> HTMLSourceManifest:
    """Validate an ACF export and verify its explicit local primary source."""

    try:
        from ac_document import (
            HTMLSourceBundleError,
            html_source_bundle_from_document,
            verify_html_source_bundle_export,
        )
    except ImportError as exc:
        raise ValueError(
            "installed ac-document lacks HTML source export support"
        ) from exc
    manifest = Path(manifest_path).resolve()
    supplied_source = Path(source_path).resolve()
    if manifest.name != "manifest.json":
        raise ValueError("HTML source manifest must be named manifest.json")
    try:
        exported = verify_html_source_bundle_export(manifest.parent)
    except (HTMLSourceBundleError, ValueError) as exc:
        raise ValueError("HTML source manifest verification failed") from exc
    materialized = exported["materialized_source"]
    expected_source = (manifest.parent / materialized["path"]).resolve()
    if supplied_source != expected_source:
        raise ValueError(
            "source path does not match the HTML source manifest materialization"
        )
    bundle = html_source_bundle_from_document(exported["bundle"])
    return HTMLSourceManifest(
        binding=HTMLSourceBundleBinding(
            bundle_digest=bundle.bundle_digest,
            primary_artifact_digest=bundle.primary.artifact_digest,
            materialized_source_digest=materialized["artifact_digest"],
            requested_url=bundle.requested_url,
            final_url=bundle.final_url,
        ),
        warnings=tuple(str(item) for item in bundle.warnings),
    )


__all__ = [
    "HTML_SOURCE_BINDING_SCHEMA",
    "HTML_SOURCE_BUNDLE_SCHEMA",
    "HTML_SOURCE_EXPORT_SCHEMA",
    "HTMLSourceBundleBinding",
    "HTMLSourceManifest",
    "decode_html_source_bundle_binding",
    "encode_html_source_bundle_binding",
    "load_html_source_manifest",
]
