# Autonomous Capture

Use `remember` for durable knowledge that should change future behavior in the
selected workspace. Keep the write path deliberate, not continuous.

## Save Without Asking First

Call `scripts/memwiz remember --format json` when one of these becomes clear:

- A workflow the agent should repeat.
- A durable constraint or preference that will shape later choices.
- A warning or failure mode that should be avoided later.
- A decision with enough evidence to justify repeating it.
- A stable fact that is likely to matter again in the same workspace.

Routine save approval is not required for those cases. The point of the
autonomous path is that the agent should decide and write on demand.

## Skip Or Leave For Review

Do not write memories for:

- One-off progress chatter, task status, or temporary TODOs.
- Conversational filler or summaries with no future reuse.
- Low-confidence guesses or agent-only assertions with weak evidence.
- Strong duplicates or thin rephrasings of existing memories.
- Credentials, tokens, secrets, or secret-like material.

If a candidate is ambiguous, duplicate-prone, or sensitive, skip it or rely on
the normal review surfaces instead of interrupting the user for routine
approval.

## Lightweight Review Cadence

- Start or resume with `scripts/memwiz context --format json`.
- Write with `scripts/memwiz remember --format json` only at trigger moments.
- After autonomous writes or before handoff, inspect `scripts/memwiz status --format json`.
- Use `scripts/memwiz audit --format json` only when targeted follow-up is needed.
