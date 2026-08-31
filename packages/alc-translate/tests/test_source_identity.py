from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest
import alc_translate.source as source_module

from ac_document import (
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
from alc_translate import TranslationSource

from alc_translate.source import (
    TranslationSourceError,
    formula_identity_diagnostics,
    prompt_block,
    source_blocks,
    source_identity,
    validate_translation_text,
)


def _paragraph_block() -> dict[str, object]:
    return {
        "block_id": "block-inline",
        "kind": "paragraph",
        "payload": {
            "text": r"Use $a$ before $\Psi^\dagger$ and read notes.",
            "inline_spans": [
                {
                    "kind": "text",
                    "start": 0,
                    "end": 4,
                    "text": "Use ",
                },
                {
                    "kind": "math",
                    "start": 4,
                    "end": 7,
                    "text": "$a$",
                    "tex": "a",
                    "source": "$a$",
                },
                {
                    "kind": "text",
                    "start": 7,
                    "end": 15,
                    "text": " before ",
                },
                {
                    "kind": "math",
                    "start": 15,
                    "end": 29,
                    "text": r"$\Psi^\dagger$",
                    "tex": r"\Psi^\dagger",
                    "source": r"$\Psi^\dagger$",
                },
                {
                    "kind": "text",
                    "start": 29,
                    "end": 39,
                    "text": " and read ",
                },
                {
                    "kind": "link",
                    "start": 39,
                    "end": 44,
                    "text": "notes",
                    "target": "https://example.test/notes",
                },
                {
                    "kind": "text",
                    "start": 44,
                    "end": 45,
                    "text": ".",
                },
            ],
        },
    }


def test_source_identity_uses_current_inline_spans() -> None:
    identity = source_identity(_paragraph_block())

    assert identity["equations"] == ["a", r"\Psi^\dagger"]
    assert identity["link_targets"] == ["https://example.test/notes"]

    prompted = prompt_block(_paragraph_block())
    assert prompted["payload"] == {
        "text": r"Use $a$ before $\Psi^\dagger$ and read "
        "[notes](https://example.test/notes)."
    }
    assert "inline_spans" not in str(prompted["payload"])


def test_nested_old_tex_math_shifts_are_preserved_as_one_formula() -> None:
    tex = (
        r"\langle\Psi^{-}|M|\Psi^{-}\rangle>"
        r"\mbox{$\textstyle\frac{1}{2}$}"
    )
    block = _math_paragraph("nested-math-shift", tex)

    prompted = prompt_block(block)
    assert prompted["payload"]["text"] == rf"\({tex}\)"
    validate_translation_text(rf"当 \({tex}\) 时成立。", block)
    # Accept already-produced translations that used dollar delimiters around
    # the exact old-style TeX payload.
    validate_translation_text(rf"当 ${tex}$ 时成立。", block)

    with pytest.raises(
        TranslationSourceError,
        match="changed formula occurrences",
    ):
        validate_translation_text(
            rf"当 $\langle\Psi^{{-}}|M|\Psi^{{-}}\rangle>"
            r"\mbox{$\textstyle\frac{2}{3}$}$ 时成立。",
            block,
        )


def test_formula_occurrences_and_links_can_be_reordered_exactly() -> None:
    validate_translation_text(
        r"先看 $\Psi^\dagger$，再看 $a$；"
        r"[注释](https://example.test/notes)。",
        _paragraph_block(),
    )


def test_undelimited_nested_formula_text_is_not_double_counted() -> None:
    block = {
        "block_id": "block-nested-html-math",
        "kind": "paragraph",
        "payload": {
            "text": r"H, {\cal O}(H), H",
            "inline_spans": [
                {"kind": "math", "tex": "H"},
                {"kind": "text", "text": ", "},
                {"kind": "math", "tex": r"{\cal O}(H)"},
                {"kind": "text", "text": ", "},
                {"kind": "math", "tex": "H"},
            ],
        },
    }

    validate_translation_text(r"质量为 H、远大于 {\cal O}(H)，或约为 H。", block)
    with pytest.raises(
        TranslationSourceError,
        match="changed formula occurrences",
    ):
        validate_translation_text(
            r"质量为 H、远大于 {\cal O}(H)，约为 H，另有 H。", block
        )


@pytest.mark.parametrize(
    "text",
    [
        r"先看 $\\Psi^\dagger$，再看 $a$；https://example.test/notes",
        r"先看 $\Phi^\dagger$，再看 $a$；https://example.test/notes",
        r"只看 $a$；https://example.test/notes",
        r"看 $a$、$\Psi^\dagger$ 和 $b$；https://example.test/notes",
        r"看 $a$、$a$、$\Psi^\dagger$；https://example.test/notes",
    ],
    ids=[
        "overescaped",
        "substituted",
        "missing",
        "extra-different",
        "extra-duplicate",
    ],
)
def test_changed_formula_multiset_is_rejected(text: str) -> None:
    with pytest.raises(
        TranslationSourceError,
        match="changed formula occurrences",
    ):
        validate_translation_text(text, _paragraph_block())


def test_formula_failure_exposes_missing_and_added_tex_diagnostics() -> None:
    with pytest.raises(TranslationSourceError) as raised:
        validate_translation_text(
            r"看 $b$；https://example.test/notes", _paragraph_block()
        )

    diagnostics = raised.value.details["formula_diagnostics"]
    assert {item["code"] for item in diagnostics} == {
        "formula_missing",
        "formula_added",
    }
    assert {item["tex"] for item in diagnostics} == {
        "a",
        r"\Psi^\dagger",
        "b",
    }
    assert all(item["source_block_id"] == "block-inline" for item in diagnostics)
    assert all(
        item["translation_block_id"] == "block-inline" for item in diagnostics
    )
    assert all(item["source_neighbor_block_ids"] == [] for item in diagnostics)
    assert all(item["translation_neighbor_block_ids"] == [] for item in diagnostics)


def test_formula_diagnostics_identify_cross_block_moves_with_neighbors() -> None:
    source_blocks = (
        _math_paragraph("first", "a"),
        _plain_paragraph("middle"),
        _plain_paragraph("last"),
    )
    diagnostics = formula_identity_diagnostics(
        source_blocks,
        (
            {"block_id": "first", "text": "翻译。"},
            {"block_id": "middle", "text": "翻译 $a$。"},
            {"block_id": "last", "text": "翻译。"},
        ),
    )

    assert diagnostics == (
        {
            "code": "formula_moved",
            "tex": "a",
            "occurrence_count": 1,
            "source_block_id": "first",
            "translation_block_id": "middle",
            "source_neighbor_block_ids": ["middle"],
            "translation_neighbor_block_ids": ["first", "last"],
        },
    )


def _math_paragraph(block_id: str, tex: str) -> dict[str, object]:
    return {
        "block_id": block_id,
        "kind": "paragraph",
        "payload": {
            "text": f"${tex}$",
            "inline_spans": [
                {
                    "kind": "math",
                    "start": 0,
                    "end": len(tex) + 2,
                    "text": f"${tex}$",
                    "tex": tex,
                    "source": f"${tex}$",
                }
            ],
        },
    }


def _plain_paragraph(block_id: str) -> dict[str, object]:
    return {
        "block_id": block_id,
        "kind": "paragraph",
        "payload": {"text": "plain", "inline_spans": []},
    }


@pytest.mark.parametrize(
    "text",
    [
        r"看 $a$ 和 $\Psi^\dagger$，但没有链接。",
        r"看 $a$ 和 $\Psi^\dagger$；"
        r"[注释](https://example.test/replaced)。",
        r"看 $a$ 和 $\Psi^\dagger$；"
        r"[注释](https://example.test/notes) "
        r"[额外](https://example.test/extra)。",
        r"看 $a$ 和 $\Psi^\dagger$；"
        r"https://example.test/notes https://example.test/notes",
    ],
    ids=["missing", "replaced", "extra-target", "extra-duplicate"],
)
def test_changed_link_multiset_is_rejected(text: str) -> None:
    with pytest.raises(
        TranslationSourceError,
        match="changed link occurrences",
    ):
        validate_translation_text(text, _paragraph_block())


def test_link_validation_ignores_markdown_shapes_inside_inline_math() -> None:
    tex = r"\left[p_\mu\right](p'-p)"
    block = {
        "block_id": "block-math-link-shape",
        "kind": "paragraph",
        "payload": {
            "text": f"${tex}$",
            "inline_spans": [
                {
                    "kind": "math",
                    "start": 0,
                    "end": len(tex) + 2,
                    "text": f"${tex}$",
                    "tex": tex,
                    "source": f"${tex}$",
                }
            ],
        },
    }

    assert source_identity(block)["link_targets"] == []
    validate_translation_text(f"${tex}$", block)
    with pytest.raises(
        TranslationSourceError,
        match="changed link occurrences",
    ):
        validate_translation_text(
            f"${tex}$ [extra](https://example.test/extra)",
            block,
        )


def test_list_identity_uses_each_items_inline_spans() -> None:
    block = {
        "block_id": "block-list",
        "kind": "list",
        "payload": {
            "items": [
                {
                    "text": "$x$",
                    "inline_spans": [
                        {
                            "kind": "math",
                            "start": 0,
                            "end": 3,
                            "text": "$x$",
                            "tex": "x",
                            "source": "$x$",
                        }
                    ],
                },
                {
                    "text": "reference",
                    "inline_spans": [
                        {
                            "kind": "link",
                            "start": 0,
                            "end": 9,
                            "text": "reference",
                            "target": "appendix.html",
                        }
                    ],
                },
            ]
        },
    }

    assert source_identity(block)["equations"] == ["x"]
    assert source_identity(block)["link_targets"] == ["appendix.html"]
    validate_translation_text("$x$ appendix.html", block)

    prompted = prompt_block(block)
    assert prompted["payload"] == {
        "ordered": False,
        "items": [
            {"text": "$x$"},
            {"text": "[reference](appendix.html)"},
        ],
    }
    assert "inline_spans" not in str(prompted["payload"])


def test_heading_identity_extracts_markdown_math_without_inline_spans() -> None:
    link_shaped_tex = r"\left[V\right](p)"
    block = {
        "block_id": "block-heading",
        "kind": "heading",
        "payload": {
            "text": (
                r"Representations of $G$, $\mathfrak g$, and "
                f"${link_shaped_tex}$"
            ),
            "level": 2,
        },
    }

    identity = source_identity(block)
    assert identity["equations"] == ["G", r"\mathfrak g", link_shaped_tex]
    assert identity["link_targets"] == []
    validate_translation_text(
        f"${link_shaped_tex}$、" r"$\mathfrak g$ 与 $G$ 的表示",
        block,
    )


def test_table_identity_extracts_markdown_math_and_links() -> None:
    block = {
        "block_id": "block-table",
        "kind": "table",
        "payload": {
            "headers": ["Operator", "[Reference](operators.html)"],
            "rows": [[r"$H$", "Hamiltonian"], [r"$P^\mu$", "momentum"]],
            "caption": r"Results for $E$ from [data](caption.html)",
        },
    }

    identity = source_identity(block)
    assert identity["equations"] == ["E", "H", r"P^\mu"]
    assert identity["link_targets"] == ["caption.html", "operators.html"]
    validate_translation_text(
        r"[数据](caption.html)给出 $E$。" "\n"
        r"$P^\mu$ | 动量" "\n"
        r"$H$ | [哈密顿量](operators.html)",
        block,
    )


def test_source_presentation_accessor_is_optional_only_when_metadata_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(source_module._ac_document, "source_presentation")

    assert source_module._source_presentation_or_none(
        SimpleNamespace(metadata={})
    ) is None
    with pytest.raises(
        TranslationSourceError,
        match="requires AC Document source-presentation support",
    ):
        source_module._source_presentation_or_none(
            SimpleNamespace(metadata={"source_presentation": {}})
        )

def test_figure_identity_uses_caption_without_exposing_asset_target() -> None:
    block = {
        "block_id": "block-figure",
        "ordinal": 4,
        "kind": "figure",
        "section_path": [],
        "payload": {
            "caption": r"Plot of $f(x)$ from [data](caption-data.html)",
            "alt_text": "private alt text",
            "asset_digest": "a" * 64,
            "target": "images/plot.png",
        },
    }

    prompted = prompt_block(block)
    assert prompted["source_identity"] == {
        "equations": ["f(x)"],
        "code_text": None,
        "link_targets": ["caption-data.html"],
    }
    assert "images/plot.png" not in str(prompted)
    validate_translation_text(
        r"[数据](caption-data.html)中的 $f(x)$ 图",
        block,
    )


def test_source_blocks_project_authoritative_figure_caption_math() -> None:
    source_bytes = b"<article><figure>Figure: Theta.</figure></article>"
    source = SourceArtifact(
        SourceFormat.HTML,
        hashlib.sha256(source_bytes).hexdigest(),
        len(source_bytes),
        "text/html",
        SourceOrigin(SourceOriginKind.REPOSITORY),
    )
    block = RichBlock(
        "block-figure-rich-caption",
        0,
        RichBlockKind.FIGURE,
        ("section-figure",),
        SourceLocator(
            SourceFormat.HTML,
            selector="#figure",
            source_id="figure",
        ),
        {
            "asset_digest": None,
            "alt_text": "",
            "caption": "Figure: Θ.",
            "target": "",
            "media_type": "",
            "logical_name": "",
            "size": 0,
        },
    )
    document = RichDocument(
        source,
        (block,),
        (
            RichSection(
                "section-figure",
                "Figure",
                1,
                0,
                ("section-figure",),
                0,
                1,
            ),
        ),
        metadata={
            "source_presentation": {
                "schema_version": "ac.document.source_presentation.v1",
                "blocks": [
                    {
                        "block_id": block.block_id,
                        "roles": [],
                        "fields": [
                            {
                                "field": "caption",
                                "item_index": None,
                                "row_index": None,
                                "column_index": None,
                                "text": "Figure: Θ.",
                                "inline_spans": [
                                    {
                                        "kind": "text",
                                        "start": 0,
                                        "end": 8,
                                        "text": "Figure: ",
                                    },
                                    {
                                        "kind": "math",
                                        "start": 8,
                                        "end": 9,
                                        "text": "Θ",
                                        "tex": r"\Theta",
                                        "source": r"\Theta",
                                    },
                                    {
                                        "kind": "text",
                                        "start": 9,
                                        "end": 10,
                                        "text": ".",
                                    },
                                ],
                                "marks": [],
                            }
                        ],
                    }
                ],
                "classifications": [],
                "figures": [],
                "captions": [
                    {
                        "block_id": block.block_id,
                        "kind": "figure",
                        "placement": "after_content",
                        "alignment": None,
                        "alignment_sources": [],
                    }
                ],
                "tables": [],
            }
        },
    )

    projected = source_blocks(TranslationSource(document))[0]

    assert projected["payload"]["caption"] == r"Figure: $\Theta$."
    assert source_identity(projected)["equations"] == [r"\Theta"]
    validate_translation_text(r"图：$\Theta$。", projected)
    with pytest.raises(
        TranslationSourceError,
        match="changed formula occurrences",
    ):
        validate_translation_text(r"图：Θ。", projected)
    with pytest.raises(
        TranslationSourceError,
        match="changed formula occurrences",
    ):
        validate_translation_text(r"图：\Theta。", projected)


def test_internal_bibliography_link_labels_are_source_authoritative() -> None:
    block = {
        "block_id": "block-numeric-citation",
        "kind": "paragraph",
        "payload": {
            "text": "Defined in [30].",
            "inline_spans": [
                {"kind": "text", "start": 0, "end": 12, "text": "Defined in ["},
                {
                    "kind": "link",
                    "start": 12,
                    "end": 14,
                    "text": "30",
                    "target": "#bib.bib30",
                },
                {"kind": "text", "start": 14, "end": 16, "text": "]."},
            ],
        },
    }

    validate_translation_text(r"定义见 [[30](#bib.bib30)]。", block)
    with pytest.raises(
        TranslationSourceError,
        match="changed internal bibliography citation groups",
    ):
        validate_translation_text(r"定义见 [30](#bib.bib30)。", block)
    with pytest.raises(
        TranslationSourceError,
        match="changed internal bibliography link labels",
    ):
        validate_translation_text(
            r"定义见 [Bond et al. 1997](#bib.bib30)。", block
        )

    author_label = {
        **block,
        "block_id": "block-author-citation",
        "payload": {
            "text": "Tejeda and Toalá [129] found this.",
            "inline_spans": [
                {
                    "kind": "link",
                    "start": 0,
                    "end": 23,
                    "text": "Tejeda and Toalá [129]",
                    "target": "#bib.bib129",
                },
                {"kind": "text", "start": 23, "end": 35, "text": " found this."},
            ],
        },
    }
    validate_translation_text(
        r"[Tejeda and Toalá [129]](#bib.bib129) 发现了这一点。",
        author_label,
    )
    with pytest.raises(
        TranslationSourceError,
        match="changed internal bibliography link labels",
    ):
        validate_translation_text(
            r"[Tejeda 和 Toalá [129]](#bib.bib129) 发现了这一点。",
            author_label,
        )

    external = {
        **block,
        "block_id": "block-external-label",
        "payload": {
            "text": "Read source.",
            "inline_spans": [
                {
                    "kind": "link",
                    "start": 0,
                    "end": 11,
                    "text": "Read source",
                    "target": "https://example.test/source",
                },
                {"kind": "text", "start": 11, "end": 12, "text": "."},
            ],
        },
    }
    validate_translation_text(
        r"[阅读来源](https://example.test/source)。", external
    )


def test_internal_bibliography_groups_and_entry_labels_are_authoritative() -> None:
    citation = {
        "block_id": "block-citation-group",
        "kind": "paragraph",
        "payload": {
            "text": "Compare [8, 12].",
            "inline_spans": [
                {"kind": "text", "start": 0, "end": 9, "text": "Compare ["},
                {
                    "kind": "link",
                    "start": 9,
                    "end": 10,
                    "text": "8",
                    "target": "#bib.bib8",
                },
                {"kind": "text", "start": 10, "end": 12, "text": ", "},
                {
                    "kind": "link",
                    "start": 12,
                    "end": 14,
                    "text": "12",
                    "target": "#bib.bib12",
                },
                {"kind": "text", "start": 14, "end": 16, "text": "]."},
            ],
        },
    }
    exact_group = r"比较 [[8](#bib.bib8), [12](#bib.bib12)]。"
    validate_translation_text(exact_group, citation)
    for changed in (
        r"比较 [8](#bib.bib8)；[12](#bib.bib12)。",
        r"比较（[8](#bib.bib8), [12](#bib.bib12)）。",
    ):
        with pytest.raises(
            TranslationSourceError,
            match="changed internal bibliography citation groups",
        ):
            validate_translation_text(changed, citation)

    narrative_authors = {
        "block_id": "block-narrative-authors",
        "kind": "paragraph",
        "payload": {
            "text": "Using Sowell et al. [127], Mukai et al. [92] found this.",
            "inline_spans": [
                {"kind": "text", "start": 0, "end": 6, "text": "Using "},
                {
                    "kind": "link",
                    "start": 6,
                    "end": 25,
                    "text": "Sowell et al. [127]",
                    "target": "#bib.bib129",
                },
                {"kind": "text", "start": 25, "end": 27, "text": ", "},
                {
                    "kind": "link",
                    "start": 27,
                    "end": 44,
                    "text": "Mukai et al. [92]",
                    "target": "#bib.bib6",
                },
                {
                    "kind": "text",
                    "start": 44,
                    "end": 56,
                    "text": " found this.",
                },
            ],
        },
    }
    validate_translation_text(
        "使用 [Sowell et al. [127]](#bib.bib129) 的 H-R 图，"
        "[Mukai et al. [92]](#bib.bib6) 得到结果。",
        narrative_authors,
    )

    bibliography = {
        "block_id": "block-bibliography-1",
        "kind": "list",
        "locator": {"source_id": "bib.bib1"},
        "payload": {
            "ordered": False,
            "items": [
                {
                    "text": "[1] Source reference.",
                    "inline_spans": [
                        {
                            "kind": "text",
                            "start": 0,
                            "end": 21,
                            "text": "[1] Source reference.",
                        }
                    ],
                }
            ],
        },
    }
    validate_translation_text("[1] 译文参考文献。", bibliography)
    validate_translation_text("- [1] 译文参考文献。", bibliography)

    shuffled_source_identity = {
        **bibliography,
        "block_id": "block-bibliography-shuffled-source-id",
        "locator": {"source_id": "bib.bib134"},
    }
    validate_translation_text("[1] 译文参考文献。", shuffled_source_identity)
    with pytest.raises(
        TranslationSourceError,
        match="changed bibliography entry label",
    ):
        validate_translation_text("译文参考文献。", bibliography)


def test_undelimited_inline_math_still_uses_exact_tex_identity() -> None:
    block = {
        "block_id": "block-html-math",
        "kind": "paragraph",
        "payload": {
            "text": r"\Psi",
            "inline_spans": [
                {
                    "kind": "math",
                    "start": 0,
                    "end": 4,
                    "text": r"\Psi",
                    "tex": r"\Psi",
                    "source": r"\Psi",
                }
            ],
        },
    }

    validate_translation_text(r"态 \Psi。", block)
    with pytest.raises(
        TranslationSourceError,
        match="changed formula occurrences",
    ):
        validate_translation_text(r"态 \\Psi。", block)


def test_adjacent_inline_math_spans_preserve_each_formula_identity() -> None:
    block = {
        "block_id": "block-adjacent-inline-math",
        "kind": "paragraph",
        "payload": {
            "text": "π1 Gruis",
            "inline_spans": [
                {
                    "kind": "math",
                    "start": 0,
                    "end": 1,
                    "text": "π",
                    "tex": r"\pi",
                    "source": "π",
                },
                {
                    "kind": "math",
                    "start": 1,
                    "end": 2,
                    "text": "1",
                    "tex": r"{}^{1}",
                    "source": "1",
                },
                {"kind": "text", "start": 2, "end": 8, "text": " Gruis"},
            ],
        },
    }

    validate_translation_text(r"巨星 $\pi$${}^{1}$ Gruis。", block)
    with pytest.raises(
        TranslationSourceError,
        match="changed formula occurrences",
    ):
        validate_translation_text(r"巨星 $\pi$ Gruis。", block)


@pytest.mark.parametrize(
    ("source_tex", "text"),
    [
        (r"x^2 + y^2 = z^2", r"x^2 + y^2 = z^2"),
        (r"x^2 + y^2 = z^2", r"$$x^2 + y^2 = z^2$$"),
        (r"x^2 + y^2 = z^2", r"x^2  + y^2 = z^2"),
        (r"\left[p_\mu\right](p'-p)", r"\left[p_\mu\right](p'-p)"),
    ],
)
def test_equation_translation_must_equal_source_tex(
    source_tex: str,
    text: str,
) -> None:
    block = {
        "block_id": "block-equation",
        "kind": "equation",
        "payload": {
            "tex": source_tex,
            "display": True,
            "label": "",
        },
    }

    if text == block["payload"]["tex"]:
        validate_translation_text(text, block)
    else:
        with pytest.raises(
            TranslationSourceError,
            match="changed equation text",
        ):
            validate_translation_text(text, block)
