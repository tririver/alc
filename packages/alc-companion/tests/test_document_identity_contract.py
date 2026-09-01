from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from ac_document import (
    RichDocumentParserService,
    SourceFormat,
    SourceOrigin,
    SourceOriginKind,
    SourceRepository,
)

from alc_companion.request_contracts import (
    COMPANION_BUILD_REQUEST_SCHEMA,
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
from alc_companion.source_identity import resolve_document_identity


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
    assert request_document["schema_version"] == COMPANION_BUILD_REQUEST_SCHEMA
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
