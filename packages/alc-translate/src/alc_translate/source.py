"""Source resolution, sampling, and immutable block projections."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import ac_document as _ac_document
from markdown_it import MarkdownIt
from markdown_it.common.utils import isStrSpace as _markdown_it_space
from markdown_it.rules_inline.link import link as _markdown_it_link
from ac_jobs import canonical_json_bytes
from ac_document import (
    AcDocumentService,
    ParseError,
    RichBlock,
    RichBlockKind,
    RichDocumentParserService,
    RichDocumentValidationError,
    SourceRepositoryError,
    rich_block_to_document,
)

from .contracts import TranslationSource


STRUCTURAL_FIGURE_PLACEHOLDER = "\ufffc"
_INTERNAL_BIBLIOGRAPHY_TARGET = re.compile(r"#bib\.bib[1-9][0-9]*")
_LINK_TOKEN_CHARACTER = r"A-Za-z0-9._~:/?#@!$&'*+,;=%-"


def _markdown_link_matches(
    text: str,
) -> tuple[tuple[int, int, str, str], ...]:
    """Return inline link spans using the same CommonMark parser as rendering."""

    text = _normalize_markdown_text(text)
    matches: list[tuple[int, int, str, str]] = []
    parser = MarkdownIt(
        "commonmark",
        {
            "html": False,
            "linkify": False,
            "typographer": False,
            "breaks": False,
        },
    )

    def capture_link(state: Any, silent: bool) -> bool:
        start = state.pos
        link_level = state.linkLevel
        label_end = state.md.helpers.parseLinkLabel(state, start, True)
        target = _markdown_link_lexical_target(state, label_end)
        matched = _markdown_it_link(state, silent)
        if (
            matched
            and not silent
            and link_level == 0
            and label_end >= 0
            and target is not None
        ):
            matches.append((start, state.pos, text[start + 1 : label_end], target))
        return matched

    parser.inline.ruler.at("link", capture_link)
    parser.inline.parse(text, parser, {}, [])
    return tuple(matches)


def _normalize_markdown_text(text: str) -> str:
    return re.sub(r"\r\n?|\n", "\n", text).replace("\0", "\ufffd")


def _markdown_link_lexical_target(state: Any, label_end: int) -> str | None:
    position = label_end + 1
    if label_end < 0 or position >= state.posMax or state.src[position] != "(":
        return None
    position += 1
    while position < state.posMax:
        character = state.src[position]
        if character != "\n" and not _markdown_it_space(character):
            break
        position += 1
    if position < state.posMax and state.src[position] == ")":
        return ""
    result = state.md.helpers.parseLinkDestination(
        state.src, position, state.posMax
    )
    if not result.ok:
        return None
    return state.src[position : result.pos]


class TranslationSourceError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


def resolve_translation_source(
    document: AcDocumentService,
    source: str | Path,
    *,
    refresh: bool = False,
) -> TranslationSource:
    """Resolve an existing local source through public ac-document APIs."""

    source_text = str(source)
    try:
        artifact = document.resolve_local_source(source_text)
        rich = RichDocumentParserService(document.repository).parse_source(
            artifact
        )
    except (
        ParseError,
        RichDocumentValidationError,
        SourceRepositoryError,
    ) as exc:
        raise TranslationSourceError(
            getattr(exc, "code", "rich_source_required"),
            str(exc),
        ) from exc
    if not rich.blocks:
        raise TranslationSourceError(
            "source_content_empty", "source contains no translatable blocks"
        )
    return TranslationSource(rich)


def source_blocks(source: TranslationSource) -> tuple[dict[str, Any], ...]:
    """Return source blocks projected for lossless translation prompts."""

    presentation = _source_presentation_or_none(source.rich)
    views_by_block_id = {
        str(entry["block_id"]): entry
        for entry in (presentation or {}).get("blocks", ())
    }
    return tuple(
        _project_translation_surface(
            _project_source_presentation(
                rich_block_to_document(item),
                views_by_block_id.get(item.block_id),
            )
        )
        for item in source.rich.blocks
    )


def source_note_blocks(
    source: TranslationSource,
    *,
    owner_block_ids: set[str] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Return provenance-bound source-note units for translation."""

    notes = _source_notes_or_none(source.rich)
    if notes is None:
        return ()
    blocks_by_id = {block.block_id: block for block in source.rich.blocks}
    output: list[dict[str, Any]] = []
    for note in notes.get("notes", ()):
        if not isinstance(note, Mapping):
            raise TranslationSourceError(
                "source_notes_invalid", "source note entry must be an object"
            )
        note_id = str(note.get("note_id", ""))
        owner_block_id = str(note.get("owner_block_id", ""))
        owner = blocks_by_id.get(owner_block_id)
        if not note_id or owner is None:
            raise TranslationSourceError(
                "source_notes_invalid", "source note identity is invalid"
            )
        if owner_block_ids is not None and owner_block_id not in owner_block_ids:
            continue
        payload = {
            "text": str(note.get("body", "")),
            "inline_spans": list(note.get("inline_spans", ())),
        }
        unit = {
            "block_id": f"source-note:{note_id}",
            "ordinal": int(note.get("ordinal", len(output))),
            "kind": "source_note",
            "section_path": list(owner.section_path),
            "payload": payload,
            "source_note": {
                "note_id": note_id,
                "owner_block_id": owner_block_id,
            },
        }
        output.append({**unit, "source_identity": source_identity(unit)})
    return tuple(output)


