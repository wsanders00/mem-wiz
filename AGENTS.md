# Repository Guidelines

## Project Structure & Module Organization
Root files such as `README.md`, `AGENTS.md`, `pyproject.toml`, and `tests/` define the development workspace. The shipped bundle root is `src/mem-wiz/`. Keep the runtime package under `src/mem-wiz/memwiz/`, CLI wiring in `src/mem-wiz/memwiz/cli.py`, command handlers in `src/mem-wiz/memwiz/commands/`, and shared logic in focused modules such as `config.py`, `models.py`, `storage.py`, `scoring.py`, and `dedupe.py`. Tests live in `tests/` and should mirror the behavior they cover, for example `tests/test_promote.py` or `tests/test_storage.py`.

Treat `src/mem-wiz/` as shipped runtime surface only. Root-level docs, packaging config, and tests stay outside the release artifact. Treat `ai/` as local planning workspace; do not push stale design notes. Do not commit generated artifacts such as `__pycache__/`, `.pytest_cache/`, `*.egg-info/`, or `dist/`.

## Build, Test, and Development Commands
- `python3 -m venv .venv`: create a local Python 3.11+ development environment.
- `.venv/bin/python -m pip install -e . pytest`: install the editable `memwiz` CLI and test tools.
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q`: run the full automated test suite without leaving `__pycache__/` under `src/mem-wiz/`.
- `.venv/bin/python -m pytest tests/test_promote.py -q`: run a focused test slice while iterating.
- `.venv/bin/memwiz --help`: inspect the CLI surface after editable install.

Editable installs currently rely on `pyproject.toml` and `setup.cfg`. Test import bootstrapping lives in `tests/conftest.py`.

## Coding Style & Naming Conventions
Target Python `>=3.11`. Use 4-space indentation, type hints, and descriptive `snake_case` names for modules, functions, and tests. Keep one primary behavior per command module under `src/mem-wiz/memwiz/commands/`. Prefer small, explicit helpers over broad utility layers, and keep file contents ASCII unless a dependency requires otherwise.

## Testing Guidelines
Use `pytest` for all coverage. Add or update tests with every behavior change, especially around CLI contracts, schema validation, storage transitions, scoring policy, and promotion rules. Name tests after observable behavior, such as `test_capture_rejects_secret_like_input_before_write`. Run `python3 -m pytest -q` before merging.

## Commit & Pull Request Guidelines
History uses Conventional Commit prefixes such as `feat:`, `fix:`, `docs:`, and `chore:`. Keep subjects imperative and scoped to one behavior change. Pull requests should summarize user-visible changes, call out CLI or schema impacts, and include the verification command used, usually `python3 -m pytest -q`. Releases follow SimVer.

## Agent-Specific Notes
This repository is an agent-agnostic memory skill. Preserve the current model: manual workspace `capture` is explicit, autonomous workspace capture happens through `remember`, global memory promotion is explicit, and memory should stay lightweight rather than grow without bound. Preserve the v1 CLI scope contract: `get`, `lint`, `compile`, and `prune` default to workspace, `search` spans the selected workspace plus global, and `--scope all` never scans every workspace under a root.

### Agent Usage Pattern
- Start or resume a task with `.venv/bin/memwiz context --format json` for the selected workspace so the agent loads bounded workspace and global context before acting.
- Prefer `.venv/bin/memwiz remember --format json` over manual `capture` when the agent needs to save durable knowledge on demand.
- Save high-signal items only: reusable workflows, durable constraints, warnings, decisions, and stable facts or preferences that will matter again.
- Prefer non-agent evidence sources such as `command`, `doc`, `file`, `test`, or `user` when available. The default balanced policy is more willing to auto-accept those than pure agent assertions.
- After autonomous writes, before handoff, or whenever `remember` reports follow-up reason codes, inspect `.venv/bin/memwiz status --format json` and `.venv/bin/memwiz audit --format json`.
- Do not save one-off task status updates, filler chatter, unsupported guesses, duplicate memories, or secret-like content.
- Keep `promote` manual and conservative. Only promote accepted workspace memories that deserve cross-workspace reuse.
