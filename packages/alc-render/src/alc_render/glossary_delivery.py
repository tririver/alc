"""Source-bound glossary handoff for standalone render publications."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ac_document import RichDocument

from ._io import atomic_write_bytes
from ._json import (
    JsonValue,
    canonical_json_bytes,
    freeze_json,
    strict_json_loads,
    thaw_json,
)
from .contracts import (
    SourceIdentity,
    source_identity_from_document,
    source_identity_from_rich_document,
    source_identity_to_document,
)


GLOSSARY_DELIVERY_SCHEMA = "alc.render.glossary_delivery.v1"
_DELIVERY_FIELDS = {"schema_version", "source", "entries", "glossary_digest"}
_ENTRY_FIELDS = {
    "entry_id",
    "term",
    "translated_term",
    "definition",
    "anchor_ids",
    "citations",
}
_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")
_DIGEST_RE = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class GlossaryDelivery:
    """A render-native glossary bound to one exact rich source."""

    source: SourceIdentity
    entries: tuple[Mapping[str, JsonValue], ...]
    schema_version: str = GLOSSARY_DELIVERY_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != GLOSSARY_DELIVERY_SCHEMA:
            raise ValueError("unsupported glossary delivery schema")
        if not isinstance(self.source, SourceIdentity):
            raise ValueError("glossary delivery source must be a SourceIdentity")
        frozen_entries: list[Mapping[str, JsonValue]] = []
        entry_ids: set[str] = set()
        for raw in tuple(self.entries):
            if not isinstance(raw, Mapping) or set(raw) != _ENTRY_FIELDS:
                raise ValueError("glossary delivery entry has invalid fields")
            entry = dict(raw)
            entry_id = _identifier(entry["entry_id"], "glossary entry_id")
            if entry_id in entry_ids:
                raise ValueError("glossary delivery repeats an entry_id")
            entry_ids.add(entry_id)
            for field in ("term", "translated_term", "definition"):
                entry[field] = _nonblank(entry[field], f"glossary {field}")
            entry["anchor_ids"] = list(
                _identifiers(
                    entry["anchor_ids"],
                    "glossary anchor_ids",
                    nonempty=True,
                )
            )
            entry["citations"] = list(
                _identifiers(
                    entry["citations"],
                    "glossary citations",
                    nonempty=False,
                )
            )
            frozen = freeze_json(entry, "glossary delivery entry")
            assert isinstance(frozen, Mapping)
            frozen_entries.append(frozen)
        object.__setattr__(self, "entries", tuple(frozen_entries))

    @property
    def glossary_digest(self) -> str:
        return hashlib.sha256(
            canonical_json_bytes(_glossary_delivery_material(self))
        ).hexdigest()


def validate_glossary_delivery(
    document: RichDocument, delivery: GlossaryDelivery
) -> None:
    """Validate exact source identity and every glossary block anchor."""

    if not isinstance(document, RichDocument):
        raise TypeError("document must be a RichDocument")
    if not isinstance(delivery, GlossaryDelivery):
        raise TypeError("delivery must be a GlossaryDelivery")
    if delivery.source != source_identity_from_rich_document(document):
        raise ValueError("glossary delivery binds another rich source")
    block_ids = {block.block_id for block in document.blocks}
    for entry in delivery.entries:
        if any(anchor not in block_ids for anchor in entry["anchor_ids"]):
            raise ValueError("glossary delivery contains an unknown block anchor")


def glossary_delivery_to_document(delivery: GlossaryDelivery) -> dict[str, Any]:
    return {
        **_glossary_delivery_material(delivery),
        "glossary_digest": delivery.glossary_digest,
    }


def glossary_delivery_from_document(value: Any) -> GlossaryDelivery:
    if not isinstance(value, Mapping) or set(value) != _DELIVERY_FIELDS:
        raise ValueError("glossary delivery has invalid fields")
    if value["schema_version"] != GLOSSARY_DELIVERY_SCHEMA:
        raise ValueError("unsupported glossary delivery schema")
    entries = value["entries"]
    if not isinstance(entries, list):
        raise ValueError("glossary delivery entries must be an array")
    delivery = GlossaryDelivery(
        source_identity_from_document(value["source"]),
        tuple(entries),
    )
    digest = value["glossary_digest"]
    if not isinstance(digest, str) or _DIGEST_RE.fullmatch(digest) is None:
        raise ValueError("glossary delivery digest must be SHA-256")
    if digest != delivery.glossary_digest:
        raise ValueError("glossary delivery digest does not match its content")
    return delivery


def read_glossary_delivery(path: str | Path) -> GlossaryDelivery:
    try:
        value = strict_json_loads(Path(path).read_text(encoding="utf-8"))
        return glossary_delivery_from_document(value)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"glossary delivery is unreadable or invalid: {path}") from exc


def write_glossary_delivery(
    path: str | Path, delivery: GlossaryDelivery
) -> Path:
    target = Path(path).resolve()
    atomic_write_bytes(
        target, canonical_json_bytes(glossary_delivery_to_document(delivery))
    )
    return target


def _glossary_delivery_material(delivery: GlossaryDelivery) -> dict[str, Any]:
    return {
        "schema_version": delivery.schema_version,
        "source": source_identity_to_document(delivery.source),
        "entries": thaw_json(delivery.entries),
    }


def _nonblank(value: object, description: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{description} must be a non-empty string")
    return value.strip()


def _identifier(value: object, description: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        raise ValueError(f"{description} must be a portable identifier")
    return value


def _identifiers(
    value: object, description: str, *, nonempty: bool
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(
        value, Sequence
    ):
        raise ValueError(f"{description} must be an array")
    items = tuple(_identifier(item, description) for item in value)
    if nonempty and not items:
        raise ValueError(f"{description} must not be empty")
    if len(items) != len(set(items)):
        raise ValueError(f"{description} must not contain duplicates")
    return items


__all__ = [
    "GLOSSARY_DELIVERY_SCHEMA",
    "GlossaryDelivery",
    "glossary_delivery_from_document",
    "glossary_delivery_to_document",
    "read_glossary_delivery",
    "validate_glossary_delivery",
    "write_glossary_delivery",
]
