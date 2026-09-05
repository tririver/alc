from __future__ import annotations

import random

import pytest
from alc_translate.atoms import (
    PROTECTED_ATOM_PLAN_SCHEMA,
    TEXT_SLOT_PLAN_SCHEMA,
    ProtectedAtomError,
    assemble_model_protected_translation,
    assemble_protected_translation,
    assemble_text_slot_translation,
    protected_atom_ids,
    protected_atom_part_groups,
    protected_atom_plan,
    protected_atom_subplan,
    protected_prompt_block,
    text_slot_ids,
    text_slot_plan,
    text_slot_prompt_block,
    text_slot_values_from_parts,
)


def _paragraph(text: str) -> dict[str, object]:
    return {
        "block_id": "block-1",
        "ordinal": 0,
        "kind": "paragraph",
        "section_path": [],
        "payload": {
            "text": text,
            "inline_spans": [{"kind": "text", "text": text}],
        },
    }


def _atom_ids(plan: dict[str, object]) -> list[str]:
    return [str(atom["atom_id"]) for atom in plan["atoms"]]  # type: ignore[index]


def test_prompt_hides_formula_link_and_url_payloads() -> None:
    block = _paragraph(
        r"Adjacent $\pi$${}^{1}$; [nested [label]](https://example.test/$x$(a))."
    )

    plan = protected_atom_plan(block)
    prompt = protected_prompt_block(block)

    assert [atom["kind"] for atom in plan["atoms"]] == [
        "formula",
        "formula",
        "link",
    ]
    assert prompt["content"] == {
        "schema_version": PROTECTED_ATOM_PLAN_SCHEMA,
        "parts": plan["parts"],
    }
    assert "https://example.test" not in repr(prompt)
    assert r"\pi" not in repr(prompt)
    assert "nested [label]" in repr(prompt)


def test_atoms_allow_natural_reordering_and_reassemble_source_payloads() -> None:
    block = _paragraph(r"Before $x$ and [the label](https://example.test/a).")
    plan = protected_atom_plan(block)
    first, second = _atom_ids(plan)

    assembled, parts = assemble_protected_translation(
        block,
        [
            {"kind": "text", "text": "译文先引用 "},
            {
                "kind": "link",
                "atom_id": second,
                "parts": [{"kind": "text", "text": "译文标签"}],
            },
            {"kind": "text", "text": "，再计算 "},
            {"kind": "atom", "atom_id": first},
            {"kind": "text", "text": "。"},
        ],
    )

    assert assembled == "译文先引用 [译文标签](https://example.test/a)，再计算 $x$。"
    assert [part["atom_id"] for part in parts if part["kind"] != "text"] == [
        second,
        first,
    ]


def test_text_slot_plan_keeps_atoms_input_only_and_output_ids_exact() -> None:
    block = _paragraph(r"Before $x$ and [the label](https://example.test/a).")

    plan = text_slot_plan(block)
    prompt = text_slot_prompt_block(block)

    assert plan["schema_version"] == TEXT_SLOT_PLAN_SCHEMA
    assert text_slot_ids(block) == (
        "block-1.text-000000",
        "block-1.text-000001",
        "block-1.text-000002",
        "block-1.text-000003",
    )
    assert prompt["content"] == {
        "schema_version": TEXT_SLOT_PLAN_SCHEMA,
        "parts": plan["parts"],
    }
    assert "https://example.test" not in repr(prompt)
    assert r"$x$" not in repr(prompt)


def test_text_slot_assembly_never_accepts_or_requires_model_atom_ids() -> None:
    block = _paragraph(r"Before $x$ and [the label](https://example.test/a).")
    slots = {
        slot_id: f"译文-{ordinal}"
        for ordinal, slot_id in enumerate(text_slot_ids(block))
    }

    rendered, parts = assemble_text_slot_translation(block, slots)

    assert "$x$" in rendered
    assert "https://example.test/a" in rendered
    assert [part["kind"] for part in parts] == [
        "text",
        "atom",
        "text",
        "link",
        "text",
    ]
    assert text_slot_values_from_parts(block, parts) == slots


def test_text_slot_assembly_rejects_missing_unknown_and_unsafe_slots() -> None:
    block = _paragraph("Before $x$ after.")
    first, second = text_slot_ids(block)

    with pytest.raises(ProtectedAtomError) as missing:
        assemble_text_slot_translation(block, {first: "之前"})
    assert missing.value.code == "translation_text_slots_invalid"
    assert missing.value.details["missing_text_slot_ids"] == [second]

    with pytest.raises(ProtectedAtomError) as unknown:
        assemble_text_slot_translation(
            block, {first: "之前", second: "之后", "unknown": "错误"}
        )
    assert unknown.value.code == "translation_text_slots_invalid"

    with pytest.raises(ProtectedAtomError) as unsafe:
        assemble_text_slot_translation(
            block, {first: "之前", second: "不安全\x00"}
        )
    assert unsafe.value.code == "translation_text_slot_invalid"


