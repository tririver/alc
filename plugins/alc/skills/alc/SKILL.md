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

## Completion

Validate the owning workflow before delivery. Publish visible HTML or native
source artifacts; hidden state is not the final deliverable. Preserve exact
source identity, returned run IDs, assumptions, and warnings.
