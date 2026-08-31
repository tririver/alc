"""Publish native alc-render translation fragments and their Layer."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Sequence

from ac_document import (
    RichDocument,
    literal_term_occurs,
    rich_block_to_document,
)

from alc_render import (
    AnchorKind,
    FragmentRevision,
    GlossaryDelivery,
    decode_fragment_revision,
    fragment_revision_storage_path,
    read_fragment_revision,
    read_glossary_delivery,
    read_layer,
    relative_fragment_path,
    source_identity_from_rich_document,
    validate_glossary_delivery,
    write_fragment_revision,
    write_glossary_delivery,
    write_layer,
)

from .project import TranslationProject
from .workflow import GlossaryResult, TranslationResult


class TranslationDeliveryError(RuntimeError):
    code = "translation_delivery_invalid"


def build_translation_glossary(
    document: RichDocument, result: GlossaryResult
) -> GlossaryDelivery:
    """Convert one exact translation glossary to render-native block anchors."""

    if not isinstance(document, RichDocument):
        raise TypeError("document must be a RichDocument")
    if not isinstance(result, GlossaryResult):
        raise TypeError("result must be a GlossaryResult")
    if (
        result.document_digest != document.document_digest
        or result.source_digest != document.source.artifact_digest
    ):
        raise TranslationDeliveryError(
            "glossary result binds another rich source"
        )
    block_documents = {
        block.block_id: rich_block_to_document(block)
        for block in document.blocks
    }
    entries: list[dict[str, Any]] = []
    for item in result.entries:
        term = str(item["term"]).strip()
        source_refs = {
            str(value)
            for value in item.get("source_refs", ())
            if isinstance(value, str)
        }
        anchors = [
            block_id
            for block_id, block in block_documents.items()
            if block_id in source_refs
            or literal_term_occurs(
                _literal_strings(block.get("payload")), (term,)
            )
        ]
        if not anchors:
            continue
        entries.append(
            {
                "entry_id": str(item["term_id"]),
                "term": term,
                "translated_term": str(item["preferred_translation"]),
                "definition": str(item["target_definition"]),
                "anchor_ids": anchors,
                "citations": [],
            }
        )
    delivery = GlossaryDelivery(
        source_identity_from_rich_document(document), tuple(entries)
    )
    validate_glossary_delivery(document, delivery)
    return delivery


def publish_translation_glossary(
    project: TranslationProject,
    *,
    document: RichDocument,
    result: GlossaryResult,
) -> Path:
    """Atomically publish one source-bound render glossary delivery."""

    delivery = build_translation_glossary(document, result)
    try:
        path = write_glossary_delivery(project.translation_glossary, delivery)
        validate_translation_glossary(
            project, document=document, result=result
        )
        return path
    except (OSError, UnicodeError, ValueError) as exc:
        raise TranslationDeliveryError(
            "translation glossary could not be published"
        ) from exc


def validate_translation_glossary(
    project: TranslationProject,
    *,
    document: RichDocument,
    result: GlossaryResult,
) -> None:
    """Validate the visible glossary delivery against its exact result/source."""

    try:
        expected = build_translation_glossary(document, result)
        actual = read_glossary_delivery(project.translation_glossary)
        validate_glossary_delivery(document, actual)
        if actual != expected:
            raise ValueError("published glossary does not match its result")
    except (OSError, UnicodeError, ValueError) as exc:
        raise TranslationDeliveryError(
            "translation glossary delivery is unreadable or invalid"
        ) from exc


def publish_translation_layer(
    project: TranslationProject,
    *,
    result: TranslationResult,
    revision_payloads: Sequence[bytes],
) -> Path:
    """Publish immutable revision files followed by their atomic Layer."""

    if not isinstance(result, TranslationResult):
        raise TypeError("result must be a TranslationResult")
    if result.coverage != "document":
        raise TranslationDeliveryError(
            "a selected-block translation cannot replace the document Layer"
        )
    payloads = tuple(revision_payloads)
    if len(payloads) != len(result.revision_artifacts):
        raise TranslationDeliveryError(
            "translation revision payload count does not match the result manifest"
        )
    revisions = _validated_revisions(result, payloads)
    for item, revision in zip(
        result.revision_artifacts, revisions, strict=True
    ):
        try:
            published = write_fragment_revision(project.root, revision)
            if (
                relative_fragment_path(project.root, published)
                != item.revision.path
            ):
                raise ValueError("revision path mismatch")
        except (OSError, UnicodeError, ValueError) as exc:
            raise TranslationDeliveryError(
                "translation revision payload is invalid"
            ) from exc
    try:
        write_layer(project.translation_layer, result.layer)
    except (OSError, ValueError) as exc:
        raise TranslationDeliveryError(
            "translation Layer could not be published"
        ) from exc
    validate_translation_layer(project, result=result)
    return project.translation_layer


def _validated_revisions(
    result: TranslationResult,
    payloads: Sequence[bytes],
) -> tuple[FragmentRevision, ...]:
    revisions: list[FragmentRevision] = []
    try:
        for item, payload in zip(
            result.revision_artifacts, payloads, strict=True
        ):
            revision = decode_fragment_revision(
                payload.decode("utf-8"),
                filename=Path(item.revision.path).name,
            )
            if (
                revision.fragment_id != item.revision.fragment_id
                or revision.revision != item.revision.revision
                or revision.semantic_digest != item.revision.semantic_digest
                or revision.source != result.layer.source
                or revision.priority != 10
                or revision.role != "translation"
                or revision.language != result.target_language
                or revision.anchor.kind is not AnchorKind.BLOCK
                or revision.title is not None
                or revision.citation_ids
                or revision.provenance.get("producer") != "alc-translate"
                or item.revision.path
                != fragment_revision_storage_path(revision)
            ):
                raise ValueError(
                    "revision does not match the translation result"
                )
            revisions.append(revision)
    except (OSError, UnicodeError, ValueError) as exc:
        raise TranslationDeliveryError(
            "translation revision payload is invalid"
        ) from exc
    return tuple(revisions)


def validate_translation_layer(
    project: TranslationProject,
    *,
    result: TranslationResult,
) -> None:
    """Validate a visible Layer and every referenced immutable revision."""

    try:
        layer = read_layer(project.translation_layer)
        if layer != result.layer:
            raise ValueError("published Layer does not match the result")
        for reference in layer.initial_revisions:
            revision = read_fragment_revision(project.root / reference.path)
            if (
                revision.fragment_id != reference.fragment_id
                or revision.semantic_digest != reference.semantic_digest
                or revision.source != layer.source
                or revision.priority != 10
                or revision.role != "translation"
                or revision.language != result.target_language
            ):
                raise ValueError("published revision does not match its Layer")
    except (OSError, UnicodeError, ValueError) as exc:
        raise TranslationDeliveryError(
            "translation Layer delivery is unreadable or invalid"
        ) from exc


def _literal_strings(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return "\n".join(_literal_strings(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return "\n".join(_literal_strings(item) for item in value)
    return ""


__all__ = [
    "TranslationDeliveryError",
    "build_translation_glossary",
    "publish_translation_layer",
    "publish_translation_glossary",
    "validate_translation_layer",
    "validate_translation_glossary",
]
