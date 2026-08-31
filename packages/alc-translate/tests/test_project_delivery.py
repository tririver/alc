from __future__ import annotations

import hashlib
import json

import pytest
from ac_jobs import ArtifactDigest, ArtifactRef
from ac_document import AcDocumentService, RichDocumentParserService
from ac_document import rich_document_to_document
from alc_render import (
    AnchorKind,
    FragmentAnchor,
    FragmentRevision,
    GlossaryDelivery,
    Layer,
    anchor_block_from_rich_block,
    encode_fragment_revision,
    fragment_revision_filename,
    fragment_revision_ref,
    read_fragment_revision,
    read_glossary_delivery,
    read_layer,
    read_publication,
    source_identity_from_rich_document,
)
from alc_render.cli import main as render_main
from alc_translate.delivery import (
    TranslationDeliveryError,
    publish_translation_glossary,
    publish_translation_layer,
    validate_translation_layer,
)
from alc_translate.project import TranslationProject
from alc_translate.workflow import (
    GlossaryResult,
    TranslationResult,
    TranslationRevisionArtifact,
)


def test_translation_runtime_is_hidden_and_can_share_an_alc_project(tmp_path) -> None:
    root = tmp_path / "project"
    (root / ".alc" / "companion").mkdir(parents=True)

    project = TranslationProject.open(root)

    assert project.runtime_root == root / ".alc" / "translate"
    assert project.marker == project.runtime_root / "project.json"
    assert not (root / "alc-translate-project.json").exists()
    assert not (project.runtime_root / "document-cache").exists()


def test_successful_translation_delivery_is_native_layer_and_revision(
    tmp_path,
) -> None:
    source_path = tmp_path / "paper.md"
    source_path.write_text("# Source\n\nSource paragraph.\n", encoding="utf-8")
    paper = AcDocumentService(cache_root=tmp_path / "cache")
    artifact = paper.import_source(source_path)
    document = RichDocumentParserService(paper.repository).parse_source(
        artifact
    )
    block = document.blocks[1]
    source = source_identity_from_rich_document(document)
    revision = FragmentRevision(
        source=source,
        fragment_id="translation-fixture",
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
        provenance={
            "producer": "alc-translate",
            "source_language": "en",
            "translation_mode": "enabled",
        },
        markdown_body="翻译后的段落。",
    )
    filename = fragment_revision_filename(revision)
    path = f"fragments/{filename}"
    reference = fragment_revision_ref(path, revision)
    payload = encode_fragment_revision(revision).encode("utf-8")
    artifact_ref = ArtifactRef(
        "translation/fragments/fixture/revision-000001",
        ArtifactDigest(
            "sha256",
            hashlib.sha256(payload).hexdigest(),
            len(payload),
        ),
        "text/markdown",
        "artifacts/objects/fixture",
    )
    result = TranslationResult(
        source_language="en",
        target_language="zh-CN",
        mode="enabled",
        coverage="document",
        layer=Layer(source, "alc-translate", (reference,)),
        revision_artifacts=(
            TranslationRevisionArtifact(reference, artifact_ref),
        ),
    )
    project = TranslationProject.open(tmp_path / "project")

    delivery = publish_translation_layer(
        project, result=result, revision_payloads=(payload,)
    )

    assert delivery == project.root / "translation.layer.json"
    assert read_layer(delivery) == result.layer
    published = read_fragment_revision(project.root / path)
    assert published.markdown_body == "翻译后的段落。"
    assert published.priority == 10
    validate_translation_layer(project, result=result)


