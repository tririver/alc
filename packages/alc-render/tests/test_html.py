from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
import re
import shutil
import subprocess

import pytest
from ac_document import (
    RichAsset,
    RichBlock,
    RichBlockKind,
    RichDocument,
    RichSection,
    SourceArtifact,
    SourceFormat,
    SourceLocator,
    SourceOrigin,
    SourceOriginKind,
)

from alc_render import (
    encode_glossary_revision,
    encode_fragment_revision,
    FragmentAnchor,
    FragmentRevision,
    GlossaryRevision,
    Layer,
    Publication,
    anchor_block_from_rich_block,
    fragment_revision_filename,
    fragment_revision_ref,
    glossary_base_semantic_digest,
    glossary_revision_filename,
    glossary_revision_storage_path,
    glossary_revision_to_document,
    write_glossary_revision,
    publication_edition_digest,
    read_publication_workspace_state,
    source_identity_from_rich_document,
)
from alc_render.html import (
    HTMLRenderError,
    _extract_json_script,
    _extract_reader_payload,
    _legacy_bibliography_targets,
    _reader_payload,
    _reader_icon_link,
    _validate_fragment_glossary_mentions,
    render_publication_html,
    validate_standalone_html,
)
from alc_render.standalone_html import _split_reader_payload
from alc_render.workspace import (
    relative_fragment_path,
    write_fragment_revision,
    write_layer,
    write_publication,
)


def _rich_document(asset_payload: bytes | None = None) -> RichDocument:
    source_payload = b"# Reader\n\nSource paragraph.\n"
    source = SourceArtifact(
        SourceFormat.MARKDOWN,
        hashlib.sha256(source_payload).hexdigest(),
        len(source_payload),
        "text/markdown",
        SourceOrigin(SourceOriginKind.REPOSITORY),
    )
    blocks = [
        RichBlock(
            "block-heading",
            0,
            RichBlockKind.HEADING,
            ("section-reader",),
            SourceLocator(SourceFormat.MARKDOWN, 1, 1, 1, 8),
            {"text": "Reader", "level": 1},
        ),
        RichBlock(
            "block-paragraph",
            1,
            RichBlockKind.PARAGRAPH,
            ("section-reader",),
            SourceLocator(SourceFormat.MARKDOWN, 3, 1, 3, 17),
            {
                "text": "Source paragraph.",
                "inline_spans": [
                    {
                        "kind": "text",
                        "start": 0,
                        "end": 17,
                        "text": "Source paragraph.",
                    }
                ],
            },
        ),
    ]
    assets = ()
    if asset_payload is not None:
        digest = hashlib.sha256(asset_payload).hexdigest()
        assets = (RichAsset(digest, "image/png", "figure.png", len(asset_payload)),)
        blocks.append(
            RichBlock(
                "block-figure",
                2,
                RichBlockKind.FIGURE,
                ("section-reader",),
                SourceLocator(SourceFormat.MARKDOWN, 5, 1, 5, 20),
                {
                    "asset_digest": digest,
                    "alt_text": "A source figure",
                    "caption": "Figure caption",
                    "target": "figure.png",
                    "media_type": "image/png",
                    "logical_name": "figure.png",
                    "size": len(asset_payload),
                },
            )
        )
    return RichDocument(
        source,
        tuple(blocks),
        (
            RichSection(
                "section-reader",
                "Reader",
                1,
                0,
                ("section-reader",),
                0,
                len(blocks),
            ),
        ),
        assets,
    )


def _bibliography_document(
    *,
    second_label: str = "Jones 2021",
    second_target: str = "#bib.bib2",
    reference_title: str = "References",
    duplicate_list: bool = False,
) -> RichDocument:
    document = _rich_document()
    citation_text = f"Smith 2020; {second_label}"
    smith_reference = "Smith (2020) S. Smith, Journal 1."
    jones_reference = "Jones (2021) J. Jones, Journal 2."
    smith_duplicate = "Smith (2020) Another entry."
    jones_duplicate = "Jones (2021) Another entry."
    blocks = [
        RichBlock(
            "block-citations",
            0,
            RichBlockKind.PARAGRAPH,
            ("section-reader",),
            SourceLocator(SourceFormat.MARKDOWN, 1, 1, 1, len(citation_text)),
            {
                "text": citation_text,
                "inline_spans": [
                    {
                        "kind": "link",
                        "start": 0,
                        "end": 10,
                        "text": "Smith 2020",
                        "target": "#bib.bib1",
                    },
                    {
                        "kind": "text",
                        "start": 10,
                        "end": 12,
                        "text": "; ",
                    },
                    {
                        "kind": "link",
                        "start": 12,
                        "end": len(citation_text),
                        "text": second_label,
                        "target": second_target,
                    },
                ],
            },
        ),
        RichBlock(
            "block-references",
            1,
            RichBlockKind.LIST,
            ("section-references",),
            SourceLocator(SourceFormat.MARKDOWN, 3, 1, 4, 40),
            {
                "ordered": False,
                "items": [
                    {
                        "text": smith_reference,
                        "inline_spans": [
                            {
                                "kind": "text",
                                "start": 0,
                                "end": len(smith_reference),
                                "text": smith_reference,
                            }
                        ],
                    },
                    {
                        "text": jones_reference,
                        "inline_spans": [
                            {
                                "kind": "text",
                                "start": 0,
                                "end": len(jones_reference),
                                "text": jones_reference,
                            }
                        ],
                    },
                ],
            },
        ),
    ]
    if duplicate_list:
        blocks.append(
            RichBlock(
                "block-other-list",
                2,
                RichBlockKind.LIST,
                ("section-references",),
                SourceLocator(SourceFormat.MARKDOWN, 6, 1, 7, 40),
                {
                    "ordered": False,
                    "items": [
                        {
                            "text": smith_duplicate,
                            "inline_spans": [
                                {
                                    "kind": "text",
                                    "start": 0,
                                    "end": len(smith_duplicate),
                                    "text": smith_duplicate,
                                }
                            ],
                        },
                        {
                            "text": jones_duplicate,
                            "inline_spans": [
                                {
                                    "kind": "text",
                                    "start": 0,
                                    "end": len(jones_duplicate),
                                    "text": jones_duplicate,
                                }
                            ],
                        },
                    ],
                },
            )
        )
    return RichDocument(
        document.source,
        tuple(blocks),
        (
            RichSection(
                "section-reader",
                "Reader",
                1,
                0,
                ("section-reader",),
                0,
                1,
            ),
            RichSection(
                "section-references",
                reference_title,
                1,
                1,
                ("section-references",),
                1,
                len(blocks),
            ),
        ),
    )


def test_legacy_bibliography_targets_require_one_exact_ordinal_mapping() -> None:
    assert _legacy_bibliography_targets(_bibliography_document()) == (
        {
            "alias": "bib.bib1",
            "block_id": "block-references",
            "item_index": 0,
        },
        {
            "alias": "bib.bib2",
            "block_id": "block-references",
            "item_index": 1,
        },
    )
    assert _legacy_bibliography_targets(
        _bibliography_document(duplicate_list=True)
    ) == ()
    assert _legacy_bibliography_targets(
        _bibliography_document(second_label="Different 2021")
    ) == ()
    assert _legacy_bibliography_targets(
        _bibliography_document(reference_title="Reading plan")
    ) == ()
    assert _legacy_bibliography_targets(
        _bibliography_document(second_target="#bib.bib" + "9" * 5000)
    ) == ()


def test_reader_v2_boot_preserves_legacy_bibliography_targets() -> None:
    publication = Publication(
        source_document=_bibliography_document(),
        layers=(),
        glossary=(),
        bibliography=(),
        labels={},
        resources=(),
        reader_profile={},
    )
    payload = _reader_payload(
        publication,
        revisions=(),
        selected=(),
        glossary_revisions=(),
        selected_glossary_revision_digests=(),
        resources=(),
        diagnostics=(),
    )
    html = (
        '<script id="alc-render-payload" type="application/json">'
        + json.dumps(payload)
        + "</script>"
    )

    boot = _boot_payload(_split_reader_payload(html))

    assert boot["legacy_bibliography_targets"] == [
        {
            "alias": "bib.bib1",
            "block_id": "block-references",
            "item_index": 0,
        },
        {
            "alias": "bib.bib2",
            "block_id": "block-references",
            "item_index": 1,
        },
    ]


