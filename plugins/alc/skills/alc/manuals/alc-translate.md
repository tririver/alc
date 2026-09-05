# ALC Translate Quick Start

`alc-translate` owns reusable scientific language detection, bilingual
glossary generation, source-block translation, and translation review. Use it
when these steps must run independently of a Companion build. A source is a
verified local Markdown, HTML, or flattened TeX document.

The three generation commands use `ac-llm`; `get-result`, status, and
validation only read existing project state.

Every command returns a typed JSON envelope. Check top-level `status`,
`warnings`, and `error` before using fields under `data`.

## Run ALC Translate

Examples below assume `alc-translate` is on `PATH`. Check once with:

```bash
alc-translate --help
```

If unavailable, use the portable Skill launcher. Inside an ALC source checkout,
the package virtual environment is a direct development fallback:

```bash
<skill-dir>/scripts/alc-runtime alc-translate --help
<alc-venv>/bin/alc-translate --help
```

Use the selected launcher in place of `alc-translate` below. Do not search
package internals for another executable.

## Run the Three Translation Steps

This concrete example translates `paper.md` into Chinese in one stable project
directory.

### 1. Detect the Source Language

```bash
alc-translate detect-language paper.md \
  --target-language zh-CN \
  --project-dir local/quasi-single-field-translation \
  --document-cache-root local/cache/ac-document \
  --host-authority unknown

alc-translate get-result \
  --project-dir local/quasi-single-field-translation \
  --step language
```

`detect-language` returns the durable run identity at `run.id`. Read the
verified classification with `get-result`; its exact fields are:

| Meaning | JSON result path |
| --- | --- |
| Detected language | `data.result.language_tag` |
| Requested target | `data.result.target_language` |
| Translation decision | `data.result.mode` |

`data.result.mode` is `enabled` when translation should continue and `skipped`
when source and target languages already match. If it is `skipped`, stop; no
glossary or translated reader delivery is needed.

Set `--host-authority` once per run lineage. Use `unrestricted` only when the
host explicitly reports unrestricted authority; otherwise use `unknown`.
Reuse the identical value for subsequent generation and resume commands. For
`restricted` or `unknown`, honor the command's returned host-request pause; do
not assume a universal broker.

### 2. Build and Inspect the Glossary

```bash
alc-translate build-glossary paper.md \
  --project-dir local/quasi-single-field-translation \
  --document-cache-root local/cache/ac-document \
  --host-authority unknown \
  --approx-term-count 50

alc-translate get-result \
  --project-dir local/quasi-single-field-translation \
  --step glossary
```

The verified glossary is at `data.result.entries[]`; its requested approximate
size is `data.result.approx_count`, and its content identity is
`data.result.inventory_digest`. The target term
count is approximate and deduplicated underfill is accepted. Each entry's
`matched_sentences` are literal source search hits for disambiguation, never
definitions or explanations.
Generated glossary content containing disallowed control characters is retried
once. If the retry remains invalid, bounded ANSI SGR style sequences are removed
and deterministically truncated Unicode code points are reconstructed before
validation runs again. Only entries whose remaining content is unsafe or empty
are omitted; recovered and valid entries plus the remaining translation
workflow continue.

### 3. Translate and Inspect All Blocks

```bash
alc-translate translate-blocks paper.md \
  --project-dir local/quasi-single-field-translation \
  --document-cache-root local/cache/ac-document \
  --host-authority unknown

alc-translate get-result \
  --project-dir local/quasi-single-field-translation \
  --step blocks
```

Each generation command runs only its named step and verifies its selected
prerequisites. A successful block translation reports the native Layer at
`data.delivery.layer` and revision count at `data.delivery.revision_count`;
`get-result --step blocks` returns the canonical translation contract at
`data.result`, including `source_language`, `target_language`, `mode`, and
`coverage`. The Layer also appears in `artifacts[]` with role `layer`.

