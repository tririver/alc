# Interaction

ALC tasks default to automatic execution with safe, documented defaults. Use
interactive checkpoints only when the user requests step-by-step review or a
real choice changes the result materially. Do not ask the user to choose an
execution mode at startup.

Pause for missing source authority, an unsafe destructive action, unreadable
durable state, or a product choice that cannot be inferred safely. Ordinary
model correction, retry, and review remain workflow work, not user gates.

An explicit stop uses the owning command's cooperative stop semantics. Resume
the same run through the owning package; do not invent a second cancel state.
