# ALC Companion Quick Start

`alc-companion` builds a source-anchored, run-owned `alc-render` publication and
promotes its standalone reader to `<project-dir>/companion.html`. Build and
resume require ALC's public package dependencies; an incomplete runtime returns
`runtime_dependency_missing`.

## Run ALC Companion

Use `alc-companion` directly when it is on `PATH`. Check once:

```bash
alc-companion --help
```

If the bare command is unavailable, use the portable Skill runtime:

```bash
<skill-dir>/scripts/alc-runtime alc-companion --help
```

Inside an ALC source checkout, the package virtual environment is the direct
development fallback:

```bash
packages/alc-companion/.venv/bin/alc-companion --help
```

Use the selected launcher in place of `alc-companion` below. Do not inspect
package internals for another executable.

## Build from a Local Source

Markdown, HTML, or flattened single-file TeX is authoritative. A PDF is an
optional input validator for fidelity and page mapping, never a reader output:

If OCR proofreading was explicitly requested, follow
`workflows/ocr-proofread.md` first and use its validated `proofread.md` here.
The original PDF remains only a Companion validator. The two packages remain
independent; this sequencing belongs to the ALC Skill.

```bash
alc-companion build <source.md> --pdf <validator.pdf> \
  --project-dir <project-dir> --target-language <language-tag> \
  --host-authority <host-authority>
```

For example:

```bash
alc-companion build note.md \
  --pdf note.pdf \
  --project-dir local/note-companion \
  --target-language zh-CN \
  --user-intent "Explain the argument and its assumptions." \
  --host-authority unknown
```

Omit `--pdf` when no validator is available. Use the user-selected project
directory itself; do not append an attempt suffix. Inside this checkout, choose
a stable ignored path under `local/`. Companion claims only
`<project-dir>/.alc/companion/` and `<project-dir>/companion.html`; unrelated
files remain untouched.

Remote academic acquisition belongs to an optional host-level ARC research
workflow. It must materialize one local rich source before this command. For an
exact-version arXiv HTML URL, keep one self-contained HTML bundle authoritative
for the selected project and run; do not fall back to TeX or flattened Markdown
after a failure. If the
user explicitly supplies authors, repeat `--author <name>`; otherwise let Companion
verify source-derived candidates. Unsupported reader-interface languages need
one complete `--reader-labels <json-file>` map.

## Authority and Document Cache

Choose `--host-authority` once per run. Use `unrestricted` only when the host
explicitly grants it; otherwise use `unknown` (or `restricted` when known).
Reuse the same value on resume. Without an authorized broker, a required host
model turn becomes a durable pause returned by the command. Companion supplies
a bounded broker for its own declared read-only `ac-document` source and
translation commands; arbitrary commands, writes, network access, and another
source identity are not brokered.

Codex Desktop command execution permission is a separate boundary. A
model-backed Companion `build` or `resume` that may use the Codex provider must
run through host execution, as specified in `workflows/companion.md`, so the
nested provider can reach its own local state and app-server. Granting that
outer command permission does not make `--host-authority unrestricted`
truthful: keep `unknown` unless the host independently reports unrestricted
broker authority. Read-only commands such as `status` and `validate` do not
need this model-provider permission merely because they inspect the same run.
The Skill requests host execution directly and leaves approval to the host's
configured reviewer; it cannot grant its own escalation. Do not add a separate
chat confirmation before the tool call.
The user's Companion request is the authorization to process the supplied
source with the workflow's frozen provider. It is not necessary to obtain a
second destination confirmation for that same provider.

For a new `build`, never send unresolved `--provider auto` to host approval.
Run the public `ac-llm doctor --provider auto` preflight through `alc-runtime`
in the ordinary sandbox, require `data.available: true`, and pass its exact
`data.provider` to the build. For `resume`, use the frozen provider/model
reported by `status` in the host justification without changing the run.

