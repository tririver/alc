"""Versioned, closed prompt contracts for translation tasks."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


LANGUAGE_PROMPT_VERSION = "alc.translate.language_prompt.v1"
GLOSSARY_PROMPT_VERSION = "alc.translate.glossary_prompt.v4"
TRANSLATION_PROMPT_VERSION = "alc.translate.blocks_prompt.v11"
REVIEW_PROMPT_VERSION = "alc.translate.review_prompt.v9"


def _closed(
    properties: Mapping[str, Any], required: Sequence[str]
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": dict(properties),
        "required": list(required),
        "additionalProperties": False,
    }


_NONEMPTY = {"type": "string", "minLength": 1}
LANGUAGE_SCHEMA = _closed(
    {
        "language_tag": _NONEMPTY,
        "classification": {
            "type": "string",
            "enum": ["known", "mixed", "unknown"],
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    ("language_tag", "classification", "confidence"),
)

GLOSSARY_SCHEMA = _closed(
    {
        "entries": {
            "type": "array",
            "items": _closed(
                {
                    "term_id": _NONEMPTY,
                    "preferred_translation": _NONEMPTY,
                    "target_definition": _NONEMPTY,
                },
                (
                    "term_id",
                    "preferred_translation",
                    "target_definition",
                ),
            ),
        }
    },
    ("entries",),
)

TRANSLATION_SCHEMA = _closed(
    {
        "translations": {
            "type": "array",
            "items": _closed(
                {
                    "block_id": _NONEMPTY,
                    "text": _NONEMPTY,
                },
                ("block_id", "text"),
            ),
        }
    },
    ("translations",),
)

REVIEW_SCHEMA = _closed(
    {
        "translation_patches": {
            "type": "array",
            "items": _closed(
                {"block_id": _NONEMPTY, "replacement": _NONEMPTY},
                ("block_id", "replacement"),
            ),
        },
        "summary": _NONEMPTY,
    },
    ("translation_patches", "summary"),
)


def language_prompt(samples: Sequence[str]) -> str:
    return _prompt(
        LANGUAGE_PROMPT_VERSION,
        """
Detect the primary natural language of the supplied source samples. Return a
BCP-47-compatible primary language tag. Use classification "mixed" when
multiple substantive languages are present and "unknown" when the evidence is
insufficient. Do not infer the target language and do not translate.
""",
        {"samples": list(samples)},
    )


def glossary_prompt(
    *,
    terms: Sequence[Mapping[str, Any]],
    target_language: str,
    window_ordinal: int,
) -> str:
    return _prompt(
        GLOSSARY_PROMPT_VERSION,
        """
Create a target-language glossary entry for every supplied scientific term.
Return every term_id exactly once and in the supplied order. Add only
preferred_translation and target_definition; the caller attaches the supplied
term text and source evidence locally. matched_sentences are search
grounding, never definitions; do not label, quote, or treat them as a source
definition. Preserve distinctions between nearby terms and do not merge,
deduplicate, select, drop, pad, or reorder terms. This is one byte-bounded
window; a local caller concatenates windows without a reducer.
Keep preferred_translation as plain text. Write target_definition as concise
CommonMark-compatible Markdown in the target language. Use $...$ for inline
formulas and a pair of $$ lines around display formulas. Paragraphs, emphasis,
inline code, and ordinary links are allowed. Do not use raw HTML, headings,
tables, images, or fenced code blocks in a glossary definition.
Interpret each term only in its supplied matched sentences and source evidence.
When it belongs to a title or proper name, explain that source usage rather
than a modern namesake. Use established target-language scientific and
historical terminology instead of a literal calque when a conventional term
exists.
""",
        {
            "target_language": target_language,
            "window_ordinal": window_ordinal,
            "terms": list(terms),
        },
    )


def translation_prompt(
    *,
    blocks: Sequence[Mapping[str, Any]],
    glossary: Sequence[Mapping[str, Any]],
    target_language: str,
    language_result: Mapping[str, Any],
    window_ordinal: int,
) -> str:
    return _prompt(
        TRANSLATION_PROMPT_VERSION,
        """
Translate every supplied source block into the target language. Return each
block ID exactly once and in source order. Keep each block indivisible. Preserve
formulas, code, link targets, internal bibliography citation brackets and
separators, and bibliography entry labels exactly; use the preferred glossary
translations consistently. A supplied Figure or Table contains only its
authored visible caption; translate that caption without inventing an image
description or reproducing Table cells. Table geometry and data, structural
Figures, and all asset identity remain local and are not supplied for
translation. A source_note is an authored note body and must be translated in
full. A note whose entire body is one link is preserved locally and is not
supplied to the model. Copy each block_id exactly; the caller attaches source identity locally.
Return only the translation layer: do not add
explanations, guides, summaries, or learning material.
Translate every language-bearing part of each block from beginning to end;
never omit, summarize, or start partway through. A source block may begin or
end mid-sentence at a page boundary, and that fragment must still be translated.
""",
        {
            "target_language": target_language,
            "language_result": dict(language_result),
            "window_ordinal": window_ordinal,
            "blocks": list(blocks),
            "glossary": list(glossary),
        },
    )


def review_prompt(
    *,
    blocks: Sequence[Mapping[str, Any]],
    translations: Sequence[Mapping[str, Any]],
    glossary: Sequence[Mapping[str, Any]],
    target_language: str,
    window_ordinal: int,
) -> str:
    return _prompt(
        REVIEW_PROMPT_VERSION,
        """
Review only the supplied translation layer for scientific accuracy,
terminology consistency, and fluency. Return text replacement patches only
when needed. Patch block IDs must already exist. Do not change coverage, order,
source identity, formulas, code, links, citation grouping or labels, assets, or
glossary entries.
Do not add commentary to translated text. An empty patch list is valid.
Compare every source block with its translation from beginning to end. Patch
any omission, summary, or truncation, including source fragments that begin or
end mid-sentence at page boundaries.
""",
        {
            "target_language": target_language,
            "window_ordinal": window_ordinal,
            "blocks": list(blocks),
            "translations": list(translations),
            "glossary": list(glossary),
        },
    )


def _prompt(
    version: str, instruction: str, payload: Mapping[str, Any]
) -> str:
    compact_instruction = " ".join(
        line.strip() for line in instruction.strip().splitlines()
    )
    return (
        f"Contract: {version}\n\n{compact_instruction}\n\nInput JSON:\n"
        + json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


__all__ = [
    "GLOSSARY_PROMPT_VERSION",
    "GLOSSARY_SCHEMA",
    "LANGUAGE_PROMPT_VERSION",
    "LANGUAGE_SCHEMA",
    "REVIEW_PROMPT_VERSION",
    "REVIEW_SCHEMA",
    "TRANSLATION_PROMPT_VERSION",
    "TRANSLATION_SCHEMA",
    "glossary_prompt",
    "language_prompt",
    "review_prompt",
    "translation_prompt",
]
