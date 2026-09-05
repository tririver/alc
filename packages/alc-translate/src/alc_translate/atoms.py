"""Caller-owned protected atoms for model translation boundaries.

The model sees atom identifiers but never the Markdown/TeX/URL payload that an
identifier represents.  Rendering that payload is deliberately local, after
the model result has passed exact atom-coverage validation.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from .source import (
    TranslationSourceError,
    _bibliography_entry_label,
    _compact_inline_text,
    _markdown_link_details,
    _markdown_math_spans,
    _normalize_markdown_text,
    _without_markdown_math,
    block_text,
)

PROTECTED_ATOM_PLAN_SCHEMA = "alc.translate.protected_atom_plan.v1"
PROTECTED_ATOM_RESULT_SCHEMA = "alc.translate.protected_atom_result.v1"
TEXT_SLOT_PLAN_SCHEMA = "alc.translate.text_slot_plan.v1"
TEXT_SLOT_RESULT_SCHEMA = "alc.translate.text_slot_result.v1"


class ProtectedAtomError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


def protected_atom_plan(block: Mapping[str, Any]) -> dict[str, Any]:
    """Build the immutable, source-bound atom plan for one translation unit."""

    existing = block.get("protected_atom_plan")
    if isinstance(existing, Mapping):
        return _copied_plan(existing)
    block_id = _block_id(block)
    surface = _translation_surface(block)
    selected: list[tuple[int, int, str]] = []
    for start, end, kind in _protected_spans(surface, block):
        if start < 0 or end <= start or end > len(surface):
            raise ProtectedAtomError(
                "translation_atom_plan_invalid",
                f"protected atom span is invalid for {block_id}",
            )
        if any(start < other_end and other_start < end for other_start, other_end, _ in selected):
            continue
        selected.append((start, end, kind))
    selected.sort()

    link_details = {
        (start, end): (label, target)
        for start, end, label, target, _target_start, _target_end in _markdown_link_details(
            surface, normalize=False
        )
    }
    atoms: list[dict[str, Any]] = []
    parts: list[dict[str, Any]] = []
    cursor = 0
    for ordinal, (start, end, kind) in enumerate(selected):
        if start > cursor:
            parts.append({"kind": "text", "text": surface[cursor:start]})
        atom_id = f"{block_id}.atom-{ordinal:06d}"
        if kind == "link":
            label, _target = link_details[(start, end)]
            raw = surface[start:end]
            suffix = raw[2 + len(label) :]
            atoms.append(
                {
                    "atom_id": atom_id,
                    "kind": "link",
                    "payload": {
                        "source_markdown": raw,
                        "source_label": label,
                        "suffix": suffix,
                    },
                }
            )
            parts.append(
                {
                    "kind": "link",
                    "atom_id": atom_id,
                    "parts": [{"kind": "text", "text": label}],
                }
            )
        else:
            atoms.append(
                {
                    "atom_id": atom_id,
                    "kind": kind,
                    "payload": surface[start:end],
                }
            )
            parts.append({"kind": "atom", "atom_id": atom_id})
        cursor = end
    if cursor < len(surface):
        parts.append({"kind": "text", "text": surface[cursor:]})
    if not parts and surface:
        parts.append({"kind": "text", "text": surface})
    return {
        "schema_version": PROTECTED_ATOM_PLAN_SCHEMA,
        "block_id": block_id,
        "parts": parts,
        "atoms": atoms,
    }


def protected_prompt_block(block: Mapping[str, Any]) -> dict[str, Any]:
    """Return the model-safe plan projection, omitting every atom payload."""

    plan = protected_atom_plan(block)
    return {
        "block_id": plan["block_id"],
        "ordinal": block.get("ordinal"),
        "kind": str(block.get("kind")),
        "section_path": list(block.get("section_path", ())),
        "content": {
            "schema_version": PROTECTED_ATOM_PLAN_SCHEMA,
            "parts": plan["parts"],
        },
    }


def text_slot_plan(block: Mapping[str, Any]) -> dict[str, Any]:
    """Project caller-owned atoms into ordered, model-translatable text slots."""

    atom_plan = protected_atom_plan(block)
    block_id = str(atom_plan["block_id"])
    ordinal = 0

    def slot(text: str) -> dict[str, str]:
        nonlocal ordinal
        slot_id = f"{block_id}.text-{ordinal:06d}"
        ordinal += 1
        return {"kind": "text_slot", "slot_id": slot_id, "text": text}

    parts: list[dict[str, Any]] = []
    for raw in atom_plan["parts"]:
        part = _copy_part(raw)
        if part["kind"] == "text":
            parts.append(slot(str(part["text"])))
        elif part["kind"] == "link":
            parts.append(
                {
                    "kind": "link",
                    "atom_id": str(part["atom_id"]),
                    "parts": [slot(str(label["text"])) for label in part["parts"]],
                }
            )
        else:
            parts.append(
                {"kind": "atom", "atom_id": str(part["atom_id"])}
            )
    return {
        "schema_version": TEXT_SLOT_PLAN_SCHEMA,
        "block_id": block_id,
        "parts": parts,
    }


def text_slot_prompt_block(block: Mapping[str, Any]) -> dict[str, Any]:
    """Return a model-safe block whose output surface contains text slots only."""

    plan = text_slot_plan(block)
    return {
        "block_id": plan["block_id"],
        "ordinal": block.get("ordinal"),
        "kind": str(block.get("kind")),
        "section_path": list(block.get("section_path", ())),
        "content": {
            "schema_version": TEXT_SLOT_PLAN_SCHEMA,
            "parts": plan["parts"],
        },
    }


def text_slot_ids(block: Mapping[str, Any]) -> tuple[str, ...]:
    """Return every required text slot in deterministic source order."""

    output: list[str] = []
    for part in text_slot_plan(block)["parts"]:
        if part["kind"] == "text_slot":
            output.append(str(part["slot_id"]))
        elif part["kind"] == "link":
            output.extend(str(label["slot_id"]) for label in part["parts"])
    return tuple(output)


def assemble_text_slot_translation(
    block: Mapping[str, Any], text_slots: Any
) -> tuple[str, list[dict[str, Any]]]:
    """Assemble model-authored text slots with caller-owned source atoms."""

    if not isinstance(text_slots, Mapping):
        raise ProtectedAtomError(
            "translation_text_slots_invalid",
            "translation text_slots must be an object",
        )
    expected = text_slot_ids(block)
    actual = tuple(str(key) for key in text_slots)
    if set(actual) != set(expected) or len(actual) != len(expected):
        raise ProtectedAtomError(
            "translation_text_slots_invalid",
            f"translation text-slot coverage is invalid for {_block_id(block)}",
            {
                "missing_text_slot_ids": sorted(set(expected) - set(actual)),
                "unknown_text_slot_ids": sorted(set(actual) - set(expected)),
            },
        )
    values: dict[str, str] = {}
    for slot_id in expected:
        value = text_slots.get(slot_id)
        if not isinstance(value, str) or _has_unsafe_control(value):
            raise ProtectedAtomError(
                "translation_text_slot_invalid",
                f"translation text slot is invalid for {slot_id}",
            )
        values[slot_id] = value

    parts: list[dict[str, Any]] = []
    for part in text_slot_plan(block)["parts"]:
        if part["kind"] == "text_slot":
            parts.append({"kind": "text", "text": values[str(part["slot_id"])]})
        elif part["kind"] == "link":
            parts.append(
                {
                    "kind": "link",
                    "atom_id": str(part["atom_id"]),
                    "parts": [
                        {
                            "kind": "text",
                            "text": values[str(label["slot_id"])],
                        }
                        for label in part["parts"]
                    ],
                }
            )
        else:
            parts.append(
                {"kind": "atom", "atom_id": str(part["atom_id"])}
            )
    return assemble_protected_translation(block, parts)


def text_slot_values_from_parts(
    block: Mapping[str, Any], parts: Any
) -> dict[str, str]:
    """Project a source-ordered protected translation into review text slots."""

    _rendered, normalized = assemble_protected_translation(block, parts)
    plan_parts = text_slot_plan(block)["parts"]
    if len(normalized) != len(plan_parts):
        raise ProtectedAtomError(
            "translation_text_slot_projection_invalid",
            "protected translation no longer follows the caller-owned slot order",
        )
    values: dict[str, str] = {}
    for expected, actual in zip(plan_parts, normalized, strict=True):
        if expected["kind"] == "text_slot" and actual["kind"] == "text":
            values[str(expected["slot_id"])] = str(actual["text"])
            continue
        if expected["kind"] == "atom" and actual == {
            "kind": "atom",
            "atom_id": expected["atom_id"],
        }:
            continue
        if (
            expected["kind"] == "link"
            and actual["kind"] == "link"
            and actual["atom_id"] == expected["atom_id"]
            and len(actual["parts"]) == len(expected["parts"])
        ):
            for expected_label, actual_label in zip(
                expected["parts"], actual["parts"], strict=True
            ):
                if actual_label["kind"] != "text":
                    break
                values[str(expected_label["slot_id"])] = str(actual_label["text"])
            else:
                continue
        raise ProtectedAtomError(
            "translation_text_slot_projection_invalid",
            "protected translation changed the caller-owned slot order",
        )
    if set(values) != set(text_slot_ids(block)):
        raise ProtectedAtomError(
            "translation_text_slot_projection_invalid",
            "protected translation text-slot projection is incomplete",
        )
    return values


def source_protected_parts(block: Mapping[str, Any]) -> list[dict[str, str]]:
    """Return the local source arrangement for deterministic source fallback."""

    return [_copy_part(part) for part in protected_atom_plan(block)["parts"]]


def protected_atom_ids(block: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(str(atom["atom_id"]) for atom in protected_atom_plan(block)["atoms"])


def protected_atom_subplan(
    block: Mapping[str, Any],
    *,
    block_id: str,
    parts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Bind a split translation unit to a subset of one canonical atom plan."""

    source_plan = protected_atom_plan(block)
    atom_ids = _part_atom_ids(parts)
    atoms_by_id = {
        str(atom["atom_id"]): atom for atom in source_plan["atoms"]
    }
    if len(atom_ids) != len(set(atom_ids)) or set(atom_ids) - set(atoms_by_id):
        raise ProtectedAtomError(
            "translation_atom_plan_invalid",
            "split atom plan has invalid atom coverage",
        )
    return {
        "schema_version": PROTECTED_ATOM_PLAN_SCHEMA,
        "block_id": block_id,
        "parts": [_copy_part(part) for part in parts],
        "atoms": [
            _copy_atom(atoms_by_id[atom_id]) for atom_id in atom_ids
        ],
    }