The deliveries are normally `<project-dir>/translation.layer.json` and
`<project-dir>/translation.glossary.json`, with immutable Markdown revisions
under `<project-dir>/fragments/`. The glossary handoff is render-native,
source-bound, and contains only entries with exact RichDocument block anchors.
Language and glossary steps publish no reader. Compose both deliveries with
`alc-render` to produce
standalone HTML; `alc-translate` itself does not publish a translation HTML
file. Follow `manuals/alc-render.md`: export the same source with
`ac-document export-rich-document`, then copy `translation.layer.json`,
`translation.glossary.json`, and the complete `fragments/` tree below that
publication root before composing. Pass the glossary file with `--glossary`;
omitting it deliberately produces no visible Reader glossary.
The Layer binds the exact rich source, so a different parse is rejected rather
than silently misanchoring translations.

For a project created before 2.0.2, rerun `build-glossary` with the identical
source, project, cache, authority, provider, and model options. A valid durable
result is replayed without another accepted model generation and publishes the
missing `translation.glossary.json`.

## Status, Recovery, and Validation

```bash
alc-translate status --project-dir local/quasi-single-field-translation
alc-translate validate --project-dir local/quasi-single-field-translation
alc-translate resume \
  --project-dir local/quasi-single-field-translation \
  --document-cache-root local/cache/ac-document \
  --host-authority unknown
alc-translate stop --project-dir local/quasi-single-field-translation \
  --reason "operator requested stop"
```

Status reports the selected step at `data.current_step`, its run snapshot at
`data.run`, and all selected language, glossary, and block snapshots under
`data.steps`. Inspect `data.run.status`, `data.run.can_resume`,
`data.run.error`, `data.run.resume`, and the paths under
`data.run.working_state`. Use `get-result --step language|glossary|blocks`
only to read a verified successful selected result. Validation returns
`data.valid`, `data.issues`, and, for a completed block translation, both
`data.delivery.layer` and `data.delivery.glossary`.

Resume the same project and selected step after a pause, interruption, failure,
or stop. Omit `--input` when no response is required; otherwise pass either
the exact ResumeInput JSON object or a file containing it. Completed and
verified work is reused within the same run lineage.

For model-correctable machine-output failures—changed term or block identities,
missing coverage, or damaged language or review content—ALC makes one fresh
generation attempt with exact bounded validation feedback. New translation and
review calls return only input-dependent text-slot objects. Formulae, links,
citations, bibliography labels, and code remain caller-owned and are
deterministically reinserted; the model cannot omit or rewrite their IDs.
Historical protected-atom results retain their explicit compatibility path.
Retries are scoped to invalid or missing blocks and retain valid first-response
neighbors.
If the scoped retry remains unusable, only the still-invalid units use source
fallback. Completed windows are reused, and an invalid review cannot replace
its valid pre-review translation.
This boundary also validates assembled Markdown. An unclosed display-math
delimiter or environment is retried as a model-output defect and then falls
back only for that unit; it must not reach Companion as a whole-chapter parse
failure. Touching inline formula delimiters are disambiguated locally without
changing the caller-owned formula payload.

Exhausted provider transport, timeout, quota, rate-limit, unavailability, and
open-circuit outcomes preserve the affected source window while retaining
earlier accepted translations. The next window still runs; any successful
window resets the failure streak. Only two consecutive failed windows preserve
all remaining model-dependent windows. The workflow records a sanitized
provider fallback diagnostic with provider/model, category/detail, window,
streak, and remaining skipped-window count. Authentication, host authority,
invalid request/schema, prerequisite binding, input-budget, explicit stop, and
corrupt durable state keep their typed stopping paths. Translation quality,
scientific judgment, style, and other debatable choices belong to review.

Use the same project directory for every step. Durable translation state lives
only below `<project-dir>/.alc/translate/`. Without `--document-cache-root`, document
data uses `AC_DOCUMENT_CACHE` when set and otherwise `.ac/cache/ac-document` below
the launch directory. Keep the working directory stable or pass the same
explicit local cache to every source-reading or resume command.

## Help

```bash
alc-translate --help
alc-translate detect-language --help
alc-translate get-result --help
alc-translate <command> --help
```

Use command help for accepted source forms, provider and model selection,
refresh behavior, project state, result selection, and exact failure flags.