def _revision(
    document: RichDocument,
    *,
    body: str = "译文带有公式 $x^2$ 和引用 [@ref-1]。",
    revision: int = 1,
    parent: str | None = None,
) -> FragmentRevision:
    block = document.blocks[1]
    return FragmentRevision(
        source=source_identity_from_rich_document(document),
        fragment_id="translation-block-paragraph",
        revision=revision,
        parent_semantic_digest=parent,
        anchor=FragmentAnchor(
            "block",
            block.block_id,
            (anchor_block_from_rich_block(block),),
        ),
        priority=10,
        role="translation",
        language="zh-CN",
        title=None,
        citation_ids=("ref-1",),
        provenance={"producer": "alc-translate"},
        markdown_body=body,
    )


def _workspace(
    tmp_path: Path,
    *,
    asset_payload: bytes | None = None,
    add_second_revision: bool = False,
) -> tuple[Path, Publication, FragmentRevision]:
    document = _rich_document(asset_payload)
    first = _revision(document)
    first_path = write_fragment_revision(tmp_path, first)
    layer = Layer(
        first.source,
        "alc-translate",
        (
            fragment_revision_ref(
                relative_fragment_path(tmp_path, first_path),
                first,
            ),
        ),
    )
    layer_path = tmp_path / "layers" / "translation.json"
    write_layer(layer_path, layer)
    resources = ()
    if asset_payload is not None:
        asset = document.assets[0]
        asset_path = tmp_path / "source-assets" / asset.logical_name
        asset_path.parent.mkdir(parents=True)
        asset_path.write_bytes(asset_payload)
        resources = (
            {
                "artifact_digest": asset.artifact_digest,
                "path": "source-assets/figure.png",
            },
        )
    publication = Publication(
        source_document=document,
        layers=(layer.reference("layers/translation.json"),),
        glossary=(
            {
                "entry_id": "term-reader",
                "term": "Reader",
                "translated_term": "读者",
                "definition": "阅读文本的人。",
                "anchor_ids": ["block-paragraph"],
            },
        ),
        bibliography=(
            {
                "evidence_id": "ref-1",
                "title": "Reference",
                "source": "https://example.test/reference",
                "dois": [],
                "arxiv_ids": [],
            },
        ),
        labels={"document_title": "Portable Reader"},
        resources=resources,
        reader_profile={
            "title": "Portable Reader",
            "source_language": "en",
            "target_language": "zh-CN",
        },
    )
    if add_second_revision:
        second = _revision(
            document,
            body="修订后的译文 [@ref-1]。",
            revision=2,
            parent=first.semantic_digest,
        )
        write_fragment_revision(tmp_path, second)
    else:
        second = first
    publication_path = tmp_path / "publication.json"
    write_publication(publication_path, publication)
    return publication_path, publication, second


def _payload(html: str) -> dict[str, object]:
    return dict(_extract_reader_payload(html))


