---
name: alc
description: Use for source-faithful OCR proofreading, translation, interactive HTML rendering, or textbook-style Companion reading guides. Also use when the user explicitly invokes ALC or `$alc` for one of these learning workflows.
---

# Agentic Learning Copilot (ALC)

ALC turns local source material into verified text, translations, interactive
readers, and source-anchored learning companions. It does not own academic
paper discovery or research judgment.

## Select one capability

- OCR proofreading against a PDF: read `workflows/ocr-proofread.md` and
  `manuals/alc-ocr-proofread.md`.
- Standalone translation: read `manuals/alc-translate.md`.
- Rich-document or standalone HTML rendering: read
  `manuals/ac-document.md` and `manuals/alc-render.md`.
- Companion build, resume, revision, or render: read
  `workflows/companion.md` and `manuals/alc-companion.md`.

When the requested result includes a reading guide, paragraph companion,
visible glossary, or a complete learning Reader, select the Companion workflow.
Standalone translation owns source-plus-translation delivery; it does not
substitute for Companion merely because it builds a glossary prerequisite.

Read `rules/interaction.md` for user-choice and automation behavior and
`rules/operating.md` for shared local-state rules. Do not preload unrelated
manuals.

## CLI resolution

Use `alc-ocr-proofread`, `alc-translate`, `alc-render`, or `alc-companion`
directly when exposed by the host. Shared Foundation commands such as
`ac-document`, `ac-jobs`, `ac-llm`, and `ac-proposer-reviewer` are intentionally
not separate plugin wrappers; invoke them through the product launcher:

```bash
<skill-dir>/scripts/alc-runtime ac-document <command> [args...]
```

For an ALC command unavailable on `PATH`, use the same launcher:

```bash
<skill-dir>/scripts/alc-runtime alc-translate <command> [args...]
```

In DeepSeek Harness, use `$DSH_ALC_RUNTIME` in place of the launcher path.
Prewarm with `alc-runtime setup`; inspect source identity and readiness with
`alc-runtime doctor`. Runtime locks pin full Git SHAs for both ALC and AC
Foundation.

Generic document cache defaults to `.ac/cache/ac-document` under the launch
directory. Durable learning state stays under the selected project's `.alc/`
directory. Never treat durable runs as shared cache.

## Optional academic enrichment

`alc-companion` itself neither imports ARC nor performs academic research. If
a Companion would materially benefit from paper discovery or literature
review, the Skill may suggest using ARC first and passing reviewed local
supplements into ALC. If ARC is unavailable, state that it is optional and ask
whether the user wants to install it or continue without enrichment. Never
install ARC automatically and never make it a Python or runtime dependency of
ALC.

## Direct HTML sources

`alc-companion` accepts a local source only. When the user provides one direct
HTML URL for a Companion, materialize it at the Skill layer before starting the
build. This is acquisition, not academic enrichment:

1. This workflow accepts direct HTML URLs only. Classify locally before probing
   an executable. Route to ARC only for an exact
   `https://arxiv.org/html/<id>[vN]` URL, deterministically extracting the ID
   and preserving an explicit `vN` version. An explicit ar5iv URL and every
   other HTTPS HTML URL go to generic ACF with the original URL unchanged.
2. Probe ARC without installing it. When `arc-paper` is already on `PATH`, run
   this no-network, no-write capability probe:

   ```bash
   arc-paper export-arxiv-html-acquisition --help
   ```

   Use that launcher only when the probe exits with status 0. Otherwise, only
   when the ARC Skill is present, run its own:

   ```bash
   <arc-skill-dir>/scripts/arc-runtime doctor
   ```

   Continue only if it exits successfully and returns JSON with `ready:true`.
   Then run the same no-network, no-write capability probe through that ready
   runtime:

   ```bash
   <arc-skill-dir>/scripts/arc-runtime arc-paper \
     export-arxiv-html-acquisition --help
   ```

   Use the runtime launcher only when this second probe exits with status 0.
   Never call `setup`; any missing, not-ready, or failed probe goes to generic
   ACF.
3. When the exact official URL and an executable probe both pass, materialize
   through:

   ```bash
   arc-paper export-arxiv-html-acquisition <paper-id> \
     --output-dir <bundle-dir> [--cache-root <root>]
   ```

   If the ready ARC Skill runtime is being used instead of the console script,
   use its own launcher:

   ```bash
   <arc-skill-dir>/scripts/arc-runtime arc-paper \
     export-arxiv-html-acquisition <paper-id> --output-dir <bundle-dir>
   ```

   Do not use ALC's runtime launcher for an ARC command. ARC's materialized
   export must contain the shared `ac.document.html_source_bundle.v1` bundle.
4. If ARC is unavailable, old, not ready, incapable, or the input is not an
   exact official arXiv HTML URL, invoke the explicit
   provider-neutral `ac-document acquire-html-bundle` flow through
   `alc-runtime` with `--output-dir <bundle-dir>`. It atomically creates
   `<bundle-dir>/source.html`, `<bundle-dir>/manifest.json`, and any local
   resources. Pass the original HTTPS URL unchanged. Do not install ARC or
   retry through a different source type.
5. In either route, retain the one materialized local HTML primary and its
   materialized export manifest. The export's nested bundle uses the shared
   contract, and the Companion integration projects its bundle identity,
   primary artifact digest, requested URL, and final URL into the durable
   lineage. Start Companion with the local `source.html` plus
   `--html-source-manifest <manifest-path>`.

Acquisition warnings, including partially unavailable resources, are retained
through Companion's existing source-diagnostic warning surface. ALC package
code does not import, install, or invoke ARC; ARC presence and recognition are
Skill-level coordination only.

## Completion

Validate the owning workflow before delivery. Publish visible HTML or native
source artifacts; hidden state is not the final deliverable. Preserve exact
source identity, returned run IDs, assumptions, and warnings.
