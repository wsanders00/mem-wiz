# mem-wiz

mem-wiz is an agent-agnostic memory skill for capturing, scoring, accepting,
and promoting durable memories without letting storage bloat over time.

## Memory Model

- Workspace memories start as candidates in the selected workspace inbox.
- Accepted workspace memories move into workspace canon after scoring.
- Global memories are promoted explicitly from accepted workspace records.

## Current Commands

- `init`: create the memory root plus shared global directories.
- `capture`: write a workspace candidate and reject secret-like content.
- `score`: evaluate workspace candidates for workspace retention fitness.
- `accept`: move an eligible workspace candidate into workspace canon.
- `promote`: copy an eligible accepted workspace memory into global canon with provenance.
- `search`: query accepted workspace and global canon with deterministic text matching.
- `get`: print canonical YAML for one accepted memory by ID.

## Runtime Notes

- The memory root defaults to `~/.memwiz` and can be overridden with `MEMWIZ_ROOT`.
- The workspace slug comes from `--workspace`, `MEMWIZ_WORKSPACE`, or the current repo name.
- Prefer concise, evidence-backed, durable memories over ephemeral task chatter.
- Never store credentials or other secret-like content.