`--document-cache-root <path>` overrides the document cache for build or resume.
Without it, Companion uses `AC_DOCUMENT_CACHE` when set, otherwise
`<launch-directory>/.ac/cache/ac-document`. Durable Companion state always stays
under `<project-dir>/.alc/companion/`; it is not a shared cache. Keep the same
launch directory, environment value, or explicit cache root across build and
resume.

## Read Build and Status Results

Every command prints one `ac.command_result.v2` JSON envelope. Always inspect
top-level `status`, `warnings`, `error`, and `resume`.

For `build` and `resume`:

- selected durable identity: top-level `run.id`;
- durable lifecycle: `data.run.status` (with the same ID at `data.run.id`);
- promoted reader, when delivered: `data.delivery.html`;
- publication identity: `data.publication_digest` and `data.edition_digest`;
- selected heads: `data.selected_revision_digests[]`;
- delivery consistency: `data.workspace_html_consistent`.

A successful generation whose web rendering failed keeps top-level `status` at
`"completed"`, but reports `data.published: false`, an empty `data.delivery`,
and a `web_render_failed` warning. Do not claim reader delivery in that case.

Inspect the selected project at any time:

```bash
alc-companion status --project-dir <project-dir>
```

For `status`, the selected identity remains top-level `run.id`, while its
lifecycle is `data.selected_run.status`. A succeeded publication also reports
`data.publication`, `data.publication_digest`, `data.edition_digest`,
`data.selected_revision_digests`, and `data.workspace_html_consistent`. A valid
root reader appears as an artifact with role `web`; status does not expose a
`data.delivery` field. Preserve status warnings about invalid workspaces or
stale HTML.
`data.progress` reports the current phase, completed and total units, completed
and total chapters, the frozen provider/model, last progress time, partial
Reader availability, translation fallback counts/reasons, and one normalized
`next_action`.

## Resume, Render, and Validate

If `status` or a build returns a pause, inspect top-level `resume`, including
`resume.input_required` and `resume.request_artifact`, together with
`data.progress.next_action`. Resume the selected lineage; never create an
attempt-suffixed project, substitute another source representation, or change
provider/model as an implicit fallback:

```bash
alc-companion resume \
  --project-dir <project-dir> \
  --input <resume-input.json> \
  --host-authority <same-host-authority>
```

`--input` accepts an inline JSON object or a JSON file. Omit it when the current
pause descriptor does not require input. Completed verified child work is
replayed within the same run. A failed result with an editable candidate reports
that exact path in `data.progress.next_action.candidate_path`; repair only that
declared candidate and resume the same run without hand-writing an `ac-llm`
resume object.

Recoverable block-translation identity failures automatically preserve the
affected source text as identity-preserving Markdown and continue after the
bounded retry, including failures detected after bounded units are reassembled
into their original block. Resuming through a previously persisted invalid
draft or accepted model artifact applies the same block-local salvage instead
of repeating the failure. Review failures keep the validated pre-review
translation. These cases remain visible in
`data.progress.translation_fallbacks` and fragment provenance; they do not
require hand-written resume input. Source corruption, permission decisions,
explicit stops, and invalid final publication remain safe stopping boundaries.

`build` refuses to replace a different selected source/recipe by default. Use
`--new-lineage` only after an explicit decision to start a genuinely different
lineage; pauses, failures, and slow progress use `status` and `resume` instead.

Use the existing cooperative stop when the user asks to stop:

```bash
alc-companion stop --project-dir <project-dir> --reason "<reason>"
```

Render again after renderer, style, font, or validator changes, without model
calls:

```bash
alc-companion render --project-dir <project-dir>
```

On promotion, use `data.delivery.html`; it is the root
`<project-dir>/companion.html`. `data.publication_digest`,
`data.edition_digest`, `data.selected_revision_digests`, and
`data.workspace_html_consistent` describe the rendered edition. An empty
`data.delivery` plus `publication_not_selected` means another run became
selected before promotion.

Validate both the run-owned publication and root standalone reader:

```bash
alc-companion validate --project-dir <project-dir>
```