def protected_atom_part_groups(
    block: Mapping[str, Any], *, max_bytes: int
) -> tuple[tuple[tuple[dict[str, Any], ...], ...], ...]:
    """Split only text parts after atom planning; all atoms stay indivisible."""

    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 64:
        raise ProtectedAtomError(
            "translation_unit_invalid", "translation max_bytes is too small"
        )
    plan = protected_atom_plan(block)
    groups = _list_part_groups(plan["parts"]) if str(block.get("kind")) == "list" else (plan["parts"],)
    return tuple(
        tuple(tuple(part for part in chunk) for chunk in _split_parts(group, max_bytes=max_bytes))
        for group in groups
    )


def assemble_protected_translation(
    block: Mapping[str, Any],
    parts: Any,
) -> tuple[str, list[dict[str, Any]]]:
    """Validate exact atom coverage and locally assemble immutable payloads."""

    plan = protected_atom_plan(block)
    expected = {str(atom["atom_id"]): atom for atom in plan["atoms"]}
    normalized = _result_parts(parts)
    seen = _part_atom_ids(normalized)
    unknown = sorted(set(seen) - set(expected))
    duplicate = sorted(atom_id for atom_id, count in Counter(seen).items() if count > 1)
    missing = sorted(set(expected) - set(seen))
    if unknown or duplicate or missing:
        category = (
            "unknown" if unknown else "duplicate" if duplicate else "missing"
        )
        raise ProtectedAtomError(
            f"translation_atom_{category}",
            f"translation atom coverage is invalid for {plan['block_id']}",
            {
                "unknown_atom_ids": unknown,
                "duplicate_atom_ids": duplicate,
                "missing_atom_ids": missing,
            },
        )
    _validate_part_kinds(normalized, expected)
    source_lexical_characters = _text_part_lexical_character_count(plan["parts"])
    translated_lexical_characters = _text_part_lexical_character_count(normalized)
    if source_lexical_characters and not translated_lexical_characters:
        raise ProtectedAtomError(
            "translation_coverage_invalid",
            f"translation omitted all meaningful text for {plan['block_id']}",
            {
                "source_lexical_characters": source_lexical_characters,
                "translated_lexical_characters": translated_lexical_characters,
            },
        )
    rendered = _render_parts(normalized, expected)
    if not rendered.strip():
        raise ProtectedAtomError(
            "translation_coverage_invalid",
            f"translation text is empty for {plan['block_id']}",
        )
    return rendered, normalized


