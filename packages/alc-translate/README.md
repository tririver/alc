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
`<project-dir>/translation.layer.json`. Language and glossary steps remain
durable prerequisites and do not publish a reader delivery. Compose the Layer
with `alc-render` to produce standalone reader HTML.

Use `alc-translate --help`, `alc-translate get-result --help`, and each stage's
`--help` for exact source, prerequisite, result, and durable-control options.

Each translation revision is bound to exactly one source RichDocument block,
has priority `10`, and preserves the block locator and content fingerprint.
Full-document results are publishable Layers. The lower-level selected-block
mode is an orchestration result for callers such as Companion and cannot
replace `translation.layer.json`.
Source figures or media with no language-bearing caption or alt text do not
produce visible translation fragments; their assets remain source-owned.

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
machine-checkable language, term, block, formula, link, or review identity or
coverage contract, ALC makes one fresh full-generation attempt with validation
feedback. A second unusable response pauses with both attempts and an editable
candidate preserved. Completed windows and a valid pre-review translation stay
available. Provider, authority, binding, input-budget, and corrupt-artifact
failures are not semantic-output retries. Translation quality and scientific
judgment are reviewer concerns, not program-invalid output.

## Tests

The default suite uses deterministic sources and fake model services:

```bash
python -m pytest packages/alc-translate/tests
```