def test_text_slot_assembly_rejects_bibliography_shell_without_prose() -> None:
    block = {
        "block_id": "bibliography-empty-shell",
        "ordinal": 36,
        "kind": "list",
        "locator": {"source_id": "bib.bib36"},
        "payload": {
            "ordered": False,
            "items": [
                {
                    "text": (
                        "[36] A. Author. "
                        "[Paper title](https://doi.org/10.1000/example)."
                    )
                }
            ],
        },
    }
    slots = {slot_id: "" for slot_id in text_slot_ids(block)}

    with pytest.raises(ProtectedAtomError) as raised:
        assemble_text_slot_translation(block, slots)

    assert raised.value.code == "translation_coverage_invalid"
    assert raised.value.details["source_lexical_characters"] > 0
    assert raised.value.details["translated_lexical_characters"] == 0


def test_text_slot_assembly_allows_nonlexical_structure_only_source() -> None:
    block = _paragraph(r"$x$ 123.")
    slots = {slot_id: "" for slot_id in text_slot_ids(block)}

    rendered, _parts = assemble_text_slot_translation(block, slots)

    assert rendered == "$x$"


def test_model_assembly_restores_missing_atoms_when_text_slots_are_exact() -> None:
    block = _paragraph("Before $x$ and [the label](https://example.test/a).")
    plan = protected_atom_plan(block)
    translated_text = [
        {"kind": "text", "text": f"译:{part['text']}"}
        for part in plan["parts"]
        if part["kind"] == "text"
    ]

    rendered, parts = assemble_model_protected_translation(
        block, translated_text
    )

    assert "$x$" in rendered
    assert "[the label](https://example.test/a)" in rendered
    assert [part["kind"] for part in parts] == [
        part["kind"] for part in plan["parts"]
    ]


def test_model_assembly_does_not_guess_after_text_slots_are_merged() -> None:
    block = _paragraph("Before $x$ after.")

    with pytest.raises(ProtectedAtomError) as raised:
        assemble_model_protected_translation(
            block,
            [{"kind": "text", "text": "译文合并了公式两侧的文本。"}],
        )

    assert raised.value.code == "translation_atom_missing"


def test_model_assembly_repairs_one_unknown_atom_prefix_by_unique_ordinal() -> None:
    block = _paragraph("Before $x$ and $y$ after.")
    plan = protected_atom_plan(block)
    parts = [dict(part) for part in plan["parts"]]
    atom = next(part for part in parts if part["kind"] == "atom")
    atom["atom_id"] = "block-typo.atom-000000"

    rendered, repaired = assemble_model_protected_translation(block, parts)

    assert rendered == "Before $x$ and $y$ after."
    assert [
        part["atom_id"] for part in repaired if part["kind"] == "atom"
    ] == _atom_ids(plan)


def test_model_assembly_does_not_guess_an_unknown_atom_without_matching_ordinal() -> None:
    block = _paragraph("Before $x$ after.")

    with pytest.raises(ProtectedAtomError) as raised:
        assemble_model_protected_translation(
            block,
            [
                {"kind": "text", "text": "之前"},
                {"kind": "atom", "atom_id": "block-typo.atom-999999"},
                {"kind": "text", "text": "之后"},
            ],
        )

    assert raised.value.code == "translation_atom_unknown"


@pytest.mark.parametrize(
    ("parts", "code"),
    [
        ([{"kind": "text", "text": "missing"}], "translation_atom_missing"),
        (
            [
                {"kind": "atom", "atom_id": "block-1.atom-000000"},
                {"kind": "atom", "atom_id": "block-1.atom-000000"},
            ],
            "translation_atom_duplicate",
        ),
        (
            [
                {"kind": "atom", "atom_id": "untrusted.atom"},
                {"kind": "atom", "atom_id": "block-1.atom-000000"},
            ],
            "translation_atom_unknown",
        ),
    ],
)
def test_atom_coverage_rejects_missing_duplicate_and_unknown(
    parts: list[dict[str, str]], code: str
) -> None:
    with pytest.raises(ProtectedAtomError) as raised:
        assemble_protected_translation(_paragraph(r"Value $x$."), parts)

    assert raised.value.code == code


def test_citation_group_and_bibliography_label_are_one_caller_owned_atom() -> None:
    citation = _paragraph("Compare [[8](#bib.bib8), [12](#bib.bib12)].")
    bibliography = {
        "block_id": "bibliography-1",
        "ordinal": 1,
        "kind": "list",
        "locator": {"source_id": "bib.bib1"},
        "payload": {
            "ordered": False,
            "items": [
                {
                    "text": "[1] Author title.",
                    "inline_spans": [
                        {"kind": "text", "text": "[1] Author title."}
                    ],
                }
            ],
        },
    }

    citation_plan = protected_atom_plan(citation)
    bibliography_plan = protected_atom_plan(bibliography)

    assert citation_plan["atoms"] == [
        {
            "atom_id": "block-1.atom-000000",
            "kind": "citation_group",
            "payload": "[[8](#bib.bib8), [12](#bib.bib12)]",
        }
    ]
    assert bibliography_plan["atoms"][0]["kind"] == "bibliography_label"
    assert bibliography_plan["atoms"][0]["payload"] == "[1]"


