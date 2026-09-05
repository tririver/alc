from __future__ import annotations

import json
from pathlib import Path

import alc_companion.publication as publication_module
import pytest
from ac_document import (
    AcDocumentService,
    RichDocumentParserService,
    SourceFormat,
    SourceOrigin,
    SourceOriginKind,
    SourceRepository,
)
from ac_jobs import ImmutableArtifactStore, RunContext, RunRepository, RunSpec
from alc_companion.generation_validation import validate_chapter_guide
from alc_companion.publication import (
    CompanionPublicationError,
    PublishedCompanion,
    build_result_document,
    materialize_published_companion,
    publish_companion,
)
from alc_companion.reviewed_supplements import (
    ReviewedCompanionSupplement,
    ReviewedOwnedResource,
    ReviewedSourceDraft,
    ReviewedSourceUnit,
    ReviewedSupplementEntry,
    reviewed_anchor_fingerprint,
    reviewed_source_inventory_digest,
)
from alc_companion.source_planning import plan_source_chapters
from alc_companion.translation_results import load_translation_selection
from alc_render import (
    AnchorKind,
    FragmentAnchor,
    FragmentRevision,
    Layer,
    anchor_block_from_rich_block,
    block_text_to_markdown,
    decode_fragment_revision,
    encode_fragment_revision,
    fragment_revision_filename,
    fragment_revision_ref,
    render_publication_html,
    source_identity_from_rich_document,
    validate_publication_workspace,
)
from alc_translate import TranslationResult, TranslationRevisionArtifact


def _source(tmp_path: Path):
    repository = SourceRepository(tmp_path / "paper")
    payload = b"# Title\n\nBody.\n\n```python\nprint('x')\n```\n"
    artifact = repository.store_bytes(
        payload,
        source_format=SourceFormat.MARKDOWN,
        origin=SourceOrigin(SourceOriginKind.LOCAL_IMPORT, locator="source.md"),
    )
    return RichDocumentParserService(repository).parse_source(artifact)


def _illustrated_source(tmp_path: Path):
    source_path = tmp_path / "illustrated.md"
    asset_path = tmp_path / "figure.svg"
    asset_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"></svg>',
        encoding="utf-8",
    )
    source_path.write_text(
        "# Illustrated\n\nBody.\n\n![Figure](figure.svg)\n",
        encoding="utf-8",
    )
    service = AcDocumentService(cache_root=tmp_path / "paper")
    artifact = service.import_source(source_path)
    return RichDocumentParserService(service.repository).parse_source(artifact)


