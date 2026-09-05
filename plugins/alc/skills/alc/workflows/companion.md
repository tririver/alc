# Companion Workflow

Use this workflow for an explicit request to build or refresh a textbook-style
reading companion. Read `manuals/alc-companion.md` before the first command.

## Phase 1: Prepare

### Step 1: Choose the project directory

Use the directory explicitly supplied by the user as `<project-dir>` itself.
Do not append another `companion`, `build-v2`, `fresh`, or attempt-specific
directory. If choosing the location inside this checkout, use one stable,
descriptive directory under the ignored `local/` tree and verify it before
running:

```bash
git check-ignore -q --no-index <project-dir>
```

The `local/` rule applies only inside this checkout; respect an external
project directory supplied by the user. A new Companion project root may
already contain source material, notes, or other unrelated user files.
Companion leaves unrelated files untouched and claims only
`.alc/companion/` and the root `companion.html`. Before the first build,
choose another root or resolve the conflict if either managed path already
exists. An existing recognized Companion project may contain additional
unrelated files.

Ensure the installed environment contains the complete Companion runtime,
including the public `alc-translate` facade. Build checks this before creating
the project and returns `runtime_dependency_missing` for an incomplete
installation.

### Step 2: Resolve source and intent

Choose a local rich Markdown, HTML, or flattened single-file TeX source. A PDF
is optional and is used only for validation and page mapping. `alc-companion`
does not resolve remote paper identifiers. For one direct HTML URL, use ARC
only for exact `https://arxiv.org/html/<id>[vN]`; preserve the version while
extracting the paper ID. An ar5iv URL or any other HTTPS HTML URL always goes
to generic ACF with the original URL unchanged. If `arc-paper` is on `PATH`,
first run `arc-paper export-arxiv-html-acquisition --help`; only exit status 0
is usable. Otherwise, only an ARC Skill runtime whose `doctor` exits 0 with
JSON `ready:true` may run
`<arc-skill-dir>/scripts/arc-runtime arc-paper
export-arxiv-html-acquisition --help`; only exit status 0 is usable. These
probes are no-network and no-write. Never run `setup`; any failed probe uses
the generic route. The accepted ARC route uses
`arc-paper export-arxiv-html-acquisition <paper-id> --output-dir <bundle-dir>`
with an optional `--cache-root <root>`. Both routes must return one materialized
export containing an
`ac.document.html_source_bundle.v1` bundle and one local HTML primary. The
Companion integration projects the nested bundle's identity, primary artifact
digest, requested URL, and final URL into the lineage; partial-resource
warnings remain Companion source diagnostics. Do not retry a structural,
translation, or provider failure through TeX, flattened Markdown, a second
source bundle, or another project root. Preserve the user's exact
`user_intent`; when absent, Companion uses its neutral textbook intent.

For the generic route, create one explicit materialization directory:

```bash
<skill-dir>/scripts/alc-runtime ac-document acquire-html-bundle <html-url> \
  --output-dir <bundle-dir>
```

Start the build with the manifest-adjacent local `source.html` and the export:

```bash
alc-companion build <bundle-dir>/source.html \
  --html-source-manifest <bundle-dir>/manifest.json \
  --project-dir <project-dir> \
  --target-language <language-tag> \
  --host-authority <host-authority>
```

Companion verifies that the explicit source path and bytes match the manifest;
do not copy, rename, or substitute that source between acquisition and build.

When the user explicitly requests OCR proofreading and supplies source
Markdown, original PDF, and MinerU content-list JSON, first complete
`workflows/ocr-proofread.md` in this same project root. Use its validated
`proofread.md` as the Companion source and retain the original PDF as the
optional validator. This is Skill-level sequencing: `alc-companion` does not
depend on `alc-ocr-proofread`. If any required proofreading input is absent,
stop that prerequisite instead of inferring page alignment. Do not add this
stage when the user did not request it.

If the user explicitly supplies an author, pass one `--author <name>` per
author. Otherwise leave author resolution to Companion: source metadata and
bylines are only candidates, and a model identity check publishes them only at
high confidence. Do not guess or force an uncertain author. Reader-facing
framework labels must use the target language; for an unsupported target
language, supply one complete label map with `--reader-labels <json>`.