def source_note_link_markdown(block: Mapping[str, Any]) -> str | None:
    """Return exact Markdown for one link-only source-note body."""

    if str(block.get("kind")) != "source_note":
        return None
    payload = block.get("payload")
    if not isinstance(payload, Mapping):
        raise TranslationSourceError(
            "source_block_invalid", "source block payload must be an object"
        )
    spans = _mapping_items(payload.get("inline_spans"))
    if len(spans) != 1 or str(spans[0].get("kind")) != "link":
        return None
    label = str(spans[0].get("text", ""))
    target = str(spans[0].get("target", ""))
    if not label or not target or label != str(payload.get("text", "")):
        return None
    if label == target and re.fullmatch(r"[A-Za-z][A-Za-z0-9+.-]*:[^\s<>]+", target):
        return f"<{target}>"
    return f"[{label}]({target})"


def _source_presentation_or_none(document: Any) -> Mapping[str, Any] | None:
    metadata = getattr(document, "metadata", {})
    present = isinstance(metadata, Mapping) and "source_presentation" in metadata
    accessor = getattr(_ac_document, "source_presentation", None)
    if not callable(accessor):
        if present:
            raise TranslationSourceError(
                "source_presentation_unsupported",
                "source presentation metadata requires AC Document "
                "source-presentation support",
            )
        return None
    return accessor(document)


def _source_notes_or_none(document: Any) -> Mapping[str, Any] | None:
    metadata = getattr(document, "metadata", {})
    present = isinstance(metadata, Mapping) and "source_notes" in metadata
    accessor = getattr(_ac_document, "source_notes", None)
    if not callable(accessor):
        if present:
            raise TranslationSourceError(
                "source_notes_unsupported",
                "source note metadata requires AC Document source-note support",
            )
        return None
    return accessor(document)


