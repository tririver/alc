"""Validation for model-authored Companion Markdown."""

from __future__ import annotations

import re
from collections.abc import Sequence

from markdown_it import MarkdownIt
from markdown_it.rules_inline import StateInline
from markdown_it.token import Token


_CITATION = re.compile(r"\[@([A-Za-z0-9][A-Za-z0-9._:-]*)\]")


class RichTextError(ValueError):
    """Companion Markdown is invalid."""


def parse_markdown(value: str) -> tuple[Token, ...]:
    if not isinstance(value, str) or not value.strip():
        raise RichTextError("learning-unit markdown must be a non-empty string")
    _validate_display_math(value)
    tokens = tuple(_parser().parse(value))
    _reject_raw_html(tokens)
    return tokens


def citation_ids(value: str) -> tuple[str, ...]:
    return citation_ids_from_tokens(parse_markdown(value))


def citation_ids_from_tokens(tokens: Sequence[Token]) -> tuple[str, ...]:
    values: list[str] = []
    for token in tokens:
        values.extend(
            child.content
            for child in token.children or ()
            if child.type == "alc_citation"
        )
    return tuple(values)


def validate_rich_markdown(
    markdown: str,
    *,
    allowed_evidence_ids: Sequence[str] | None = None,
) -> tuple[str, ...]:
    values = citation_ids(markdown)
    if allowed_evidence_ids is not None:
        allowed = set(allowed_evidence_ids)
        try:
            unknown = next(item for item in values if item not in allowed)
        except StopIteration:
            pass
        else:
            raise RichTextError(
                f"citation is not in bibliography: {unknown}"
            )
    return values


def canonicalize_display_math(value: str) -> str:
    """Put unambiguous whole-line ``$$...$$`` math into canonical blocks."""

    if not isinstance(value, str):
        raise RichTextError("learning-unit markdown must be a string")
    lines = value.split("\n")
    code_lines = _code_line_numbers(value)
    output: list[str] = []
    for line_number, line in enumerate(lines):
        if line_number in code_lines:
            output.append(line)
            continue
        visible = _outside_code_spans(line)
        positions = _double_dollar_positions(visible)
        stripped = line.strip()
        if (
            len(positions) == 2
            and stripped.startswith("$$")
            and stripped.endswith("$$")
            and not stripped[2:-2].strip().startswith("$$")
        ):
            body = stripped[2:-2].strip()
            if body and "$$" not in _outside_code_spans(body):
                indent = line[: len(line) - len(line.lstrip())]
                output.extend((indent + "$$", indent + body, indent + "$$"))
                continue
        output.append(line)
    normalized = "\n".join(output)
    _validate_display_math(normalized)
    return normalized


def _parser() -> MarkdownIt:
    parser = MarkdownIt("commonmark", {"html": True})
    parser.inline.ruler.before("text", "alc_citation", _citation)
    return parser


def _validate_display_math(value: str) -> None:
    code_lines = _code_line_numbers(value)
    display_open = False
    for line_number, line in enumerate(value.split("\n")):
        if line_number in code_lines:
            continue
        visible = _outside_code_spans(line)
        positions = _double_dollar_positions(visible)
        if not positions:
            continue
        if visible.strip() != "$$" or len(positions) != 1:
            raise RichTextError(
                "display-math $$ delimiters must occupy separate lines"
            )
        display_open = not display_open
    if display_open:
        raise RichTextError("display-math $$ delimiters are unbalanced")


def _code_line_numbers(value: str) -> set[int]:
    lines: set[int] = set()
    for token in _parser().parse(value):
        if token.type not in {"fence", "code_block"} or token.map is None:
            continue
        lines.update(range(token.map[0], token.map[1]))
    return lines


def _outside_code_spans(line: str) -> str:
    output = list(line)
    position = 0
    while position < len(line):
        if line[position] != "`":
            position += 1
            continue
        run_end = position
        while run_end < len(line) and line[run_end] == "`":
            run_end += 1
        run_length = run_end - position
        cursor = run_end
        closing = -1
        while cursor < len(line):
            if line[cursor] != "`":
                cursor += 1
                continue
            close_end = cursor
            while close_end < len(line) and line[close_end] == "`":
                close_end += 1
            if close_end - cursor == run_length:
                closing = close_end
                break
            cursor = close_end
        if closing < 0:
            position = run_end
            continue
        output[position:closing] = " " * (closing - position)
        position = closing
    return "".join(output)


def _double_dollar_positions(value: str) -> tuple[int, ...]:
    positions: list[int] = []
    index = 0
    while index + 1 < len(value):
        if value[index : index + 2] != "$$":
            index += 1
            continue
        slashes = 0
        cursor = index - 1
        while cursor >= 0 and value[cursor] == "\\":
            slashes += 1
            cursor -= 1
        if slashes % 2 == 0:
            positions.append(index)
        index += 2
    return tuple(positions)


def _citation(state: StateInline, silent: bool) -> bool:
    match = _CITATION.match(state.src, state.pos)
    if match is None:
        return False
    if not silent:
        token = state.push("alc_citation", "", 0)
        token.content = match.group(1)
    state.pos = match.end()
    return True


def _reject_raw_html(tokens: Sequence[Token]) -> None:
    for token in tokens:
        if token.type == "html_block":
            raise RichTextError(
                "raw HTML is not permitted in learning-unit markdown"
            )
        if any(
            child.type == "html_inline" for child in token.children or ()
        ):
            raise RichTextError(
                "raw HTML is not permitted in learning-unit markdown"
            )


__all__ = [
    "RichTextError",
    "canonicalize_display_math",
    "citation_ids",
    "citation_ids_from_tokens",
    "parse_markdown",
    "validate_rich_markdown",
]
