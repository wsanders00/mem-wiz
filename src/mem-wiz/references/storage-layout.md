# Storage Layout

## Shipped Skill Bundle

- `SKILL.md`: concise operator-facing instructions.
- `memwiz/`: the Python runtime package and CLI implementation.
- `scripts/memwiz`: bundle-local entrypoint for running the CLI from an unpacked skill.
- `references/storage-layout.md`: durable reference material for structure and paths.

## Runtime Memory Root

- `policy.yaml`: root-level autonomy policy for `remember`, scaffolded by `memwiz init` when missing.
- `audit/YYYY-MM-DD.jsonl`: append-only autonomous decision log.
- `global/canon/`: accepted global memories.
- `global/archive/`: archived global memories.
- `global/cache/`: shared cache data.
- `workspaces/<slug>/inbox/`: captured workspace candidates.
- `workspaces/<slug>/canon/`: accepted workspace memories.
- `workspaces/<slug>/archive/`: archived workspace memories.
- `workspaces/<slug>/cache/`: workspace-local cache data.

## Notes

- Global memory has no inbox; promotion starts from accepted workspace canon.
- `remember` may auto-accept into workspace canon under policy, but global
  promotion remains explicit by default.
- `status`, `audit`, and `context` read this layout directly; no secondary
  memory store or hidden index is introduced.
- Release artifacts package `src/mem-wiz/` directly, so these paths appear at archive root.
