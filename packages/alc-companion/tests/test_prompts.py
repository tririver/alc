from __future__ import annotations

from alc_companion.prompts import (
    AUTHOR_IDENTITY_PROMPT_VERSION,
    HISTORICAL_AUTHOR_IDENTITY_PROMPT_VERSION_V3,
    HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V16,
    HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V17,
    HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V16,
    HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V17,
    author_identity_prompt,
    chapter_guide_proposer_instructions,
    chapter_guide_reviewer_instructions,
)
from alc_companion.request_contracts import CompanionGenerationRecipe


def test_author_identity_prompt_embeds_bounded_front_matter_evidence() -> None:
    prompt = author_identity_prompt(
        title="A paper",
        auto_candidates=[],
        block_access=[],
        front_matter_evidence=[
            {
                "block_id": "block-author",
                "text": "Ada Example, Example Institute.",
            }
        ],
    )

    assert AUTHOR_IDENTITY_PROMPT_VERSION.endswith(".v4")
    assert '"block_id":"block-author"' in prompt
    assert '"text":"Ada Example, Example Institute."' in prompt
    assert "Do not request a host action" in prompt


def test_v3_author_identity_prompt_remains_decodable() -> None:
    recipe = CompanionGenerationRecipe(
        author_identity_prompt=HISTORICAL_AUTHOR_IDENTITY_PROMPT_VERSION_V3
    )
    prompt = author_identity_prompt(
        title="Historical paper",
        auto_candidates=[],
        block_access=[],
        front_matter_evidence=[
            {"block_id": "ignored", "text": "new-only evidence"}
        ],
        version=recipe.author_identity_prompt,
    )

    assert HISTORICAL_AUTHOR_IDENTITY_PROMPT_VERSION_V3 in prompt
    assert "front_matter_evidence" not in prompt


def test_guide_prompts_treat_paratext_as_model_judgment() -> None:
    proposer = chapter_guide_proposer_instructions()
    reviewer = chapter_guide_reviewer_instructions()

    assert "current source segment" in proposer
    assert "current real chapter" not in proposer
    assert "current source segment" in reviewer
    assert "current real chapter" not in reviewer
    for prompt in (proposer, reviewer):
        assert "publication metadata" in prompt
        assert (
            "prefer `chapter_guide: null`" in prompt
            or "prefer a null guide" in prompt
        )
        assert "title keywords" in prompt
        assert "preface" in prompt
        assert "cross-segment reading route" in prompt
        assert "specific reading action or understanding increment" in prompt


def test_guide_prompts_bind_local_section_numbers() -> None:
    proposer = chapter_guide_proposer_instructions()
    reviewer = chapter_guide_reviewer_instructions()

    for prompt in (proposer, reviewer):
        assert "section_number" in prompt
        assert "source heading" in prompt or "source-heading" in prompt
        assert "sections" in prompt


def test_current_guide_prompts_require_canonical_display_math() -> None:
    proposer = chapter_guide_proposer_instructions()
    reviewer = chapter_guide_reviewer_instructions()

    for prompt in (proposer, reviewer):
        assert "display-math" in prompt or "display math" in prompt
        assert "separate lines" in prompt


def test_v17_guide_prompt_recipe_remains_decodable() -> None:
    recipe = CompanionGenerationRecipe(
        chapter_guide_prompt=HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V17,
        chapter_guide_review_prompt=(
            HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V17
        ),
    )

    proposer = chapter_guide_proposer_instructions(
        recipe.chapter_guide_prompt
    )
    reviewer = chapter_guide_reviewer_instructions(
        recipe.chapter_guide_review_prompt
    )
    assert HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V17 in proposer
    assert HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V17 in reviewer
    assert "display-math" not in proposer
    assert "display-math" not in reviewer


def test_historical_guide_prompt_recipe_remains_decodable() -> None:
    recipe = CompanionGenerationRecipe(
        chapter_guide_prompt=HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V16,
        chapter_guide_review_prompt=(
            HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V16
        ),
    )

    proposer = chapter_guide_proposer_instructions(
        recipe.chapter_guide_prompt
    )
    reviewer = chapter_guide_reviewer_instructions(
        recipe.chapter_guide_review_prompt
    )
    assert HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V16 in proposer
    assert HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V16 in reviewer
    assert "numeral printed in the source heading" not in proposer
    assert "source-heading numerals" not in reviewer
