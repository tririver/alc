# Agentic Learning Copilot (ALC)

ALC turns local source material into verified OCR text, translations,
interactive HTML readers, and source-anchored learning companions.

Packages:

- `alc-ocr-proofread`: PDF-vision review of page-mapped OCR.
- `alc-translate`: durable language detection, glossary, translation, and review.
- `alc-render`: rich-document composition and standalone interactive HTML.
- `alc-companion`: translated, source-anchored Companion builds and revisions.

ALC depends on [AC Foundation](https://github.com/tririver/ac-foundation) for
durable jobs, model execution, neutral documents, and proposer-reviewer
orchestration. Major-compatible Python dependencies use `>=2,<3`; plugin
runtimes pin full Git commit SHAs.

ALC does not depend on ARC. Its Skill may optionally suggest ARC when academic
research would improve a Companion; the user decides whether to install or
continue without it.

## Install

ALC is distributed as an agent plugin with a lazy, SHA-locked private runtime.
The runtime installs exact Git revisions of AC Foundation and ALC; no PyPI
publication is assumed.

For Codex:

```bash
codex plugin marketplace add tririver/alc --ref stable
codex plugin add alc@alc
```

For Claude Code:

```text
/plugin marketplace add tririver/alc@stable
/plugin install alc
```

For DeepSeek Harness:

```bash
dsh plugin --profile alc add github:tririver/alc
```

Check or prewarm the locked runtime:

```bash
plugins/alc/bin/alc-runtime doctor
plugins/alc/bin/alc-runtime setup
```

The neutral document cache defaults to `.ac/cache/ac-document` below the
launch directory; override it with `AC_DOCUMENT_CACHE`. Foundation runtime
state uses `AC_HOME` and `AC_RUNTIME_HOME`.

## Development

```bash
python -m pytest --import-mode=importlib packages/*/tests tests
scripts/build-packages.sh
```

Generated files, test runs, and caches belong under ignored `local/` paths.
See `AGENTS.md` for repository rules.

## Plugin

The plugin lives at `plugins/alc`. It exposes `alc-runtime` and wrappers for
the four ALC CLIs. Shared AC commands are reached through `alc-runtime`, not
duplicated wrappers.

## Release

```bash
scripts/release-alc.sh VERSION
```

The release script updates all four distributions and both plugin manifests.
No PyPI publication is assumed.

## License

MIT. See `LICENSE`.
