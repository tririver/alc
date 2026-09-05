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

Glossary results use `alc.translate.glossary_result.v2` and always expose a
closed `fallback_summary`: `{schema_version,recovered_term_ids,dropped_term_ids,
reason_codes}`. All three arrays are empty when no fallback occurred. A
recovered term remains in `entries`; a dropped term is absent from `entries`.
The summary is derived from the existing durable per-window fallback diagnostic,
not a second artifact, and is replay-safe. Pre-v2 result artifacts are read as
explicit legacy input; when their durable diagnostic and keyword inventory are
available, the runtime hydrates the same public summary without rewriting the
historical artifact. Companion consumers need only read
`data.result.fallback_summary` to account for glossary degradation.

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
retains its ordinal rather than expanding to an author-year title). Authored
LaTeXML bibliography prefixes remain exact in numeric `[30]` and `(30)` form
and in author-year form such as `Baldwin et al. (1981)` or
`Rupke et al. (2005b)`.
LaTeXML `bib.bib*` IDs remain target identities and are not interpreted as the
visible bibliography ordinal; the authored list prefix supplies that label.
Comma-adjacent narrative author links retain their individual labels/targets
without being frozen as a numeric citation group. Adjacent inline math spans
are validated as separate formulas even when their Markdown delimiters touch.
Markdown formulas or links left inside a parser text span, including arXiv
links with nested bracket labels, are incorporated into the same source
identity so the canonical source-text fallback always validates itself. Math
syntax inside a Markdown link destination is excluded from visible formula
counting, while formulas in the link label remain source-authoritative.
Every list is translated and reviewed item by item. Oversized items and
paragraph blocks are further divided into bounded internal units, then
deterministically reassembled into one revision with the original block
identity. Historical accepted whole-list translations are expanded into those
item units before current budget windows are formed, so a changed window
boundary does not discard already accepted work. The canonical protected atom
plan is built before bounded splitting, so splitting affects only text parts;
formulae, inline code, citation groups, bibliography labels, and caller-owned
link targets/delimiters remain indivisible. Ordinary link labels are nested
translatable text inside their closed link atom; citation links, and labels that
themselves contain formulae or inline code, remain immutable.
If a model adds exactly one redundant escape layer to a known source formula,
the translator restores that exact source formula before strict validation;
substituted, missing, duplicated, or newly invented formulas still fail.

Generation and resume commands accept `--host-authority`. Set
`<host-authority>` once per run: use `unrestricted` only when the host
explicitly reports unrestricted authority; otherwise use `unknown`. Reuse the
identical value when resuming. The setting is execution-only and is not
recorded in a translation request or result.

A failed step is the latest failed attempt, not a permanent project terminal
state. Status exposes `can_resume`, `recovery_epoch`, and stable `working/`
paths. Glossary candidates contain only term IDs plus translated content. New
model translation candidates use `alc.translate.text_slot_result.v1`. The
input contains an ordered source skeleton, but the output schema exposes only
the exact required text-slot properties. Formulae, citations, code,
bibliography labels, and link targets never appear in the model result. The
caller deterministically reinserts every immutable atom and normal-link
delimiter around the translated slots. Review patches use the same text-slot
boundary and cannot rewrite atom identity. The input-dependent closed schema
requires every block and slot and rejects unknown properties before semantic
assembly. Historical protected-atom candidates remain readable through the
explicit v1 compatibility path.

Assembled units are also checked as standalone Markdown before they become
accepted artifacts. Unclosed `$$`, `\[`, or supported display-math environments
are model-output errors: they receive the same bounded semantic retry and then
fall back only for the affected source unit. Adjacent inline formula spans are
canonicalized only in downstream model views so their touching `$` delimiters
cannot be mistaken for display math; the immutable source atom payload remains
unchanged.

A retry contains only invalid or missing blocks, includes the exact bounded
validation diagnostics, and retains valid neighbors from the first response.
A second invalid result preserves only the still-invalid smallest source
translation units and records the fallback. Translation fragments assembled
this way carry
`protected_atoms = {schema_version,assembled_by}` provenance. Existing
pre-v13 `{block_id,text}` accepted artifacts are read only through the explicit
legacy compatibility path and are never reclassified as protected-atom output.
An agent may correct a candidate and resume without another provider call.
Deleting an exhausted retry candidate does not grant a third automatic
generation attempt.

When a model response is structurally valid JSON but violates a
machine-checkable language, term, block, text-slot, or review coverage
contract, ALC makes one fresh full-generation attempt with validation feedback.
After a second unusable block-translation response, ALC preserves the affected
source text as the translation fallback and continues. The text-slot
assembler reconstructs structured inline math and links from caller-owned
payloads; it does not parse a model copy of complete Markdown. Final
original-block reassembly applies the same per-block fallback without discarding
valid neighboring translations. Legacy artifacts continue to use their existing
source-relative Markdown validator only while being replayed.
Glossary translations and definitions containing disallowed control characters
use the same one-retry boundary. If the retry remains invalid, ALC removes
bounded ANSI SGR style sequences and reconstructs deterministically truncated
Unicode code points, then validates the recovered entries again. It drops only
entries whose remaining content is unsafe or empty, retains valid neighboring
entries, records recovered and dropped counts plus the reason, and continues
the translation workflow.
`preferred_translation` remains a plain-text contract. If a model returns
Markdown math delimiters there after the bounded retry, ALC keeps the entry and
uses its exact source term as the safe plain fallback while retaining a valid
Markdown definition. The recovered entry and reason remain visible in the same
fallback summary.
Replayed draft or accepted model artifacts use the same salvage boundary, so a
resumed run cannot turn a previously persisted block-local content error into a
workflow failure.
If review fails, ALC keeps the already validated pre-review translation.
Fragment provenance records `alc.translate.fallback.v1`, and run events record
fallback counts and reasons. Exhausted provider transport, timeout, quota,
rate-limit, unavailability, or circuit failure source-preserves the affected
window while retaining earlier accepted translations. A later successful
window resets the provider-failure streak; only two consecutive failed windows
source-preserve all remaining model-dependent windows. Provider diagnostics
record the frozen provider/model, failure category and detail code, affected
window, and any remaining-window fallback without storing source content.
Provider authentication, host-authority, invalid request/schema, source/binding
corruption, explicit stops, and publication failures remain terminal or
resumable boundaries. Translation quality and scientific judgment remain
reviewer concerns, not program-invalid output.

## Tests

The default suite uses deterministic sources and fake model services:

```bash
python -m pytest packages/alc-translate/tests
```
