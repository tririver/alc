from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from ac_llm import ModelSelection
from ac_document import (
    RichDocumentParserService,
    SourceFormat,
    SourceOrigin,
    SourceOriginKind,
    SourceRepository,
)

from alc_companion.request_contracts import (
    COMPANION_BUILD_REQUEST_SCHEMA,
    LEGACY_COMPANION_BUILD_REQUEST_SCHEMA,
    COMPANION_GENERATION_RECIPE_SCHEMA,
    EDITORIAL_COMPANION_GENERATION_RECIPE_SCHEMA,
    EDITORIAL_PROPOSER_PROMPT_VERSION,
    EDITORIAL_REVIEWER_PROMPT_VERSION,
    CompanionBuildRequest,
    CompanionGenerationRecipe,
    decode_build_request,
    decode_generation_recipe,
    encode_build_request,
    encode_generation_recipe,
)
from alc_companion.source_bundle import HTMLSourceBundleBinding
from alc_companion.source_identity import resolve_document_identity
from alc_companion.service import companion_run_id


def _document(tmp_path: Path, text: str):
    repository = SourceRepository(tmp_path / "paper")
    artifact = repository.store_bytes(
        text.encode("utf-8"),
        source_format=SourceFormat.MARKDOWN,
        origin=SourceOrigin(SourceOriginKind.LOCAL_IMPORT, locator="source.md"),
    )
    return RichDocumentParserService(repository).parse_source(artifact)


def test_document_identity_prefers_metadata_then_shallow_heading(
    tmp_path: Path,
) -> None:
    document = _document(
        tmp_path, "## Deep\n\nBody.\n\n# Shallow\n\nMore.\n"
    )
    assert resolve_document_identity(document).title == "Shallow"
    with_metadata = replace(
        document, metadata={**document.metadata, "title": "Metadata"}
    )
    assert resolve_document_identity(with_metadata).title == "Metadata"


def test_current_request_and_recipe_round_trip_only(tmp_path: Path) -> None:
    request = CompanionBuildRequest(
        _document(tmp_path, "# Source\n\nBody.\n"),
        authors=("Author",),
    )
    request_document = encode_build_request(request)
    recipe = CompanionGenerationRecipe()
    recipe_document = encode_generation_recipe(recipe)
    assert request_document["schema_version"] == LEGACY_COMPANION_BUILD_REQUEST_SCHEMA
    assert "source_bundle" not in request_document
    assert request_document["reviewed_supplements"] == []
    assert recipe_document["schema_version"] == COMPANION_GENERATION_RECIPE_SCHEMA
    assert recipe_document == {
        "schema_version": "alc.companion.generation_recipe.v19",
        "model": {"provider": "auto", "model": None, "tier": "medium"},
        "approx_term_count": 50,
        "author_identity_prompt": "alc.companion.author-identity-prompt.v4",
        "chapter_guide_prompt": "alc.companion.chapter-learning-prompt.v18",
        "chapter_guide_review_prompt": (
            "alc.companion.chapter-learning-review-prompt.v18"
        ),
        "chapter_guide_max_rounds": 3,
        "chapter_guide_review_final_round": False,
            "equation_label_visual_prompt": (
                "ac.document.equation_label_visual_prompt.v1"
            ),
        "reader_publication_recipe": "alc.companion.reader_publication.v1",
    }
    decoded_request = decode_build_request(request_document)
    assert decoded_request.source.document_digest == request.source.document_digest
    assert decoded_request.authors == request.authors
    assert decoded_request.target_language == request.target_language
    assert decode_generation_recipe(recipe_document) == recipe


def test_generation_recipe_round_trips_reasoning_effort_and_accepts_legacy_model() -> None:
    recipe = CompanionGenerationRecipe(
        model=ModelSelection(
            provider="codex",
            model="gpt-5.6-terra",
            reasoning_effort="high",
        )
    )
    document = encode_generation_recipe(recipe)

    assert document["model"]["reasoning_effort"] == "high"
    assert decode_generation_recipe(document) == recipe

    legacy = encode_generation_recipe(
        replace(recipe, model=ModelSelection("codex", "gpt-5.6-terra"))
    )
    assert "reasoning_effort" not in legacy["model"]
    assert decode_generation_recipe(legacy).model.reasoning_effort is None


