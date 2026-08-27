"""Standalone HTML publication rendering for rich sources and atomic overlays."""

from __future__ import annotations

import base64
import binascii
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
from html import escape
from html.parser import HTMLParser
from importlib.resources import files
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Any

from ac_document import RichDocument

from .contracts import (
    FragmentRevision,
    Layer,
    Publication,
    anchor_block_from_rich_block,
    fragment_revision_from_document,
    fragment_revision_to_document,
    publication_from_document,
    publication_to_document,
    source_identity_to_document,
)
from .markdown import extract_markdown_citation_ids, read_fragment_revision
from .resolver import (
    RevisionDiagnostic,
    resolve_fragment_revision_files,
    resolve_fragment_revisions,
)
from .standalone_html import (
    StandaloneHtmlError,
    _selected_fragment_boot_metadata,
    _srcset_candidates,
    write_standalone_html,
)
from .workspace import RenderWorkspaceError, read_layer, read_publication


HTML_RENDER_RECIPE = "alc.render.standalone_html.v1"
READER_PAYLOAD_SCHEMA = "alc.render.reader_payload.v1"
READER_PAYLOAD_V2_SCHEMA = "alc.render.reader_payload.v2"
READER_CHUNK_SCHEMA = "alc.render.reader_chunk.v1"
READER_RESOURCE_SCHEMA = "alc.render.reader_resource.v1"
AssetLoader = Callable[[str], bytes | None]
_CSS_URL_PATTERN = re.compile(
    r"url\(\s*(?:'(?P<single>[^']*)'|\"(?P<double>[^\"]*)\"|"
    r"(?P<plain>[^)]*))\s*\)",
    re.IGNORECASE,
)


class HTMLRenderError(RuntimeError):
    """A publication cannot be rendered as a verified standalone HTML file."""


@dataclass(frozen=True)
class RenderedHTML:
    publication_digest: str
    html_path: Path
    selected_revision_digests: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    renderer_recipe: str = HTML_RENDER_RECIPE


EDITION_DIGEST_SCHEMA = "alc.render.edition.v1"


@dataclass(frozen=True)
class PublicationWorkspaceState:
    """Resolved current state of one publication workspace.

    The publication digest identifies immutable publication metadata, while
    the edition digest also binds the ordered current fragment revision heads.
    """

    publication: Publication
    revisions: tuple[FragmentRevision, ...]
    selected_revisions: tuple[FragmentRevision, ...]
    selected_revision_digests: tuple[str, ...]
    diagnostics: tuple[RevisionDiagnostic, ...]
    publication_digest: str
    edition_digest: str


