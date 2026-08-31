# alc-translate

`alc-translate` owns reusable scientific language detection, LLM-reviewed
bilingual glossary generation, source-block translation, and translation
review over verified `ac-document.RichDocument` sources. It uses `ac-jobs` for
durable execution, `ac-llm` for model calls, and publishes native
`alc-render` fragment revisions plus a translation Layer.

## Running the CLI

An installed package provides the `alc-translate` console script. The ALC Skill
runtime is the portable fallback; inside an ALC source checkout, the package
virtual environment is a direct development fallback:

```bash
alc-translate --help
<skill-dir>/scripts/alc-runtime alc-translate --help
packages/ac-document/.venv/bin/alc-translate --help
```

Use the first available launcher consistently in later commands.

## Quick start

Detect whether a verified source needs translation:

```bash
alc-translate detect-language note.md \
  --target-language zh-CN \
  --project-dir local/example/translation \
  --document-cache-root local/cache/ac-document \
  --host-authority unknown

alc-translate get-result --project-dir local/example/translation \
  --step language
```

Read `data.result.language_tag`, `data.result.target_language`, and
`data.result.mode` from `get-result`. Stop when `mode` is `skipped`; when it is
`enabled`, run the remaining two stages against the same source and project:

```bash
alc-translate build-glossary note.md \
  --project-dir local/example/translation \
  --document-cache-root local/cache/ac-document \
  --host-authority unknown --approx-term-count 50

alc-translate translate-blocks note.md \
  --project-dir local/example/translation \
  --document-cache-root local/cache/ac-document \
  --host-authority unknown

alc-translate get-result --project-dir local/example/translation \
  --step blocks
```

The three commands are separately durable stages and verify their selected
prerequisites. The final command returns the canonical result at `data.result`
and the Layer handoff at `data.delivery.layer`.

Glossary `preferred_translation` values are plain text. Glossary
`target_definition` values use the Reader's CommonMark-compatible Markdown
dialect: `$...$` is inline math and `$$` delimiter lines wrap display math.
Definitions should stay compact and omit raw HTML, headings, tables, images,
and fenced code blocks.

`--document-cache-root` is optional. Without it, source access uses
`AC_DOCUMENT_CACHE` when set, otherwise
`<launch-directory>/.ac/cache/ac-document`. Durable state is project-local under
`<project-dir>/.alc/translate/`.
The final translation step publishes immutable revisions below
`<project-dir>/fragments/` and
`<project-dir>/translation.layer.json`. A successful glossary step also
publishes `<project-dir>/translation.glossary.json`, a render-native delivery
bound to the exact RichDocument and its block anchors. Language and glossary
steps do not publish a reader by themselves. Compose both deliveries with
`alc-render`; omitting `--glossary` deliberately creates no visible Reader
glossary.

For a pre-2.0.2 project whose durable glossary already succeeded, rerun
`build-glossary` with the identical source, project, cache, and generation
options. The verified durable result is reused and the missing render handoff
is materialized without another accepted model generation.

Use `alc-translate --help`, `alc-translate get-result --help`, and each stage's
`--help` for exact source, prerequisite, result, and durable-control options.

Each translation revision is bound to exactly one source RichDocument block,
has priority `10`, and preserves the block locator and content fingerprint.
Full-document results are publishable Layers. The lower-level selected-block
mode is an orchestration result for callers such as Companion and cannot
replace `translation.layer.json`.
Source figures or media with no language-bearing caption or alt text do not
produce visible translation fragments; their assets remain source-owned.
When `ac-document` supplies authoritative `source_presentation` rich fields,
translation prompts project heading text and Figure/Table captions from those
typed spans so TeX and link identity are not flattened into plain Unicode.
Table geometry and scientific cell data remain source-owned in the Reader;
only the authored caption is translated, preventing a second untyped copy of
the Table. Validated `source_notes` are scheduled as separate translation units
and published with exact `source_note_translation = {schema_version,note_id}`
provenance bound to the owner block. Present metadata is validated by
`ac-document`; absent metadata keeps the legacy plain-block projection.
When a source note consists of exactly one authored link, the translator
bypasses the model and preserves its visible label and exact target; a URL
label therefore remains the original URL instead of becoming a translated
generic word such as `link`.
Canonical translated heading Markdown
uses the RichBlock semantic level, including exact abstract and acknowledgements
normalization supplied by `ac-document`; raw source tag depth is not inferred in
the translator. Internal bibliography links preserve their exact target,
source-visible label, surrounding citation brackets/separators, and bibliography
entry prefix (for example, `[8, 12]` remains one group and reference `[30]`
retains its ordinal rather than expanding to an author-year title).
LaTeXML `bib.bib*` IDs remain target identities and are not interpreted as the
visible bibliography ordinal; the authored list prefix supplies that label.
Comma-adjacent narrative author links retain their individual labels/targets
without being frozen as a numeric citation group. Adjacent inline math spans
are validated as separate formulas even when their Markdown delimiters touch.

Generation and resume commands accept `--host-authority`. Set
`<host-authority>` once per run: use `unrestricted` only when the host
explicitly reports unrestricted authority; otherwise use `unknown`. Reuse the
identical value when resuming. The setting is execution-only and is not
recorded in a translation request or result.

A failed step is the latest failed attempt, not a permanent project terminal
state. Status exposes `can_resume`, `recovery_epoch`, and stable `working/`
paths. Glossary candidates contain only term IDs plus translated content, and
translation candidates contain only block IDs plus translated text; source
identity is attached locally. An agent may correct a candidate and resume
without another provider call. Deleting an exhausted retry candidate does not
grant a third automatic generation attempt.

When a model response is structurally valid JSON but violates a
machine-checkable language, term, block, formula, link target/label, or review
identity or coverage contract, ALC makes one fresh full-generation attempt
with validation feedback. A second unusable response pauses with both attempts
and an editable candidate preserved. Completed windows and a valid pre-review
translation stay available. Provider, authority, binding, input-budget, and
corrupt-artifact failures are not semantic-output retries. Translation quality
and scientific judgment are reviewer concerns, not program-invalid output.

## Tests

The default suite uses deterministic sources and fake model services:

```bash
python -m pytest packages/alc-translate/tests
```
