# ALC Development Guidance

ALC owns learning workflows: OCR proofreading, translation, interactive HTML,
and Companion reading guides. Package code must not import ARC or depend on an
agent host or checked-out Skill.

## Boundaries

- `alc-render` may depend on `ac-document`.
- `alc-ocr-proofread` may depend on `ac-jobs`, `ac-llm`, and `ac-document`.
- `alc-translate` may additionally depend on `alc-render`.
- `alc-companion` may depend on all AC packages plus `alc-render` and
  `alc-translate`.
- Schemas, imports, distributions, CLIs, and product environment variables use
  `alc.*`, `alc_*`, `alc-*`, and `ALC_*` respectively. Shared infrastructure
  keeps `ac.*`, `ac_*`, `ac-*`, and `AC_*`.
- Durable learning state lives under `<project-dir>/.alc/`. Neutral document
  cache remains AC-owned at `.ac/cache/ac-document`.
- Academic enrichment is optional Skill-level coordination with ARC. ALC code
  never imports, installs, or invokes ARC.

## Runtime and plugin

The plugin exposes only `alc-runtime`, `alc-render`, `alc-ocr-proofread`,
`alc-translate`, and `alc-companion`. Foundation commands are invoked through
`alc-runtime`. Generated bootstrap and DSH bridge copies must match the SHA-256
digests in `generated-sources.json`; their Foundation source is pinned by full
Git SHA in `runtime-sources.json`.

## Development

- Use ignored `local/` paths for non-source artifacts.
- Unit tests are offline by default; network tests require
  `ALC_RUN_NET_TESTS=1`.
- Run focused tests first, then the complete suite and package builds.
- Do not change a release version without explicit user approval.
- Preserve unrelated worktree changes; commit each validated functional unit.