def test_publication_uses_atomic_overlays_and_materializes_directly(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    repository = RunRepository(tmp_path / "jobs")
    spec = RunSpec("run", "handler", {"input": "test"})
    snapshot = repository.create(spec)
    context = RunContext(repository, snapshot, resume_input=None)
    translation_result = _translation_result(context, source)
    chapters = [
        {
            "chapter_id": "chapter",
            "title": "Title",
            "block_ids": [block.block_id for block in source.blocks],
            "display_anchor_block_id": source.blocks[0].block_id,
            "section_block_ids": [],
            "section_titles": [],
            "section_levels": [],
            "translation_result": translation_result.to_document(),
            "learning_units": [
                {
                    "unit_id": "unit",
                    "title": "说明",
                    "anchor_block_ids": [source.blocks[1].block_id],
                    "purpose": "companion",
                    "content_markdown": "新增背景。",
                    "citations": [],
                }
            ],
        }
    ]
    published = publish_companion(
        context,
        source=source,
        title="Title",
        authors=(),
        source_language="en",
        target_language="zh-CN",
        translation_mode="enabled",
        reader_labels={"source": "原文"},
        chapters=chapters,
        glossary=(),
        bibliography=(),
        editorial_review={
            "schema_version": "alc.companion.editorial_review.v1",
            "status": "no_changes",
            "inventory_digest": "a" * 64,
            "proposal_digest": "d" * 64,
            "proposer_artifact_digest": "b" * 64,
            "reviewer_artifact_digest": "c" * 64,
            "reason": "The audit binding was incomplete.",
            "warnings": ["The final audit did not bind the proposal."],
            "counts": {
                "reviewed_units": 2,
                "findings": 1,
                "proposed_edits": 2,
                "revised_units": 0,
                "omitted_units": 0,
                "rejected_edits": 2,
            },
            "findings": [],
            "changes": [],
        },
        document_cache_root=tmp_path / "paper",
    )
    result = build_result_document(published)
    assert result["schema_version"] == "alc.companion.build_result.v2"
    assert len(published.publication.layers) == 2
    editorial = published.publication.reader_profile["editorial_review"]
    assert editorial["status"] == "no_changes"
    assert editorial["revised_units"] == 0
    assert editorial["warning"] == ("The final audit did not bind the proposal.")
    assert "Warning:" in editorial["summary"]
    icon = published.publication.reader_profile["reader_icon"]
    assert icon["initial"] == "T"
    assert icon["logical_name"] == "alc-reader-icon.svg"
    icon_resource = next(
        item
        for item in published.publication.resources
        if item["logical_name"] == "alc-reader-icon.svg"
    )
    assert any(
        item.digest.value == icon_resource["artifact_digest"]
        for item in published.resource_refs
    )
    report_resource = next(
        item
        for item in published.publication.resources
        if item["logical_name"] == "alc-companion-editorial-review.json"
    )
    report_ref = next(
        item
        for item in published.resource_refs
        if item.digest.value == report_resource["artifact_digest"]
    )
    assert (
        json.loads(context.artifacts.read_bytes(report_ref))["schema_version"]
        == "alc.companion.editorial_review.v1"
    )
    published_revisions = tuple(
        decode_fragment_revision(context.artifacts.read_bytes(ref).decode("utf-8"))
        for ref in published.fragment_refs
    )
    assert {item.priority for item in published_revisions} == {10, 20}
    assert {
        item.semantic_digest
        for item in published_revisions
        if item.role == "translation"
    } == {
        item.revision.semantic_digest for item in translation_result.revision_artifacts
    }

    workspace = tmp_path / "publication"
    publication_path = materialize_published_companion(
        ImmutableArtifactStore(
            repository.run_directory("run"),
            repository_root=repository.root,
        ),
        published,
        workspace,
    )
    assert publication_path == workspace / "publication.json"
    assert validate_publication_workspace(publication_path) == ()

    writes: list[Path] = []
    original_write = publication_module.atomic_write_bytes

    def record_write(path: Path, payload: bytes) -> None:
        writes.append(path)
        original_write(path, payload)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(publication_module, "atomic_write_bytes", record_write)
    try:
        assert (
            materialize_published_companion(
                ImmutableArtifactStore(
                    repository.run_directory("run"),
                    repository_root=repository.root,
                ),
                published,
                workspace,
            )
            == publication_path
        )
    finally:
        monkeypatch.undo()
    assert writes == []

    incomplete = PublishedCompanion(
        published.publication,
        published.publication_ref,
        published.layer_refs,
        published.fragment_refs[:-1],
        published.resource_refs,
    )
    with pytest.raises(CompanionPublicationError, match="artifacts"):
        materialize_published_companion(
            ImmutableArtifactStore(
                repository.run_directory("run"),
                repository_root=repository.root,
            ),
            incomplete,
            tmp_path / "incomplete",
        )


def test_materialization_validates_resource_size_bytes(tmp_path: Path) -> None:
    source = _illustrated_source(tmp_path)
    chapter = plan_source_chapters(source)[0]
    repository = RunRepository(tmp_path / "jobs")
    snapshot = repository.create(RunSpec("resource-run", "handler", {"input": "test"}))
    context = RunContext(repository, snapshot, resume_input=None)

    published = publish_companion(
        context,
        source=source,
        title="Illustrated",
        authors=(),
        source_language="en",
        target_language="en",
        translation_mode="skipped",
        reader_labels={},
        chapters=(
            {
                "chapter_id": chapter.chapter_id,
                "title": chapter.title,
                "block_ids": list(chapter.block_ids),
                "display_anchor_block_id": chapter.display_anchor_block_id,
                "section_block_ids": list(chapter.section_block_ids),
                "section_titles": list(chapter.section_titles),
                "section_levels": list(chapter.section_levels),
                "translation_result": None,
                "learning_units": [],
            },
        ),
        glossary=(),
        bibliography=(),
        document_cache_root=tmp_path / "paper",
    )

    assert published.resource_refs
    publication_path = materialize_published_companion(
        ImmutableArtifactStore(
            repository.run_directory("resource-run"),
            repository_root=repository.root,
        ),
        published,
        tmp_path / "publication-with-resource",
    )
    assert validate_publication_workspace(publication_path) == ()


def test_missing_source_resource_is_explicitly_degraded(
    tmp_path: Path, monkeypatch
) -> None:
    source = _illustrated_source(tmp_path)
    chapter = plan_source_chapters(source)[0]
    repository = RunRepository(tmp_path / "jobs")
    snapshot = repository.create(
        RunSpec("missing-resource", "handler", {"input": "test"})
    )
    context = RunContext(repository, snapshot, resume_input=None)

    class MissingAssetRepository:
        def get_asset(self, _digest):
            raise OSError("asset unavailable")

        def read_asset_bytes(self, _asset):
            raise AssertionError("missing asset was unexpectedly read")

    class MissingAssetDocument:
        def __init__(self, **_kwargs):
            self.repository = MissingAssetRepository()

    monkeypatch.setattr(publication_module, "AcDocumentService", MissingAssetDocument)
    published = publish_companion(
        context,
        source=source,
        title="Illustrated",
        authors=(),
        source_language="en",
        target_language="en",
        translation_mode="skipped",
        reader_labels={},
        chapters=(
            {
                "chapter_id": chapter.chapter_id,
                "title": chapter.title,
                "block_ids": list(chapter.block_ids),
                "display_anchor_block_id": chapter.display_anchor_block_id,
                "section_block_ids": list(chapter.section_block_ids),
                "section_titles": list(chapter.section_titles),
                "section_levels": list(chapter.section_levels),
                "translation_result": None,
                "learning_units": [],
            },
        ),
        glossary=(),
        bibliography=(),
        document_cache_root=tmp_path / "paper",
    )
    ledger = published.publication.reader_profile["delivery_ledger"]
    assert ledger["delivery_grade"] == "degraded"
    assert ledger["issues"][0]["category"] == "resource_unavailable"
    resources = next(item for item in ledger["stages"] if item["stage"] == "resources")
    assert resources == {
        "stage": "resources",
        "status": "degraded",
        "expected": 3,
        "produced": 2,
        "accounted": 3,
    }
    workspace = tmp_path / "missing-resource-publication"
    publication_path = materialize_published_companion(
        ImmutableArtifactStore(
            repository.run_directory("missing-resource"),
            repository_root=repository.root,
        ),
        published,
        workspace,
    )
    rendered = render_publication_html(publication_path, workspace / "reader.html")
    assert rendered.html_path.is_file()
    final_ledger = json.loads(
        (workspace / "reader.delivery-ledger.json").read_text(encoding="utf-8")
    )
    assert final_ledger["delivery_grade"] == "degraded"
    assert next(
        item for item in final_ledger["stages"] if item["stage"] == "render"
    ) == {
        "stage": "render",
        "status": "complete",
        "expected": 1,
        "produced": 1,
        "accounted": 1,
    }


def test_glossary_fallback_summary_is_accounted_in_delivery_ledger(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    chapter = plan_source_chapters(source)[0]
    repository = RunRepository(tmp_path / "jobs")
    snapshot = repository.create(
        RunSpec("glossary-fallback", "handler", {"input": "test"})
    )
    context = RunContext(repository, snapshot, resume_input=None)
    published = publish_companion(
        context,
        source=source,
        title="Title",
        authors=(),
        source_language="en",
        target_language="en",
        translation_mode="skipped",
        reader_labels={},
        chapters=(
            {
                "chapter_id": chapter.chapter_id,
                "title": chapter.title,
                "block_ids": list(chapter.block_ids),
                "display_anchor_block_id": chapter.display_anchor_block_id,
                "section_block_ids": list(chapter.section_block_ids),
                "section_titles": list(chapter.section_titles),
                "section_levels": list(chapter.section_levels),
                "translation_result": None,
                "learning_units": [],
            },
        ),
        glossary=(
            {
                "entry_id": "term-recovered",
                "term": "Body",
                "translated_term": "Body",
                "definition": "Recovered definition.",
                "anchor_ids": [source.blocks[1].block_id],
                "citations": [],
            },
        ),
        glossary_fallback_summary={
            "schema_version": "alc.translate.glossary_fallback_summary.v1",
            "recovered_term_ids": ["term-recovered"],
            "dropped_term_ids": ["term-omitted"],
            "reason_codes": ["glossary_control_character_invalid"],
        },
        bibliography=(),
        document_cache_root=tmp_path / "paper",
    )
    ledger = published.publication.reader_profile["delivery_ledger"]
    glossary = next(item for item in ledger["stages"] if item["stage"] == "glossary")
    assert glossary == {
        "stage": "glossary",
        "status": "degraded",
        "expected": 2,
        "produced": 1,
        "accounted": 2,
    }
    assert {item["category"] for item in ledger["issues"]} == {
        "glossary_recovered",
        "glossary_omitted",
    }


def test_unanchored_glossary_entry_is_explicitly_omitted(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    chapter = plan_source_chapters(source)[0]
    repository = RunRepository(tmp_path / "jobs")
    snapshot = repository.create(
        RunSpec("unanchored-glossary", "handler", {"input": "test"})
    )
    context = RunContext(repository, snapshot, resume_input=None)
    published = publish_companion(
        context,
        source=source,
        title="Title",
        authors=(),
        source_language="en",
        target_language="en",
        translation_mode="skipped",
        reader_labels={},
        chapters=(
            {
                "chapter_id": chapter.chapter_id,
                "title": chapter.title,
                "block_ids": list(chapter.block_ids),
                "display_anchor_block_id": chapter.display_anchor_block_id,
                "section_block_ids": list(chapter.section_block_ids),
                "section_titles": list(chapter.section_titles),
                "section_levels": list(chapter.section_levels),
                "translation_result": None,
                "learning_units": [],
            },
        ),
        glossary=(
            {
                "entry_id": "term-anchored",
                "term": "Body",
                "translated_term": "Body",
                "definition": "Definition.",
                "anchor_ids": [source.blocks[1].block_id],
                "citations": [],
            },
        ),
        glossary_unanchored_ids=("term-unanchored",),
        bibliography=(),
        document_cache_root=tmp_path / "paper",
    )
    ledger = published.publication.reader_profile["delivery_ledger"]
    glossary = next(item for item in ledger["stages"] if item["stage"] == "glossary")
    assert glossary["expected"] == 2
    assert glossary["produced"] == 1
    assert any(
        item["issue_id"] == "glossary-omitted-term-unanchored"
        for item in ledger["issues"]
    )


def test_reviewed_supplement_publishes_provenance_resource_and_coverage(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    anchor = source.blocks[1]
    image_payload = b"\x89PNG\r\n\x1a\nreviewed"
    image = SourceRepository(tmp_path / "paper").store_asset_bytes(
        image_payload,
        media_type="image/png",
    )
    coverage = (
        ReviewedSourceUnit(
            "unit-1",
            "text",
            "notes.md:L1",
            "a" * 64,
            "published",
            "Adds a derivation.",
            ("entry-1",),
        ),
        ReviewedSourceUnit(
            "unit-2",
            "text",
            "notes.md:L2",
            "b" * 64,
            "excluded",
            "Restates the source.",
        ),
    )
    supplement = ReviewedCompanionSupplement(
        supplement_id="reviewed-notes",
        summary="Reviewed notes with exhaustive dispositions.",
        source_unit_count=len(coverage),
        source_inventory_digest=reviewed_source_inventory_digest(coverage),
        entries=(
            ReviewedSupplementEntry(
                entry_id="entry-1",
                anchor_block_id=anchor.block_id,
                anchor_fingerprint=reviewed_anchor_fingerprint(anchor),
                title="Reviewed note",
                markdown="Explanation.\n\n![Diagram](notes/diagram.png)",
                source_draft_ids=("draft-1",),
                source_unit_ids=("unit-1",),
            ),
        ),
        coverage=coverage,
        drafts=(
            ReviewedSourceDraft(
                "draft-1",
                "published",
                "Integrated after review.",
                ("unit-1",),
                ("entry-1",),
            ),
            ReviewedSourceDraft(
                "draft-2",
                "excluded",
                "Rejected after review.",
                ("unit-2",),
            ),
        ),
        resources=(
            ReviewedOwnedResource(
                image.artifact_digest,
                "notes/diagram.png",
                image.media_type,
                image.size,
            ),
        ),
    )
    chapter = plan_source_chapters(source)[0]
    chapters = [
        {
            "chapter_id": chapter.chapter_id,
            "title": chapter.title,
            "block_ids": list(chapter.block_ids),
            "display_anchor_block_id": chapter.display_anchor_block_id,
            "section_block_ids": list(chapter.section_block_ids),
            "section_titles": list(chapter.section_titles),
            "section_levels": list(chapter.section_levels),
            "translation_result": None,
            "learning_units": [],
        }
    ]
    repository = RunRepository(tmp_path / "jobs")
    snapshot = repository.create(
        RunSpec("supplement-run", "handler", {"input": "test"})
    )
    context = RunContext(repository, snapshot, resume_input=None)

    published = publish_companion(
        context,
        source=source,
        title="Source",
        authors=(),
        source_language="en",
        target_language="en",
        translation_mode="skipped",
        reader_labels={"source": "Source"},
        chapters=chapters,
        glossary=(),
        bibliography=(),
        reviewed_supplements=(supplement,),
        document_cache_root=tmp_path / "paper",
    )

    assert published.publication.source_document.assets == ()
    assert len(published.fragment_refs) == 1
    revision = decode_fragment_revision(
        context.artifacts.read_bytes(published.fragment_refs[0]).decode()
    )
    assert revision.provenance["supplement_id"] == "reviewed-notes"
    assert revision.provenance["entry_id"] == "entry-1"
    assert revision.provenance["source_draft_ids"] == ("draft-1",)
    assert revision.provenance["source_unit_ids"] == ("unit-1",)
    assert revision.provenance["source_basis"] == "supplement_units"
    assert len(published.resource_refs) == 4
    ledger_resource = next(
        item
        for item in published.publication.resources
        if item["logical_name"] == "alc-companion-delivery-ledger.json"
    )
    assert any(
        item.digest.value == ledger_resource["artifact_digest"]
        for item in published.resource_refs
    )
    report_ref = next(
        item
        for item in published.resource_refs
        if item.media_type == "application/json"
    )
    report = json.loads(context.artifacts.read_bytes(report_ref))
    assert report["schema_version"] == ("alc.companion.supplement_coverage.v1")
    assert report["totals"] == {
        "supplements": 1,
        "source_units": 2,
        "published_units": 1,
        "excluded_units": 1,
        "text_units": 2,
        "published_text_units": 1,
        "excluded_text_units": 1,
        "image_units": 0,
        "published_image_units": 0,
        "excluded_image_units": 0,
        "drafts": 2,
        "published_drafts": 1,
        "excluded_drafts": 1,
        "entries": 1,
        "supplement_unit_entries": 1,
        "supplement_draft_entries": 0,
        "primary_source_entries": 0,
        "resources": 1,
    }
    workspace = tmp_path / "supplement-publication"
    publication_path = materialize_published_companion(
        ImmutableArtifactStore(
            repository.run_directory("supplement-run"),
            repository_root=repository.root,
        ),
        published,
        workspace,
    )
    assert validate_publication_workspace(publication_path) == ()


def test_changed_companion_content_gets_a_distinct_fragment_identity(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)

    def publish(content: str, name: str) -> str:
        repository = RunRepository(tmp_path / f"jobs-{name}")
        snapshot = repository.create(RunSpec(f"run-{name}", "handler", {"input": name}))
        context = RunContext(repository, snapshot, resume_input=None)
        translation = _translation_result(context, source)
        chapter = {
            "chapter_id": "chapter",
            "title": "Title",
            "block_ids": [block.block_id for block in source.blocks],
            "display_anchor_block_id": source.blocks[0].block_id,
            "section_block_ids": [],
            "section_titles": [],
            "section_levels": [],
            "translation_result": translation.to_document(),
            "learning_units": [
                {
                    "unit_id": "unit",
                    "title": "说明",
                    "anchor_block_ids": [source.blocks[1].block_id],
                    "purpose": "companion",
                    "content_markdown": content,
                    "citations": [],
                }
            ],
        }
        result = publish_companion(
            context,
            source=source,
            title="Title",
            authors=(),
            source_language="en",
            target_language="zh-CN",
            translation_mode="enabled",
            reader_labels={},
            chapters=(chapter,),
            glossary=(),
            bibliography=(),
            document_cache_root=tmp_path / "paper",
        )
        revisions = [
            decode_fragment_revision(context.artifacts.read_bytes(ref).decode("utf-8"))
            for ref in result.fragment_refs
        ]
        return next(item.fragment_id for item in revisions if item.role == "companion")

    assert publish("第一版说明。", "first") != publish("第二版说明。", "second")


def test_chapter_display_anchor_skips_front_matter(tmp_path: Path) -> None:
    repository = SourceRepository(tmp_path / "paper")
    artifact = repository.store_bytes(
        b"March 2007\n\n# Fearful Symmetry\n\nBody.\n",
        source_format=SourceFormat.MARKDOWN,
        origin=SourceOrigin(SourceOriginKind.LOCAL_IMPORT, locator="source.md"),
    )
    source = RichDocumentParserService(repository).parse_source(artifact)

    chapter = plan_source_chapters(source)[0]

    assert source.blocks[0].kind.value == "paragraph"
    anchor = next(
        item
        for item in source.blocks
        if item.block_id == chapter.display_anchor_block_id
    )
    assert anchor.kind.value == "heading"
    assert anchor.payload["text"] == "Fearful Symmetry"
    guide = validate_chapter_guide(
        {
            "chapter_guide": {
                "title": "How to read",
                "content_markdown": "New context.",
            },
            "section_guides": [],
            "companions": [],
            "references": [],
        },
        chapter_id=chapter.chapter_id,
        block_ids=chapter.block_ids,
        chapter_anchor_block_id=chapter.display_anchor_block_id,
    )
    assert guide["learning_units"][0]["anchor_block_ids"] == [anchor.block_id]


def test_simple_chapter_may_publish_no_guide_units(tmp_path: Path) -> None:
    source = _source(tmp_path)
    chapter = plan_source_chapters(source)[0]

    guide = validate_chapter_guide(
        {
            "chapter_guide": None,
            "section_guides": [],
            "companions": [],
            "references": [],
        },
        chapter_id=chapter.chapter_id,
        block_ids=chapter.block_ids,
        chapter_anchor_block_id=chapter.display_anchor_block_id,
        section_block_ids=chapter.section_block_ids,
    )

    assert guide["learning_units"] == []


def test_chapter_guide_deduplicates_repeated_citation_metadata(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    chapter = plan_source_chapters(source)[0]

    guide = validate_chapter_guide(
        {
            "chapter_guide": {
                "title": "How to read",
                "content_markdown": "First [@1], second [@1], third [@1].",
            },
            "section_guides": [],
            "companions": [],
            "references": [
                {
                    "title": "Reference",
                    "source": "https://example.com/reference",
                }
            ],
        },
        chapter_id=chapter.chapter_id,
        block_ids=chapter.block_ids,
        chapter_anchor_block_id=chapter.display_anchor_block_id,
        section_block_ids=chapter.section_block_ids,
    )

    unit = guide["learning_units"][0]
    assert len(unit["citations"]) == 1
    assert unit["content_markdown"].count(f"[@{unit['citations'][0]}]") == 3


def test_publication_outline_uses_program_chapters_and_subsections(
    tmp_path: Path,
) -> None:
    paper = SourceRepository(tmp_path / "paper")
    artifact = paper.store_bytes(
        b"Front matter.\n\n# Real Chapter\n\nBody.\n\n## Real Section\n\nDetail.\n",
        source_format=SourceFormat.MARKDOWN,
        origin=SourceOrigin(SourceOriginKind.LOCAL_IMPORT, locator="source.md"),
    )
    source = RichDocumentParserService(paper).parse_source(artifact)
    chapter = plan_source_chapters(source)[0]
    repository = RunRepository(tmp_path / "jobs")
    snapshot = repository.create(RunSpec("outline-run", "handler", {"input": "test"}))
    context = RunContext(repository, snapshot, resume_input=None)

    published = publish_companion(
        context,
        source=source,
        title="Real Chapter",
        authors=(),
        source_language="en",
        target_language="en",
        translation_mode="skipped",
        reader_labels={},
        chapters=(
            {
                "chapter_id": chapter.chapter_id,
                "title": chapter.title,
                "block_ids": list(chapter.block_ids),
                "display_anchor_block_id": (chapter.display_anchor_block_id),
                "section_block_ids": list(chapter.section_block_ids),
                "section_titles": list(chapter.section_titles),
                "section_levels": list(chapter.section_levels),
                "translation_result": None,
                "learning_units": [],
            },
        ),
        glossary=(),
        bibliography=(),
        document_cache_root=tmp_path / "paper",
    )

    assert [item.title for item in published.publication.outline] == [
        "Real Chapter",
        "Real Section",
    ]
    assert published.publication.outline[0].anchor_block_id == (
        chapter.display_anchor_block_id
    )
    subsection = published.publication.outline[1]
    assert subsection.level == 2
    assert subsection.path[0] == chapter.chapter_id


def test_publication_omits_one_persisted_malformed_translation(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    chapter = plan_source_chapters(source)[0]
    repository = RunRepository(tmp_path / "jobs")
    snapshot = repository.create(
        RunSpec("malformed-translation", "handler", {"input": "test"})
    )
    context = RunContext(repository, snapshot, resume_input=None)
    malformed = source.blocks[1]
    translation = _translation_result(
        context, source, malformed_ordinal=malformed.ordinal
    )
    selection = load_translation_selection(
        context,
        translation.to_document(),
        source=source,
        block_ids=chapter.block_ids,
        target_language="zh-CN",
    )
    fallback_record = next(
        item
        for item in selection.view_records
        if item["block_id"] == malformed.block_id
    )
    assert "Body." in fallback_record["text"]
    assert "$$" not in fallback_record["text"]

    published = publish_companion(
        context,
        source=source,
        title="Title",
        authors=(),
        source_language="en",
        target_language="zh-CN",
        translation_mode="enabled",
        reader_labels={},
        chapters=(
            {
                "chapter_id": chapter.chapter_id,
                "title": chapter.title,
                "block_ids": list(chapter.block_ids),
                "display_anchor_block_id": chapter.display_anchor_block_id,
                "section_block_ids": list(chapter.section_block_ids),
                "section_titles": list(chapter.section_titles),
                "section_levels": list(chapter.section_levels),
                "translation_result": translation.to_document(),
                "learning_units": [],
            },
        ),
        glossary=(),
        bibliography=(),
        document_cache_root=tmp_path / "paper",
    )

    ledger = published.publication.reader_profile["delivery_ledger"]
    assert published.publication.reader_profile["delivery_mode"] == (
        "partial_bilingual"
    )
    translation_stage = next(
        item for item in ledger["stages"] if item["stage"] == "translation"
    )
    assert translation_stage["status"] == "degraded"
    assert translation_stage["produced"] == len(source.blocks) - 1
    issue = next(
        item for item in ledger["issues"] if item["category"] == "translation_omitted"
    )
    assert issue["scope"] == malformed.block_id
    assert issue["evidence"] == "translation_markdown_invalid"
    published_revisions = tuple(
        decode_fragment_revision(context.artifacts.read_bytes(ref).decode("utf-8"))
        for ref in published.fragment_refs
    )
    assert all(
        revision.role != "translation"
        or revision.anchor.target_id != malformed.block_id
        for revision in published_revisions
    )


def test_publication_records_sanitized_provider_failure(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    chapter = plan_source_chapters(source)[0]
    repository = RunRepository(tmp_path / "jobs")
    snapshot = repository.create(
        RunSpec("provider-diagnostic", "handler", {"input": "test"})
    )
    context = RunContext(repository, snapshot, resume_input=None)
    translation = _translation_result(context, source)
    context.events.emit(
        "translation_provider_fallback",
        {
            "provider": "codex",
            "model": "gpt-5.6-luna",
            "tier": "medium",
            "reason_code": "provider_crash_retry_exhausted",
            "failure_category": "timeout",
            "detail_code": "provider_idle_timeout",
            "stage": "translation",
            "window_ordinal": 2,
            "consecutive_window_failures": 2,
            "global_fallback_triggered": True,
            "remaining_windows_skipped": 3,
        },
    )

    published = publish_companion(
        context,
        source=source,
        title="Title",
        authors=(),
        source_language="en",
        target_language="zh-CN",
        translation_mode="enabled",
        reader_labels={},
        chapters=(
            {
                "chapter_id": chapter.chapter_id,
                "title": chapter.title,
                "block_ids": list(chapter.block_ids),
                "display_anchor_block_id": chapter.display_anchor_block_id,
                "section_block_ids": list(chapter.section_block_ids),
                "section_titles": list(chapter.section_titles),
                "section_levels": list(chapter.section_levels),
                "translation_result": translation.to_document(),
                "learning_units": [],
            },
        ),
        glossary=(),
        bibliography=(),
        document_cache_root=tmp_path / "paper",
    )

    issue = next(
        item
        for item in published.publication.reader_profile["delivery_ledger"][
            "issues"
        ]
        if item["category"] == "translation_provider_failure"
    )
    assert issue == {
        "issue_id": "translation-provider-translation-2",
        "category": "translation_provider_failure",
        "scope": "window:2",
        "fallback": "source_text_remaining_windows",
        "affected_count": 4,
        "source_preserved": True,
        "retry": "provider_crash_retry_exhausted",
        "evidence": "codex/gpt-5.6-luna:timeout/provider_idle_timeout",
    }


def _translation_result(
    context: RunContext,
    source,
    *,
    malformed_ordinal: int | None = None,
) -> TranslationResult:
    source_identity = source_identity_from_rich_document(source)
    references = []
    artifacts = []
    for block in source.blocks:
        text = (
            str(block.payload["text"])
            if block.kind.value == "code"
            else f"译文 {block.ordinal}"
        )
        revision = FragmentRevision(
            source=source_identity,
            fragment_id=f"translation-publication-{block.ordinal}",
            revision=1,
            parent_semantic_digest=None,
            anchor=FragmentAnchor(
                AnchorKind.BLOCK,
                block.block_id,
                (anchor_block_from_rich_block(block),),
            ),
            priority=10,
            role="translation",
            language="zh-CN",
            title=None,
            citation_ids=(),
            provenance={"producer": "alc-translate"},
            markdown_body=(
                "模型译文意外打开 $$ 但没有关闭。\n"
                if block.ordinal == malformed_ordinal
                else block_text_to_markdown(block, text)
            ),
        )
        relative = f"fragments/{fragment_revision_filename(revision)}"
        reference = fragment_revision_ref(relative, revision)
        payload = encode_fragment_revision(revision).encode("utf-8")
        artifact = context.artifacts.publish_bytes(
            f"translation-input/{revision.fragment_id}",
            payload,
            media_type="text/markdown",
        )
        references.append(reference)
        artifacts.append(TranslationRevisionArtifact(reference, artifact))
    return TranslationResult(
        source_language="en",
        target_language="zh-CN",
        mode="enabled",
        coverage="selection",
        layer=Layer(source_identity, "alc-translate", tuple(references)),
        revision_artifacts=tuple(artifacts),
    )