def publication_edition_digest(
    publication_digest: str,
    selected_revision_digests: Sequence[str],
) -> str:
    """Return the identity of a publication plus ordered selected revisions."""

    if (
        not isinstance(publication_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", publication_digest) is None
    ):
        raise ValueError("publication_digest must be a SHA-256 digest")
    if isinstance(selected_revision_digests, (str, bytes, bytearray)):
        raise TypeError("selected revision digests must be a sequence")
    digests = tuple(selected_revision_digests)
    if any(
        not isinstance(item, str)
        or re.fullmatch(r"[0-9a-f]{64}", item) is None
        for item in digests
    ):
        raise ValueError("selected revision digests must be SHA-256 digests")
    material = {
        "schema_version": EDITION_DIGEST_SCHEMA,
        "publication_digest": publication_digest,
        "selected_revision_digests": digests,
    }
    return hashlib.sha256(
        json.dumps(
            material,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def render_publication_html(
    publication_path: str | Path,
    output_path: str | Path,
    *,
    asset_loader: AssetLoader | None = None,
) -> RenderedHTML:
    """Load a publication workspace and write one portable HTML reader."""

    source_path = Path(publication_path).resolve()
    try:
        publication = read_publication(source_path)
    except RenderWorkspaceError as exc:
        raise HTMLRenderError(str(exc)) from exc
    return render_html(
        publication,
        output_path,
        project_root=source_path.parent,
        asset_loader=asset_loader,
    )


def read_publication_workspace_state(
    publication_path: str | Path,
) -> PublicationWorkspaceState:
    """Resolve current revision heads and diagnostics for one workspace."""

    source_path = Path(publication_path).resolve()
    try:
        publication = read_publication(source_path)
    except RenderWorkspaceError as exc:
        raise HTMLRenderError(str(exc)) from exc
    revisions, selected, diagnostics = _load_revisions(
        publication, source_path.parent
    )
    _validate_selected(publication, selected)
    selected_digests = tuple(item.semantic_digest for item in selected)
    return PublicationWorkspaceState(
        publication=publication,
        revisions=revisions,
        selected_revisions=selected,
        selected_revision_digests=selected_digests,
        diagnostics=diagnostics,
        publication_digest=publication.publication_digest,
        edition_digest=publication_edition_digest(
            publication.publication_digest, selected_digests
        ),
    )


def render_html(
    publication: Publication,
    output_path: str | Path,
    *,
    project_root: str | Path,
    asset_loader: AssetLoader | None = None,
) -> RenderedHTML:
    """Render ``publication`` and discovered project revisions to one HTML."""

    if not isinstance(publication, Publication):
        raise TypeError("publication must be a Publication")
    root = Path(project_root).resolve()
    if not root.is_dir():
        raise HTMLRenderError(f"publication project root is missing: {root}")
    output = Path(output_path).resolve()
    revisions, selected, diagnostics = _load_revisions(publication, root)
    _validate_selected(publication, selected)
    resources = _embedded_resources(
        publication,
        root=root,
        asset_loader=asset_loader,
    )
    payload = _reader_payload(
        publication,
        revisions=revisions,
        selected=selected,
        resources=resources,
        diagnostics=diagnostics,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".alc-render-html-", dir=output.parent
    ) as raw:
        bundle = Path(raw)
        assets = bundle / "assets"
        _copy_web_assets(assets)
        index = bundle / "index.html"
        index.write_text(_html_shell(publication, payload), encoding="utf-8")
        try:
            write_standalone_html(index, output)
        except StandaloneHtmlError as exc:
            raise HTMLRenderError(str(exc)) from exc
    validate_standalone_html(publication, output)
    warnings = tuple(
        _diagnostic_text(item)
        for item in diagnostics
    )
    return RenderedHTML(
        publication_digest=publication.publication_digest,
        html_path=output,
        selected_revision_digests=tuple(
            item.semantic_digest for item in selected
        ),
        warnings=warnings,
    )


def validate_publication_workspace(
    publication_path: str | Path,
    *,
    asset_loader: AssetLoader | None = None,
) -> tuple[str, ...]:
    """Validate one publication, its layers, revisions, and declared assets."""

    state = read_publication_workspace_state(publication_path)
    _embedded_resources(
        state.publication,
        root=Path(publication_path).resolve().parent,
        asset_loader=asset_loader,
    )
    return tuple(_diagnostic_text(item) for item in state.diagnostics)


def validate_standalone_html(
    publication: Publication,
    html_path: str | Path,
    *,
    expected_selected_revision_digests: Sequence[str] | None = None,
) -> None:
    """Validate identity, source coverage, and automatic-resource portability.

    ``expected_selected_revision_digests`` binds the delivered reader to a
    caller-resolved current workspace head, detecting a stale HTML delivery
    without changing the immutable publication identity.
    """

    expected_selected = _expected_selected_revision_digests(
        expected_selected_revision_digests
    )

    path = Path(html_path).resolve()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise HTMLRenderError("standalone HTML is unreadable") from exc
    if (
        f'data-publication-digest="{publication.publication_digest}"'
        not in text
    ):
        raise HTMLRenderError("standalone HTML is not bound to its publication")
    payload = _extract_reader_payload(text)
    if payload.get("schema_version") != READER_PAYLOAD_SCHEMA:
        raise HTMLRenderError("standalone HTML contains an invalid reader payload")
    encoded_publication = payload.get("publication")
    if not isinstance(encoded_publication, Mapping):
        raise HTMLRenderError("standalone HTML has no encoded publication")
    try:
        embedded_publication = publication_from_document(encoded_publication)
    except ValueError as exc:
        raise HTMLRenderError(
            "standalone HTML contains an invalid publication"
        ) from exc
    if embedded_publication != publication:
        raise HTMLRenderError(
            "standalone HTML publication digest is inconsistent"
        )
    source = encoded_publication.get("source_document")
    if not isinstance(source, Mapping):
        raise HTMLRenderError("standalone HTML has no rich source")
    blocks = source.get("blocks")
    if not isinstance(blocks, list):
        raise HTMLRenderError("standalone HTML source blocks are invalid")
    expected = [item.block_id for item in publication.source_document.blocks]
    actual = [
        item.get("block_id")
        for item in blocks
        if isinstance(item, Mapping)
    ]
    if actual != expected:
        raise HTMLRenderError("standalone HTML source block order is invalid")
    _validate_reader_resources(publication, payload)
    selected = _validate_reader_revisions(publication, payload)
    actual_selected = tuple(item.semantic_digest for item in selected)
    if expected_selected is not None and actual_selected != expected_selected:
        raise HTMLRenderError(
            "standalone HTML selected revisions differ from expected workspace"
        )
    portability = _PortabilityValidator()
    portability.feed(text)
    portability.close()
    if portability.errors:
        raise HTMLRenderError(
            "standalone HTML contains an external automatic resource: "
            + portability.errors[0]
        )
    if "window.markdownit" not in text or "window.katex" not in text:
        raise HTMLRenderError("standalone HTML is missing embedded reader libraries")
    if "@media print" not in text:
        raise HTMLRenderError("standalone HTML is missing its print stylesheet")


def _load_revisions(
    publication: Publication,
    root: Path,
) -> tuple[
    tuple[FragmentRevision, ...],
    tuple[FragmentRevision, ...],
    tuple[RevisionDiagnostic, ...],
]:
    source = publication.source
    paths_by_fragment: dict[str, list[Path]] = defaultdict(list)
    fragment_order: list[str] = []
    claimed_paths: dict[Path, str] = {}
    seen_layer_producers: set[str] = set()

    for layer_reference in publication.layers:
        layer_path = _project_path(root, layer_reference.path, "layer")
        try:
            layer = read_layer(layer_path)
        except RenderWorkspaceError as exc:
            raise HTMLRenderError(str(exc)) from exc
        _validate_layer_reference(layer, layer_reference)
        if layer.producer in seen_layer_producers:
            raise HTMLRenderError(
                f"publication contains duplicate producer layer: {layer.producer}"
            )
        seen_layer_producers.add(layer.producer)
        for revision_reference in layer.initial_revisions:
            revision_path = _project_path(
                root, revision_reference.path, "fragment revision"
            )
            try:
                initial = read_fragment_revision(revision_path)
            except ValueError as exc:
                raise HTMLRenderError(
                    f"initial fragment revision is invalid: {revision_reference.path}"
                ) from exc
            if (
                initial.fragment_id != revision_reference.fragment_id
                or initial.revision != revision_reference.revision
                or initial.semantic_digest != revision_reference.semantic_digest
                or initial.source != source
            ):
                raise HTMLRenderError(
                    "initial fragment revision does not match its layer reference: "
                    f"{revision_reference.path}"
                )
            claimed_producer = initial.provenance.get("producer")
            if (
                claimed_producer is not None
                and claimed_producer != layer.producer
            ):
                raise HTMLRenderError(
                    "initial fragment provenance contradicts its layer producer: "
                    f"{revision_reference.path}"
                )
            existing = claimed_paths.get(revision_path)
            if existing is not None and existing != revision_reference.fragment_id:
                raise HTMLRenderError(
                    "two fragment identities claim the same revision path"
                )
            claimed_paths[revision_path] = revision_reference.fragment_id
            paths_by_fragment[revision_reference.fragment_id].append(revision_path)
            if revision_reference.fragment_id not in fragment_order:
                fragment_order.append(revision_reference.fragment_id)

    fragments_root = root / "fragments"
    declared_fragment_ids = set(paths_by_fragment)
    if fragments_root.exists():
        if not fragments_root.is_dir():
            raise HTMLRenderError("project fragments path is not a directory")
        for candidate in sorted(fragments_root.rglob("*.md")):
            resolved = candidate.resolve()
            try:
                resolved.relative_to(fragments_root.resolve())
            except ValueError as exc:
                raise HTMLRenderError("fragment path escapes the project") from exc
            fragment_id = claimed_paths.get(resolved)
            if fragment_id is None:
                try:
                    fragment_id = read_fragment_revision(resolved).fragment_id
                except ValueError:
                    # Keep malformed files grouped only long enough for the
                    # resolver to diagnose them. Directory names are storage
                    # organization and never define a valid fragment identity.
                    fragment_id = candidate.parent.name
            if resolved not in paths_by_fragment[fragment_id]:
                paths_by_fragment[fragment_id].append(resolved)
            if fragment_id not in fragment_order:
                fragment_order.append(fragment_id)

    revisions: list[FragmentRevision] = []
    selected: list[FragmentRevision] = []
    diagnostics: list[RevisionDiagnostic] = []
    selected_ids: set[str] = set()
    for fragment_id in fragment_order:
        resolution = resolve_fragment_revision_files(
            paths_by_fragment[fragment_id],
            fragment_id=fragment_id,
        )
        if (
            fragment_id not in declared_fragment_ids
            and not _browser_created_history(resolution.revisions)
        ):
            continue
        diagnostics.extend(resolution.diagnostics)
        revisions.extend(resolution.revisions)
        if resolution.selected is None:
            continue
        if resolution.selected.source != source:
            raise HTMLRenderError(
                f"fragment binds another rich source: {fragment_id}"
            )
        if fragment_id in selected_ids:
            raise HTMLRenderError(f"duplicate selected fragment: {fragment_id}")
        selected_ids.add(fragment_id)
        selected.append(resolution.selected)

    order_index = {
        fragment_id: index for index, fragment_id in enumerate(fragment_order)
    }
    selected.sort(
        key=lambda item: (item.priority, order_index[item.fragment_id])
    )
    return tuple(revisions), tuple(selected), tuple(diagnostics)


def _browser_created_history(
    revisions: Sequence[FragmentRevision],
) -> bool:
    roots = tuple(
        item
        for item in revisions
        if item.revision == 1 and item.parent_semantic_digest is None
    )
    return (
        len(roots) == 1
        and roots[0].provenance.get("producer") == "alc-render-browser"
    )


def _validate_layer_reference(layer: Layer, reference: Any) -> None:
    if (
        layer.source != reference.source
        or layer.producer != reference.producer
        or layer.layer_digest != reference.layer_digest
    ):
        raise HTMLRenderError(
            f"layer does not match its publication reference: {reference.path}"
        )


def _validate_selected(
    publication: Publication,
    selected: Sequence[FragmentRevision],
) -> None:
    document = publication.source_document
    blocks = {item.block_id: item for item in document.blocks}
    sections = {item.section_id for item in publication.outline or ()}
    bibliography_ids = {
        str(
            item.get("evidence_id")
            or item.get("citation_id")
            or item.get("id")
            or ""
        )
        for item in publication.bibliography
    }
    bibliography_ids.discard("")
    for revision in selected:
        anchor = revision.anchor
        if anchor.kind.value == "block" and anchor.target_id not in blocks:
            raise HTMLRenderError(
                f"fragment anchor block is absent from the source: {revision.fragment_id}"
            )
        if anchor.kind.value == "section" and anchor.target_id not in sections:
            raise HTMLRenderError(
                f"fragment anchor section is absent from the source: {revision.fragment_id}"
            )
        for frozen in anchor.related_blocks:
            current = blocks.get(frozen.block_id)
            if current is None:
                raise HTMLRenderError(
                    f"fragment provenance block is absent: {revision.fragment_id}"
                )
            if anchor_block_from_rich_block(current) != frozen:
                raise HTMLRenderError(
                    f"fragment provenance differs from the rich source: {revision.fragment_id}"
                )
        unknown = next(
            (item for item in revision.citation_ids if item not in bibliography_ids),
            None,
        )
        if unknown is not None:
            raise HTMLRenderError(
                f"fragment citation is absent from the bibliography: {unknown}"
            )
        visible_citations = extract_markdown_citation_ids(revision.markdown_body)
        if visible_citations != revision.citation_ids:
            raise HTMLRenderError(
                "fragment Markdown citations do not match citation_ids: "
                f"{revision.fragment_id}"
            )


def _embedded_resources(
    publication: Publication,
    *,
    root: Path,
    asset_loader: AssetLoader | None,
) -> tuple[dict[str, Any], ...]:
    values: list[dict[str, Any]] = []
    for declaration in _resource_declarations(publication):
        digest = str(declaration["artifact_digest"])
        media_type = str(declaration["media_type"])
        logical_name = str(declaration["logical_name"])
        size = int(declaration["size"])
        payload: bytes | None = None
        if asset_loader is not None:
            payload = asset_loader(digest)
        if payload is None:
            relative = declaration.get("path")
            if not isinstance(relative, str):
                raise HTMLRenderError(f"resource path is missing: {digest}")
            path = _project_path(root, relative, "resource")
            try:
                payload = path.read_bytes()
            except OSError as exc:
                raise HTMLRenderError(
                    f"resource is unreadable: {relative}"
                ) from exc
        if payload is None:
            raise HTMLRenderError(f"resource is unavailable: {digest}")
        actual = hashlib.sha256(payload).hexdigest()
        if actual != digest or len(payload) != size:
            raise HTMLRenderError(
                f"resource bytes do not match metadata: {digest}"
            )
        values.append(
            {
                "artifact_digest": digest,
                "media_type": media_type,
                "logical_name": logical_name,
                "size": size,
                "data_uri": (
                    f"data:{media_type};base64,"
                    f"{base64.b64encode(payload).decode('ascii')}"
                ),
            }
        )
    return tuple(values)


def _resource_declarations(
    publication: Publication,
) -> tuple[dict[str, Any], ...]:
    """Return validated source and publication-owned resource metadata."""

    declared: dict[str, Mapping[str, Any]] = {}
    for item in publication.resources:
        digest = item.get("artifact_digest") or item.get("digest")
        if (
            not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or digest in declared
        ):
            raise HTMLRenderError("publication resource identity is invalid")
        declared[digest] = item

    values: list[dict[str, Any]] = []
    source_digests: set[str] = set()
    for asset in publication.source_document.assets:
        source_digests.add(asset.artifact_digest)
        raw = declared.get(asset.artifact_digest, {})
        for field, expected in (
            ("media_type", asset.media_type),
            ("logical_name", asset.logical_name),
            ("size", asset.size),
        ):
            if field in raw and raw[field] != expected:
                raise HTMLRenderError(
                    "publication source resource metadata differs from the source"
                )
        values.append(
            {
                "artifact_digest": asset.artifact_digest,
                "media_type": asset.media_type,
                "logical_name": asset.logical_name,
                "size": asset.size,
                **({"path": raw["path"]} if "path" in raw else {}),
            }
        )

    for digest, raw in declared.items():
        if digest in source_digests:
            continue
        media_type = raw.get("media_type")
        logical_name = raw.get("logical_name")
        size = raw.get("size")
        if (
            not isinstance(media_type, str)
            or not media_type
            or not isinstance(logical_name, str)
            or not logical_name
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
        ):
            raise HTMLRenderError(
                "publication-owned resource metadata is invalid"
            )
        values.append(
            {
                "artifact_digest": digest,
                "media_type": media_type,
                "logical_name": logical_name,
                "size": size,
                **({"path": raw["path"]} if "path" in raw else {}),
            }
        )

    logical_names = [str(item["logical_name"]) for item in values]
    if len(logical_names) != len(set(logical_names)):
        raise HTMLRenderError("publication resource logical names must be unique")
    return tuple(values)


def _reader_payload(
    publication: Publication,
    *,
    revisions: Sequence[FragmentRevision],
    selected: Sequence[FragmentRevision],
    resources: Sequence[Mapping[str, Any]],
    diagnostics: Sequence[RevisionDiagnostic],
) -> dict[str, Any]:
    return {
        "schema_version": READER_PAYLOAD_SCHEMA,
        "renderer_recipe": HTML_RENDER_RECIPE,
        "publication": publication_to_document(publication),
        "source_identity": source_identity_to_document(publication.source),
        "block_fingerprints": {
            item.block_id: anchor_block_from_rich_block(item).content_fingerprint
            for item in publication.source_document.blocks
        },
        "revisions": [
            {
                "metadata": fragment_revision_to_document(item),
                "markdown_body": item.markdown_body,
                "semantic_digest": item.semantic_digest,
            }
            for item in revisions
        ],
        "selected_revision_digests": [
            item.semantic_digest for item in selected
        ],
        "resources": list(resources),
        "diagnostics": [_diagnostic_text(item) for item in diagnostics],
    }


def _html_shell(publication: Publication, payload: Mapping[str, Any]) -> str:
    profile = publication.reader_profile
    title = str(
        profile.get("title")
        or publication.labels.get("document_title")
        or _source_title(publication.source_document)
        or publication.labels.get("untitled_document")
        or "Untitled document"
    )
    language = str(
        profile.get("target_language")
        or profile.get("source_language")
        or "und"
    )
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).replace("</script", r"<\/script")
    digest = publication.publication_digest
    icon_link = _reader_icon_link(profile, payload)
    return f"""<!doctype html>
<html lang="{escape(language)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>{escape(title)}</title>
  {icon_link}
  <link rel="stylesheet" href="assets/katex/katex.min.css">
  <link rel="stylesheet" href="assets/reader.css">
  <script defer src="assets/markdown-it/markdown-it.min.js"></script>
  <script defer src="assets/katex/katex.min.js"></script>
  <script defer src="assets/reader.js"></script>
</head>
<body data-publication-digest="{digest}">
  <div class="alc-fixed-tools">
    <button id="alc-contents-toggle" class="alc-tool-button alc-tool-icon-button"
      type="button" aria-label="Contents" title="Contents"
      aria-controls="alc-contents" aria-expanded="true">
      <svg class="alc-tool-icon" viewBox="0 0 24 24" aria-hidden="true"
        focusable="false">
        <path d="M4 6h16M4 12h16M4 18h16"></path>
      </svg>
    </button>
    <div class="alc-view-control">
      <button id="alc-view" class="alc-tool-button alc-tool-icon-button"
        type="button" aria-label="View" title="View"
        aria-controls="alc-view-panel" aria-expanded="false">
        <svg class="alc-tool-icon" viewBox="0 0 24 24" aria-hidden="true"
          focusable="false">
          <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path>
          <circle cx="12" cy="12" r="2.75"></circle>
        </svg>
      </button>
      <div id="alc-view-panel" class="alc-view-panel" hidden
        role="dialog" aria-modal="false" aria-labelledby="alc-view-heading">
        <header class="alc-tool-panel-header">
          <h2 id="alc-view-heading">Show content</h2>
        </header>
        <div class="alc-tool-panel-body alc-view-body">
          <fieldset aria-labelledby="alc-view-heading">
            <div id="alc-view-options" class="alc-view-options"></div>
          </fieldset>
        </div>
      </div>
    </div>
    <div class="alc-speech-control">
      <button id="alc-speech" class="alc-tool-button alc-tool-icon-button"
        type="button" aria-label="Listen" title="Listen"
        aria-controls="alc-speech-panel" aria-expanded="false">
        <svg class="alc-tool-icon" viewBox="0 0 24 24" aria-hidden="true"
          focusable="false">
          <path d="M11 5 6 9H2v6h4l5 4V5Z"></path>
          <path d="M15.54 8.46a5 5 0 0 1 0 7.07M19.07 4.93a10 10 0 0 1 0 14.14"></path>
        </svg>
      </button>
      <div id="alc-speech-panel" class="alc-speech-panel" hidden
        role="dialog" aria-modal="false" aria-labelledby="alc-speech-heading">
        <header class="alc-tool-panel-header">
          <h2 id="alc-speech-heading">Read content</h2>
        </header>
        <div class="alc-tool-panel-body alc-speech-body">
          <fieldset>
            <legend id="alc-speech-content-label">Include</legend>
            <div id="alc-speech-role-options"
              class="alc-speech-role-options"></div>
          </fieldset>
          <div class="alc-speech-voice-grid">
            <label class="alc-speech-field">
              <span id="alc-speech-source-voice-label">English voice</span>
              <select id="alc-speech-source-voice"></select>
            </label>
            <label class="alc-speech-field">
              <span id="alc-speech-target-voice-label">Chinese voice</span>
              <select id="alc-speech-target-voice"></select>
            </label>
          </div>
          <p id="alc-speech-status" class="alc-speech-status"
            aria-live="polite"></p>
          <div id="alc-speech-panel-player" class="alc-speech-player"
            data-player-kind="panel"></div>
        </div>
      </div>
    </div>
    <div class="alc-export-control">
      <button id="alc-export" class="alc-tool-button alc-tool-icon-button"
        type="button" aria-label="Export" title="Export"
        aria-controls="alc-export-panel" aria-expanded="false">
        <svg class="alc-tool-icon" viewBox="0 0 24 24" aria-hidden="true"
          focusable="false">
          <path d="M12 3v11M8 10l4 4 4-4M4 18v2h16v-2"></path>
        </svg>
      </button>
      <div id="alc-export-panel" class="alc-export-panel" hidden
        role="dialog" aria-modal="false" aria-labelledby="alc-export-heading">
        <header class="alc-tool-panel-header alc-export-header">
          <h2 id="alc-export-heading">Export content</h2>
        </header>
        <div class="alc-tool-panel-body alc-export-body">
          <section id="alc-export-markdown-section" class="alc-export-section"
            aria-labelledby="alc-export-markdown-heading">
            <h3 id="alc-export-markdown-heading">Markdown</h3>
          <fieldset id="alc-export-scope">
            <legend id="alc-export-scope-label">Export range</legend>
            <label>
              <input type="radio" name="alc-export-scope" value="all" checked>
              <span id="alc-export-all-label">All latest</span>
            </label>
            <label>
              <input type="radio" name="alc-export-scope" value="changed">
              <span id="alc-export-changed-label">Latest changes only</span>
            </label>
          </fieldset>
          <fieldset id="alc-export-content">
            <legend id="alc-export-content-label">Include</legend>
            <div id="alc-export-role-options"
              class="alc-export-content-options"></div>
          </fieldset>
          <fieldset id="alc-export-markdown-mode">
            <legend id="alc-export-markdown-mode-label">Output</legend>
            <label>
              <input type="radio" name="alc-export-markdown-mode" value="file">
              <span id="alc-export-markdown-file-label">Single Markdown</span>
            </label>
            <label>
              <input type="radio" name="alc-export-markdown-mode"
                value="package" checked>
              <span id="alc-export-markdown-package-label">Markdown package</span>
            </label>
          </fieldset>
          <div class="alc-export-actions">
            <button id="alc-export-markdown-package"
              class="alc-export-action" type="button">
              <svg class="alc-export-action-icon" viewBox="0 0 24 24"
                aria-hidden="true" focusable="false">
                <path d="M12 3v12M8 11l4 4 4-4M4 20h16"></path>
              </svg>
              <span id="alc-export-markdown-label">Export Markdown</span>
            </button>
          </div>
          </section>
          <section id="alc-export-html-section"
            class="alc-export-section alc-export-format-section"
            aria-labelledby="alc-export-html-heading">
            <div class="alc-export-section-copy">
              <h3 id="alc-export-html-heading">HTML</h3>
              <p id="alc-export-html-description"
                class="alc-export-description"></p>
            </div>
            <button id="alc-export-html" class="alc-export-action" type="button">
              <svg class="alc-export-action-icon" viewBox="0 0 24 24"
                aria-hidden="true" focusable="false">
                <path d="M6 2h8l4 4v16H6Z M14 2v5h5"></path>
                <path d="M10 11l-2 2 2 2M14 11l2 2-2 2"></path>
              </svg>
              <span id="alc-export-html-label">Export HTML</span>
            </button>
          </section>
          <section id="alc-export-pdf-section"
            class="alc-export-section alc-export-format-section"
            aria-labelledby="alc-export-pdf-heading">
            <div class="alc-export-section-copy">
              <h3 id="alc-export-pdf-heading">PDF</h3>
              <p id="alc-export-pdf-description"
                class="alc-export-description"></p>
            </div>
            <button id="alc-export-pdf" class="alc-export-action" type="button">
              <svg class="alc-export-action-icon" viewBox="0 0 24 24"
                aria-hidden="true" focusable="false">
                <path d="M7 8V3h10v5M6 17H4v-6h16v6h-2M7 14h10v7H7Z"></path>
              </svg>
              <span id="alc-export-pdf-label">Export PDF</span>
            </button>
          </section>
        </div>
      </div>
    </div>
    <button id="alc-connect" class="alc-tool-button alc-tool-icon-button"
      type="button" aria-label="New save location" title="New save location">
      <svg class="alc-tool-icon" viewBox="0 0 24 24" aria-hidden="true"
        focusable="false">
        <path d="M3 7h6l2 2h10l-2 10H3Z"></path>
        <path d="M12 12v5M9.5 14.5h5"></path>
      </svg>
    </button>
    <div class="alc-settings-control">
      <button id="alc-settings" class="alc-tool-button alc-tool-icon-button"
        type="button" aria-label="More settings" title="More settings"
        aria-controls="alc-settings-panel" aria-expanded="false">
        <svg class="alc-tool-icon" viewBox="0 0 24 24" aria-hidden="true"
          focusable="false">
          <circle cx="12" cy="12" r="3"></circle>
          <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.86 2.86-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21H9.6v-.1A1.7 1.7 0 0 0 8.6 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.86-2.86.06-.06A1.7 1.7 0 0 0 4.2 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H2.4V9.6h.1A1.7 1.7 0 0 0 4.2 8.6a1.7 1.7 0 0 0-.34-1.88l-.06-.06L6.66 3.8l.06.06A1.7 1.7 0 0 0 8.6 4.2a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V2.4h4v.1a1.7 1.7 0 0 0 1 1.7 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.86 2.86-.06.06A1.7 1.7 0 0 0 19.4 8.6a1.7 1.7 0 0 0 .6 1 1.7 1.7 0 0 0 1.1.4h.1v4h-.1a1.7 1.7 0 0 0-1.7 1z"></path>
        </svg>
      </button>
      <section id="alc-settings-panel" class="alc-settings-panel" hidden
        role="dialog" aria-modal="false" aria-labelledby="alc-settings-heading">
        <header class="alc-settings-header">
          <h2 id="alc-settings-heading">More settings</h2>
          <button id="alc-settings-close" class="alc-settings-close"
            type="button" aria-label="Close more settings">
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              <path d="M6 6l12 12M18 6L6 18"></path>
            </svg>
          </button>
        </header>
        <div class="alc-settings-grid">
          <label class="alc-settings-field">
            <span id="alc-settings-layout-label">Translation layout</span>
            <select id="alc-settings-layout">
              <option value="parallel">Side by side</option>
              <option value="stacked">Stacked</option>
            </select>
          </label>
          <label class="alc-settings-field">
            <span id="alc-settings-edit-label">Enter edit mode</span>
            <select id="alc-settings-edit">
              <option value="double">Double click</option>
              <option value="single">Single click</option>
            </select>
          </label>
          <label class="alc-settings-field">
            <span id="alc-settings-english-font-label">English font</span>
            <select id="alc-settings-english-font">
              <option value="system">System default</option>
              <option value="arial">Arial</option>
              <option value="helvetica">Helvetica</option>
              <option value="georgia">Georgia</option>
              <option value="times">Times New Roman</option>
              <option value="charter">Charter</option>
            </select>
          </label>
          <label class="alc-settings-field">
            <span id="alc-settings-chinese-font-label">Chinese font</span>
            <select id="alc-settings-chinese-font">
              <option value="system">System default</option>
              <option value="pingfang">PingFang SC</option>
              <option value="heiti">Heiti SC</option>
              <option value="song">Songti SC</option>
              <option value="kai">Kaiti SC</option>
            </select>
          </label>
          <label class="alc-settings-field alc-settings-range-field">
            <span class="alc-settings-range-header">
              <span id="alc-settings-scale-label">Display scale</span>
              <output id="alc-settings-scale-value" for="alc-settings-scale">100%</output>
            </span>
            <input id="alc-settings-scale" type="range" min="50" max="150"
              step="5" value="100">
            <span class="alc-settings-range-scale" aria-hidden="true">
              <span>50%</span><span>150%</span>
            </span>
          </label>
          <label class="alc-settings-field alc-settings-range-field">
            <span class="alc-settings-range-header">
              <span id="alc-settings-line-label">Line spacing</span>
              <output id="alc-settings-line-value" for="alc-settings-line">1.65</output>
            </span>
            <input id="alc-settings-line" type="range" min="1.3" max="2"
              step="0.05" value="1.65">
            <span class="alc-settings-range-scale" aria-hidden="true">
              <span>1.30</span><span>2.00</span>
            </span>
          </label>
          <label class="alc-settings-field alc-settings-range-field">
            <span class="alc-settings-range-header">
              <span id="alc-settings-block-spacing-label">Block spacing</span>
              <output id="alc-settings-block-spacing-value"
                for="alc-settings-block-spacing">100%</output>
            </span>
            <input id="alc-settings-block-spacing" type="range"
              min="50" max="150" step="5" value="100">
            <span class="alc-settings-range-scale" aria-hidden="true">
              <span>50%</span><span>150%</span>
            </span>
          </label>
          <label class="alc-settings-field alc-settings-range-field">
            <span class="alc-settings-range-header">
              <span id="alc-settings-width-label">Content width</span>
              <output id="alc-settings-width-value" for="alc-settings-width">100%</output>
            </span>
            <input id="alc-settings-width" type="range" min="50" max="150"
              step="5" value="100">
            <span class="alc-settings-range-scale" aria-hidden="true">
              <span>50%</span><span>150%</span>
            </span>
          </label>
        </div>
        <footer class="alc-settings-footer">
          <p id="alc-settings-note">Settings affect this preview only and do not modify source.</p>
          <button id="alc-settings-reset" type="button">Restore recommended values</button>
        </footer>
      </section>
    </div>
  </div>
  <p id="alc-storage-status" class="alc-storage-status" hidden></p>
  <div id="alc-speech-dock" class="alc-speech-player alc-speech-dock"
    data-player-kind="dock" hidden></div>
  <div id="alc-shell" class="alc-shell">
    <aside id="alc-contents" class="alc-contents">
      <nav aria-labelledby="alc-contents-heading">
        <h2 id="alc-contents-heading">Contents</h2>
        <ol id="alc-contents-list"></ol>
      </nav>
      <div id="alc-contents-resizer" class="alc-contents-resizer"
        role="separator" aria-orientation="vertical" tabindex="0"></div>
    </aside>
    <div class="alc-reader">
      <header id="alc-book-header" class="alc-book-header"></header>
      <main id="ac-document" class="ac-document"></main>
    </div>
  </div>
  <div id="alc-tooltip" class="alc-tooltip" role="tooltip" hidden></div>
  <dialog id="alc-editor-dialog" class="alc-dialog">
    <div class="alc-dialog-form">
      <header class="alc-dialog-header">
        <h2 id="alc-editor-heading">Edit</h2>
        <button id="alc-editor-close" class="alc-settings-close"
          type="button" aria-label="Close">
          <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <path d="M6 6l12 12M18 6L6 18"></path>
          </svg>
        </button>
      </header>
      <div class="alc-dialog-fields alc-dialog-primary-fields">
        <label><span id="alc-editor-title-label">Title</span>
          <input id="alc-editor-title" type="text">
        </label>
      </div>
      <div class="alc-editor-grid">
        <div class="alc-editor-pane">
          <label><span id="alc-editor-markdown-label">Markdown</span>
            <textarea id="alc-editor-markdown" spellcheck="true"></textarea>
          </label>
        </div>
      </div>
      <section id="alc-editor-advanced" class="alc-editor-advanced"
        aria-labelledby="alc-editor-advanced-label">
        <h3 id="alc-editor-advanced-label" class="alc-editor-advanced-heading">Preview and more settings</h3>
        <div class="alc-editor-extra-content">
          <div class="alc-editor-preview-pane">
            <span id="alc-editor-preview-label">Preview</span>
            <div id="alc-editor-preview" class="alc-editor-preview"></div>
          </div>
          <div class="alc-dialog-fields alc-dialog-advanced-fields">
            <label><span id="alc-editor-role-label">Role</span>
              <select id="alc-editor-role">
                <option value="translation">Translation</option>
                <option value="companion">Companion</option>
                <option value="guide">Guide</option>
                <option value="note">Note</option>
              </select>
            </label>
            <label><span id="alc-editor-priority-label">Priority</span>
              <input id="alc-editor-priority" type="number" min="1">
            </label>
          </div>
          <section class="alc-appearance-editor" aria-labelledby="alc-editor-colors-label">
            <div class="alc-appearance-heading">
              <span id="alc-editor-colors-label">Style for this role and priority</span>
              <button id="alc-editor-colors-reset" type="button">Use role default</button>
            </div>
            <div id="alc-editor-color-presets" class="alc-color-presets"></div>
            <div class="alc-color-fields">
              <label><span id="alc-editor-foreground-label">Text color</span>
                <span class="alc-color-control">
                  <input id="alc-editor-foreground-picker" type="color">
                  <input id="alc-editor-foreground" type="text" inputmode="text"
                    maxlength="7" pattern="#[0-9A-Fa-f]{{6}}" placeholder="#20262e">
                </span>
              </label>
              <label><span id="alc-editor-background-label">Background color</span>
                <span class="alc-color-control">
                  <input id="alc-editor-background-picker" type="color">
                  <input id="alc-editor-background" type="text" inputmode="text"
                    maxlength="7" pattern="#[0-9A-Fa-f]{{6}}" placeholder="#ffffff">
                </span>
              </label>
            </div>
          </section>
          <div id="alc-editor-history" class="alc-history"></div>
        </div>
      </section>
      <footer class="alc-dialog-footer">
        <button id="alc-editor-delete" class="alc-editor-delete" type="button"
          aria-label="Delete this element" hidden>Delete</button>
        <span class="alc-dialog-commit-actions">
          <button id="alc-editor-cancel" type="button">Cancel</button>
          <button id="alc-editor-save" type="button">Save</button>
        </span>
      </footer>
    </div>
  </dialog>
  <dialog id="alc-unsaved-dialog" class="alc-unsaved-dialog"
    aria-labelledby="alc-unsaved-heading">
    <div class="alc-unsaved-surface">
      <header>
        <h2 id="alc-unsaved-heading">Save current changes?</h2>
        <button id="alc-unsaved-close" type="button" aria-label="Continue editing">×</button>
      </header>
      <p id="alc-unsaved-description">
        Save the changes before leaving this editor, or leave without saving.
      </p>
      <p id="alc-unsaved-error" class="alc-unsaved-error" role="alert" hidden></p>
      <footer>
        <button id="alc-unsaved-discard" type="button">Don't save</button>
        <button id="alc-unsaved-save" type="button">Save changes</button>
      </footer>
    </div>
  </dialog>
  <script id="alc-render-payload" type="application/json">{encoded}</script>
</body>
</html>
"""


def _reader_icon_link(
    profile: Mapping[str, Any], payload: Mapping[str, Any]
) -> str:
    icon = profile.get("reader_icon")
    if not isinstance(icon, Mapping):
        return ""
    logical_name = icon.get("logical_name")
    resources = payload.get("resources")
    if not isinstance(logical_name, str) or not isinstance(resources, list):
        return ""
    for resource in resources:
        if not isinstance(resource, Mapping):
            continue
        if resource.get("logical_name") != logical_name:
            continue
        media_type = resource.get("media_type")
        data_uri = resource.get("data_uri")
        if isinstance(media_type, str) and isinstance(data_uri, str):
            return (
                f'<link rel="icon" type="{escape(media_type, quote=True)}" '
                f'href="{escape(data_uri, quote=True)}">'
            )
    return ""


def _source_title(document: RichDocument) -> str:
    for block in document.blocks:
        if (
            block.kind.value == "heading"
            and int(block.payload["level"]) == 1
        ):
            return str(block.payload["text"])
    return ""


def _copy_web_assets(output: Path) -> None:
    root = files("alc_render").joinpath("web_assets")
    _copy_traversable(root, output)
    katex_css = output / "katex" / "katex.min.css"
    css = katex_css.read_text(encoding="utf-8")
    css = re.sub(
        r'(src:url\((?P<woff2>[^)]+[.]woff2)\) format\("woff2"\))'
        r',url\([^)]+[.]woff\) format\("woff"\)'
        r',url\([^)]+[.]ttf\) format\("truetype"\)',
        r"\1",
        css,
    )
    katex_css.write_text(css, encoding="utf-8")


def _copy_traversable(source: Any, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        target = output / child.name
        if child.is_dir():
            _copy_traversable(child, target)
        else:
            target.write_bytes(child.read_bytes())


def _project_path(root: Path, relative: str, description: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise HTMLRenderError(f"{description} path is invalid")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or str(pure) != relative:
        raise HTMLRenderError(f"{description} path is unsafe: {relative}")
    path = (root / Path(*pure.parts)).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HTMLRenderError(f"{description} path escapes the project") from exc
    if not path.is_file():
        raise HTMLRenderError(f"{description} is missing: {relative}")
    return path


def _extract_reader_payload(text: str) -> Mapping[str, Any]:
    match = re.search(
        r'<script id="alc-render-payload" type="application/json">'
        r"(?P<value>.*?)</script>",
        text,
        re.DOTALL,
    )
    if match is None:
        raise HTMLRenderError("standalone HTML has no reader payload")
    try:
        value = json.loads(match.group("value").replace(r"<\/script", "</script"))
    except json.JSONDecodeError as exc:
        raise HTMLRenderError("standalone HTML reader payload is invalid") from exc
    if not isinstance(value, Mapping):
        raise HTMLRenderError("standalone HTML reader payload must be an object")
    if value.get("schema_version") == READER_PAYLOAD_V2_SCHEMA:
        return _expand_reader_payload_v2(text, value)
    return value


def _expand_reader_payload_v2(
    text: str, boot: Mapping[str, Any]
) -> Mapping[str, Any]:
    chunks = boot.get("reader_chunks")
    manifest = boot.get("block_manifest")
    resources = boot.get("resources")
    if (
        not isinstance(chunks, list)
        or not isinstance(manifest, list)
        or not isinstance(resources, list)
    ):
        raise HTMLRenderError("standalone HTML reader manifest is invalid")
    expanded = json.loads(json.dumps(boot, ensure_ascii=False))
    publication = expanded.get("publication")
    source = publication.get("source_document") if isinstance(publication, dict) else None
    if not isinstance(source, dict):
        raise HTMLRenderError("standalone HTML reader manifest has no source")

    expected_chunk_ids: set[str] = set()
    manifest_chunk_names = {
        raw.get("chunk_id")
        for raw in chunks
        if isinstance(raw, Mapping) and isinstance(raw.get("chunk_id"), str)
    }
    blocks: list[object] = []
    fingerprints: dict[str, object] = {}
    positioned_revisions: list[tuple[int, object]] = []
    chunk_selected_values: list[object] = []
    cursor = 0
    for raw in chunks:
        if not isinstance(raw, Mapping) or set(raw) != {
            "chunk_id",
            "payload_id",
            "block_start",
            "block_end",
        }:
            raise HTMLRenderError("standalone HTML reader chunk manifest is invalid")
        chunk_id = raw.get("chunk_id")
        payload_id = raw.get("payload_id")
        start = raw.get("block_start")
        end = raw.get("block_end")
        if (
            not isinstance(chunk_id, str)
            or not isinstance(payload_id, str)
            or payload_id in expected_chunk_ids
            or isinstance(start, bool)
            or not isinstance(start, int)
            or isinstance(end, bool)
            or not isinstance(end, int)
            or start != cursor
            or end < start
        ):
            raise HTMLRenderError("standalone HTML reader chunk ranges are invalid")
        expected_chunk_ids.add(payload_id)
        chunk = _extract_json_script(text, payload_id)
        if (
            chunk.get("schema_version") != READER_CHUNK_SCHEMA
            or chunk.get("chunk_id") != chunk_id
            or chunk.get("block_start") != start
            or chunk.get("block_end") != end
        ):
            raise HTMLRenderError("standalone HTML reader chunk identity is invalid")
        chunk_blocks = chunk.get("blocks")
        chunk_fingerprints = chunk.get("block_fingerprints")
        chunk_revisions = chunk.get("revisions")
        revision_positions = chunk.get("revision_positions")
        chunk_selected = chunk.get("selected_revision_digests")
        required_chunk_ids = chunk.get("required_chunk_ids", [])
        if (
            not isinstance(chunk_blocks, list)
            or len(chunk_blocks) != end - start
            or not isinstance(chunk_fingerprints, Mapping)
            or not isinstance(chunk_revisions, list)
            or not isinstance(revision_positions, list)
            or len(revision_positions) != len(chunk_revisions)
            or any(
                isinstance(item, bool) or not isinstance(item, int)
                for item in revision_positions
            )
            or not isinstance(chunk_selected, list)
            or not isinstance(required_chunk_ids, list)
            or any(not isinstance(item, str) for item in required_chunk_ids)
            or len(required_chunk_ids) != len(set(required_chunk_ids))
            or chunk_id in required_chunk_ids
            or not set(required_chunk_ids).issubset(manifest_chunk_names)
        ):
            raise HTMLRenderError("standalone HTML reader chunk content is invalid")
        blocks.extend(chunk_blocks)
        fingerprints.update(chunk_fingerprints)
        positioned_revisions.extend(zip(revision_positions, chunk_revisions))
        chunk_selected_values.extend(chunk_selected)
        cursor = end
    if cursor != len(manifest):
        raise HTMLRenderError("standalone HTML reader chunks are incomplete")
    positioned_revisions.sort(key=lambda item: item[0])
    if [item[0] for item in positioned_revisions] != list(
        range(len(positioned_revisions))
    ):
        raise HTMLRenderError(
            "standalone HTML reader revision order is invalid"
        )
    revisions = [item[1] for item in positioned_revisions]
    selected = boot.get("selected_revision_digests")
    if (
        not isinstance(selected, list)
        or len(selected) != len(set(selected))
        or set(selected) != set(chunk_selected_values)
    ):
        raise HTMLRenderError(
            "standalone HTML reader selected revisions are inconsistent"
        )
    for index, raw in enumerate(blocks):
        item = manifest[index]
        if (
            not isinstance(raw, Mapping)
            or not isinstance(item, Mapping)
            or item.get("block_id") != raw.get("block_id")
            or item.get("kind") != raw.get("kind")
            or item.get("ordinal") != raw.get("ordinal")
        ):
            raise HTMLRenderError("standalone HTML reader block manifest differs")

    boot_roles = boot.get("selected_roles")
    boot_headings = boot.get("selected_heading_fragments")
    if boot_roles is not None or boot_headings is not None:
        outline = publication.get("outline")
        if not isinstance(outline, list):
            raise HTMLRenderError("standalone HTML reader outline is invalid")
        try:
            expected_roles, expected_headings = _selected_fragment_boot_metadata(
                revisions, selected, blocks, outline
            )
        except StandaloneHtmlError as exc:
            raise HTMLRenderError(
                "standalone HTML reader visibility manifest is invalid"
            ) from exc
        if (
            (boot_roles is not None and boot_roles != expected_roles)
            or (boot_headings is not None and boot_headings != expected_headings)
        ):
            raise HTMLRenderError(
                "standalone HTML reader visibility manifest differs"
            )

    expected_resource_ids: set[str] = set()
    loaded_resources: list[object] = []
    for raw in resources:
        if not isinstance(raw, Mapping):
            raise HTMLRenderError("standalone HTML resource manifest is invalid")
        payload_id = raw.get("payload_id")
        if not isinstance(payload_id, str) or payload_id in expected_resource_ids:
            raise HTMLRenderError("standalone HTML resource payload IDs repeat")
        expected_resource_ids.add(payload_id)
        value = _extract_json_script(text, payload_id)
        loaded = value.get("resource")
        if (
            value.get("schema_version") != READER_RESOURCE_SCHEMA
            or not isinstance(loaded, Mapping)
            or any(
                loaded.get(key) != item
                for key, item in raw.items()
                if key != "payload_id"
            )
        ):
            raise HTMLRenderError("standalone HTML resource payload is invalid")
        loaded_resources.append(dict(loaded))

    actual_chunk_ids = set(re.findall(
        r'<script id="([^"]+)" class="alc-render-reader-chunk"', text
    ))
    actual_resource_ids = set(re.findall(
        r'<script id="([^"]+)" class="alc-render-reader-resource"', text
    ))
    if (
        actual_chunk_ids != expected_chunk_ids
        or actual_resource_ids != expected_resource_ids
    ):
        raise HTMLRenderError("standalone HTML contains orphan reader payloads")

    expanded["schema_version"] = READER_PAYLOAD_SCHEMA
    expanded.pop("block_manifest", None)
    expanded.pop("reader_chunks", None)
    expanded.pop("selected_roles", None)
    expanded.pop("selected_heading_fragments", None)
    expanded["block_fingerprints"] = fingerprints
    expanded["revisions"] = revisions
    expanded["selected_revision_digests"] = selected
    expanded["resources"] = loaded_resources
    source["blocks"] = blocks
    return expanded


def _extract_json_script(text: str, identifier: str) -> Mapping[str, Any]:
    matches = re.findall(
        r'<script id="' + re.escape(identifier) + r'"[^>]*>'
        r"(?P<value>.*?)</script>",
        text,
        re.DOTALL,
    )
    if len(matches) != 1:
        raise HTMLRenderError(
            f"standalone HTML reader payload count is invalid: {identifier}"
        )
    try:
        value = json.loads(matches[0].replace(r"<\/script", "</script"))
    except json.JSONDecodeError as exc:
        raise HTMLRenderError(
            f"standalone HTML reader payload is invalid: {identifier}"
        ) from exc
    if not isinstance(value, Mapping):
        raise HTMLRenderError(
            f"standalone HTML reader payload must be an object: {identifier}"
        )
    return value


def _validate_reader_resources(
    publication: Publication,
    payload: Mapping[str, Any],
) -> None:
    raw_resources = payload.get("resources")
    if not isinstance(raw_resources, list):
        raise HTMLRenderError("standalone HTML resources are invalid")
    resources: dict[str, Mapping[str, Any]] = {}
    expected_fields = {
        "artifact_digest",
        "media_type",
        "logical_name",
        "size",
        "data_uri",
    }
    for raw in raw_resources:
        if not isinstance(raw, Mapping) or set(raw) != expected_fields:
            raise HTMLRenderError("standalone HTML resource metadata is invalid")
        digest = raw.get("artifact_digest")
        if not isinstance(digest, str) or digest in resources:
            raise HTMLRenderError("standalone HTML resource identity is invalid")
        resources[digest] = raw
    declarations = _resource_declarations(publication)
    expected_digests = {str(item["artifact_digest"]) for item in declarations}
    if set(resources) != expected_digests:
        raise HTMLRenderError(
            "standalone HTML resources are incomplete"
        )
    for declaration in declarations:
        digest = str(declaration["artifact_digest"])
        media_type = str(declaration["media_type"])
        size = int(declaration["size"])
        raw = resources[digest]
        if (
            raw.get("media_type") != media_type
            or raw.get("logical_name") != declaration["logical_name"]
            or raw.get("size") != size
        ):
            raise HTMLRenderError(
                "standalone HTML resource metadata differs from the publication"
            )
        data_uri = raw.get("data_uri")
        prefix = f"data:{media_type};base64,"
        if not isinstance(data_uri, str) or not data_uri.startswith(prefix):
            raise HTMLRenderError(
                "standalone HTML source resource data URI is invalid"
            )
        try:
            resource_bytes = base64.b64decode(
                data_uri[len(prefix) :],
                validate=True,
            )
        except (binascii.Error, ValueError) as exc:
            raise HTMLRenderError(
                "standalone HTML source resource base64 is invalid"
            ) from exc
        if (
            len(resource_bytes) != size
            or hashlib.sha256(resource_bytes).hexdigest()
            != digest
        ):
            raise HTMLRenderError(
                "standalone HTML resource bytes differ from the publication"
            )


def _validate_reader_revisions(
    publication: Publication,
    payload: Mapping[str, Any],
) -> tuple[FragmentRevision, ...]:
    raw_revisions = payload.get("revisions")
    if not isinstance(raw_revisions, list):
        raise HTMLRenderError("standalone HTML revisions are invalid")
    groups: dict[str, list[FragmentRevision]] = {}
    order: list[str] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_revisions:
        if (
            not isinstance(raw, Mapping)
            or set(raw) != {
                "metadata",
                "markdown_body",
                "semantic_digest",
            }
            or not isinstance(raw.get("metadata"), Mapping)
            or not isinstance(raw.get("markdown_body"), str)
            or not isinstance(raw.get("semantic_digest"), str)
        ):
            raise HTMLRenderError(
                "standalone HTML revision record is invalid"
            )
        try:
            revision = fragment_revision_from_document(
                raw["metadata"],
                raw["markdown_body"],
            )
        except ValueError as exc:
            raise HTMLRenderError(
                "standalone HTML contains malformed fragment metadata"
            ) from exc
        if (
            revision.semantic_digest != raw["semantic_digest"]
            or revision.source != publication.source
        ):
            raise HTMLRenderError(
                "standalone HTML fragment identity is inconsistent"
            )
        identity = (revision.fragment_id, revision.semantic_digest)
        if identity in seen:
            raise HTMLRenderError(
                "standalone HTML contains a duplicate fragment revision"
            )
        seen.add(identity)
        if revision.fragment_id not in groups:
            groups[revision.fragment_id] = []
            order.append(revision.fragment_id)
        groups[revision.fragment_id].append(revision)

    selected: list[FragmentRevision] = []
    for fragment_id in order:
        try:
            resolution = resolve_fragment_revisions(groups[fragment_id])
        except ValueError as exc:
            raise HTMLRenderError(
                "standalone HTML fragment history is invalid"
            ) from exc
        if resolution.selected is not None:
            selected.append(resolution.selected)
    position = {fragment_id: index for index, fragment_id in enumerate(order)}
    selected.sort(
        key=lambda item: (item.priority, position[item.fragment_id])
    )
    _validate_selected(publication, selected)

    claimed = payload.get("selected_revision_digests")
    expected = [item.semantic_digest for item in selected]
    if (
        not isinstance(claimed, list)
        or any(not isinstance(item, str) for item in claimed)
        or claimed != expected
    ):
        raise HTMLRenderError(
            "standalone HTML selected revisions are inconsistent"
        )
    return tuple(selected)


def _expected_selected_revision_digests(
    value: Sequence[str] | None,
) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes, bytearray)):
        raise TypeError("expected selected revision digests must be a sequence")
    result = tuple(value)
    if any(not isinstance(item, str) or not item for item in result):
        raise ValueError(
            "expected selected revision digests must be non-empty strings"
        )
    return result


def _diagnostic_text(item: RevisionDiagnostic) -> str:
    detail = f" ({', '.join(item.paths)})" if item.paths else ""
    return f"{item.code}: {item.message}{detail}"


class _PortabilityValidator(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.errors: list[str] = []
        self._style_depth = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self._check(tag, attrs)
        if tag.casefold() == "style":
            self._style_depth += 1

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self._check(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "style" and self._style_depth:
            self._style_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._style_depth:
            self._check_css(data)

    def _check(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = {
            key.casefold(): value
            for key, value in attrs
            if value is not None
        }
        lower = tag.casefold()
        for name in ("src", "poster"):
            value = values.get(name)
            if value is not None and not value.startswith("data:"):
                self.errors.append(f"{lower}[{name}]={value}")
        srcset = values.get("srcset")
        if srcset is not None:
            try:
                candidates = _srcset_candidates(srcset)
            except StandaloneHtmlError:
                self.errors.append(f"{lower}[srcset]={srcset}")
            else:
                for reference, _descriptor in candidates:
                    if not reference.startswith("data:"):
                        self.errors.append(
                            f"{lower}[srcset]={reference}"
                        )
        if lower == "object":
            value = values.get("data")
            if value is not None and not value.startswith("data:"):
                self.errors.append(f"object[data]={value}")
        if lower == "link":
            value = values.get("href")
            if value is not None and not (
                value.startswith("data:") or value.startswith("#")
            ):
                self.errors.append(f"link[href]={value}")
        if lower in {"image", "feimage", "use"}:
            for name in ("href", "xlink:href"):
                value = values.get(name)
                if value is not None and not (
                    value.startswith("data:") or value.startswith("#")
                ):
                    self.errors.append(f"{lower}[{name}]={value}")
        style = values.get("style")
        if style is not None:
            self._check_css(style)

    def _check_css(self, value: str) -> None:
        if re.search(r"@import\b", value, re.IGNORECASE):
            self.errors.append("css[@import]")
        for match in _CSS_URL_PATTERN.finditer(value):
            reference = next(
                item
                for item in (
                    match.group("single"),
                    match.group("double"),
                    match.group("plain"),
                )
                if item is not None
            ).strip()
            if not (
                reference.startswith("data:")
                or reference.startswith("#")
            ):
                self.errors.append(f"css[url]={reference}")


__all__ = [
    "AssetLoader",
    "EDITION_DIGEST_SCHEMA",
    "HTML_RENDER_RECIPE",
    "HTMLRenderError",
    "PublicationWorkspaceState",
    "READER_PAYLOAD_SCHEMA",
    "RenderedHTML",
    "publication_edition_digest",
    "read_publication_workspace_state",
    "render_html",
    "render_publication_html",
    "validate_publication_workspace",
    "validate_standalone_html",
]
