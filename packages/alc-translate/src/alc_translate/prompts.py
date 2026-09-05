"""Versioned, closed prompt contracts for translation tasks."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

LANGUAGE_PROMPT_VERSION = "alc.translate.language_prompt.v1"
GLOSSARY_PROMPT_VERSION = "alc.translate.glossary_prompt.v4"
TRANSLATION_PROMPT_VERSION = "alc.translate.blocks_prompt.v14"
REVIEW_PROMPT_VERSION = "alc.translate.review_prompt.v12"
PROTECTED_ATOM_RESULT_SCHEMA = "alc.translate.protected_atom_result.v1"
PROTECTED_ATOM_REVIEW_RESULT_SCHEMA = (
    "alc.translate.protected_atom_review_result.v1"
)
TEXT_SLOT_RESULT_SCHEMA = "alc.translate.text_slot_result.v1"
TEXT_SLOT_REVIEW_RESULT_SCHEMA = "alc.translate.text_slot_review_result.v1"


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

_ATOM_PART_SCHEMA = {
    "oneOf": [
        _closed({"kind": {"const": "text"}, "text": {"type": "string"}}, ("kind", "text")),
        _closed({"kind": {"const": "atom"}, "atom_id": _NONEMPTY}, ("kind", "atom_id")),
        _closed(
            {
                "kind": {"const": "link"},
                "atom_id": _NONEMPTY,
                "parts": {
                    "type": "array",
                    "items": _closed(
                        {"kind": {"const": "text"}, "text": {"type": "string"}},
                        ("kind", "text"),
                    ),
                },
            },
            ("kind", "atom_id", "parts"),
        ),
    ]
}

TRANSLATION_SCHEMA = _closed(
    {
        "schema_version": {"const": PROTECTED_ATOM_RESULT_SCHEMA},
        "translations": {
            "type": "array",
            "items": _closed(
                {
                    "block_id": _NONEMPTY,
                    "parts": {"type": "array", "items": _ATOM_PART_SCHEMA},
                },
                ("block_id", "parts"),
            ),
        },
    },
    ("schema_version", "translations"),
)

REVIEW_SCHEMA = _closed(
    {
        "schema_version": {"const": PROTECTED_ATOM_REVIEW_RESULT_SCHEMA},
        "translation_patches": {
            "type": "array",
            "items": _closed(
                {
                    "block_id": _NONEMPTY,
                    "parts": {"type": "array", "items": _ATOM_PART_SCHEMA},
                },
                ("block_id", "parts"),
            ),
        },
        "summary": _NONEMPTY,
    },
    ("schema_version", "translation_patches", "summary"),
)


def translation_schema(
    blocks: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build an input-dependent schema that requires every exact text slot."""

    translations: dict[str, Any] = {}
    block_ids: list[str] = []
    for block in blocks:
        block_id = str(block["block_id"])
        block_ids.append(block_id)
        slot_ids = _prompt_text_slot_ids(block)
        translations[block_id] = _closed(
            {
                "text_slots": _closed(
                    {slot_id: {"type": "string"} for slot_id in slot_ids},
                    slot_ids,
                )
            },
            ("text_slots",),
        )
    return _closed(
        {
            "schema_version": {
                "type": "string",
                "const": TEXT_SLOT_RESULT_SCHEMA,
            },
            "translations": _closed(translations, block_ids),
        },
        ("schema_version", "translations"),
    )


def review_schema(blocks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build a closed optional-patch schema over caller-owned text slots."""

    patches: dict[str, Any] = {}
    for block in blocks:
        block_id = str(block["block_id"])
        slot_ids = _prompt_text_slot_ids(block)
        patches[block_id] = _closed(
            {
                "text_slots": _closed(
                    {slot_id: {"type": "string"} for slot_id in slot_ids},
                    slot_ids,
                )
            },
            ("text_slots",),
        )
    return _closed(
        {
            "schema_version": {
                "type": "string",
                "const": TEXT_SLOT_REVIEW_RESULT_SCHEMA,
            },
            "translation_patches": _closed(patches, ()),
            "summary": _NONEMPTY,
        },
        ("schema_version", "translation_patches", "summary"),
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
block ID exactly once as a property of the translations object. Keep each
block indivisible. Each block content is an ordered source skeleton containing
translatable text_slot parts plus caller-owned atom and link positions. Return
only the exact required text_slots object for each block. Translate every slot
value and copy each slot_id exactly; never return, reproduce, move, or invent an
atom_id. The caller deterministically reinserts all immutable atoms after the
text-slot result validates. A normal link contains translatable label slots;
translate those slots while its Markdown delimiters and target remain local.
Formulae, code, citation-link labels, bibliography labels, citation grouping,
and link targets are caller-owned and intentionally not supplied. A supplied Figure or Table
contains only its authored visible caption; translate that caption without
inventing an image description or reproducing Table cells. Table geometry and
data, structural Figures, and all asset identity remain local and are not
supplied for translation. A source_note is an authored note body and must be
translated in full. A note whose entire body is one link is preserved locally
and is not supplied to the model. Copy each block_id exactly.
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
terminology consistency, and fluency. Return text-slot replacement patches only
when needed. `translation_patches` is an object whose optional properties are
existing block IDs. A supplied block patch must contain every exact text_slot
for that block. Never return or rewrite atom IDs: the caller owns and
deterministically reinserts formulas, code, citation grouping/labels, assets,
glossary entries, Markdown link delimiters, and all link targets.
Do not add commentary to translated text. An empty patch object is valid.
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


def _prompt_text_slot_ids(block: Mapping[str, Any]) -> list[str]:
    content = block.get("content")
    if not isinstance(content, Mapping):
        raise ValueError("prompt block content must be an object")
    parts = content.get("parts")
    if not isinstance(parts, Sequence) or isinstance(parts, (str, bytes)):
        raise ValueError("prompt block parts must be an array")
    output: list[str] = []
    for part in parts:
        if not isinstance(part, Mapping):
            raise ValueError("prompt part must be an object")
        if part.get("kind") == "text_slot":
            output.append(str(part["slot_id"]))
        elif part.get("kind") == "link":
            labels = part.get("parts")
            if not isinstance(labels, Sequence) or isinstance(labels, (str, bytes)):
                raise ValueError("prompt link parts must be an array")
            output.extend(str(label["slot_id"]) for label in labels)
    if len(output) != len(set(output)):
        raise ValueError("prompt text-slot IDs must be unique")
    return output


__all__ = [
    "GLOSSARY_PROMPT_VERSION",
    "GLOSSARY_SCHEMA",
    "LANGUAGE_PROMPT_VERSION",
    "LANGUAGE_SCHEMA",
    "PROTECTED_ATOM_RESULT_SCHEMA",
    "PROTECTED_ATOM_REVIEW_RESULT_SCHEMA",
    "TEXT_SLOT_RESULT_SCHEMA",
    "TEXT_SLOT_REVIEW_RESULT_SCHEMA",
    "REVIEW_PROMPT_VERSION",
    "REVIEW_SCHEMA",
    "TRANSLATION_PROMPT_VERSION",
    "TRANSLATION_SCHEMA",
    "glossary_prompt",
    "language_prompt",
    "review_prompt",
    "review_schema",
    "translation_prompt",
    "translation_schema",
]
