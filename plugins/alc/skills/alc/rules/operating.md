# Operating rules

- Treat a user-supplied project directory as the project root. Do not append an
  attempt directory or replace it with a new build root.
- Keep durable workflow state under `<project-dir>/.alc/`; keep generic AC
  document cache under `.ac/cache/ac-document` or an explicit
  `AC_DOCUMENT_CACHE`.
- Use public CLI/API status, validation, result, resume, and stop surfaces.
  Do not infer state by editing private run files unless the owning command
  explicitly returns an editable recovery path.
- Preserve frozen source and translation identity. Do not silently substitute
  another paper, edition, PDF, or translation.
- Freeze the provider and model selected by the first durable build. Retries
  and resume use that same recipe; never create a fallback project or switch
  providers without an explicit new user-authorized action.
- In Codex Desktop, request host execution before launching a model-backed
  Companion `build` or `resume` that may use the Codex provider. Resolve
  `--provider auto` through public `ac-llm doctor` first and submit only the
  exact provider to host review. Do not discover this boundary by first
  launching a nested Codex CLI inside the command
  sandbox: repeated local permission failures consume retries and open the
  provider circuit. Host execution for the outer command is not unrestricted
  broker authority. Request it through the tool and its configured reviewer;
  do not add a separate chat confirmation or self-authorize the escalation.
- Treat an explicit Companion request as authorization for the frozen provider
  to process the supplied source. Do not split that one requested workflow into
  repeated chat approvals for the same source and provider.
- Do not stop a valid run because it is long or quiet. Use status or host
  background execution.
- Recoverable translation-output defects use the owning workflow's declared
  source-preserving fallback and remain visible in status/provenance. Never
  delete source content or hide a fallback merely to reach success.
- Deliver visible HTML or source artifacts in addition to hidden state.