def test_successful_glossary_delivery_is_source_bound_and_render_native(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "paper.md"
    source_path.write_text(
        "# Source\n\nA quantum field appears here.\n", encoding="utf-8"
    )
    paper = AcDocumentService(cache_root=tmp_path / "cache")
    artifact = paper.import_source(source_path)
    document = RichDocumentParserService(paper.repository).parse_source(
        artifact
    )
    result = GlossaryResult(
        document_digest=document.document_digest,
        source_digest=document.source.artifact_digest,
        target_language="zh-CN",
        approx_count=1,
        inventory_digest="a" * 64,
        entries=({
            "term_id": "term-quantum-field",
            "term": "quantum field",
            "aliases": [],
            "occurrence_count": 1,
            "source_refs": [],
            "matched_sentences": [],
            "preferred_translation": "量子场",
            "target_definition": "量子理论中的场。",
        },),
    )
    project = TranslationProject.open(tmp_path / "project")

    path = publish_translation_glossary(
        project, document=document, result=result
    )
    delivery = read_glossary_delivery(path)
    assert isinstance(delivery, GlossaryDelivery)
    assert delivery.source == source_identity_from_rich_document(document)
    assert delivery.entries[0]["term"] == "quantum field"
    assert delivery.entries[0]["translated_term"] == "量子场"
    assert delivery.entries[0]["anchor_ids"] == (
        document.blocks[1].block_id,
    )

    mismatched = GlossaryResult(
        **{**result.__dict__, "source_digest": "b" * 64}
    )
    with pytest.raises(TranslationDeliveryError, match="another rich source"):
        publish_translation_glossary(
            project, document=document, result=mismatched
        )


def test_standalone_glossary_delivery_composes_into_publication(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "paper.md"
    source_path.write_text(
        "# Source\n\nA quantum field appears here.\n", encoding="utf-8"
    )
    paper = AcDocumentService(cache_root=tmp_path / "cache")
    document = RichDocumentParserService(paper.repository).parse_source(
        paper.import_source(source_path)
    )
    glossary = GlossaryResult(
        document_digest=document.document_digest,
        source_digest=document.source.artifact_digest,
        target_language="zh-CN",
        approx_count=1,
        inventory_digest="c" * 64,
        entries=({
            "term_id": "term-quantum-field",
            "term": "quantum field",
            "aliases": [],
            "occurrence_count": 1,
            "source_refs": [],
            "matched_sentences": [],
            "preferred_translation": "量子场",
            "target_definition": "量子理论中的场。",
        },),
    )
    project = TranslationProject.open(tmp_path / "project")
    glossary_path = publish_translation_glossary(
        project, document=document, result=glossary
    )
    source_json = tmp_path / "rich-source.json"
    source_json.write_text(
        json.dumps(rich_document_to_document(document)), encoding="utf-8"
    )
    publication_path = tmp_path / "publication.json"

    assert render_main([
        "compose",
        "--source", str(source_json),
        "--glossary", str(glossary_path),
        "--output", str(publication_path),
    ]) == 0
    publication = read_publication(publication_path)
    assert publication.glossary[0]["term"] == "quantum field"
    assert publication.glossary[0]["anchor_ids"] == (
        document.blocks[1].block_id,
    )


def test_selected_translation_cannot_replace_document_layer(tmp_path) -> None:
    project, result, payload = _delivery_fixture(tmp_path)
    publish_translation_layer(
        project, result=result, revision_payloads=(payload,)
    )
    before = project.translation_layer.read_bytes()
    selected = TranslationResult(
        source_language=result.source_language,
        target_language=result.target_language,
        mode=result.mode,
        coverage="selection",
        layer=result.layer,
        revision_artifacts=result.revision_artifacts,
    )

    with pytest.raises(TranslationDeliveryError, match="selected-block"):
        publish_translation_layer(
            project, result=selected, revision_payloads=(payload,)
        )

    assert project.translation_layer.read_bytes() == before


def test_invalid_revision_is_rejected_before_layer_replacement(tmp_path) -> None:
    project, result, payload = _delivery_fixture(tmp_path)
    publish_translation_layer(
        project, result=result, revision_payloads=(payload,)
    )
    before = project.translation_layer.read_bytes()
    original = read_fragment_revision(
        project.root / result.revision_artifacts[0].revision.path
    )
    invalid = FragmentRevision(
        source=original.source,
        fragment_id="invalid-translation-fixture",
        revision=1,
        parent_semantic_digest=None,
        anchor=original.anchor,
        priority=10,
        role="companion",
        language=original.language,
        title=None,
        citation_ids=(),
        provenance=original.provenance,
        markdown_body=original.markdown_body,
    )
    invalid_path = (
        f"fragments/{fragment_revision_filename(invalid)}"
    )
    invalid_ref = fragment_revision_ref(invalid_path, invalid)
    invalid_payload = encode_fragment_revision(invalid).encode("utf-8")
    invalid_artifact = ArtifactRef(
        "translation/fragments/invalid/revision-000001",
        ArtifactDigest(
            "sha256",
            hashlib.sha256(invalid_payload).hexdigest(),
            len(invalid_payload),
        ),
        "text/markdown",
        "artifacts/objects/invalid",
    )
    invalid_result = TranslationResult(
        source_language="en",
        target_language="zh-CN",
        mode="enabled",
        coverage="document",
        layer=Layer(original.source, "alc-translate", (invalid_ref,)),
        revision_artifacts=(
            TranslationRevisionArtifact(invalid_ref, invalid_artifact),
        ),
    )

    with pytest.raises(TranslationDeliveryError, match="payload is invalid"):
        publish_translation_layer(
            project,
            result=invalid_result,
            revision_payloads=(invalid_payload,),
        )

    assert project.translation_layer.read_bytes() == before


def _delivery_fixture(
    tmp_path,
) -> tuple[TranslationProject, TranslationResult, bytes]:
    source_path = tmp_path / "fixture-source.md"
    source_path.write_text("# Source\n\nSource paragraph.\n", encoding="utf-8")
    paper = AcDocumentService(cache_root=tmp_path / "fixture-cache")
    artifact = paper.import_source(source_path)
    document = RichDocumentParserService(paper.repository).parse_source(
        artifact
    )
    block = document.blocks[1]
    source = source_identity_from_rich_document(document)
    revision = FragmentRevision(
        source=source,
        fragment_id="translation-delivery-fixture",
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
        provenance={
            "producer": "alc-translate",
            "source_language": "en",
            "translation_mode": "enabled",
        },
        markdown_body="翻译后的段落。",
    )
    path = (
        f"fragments/{fragment_revision_filename(revision)}"
    )
    reference = fragment_revision_ref(path, revision)
    payload = encode_fragment_revision(revision).encode("utf-8")
    artifact_ref = ArtifactRef(
        "translation/fragments/delivery/revision-000001",
        ArtifactDigest(
            "sha256",
            hashlib.sha256(payload).hexdigest(),
            len(payload),
        ),
        "text/markdown",
        "artifacts/objects/delivery",
    )
    result = TranslationResult(
        source_language="en",
        target_language="zh-CN",
        mode="enabled",
        coverage="document",
        layer=Layer(source, "alc-translate", (reference,)),
        revision_artifacts=(
            TranslationRevisionArtifact(reference, artifact_ref),
        ),
    )
    return TranslationProject.open(tmp_path / "delivery-project"), result, payload