## Phase 2: Build

### Step 1: Start the durable build

```bash
alc-companion build <source-path> \
  --project-dir <project-dir> \
  --target-language <language-tag> \
  --approx-term-count <estimate> \
  --user-intent '<intent>' \
  --provider <provider> \
  --model <model> \
  --effort <effort> \
  --host-authority <host-authority> \
  --workers <workers>
```

Before requesting host execution for a new build whose provider is `auto`,
resolve it in the ordinary command sandbox:

```bash
<skill-dir>/scripts/alc-runtime run ac-llm doctor --provider auto
```

Require a completed result with `data.available: true` and a non-empty exact
`data.provider`. Replace the build argument with
`--provider <resolved-provider>` before requesting host execution. Do not
submit `--provider auto` to host execution, and do not turn a missing or
unavailable provider into a user authorization question; report it as a
technical readiness error. Provider-specific model resolution still belongs
to the durable build and is frozen in its recipe. For `resume`, read the exact
frozen provider/model from `status` and include them in the host-tool
`justification`; never alter the recipe.

Before starting a new model-backed build, resolve and freeze both the exact
model and effort, then announce them once in commentary without waiting for a
reply. This is a non-blocking parameter disclosure, not an approval checkpoint.
When neither value was supplied by the user and the Codex defaults resolve to
Luna plus medium effort, use this exact wording:

> 当前伴读将使用默认模型 `gpt-5.6-luna + effort medium` 进行。如需调整，可在请求中指定模型和 effort；本次将按上述参数继续执行。

When the user supplied either value, use this pattern with the fully resolved
values:

> 当前伴读将按用户自定义模型 `gpt-5.6-terra + effort high` 进行，并继续自动执行。

Pass the exact resolved model with `--model` and the resolved effort with
`--effort`. A user may override only the model, only the effort, or both; the
other value keeps its default. Do not call it an
"internal model", do not ask for confirmation, and do not delay the build after
the announcement. Once the run is created, its model and effort are immutable
for ordinary resume.

When this Skill runs inside Codex Desktop, execute the outer model-backed
`alc-companion build` or `alc-companion resume` command with host execution
instead of the command sandbox. Do this before the first model-backed `build`
or `resume`; do not wait for a nested Codex provider to fail first. For the
Codex command tool, set `sandbox_permissions="require_escalated"` and give the
tool a concise `justification` that the Companion invokes the selected model
exact provider. Do not ask a separate chat confirmation before making that tool
call; let the host's configured approval reviewer decide. If the host still
surfaces a user approval prompt, wait for that decision and do not simulate or
claim approval. Apply this boundary when `--provider codex` is selected and
when another exact provider requires host execution. It grants the outer
process the local access needed by the nested provider; it does not grant
arbitrary source authority, change the frozen provider/model, or justify
passing `--host-authority unrestricted`.

The user's explicit request to build a Companion from the supplied source
already authorizes model processing of that source through the provider frozen
by this workflow. Do not ask a second chat question about sending the document
to that same provider. Ask again only if a materially different provider,
destination, source, or lineage is proposed.

Add `--cross-chapter-editorial-review` only when the user wants an additional
global redundancy audit after all chapter-local guides complete. It runs a
separate single-worker proposer-reviewer scope for at most three rounds. Only
edits explicitly approved by the final reviewer are used in the resolved
publication; original accepted guide artifacts remain unchanged. The
publication exposes a short status plus a downloadable complete editorial
review report. Without the flag, the build keeps its existing recipe identity
and model-call count.

Choose `<host-authority>` once: use `unrestricted` only when the host
explicitly reports unrestricted authority; otherwise use `unknown`. Reuse the
identical value when resuming this run. Companion automatically brokers only
the exact read-only `ac-document` source and frozen-translation commands it
declares. Unknown commands, writes, network access, and another source identity
remain durable refusals or pauses.

