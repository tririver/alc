# alc-companion

`alc-companion` generates source-anchored translation and guide overlays for
an `ac-document` `RichDocument`. Its durable output is an `alc-render`
publication: atomic Markdown fragment revisions, producer layers, the complete
rich source, bibliography and glossary metadata, and run-owned source
resources.

The package does not own a second book model or rendering engine. Use
`alc-render` to render or edit the publication workspace.

For translated builds, every chapter translation is frozen before guide
generation. Chapter proposers and reviewers receive exact commands for reading
both the original and translated cached documents, so guide wording can follow
the accepted names and terminology without copying whole document bodies into
model-request JSON.

Guide writing uses `ac-proposer-reviewer`. A reviewer may accept a strong
proposal immediately or give concrete, constructive suggestions for up to two
complete revisions. Both roles compare the guide with the corresponding source
and translation. Inline guide fragments add information rather than compress
or restate the source; chapter guides may use concise orientation as one part
of a broader guide.

## Quick start

Use `alc-companion` directly when installed on `PATH`. If it is unavailable in
an installed ALC Skill, use `<skill-dir>/scripts/alc-runtime alc-companion`.
From this source checkout, use
`packages/alc-companion/.venv/bin/alc-companion`.

Build from a local source:

```bash
alc-companion build note.md \
  --project-dir local/example \
  --target-language zh-CN \
  --user-intent "Explain the main argument and its assumptions." \
  --host-authority unknown

alc-companion status --project-dir local/example
alc-companion render --project-dir local/example
alc-companion validate --project-dir local/example
```

Markdown, HTML, or flattened single-file TeX is authoritative. For local
sources, `--pdf note.pdf` supplies an optional validator; PDF is never the
reader source or output. Use `unrestricted` only when the host explicitly
grants it. Otherwise use `unknown`, or `restricted` when known, and preserve the
same authority on resume. Remote academic acquisition belongs to an optional
host-level ARC research workflow, which must first materialize a local source
for Companion.

Every command prints an `ac.command_result.v2` envelope. For `build` and
`resume`, read the selected durable identity at top-level `run.id`, lifecycle at
`data.run.status`, and delivered reader at `data.delivery.html`. Publication
identity and consistency are at `data.publication_digest`,
`data.edition_digest`, `data.selected_revision_digests[]`, and
`data.workspace_html_consistent`. A generation may complete while rendering
fails: in that case top-level `status` is `"completed"`, but
`data.published` is false, `data.delivery` is empty, and warnings include
`web_render_failed`.

Inspect and recover a paused selected run with:

```bash
alc-companion status --project-dir local/example

alc-companion resume \
  --project-dir local/example \
  --input resume-input.json \
  --host-authority unknown

alc-companion render --project-dir local/example
alc-companion validate --project-dir local/example
```

For `status`, lifecycle is at `data.selected_run.status`; status deliberately
has no `data.delivery`. A valid promoted reader is reported as an artifact with
role `web`. On a pause, inspect top-level `resume.input_required` and
`resume.request_artifact`; `--input` accepts inline JSON or a JSON file and may
be omitted when no input is required. Resume replays verified completed work in
the same durable run. Keep the original document-cache root and host authority.
After an explicit render, use `data.delivery.html`; an empty delivery with
`publication_not_selected` means a different run won selection before
promotion.

Add `--cross-chapter-editorial-review` to `build` to run one optional,
single-worker proposer-reviewer pass after all chapter-local guides finish.
The pass may revise or omit a guide only when the final reviewer explicitly
approves the exact digest-bound edit. Original accepted guides remain as the
audit baseline. The resolved publication includes a lightweight summary and a
downloadable `alc.companion.editorial_review.v1` JSON report. Builds without
the flag retain the v17 recipe identity and make no editorial model calls.

Post-publication corrections use a canonical request and create immutable
child revisions without changing the run-owned publication:

```bash
alc-companion revise \
  --project-dir local/example \
  --request revision-request.json
```

The request binds the selected run and publication digest. Each replacement
binds the current fragment semantic digest and supplies the complete new title
and Markdown body. Citations must already exist in the publication
bibliography; source identity, anchors, language, role, and priority are
inherited. Committed reviews live below
`.alc/companion/operator-revisions/<run-id>/` and are replayed by status,
render, revise, and validate. The immutable `publication_digest` identifies
the base publication; `edition_digest` identifies that publication plus its
ordered current fragment heads. Glossary revision heads are carried separately
by the Reader/export contract and do not change this existing digest.

Use `alc-companion --help` and each subcommand's `--help` for the complete
durable-control and publication options. `--document-cache-root` overrides document
storage; otherwise the command uses `AC_DOCUMENT_CACHE` or
`<launch-directory>/.ac/cache/ac-document`. This cache is separate from durable
project state.

A successful build writes its immutable artifacts under
`<project-dir>/.alc/companion/jobs/` and materializes the selected publication
under `<project-dir>/.alc/companion/publications/<run-id>/`. The `render`
command first writes and validates a run-specific reader there, then atomically
promotes it to portable standalone `<project-dir>/companion.html` only if that
run is still selected.

ALC publishes and validates the publication workspace and standalone HTML
only. A PDF made manually with a browser's print command is a user-side
derivative, not an ALC release artifact, and ALC does not promise to validate,
reproduce, retain, or automatically publish it.

The publication workspace is self-contained:

```text
publication.json
layers/translation.json
layers/companion.json
fragments/revision-....md
glossary/revision-....md
glossary-batches/<batch-id>/fragments/revision-....md
resources/<sha256>
```

Translation fragments use priority 10. Inline Companion fragments use priority
20; chapter and section guides use priority 101. Fragment location is anchored
to immutable rich-source block identity, while the Markdown file contains only
the human-authored semantic content. The validated JSON front matter owns
fragment identity; directory names are never semantic identities.
Model-authored display math is canonicalized before publication: opening and
closing `$$` delimiters occupy separate lines around the TeX body. Ambiguous or
unbalanced display-math delimiters are rejected instead of being published as
literal Reader text.

## Reader assumptions

An explicit reader background in user intent takes precedence. Otherwise,
popular or weakly specialized writing assumes a generally educated adult
without specialist training; research papers assume a student who has
completed the relevant foundational courses; textbooks assume completion of
standard prerequisites without assuming difficult prerequisite material is
already mastered.

## Tests

```bash
python -m pytest packages/alc-companion/tests
```
