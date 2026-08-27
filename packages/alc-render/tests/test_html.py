from __future__ import annotations

import hashlib
import json
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
    encode_fragment_revision,
    FragmentAnchor,
    FragmentRevision,
    Layer,
    Publication,
    anchor_block_from_rich_block,
    fragment_revision_filename,
    fragment_revision_ref,
    publication_edition_digest,
    read_publication_workspace_state,
    source_identity_from_rich_document,
)
from alc_render.html import (
    HTMLRenderError,
    _extract_json_script,
    _extract_reader_payload,
    _reader_icon_link,
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
    assert (
        '<h3 id="alc-editor-advanced-label" class="alc-editor-advanced-heading">'
        "Preview and more settings</h3>"
        in text
    )
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
    buildStandaloneExportHtml: buildStandaloneExportHtml,
    initialRevisions: initialRevisions,
    metadataOnly: metadataOnly,
    resolveOne: resolveOne,
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
