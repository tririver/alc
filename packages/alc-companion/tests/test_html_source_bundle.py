from __future__ import annotations

import json
from pathlib import Path

import pytest

from alc_companion.source_bundle import (
    HTML_SOURCE_BINDING_SCHEMA,
    HTML_SOURCE_BUNDLE_SCHEMA,
    HTMLSourceBundleBinding,
    decode_html_source_bundle_binding,
    encode_html_source_bundle_binding,
    load_html_source_manifest,
)


def _binding() -> HTMLSourceBundleBinding:
    return HTMLSourceBundleBinding(
        bundle_digest="a" * 64,
        primary_artifact_digest="b" * 64,
        materialized_source_digest="c" * 64,
        requested_url="https://example.test/paper.html",
        final_url="https://example.test/paper-v2.html",
    )


def test_binding_round_trips_the_closed_alc_projection() -> None:
    binding = _binding()

    assert encode_html_source_bundle_binding(binding) == {
        "schema_version": HTML_SOURCE_BINDING_SCHEMA,
        "bundle_schema_version": HTML_SOURCE_BUNDLE_SCHEMA,
        "export_schema_version": "ac.document.html_source_export.v1",
        "bundle_digest": "a" * 64,
        "primary_artifact_digest": "b" * 64,
        "materialized_source_digest": "c" * 64,
        "requested_url": "https://example.test/paper.html",
        "final_url": "https://example.test/paper-v2.html",
    }
    assert decode_html_source_bundle_binding(
        encode_html_source_bundle_binding(binding)
    ) == binding


@pytest.mark.parametrize(
    "change, message",
    [
        (("schema_version", "unexpected.schema.v1"), "binding schema"),
        (("bundle_schema_version", "unexpected.schema.v1"), "bundle schema"),
        (("bundle_digest", "not-a-sha256"), "bundle_digest"),
        (("primary_artifact_digest", "not-a-sha256"), "primary_artifact_digest"),
        (("materialized_source_digest", "not-a-sha256"), "materialized_source_digest"),
        (("requested_url", ""), "requested_url"),
        (("final_url", ""), "final_url"),
    ],
)
def test_binding_rejects_invalid_closed_fields(
    change: tuple[str, str], message: str
) -> None:
    binding = _binding()

    with pytest.raises(ValueError, match=message):
        HTMLSourceBundleBinding(**{**binding.__dict__, change[0]: change[1]})


def test_binding_decoder_rejects_extra_or_missing_fields() -> None:
    document = encode_html_source_bundle_binding(_binding())
    document["untrusted_acf_field"] = "not part of the ALC projection"

    with pytest.raises(ValueError, match="invalid fields"):
        decode_html_source_bundle_binding(document)

    document = encode_html_source_bundle_binding(_binding())
    del document["final_url"]

    with pytest.raises(ValueError, match="invalid fields"):
        decode_html_source_bundle_binding(document)


def _ac_document_export(tmp_path: Path) -> tuple[Path, Path]:
    try:
        from ac_document import (
            HTMLAcquisitionPolicy,
            HTMLSourceBundle,
            HTMLSourceDependency,
            HTMLSourceWarning,
            SourceFormat,
            SourceOrigin,
            SourceOriginKind,
            SourceRepository,
            html_source_bundle_export_to_document,
        )
    except ImportError:
        pytest.skip("ac-document HTML source export support is unavailable")
    primary_bytes = b'<img src="figure.png"><img src="missing.png">'
    materialized_bytes = primary_bytes + b"\n"
    repository = SourceRepository(tmp_path / "cache")
    primary = repository.store_bytes(
        primary_bytes,
        source_format=SourceFormat.HTML,
        media_type="text/html",
        origin=SourceOrigin(
            SourceOriginKind.REMOTE_PROVIDER,
            provider="web",
            locator="https://example.test/paper.html",
        ),
    )
    asset = repository.store_asset_bytes(b"PNG", media_type="image/png")
    available_dependency = HTMLSourceDependency(
        ordinal=0,
        element="img",
        attribute="src",
        authored_target="figure.png",
        request_url="https://example.test/figure.png",
        resolved_url="https://example.test/figure.png",
        availability="available",
        materialization_path="figure.png",
        media_type=asset.media_type,
        artifact_digest=asset.artifact_digest,
        size=asset.size,
    )
    unavailable_dependency = HTMLSourceDependency(
        ordinal=1,
        element="img",
        attribute="src",
        authored_target="missing.png",
        availability="unavailable",
        error_code="html_dependency_fetch_failed",
        error_message="dependency could not be fetched",
    )
    bundle = HTMLSourceBundle(
        primary=primary,
        requested_url="https://example.test/paper.html",
        final_url="https://example.test/paper-v2.html",
        base_url="https://example.test/paper-v2.html",
        acquisition_policy=HTMLAcquisitionPolicy().to_document(),
        dependencies=(available_dependency, unavailable_dependency),
        warnings=(
            HTMLSourceWarning(
                code=unavailable_dependency.error_code,
                message=unavailable_dependency.error_message,
                dependency_ordinal=unavailable_dependency.ordinal,
                element=unavailable_dependency.element,
                attribute=unavailable_dependency.attribute,
                authored_target=unavailable_dependency.authored_target,
            ),
        ),
    )
    export = html_source_bundle_export_to_document(
        bundle, materialized_source=materialized_bytes
    )
    root = tmp_path / "materialized"
    root.mkdir()
    manifest = root / "manifest.json"
    source = root / "source.html"
    manifest.write_text(json.dumps(export), encoding="utf-8")
    source.write_bytes(materialized_bytes)
    (root / "figure.png").write_bytes(b"PNG")
    return manifest, source


def test_manifest_loader_uses_acf_decoders_and_projects_warnings(
    tmp_path: Path,
) -> None:
    manifest, source = _ac_document_export(tmp_path)

    loaded = load_html_source_manifest(manifest, source_path=source)

    assert loaded.binding.bundle_schema_version == HTML_SOURCE_BUNDLE_SCHEMA
    assert loaded.binding.export_schema_version == "ac.document.html_source_export.v1"
    assert (
        loaded.binding.primary_artifact_digest
        != loaded.binding.materialized_source_digest
    )
    assert loaded.binding.requested_url == "https://example.test/paper.html"
    assert loaded.binding.final_url == "https://example.test/paper-v2.html"
    assert loaded.warnings == (
        "html_dependency_fetch_failed: dependency could not be fetched: missing.png",
    )


def test_manifest_loader_rejects_source_path_or_content_mismatch(
    tmp_path: Path,
) -> None:
    manifest, source = _ac_document_export(tmp_path)
    other = tmp_path / "other.html"
    other.write_bytes(source.read_bytes())

    with pytest.raises(ValueError, match="source path"):
        load_html_source_manifest(manifest, source_path=other)

    source.write_text("different", encoding="utf-8")
    with pytest.raises(ValueError, match="verification failed"):
        load_html_source_manifest(manifest, source_path=source)


def test_manifest_loader_rejects_tampered_materialized_resource(
    tmp_path: Path,
) -> None:
    manifest, source = _ac_document_export(tmp_path)
    (manifest.parent / "figure.png").write_bytes(b"tampered")

    with pytest.raises(ValueError, match="verification failed"):
        load_html_source_manifest(manifest, source_path=source)