The build resolves `--provider auto` to one exact provider and model before it
creates the durable recipe. Read the frozen values from status and keep them
for every retry and resume. Never switch providers, create a fallback run, or
start another project root because a build is slow, paused, or failed; that is
a separate material action requiring explicit user authorization.
When the command tool yields a running execution handle, keep waiting on that
same handle until the build command returns a terminal result or an actionable
pause. `status` is an observation surface, not a replacement owner for the
running process. Do not end the Codex task or claim delivery while the selected
Companion run remains `PENDING` or `RUNNING`; wait for a terminal result or a
pause that can be handled through the same lineage's resume descriptor.
In Codex Desktop, a command result carrying `session_id` must be followed with
`write_stdin` polls on that exact session; a result carrying a running cell ID
must be followed with the matching cell wait operation. Commentary-only waiting,
process-list checks, and repeated `status` calls do not keep ownership of the
build. A final answer while public status remains `running` violates this
workflow even if a partial Reader exists.
If the original execution handle is no longer available, attach exactly once
with `alc-companion wait --project-dir <project-dir> --poll-seconds 15` and wait
on that command's handle until it returns. Do not replace terminal waiting with
repeated `status` calls.
The wait attachment resumes only the same durable run when a `RUNNING`
execution is orphaned; an active execution lease keeps it observation-only.
It returns when the run is terminal or reaches an actionable pause; handle the
pause through the same lineage rather than treating it as final delivery.
If the selected project genuinely needs a different source or recipe, obtain
that authorization and pass `--new-lineage`; never use it for ordinary retry
or recovery.

Add `--pdf <path>` only for a local PDF input validator. It is never a
Companion output. `--pdf fetch` and remote refresh are not Companion features.
Command JSON may be redirected to an unrelated path inside `<project-dir>`;
Companion does not treat unrelated files as project-state conflicts. Do not
redirect to a managed Companion path.

Companion detects source language once. It skips translation only for a known
matching primary language; mixed or unknown source is translated. Chapter
boundaries come from the validated source structure when available, otherwise
from source headings, and cover every source block exactly once.

Model tasks receive a small cache-identity manifest, while each chapter task
receives that chapter's block locators in its task payload. With an exact
`ac-document` cached document, agents should prefer cache-only reads of the
precise line ranges or search results they need. They may read a complete
current chapter when narrower excerpts are insufficient; discourage
whole-book reads when chapter-scoped access is enough, but do not prohibit
them in program logic. Companion does not duplicate the whole source into
every agent workspace. A verified text-only whole-source input exists only
when cache access could not be established. Do not open source image or media
assets for reading; deterministic assembly restores them later. Models author
semantic JSON, while Companion injects routing identities such as chapter IDs.

All required chapter translations finish and freeze before any guide loop
starts. Companion materializes the complete frozen translation as a separate
content-addressed `ac-document` document and gives each proposer and reviewer
direct commands for the complete current original chapter, complete current
translation, and matching exact parts and sections. Both roles must inspect
the original and translation together and preserve the translation's
established proper names, translated titles, and technical terminology.
Translation bodies remain outside loop-context JSON; a modified translation
gets a new immutable cache identity, so searches for the selected translation
never mix old and new versions.

Academic enrichment is an optional host-level ARC step, not a Companion code
capability. When the user wants academic research for a Companion, first check
whether the ARC Skill and `arc-paper` are available. If either is absent, tell
the user that academic enrichment is optional and ask whether to install it or
continue without it; never install it silently. When available and authorized,
ALC may call ARC, review the resulting evidence, and pass only explicit local
reviewed supplements into the Companion build. `alc-companion` itself neither
imports `arc-paper` nor acquires or admits references.

Do not impose a reference target, minimum, or maximum, and do not criticize a
proposal merely for having few references. Keep only sources that improve a
specific anchored explanation. If enrichment is declined or unavailable,
continue with the verified source, translation, and already supplied reviewed
supplements.

Reviewed supplement prose and translated excerpts use the target language
while source titles and URLs retain source identity.

