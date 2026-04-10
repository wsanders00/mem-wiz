# mem-wiz

This repository keeps development files at the root and is organized so the
skill bundle can be released from `src/mem-wiz/`.

- The repository root holds contributor-facing files such as `README.md`,
  `AGENTS.md`, `pyproject.toml`, `tests/`, and local planning material under
  ignored `ai/`.
- `src/mem-wiz/` is the intended release boundary. Release artifacts should
  package the contents of this directory so unpacked bundles expose `SKILL.md`,
  `memwiz/`, `scripts/`, and `references/` at archive root.
- `src/mem-wiz/memwiz/` contains the runtime Python package and the `memwiz`
  CLI entrypoint used for editable installs.
- `src/mem-wiz/scripts/memwiz` is the bundle-local wrapper for invoking the CLI
  from an unpacked skill bundle.
- `src/mem-wiz/references/` holds on-demand reference material that keeps
  `SKILL.md` concise.
- `python3 scripts/build_skill_artifact.py` writes a zip under `dist/` using
  the contents of `src/mem-wiz/` as the archive root.
- CLI scope defaults are part of the v1 contract: `get`, `lint`, `compile`,
  and `prune` default to the selected workspace; `search` defaults to selected
  workspace plus global; `--scope all` means selected workspace plus global
  only.
- Releases follow SimVer and should only include docs that match the current
  repository state. Keep local planning notes under ignored `ai/`.
- When running directly against `src/mem-wiz/`, prefer
  `PYTHONDONTWRITEBYTECODE=1` to avoid leaving `__pycache__/` under the shipped
  bundle tree.

## Memory Workflow

- `capture` remains the low-level manual write to the selected workspace inbox.
- `remember` is the policy-aware autonomous entrypoint for agents. It captures,
  scores, and may auto-accept safe workspace memories while always writing an
  audit event.
- Workspace canon is the self-improvement layer. Global canon remains the
  higher-trust layer and still requires explicit promotion by default.

## Autonomy Defaults

- `policy.yaml` lives at the memory root and defaults to the `balanced` profile
  when absent.
- The default `balanced` profile allows autonomous capture plus safe workspace
  auto-accept for durable kinds such as `workflow`, `constraint`, `warning`,
  and `decision`.
- Global auto-promotion stays conservative. The default policy is `suggest`,
  not automatic promotion.
- Autonomous decisions are append-only under `audit/YYYY-MM-DD.jsonl`.

## Command Surface

- Manual flow: `capture`, `score`, `accept`, `promote`
- Autonomous flow: `remember`
- Review surfaces: `status`, `audit`, `context`
- Retrieval and diagnostics: `search`, `get`, `doctor`, `compile`, `lint`, `prune`

## Agent-Facing Output

- `remember --format json` returns a structured decision payload.
- `search`, `get`, `doctor`, `compile`, `status`, `audit`, and `context` all
  support `--format json`.
- `context` produces bounded wake-up context from the selected workspace plus
  global scope boundaries without scanning unrelated workspaces.