def _boot_payload(html: str) -> dict[str, object]:
    match = re.search(
        r'<script id="alc-render-payload" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1).replace(r"<\/script", "</script"))


def test_glossary_history_is_loaded_without_changing_publication_identity(
    tmp_path: Path,
) -> None:
    publication_path, publication, _selected = _workspace(tmp_path)
    base = dict(publication.glossary[0])
    revision = GlossaryRevision(
        entry_id="term-reader",
        revision=2,
        parent_semantic_digest=glossary_base_semantic_digest(base),
        entry={**base, "translated_term": "阅读器", "definition": "修订解释。"},
        provenance={"producer": "alc-render-browser", "edited_at": "2026-08-28T00:00:00Z"},
    )
    revision_path = write_glossary_revision(tmp_path, revision)
    assert revision_path.relative_to(tmp_path).as_posix() == (
        glossary_revision_storage_path(revision)
    )

    state = read_publication_workspace_state(publication_path)
    assert state.publication_digest == publication.publication_digest
    assert state.selected_glossary_revision_digests == (revision.semantic_digest,)
    assert state.edition_digest == publication_edition_digest(
        publication.publication_digest,
        state.selected_revision_digests,
    )

    output = tmp_path / "reader.html"
    result = render_publication_html(publication_path, output)
    payload = _payload(output.read_text(encoding="utf-8"))
    assert result.selected_glossary_revision_digests == (revision.semantic_digest,)
    assert payload["selected_glossary_revision_digests"] == [revision.semantic_digest]
    assert payload["glossary_base_digests"] == {
        "term-reader": glossary_base_semantic_digest(base)
    }
    assert payload["glossary_revisions"][0]["entry"]["translated_term"] == "阅读器"
    assert payload["publication"]["publication_digest"] == publication.publication_digest


def _glossary_propagation_revision(
    tmp_path: Path,
    publication: Publication,
    first: FragmentRevision,
    *,
    parent: str | None = None,
    batch_id: str = "glossary-test-batch",
) -> tuple[GlossaryRevision, FragmentRevision, Path]:
    body = "阅读器使用修订后的术语 [@ref-1]。"
    fragment = FragmentRevision(
        source=first.source,
        fragment_id=first.fragment_id,
        revision=2,
        parent_semantic_digest=parent or first.semantic_digest,
        anchor=first.anchor,
        priority=first.priority,
        role=first.role,
        language=first.language,
        title=first.title,
        citation_ids=first.citation_ids,
        appearance=first.appearance,
        deleted=first.deleted,
        provenance={
            **dict(first.provenance),
            "last_editor": "alc-render-browser",
            "reason": "glossary-propagation",
            "propagation_batch_id": batch_id,
            "glossary_entry_id": "term-reader",
            "glossary_mentions_schema": "alc.render.glossary_mentions.v1",
            "glossary_mentions": [
                {
                    "entry_id": "term-reader",
                    "markdown_start": 0,
                    "markdown_end": 3,
                    "surface": "阅读器",
                }
            ],
        },
        markdown_body=body,
    )
    relative = (
        f"glossary-batches/{batch_id}/fragments/"
        f"{fragment_revision_filename(fragment)}"
    )
    path = tmp_path.joinpath(*relative.split("/"))
    path.parent.mkdir(parents=True)
    path.write_text(encode_fragment_revision(fragment), encoding="utf-8")
    base = dict(publication.glossary[0])
    glossary = GlossaryRevision(
        entry_id="term-reader",
        revision=2,
        parent_semantic_digest=glossary_base_semantic_digest(base),
        entry={**base, "translated_term": "阅读器"},
        provenance={
            "producer": "alc-render-browser",
            "propagation": {
                "schema_version": "alc.render.glossary_propagation.v1",
                "batch_id": batch_id,
                "fragments": [
                    {
                        "path": relative,
                        "fragment_id": fragment.fragment_id,
                        "revision": fragment.revision,
                        "parent_semantic_digest": fragment.parent_semantic_digest,
                        "semantic_digest": fragment.semantic_digest,
                    }
                ],
            },
        },
    )
    write_glossary_revision(tmp_path, glossary)
    return glossary, fragment, path


def _peer_glossary_definition_batch(
    tmp_path: Path,
    publication: Publication,
    *,
    batch_id: str = "glossary-peer-definition",
) -> tuple[Publication, GlossaryRevision, GlossaryRevision, Path]:
    source_entry = dict(publication.glossary[0])
    peer_entry = {
        "entry_id": "term-peer",
        "term": "Peer",
        "translated_term": "相关术语",
        "definition": "读者用于解释；`读者`；$读者$。",
        "anchor_ids": ["block-paragraph"],
    }
    publication = replace(
        publication,
        glossary=(source_entry, peer_entry),
    )
    write_publication(tmp_path / "publication.json", publication)
    dependent = GlossaryRevision(
        entry_id="term-peer",
        revision=2,
        parent_semantic_digest=glossary_base_semantic_digest(peer_entry),
        entry={
            **peer_entry,
            "definition": "阅读器用于解释；`读者`；$读者$。",
        },
        provenance={
            "producer": "alc-render-browser",
            "reason": "glossary-propagation",
            "propagation_batch_id": batch_id,
            "glossary_entry_id": "term-reader",
        },
    )
    relative = (
        f"glossary-batches/{batch_id}/glossary/"
        f"{glossary_revision_filename(dependent)}"
    )
    dependent_path = tmp_path.joinpath(*relative.split("/"))
    dependent_path.parent.mkdir(parents=True)
    dependent_path.write_bytes(encode_glossary_revision(dependent))
    commit = GlossaryRevision(
        entry_id="term-reader",
        revision=2,
        parent_semantic_digest=glossary_base_semantic_digest(source_entry),
        entry={**source_entry, "translated_term": "阅读器"},
        provenance={
            "producer": "alc-render-browser",
            "propagation": {
                "schema_version": "alc.render.glossary_propagation.v1",
                "batch_id": batch_id,
                "fragments": [],
                "glossary_revisions": [
                    {
                        "path": relative,
                        "entry_id": dependent.entry_id,
                        "revision": dependent.revision,
                        "parent_semantic_digest": (
                            dependent.parent_semantic_digest
                        ),
                        "semantic_digest": dependent.semantic_digest,
                    }
                ],
            },
        },
    )
    write_glossary_revision(tmp_path, commit)
    return publication, commit, dependent, dependent_path


def test_glossary_propagation_batch_selects_glossary_and_fragment_together(
    tmp_path: Path,
) -> None:
    publication_path, publication, first = _workspace(tmp_path)
    glossary, fragment, _path = _glossary_propagation_revision(
        tmp_path, publication, first
    )

    state = read_publication_workspace_state(publication_path)

    assert state.selected_glossary_revision_digests == (glossary.semantic_digest,)
    assert state.selected_revision_digests == (fragment.semantic_digest,)
    assert state.selected_revisions[0].markdown_body.startswith("阅读器")
    assert not state.diagnostics

    output = tmp_path / "reader-propagated.html"
    result = render_publication_html(publication_path, output)
    payload = _payload(output.read_text(encoding="utf-8"))
    assert result.selected_revision_digests == (fragment.semantic_digest,)
    assert result.selected_glossary_revision_digests == (glossary.semantic_digest,)
    assert payload["selected_revision_digests"] == [fragment.semantic_digest]
    assert payload["selected_glossary_revision_digests"] == [
        glossary.semantic_digest
    ]
    validate_standalone_html(publication, output)


def test_glossary_propagation_versions_peer_definitions_atomically(
    tmp_path: Path,
) -> None:
    publication_path, publication, _first = _workspace(tmp_path)
    publication, commit, dependent, _path = _peer_glossary_definition_batch(
        tmp_path, publication
    )

    state = read_publication_workspace_state(publication_path)

    assert state.selected_glossary_revision_digests == (
        commit.semantic_digest,
        dependent.semantic_digest,
    )
    selected_entries = {
        item.entry_id: item.entry for item in state.glossary_revisions
    }
    assert selected_entries["term-peer"]["definition"].startswith("阅读器")

    output = tmp_path / "reader-peer-definition.html"
    result = render_publication_html(publication_path, output)
    payload = _payload(output.read_text(encoding="utf-8"))
    assert result.selected_glossary_revision_digests == (
        commit.semantic_digest,
        dependent.semantic_digest,
    )
    revisions = {
        item["entry_id"]: item for item in payload["glossary_revisions"]
    }
    assert revisions["term-peer"]["entry"]["definition"].startswith(
        "阅读器"
    )
    validate_standalone_html(publication, output)


def test_glossary_propagation_rejects_a_missing_peer_definition_member(
    tmp_path: Path,
) -> None:
    publication_path, publication, _first = _workspace(tmp_path)
    _publication, _commit, _dependent, path = _peer_glossary_definition_batch(
        tmp_path, publication
    )
    path.unlink()

    state = read_publication_workspace_state(publication_path)

    assert state.selected_glossary_revision_digests == ()
    assert any(
        item.code == "incomplete_glossary_propagation"
        for item in state.diagnostics
    )


def test_glossary_propagation_rejects_a_peer_definition_fork(
    tmp_path: Path,
) -> None:
    publication_path, publication, _first = _workspace(tmp_path)
    publication, _commit, dependent, _path = _peer_glossary_definition_batch(
        tmp_path, publication
    )
    peer_entry = dict(publication.glossary[1])
    manual = GlossaryRevision(
        entry_id="term-peer",
        revision=2,
        parent_semantic_digest=dependent.parent_semantic_digest,
        entry={**peer_entry, "definition": "人工修订解释。"},
        provenance={"producer": "alc-render-browser"},
    )
    write_glossary_revision(tmp_path, manual)

    state = read_publication_workspace_state(publication_path)

    assert state.selected_glossary_revision_digests == (
        manual.semantic_digest,
    )
    assert any(
        item.code == "stale_glossary_propagation_parent"
        for item in state.diagnostics
    )


def test_manual_peer_edit_can_descend_from_propagated_definition(
    tmp_path: Path,
) -> None:
    publication_path, publication, _first = _workspace(tmp_path)
    _publication, commit, dependent, _path = _peer_glossary_definition_batch(
        tmp_path, publication
    )
    manual = GlossaryRevision(
        entry_id=dependent.entry_id,
        revision=3,
        parent_semantic_digest=dependent.semantic_digest,
        entry={**dict(dependent.entry), "definition": "后续人工解释。"},
        provenance={"producer": "alc-render-browser"},
    )
    write_glossary_revision(tmp_path, manual)

    state = read_publication_workspace_state(publication_path)

    assert state.selected_glossary_revision_digests == (
        commit.semantic_digest,
        manual.semantic_digest,
    )
    assert dependent.semantic_digest in {
        item.semantic_digest for item in state.glossary_revisions
    }


@pytest.mark.parametrize("role", ["translation", "companion", "guide"])
def test_glossary_propagation_accepts_authored_reading_aid_roles(
    tmp_path: Path,
    role: str,
) -> None:
    _publication_path, publication, first = _workspace(tmp_path)
    fragment = FragmentRevision(
        source=first.source,
        fragment_id=f"{role}-term-reader",
        revision=2,
        parent_semantic_digest=first.semantic_digest,
        anchor=first.anchor,
        priority={"translation": 10, "companion": 20, "guide": 101}[role],
        role=role,
        language=first.language,
        title=None,
        citation_ids=(),
        appearance=None,
        deleted=False,
        provenance={
            "producer": "alc-render-browser",
            "glossary_mentions_schema": "alc.render.glossary_mentions.v1",
            "glossary_mentions": [
                {
                    "entry_id": "term-reader",
                    "markdown_start": 0,
                    "markdown_end": 2,
                    "surface": "读者",
                }
            ],
        },
        markdown_body="读者辅助说明。",
    )

    _validate_fragment_glossary_mentions(publication, fragment)

    if role == "translation":
        entry = dict(publication.glossary[0])
        unanchored = replace(
            publication,
            glossary=({**entry, "anchor_ids": ["another-block"]},),
        )
        _validate_fragment_glossary_mentions(unanchored, fragment)


def test_glossary_propagation_rejects_note_role(tmp_path: Path) -> None:
    _publication_path, publication, first = _workspace(tmp_path)
    note = FragmentRevision(
        source=first.source,
        fragment_id="note-term-reader",
        revision=2,
        parent_semantic_digest=first.semantic_digest,
        anchor=first.anchor,
        priority=110,
        role="note",
        language=first.language,
        title=None,
        citation_ids=(),
        appearance=None,
        deleted=False,
        provenance={
            "producer": "alc-render-browser",
            "glossary_mentions_schema": "alc.render.glossary_mentions.v1",
            "glossary_mentions": [],
        },
        markdown_body="用户笔记。",
    )

    with pytest.raises(HTMLRenderError, match="role is not editable"):
        _validate_fragment_glossary_mentions(publication, note)


def test_glossary_propagation_batch_is_ignored_when_a_member_is_missing(
    tmp_path: Path,
) -> None:
    publication_path, publication, first = _workspace(tmp_path)
    _glossary, _fragment, path = _glossary_propagation_revision(
        tmp_path, publication, first
    )
    path.unlink()

    state = read_publication_workspace_state(publication_path)

    assert state.selected_glossary_revision_digests == ()
    assert state.selected_revision_digests == (first.semantic_digest,)
    assert any(
        item.code == "incomplete_glossary_propagation"
        for item in state.diagnostics
    )


def test_uncommitted_staged_glossary_fragments_are_invisible(
    tmp_path: Path,
) -> None:
    publication_path, publication, first = _workspace(tmp_path)
    glossary, _fragment, staged_path = _glossary_propagation_revision(
        tmp_path, publication, first
    )
    (tmp_path / "glossary" / glossary_revision_filename(glossary)).unlink()

    state = read_publication_workspace_state(publication_path)

    assert staged_path.exists()
    assert state.selected_glossary_revision_digests == ()
    assert state.selected_revision_digests == (first.semantic_digest,)
    assert not state.diagnostics


def test_glossary_propagation_follows_a_manually_edited_fragment_successor(
    tmp_path: Path,
) -> None:
    publication_path, publication, first = _workspace(tmp_path)
    glossary_v2, fragment_v2, _path = _glossary_propagation_revision(
        tmp_path, publication, first
    )
    manual_body = "补充：阅读器仍在使用 [@ref-1]。"
    manual_v3 = FragmentRevision(
        source=first.source,
        fragment_id=first.fragment_id,
        revision=3,
        parent_semantic_digest=fragment_v2.semantic_digest,
        anchor=first.anchor,
        priority=first.priority,
        role=first.role,
        language=first.language,
        title=first.title,
        citation_ids=first.citation_ids,
        appearance=first.appearance,
        deleted=first.deleted,
        provenance={
            **dict(first.provenance),
            "last_editor": "alc-render-browser",
            "glossary_mentions_schema": "alc.render.glossary_mentions.v1",
            "glossary_mentions": [
                {
                    "entry_id": "term-reader",
                    "markdown_start": 3,
                    "markdown_end": 6,
                    "surface": "阅读器",
                }
            ],
        },
        markdown_body=manual_body,
    )
    write_fragment_revision(tmp_path, manual_v3)

    batch_id = "glossary-test-batch-2"
    final_body = "补充：阅读界面仍在使用 [@ref-1]。"
    fragment_v4 = FragmentRevision(
        source=first.source,
        fragment_id=first.fragment_id,
        revision=4,
        parent_semantic_digest=manual_v3.semantic_digest,
        anchor=first.anchor,
        priority=first.priority,
        role=first.role,
        language=first.language,
        title=first.title,
        citation_ids=first.citation_ids,
        appearance=first.appearance,
        deleted=first.deleted,
        provenance={
            **dict(manual_v3.provenance),
            "reason": "glossary-propagation",
            "propagation_batch_id": batch_id,
            "glossary_entry_id": "term-reader",
            "glossary_mentions": [
                {
                    "entry_id": "term-reader",
                    "markdown_start": 3,
                    "markdown_end": 7,
                    "surface": "阅读界面",
                }
            ],
        },
        markdown_body=final_body,
    )
    relative = (
        f"glossary-batches/{batch_id}/fragments/"
        f"{fragment_revision_filename(fragment_v4)}"
    )
    path = tmp_path.joinpath(*relative.split("/"))
    path.parent.mkdir(parents=True)
    path.write_text(encode_fragment_revision(fragment_v4), encoding="utf-8")
    entry_v2 = dict(glossary_v2.entry)
    glossary_v3 = GlossaryRevision(
        entry_id="term-reader",
        revision=3,
        parent_semantic_digest=glossary_v2.semantic_digest,
        entry={**entry_v2, "translated_term": "阅读界面"},
        provenance={
            "producer": "alc-render-browser",
            "propagation": {
                "schema_version": "alc.render.glossary_propagation.v1",
                "batch_id": batch_id,
                "fragments": [
                    {
                        "path": relative,
                        "fragment_id": fragment_v4.fragment_id,
                        "revision": fragment_v4.revision,
                        "parent_semantic_digest": fragment_v4.parent_semantic_digest,
                        "semantic_digest": fragment_v4.semantic_digest,
                    }
                ],
            },
        },
    )
    write_glossary_revision(tmp_path, glossary_v3)

    state = read_publication_workspace_state(publication_path)

    assert state.selected_glossary_revision_digests == (glossary_v3.semantic_digest,)
    assert state.selected_revision_digests == (fragment_v4.semantic_digest,)
    assert state.selected_revisions[0].markdown_body == final_body
    assert not state.diagnostics


def test_glossary_propagation_batch_is_ignored_on_a_stale_fragment_parent(
    tmp_path: Path,
) -> None:
    publication_path, publication, first = _workspace(tmp_path)
    _glossary_propagation_revision(
        tmp_path, publication, first, parent="f" * 64
    )

    state = read_publication_workspace_state(publication_path)

    assert state.selected_glossary_revision_digests == ()
    assert state.selected_revision_digests == (first.semantic_digest,)
    assert any(
        item.code == "stale_glossary_propagation_parent"
        for item in state.diagnostics
    )


def test_glossary_propagation_readmits_an_equivalent_retry_after_rejection(
    tmp_path: Path,
) -> None:
    publication_path, publication, first = _workspace(tmp_path)
    valid, valid_fragment, _path = _glossary_propagation_revision(
        tmp_path,
        publication,
        first,
        batch_id="glossary-valid-retry",
    )
    stale, _stale_fragment, _stale_path = _glossary_propagation_revision(
        tmp_path,
        publication,
        first,
        parent="f" * 64,
        batch_id="glossary-stale-retry",
    )
    successor = GlossaryRevision(
        entry_id=stale.entry_id,
        revision=3,
        parent_semantic_digest=stale.semantic_digest,
        entry={**dict(stale.entry), "definition": "后续解释。"},
        provenance={"producer": "alc-render-browser"},
    )
    write_glossary_revision(tmp_path, successor)

    state = read_publication_workspace_state(publication_path)

    assert state.selected_glossary_revision_digests == (valid.semantic_digest,)
    assert state.selected_revision_digests == (valid_fragment.semantic_digest,)
    assert any(
        item.code == "stale_glossary_propagation_parent"
        for item in state.diagnostics
    )


def test_glossary_propagation_rejects_an_existing_fragment_fork(
    tmp_path: Path,
) -> None:
    publication_path, publication, first = _workspace(tmp_path)
    for body in ("人工分支甲 [@ref-1]。", "人工分支乙 [@ref-1]。"):
        write_fragment_revision(
            tmp_path,
            _revision(
                publication.source_document,
                body=body,
                revision=2,
                parent=first.semantic_digest,
            ),
        )
    _glossary_propagation_revision(
        tmp_path,
        publication,
        first,
        batch_id="glossary-forked-fragment",
    )

    state = read_publication_workspace_state(publication_path)

    assert state.selected_glossary_revision_digests == ()
    assert state.selected_revision_digests == (first.semantic_digest,)
    assert any(
        item.code == "stale_glossary_propagation_parent"
        for item in state.diagnostics
    )


def test_glossary_history_symlink_outside_project_is_ignored(
    tmp_path: Path,
) -> None:
    publication_path, publication, _first = _workspace(tmp_path)
    entry = dict(publication.glossary[0])
    revision = GlossaryRevision(
        entry_id="term-reader",
        revision=2,
        parent_semantic_digest=glossary_base_semantic_digest(entry),
        entry={**entry, "translated_term": "外部术语"},
        provenance={"producer": "alc-render-browser"},
    )
    outside = tmp_path.parent / f"{tmp_path.name}-outside-glossary"
    outside.mkdir()
    outside_revision = write_glossary_revision(outside, revision)
    glossary_root = tmp_path / "glossary"
    glossary_root.mkdir()
    (glossary_root / outside_revision.name).symlink_to(outside_revision)

    state = read_publication_workspace_state(publication_path)

    assert state.selected_glossary_revision_digests == ()
    assert any(
        item.code == "glossary_path_escapes_project"
        for item in state.diagnostics
    )


def test_rendered_html_warnings_include_glossary_diagnostics(
    tmp_path: Path,
) -> None:
    publication_path, _publication, _first = _workspace(tmp_path)
    glossary_root = tmp_path / "glossary"
    glossary_root.mkdir()
    malformed = glossary_root / f"revision-000002-{'0' * 64}.md"
    malformed.write_text("not a glossary revision", encoding="utf-8")
    result = render_publication_html(publication_path, tmp_path / "reader.html")

    assert any("malformed_glossary_revision" in item for item in result.warnings)


def test_legacy_glossary_json_history_remains_loadable(tmp_path: Path) -> None:
    publication_path, publication, _selected = _workspace(tmp_path)
    base = dict(publication.glossary[0])
    revision = GlossaryRevision(
        entry_id="term-reader",
        revision=2,
        parent_semantic_digest=glossary_base_semantic_digest(base),
        entry={**base, "translated_term": "阅读器"},
        provenance={"producer": "alc-render-browser"},
    )
    filename = glossary_revision_filename(revision).removesuffix(".md") + ".json"
    target = tmp_path / "glossary" / filename
    target.parent.mkdir()
    target.write_text(
        json.dumps(
            glossary_revision_to_document(revision),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    state = read_publication_workspace_state(publication_path)

    assert state.selected_glossary_revision_digests == (revision.semantic_digest,)


def test_reader_icon_link_uses_embedded_resource() -> None:
    link = _reader_icon_link(
        {"reader_icon": {"logical_name": "alc-reader-icon.svg"}},
        {
            "resources": [
                {
                    "logical_name": "alc-reader-icon.svg",
                    "media_type": "image/svg+xml",
                    "data_uri": "data:image/svg+xml;base64,PHN2Zy8+",
                }
            ]
        },
    )

    assert 'rel="icon"' in link
    assert 'type="image/svg+xml"' in link
    assert 'href="data:image/svg+xml;base64,PHN2Zy8+"' in link


def test_rendered_html_is_standalone_and_embeds_atomic_markdown(
    tmp_path: Path,
) -> None:
    asset_payload = b"\x89PNG\r\n\x1a\nportable-source-figure"
    publication_path, publication, selected = _workspace(
        tmp_path,
        asset_payload=asset_payload,
        add_second_revision=True,
    )
    output = tmp_path / "reader.html"

    result = render_publication_html(publication_path, output)
    text = output.read_text(encoding="utf-8")
    payload = _payload(text)

    assert result.publication_digest == publication.publication_digest
    assert result.selected_revision_digests == (selected.semantic_digest,)
    assert 'src="assets/' not in text
    assert 'href="assets/' not in text
    assert "window.markdownit" in text
    assert "window.katex" in text
    assert "showDirectoryPicker" in text
    assert "@media print" in text
    assert "--print-to-pdf" not in text
    assert 'id="alc-export"' in text
    assert 'id="alc-view"' in text
    assert 'id="alc-view-panel"' in text
    assert 'aria-labelledby="alc-view-heading"' in text
    assert 'id="alc-view-options"' in text
    assert 'id="alc-speech"' in text
    assert 'id="alc-speech-panel"' in text
    assert 'aria-labelledby="alc-speech-heading"' in text
    assert 'id="alc-speech-heading"' in text
    assert 'id="alc-speech-role-options"' in text
    assert 'id="alc-speech-source-voice"' in text
    assert 'id="alc-speech-target-voice"' in text
    assert 'id="alc-speech-panel-player"' in text
    assert 'id="alc-speech-dock"' in text
    assert text.count('class="alc-tool-panel-header') == 3
    assert 'id="alc-settings"' in text
    assert 'id="alc-settings-panel"' in text
    assert 'id="alc-settings-layout"' in text
    assert 'id="alc-settings-english-font"' in text
    assert 'id="alc-settings-chinese-font"' in text
    assert 'id="alc-settings-scale"' in text
    assert 'id="alc-settings-line"' in text
    assert 'id="alc-settings-block-spacing"' in text
    assert 'id="alc-settings-block-spacing-value"' in text
    assert 'id="alc-settings-width"' in text
    assert 'id="alc-unsaved-dialog"' in text
    assert 'id="alc-unsaved-discard"' in text
    assert 'id="alc-unsaved-save"' in text
    assert 'id="alc-storage-status" class="alc-storage-status" role="status"' in text
    assert 'id="alc-editor-error" class="alc-editor-error" role="alert"' in text
    assert "You changed the current content. Save it?" in text
    assert "Save the changes before leaving this editor" not in text
    assert text.count('class="alc-tool-icon"') == 6
    assert text.count('class="alc-tool-button alc-tool-icon-button"') == 6
    assert 'id="alc-connect" class="alc-tool-button alc-tool-icon-button"' in text
    assert 'd="M11 5 6 9H2v6h4l5 4V5Z"' in text
    assert 'd="M4 10h4l4-3v10l-4-3H4Z"' not in text
    assert 'aria-label="New save location" title="New save location"' in text
    assert 'id="alc-contents-resizer"' in text
    assert 'role="separator" aria-orientation="vertical"' in text
    assert 'id="alc-export-panel"' in text
    assert 'aria-labelledby="alc-export-heading"' in text
    assert 'id="alc-export-heading"' in text
    assert 'id="alc-export-markdown-section"' in text
    assert 'id="alc-export-scope"' in text
    assert 'id="alc-export-content"' in text
    assert 'id="alc-export-markdown-mode"' in text
    assert 'id="alc-export-markdown-file-label"' in text
    assert 'id="alc-export-markdown-package-label"' in text
    assert 'id="alc-export-markdown-package"' in text
    assert 'id="alc-export-empty"' not in text
    assert 'alc-export-action-primary' not in text
    assert 'id="alc-export-markdown-label"' in text
    assert 'id="alc-export-html-section"' in text
    assert 'id="alc-export-html"' in text
    assert 'id="alc-export-html-label"' in text
    assert 'id="alc-export-pdf-section"' in text
    assert 'id="alc-export-pdf"' in text
    assert 'id="alc-export-pdf-label"' in text
    assert '<section id="alc-editor-advanced"' in text
    assert 'id="alc-editor-advanced-label"' not in text
    assert "Preview and more settings" not in text
    assert 'id="alc-editor-glossary-source-label">Source (read-only)</span>' in text
    assert '<textarea id="alc-editor-glossary-source" readonly' in text
    assert 'aria-readonly="true"></textarea>' in text
    assert 'id="alc-editor-priority"' in text
    assert 'id="alc-editor-color-presets"' in text
    assert 'id="alc-editor-foreground-picker"' in text
    assert 'pattern="#[0-9A-Fa-f]{6}"' in text
    assert 'id="alc-editor-background-picker"' in text
    assert 'id="alc-editor-colors-reset"' in text
    assert 'id="alc-editor-close" class="alc-settings-close"' in text
    assert 'id="alc-editor-colors-label">Style for this role and priority' in text
    assert 'id="alc-editor-foreground-label">Text color' in text
    assert 'id="alc-editor-background-label">Background color' in text
    assert 'id="alc-editor-delete"' in text
    assert 'class="alc-dialog-commit-actions"' in text
    assert 'class="alc-editor-delete"' in text
    assert text.index('id="alc-editor-delete"') < text.index('id="alc-editor-save"')
    assert "line-break: strict" in text
    assert '<h2 id="alc-editor-heading">Edit</h2>' in text
    assert '<button id="alc-editor-cancel" type="button">Cancel</button>' in text
    assert '<button id="alc-editor-save" type="button">Save</button>' in text
    assert "Edit overlay" not in text
    assert "Save as new revision" not in text
    assert "data:image/png;base64," in text
    validate_standalone_html(publication, output)
    assert payload["publication"]["publication_digest"] == (
        publication.publication_digest
    )
    assert payload["revisions"][0]["metadata"]["appearance"] is None
    assert payload["publication"]["outline"] == [
        {
            "anchor_block_id": "block-heading",
            "block_end": 3,
            "block_start": 0,
            "level": 1,
            "ordinal": 0,
            "path": ["section-reader"],
            "section_id": "section-reader",
            "title": "Reader",
        }
    ]
    assert payload["selected_revision_digests"] == [selected.semantic_digest]
    revisions = payload["revisions"]
    assert [item["metadata"]["revision"] for item in revisions] == [1, 2]
    assert revisions[-1]["markdown_body"] == "修订后的译文 [@ref-1]。"


def test_workspace_state_exposes_current_heads_and_edition_identity(
    tmp_path: Path,
) -> None:
    publication_path, publication, selected = _workspace(
        tmp_path, add_second_revision=True
    )

    state = read_publication_workspace_state(publication_path)

    assert state.publication == publication
    assert state.selected_revisions == (selected,)
    assert state.selected_revision_digests == (selected.semantic_digest,)
    assert state.diagnostics == ()
    assert state.edition_digest == publication_edition_digest(
        publication.publication_digest,
        state.selected_revision_digests,
    )


def test_standalone_validation_detects_a_stale_selected_revision_head(
    tmp_path: Path,
) -> None:
    publication_path, publication, first = _workspace(tmp_path)
    output = tmp_path / "reader.html"
    render_publication_html(publication_path, output)

    second = _revision(
        _rich_document(),
        body="新的当前版本 [@ref-1]。",
        revision=2,
        parent=first.semantic_digest,
    )
    write_fragment_revision(tmp_path, second)
    state = read_publication_workspace_state(publication_path)

    with pytest.raises(HTMLRenderError, match="differ from expected workspace"):
        validate_standalone_html(
            publication,
            output,
            expected_selected_revision_digests=state.selected_revision_digests,
        )


def test_standalone_reader_v2_defers_blocks_revisions_and_resources(
    tmp_path: Path,
) -> None:
    publication_path, publication, _selected = _workspace(
        tmp_path,
        asset_payload=b"\x89PNG\r\n\x1a\nlazy-resource",
        add_second_revision=True,
    )
    output = tmp_path / "reader-v2.html"
    render_publication_html(publication_path, output)
    text = output.read_text(encoding="utf-8")
    boot = _boot_payload(text)

    assert boot["schema_version"] == "alc.render.reader_payload.v2"
    assert boot["revisions"] == []
    assert boot["block_fingerprints"] == {}
    assert all("data_uri" not in item for item in boot["resources"])
    assert len(boot["block_manifest"]) == 3
    assert len(boot["reader_chunks"]) == 1
    assert boot["selected_roles"] == ["translation"]
    assert boot["selected_heading_fragments"] == []
    assert text.count('class="alc-render-reader-chunk"') == 1
    assert text.count('class="alc-render-reader-resource"') == 1
    assert len(_payload(text)["revisions"]) == 2
    validate_standalone_html(publication, output)


def test_standalone_reader_v2_boot_declares_dynamic_roles_and_heading_text() -> None:
    payload = {
        "schema_version": "alc.render.reader_payload.v1",
        "publication": {
            "source_document": {
                "blocks": [
                    {
                        "block_id": "heading-1",
                        "kind": "heading",
                        "ordinal": 0,
                        "payload": {"text": "Source", "level": 1},
                    }
                ]
            },
            "outline": [
                {
                    "section_id": "section-1",
                    "anchor_block_id": "heading-1",
                }
            ],
            "reader_profile": {},
            "labels": {},
        },
        "revisions": [
            {
                "metadata": {
                    "fragment_id": "custom-heading",
                    "priority": 25,
                    "role": "commentary-custom",
                    "anchor": {"kind": "section", "target_id": "section-1"},
                },
                "markdown_body": "# Visible custom heading\n",
                "semantic_digest": "a" * 64,
            }
        ],
        "selected_revision_digests": ["a" * 64],
        "resources": [],
        "block_fingerprints": {"heading-1": "b" * 64},
    }
    html = (
        '<script id="alc-render-payload" type="application/json">'
        + json.dumps(payload)
        + "</script>"
    )

    split = _split_reader_payload(html)
    boot = _boot_payload(split)

    assert boot["selected_roles"] == ["commentary-custom"]
    assert boot["selected_heading_fragments"] == [
        {
            "fragment_id": "custom-heading",
            "role": "commentary-custom",
            "target_id": "heading-1",
            "priority": 25,
            "markdown_body": "# Visible custom heading\n",
        }
    ]


def test_standalone_reader_v2_rejects_a_missing_chunk(tmp_path: Path) -> None:
    publication_path, publication, _selected = _workspace(tmp_path)
    output = tmp_path / "reader-v2.html"
    render_publication_html(publication_path, output)
    text = output.read_text(encoding="utf-8")
    text = re.sub(
        r'<script[^>]*class="alc-render-reader-chunk"[^>]*>.*?</script>',
        "",
        text,
        count=1,
        flags=re.DOTALL,
    )
    output.write_text(text, encoding="utf-8")

    with pytest.raises(HTMLRenderError, match="payload count"):
        validate_standalone_html(publication, output)


def test_standalone_reader_v2_rejects_visibility_manifest_drift(
    tmp_path: Path,
) -> None:
    publication_path, publication, _selected = _workspace(tmp_path)
    output = tmp_path / "reader-v2.html"
    render_publication_html(publication_path, output)
    text = output.read_text(encoding="utf-8")
    boot = _boot_payload(text)
    boot["selected_roles"] = ["invented-role"]
    encoded = json.dumps(
        boot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).replace("</script", r"<\/script")
    text = re.sub(
        r'(<script id="alc-render-payload" type="application/json">)'
        r".*?(</script>)",
        lambda match: match.group(1) + encoded + match.group(2),
        text,
        count=1,
        flags=re.DOTALL,
    )
    output.write_text(text, encoding="utf-8")

    with pytest.raises(HTMLRenderError, match="visibility manifest differs"):
        validate_standalone_html(publication, output)


def test_standalone_reader_v2_declares_cross_chunk_anchor_dependencies(
    tmp_path: Path,
) -> None:
    source_payload = b"cross chunk source"
    source = SourceArtifact(
        SourceFormat.MARKDOWN,
        hashlib.sha256(source_payload).hexdigest(),
        len(source_payload),
        "text/markdown",
        SourceOrigin(SourceOriginKind.REPOSITORY),
    )
    blocks = tuple(
        RichBlock(
            f"block-{index:02d}",
            index,
            RichBlockKind.PARAGRAPH,
            ("section-cross",),
            SourceLocator(SourceFormat.MARKDOWN, index + 1, 1, index + 1, 8),
            {
                "text": f"Block {index}.",
                "inline_spans": [
                    {
                        "kind": "text",
                        "start": 0,
                        "end": len(f"Block {index}."),
                        "text": f"Block {index}.",
                    }
                ],
            },
        )
        for index in range(40)
    )
    document = RichDocument(
        source,
        blocks,
        (
            RichSection(
                "section-cross",
                "Cross chunk",
                1,
                0,
                ("section-cross",),
                0,
                len(blocks),
            ),
        ),
        (),
    )
    revision = FragmentRevision(
        source=source_identity_from_rich_document(document),
        fragment_id="companion-cross-chunk",
        revision=1,
        parent_semantic_digest=None,
        anchor=FragmentAnchor(
            "block",
            blocks[0].block_id,
            (
                anchor_block_from_rich_block(blocks[0]),
                anchor_block_from_rich_block(blocks[-1]),
            ),
        ),
        priority=20,
        role="companion",
        language="en",
        title="Cross chunk",
        citation_ids=(),
        provenance={"producer": "alc-companion"},
        markdown_body="Cross-chunk companion.",
    )
    revision_path = write_fragment_revision(tmp_path, revision)
    layer = Layer(
        revision.source,
        "alc-companion",
        (
            fragment_revision_ref(
                relative_fragment_path(tmp_path, revision_path), revision
            ),
        ),
    )
    layer_path = tmp_path / "layers" / "companion.json"
    write_layer(layer_path, layer)
    publication = Publication(
        source_document=document,
        layers=(layer.reference("layers/companion.json"),),
        labels={"document_title": "Cross chunk"},
        reader_profile={"title": "Cross chunk"},
    )
    publication_path = tmp_path / "publication.json"
    write_publication(publication_path, publication)
    output = tmp_path / "cross-chunk.html"
    render_publication_html(publication_path, output)
    text = output.read_text(encoding="utf-8")
    boot = _boot_payload(text)
    first = boot["reader_chunks"][0]
    chunk = _extract_json_script(text, first["payload_id"])

    assert chunk["required_chunk_ids"] == ["payload-chunk-0001"]
    validate_standalone_html(publication, output)

    legacy_chunk = dict(chunk)
    del legacy_chunk["required_chunk_ids"]
    encoded = json.dumps(
        legacy_chunk,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).replace("</script", r"<\/script")
    text = re.sub(
        rf'(<script id="{re.escape(first["payload_id"])}"[^>]*>)'
        r".*?(</script>)",
        lambda match: match.group(1) + encoded + match.group(2),
        text,
        count=1,
        flags=re.DOTALL,
    )
    output.write_text(text, encoding="utf-8")
    validate_standalone_html(publication, output)


def test_browser_exported_html_remains_a_valid_latest_reader(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    publication_path, publication, selected = _workspace(tmp_path)
    initial_path = tmp_path / "initial.html"
    render_publication_html(publication_path, initial_path)
    initial_html = initial_path.read_text(encoding="utf-8")
    payload = _payload(initial_html)
    export_template = initial_html.replace(
        '<html lang="zh-CN">',
        '<html lang="zh-CN" style="--alc-font-scale:1.15;'
        '--alc-reader-line-height:1.8;--alc-reader-width:81.6rem">',
        1,
    ).replace(
        '<body data-publication-digest=',
        '<body class="alc-stacked-layout" data-alc-reader-layout="stacked" '
        'data-alc-reader-edit-activation="double" '
        'data-alc-reader-english-font="georgia" '
        'data-alc-reader-chinese-font="song" '
        'data-alc-reader-scale="115" data-alc-reader-line-height="1.8" '
        'data-alc-reader-width="85" data-publication-digest=',
        1,
    )
    export_template_path = tmp_path / "export-template.html"
    export_template_path.write_text(export_template, encoding="utf-8")
    javascript = (
        Path(__file__).parents[1]
        / "src"
        / "alc_render"
        / "web_assets"
        / "reader.js"
    ).read_text(encoding="utf-8")
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    instrumented = (
        "globalThis.window = globalThis;\n"
        + javascript[:startup]
        + """
  globalThis.__alcReaderTest = {
    state: state,
    addRevision: addRevision,
    addGlossaryRevision: addGlossaryRevision,
    buildStandaloneExportHtml: buildStandaloneExportHtml,
    canonicalDigest: canonicalDigest,
    glossaryBaseMaterial: glossaryBaseMaterial,
    glossaryRevisionMaterial: glossaryRevisionMaterial,
    initialRevisions: initialRevisions,
    metadataOnly: metadataOnly,
    prepareGlossary: prepareGlossary,
    resolveOne: resolveOne,
    resolveGlossaryAll: resolveGlossaryAll,
    semanticDigest: semanticDigest
  };
}());
var fs = require("fs");
var helpers = globalThis.__alcReaderTest;
helpers.state.payload = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
helpers.state.exportStandaloneSupported = true;
helpers.state.exportHtmlTemplate = fs.readFileSync(process.argv[3], "utf8");
helpers.initialRevisions();
var current = helpers.state.selected.values().next().value;
var metadata = helpers.metadataOnly(current);
metadata.revision = current.revision + 1;
metadata.parent_semantic_digest = current.semantic_digest;
metadata.title = "Browser export";
metadata.provenance = {producer: "alc-render-browser"};
var body = "浏览器中的最新版 [@ref-1]。";
(async function () {
  await helpers.prepareGlossary();
  var glossaryBase = helpers.state.glossaryBase[0];
  var glossaryBaseDigest = await helpers.canonicalDigest(
    helpers.glossaryBaseMaterial(glossaryBase)
  );
  var glossaryMetadata = {
    schema_version: "alc.render.glossary_revision.v1",
    entry_id: "term-reader",
    revision: 2,
    parent_semantic_digest: glossaryBaseDigest,
    entry: Object.assign({}, glossaryBase, {
      translated_term: "阅读器",
      definition: "浏览器导出的最新版。"
    }),
    provenance: {producer: "alc-render-browser"}
  };
  var glossaryDigest = await helpers.canonicalDigest(
    helpers.glossaryRevisionMaterial(glossaryMetadata)
  );
  helpers.addGlossaryRevision(Object.assign({}, glossaryMetadata, {
    semantic_digest: glossaryDigest
  }));
  helpers.resolveGlossaryAll();
  var digest = await helpers.semanticDigest(metadata, body);
  helpers.addRevision({
    metadata: metadata,
    markdown_body: body,
    semantic_digest: digest
  });
  helpers.resolveOne(metadata.fragment_id);
  process.stdout.write(helpers.buildStandaloneExportHtml());
})().catch(function (error) {
  console.error(error.stack || error);
  process.exitCode = 1;
});
"""
    )
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    completed = subprocess.run(
        [node, "-", str(payload_path), str(export_template_path)],
        input=instrumented,
        check=True,
        capture_output=True,
        text=True,
    )
    exported_path = tmp_path / "exported.html"
    exported_path.write_text(completed.stdout, encoding="utf-8")
    exported = _payload(completed.stdout)

    assert exported["selected_revision_digests"] != [selected.semantic_digest]
    assert [item["metadata"]["revision"] for item in exported["revisions"]] == [
        1,
        2,
    ]
    assert exported["revisions"][-1]["markdown_body"] == (
        "浏览器中的最新版 [@ref-1]。"
    )
    assert exported["publication"]["glossary"][0]["translated_term"] == "读者"
    assert exported["glossary_revisions"][0]["entry"]["translated_term"] == "阅读器"
    assert exported["selected_glossary_revision_digests"]
    assert 'id="alc-export"' in completed.stdout
    assert "showDirectoryPicker" in completed.stdout
    assert 'class="alc-stacked-layout"' in completed.stdout
    assert 'data-alc-reader-layout="stacked"' in completed.stdout
    assert 'data-alc-reader-english-font="georgia"' in completed.stdout
    assert 'data-alc-reader-chinese-font="song"' in completed.stdout
    assert 'data-alc-reader-scale="115"' in completed.stdout
    assert 'data-alc-reader-line-height="1.8"' in completed.stdout
    assert 'data-alc-reader-width="85"' in completed.stdout
    assert "--alc-font-scale:1.15" in completed.stdout
    assert "--alc-reader-line-height:1.8" in completed.stdout
    assert "--alc-reader-width:81.6rem" in completed.stdout
    validate_standalone_html(publication, exported_path)


def test_repeated_browser_export_recaptures_current_reader_snapshot() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = (
        Path(__file__).parents[1]
        / "src"
        / "alc_render"
        / "web_assets"
        / "reader.js"
    ).read_text(encoding="utf-8")
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    instrumented = (
        "globalThis.window = globalThis;\n"
        + javascript[:startup]
        + r'''
  globalThis.__alcReaderTest = {
    state: state,
    buildStandaloneExportHtml: buildStandaloneExportHtml
  };
}());
function assert(condition, message) {
  if (!condition) throw new Error(message);
}
var snapshot = "first";
function emptySurface() {
  return {replaceChildren: function () {}};
}
function clonedRoot() {
  var body = {
    dataset: {},
    classList: {remove: function () {}}
  };
  var surfaces = {
    body: body,
    "#ac-document": emptySurface(),
    "#alc-book-header": emptySurface(),
    "#alc-contents-list": emptySurface()
  };
  return {
    querySelector: function (selector) { return surfaces[selector] || null; },
    querySelectorAll: function () { return []; },
    get outerHTML() {
      return '<html data-reader-snapshot="' + snapshot + '"><body>' +
        '<script id="alc-render-payload" type="application/json">{}</script>' +
        '</body></html>';
    }
  };
}
globalThis.document = {
  querySelector: function () { return null; },
  documentElement: {cloneNode: function () { return clonedRoot(); }}
};
var helpers = globalThis.__alcReaderTest;
helpers.state.payload = {
  resources: [],
  publication: {
    source_document: {blocks: []},
    labels: {},
    reader_profile: {}
  }
};
helpers.state.revisions = new Map();
helpers.state.selected = new Map();
helpers.state.activeFragmentIds = new Set();
var first = helpers.buildStandaloneExportHtml();
snapshot = "second";
var second = helpers.buildStandaloneExportHtml();
assert(first.includes('data-reader-snapshot="first"'), "first snapshot was not captured");
assert(second.includes('data-reader-snapshot="second"'), "second export reused the first snapshot");
assert(!second.includes('data-reader-snapshot="first"'), "stale snapshot survived the second export");
'''
    )
    completed = subprocess.run(
        [node, "-"],
        input=instrumented,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_renderer_groups_revision_by_front_matter_not_parent_directory(
    tmp_path: Path,
) -> None:
    publication_path, _publication, first = _workspace(tmp_path)
    second = _revision(
        _rich_document(),
        body="目录名不参与身份解析 [@ref-1]。",
        revision=2,
        parent=first.semantic_digest,
    )
    arbitrary = tmp_path / "fragments" / "opaque-storage-layout"
    arbitrary.mkdir()
    (arbitrary / fragment_revision_filename(second)).write_text(
        encode_fragment_revision(second),
        encoding="utf-8",
    )

    output = tmp_path / "opaque-layout.html"
    result = render_publication_html(publication_path, output)
    payload = _payload(output.read_text(encoding="utf-8"))

    assert result.selected_revision_digests == (second.semantic_digest,)
    assert [
        item["metadata"]["revision"] for item in payload["revisions"]
    ] == [1, 2]


def test_source_only_publication_renders_without_layers(tmp_path: Path) -> None:
    publication = Publication(
        _rich_document(),
        labels={"document_title": "Source only"},
        reader_profile={"title": "Source only", "source_language": "en"},
    )
    path = tmp_path / "publication.json"
    write_publication(path, publication)

    result = render_publication_html(path, tmp_path / "source-only.html")

    assert result.selected_revision_digests == ()
    assert (tmp_path / "source-only.html").is_file()


def test_renderer_ignores_stale_machine_fragments_but_keeps_user_notes(
    tmp_path: Path,
) -> None:
    publication_path, _publication, active = _workspace(tmp_path)
    stale = FragmentRevision(
        source=active.source,
        fragment_id="translation-stale-generation",
        revision=1,
        parent_semantic_digest=None,
        anchor=active.anchor,
        priority=10,
        role="translation",
        language=active.language,
        title=None,
        citation_ids=active.citation_ids,
        provenance={"producer": "alc-translate"},
        markdown_body="不再由当前 Layer 声明的旧译文 [@ref-1]。",
    )
    note = FragmentRevision(
        source=active.source,
        fragment_id="user-browser-note",
        revision=1,
        parent_semantic_digest=None,
        anchor=active.anchor,
        priority=110,
        role="note",
        language=active.language,
        title="Reader note",
        citation_ids=(),
        provenance={"producer": "alc-render-browser"},
        markdown_body="用户新增的外挂。",
    )
    write_fragment_revision(tmp_path, stale)
    write_fragment_revision(tmp_path, note)

    result = render_publication_html(
        publication_path, tmp_path / "filtered.html"
    )
    payload = _payload((tmp_path / "filtered.html").read_text(encoding="utf-8"))
    fragment_ids = {
        item["metadata"]["fragment_id"] for item in payload["revisions"]
    }

    assert result.selected_revision_digests == (
        active.semantic_digest,
        note.semantic_digest,
    )
    assert fragment_ids == {active.fragment_id, note.fragment_id}


def test_missing_source_asset_fails_before_publishing_html(tmp_path: Path) -> None:
    publication_path, _, _ = _workspace(
        tmp_path,
        asset_payload=b"\x89PNG\r\n\x1a\nmissing-later",
    )
    (tmp_path / "source-assets" / "figure.png").unlink()
    output = tmp_path / "reader.html"

    with pytest.raises(HTMLRenderError, match="missing|unreadable"):
        render_publication_html(publication_path, output)

    assert not output.exists()


def test_fragment_provenance_must_match_current_rich_source(tmp_path: Path) -> None:
    document = _rich_document()
    normal = _revision(document)
    frozen = anchor_block_from_rich_block(document.blocks[1])
    from alc_render import AnchorBlock

    wrong = FragmentRevision(
        source=normal.source,
        fragment_id=normal.fragment_id,
        revision=1,
        parent_semantic_digest=None,
        anchor=FragmentAnchor(
            "block",
            document.blocks[1].block_id,
            (
                AnchorBlock(
                    frozen.block_id,
                    frozen.kind,
                    frozen.ordinal,
                    frozen.locator,
                    "0" * 64,
                ),
            ),
        ),
        priority=normal.priority,
        role=normal.role,
        language=normal.language,
        title=normal.title,
        citation_ids=normal.citation_ids,
        provenance=normal.provenance,
        markdown_body=normal.markdown_body,
    )
    path = write_fragment_revision(tmp_path, wrong)
    layer = Layer(
        wrong.source,
        "alc-translate",
        (
            fragment_revision_ref(
                relative_fragment_path(tmp_path, path),
                wrong,
            ),
        ),
    )
    write_layer(tmp_path / "layers" / "translation.json", layer)
    publication = Publication(
        document,
        layers=(layer.reference("layers/translation.json"),),
        bibliography=(
            {
                "evidence_id": "ref-1",
                "title": "Reference",
                "source": "https://example.test/reference",
            },
        ),
    )
    publication_path = tmp_path / "publication.json"
    write_publication(publication_path, publication)

    with pytest.raises(HTMLRenderError, match="provenance differs"):
        render_publication_html(publication_path, tmp_path / "reader.html")


def test_fragment_markdown_citations_must_match_declared_ids(
    tmp_path: Path,
) -> None:
    document = _rich_document()
    revision = _revision(document, body="正文含有 [@other]。")
    path = write_fragment_revision(tmp_path, revision)
    layer = Layer(
        revision.source,
        "alc-translate",
        (
            fragment_revision_ref(
                relative_fragment_path(tmp_path, path),
                revision,
            ),
        ),
    )
    write_layer(tmp_path / "layers" / "translation.json", layer)
    publication = Publication(
        document,
        layers=(layer.reference("layers/translation.json"),),
        bibliography=(
            {
                "evidence_id": "ref-1",
                "title": "Reference",
                "source": "https://example.test/reference",
            },
            {
                "evidence_id": "other",
                "title": "Other",
                "source": "https://example.test/other",
            },
        ),
    )
    publication_path = tmp_path / "publication.json"
    write_publication(publication_path, publication)

    with pytest.raises(HTMLRenderError, match="Markdown citations"):
        render_publication_html(publication_path, tmp_path / "reader.html")


def test_layer_rejects_contradictory_fragment_producer(
    tmp_path: Path,
) -> None:
    document = _rich_document()
    normal = _revision(document)
    revision = FragmentRevision(
        source=normal.source,
        fragment_id=normal.fragment_id,
        revision=normal.revision,
        parent_semantic_digest=normal.parent_semantic_digest,
        anchor=normal.anchor,
        priority=normal.priority,
        role=normal.role,
        language=normal.language,
        title=normal.title,
        citation_ids=normal.citation_ids,
        provenance={"producer": "another-producer"},
        markdown_body=normal.markdown_body,
    )
    path = write_fragment_revision(tmp_path, revision)
    layer = Layer(
        revision.source,
        "alc-translate",
        (
            fragment_revision_ref(
                relative_fragment_path(tmp_path, path),
                revision,
            ),
        ),
    )
    write_layer(tmp_path / "layers" / "translation.json", layer)
    publication_path = tmp_path / "publication.json"
    write_publication(
        publication_path,
        Publication(
            document,
            layers=(layer.reference("layers/translation.json"),),
            bibliography=(
                {
                    "evidence_id": "ref-1",
                    "title": "Reference",
                    "source": "https://example.test/reference",
                },
            ),
        ),
    )

    with pytest.raises(HTMLRenderError, match="layer producer"):
        render_publication_html(publication_path, tmp_path / "reader.html")


@pytest.mark.parametrize("tamper", ["revision", "resource"])
def test_standalone_validation_detects_payload_tampering(
    tmp_path: Path,
    tamper: str,
) -> None:
    publication_path, publication, _selected = _workspace(
        tmp_path,
        asset_payload=b"\x89PNG\r\n\x1a\nvalidated",
    )
    output = tmp_path / "reader.html"
    render_publication_html(publication_path, output)
    text = output.read_text(encoding="utf-8")
    payload = _payload(text)
    if tamper == "revision":
        payload["revisions"][0]["markdown_body"] = "tampered"
    else:
        payload["resources"][0]["data_uri"] = "data:image/png;base64,AAAA"
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).replace("</script", r"<\/script")
    text = re.sub(
        r'(<script id="alc-render-payload" type="application/json">)'
        r".*?(</script>)",
        lambda match: match.group(1) + encoded + match.group(2),
        text,
        count=1,
        flags=re.DOTALL,
    )
    text = re.sub(
        r'<script[^>]*class="alc-render-reader-(?:chunk|resource)"[^>]*>'
        r".*?</script>",
        "",
        text,
        flags=re.DOTALL,
    )
    output.write_text(text, encoding="utf-8")

    with pytest.raises(HTMLRenderError, match="fragment identity|resource"):
        validate_standalone_html(publication, output)


def test_publication_owned_resource_is_embedded_and_validated(
    tmp_path: Path,
) -> None:
    publication_path, publication, _selected = _workspace(tmp_path)
    payload = b'{"schema_version":"alc.test.coverage.v1"}\n'
    digest = hashlib.sha256(payload).hexdigest()
    resource_path = tmp_path / "resources" / "coverage.json"
    resource_path.parent.mkdir()
    resource_path.write_bytes(payload)
    publication = Publication(
        source_document=publication.source_document,
        layers=publication.layers,
        glossary=publication.glossary,
        bibliography=publication.bibliography,
        labels=publication.labels,
        resources=(
            {
                "artifact_digest": digest,
                "media_type": "application/json",
                "logical_name": "supplement-coverage.json",
                "size": len(payload),
                "path": "resources/coverage.json",
            },
        ),
        reader_profile=publication.reader_profile,
        outline=publication.outline,
    )
    write_publication(publication_path, publication)
    output = tmp_path / "owned-resource.html"

    render_publication_html(publication_path, output)

    embedded = _payload(output.read_text(encoding="utf-8"))["resources"]
    assert [item["logical_name"] for item in embedded] == [
        "supplement-coverage.json"
    ]
    validate_standalone_html(publication, output)