Treat paragraph-local notes and chapter-level or cross-paragraph notes as
equally legitimate. Choose placement from the explanatory need, with no quota
or default preference. Keep, replace, or remove proposed units based on whether
they add motivation, a genuinely different presentation, deeper implications,
omitted reasoning, substantive connections, reliable context, or materially
useful later developments. Paraphrase, same-meaning rewriting, repeated source
reasoning, and generic summary are not Companion value; remove such units
instead of forcing one expansion per paragraph or chapter.

The proposer reads the complete current chapter and checks every source part
for reader-understanding needs; the reviewer repeats that comparison against
the original and frozen translation. An explicit user audience wins.
Otherwise, popular, directional, or weakly specialized writing assumes an
adult with average general literacy and no specialist background; a research
paper assumes a professional student who has completed the relevant
foundational courses; a textbook assumes a student who completed its standard
prerequisites without presuming that difficult prerequisite concepts are
already firmly mastered. There is no minimum number of units, and zero is
valid only when every part is genuinely simple and self-contained for the
resolved reader.

Prefer direct affirmative explanation. Use corrective contrasts only when the
source, user intent, or a cited reference establishes the misconception; never
invent a prior reader belief to create an explanatory effect. Review replaces
unsupported corrective framing and cannot remove the last unit serving a
required reader need.

The guide lane writes free-form CommonMark learning units rather than selecting
from a fixed menu of note types. Headings, short questions, worked reasoning,
comparisons, historical context, counterpoints, lists, equations, and other
forms are available when useful; none is a required repeated template. ALC
checks source anchoring, citation identity, coverage, and renderability while
leaving explanatory form and chapter composition to the model.

When translation is enabled, `alc-translate` builds the bilingual glossary and
completes translation before reviewed guide generation. Deterministic matching
supplies each chapter guide only the glossary entries that occur in that
chapter; translation windows likewise receive only entries matched to their
source window.

Guide improvement is owned by `ac-proposer-reviewer`, and every chapter enters
it even when the initial proposal is empty. The reviewer must not criticize
merely to fill a round: it stops immediately when the proposal satisfies the
reader needs and has no concrete improvement path. Otherwise it gives
constructive feedback, including good new anchored, well-supported ideas and
useful references already present in reviewed supplements, for up to two
complete revisions. The maximum sequence is
proposer-reviewer-proposer-reviewer-proposer; the last proposal is validated
directly, without an unused final review. Companion injects `chapter_id` into
the final candidate as caller-owned routing data.

### Step 2: Resolve a pause

Run `status` first and follow `data.progress.next_action`. It reports the
current phase, completed and total units, frozen provider/model, last progress
time, and any editable candidate path. Ordinary declared source reads are
handled by Companion's read-only broker and should not become user-visible
pauses. If an exceptional pause still requires input, inspect the returned
`resume` descriptor and request artifact, validate the requested response, and
resume the same opaque key:

Block translation identity failures are not exceptional pauses: after the
bounded automatic retry, ALC reconstructs structured source math and links as
identity-preserving Markdown, retains that affected block, and continues.
Final bounded-unit reassembly applies the same per-block fallback. Review
failures retain the validated pre-review translation. Glossary definitions with
disallowed control characters are retried once and then omitted per entry so
the remaining build continues. Inspect `data.progress.translation_fallbacks`
and the final fragment provenance; do not claim that fallback text is a
completed translation.
Companion also validates every persisted translation revision before building
the per-chapter guide input. If one legacy revision contains unclosed Markdown
display math, use source text for that guide part, omit only the unsafe overlay,
and record `translation_omitted`; do not patch the authoritative source or start
a new lineage merely to bypass the bad revision.
A completed publication includes a machine-verifiable delivery ledger. It must
account for every source unit and identify each local fallback; validation
rejects silent degradation. If optional interactive Reader admission fails
after a valid publication, ALC may deliver a static, no-JavaScript source-only
Reader. It does not use this fallback for invalid source identity, permission,
lineage, durable state, or a tampered ledger.
If provider transport, timeout, rate-limit, quota, unavailability, or an open
circuit prevents one translation window, bounded recovery preserves that
window as source and continues. A successful later window resets the streak;
only two consecutive failed windows source-preserve the remaining
model-dependent windows. Status and the final ledger expose a sanitized
provider failure diagnostic. Guide failure still omits only the unavailable
guide. Static source-only delivery is reserved for failure before a usable
overlay exists. Authentication,
host-authority, request/schema, source-identity, lineage, durable-state, and
publication-integrity failures still stop without a misleading Reader.