Success reports `data.valid: true`, `data.workspace_html_consistent: true`, and
the publication/edition digests. A missing or stale `companion.html` is a
delivery failure, not successful publication-only validation. Optional local
Chromium checks add browser result data:

```bash
alc-companion validate \
  --project-dir <project-dir> \
  --browser \
  --browser-timeout 60
```

Use `--browser-executable <path>` only to select a specific Chromium-family
executable.

## Post-Publication Revision

`revise` creates immutable child revisions and republishes the selected
edition. It cannot change source identity, anchors, language, role, priority,
bibliography, or resources. Use this exact closed v1 request shape:

```json
{
  "schema_version": "alc.companion.publication_revision_request.v1",
  "run_id": "<top-level status run.id>",
  "publication_digest": "<status data.publication_digest>",
  "review_id": "review-20260812-01",
  "reason": "Correct the explanation after source review.",
  "reviewer": null,
  "replacements": [
    {
      "fragment_id": "<selected fragment ID>",
      "base_semantic_digest": "<selected fragment semantic digest>",
      "title": "Corrected title",
      "markdown_body": "Complete replacement Markdown body."
    }
  ]
}
```

`title` may be `null`; `markdown_body` must be non-empty. Use the current
top-level `run.id` and `data.publication_digest` from `status`. The
`fragment_id` and its matching `base_semantic_digest` must come from the
selected publication already presented by the browser editor or from the
explicit review context that selected the correction. `status` exposes selected
revision digests but no public fragment-to-base getter. Do not invent a getter,
guess a digest, or inspect private durable layout; if that selected-fragment
context is unavailable, obtain it before constructing the request.

Run the correction with:

```bash
alc-companion revise \
  --project-dir <project-dir> \
  --request revision-request.json
```

Exact request replay is idempotent. A reused `review_id` with different content,
a stale publication or fragment base, an unknown fragment, a no-op replacement,
or an unknown bibliography citation fails. On success, read the request's
committed revision digests from `data.revision_digests[]`, all selected heads from
`data.selected_revision_digests[]`, the resulting edition from
`data.edition_digest`, replay state from `data.idempotent_replay`, and the
promoted reader from `data.delivery.html`. Add `--browser` when the corrected
reader also needs local Chromium validation.

## Build Semantics

The build reuses verified work within its durable run. Reusable translation is
owned by `alc-translate`: language detection and the glossary precede full
translation, and translation completes before reviewed guide generation. Each
proposer and reviewer compares a complete chapter with its frozen translation.
The glossary size is approximate; deduplicated underfill is valid.
Every chapter enters proposer-reviewer evaluation,
including an empty proposal; a strong proposal may be accepted immediately,
and at most two full revisions are requested. Add
`--cross-chapter-editorial-review` only when the user requests the optional
document-wide redundancy audit.

Companion itself does not run academic research or depend on `arc-paper`.
Optional academic enrichment may call ARC before the build and supply reviewed
local supplements. If ARC is unavailable, ask whether to install it or proceed
without enrichment. There is no guide-unit quota. Retain provenance and remove
generic summary, paraphrase, or repetition.
Paragraph-local and cross-paragraph explanations have equal status. Without an
explicit audience, popular writing targets a generally educated adult,
research papers target students with relevant foundations, and textbooks assume
standard prerequisites without assuming difficult material is mastered.

## Browser Editing and Printing

Click a translation or guide body in the standalone reader to edit its raw
Markdown. Only one draft may be active; unchanged Save creates no revision. A
changed Save uses the revision snapshot already loaded by the browser and
writes one new immutable fragment revision. Reconnecting or refreshing the
chosen project directory incorporates other-process revisions and reports
forks. Reader export refreshes the connected directory before producing
per-role Markdown or complete standalone HTML. Use `alc-companion revise` for
formal reviewed corrections.

Companion has no PDF release command. A person may open `companion.html` in
Chrome and use Print / Save as PDF. That PDF is a user-created derivative: ALC
does not validate, reproduce, retain, publish, or guarantee it.

## Help

```bash
alc-companion --help
alc-companion <command> --help
```
