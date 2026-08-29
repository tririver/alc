from __future__ import annotations

import json
from pathlib import Path

import pytest

from alc_render import (
    GLOSSARY_FRONT_MATTER_BEGIN,
    GLOSSARY_FRONT_MATTER_END,
    GlossaryRevision,
    decode_glossary_revision,
    encode_glossary_revision,
    glossary_base_semantic_digest,
    glossary_revision_filename,
    glossary_revision_to_document,
    resolve_glossary_revision_files,
    resolve_glossary_revisions,
    write_glossary_revision,
)


def _entry() -> dict[str, object]:
    return {
        "entry_id": "term-reader",
        "term": "Reader",
        "translated_term": "读者",
        "definition": "阅读文本的人。",
        "anchor_ids": ["block-paragraph"],
        "citations": [],
        "opaque": {"keep": True},
    }


def _revision(
    entry: dict[str, object], *, revision: int = 2, parent: str | None = None
) -> GlossaryRevision:
    return GlossaryRevision(
        entry_id="term-reader",
        revision=revision,
        parent_semantic_digest=parent or glossary_base_semantic_digest(entry),
        entry=entry,
        provenance={"producer": "alc-render-browser", "edited_at": "2026-08-28T00:00:00Z"},
    )


def test_glossary_revision_round_trip_preserves_unknown_entry_fields() -> None:
    entry = _entry()
    revision = _revision({**entry, "translated_term": "阅读器"})

    encoded = encode_glossary_revision(revision)
    text = encoded.decode("utf-8")
    decoded = decode_glossary_revision(
        encoded, filename=glossary_revision_filename(revision)
    )

    front_matter = text.removeprefix(f"{GLOSSARY_FRONT_MATTER_BEGIN}\n").split(
        f"\n{GLOSSARY_FRONT_MATTER_END}\n", 1
    )[0]
    assert glossary_revision_filename(revision).endswith(".md")
    assert '"definition"' not in front_matter
    assert text.endswith("阅读文本的人。")
    assert decoded == revision
    assert decoded.entry["opaque"] == {"keep": True}


def test_glossary_revision_reads_legacy_canonical_json() -> None:
    entry = _entry()
    revision = _revision({**entry, "translated_term": "阅读器"})
    document = glossary_revision_to_document(revision)
    encoded = (
        json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    filename = glossary_revision_filename(revision).removesuffix(".md") + ".json"

    assert decode_glossary_revision(encoded, filename=filename) == revision


def test_glossary_revision_resolver_reads_legacy_json_file(tmp_path: Path) -> None:
    entry = _entry()
    revision = _revision(
        {**entry, "definition": "旧格式解释。"},
        parent=glossary_base_semantic_digest(entry),
    )
    document = glossary_revision_to_document(revision)
    filename = glossary_revision_filename(revision).removesuffix(".md") + ".json"
    path = tmp_path / filename
    path.write_bytes(
        json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )

    resolution = resolve_glossary_revision_files([path], base_entry=entry)

    assert resolution.selected == revision
    assert not resolution.diagnostics


def test_glossary_revision_rejects_source_and_anchor_changes() -> None:
    entry = _entry()
    parent = glossary_base_semantic_digest(entry)

    source_changed = _revision({**entry, "term": "Another"}, parent=parent)
    source_resolution = resolve_glossary_revisions(entry, [source_changed])
    assert source_resolution.selected is None
    assert any(item.code == "immutable_glossary_field_changed" for item in source_resolution.diagnostics)

    anchor_changed = _revision(
        {**entry, "anchor_ids": ["another-block"]}, parent=parent
    )
    resolution = resolve_glossary_revisions(entry, [anchor_changed])
    assert resolution.selected is None
    assert any(item.code == "immutable_glossary_field_changed" for item in resolution.diagnostics)


def test_glossary_revision_resolves_lineage_and_forks_without_guessing() -> None:
    entry = _entry()
    base = glossary_base_semantic_digest(entry)
    first = _revision({**entry, "translated_term": "阅读器"}, parent=base)
    second = _revision(
        {**entry, "translated_term": "阅读界面"},
        revision=3,
        parent=first.semantic_digest,
    )
    assert resolve_glossary_revisions(entry, [first, second]).selected is second

    fork = _revision(
        {**entry, "translated_term": "读书器"},
        parent=base,
    )
    resolution = resolve_glossary_revisions(entry, [first, fork])
    assert resolution.selected is None
    assert resolution.has_conflict


def test_glossary_revision_collapses_content_equivalent_retries() -> None:
    entry = _entry()
    parent = glossary_base_semantic_digest(entry)
    edited = {**entry, "translated_term": "阅读器", "definition": "修订解释。"}
    first = GlossaryRevision(
        entry_id="term-reader",
        revision=2,
        parent_semantic_digest=parent,
        entry=edited,
        provenance={"producer": "alc-render-browser", "attempt": "first"},
    )
    retry = GlossaryRevision(
        entry_id="term-reader",
        revision=2,
        parent_semantic_digest=parent,
        entry=edited,
        provenance={"producer": "alc-render-browser", "attempt": "retry"},
    )

    resolution = resolve_glossary_revisions(entry, [first, retry])

    assert resolution.selected is min(
        (first, retry), key=lambda item: item.semantic_digest
    )
    assert not resolution.has_conflict
    assert any(
        item.code == "equivalent_revision_retry"
        for item in resolution.diagnostics
    )

    successor = GlossaryRevision(
        entry_id="term-reader",
        revision=3,
        parent_semantic_digest=retry.semantic_digest,
        entry={**edited, "definition": "后续修订。"},
        provenance={"producer": "alc-render-browser"},
    )
    continued = resolve_glossary_revisions(
        entry, [first, retry, successor]
    )
    assert continued.selected is successor
    assert not continued.has_conflict


def test_glossary_revision_write_is_immutable(tmp_path: Path) -> None:
    entry = _entry()
    revision = _revision({**entry, "definition": "修订后的解释。"})

    path = write_glossary_revision(tmp_path, revision)
    assert path == tmp_path / "glossary" / glossary_revision_filename(revision)
    assert write_glossary_revision(tmp_path, revision) == path
    path.write_bytes(b"different")
    with pytest.raises(ValueError, match="other bytes"):
        write_glossary_revision(tmp_path, revision)
