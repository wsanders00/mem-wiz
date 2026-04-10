# mem-wiz

mem-wiz is an agent-agnostic memory skill for lightweight long-term memory.
It keeps YAML as the source of truth, stays local and inspectable, and avoids
background transcript mining or heavy vector infrastructure.

## Memory Model

- Workspace memories start as candidates in the selected workspace inbox.
- Accepted workspace memories move into workspace canon after scoring.
- Global memories are promoted explicitly from accepted workspace records.
- `remember` is the only autonomous write entrypoint in v1.
- Workspace canon is the self-improvement layer; global canon stays higher trust.

## Autonomy Model

- Root policy lives at `<memwiz-root>/policy.yaml`.
- `memwiz init` scaffolds the default policy file when it is missing.
- Missing policy defaults to the `balanced` profile.
- Autonomous decisions are recorded under `<memwiz-root>/audit/YYYY-MM-DD.jsonl`.
- The default `balanced` profile may auto-accept safe workspace memories, but
  global auto-promotion remains conservative and is not the default.

## Current Commands

- `init`: create the memory root, shared global directories, and a default `policy.yaml`.
- `capture`: write a workspace candidate and reject secret-like content.
- `remember`: capture, score, audit, and possibly auto-accept a workspace memory.
- `score`: evaluate workspace candidates for workspace retention fitness.
- `accept`: move an eligible workspace candidate into workspace canon.
- `promote`: copy an eligible accepted workspace memory into global canon with provenance.
- `lint`: validate selected workspace and global records for integrity and policy conflicts.
- `compile`: build bounded `cache/digest.md` summaries from accepted workspace or global canon.
- `search`: query accepted workspace and global canon with deterministic text matching.
- `get`: print canonical YAML for one accepted memory by ID.
- `prune`: archive structurally redundant accepted canon memories, with `--dry-run` preview support.
- `doctor`: inspect root, workspace, lock, and canon/archive record health without mutating memory state.
- `status`: summarize policy, counts, digests, and current review pressure.
- `audit`: inspect append-only autonomous decisions with simple filters.
- `context`: generate bounded wake-up context for the selected workspace and global scope.

## Runtime Notes

- The memory root defaults to `~/.memwiz` and can be overridden with `MEMWIZ_ROOT`.
- The workspace slug comes from `--workspace`, `MEMWIZ_WORKSPACE`, or the current repo name.
- Prefer concise, evidence-backed, durable memories over ephemeral task chatter.
- Never store credentials or other secret-like content.
- Prefer `remember` over `capture` when an agent needs on-demand autonomous memory.
- Use `status`, `audit`, and `context` to review or consume autonomous behavior.

## Agent Operating Pattern

- Start or resume with `scripts/memwiz context --format json`.
- Save durable knowledge with `scripts/memwiz remember --format json`.
- Prefer high-signal kinds such as `workflow`, `constraint`, `warning`, and `decision`, backed by `command`, `doc`, `file`, `test`, or `user` evidence when available.
- After autonomous writes or before handoff, inspect `scripts/memwiz status --format json` and `scripts/memwiz audit --format json`.
- Do not remember one-off status chatter, unsupported guesses, strong duplicates, or secret-like content.
- Keep `promote` explicit and conservative for cross-workspace reuse.

## Bundle Layout

- `scripts/memwiz` runs the CLI from an unpacked skill bundle.
- `references/storage-layout.md` documents the shipped skill layout and the runtime memory tree.