def test_html_source_bundle_binding_has_a_distinct_durable_request_contract(
    tmp_path: Path,
) -> None:
    binding = HTMLSourceBundleBinding(
        bundle_digest="a" * 64,
        primary_artifact_digest="b" * 64,
        materialized_source_digest="c" * 64,
        requested_url="https://example.test/paper.html",
        final_url="https://example.test/paper.html",
    )
    request = CompanionBuildRequest(
        _document(tmp_path, "# Source\n\nBody.\n"),
        source_bundle=binding,
    )

    encoded = encode_build_request(request)
    decoded = decode_build_request(encoded)

    assert encoded["schema_version"] == COMPANION_BUILD_REQUEST_SCHEMA
    assert encoded["source_bundle"] == {
        "schema_version": "alc.companion.html_source_binding.v1",
        "bundle_schema_version": "ac.document.html_source_bundle.v1",
        "export_schema_version": "ac.document.html_source_export.v1",
        "bundle_digest": "a" * 64,
        "primary_artifact_digest": "b" * 64,
        "materialized_source_digest": "c" * 64,
        "requested_url": "https://example.test/paper.html",
        "final_url": "https://example.test/paper.html",
    }
    assert decoded.source_bundle == binding


def test_html_source_bundle_binding_changes_the_companion_run_identity(
    tmp_path: Path,
) -> None:
    source = _document(tmp_path, "# Source\n\nBody.\n")
    recipe = CompanionGenerationRecipe(
        model=ModelSelection(provider="codex", model="gpt-5.6-luna", tier="medium")
    )
    first = CompanionBuildRequest(
        source,
        source_bundle=HTMLSourceBundleBinding(
            bundle_digest="a" * 64,
            primary_artifact_digest="b" * 64,
            materialized_source_digest="c" * 64,
            requested_url="https://example.test/paper.html",
            final_url="https://example.test/first.html",
        ),
    )
    changed_provenance = replace(
        first,
        source_bundle=HTMLSourceBundleBinding(
            bundle_digest="a" * 64,
            primary_artifact_digest="b" * 64,
            materialized_source_digest="c" * 64,
            requested_url="https://example.test/paper.html",
            final_url="https://example.test/second.html",
        ),
    )

    assert companion_run_id(first, recipe) != companion_run_id(
        changed_provenance, recipe
    )
    assert companion_run_id(first, recipe) != companion_run_id(
        CompanionBuildRequest(source), recipe
    )


def test_editorial_recipe_uses_current_schema_only_when_enabled() -> None:
    recipe = CompanionGenerationRecipe(cross_chapter_editorial_review=True)

    document = encode_generation_recipe(recipe)

    assert document["schema_version"] == (
        EDITORIAL_COMPANION_GENERATION_RECIPE_SCHEMA
    )
    assert document["cross_chapter_editorial_review"] is True
    assert document["editorial_proposer_prompt"] == (
        EDITORIAL_PROPOSER_PROMPT_VERSION
    )
    assert document["editorial_reviewer_prompt"] == (
        EDITORIAL_REVIEWER_PROMPT_VERSION
    )
    assert decode_generation_recipe(document) == recipe


def test_editorial_recipe_cannot_disable_editorial_review() -> None:
    document = encode_generation_recipe(
        CompanionGenerationRecipe(cross_chapter_editorial_review=True)
    )
    document["cross_chapter_editorial_review"] = False

    with pytest.raises(ValueError, match="editorial generation recipe requires"):
        decode_generation_recipe(document)


def test_v7_request_is_rejected(
    tmp_path: Path,
) -> None:
    request = encode_build_request(
        CompanionBuildRequest(_document(tmp_path, "# Source\n\nBody.\n"))
    )
    request["schema_version"] = "alc.companion.build_request.v7"
    del request["reviewed_supplements"]

    with pytest.raises(ValueError, match="unsupported"):
        decode_build_request(request)


def test_old_request_and_recipe_schemas_are_rejected(tmp_path: Path) -> None:
    request = encode_build_request(
        CompanionBuildRequest(_document(tmp_path, "# Source\n\nBody.\n"))
    )
    for version in ("v6", "v7"):
        request["schema_version"] = f"alc.companion.build_request.{version}"
        with pytest.raises(ValueError, match="unsupported"):
            decode_build_request(request)

    recipe = encode_generation_recipe(CompanionGenerationRecipe())
    for version in ("v15", "v17", "v18"):
        recipe["schema_version"] = f"alc.companion.generation_recipe.{version}"
        with pytest.raises(ValueError, match="unsupported"):
            decode_generation_recipe(recipe)
