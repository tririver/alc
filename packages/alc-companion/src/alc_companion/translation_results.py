"""Validate and expose native alc-translate selection results to Companion."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ac_document import RichBlock, RichBlockKind, RichDocument
from ac_jobs import AcJobsError, RunContext
from alc_render import (
    AnchorKind,
    FragmentRevision,
    anchor_block_from_rich_block,
    decode_fragment_revision,
    source_identity_from_rich_document,
)
from alc_translate import (
    TranslationResult,
    TranslationSourceError,
    canonicalize_translation_markdown,
    validate_translation_markdown,
)

from .model_source import model_source_block_view


class CompanionTranslationResultError(ValueError):
    """A chapter translation result is not usable as a native render layer."""


@dataclass(frozen=True)
class ValidatedTranslationSelection:
    result: TranslationResult
    revisions: tuple[FragmentRevision, ...]
    view_records: tuple[Mapping[str, str], ...]
    delivery_issues: tuple[Mapping[str, Any], ...]


def load_translation_selection(
    context: RunContext,
    value: Mapping[str, Any],
    *,
    source: RichDocument,
    block_ids: Sequence[str],
    target_language: str,
) -> ValidatedTranslationSelection:
    """Load one selected-block result and verify every immutable revision."""

    try:
        result = TranslationResult.from_document(value)
    except (TypeError, ValueError) as exc:
        raise CompanionTranslationResultError(
            "alc-translate returned an invalid native result"
        ) from exc
    source_identity = source_identity_from_rich_document(source)
    if (
        result.mode != "enabled"
        or result.coverage != "selection"
        or result.target_language != target_language
        or result.layer.source != source_identity
        or result.layer.producer != "alc-translate"
    ):
        raise CompanionTranslationResultError(
            "alc-translate result does not match the Companion chapter"
        )

    blocks = {item.block_id: item for item in source.blocks}
    try:
        ordered_blocks = tuple(blocks[block_id] for block_id in block_ids)
    except KeyError as exc:
        raise CompanionTranslationResultError(
            "chapter translation refers to an unknown source block"
        ) from exc
    expected = tuple(
        block.block_id for block in ordered_blocks if not is_non_language_block(block)
    )
    expected_notes = _source_notes_for_owners(
        source, {block.block_id for block in ordered_blocks}
    )
    notes_by_id = {
        note_id: owner_block_id for note_id, owner_block_id in expected_notes
    }
    ordinary_revisions: list[FragmentRevision] = []
    note_revisions: list[FragmentRevision] = []
    ordinary_coverage: list[str] = []
    note_coverage: list[str] = []
    invalid_block_ids: set[str] = set()
    delivery_issues: list[dict[str, Any]] = []
    try:
        for item in result.revision_artifacts:
            payload = context.artifacts.read_bytes(item.artifact)
            revision = decode_fragment_revision(
                payload.decode("utf-8"),
                filename=Path(item.revision.path).name,
            )
            if (
                revision.fragment_id != item.revision.fragment_id
                or revision.revision != item.revision.revision
                or revision.semantic_digest != item.revision.semantic_digest
                or revision.source != source_identity
                or revision.priority != 10
                or revision.role != "translation"
                or revision.language != target_language
                or revision.title is not None
                or revision.citation_ids
                or revision.provenance.get("producer") != "alc-translate"
                or revision.anchor.kind is not AnchorKind.BLOCK
            ):
                raise ValueError("translation revision identity mismatch")
            note_id = _source_note_id(revision)
            if note_id is None:
                block = blocks.get(revision.anchor.target_id)
                if block is None or revision.anchor.related_blocks != (
                    anchor_block_from_rich_block(block),
                ):
                    raise ValueError("translation revision anchor mismatch")
                ordinary_coverage.append(revision.anchor.target_id)
            else:
                owner_block_id = notes_by_id.get(note_id)
                if (
                    owner_block_id is None
                    or revision.anchor.target_id != owner_block_id
                    or revision.anchor.related_blocks
                    != (anchor_block_from_rich_block(blocks[owner_block_id]),)
                ):
                    raise ValueError("source note translation anchor mismatch")
                note_coverage.append(note_id)
            recovered_markdown = canonicalize_translation_markdown(
                revision.markdown_body
            )
            try:
                validate_translation_markdown(recovered_markdown)
            except TranslationSourceError as exc:
                scope = note_id or revision.anchor.target_id
                if note_id is None:
                    invalid_block_ids.add(revision.anchor.target_id)
                delivery_issues.append(
                    {
                        "issue_id": (
                            f"translation-markdown-invalid-{revision.fragment_id}"
                        ),
                        "category": "translation_omitted",
                        "scope": scope,
                        "fallback": "source_text",
                        "affected_count": 1,
                        "source_preserved": True,
                        "retry": "translation_boundary_rejected",
                        "evidence": exc.code,
                    }
                )
                continue
            if recovered_markdown != revision.markdown_body:
                revision = replace(
                    revision,
                    provenance={
                        **dict(revision.provenance),
                        "translation_markdown_recovery": {
                            "schema_version": ("alc.translate.markdown_recovery.v1"),
                            "kind": "adjacent_inline_math",
                        },
                    },
                    markdown_body=recovered_markdown,
                )
            if note_id is None:
                ordinary_revisions.append(revision)
            else:
                note_revisions.append(revision)
    except (AcJobsError, OSError, UnicodeError, ValueError) as exc:
        raise CompanionTranslationResultError(
            "alc-translate revision artifact is invalid"
        ) from exc
    if tuple(ordinary_coverage) != expected:
        raise CompanionTranslationResultError(
            "alc-translate did not exactly cover the chapter source order"
        )
    if tuple(note_coverage) != tuple(item[0] for item in expected_notes):
        raise CompanionTranslationResultError(
            "alc-translate did not exactly cover chapter source notes"
        )

    by_block = {item.anchor.target_id: item for item in ordinary_revisions}
    records = tuple(
        {
            "block_id": block.block_id,
            "text": (
                "\ufffc"
                if is_non_language_block(block)
                else (
                    model_source_block_view(block)
                    if block.block_id in invalid_block_ids
                    else by_block[block.block_id].markdown_body
                )
            ),
        }
        for block in ordered_blocks
    )
    return ValidatedTranslationSelection(
        result,
        (*ordinary_revisions, *note_revisions),
        records,
        tuple(delivery_issues),
    )


def is_non_language_block(block: RichBlock) -> bool:
    """Return whether a block has no ALC translation surface.

    This matches alc-translate's structural-media contract: an uncaptioned
    table and a figure without caption or alt text remain source-only.
    """

    if block.kind is RichBlockKind.FIGURE:
        return not (
            str(block.payload.get("caption", "")).strip()
            or str(block.payload.get("alt_text", "")).strip()
        )
    if block.kind is RichBlockKind.TABLE:
        return not str(block.payload.get("caption", "")).strip()
    return False


def _source_note_id(revision: FragmentRevision) -> str | None:
    value = revision.provenance.get("source_note_translation")
    if value is None:
        return None
    if (
        not isinstance(value, Mapping)
        or set(value) != {"schema_version", "note_id"}
        or value.get("schema_version") != "alc.render.source_note_translation.v1"
        or not isinstance(value.get("note_id"), str)
        or not value["note_id"]
    ):
        raise ValueError("source note translation provenance is invalid")
    return str(value["note_id"])


def _source_notes_for_owners(
    source: RichDocument, owner_block_ids: set[str]
) -> tuple[tuple[str, str], ...]:
    metadata = source.metadata
    raw = metadata.get("source_notes")
    if raw is None:
        return ()
    if not isinstance(raw, Mapping) or not isinstance(raw.get("notes"), Sequence):
        raise CompanionTranslationResultError("source note metadata is invalid")
    values: list[tuple[int, str, str]] = []
    for note in raw["notes"]:
        if not isinstance(note, Mapping):
            raise CompanionTranslationResultError("source note metadata is invalid")
        note_id = note.get("note_id")
        owner_block_id = note.get("owner_block_id")
        ordinal = note.get("ordinal")
        if (
            not isinstance(note_id, str)
            or not note_id
            or not isinstance(owner_block_id, str)
            or not owner_block_id
            or isinstance(ordinal, bool)
            or not isinstance(ordinal, int)
        ):
            raise CompanionTranslationResultError("source note metadata is invalid")
        if owner_block_id in owner_block_ids:
            values.append((ordinal, note_id, owner_block_id))
    if len({item[1] for item in values}) != len(values):
        raise CompanionTranslationResultError("source note IDs repeat")
    return tuple((note_id, owner) for _ordinal, note_id, owner in sorted(values))


__all__ = [
    "CompanionTranslationResultError",
    "ValidatedTranslationSelection",
    "is_non_language_block",
    "load_translation_selection",
]