def assemble_model_protected_translation(
    block: Mapping[str, Any],
    parts: Any,
) -> tuple[str, list[dict[str, Any]]]:
    """Assemble model text while restoring only unambiguous missing atom slots.

    Some providers preserve every translated text segment but omit the opaque
    atom entries between them.  When the top-level text-slot count is still an
    exact match, restore the caller-owned source arrangement locally.  Any
    unknown/duplicate atom or changed text-slot cardinality remains invalid.
    """

    try:
        return assemble_protected_translation(block, parts)
    except ProtectedAtomError as exc:
        if exc.code == "translation_atom_unknown":
            repaired = _repair_unambiguous_atom_ids(block, parts, exc)
            return assemble_protected_translation(block, repaired)
        if exc.code != "translation_atom_missing":
            raise
        original_error = exc

    plan = protected_atom_plan(block)
    normalized = _result_parts(parts)
    expected_ids = {
        str(atom["atom_id"]) for atom in plan["atoms"]
    }
    actual_ids = _part_atom_ids(normalized)
    if (
        set(actual_ids) - expected_ids
        or len(actual_ids) != len(set(actual_ids))
    ):
        raise original_error

    source_text_parts = [
        part for part in plan["parts"] if part["kind"] == "text"
    ]
    translated_text_parts = [
        part for part in normalized if part["kind"] == "text"
    ]
    if len(source_text_parts) != len(translated_text_parts):
        raise original_error

    translated_links = {
        str(part["atom_id"]): part
        for part in normalized
        if part["kind"] == "link"
    }
    text_index = 0
    restored: list[dict[str, Any]] = []
    for source_part in plan["parts"]:
        if source_part["kind"] == "text":
            restored.append(_copy_part(translated_text_parts[text_index]))
            text_index += 1
        elif source_part["kind"] == "link":
            restored.append(
                _copy_part(
                    translated_links.get(
                        str(source_part["atom_id"]), source_part
                    )
                )
            )
        else:
            restored.append(_copy_part(source_part))
    return assemble_protected_translation(block, restored)