def deterministic_language_samples(
    source: TranslationSource,
    *,
    maximum_characters: int = 2400,
) -> tuple[str, ...]:
    """Use stable beginning/middle/end samples from natural-language text."""

    if maximum_characters < 3:
        raise ValueError("maximum_characters must be at least three")
    values = [_rich_block_text(item) for item in source.rich.blocks]
    joined = "\n\n".join(value for value in values if value.strip())
    if not joined:
        return ("",)
    if len(joined) <= maximum_characters:
        return (joined,)
    width = maximum_characters // 3
    middle = max(0, (len(joined) - width) // 2)
    return (
        joined[:width],
        joined[middle : middle + width],
        joined[-width:],
    )


def same_primary_language(source_tag: str, target_tag: str) -> bool:
    source = _primary_language(source_tag)
    target = _primary_language(target_tag)
    return bool(source and target and source == target)


def source_identity(block: Mapping[str, Any]) -> dict[str, Any]:
    """Project the source structure that translation must preserve exactly."""

    kind = str(block.get("kind"))
    payload = block.get("payload")
    if not isinstance(payload, Mapping):
        raise TranslationSourceError(
            "source_block_invalid", "source block payload must be an object"
        )
    equations: list[str] = []
    links: list[str] = []
    if kind == "equation":
        equations.append(str(payload.get("tex", "")))
    elif kind in {"paragraph", "source_note"}:
        _extend_inline_identity(
            payload.get("inline_spans"),
            equations=equations,
            links=links,
        )
    elif kind == "list":
        for item in _mapping_items(payload.get("items")):
            _extend_inline_identity(
                item.get("inline_spans"),
                equations=equations,
                links=links,
            )
    elif kind in {"heading", "table", "figure", "translation_unit"}:
        _extend_markdown_identity(
            block_text(block),
            equations=equations,
            links=links,
        )
    return {
        "equations": equations,
        "code_text": str(payload["text"]) if kind == "code" else None,
        "link_targets": links,
        "asset_digest": (
            str(payload["asset_digest"])
            if kind == "figure" and payload.get("asset_digest")
            else None
        ),
        "asset_target": (
            str(payload["target"])
            if kind == "figure" and payload.get("target")
            else None
        ),
    }


def validate_translation_text(text: str, block: Mapping[str, Any]) -> None:
    if not isinstance(text, str) or not text.strip():
        raise TranslationSourceError(
            "translation_coverage_invalid",
            f"translation text is empty for {block.get('block_id', '<unknown>')}",
        )
    identity = source_identity(block)
    if identity["code_text"] is not None and text != identity["code_text"]:
        raise TranslationSourceError(
            "translation_source_identity_invalid",
            f"translation changed code text for {block['block_id']}",
        )
    expected_equations = Counter(identity["equations"])
    if str(block.get("kind")) == "equation":
        expected_text = next(iter(expected_equations), "")
        if text != expected_text:
            raise TranslationSourceError(
                "translation_source_identity_invalid",
                f"translation changed equation text for {block['block_id']}",
            )
    elif (
        str(block.get("kind")) == "figure"
        and Counter(_markdown_math_occurrences(text)) != expected_equations
    ) or _formula_occurrences(text, expected_equations) != expected_equations:
        raise TranslationSourceError(
            "translation_source_identity_invalid",
            "translation changed formula occurrences for "
            f"{block['block_id']}",
            {
                "formula_diagnostics": list(
                    formula_identity_diagnostics(
                        (block,),
                        ({"block_id": block.get("block_id"), "text": text},),
                    )
                )
            },
        )
    if str(block.get("kind")) != "equation":
        expected_links = Counter(identity["link_targets"])
        if _link_occurrences(text, expected_links) != expected_links:
            raise TranslationSourceError(
                "translation_source_identity_invalid",
                f"translation changed link occurrences for {block['block_id']}",
            )
        expected_citations = Counter(_internal_bibliography_links(block))
        if (
            _translated_internal_bibliography_links(text)
            != expected_citations
        ):
            raise TranslationSourceError(
                "translation_source_identity_invalid",
                "translation changed internal bibliography link labels for "
                f"{block['block_id']}",
            )
        expected_groups = Counter(_internal_bibliography_citation_groups(block))
        if (
            Counter(_markdown_internal_bibliography_citation_groups(text))
            != expected_groups
        ):
            raise TranslationSourceError(
                "translation_source_identity_invalid",
                "translation changed internal bibliography citation groups for "
                f"{block['block_id']}",
            )
        bibliography_label = _bibliography_entry_label(block)
        if bibliography_label and not _translation_has_bibliography_label(
            text, bibliography_label
        ):
            raise TranslationSourceError(
                "translation_source_identity_invalid",
                f"translation changed bibliography entry label for {block['block_id']}",
            )
    if identity["asset_digest"] is not None and not str(
        identity["asset_digest"]
    ).strip():
        raise TranslationSourceError(
            "translation_source_identity_invalid",
            f"source asset identity is invalid for {block['block_id']}",
        )


def restore_translation_identity(
    text: str, block: Mapping[str, Any]
) -> str:
    """Restore one mechanically overescaped layer of source TeX identity.

    Provider JSON output occasionally preserves a Markdown math span while
    doubling every TeX command backslash.  Restore only when the decoded span
    is an exact one-layer inflation of a source equation occurrence.  This is
    deliberately source-relative: genuine authored ``\\`` commands are never
    collapsed merely because they contain adjacent backslashes.
    """

    if not isinstance(text, str):
        raise TranslationSourceError(
            "translation_coverage_invalid", "translation text must be a string"
        )
    expected = Counter(source_identity(block)["equations"])
    if not expected:
        return text
    spans = _markdown_math_spans(text)
    if not spans:
        return text
    remaining = expected.copy()
    replacements: list[tuple[int, int, str]] = []
    for start, end, actual_tex in spans:
        if remaining[actual_tex] > 0:
            remaining[actual_tex] -= 1
            continue
        restored_tex = next(
            (
                source_tex
                for source_tex, count in remaining.items()
                if count > 0
                and source_tex != actual_tex
                and actual_tex.replace("\\\\", "\\") == source_tex
            ),
            None,
        )
        if restored_tex is None:
            continue
        remaining[restored_tex] -= 1
        rendered = text[start:end]
        relative = rendered.find(actual_tex)
        if relative < 0:  # pragma: no cover - span parser owns this invariant
            continue
        replacements.append(
            (
                start + relative,
                start + relative + len(actual_tex),
                restored_tex,
            )
        )
    restored = text
    for start, end, replacement in reversed(replacements):
        restored = restored[:start] + replacement + restored[end:]
    return restored


def prompt_block(block: Mapping[str, Any]) -> dict[str, Any]:
    kind = str(block.get("kind"))
    if kind in {"paragraph", "source_note"}:
        payload = block.get("payload")
        if not isinstance(payload, Mapping):
            raise TranslationSourceError(
                "source_block_invalid", "source block payload must be an object"
            )
        return {
            "block_id": block.get("block_id"),
            "ordinal": block.get("ordinal"),
            "kind": kind,
            "section_path": block.get("section_path"),
            "payload": {"text": _compact_inline_text(payload)},
            "source_identity": source_identity(block),
        }
    if kind == "list":
        payload = block.get("payload")
        if not isinstance(payload, Mapping):
            raise TranslationSourceError(
                "source_block_invalid", "source block payload must be an object"
            )
        return {
            "block_id": block.get("block_id"),
            "ordinal": block.get("ordinal"),
            "kind": "list",
            "section_path": block.get("section_path"),
            "payload": {
                "ordered": bool(payload.get("ordered", False)),
                "items": [
                    {"text": _compact_inline_text(item)}
                    for item in _mapping_items(payload.get("items"))
                ],
            },
            "source_identity": source_identity(block),
        }
    if kind != "figure":
        return {**dict(block), "source_identity": source_identity(block)}
    payload = block.get("payload")
    if not isinstance(payload, Mapping):
        raise TranslationSourceError(
            "source_block_invalid", "source block payload must be an object"
        )
    identity = source_identity(block)
    return {
        "block_id": block.get("block_id"),
        "ordinal": block.get("ordinal"),
        "kind": "figure",
        "section_path": block.get("section_path"),
        "payload": {
            "caption": str(payload.get("caption", "")),
            "alt_text": str(payload.get("alt_text", "")),
        },
        "source_identity": {
            "equations": identity["equations"],
            "code_text": None,
            "link_targets": identity["link_targets"],
        },
    }


def _compact_inline_text(value: Mapping[str, Any]) -> str:
    spans = _mapping_items(value.get("inline_spans"))
    if not spans:
        return str(value.get("text", ""))
    rendered: list[str] = []
    for span in spans:
        kind = str(span.get("kind"))
        if kind == "math" and "tex" in span:
            tex = str(span["tex"])
            # Old LaTeX commonly embeds a math shift inside ``\mbox{...}``.
            # Wrapping such TeX in another pair of dollar delimiters creates
            # ambiguous Markdown, so use the equivalent parenthesized form.
            if _contains_unescaped(tex, "$"):
                rendered.append(f"\\({tex}\\)")
            else:
                rendered.append(f"${tex}$")
        elif kind == "link" and "target" in span:
            rendered.append(f"[{span.get('text', '')}]({span['target']})")
        else:
            rendered.append(str(span.get("text", "")))
    return "".join(rendered)


def _project_source_presentation(
    block: dict[str, Any], entry: Mapping[str, Any] | None
) -> dict[str, Any]:
    if entry is None:
        return block
    payload = block.get("payload")
    fields = entry.get("fields")
    if not isinstance(payload, dict) or not isinstance(fields, Sequence):
        raise TranslationSourceError(
            "source_block_invalid", "source presentation projection is invalid"
        )
    kind = str(block.get("kind"))
    projected = dict(payload)
    for raw_view in fields:
        if not isinstance(raw_view, Mapping):
            raise TranslationSourceError(
                "source_block_invalid", "source presentation field is invalid"
            )
        rendered = _compact_inline_text(raw_view)
        field = str(raw_view.get("field"))
        if kind == "heading" and field == "text":
            projected["text"] = rendered
        elif kind in {"figure", "table"} and field == "caption":
            projected["caption"] = rendered
        elif kind == "table" and field == "table_header":
            column = raw_view.get("column_index")
            if not isinstance(column, int) or isinstance(column, bool):
                raise TranslationSourceError(
                    "source_block_invalid", "Table header projection is invalid"
                )
            headers = list(projected.get("headers", ()))
            if not 0 <= column < len(headers):
                raise TranslationSourceError(
                    "source_block_invalid", "Table header projection is out of bounds"
                )
            headers[column] = rendered
            projected["headers"] = headers
        elif kind == "table" and field == "table_cell":
            row_index = raw_view.get("row_index")
            column = raw_view.get("column_index")
            rows = [list(row) for row in projected.get("rows", ())]
            if (
                not isinstance(row_index, int)
                or isinstance(row_index, bool)
                or not isinstance(column, int)
                or isinstance(column, bool)
                or not 0 <= row_index < len(rows)
                or not 0 <= column < len(rows[row_index])
            ):
                raise TranslationSourceError(
                    "source_block_invalid", "Table cell projection is out of bounds"
                )
            rows[row_index][column] = rendered
            projected["rows"] = rows
    return {**block, "payload": projected}


def _project_translation_surface(block: dict[str, Any]) -> dict[str, Any]:
    if str(block.get("kind")) != "table":
        return block
    payload = block.get("payload")
    if not isinstance(payload, Mapping):
        raise TranslationSourceError(
            "source_block_invalid", "source block payload must be an object"
        )
    return {**block, "payload": {"caption": str(payload.get("caption", ""))}}


def block_text(block: Mapping[str, Any]) -> str:
    """Return only human-visible source text used for literal term matching."""

    kind = str(block.get("kind"))
    payload = block.get("payload")
    if not isinstance(payload, Mapping):
        raise TranslationSourceError(
            "source_block_invalid", "source block payload must be an object"
        )
    if kind in {
        "heading",
        "paragraph",
        "source_note",
        "code",
        "translation_unit",
    }:
        return str(payload.get("text", ""))
    if kind == "equation":
        return str(payload.get("tex", ""))
    if kind == "list":
        return "\n".join(
            str(item.get("text", "")) for item in _mapping_items(payload.get("items"))
        )
    if kind == "table":
        rows = [payload.get("headers", []), *payload.get("rows", [])]
        rendered_rows = [
            " | ".join(str(cell) for cell in row)
            for row in rows
            if isinstance(row, Sequence) and not isinstance(row, (str, bytes))
        ]
        caption = str(payload.get("caption", "")).strip()
        return "\n".join(([caption] if caption else []) + rendered_rows)
    if kind == "figure":
        caption = str(payload.get("caption", "")).strip()
        return caption or str(payload.get("alt_text", ""))
    raise TranslationSourceError(
        "source_block_invalid", f"unsupported block kind: {kind}"
    )


def translation_text_groups(
    block: Mapping[str, Any], *, max_bytes: int
) -> tuple[tuple[str, ...], ...]:
    """Return bounded, source-ordered text groups for one internal translation.

    The outer tuple preserves list-item boundaries.  Inner tuples contain
    bounded segments that may be translated independently and joined with a
    space.  Markdown math and links are indivisible while splitting.
    """

    if (
        isinstance(max_bytes, bool)
        or not isinstance(max_bytes, int)
        or max_bytes < 64
    ):
        raise TranslationSourceError(
            "translation_unit_invalid", "translation max_bytes is too small"
        )
    kind = str(block.get("kind"))
    payload = block.get("payload")
    if not isinstance(payload, Mapping):
        raise TranslationSourceError(
            "source_block_invalid", "source block payload must be an object"
        )
    if kind == "list":
        values = tuple(
            _compact_inline_text(item)
            for item in _mapping_items(payload.get("items"))
        )
    elif kind in {"paragraph", "source_note"}:
        values = (_compact_inline_text(payload),)
    else:
        values = (block_text(block),)
    return tuple(
        _split_translation_markdown(value, max_bytes=max_bytes)
        for value in values
    )


def _split_translation_markdown(
    value: str, *, max_bytes: int
) -> tuple[str, ...]:
    text = _normalize_markdown_text(str(value)).strip()
    if not text or len(text.encode("utf-8")) <= max_bytes:
        return (text,) if text else ()
    protected = [
        *(span[:2] for span in _markdown_math_spans(text)),
        *(
            (start, end)
            for start, end, _, _ in _markdown_link_matches(
                _without_markdown_math(text)
            )
        ),
    ]
    protected.sort()
    atoms: dict[str, str] = {}
    masked = text
    for ordinal, (start, end) in reversed(tuple(enumerate(protected))):
        token = f"ALC_TRANSLATION_ATOM_{ordinal:06d}"
        atoms[token] = masked[start:end]
        masked = masked[:start] + token + masked[end:]
    pieces = re.findall(r"\S+(?:\s+|$)", masked)
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        candidate = current + piece
        restored_candidate = _restore_split_atoms(candidate, atoms).strip()
        if current and len(restored_candidate.encode("utf-8")) > max_bytes:
            chunks.append(_restore_split_atoms(current, atoms).strip())
            current = piece
        else:
            current = candidate
    if current:
        chunks.append(_restore_split_atoms(current, atoms).strip())
    if any(len(chunk.encode("utf-8")) > max_bytes for chunk in chunks):
        raise TranslationSourceError(
            "translation_atom_exceeds_input_budget",
            "one indivisible formula or link exceeds the translation unit budget",
        )
    return tuple(chunk for chunk in chunks if chunk)


def _restore_split_atoms(value: str, atoms: Mapping[str, str]) -> str:
    restored = value
    for token, atom in atoms.items():
        restored = restored.replace(token, atom)
    return restored


def block_digest(blocks: Sequence[Mapping[str, Any]]) -> str:
    return hashlib.sha256(canonical_json_bytes(list(blocks))).hexdigest()


def _rich_block_text(block: RichBlock) -> str:
    payload = block.payload
    if block.kind in {RichBlockKind.HEADING, RichBlockKind.PARAGRAPH}:
        return str(payload["text"])
    if block.kind is RichBlockKind.LIST:
        return "\n".join(str(item["text"]) for item in payload["items"])
    if block.kind is RichBlockKind.CODE:
        return str(payload["text"])
    if block.kind is RichBlockKind.EQUATION:
        return str(payload["tex"])
    if block.kind is RichBlockKind.TABLE:
        rows = [payload["headers"], *payload["rows"]]
        return "\n".join(" | ".join(map(str, row)) for row in rows)
    if block.kind is RichBlockKind.FIGURE:
        return str(payload["caption"])
    raise TranslationSourceError(
        "source_block_invalid", f"unsupported block kind: {block.kind}"
    )


def _mapping_items(value: Any) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TranslationSourceError(
            "source_block_invalid", "source identity array is invalid"
        )
    if any(not isinstance(item, Mapping) for item in value):
        raise TranslationSourceError(
            "source_block_invalid", "source identity item is invalid"
        )
    return tuple(value)


def _extend_inline_identity(
    value: Any,
    *,
    equations: list[str],
    links: list[str],
) -> None:
    for span in _mapping_items(value):
        kind = str(span.get("kind"))
        if kind == "math" and "tex" in span:
            equations.append(str(span["tex"]))
        elif kind == "link" and "target" in span:
            links.append(str(span["target"]))
        elif kind == "text":
            _extend_markdown_identity(
                str(span.get("text", "")),
                equations=equations,
                links=links,
            )


def _extend_markdown_identity(
    text: str,
    *,
    equations: list[str],
    links: list[str],
) -> None:
    equations.extend(_markdown_math_occurrences(text))
    links.extend(
        target
        for _, _, _, target in _markdown_link_matches(
            _without_markdown_math(text)
        )
    )


def _markdown_math_occurrences(text: str) -> tuple[str, ...]:
    return tuple(tex for _, _, tex in _markdown_math_spans(text))


def _markdown_math_spans(text: str) -> tuple[tuple[int, int, str], ...]:
    """Return Markdown math spans, tolerating old TeX nested math shifts.

    A formula such as ``$x>\\mbox{$1/2$}$`` is valid old-style TeX carried
    through LaTeXML, but a non-greedy dollar regex closes it at the inner math
    shift.  Braces make those inner shifts unambiguous: only an unescaped
    dollar at brace depth zero closes the outer Markdown span.
    """

    spans: list[tuple[int, int, str]] = []
    index = 0
    while index < len(text):
        delimiter: str | None = None
        closing: str | None = None
        content_start = index
        if text.startswith(r"\[", index) and not _is_escaped(text, index):
            delimiter, closing, content_start = r"\[", r"\]", index + 2
        elif text.startswith(r"\(", index) and not _is_escaped(text, index):
            delimiter, closing, content_start = r"\(", r"\)", index + 2
        elif text.startswith("$$", index) and not _is_escaped(text, index):
            delimiter, closing, content_start = "$$", "$$", index + 2
        elif (
            text[index] == "$"
            and not _is_escaped(text, index)
            and not text.startswith("$$", index)
        ):
            delimiter, closing, content_start = "$", "$", index + 1
        if delimiter is None or closing is None:
            index += 1
            continue

        end = _find_math_closing(
            text,
            content_start,
            closing,
            brace_aware=delimiter == "$",
        )
        if end is None:
            index += len(delimiter)
            continue
        spans.append((index, end + len(closing), text[content_start:end]))
        index = end + len(closing)
    return tuple(spans)


def _find_math_closing(
    text: str,
    start: int,
    closing: str,
    *,
    brace_aware: bool,
) -> int | None:
    brace_depth = 0
    index = start
    while index < len(text):
        if not _is_escaped(text, index):
            if brace_aware and text[index] == "{":
                brace_depth += 1
            elif brace_aware and text[index] == "}" and brace_depth:
                brace_depth -= 1
            elif brace_depth == 0 and text.startswith(closing, index):
                return index
        index += 1
    return None


def _contains_unescaped(text: str, token: str) -> bool:
    return any(
        text.startswith(token, index) and not _is_escaped(text, index)
        for index in range(len(text))
    )


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    index -= 1
    while index >= 0 and text[index] == "\\":
        backslashes += 1
        index -= 1
    return backslashes % 2 == 1


def _formula_occurrences(
    text: str,
    expected: Counter[str],
) -> Counter[str]:
    delimited = Counter(_markdown_math_occurrences(text))
    if delimited:
        return delimited
    edge_characters = r"A-Za-z0-9\\^_{}[\]"
    occupied: list[tuple[int, int]] = []
    occurrences: Counter[str] = Counter()
    # Undelimited TeX can contain another expected formula verbatim: for
    # example ``{\cal O}(H)`` contains ``H``. Treat the longest source
    # identities as atomic before counting shorter identities so the nested
    # text is not mistaken for an additional formula occurrence.
    for token in sorted(expected, key=lambda value: (-len(value), value)):
        if not token:
            continue
        pattern = re.compile(
            rf"(?<![{edge_characters}]){re.escape(token)}"
            rf"(?![{edge_characters}])"
        )
        matches = [
            match.span()
            for match in pattern.finditer(text)
            if not any(
                match.start() < end and start < match.end()
                for start, end in occupied
            )
        ]
        if matches:
            occurrences[token] = len(matches)
            occupied.extend(matches)
    return occurrences


def formula_identity_diagnostics(
    source_blocks: Sequence[Mapping[str, Any]],
    translations: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Describe formula identity differences without altering translations.

    The translation workflow already fixes block order separately.  This helper
    therefore identifies a matching TeX occurrence that left one block and
    appeared in another as a move, while retaining distinct missing and added
    diagnostics for unmatched occurrences.
    """

    source_by_id = {str(block.get("block_id")): block for block in source_blocks}
    translation_by_id = {
        str(item.get("block_id")): item
        for item in translations
        if isinstance(item.get("text"), str)
    }
    diagnostics: list[dict[str, Any]] = []
    source_occurrences: dict[str, list[tuple[str, int]]] = {}
    translation_occurrences: dict[str, list[tuple[str, int]]] = {}
    source_positions = {
        str(block.get("block_id")): index
        for index, block in enumerate(source_blocks)
    }
    translation_positions = {
        str(item.get("block_id")): index
        for index, item in enumerate(translations)
    }

    for block_id, block in source_by_id.items():
        if str(block.get("kind")) == "equation":
            continue
        expected = Counter(source_identity(block)["equations"])
        text = str(translation_by_id.get(block_id, {}).get("text", ""))
        actual = _formula_occurrences(text, expected)
        for tex in set(expected) | set(actual):
            difference = expected[tex] - actual[tex]
            if difference > 0:
                source_occurrences.setdefault(tex, []).append((block_id, difference))
            elif difference < 0:
                translation_occurrences.setdefault(tex, []).append(
                    (block_id, -difference)
                )

    for tex in sorted(set(source_occurrences) | set(translation_occurrences)):
        missing = list(source_occurrences.get(tex, ()))
        added = list(translation_occurrences.get(tex, ()))
        source_index = 0
        translation_index = 0
        while source_index < len(missing) and translation_index < len(added):
            source_block_id, missing_count = missing[source_index]
            translation_block_id, added_count = added[translation_index]
            count = min(missing_count, added_count)
            if source_block_id != translation_block_id:
                diagnostics.append(
                    _formula_diagnostic(
                        "formula_moved",
                        tex,
                        count,
                        source_block_id,
                        translation_block_id,
                        source_blocks,
                        translations,
                        source_positions,
                        translation_positions,
                    )
                )
                missing_count -= count
                added_count -= count
                if missing_count:
                    missing[source_index] = (source_block_id, missing_count)
                else:
                    source_index += 1
                if added_count:
                    added[translation_index] = (translation_block_id, added_count)
                else:
                    translation_index += 1
                continue
            source_index += 1
            translation_index += 1
        for source_block_id, count in missing[source_index:]:
            diagnostics.append(
                _formula_diagnostic(
                    "formula_missing",
                    tex,
                    count,
                    source_block_id,
                    source_block_id,
                    source_blocks,
                    translations,
                    source_positions,
                    translation_positions,
                )
            )
        for translation_block_id, count in added[translation_index:]:
            diagnostics.append(
                _formula_diagnostic(
                    "formula_added",
                    tex,
                    count,
                    translation_block_id,
                    translation_block_id,
                    source_blocks,
                    translations,
                    source_positions,
                    translation_positions,
                )
            )
    return tuple(diagnostics)


def _formula_diagnostic(
    code: str,
    tex: str,
    count: int,
    source_block_id: str,
    translation_block_id: str,
    source_blocks: Sequence[Mapping[str, Any]],
    translations: Sequence[Mapping[str, Any]],
    source_positions: Mapping[str, int],
    translation_positions: Mapping[str, int],
) -> dict[str, Any]:
    return {
        "code": code,
        "tex": tex,
        "occurrence_count": count,
        "source_block_id": source_block_id,
        "translation_block_id": translation_block_id,
        "source_neighbor_block_ids": _neighbor_block_ids(
            source_blocks, source_positions[source_block_id]
        ),
        "translation_neighbor_block_ids": _neighbor_block_ids(
            translations, translation_positions[translation_block_id]
        ),
    }


def _neighbor_block_ids(
    blocks: Sequence[Mapping[str, Any]], index: int
) -> list[str]:
    return [
        str(blocks[neighbor].get("block_id"))
        for neighbor in (index - 1, index + 1)
        if 0 <= neighbor < len(blocks)
    ]


def _link_occurrences(
    text: str,
    expected: Counter[str],
) -> Counter[str]:
    text = _normalize_markdown_text(_without_markdown_math(text))
    matches = _markdown_link_matches(text)
    occurrences = Counter(target for _, _, _, target in matches)
    pieces: list[str] = []
    previous = 0
    for start, end, _, _ in matches:
        pieces.extend(
            (text[previous:start], " " * (end - start))
        )
        previous = end
    pieces.append(text[previous:])
    unlinked_text = "".join(pieces)
    occurrences.update(
        {
            target: count
            for target in expected
            if (
                count := _literal_occurrence_count(
                    unlinked_text,
                    target,
                    edge_characters=_LINK_TOKEN_CHARACTER,
                )
            )
        }
    )
    return occurrences


def _internal_bibliography_links(
    block: Mapping[str, Any],
) -> tuple[tuple[str, str], ...]:
    kind = str(block.get("kind"))
    payload = block.get("payload")
    if not isinstance(payload, Mapping):
        raise TranslationSourceError(
            "source_block_invalid", "source block payload must be an object"
        )
    values: list[tuple[str, str]] = []
    if kind in {"paragraph", "source_note"}:
        _extend_internal_bibliography_inline(payload.get("inline_spans"), values)
    elif kind == "list":
        for item in _mapping_items(payload.get("items")):
            _extend_internal_bibliography_inline(item.get("inline_spans"), values)
    else:
        texts: list[str] = []
        if kind in {"heading", "translation_unit"}:
            texts.append(str(payload.get("text", "")))
        elif kind == "figure":
            texts.append(str(payload.get("caption", "")))
        elif kind == "table":
            texts.append(str(payload.get("caption", "")))
            texts.extend(str(item) for item in payload.get("headers", ()))
            texts.extend(
                str(item)
                for row in payload.get("rows", ())
                for item in row
            )
        for value in texts:
            values.extend(_markdown_internal_bibliography_links(value))
    return tuple(values)


def _internal_bibliography_citation_groups(
    block: Mapping[str, Any],
) -> tuple[str, ...]:
    return tuple(
        group
        for text in _block_markdown_values(block)
        for group in _markdown_internal_bibliography_citation_groups(text)
    )


def _block_markdown_values(block: Mapping[str, Any]) -> tuple[str, ...]:
    kind = str(block.get("kind"))
    payload = block.get("payload")
    if not isinstance(payload, Mapping):
        raise TranslationSourceError(
            "source_block_invalid", "source block payload must be an object"
        )
    if kind in {"paragraph", "source_note"}:
        return (_compact_inline_text(payload),)
    if kind == "list":
        return tuple(
            _compact_inline_text(item)
            for item in _mapping_items(payload.get("items"))
        )
    if kind in {"heading", "translation_unit"}:
        return (str(payload.get("text", "")),)
    if kind == "figure":
        return (str(payload.get("caption", "")),)
    if kind == "table":
        return (
            str(payload.get("caption", "")),
            *(str(item) for item in payload.get("headers", ())),
            *(
                str(item)
                for row in payload.get("rows", ())
                for item in row
            ),
        )
    return ()


def _extend_internal_bibliography_inline(
    raw_spans: Any, values: list[tuple[str, str]]
) -> None:
    for span in _mapping_items(raw_spans):
        kind = str(span.get("kind"))
        target = str(span.get("target", ""))
        if (
            kind == "link"
            and _INTERNAL_BIBLIOGRAPHY_TARGET.fullmatch(target)
        ):
            values.append((target, str(span.get("text", ""))))
        elif kind == "text":
            values.extend(
                _markdown_internal_bibliography_links(
                    str(span.get("text", ""))
                )
            )


def _markdown_internal_bibliography_links(
    text: str,
) -> tuple[tuple[str, str], ...]:
    return tuple(
        (target, label)
        for _, _, label, target in _markdown_link_matches(
            _without_markdown_math(text)
        )
        if _INTERNAL_BIBLIOGRAPHY_TARGET.fullmatch(target)
    )


def _markdown_internal_bibliography_citation_groups(
    text: str,
) -> tuple[str, ...]:
    value = _normalize_markdown_text(_without_markdown_math(text))
    matches = tuple(
        match
        for match in _markdown_link_matches(value)
        if _INTERNAL_BIBLIOGRAPHY_TARGET.fullmatch(match[3])
    )
    groups: list[str] = []
    index = 0
    separators = {" ", "\t", "\n", ",", ";", "；"}
    while index < len(matches):
        first = matches[index]
        last = first
        next_index = index + 1
        while next_index < len(matches):
            candidate = matches[next_index]
            between = value[last[1] : candidate[0]]
            if not between or any(character not in separators for character in between):
                break
            last = candidate
            next_index += 1
        start = first[0]
        end = last[1]
        bracketed = (
            start > 0
            and value[start - 1] == "["
            and not _is_escaped(value, start - 1)
            and end < len(value)
            and value[end] == "]"
            and not _is_escaped(value, end)
        )
        if bracketed:
            groups.append(value[start - 1 : end + 1])
        elif last is not first and all(
            match[2].strip().isdigit()
            for match in matches[index:next_index]
        ):
            groups.append(value[start:end])
        index = next_index
    return tuple(groups)


def _bibliography_entry_label(block: Mapping[str, Any]) -> str | None:
    if str(block.get("kind")) != "list":
        return None
    locator = block.get("locator")
    if not isinstance(locator, Mapping):
        return None
    source_id = str(locator.get("source_id", ""))
    if re.fullmatch(r"bib\.bib[1-9][0-9]*", source_id) is None:
        return None
    items = _mapping_items(
        block.get("payload", {}).get("items")
        if isinstance(block.get("payload"), Mapping)
        else None
    )
    if len(items) != 1:
        raise TranslationSourceError(
            "source_block_invalid", "bibliography block must contain one item"
        )
    label_match = re.match(
        r"\[([1-9][0-9]*)\]",
        str(items[0].get("text", "")).lstrip(),
    )
    if label_match is None:
        raise TranslationSourceError(
            "source_block_invalid",
            "bibliography block is missing its authored numeric label",
        )
    return label_match.group(0)


def _translation_has_bibliography_label(text: str, label: str) -> bool:
    value = str(text).lstrip()
    marker = re.match(r"(?:[-+*]|[1-9][0-9]*[.)])\s+", value)
    if marker is not None:
        value = value[marker.end() :]
    return value == label or value.startswith(label + " ")


def _translated_internal_bibliography_links(
    text: str,
) -> Counter[tuple[str, str]]:
    return Counter(_markdown_internal_bibliography_links(text))


def _without_markdown_math(text: str) -> str:
    pieces: list[str] = []
    previous = 0
    for start, end, _ in _markdown_math_spans(text):
        pieces.extend((text[previous:start], " " * (end - start)))
        previous = end
    pieces.append(text[previous:])
    return "".join(pieces)


def _literal_occurrence_count(
    text: str,
    token: str,
    *,
    edge_characters: str,
) -> int:
    if not token:
        return 0
    return len(
        re.findall(
            rf"(?<![{edge_characters}]){re.escape(token)}"
            rf"(?![{edge_characters}])",
            text,
        )
    )


def _primary_language(tag: str) -> str:
    value = str(tag or "").strip().replace("_", "-").casefold()
    primary = value.split("-", 1)[0]
    if not primary.isalpha() or not 2 <= len(primary) <= 8:
        return ""
    return primary


__all__ = [
    "STRUCTURAL_FIGURE_PLACEHOLDER",
    "TranslationSourceError",
    "block_digest",
    "block_text",
    "deterministic_language_samples",
    "formula_identity_diagnostics",
    "prompt_block",
    "resolve_translation_source",
    "same_primary_language",
    "source_blocks",
    "source_note_blocks",
    "source_note_link_markdown",
    "source_identity",
    "translation_text_groups",
    "restore_translation_identity",
    "validate_translation_text",
]