```bash
alc-companion resume --project-dir <project-dir> \
  --input '<resume-input-json>' \
  --host-authority <host-authority>
```

For a failed build, inspect the candidate path reported by
`data.progress.next_action`. Candidate files are written before semantic
validation and errors report their exact paths. Edit that candidate only when
the failure explicitly exposes it, then run `alc-companion resume` without
creating a replacement run. A final guide
candidate is backed by the durable proposer-reviewer transcript; deleting it
re-materializes that frozen proposal rather than creating an extra model round.
Keep visual QA under
`.alc/companion/diagnostics/visual/<run-id>/`; do not create attempt-named
project roots or loose project-level QA directories.

## Phase 3: Publish and Deliver

### Step 1: Inspect and validate

```bash
alc-companion status --project-dir <project-dir>
alc-companion validate --project-dir <project-dir>
```

Each successful build has a run-owned `alc-render` publication workspace at
`<project-dir>/.alc/companion/publications/<run-id>/`, containing
`publication.json`, native Layers, immutable Markdown fragment revisions, and
source resources. It is the durable publication state. Companion renders the
selected run's standalone reader at `<project-dir>/companion.html`; that root
file is the reader delivery, not a redirect to a release directory.

Successful build and resume commands automatically attempt to materialize the
run-owned publication and render the standalone HTML. If publication or HTML
rendering fails after generation succeeds, the command reports
`web_render_failed` and does not claim delivery. Repair the render contract or
resources and run `render`; technical diagnostics remain in command results and
run events, never in reader content.

`validate` must validate both the run-owned publication workspace and the
root standalone HTML together. A missing or invalid `companion.html` is a
delivery failure, not a substitute for publication validation.

Completion must come from `alc-companion validate`, not generic
`alc-render validate` against a manually composed translation Reader. Confirm
that the selected Companion run succeeded. A translated build must carry its
source-bound glossary when anchored entries exist. Guide or companion card
counts may legitimately be zero only after every planned chapter completed
proposer-reviewer evaluation; never infer that evaluation occurred merely
because a translation Layer renders successfully.

For a bounded correction to already published fragment text, create a formal
revision request and run:

```bash
alc-companion revise --project-dir <project-dir> \
  --request <revision-request.json>
```

Use the current selected fragment semantic digests reported by `status`.
Revisions replace complete titles and Markdown bodies while preserving source
identity, anchors, language, role, and priority. They cannot add bibliography
entries, resources, or anchors; rebuild the Companion for those changes.

Before starting a full rebuild after a source edit, classify the change. A
renderer, style, font, or validation-only change uses `render`. When the source
change is limited to standalone metadata, corrected paragraph segmentation, or
a small number of visually verified page joins, first compare the old and new
rich documents. Reuse and re-anchor fragments whose complete source content is
unchanged, remove overlays anchored only to metadata, and ask a model to revise
only the changed spans from their frozen prior translations. The main agent
must review every ambiguous mapping and every correction to source text. Keep
the prior run-owned workspace immutable and validate the newly source-bound
publication and reader. Use a full build when semantic changes are broad,
anchors cannot be mapped with high confidence, or focused revision cannot
produce a complete usable layer.

ALC has no Companion PDF release artifact or automated PDF pipeline. A person
may open the standalone HTML in Chrome and use Print / Save as PDF, but that
file is a user-side derivative: ALC does not validate it, reproduce it,
automatically publish it, or make durability guarantees for it.

### Step 2: Render without model calls

Use render after a style, font, renderer, or validator change when source
identity is unchanged:

```bash
alc-companion render --project-dir <project-dir>
```

`render` makes no model calls. It rematerializes the selected run's
`alc-render` publication and rewrites the root standalone HTML from it. This
is a model-free publication repair path, not an additional generation stage.