def _repair_unambiguous_atom_ids(
    block: Mapping[str, Any],
    parts: Any,
    original_error: ProtectedAtomError,
) -> list[dict[str, Any]]:
    """Repair a model-corrupted atom prefix only when its ordinal is unique."""

    plan = protected_atom_plan(block)
    normalized = _result_parts(parts)
    expected_ids = {str(atom["atom_id"]) for atom in plan["atoms"]}
    actual_ids = _part_atom_ids(normalized)
    missing = expected_ids - set(actual_ids)
    unknown = set(actual_ids) - expected_ids
    if len(missing) != len(unknown):
        raise original_error

    expected_by_suffix: dict[str, list[str]] = {}
    for atom_id in missing:
        suffix = _atom_ordinal_suffix(atom_id)
        if suffix is not None:
            expected_by_suffix.setdefault(suffix, []).append(atom_id)

    replacements: dict[str, str] = {}
    for atom_id in unknown:
        suffix = _atom_ordinal_suffix(atom_id)
        candidates = expected_by_suffix.get(suffix or "", ())
        if len(candidates) != 1:
            raise original_error
        replacements[atom_id] = candidates[0]
    if len(set(replacements.values())) != len(replacements):
        raise original_error

    repaired: list[dict[str, Any]] = []
    for part in normalized:
        copied = _copy_part(part)
        if copied["kind"] in {"atom", "link"}:
            atom_id = str(copied["atom_id"])
            copied["atom_id"] = replacements.get(atom_id, atom_id)
        repaired.append(copied)
    return repaired