@pytest.mark.parametrize(
    "label",
    [
        "Baldwin et al. (1981)",
        "Bruzual and Charlot (2003)",
        "Rupke et al. (2005b)",
        "Example Collaboration (n.d.)",
        "Example Collaboration (in press)",
        "Example Collaboration (forthcoming)",
    ],
)
def test_author_year_bibliography_label_is_caller_owned(label: str) -> None:
    block = {
        "block_id": "bibliography-author-year",
        "ordinal": 1,
        "kind": "list",
        "locator": {"source_id": "bib.bib32"},
        "payload": {
            "ordered": False,
            "items": [{"text": f"{label} Author and title."}],
        },
    }

    plan = protected_atom_plan(block)

    assert plan["atoms"][0]["kind"] == "bibliography_label"
    assert plan["atoms"][0]["payload"] == label
    assert plan["parts"][0] == {
        "kind": "atom",
        "atom_id": "bibliography-author-year.atom-000000",
    }


def test_control_characters_in_model_text_are_rejected_before_assembly() -> None:
    with pytest.raises(ProtectedAtomError) as raised:
        assemble_protected_translation(
            _paragraph("plain source"),
            [{"kind": "text", "text": "unsafe\x00translation"}],
        )

    assert raised.value.code == "translation_atom_text_invalid"


def test_deterministic_atom_fuzz_round_trips_adjacent_and_nested_identities() -> None:
    randomizer = random.Random(20260903)
    fragments = (
        " prose ",
        r"$x$${}^{2}$",
        r"[nested [label]](https://example.test/$value$(a))",
        "[[8](#bib.bib8), [12](#bib.bib12)]",
        "`machine_code()`",
    )
    for _ in range(128):
        source = "".join(randomizer.choice(fragments) for _ in range(9))
        block = _paragraph(source)
        plan = protected_atom_plan(block)
        rendered, _parts = assemble_protected_translation(
            block, plan["parts"]
        )

        assert rendered == source


def test_atom_first_split_keeps_long_code_and_citation_payloads_local() -> None:
    code = "machine_" * 80
    citation = "[[8](#bib.bib8), [12](#bib.bib12)]"
    source = f"Start {'prose ' * 30}`{code}` then {citation} end."
    block = _paragraph(source)

    groups = protected_atom_part_groups(block, max_bytes=64)
    source_atom_ids = protected_atom_ids(block)
    split_atom_ids = []
    reconstructed = []
    for ordinal, parts in enumerate(groups[0]):
        unit_id = f"block-1.translation-unit-{ordinal:06d}"
        plan = protected_atom_subplan(block, block_id=unit_id, parts=parts)
        unit = {
            "block_id": unit_id,
            "kind": "translation_unit",
            "payload": {"text": "local"},
            "protected_atom_plan": plan,
        }
        prompt = protected_prompt_block(unit)
        rendered, _ = assemble_protected_translation(unit, plan["parts"])
        reconstructed.append(rendered)
        split_atom_ids.extend(protected_atom_ids(unit))
        assert code not in repr(prompt)
        assert citation not in repr(prompt)

    assert "".join(reconstructed) == source
    assert sorted(split_atom_ids) == sorted(source_atom_ids)


def test_atom_first_list_split_preserves_bibliography_label_and_link_target() -> None:
    target = "https://example.test/" + ("path/" * 120)
    block = {
        "block_id": "bibliography-2",
        "ordinal": 1,
        "kind": "list",
        "locator": {"source_id": "bib.bib2"},
        "payload": {
            "ordered": False,
            "items": [
                {
                    "text": "[2] " + ("bibliography prose " * 30),
                    "inline_spans": [
                        {"kind": "text", "text": "[2] " + ("bibliography prose " * 30)},
                        {"kind": "link", "text": "second entry", "target": target},
                    ],
                },
            ],
        },
    }

    groups = protected_atom_part_groups(block, max_bytes=64)
    assert len(groups) == 1
    assert any(
        atom["kind"] == "bibliography_label"
        for atom in protected_atom_plan(block)["atoms"]
    )
    for group in groups:
        for parts in group:
            unit = {
                "block_id": "split",
                "kind": "translation_unit",
                "payload": {"text": "local"},
                "protected_atom_plan": protected_atom_subplan(
                    block, block_id="split", parts=parts
                ),
            }
            assert target not in repr(protected_prompt_block(unit))