def _atom_ordinal_suffix(atom_id: str) -> str | None:
    match = re.search(r"\.atom-(\d{6})$", atom_id)
    return match.group(1) if match is not None else None


def protected_result_document(
    translations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Strip local assembly data before persisting the versioned model result."""

    return {
        "schema_version": PROTECTED_ATOM_RESULT_SCHEMA,
        "translations": [
            {
                "block_id": str(item["block_id"]),
                "parts": [dict(part) for part in item["parts"]],
            }
            for item in translations
        ],
    }


def _result_parts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ProtectedAtomError(
            "translation_atom_parts_invalid",
            "translation parts must be an array",
        )
    output: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            raise ProtectedAtomError(
                "translation_atom_parts_invalid",
                "translation part must be an object",
            )
        kind = raw.get("kind")
        if kind == "text" and set(raw) == {"kind", "text"}:
            text = raw.get("text")
            if not isinstance(text, str) or _has_unsafe_control(text):
                raise ProtectedAtomError(
                    "translation_atom_text_invalid",
                    "translation text part contains invalid content",
                )
            output.append({"kind": "text", "text": text})
        elif kind == "atom" and set(raw) == {"kind", "atom_id"}:
            atom_id = raw.get("atom_id")
            if not isinstance(atom_id, str) or not atom_id:
                raise ProtectedAtomError(
                    "translation_atom_parts_invalid",
                    "translation atom reference is invalid",
                )
            output.append({"kind": "atom", "atom_id": atom_id})
        elif kind == "link" and set(raw) == {"kind", "atom_id", "parts"}:
            atom_id = raw.get("atom_id")
            if not isinstance(atom_id, str) or not atom_id:
                raise ProtectedAtomError(
                    "translation_atom_parts_invalid",
                    "translation link atom reference is invalid",
                )
            output.append(
                {
                    "kind": "link",
                    "atom_id": atom_id,
                    "parts": _link_label_parts(raw.get("parts")),
                }
            )
        else:
            raise ProtectedAtomError(
                "translation_atom_parts_invalid",
                "translation part must be a closed text, atom, or link object",
            )
    return output


def _link_label_parts(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ProtectedAtomError(
            "translation_atom_parts_invalid",
            "translation link label parts must be an array",
        )
    output: list[dict[str, str]] = []
    for part in value:
        if (
            not isinstance(part, Mapping)
            or set(part) != {"kind", "text"}
            or part.get("kind") != "text"
            or not isinstance(part.get("text"), str)
            or _has_unsafe_control(str(part.get("text")))
        ):
            raise ProtectedAtomError(
                "translation_atom_parts_invalid",
                "translation link label must contain closed text parts",
            )
        output.append({"kind": "text", "text": str(part["text"])})
    return output


def _part_atom_ids(parts: Sequence[Mapping[str, Any]]) -> list[str]:
    atom_ids: list[str] = []
    for part in parts:
        kind = part.get("kind")
        if kind in {"atom", "link"}:
            atom_ids.append(str(part["atom_id"]))
    return atom_ids


def _text_part_lexical_character_count(
    parts: Sequence[Mapping[str, Any]],
) -> int:
    """Count human-readable letters without inspecting protected payloads."""

    count = 0
    for part in parts:
        kind = part.get("kind")
        if kind == "text":
            count += sum(
                character.isalpha()
                for character in str(part.get("text", ""))
            )
        elif kind == "link":
            count += _text_part_lexical_character_count(part.get("parts", ()))
    return count


def _validate_part_kinds(
    parts: Sequence[Mapping[str, Any]], expected: Mapping[str, Mapping[str, Any]]
) -> None:
    for part in parts:
        kind = str(part["kind"])
        if kind == "text":
            continue
        atom = expected[str(part["atom_id"])]
        expected_kind = str(atom["kind"])
        if (kind == "link") != (expected_kind == "link"):
            raise ProtectedAtomError(
                "translation_atom_kind_invalid",
                "translation changed the protected atom kind",
            )


def _render_parts(
    parts: Sequence[Mapping[str, Any]], expected: Mapping[str, Mapping[str, Any]]
) -> str:
    rendered: list[str] = []
    for part in parts:
        if part["kind"] == "text":
            rendered.append(str(part["text"]))
            continue
        atom = expected[str(part["atom_id"])]
        if part["kind"] == "atom":
            rendered.append(str(atom["payload"]))
            continue
        payload = atom["payload"]
        if not isinstance(payload, Mapping):  # pragma: no cover - plan invariant
            raise ProtectedAtomError(
                "translation_atom_plan_invalid", "link atom payload is invalid"
            )
        label = "".join(str(item["text"]) for item in part["parts"])
        source_label = str(payload["source_label"])
        if label == source_label:
            rendered.append(str(payload["source_markdown"]))
        else:
            rendered.append(f"[{_escape_link_label(label)}]{payload['suffix']}")
    return "".join(rendered)


def _escape_link_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _list_part_groups(
    parts: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], ...]:
    groups: list[list[dict[str, Any]]] = [[]]
    for raw in parts:
        part = _copy_part(raw)
        if part["kind"] != "text" or "\n" not in str(part["text"]):
            groups[-1].append(part)
            continue
        pieces = str(part["text"]).split("\n")
        for index, piece in enumerate(pieces):
            if piece:
                groups[-1].append({"kind": "text", "text": piece})
            if index < len(pieces) - 1:
                groups.append([])
    return tuple(group for group in groups if group)


def _split_parts(
    parts: Sequence[Mapping[str, Any]], *, max_bytes: int
) -> tuple[list[dict[str, Any]], ...]:
    output: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for part in parts:
        pieces = (
            [{"kind": "text", "text": value} for value in _split_text(str(part["text"]), max_bytes=max_bytes)]
            if part["kind"] == "text"
            else [_copy_part(part)]
        )
        for piece in pieces:
            candidate = [*current, piece]
            if current and _part_size(candidate) > max_bytes:
                output.append(current)
                current = [piece]
            else:
                current = candidate
    if current:
        output.append(current)
    return tuple(output)


def _split_text(value: str, *, max_bytes: int) -> tuple[str, ...]:
    if not value or len(value.encode("utf-8")) <= max_bytes:
        return (value,) if value else ()
    pieces = re.findall(r"\S+(?:\s+|$)", value)
    output: list[str] = []
    current = ""
    for piece in pieces:
        if len(piece.encode("utf-8")) > max_bytes:
            raise ProtectedAtomError(
                "translation_text_exceeds_input_budget",
                "one text token exceeds the translation unit budget",
            )
        if current and len((current + piece).encode("utf-8")) > max_bytes:
            output.append(current)
            current = piece
        else:
            current += piece
    if current:
        output.append(current)
    return tuple(output)


def _part_size(parts: Sequence[Mapping[str, Any]]) -> int:
    return len(json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _copy_part(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    if result.get("kind") == "link":
        result["parts"] = [_copy_part(item) for item in result["parts"]]
    return result


def _copy_atom(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    if isinstance(result.get("payload"), Mapping):
        result["payload"] = dict(result["payload"])
    return result


def _copied_plan(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {"schema_version", "block_id", "parts", "atoms"}
    if set(value) != required or value.get("schema_version") != PROTECTED_ATOM_PLAN_SCHEMA:
        raise ProtectedAtomError(
            "translation_atom_plan_invalid", "protected atom plan is invalid"
        )
    if not isinstance(value.get("block_id"), str) or not value["block_id"]:
        raise ProtectedAtomError(
            "translation_atom_plan_invalid", "protected atom plan ID is invalid"
        )
    atoms = value.get("atoms")
    if not isinstance(atoms, Sequence) or isinstance(atoms, (str, bytes)):
        raise ProtectedAtomError(
            "translation_atom_plan_invalid", "protected atom plan atoms are invalid"
        )
    copied_atoms = [_copy_atom(atom) for atom in atoms if isinstance(atom, Mapping)]
    if len(copied_atoms) != len(atoms) or any(
        set(atom) != {"atom_id", "kind", "payload"}
        or not isinstance(atom["atom_id"], str)
        or not atom["atom_id"]
        or not isinstance(atom["kind"], str)
        for atom in copied_atoms
    ):
        raise ProtectedAtomError(
            "translation_atom_plan_invalid", "protected atom entry is invalid"
        )
    parts = _result_parts(value.get("parts"))
    expected = {str(atom["atom_id"]): atom for atom in copied_atoms}
    if len(expected) != len(copied_atoms):
        raise ProtectedAtomError(
            "translation_atom_plan_invalid", "protected atom IDs are duplicated"
        )
    seen = _part_atom_ids(parts)
    if set(seen) != set(expected) or len(seen) != len(expected):
        raise ProtectedAtomError(
            "translation_atom_plan_invalid", "protected atom plan coverage is invalid"
        )
    _validate_part_kinds(parts, expected)
    return {
        "schema_version": PROTECTED_ATOM_PLAN_SCHEMA,
        "block_id": str(value["block_id"]),
        "parts": parts,
        "atoms": copied_atoms,
    }


def _protected_spans(
    text: str, block: Mapping[str, Any]
) -> tuple[tuple[int, int, str], ...]:
    if str(block.get("kind")) == "code":
        return ((0, len(text), "code"),) if text else ()
    candidates = [
        *(span[:2] + ("citation_group",) for span in _citation_group_spans(text)),
        *(span[:2] + ("formula",) for span in _markdown_math_spans(text)),
        *(span[:2] + ("code",) for span in _markdown_code_spans(text)),
        *(
            (
                start,
                end,
                (
                    "citation_link"
                    if re.fullmatch(r"#bib\.bib[1-9][0-9]*", target)
                    else (
                        "link_immutable"
                        if _markdown_math_spans(label)
                        or _markdown_code_spans(label)
                        else "link"
                    )
                ),
            )
            for start, end, label, target, _target_start, _target_end in _markdown_link_details(
                text, normalize=False
            )
        ),
        *_bibliography_label_spans(text, block),
    ]
    # Larger spans own nested identities. For equal starts the category order
    # above keeps citation groups ahead of their internal links.
    candidates.sort(key=lambda value: (value[0], -(value[1] - value[0])))
    selected: list[tuple[int, int, str]] = []
    for candidate in candidates:
        start, end, _kind = candidate
        if any(start < other_end and other_start < end for other_start, other_end, _ in selected):
            continue
        selected.append(candidate)
    return tuple(selected)


def _citation_group_spans(text: str) -> tuple[tuple[int, int], ...]:
    value = _normalize_markdown_text(_without_markdown_math(text))
    matches = tuple(
        match
        for match in _markdown_link_details(value, normalize=False)
        if re.fullmatch(r"#bib\.bib[1-9][0-9]*", match[3])
    )
    spans: list[tuple[int, int]] = []
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
        start, end = first[0], last[1]
        bracketed = (
            start > 0
            and value[start - 1] == "["
            and end < len(value)
            and value[end] == "]"
        )
        if bracketed:
            spans.append((start - 1, end + 1))
        elif last is not first and all(
            match[2].strip().isdigit() for match in matches[index:next_index]
        ):
            spans.append((start, end))
        index = next_index
    return tuple(spans)


def _markdown_code_spans(text: str) -> tuple[tuple[int, int], ...]:
    spans: list[tuple[int, int]] = []
    index = 0
    while index < len(text):
        if text[index] != "`" or (index and text[index - 1] == "\\"):
            index += 1
            continue
        end_of_run = index
        while end_of_run < len(text) and text[end_of_run] == "`":
            end_of_run += 1
        delimiter = text[index:end_of_run]
        closing = text.find(delimiter, end_of_run)
        if closing < 0:
            index = end_of_run
            continue
        spans.append((index, closing + len(delimiter)))
        index = closing + len(delimiter)
    return tuple(spans)


def _bibliography_label_spans(
    text: str, block: Mapping[str, Any]
) -> tuple[tuple[int, int, str], ...]:
    try:
        label = _bibliography_entry_label(block)
    except TranslationSourceError as exc:
        raise ProtectedAtomError(exc.code, str(exc), exc.details) from exc
    if not label:
        return ()
    match = re.match(rf"\s*{re.escape(label)}", text)
    if match is None:
        raise ProtectedAtomError(
            "translation_atom_plan_invalid",
            "bibliography label is absent from the translation surface",
        )
    return ((match.start() + len(match.group(0)) - len(label), match.end(), "bibliography_label"),)


def _translation_surface(block: Mapping[str, Any]) -> str:
    payload = block.get("payload")
    if not isinstance(payload, Mapping):
        raise ProtectedAtomError(
            "source_block_invalid", "source block payload must be an object"
        )
    kind = str(block.get("kind"))
    if kind in {"paragraph", "source_note"}:
        value = _compact_inline_text(payload)
    elif kind == "list":
        raw_items = payload.get("items")
        if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
            raise ProtectedAtomError(
                "source_block_invalid", "list payload items are invalid"
            )
        value = "\n".join(
            _compact_inline_text(item)
            for item in raw_items
            if isinstance(item, Mapping)
        )
    else:
        try:
            value = block_text(block)
        except TranslationSourceError as exc:
            raise ProtectedAtomError(exc.code, str(exc), exc.details) from exc
    return _normalize_markdown_text(value)


def _block_id(block: Mapping[str, Any]) -> str:
    value = block.get("block_id")
    if not isinstance(value, str) or not value:
        raise ProtectedAtomError(
            "source_block_invalid", "source block ID must be a non-empty string"
        )
    return value


def _has_unsafe_control(value: str) -> bool:
    return any(
        ord(character) < 32 and character not in {"\n", "\r", "\t"}
        for character in value
    )


__all__ = [
    "PROTECTED_ATOM_PLAN_SCHEMA",
    "PROTECTED_ATOM_RESULT_SCHEMA",
    "TEXT_SLOT_PLAN_SCHEMA",
    "TEXT_SLOT_RESULT_SCHEMA",
    "ProtectedAtomError",
    "assemble_model_protected_translation",
    "assemble_protected_translation",
    "assemble_text_slot_translation",
    "protected_atom_ids",
    "protected_atom_part_groups",
    "protected_atom_plan",
    "protected_atom_subplan",
    "protected_prompt_block",
    "protected_result_document",
    "source_protected_parts",
    "text_slot_ids",
    "text_slot_plan",
    "text_slot_prompt_block",
    "text_slot_values_from_parts",
]
