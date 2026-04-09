# Repository Guidelines

## Project Structure & Module Organization
Root files such as `README.md` and `pyproject.toml` define the development workspace. Shipped skill code lives under `src/memwiz/`. Keep CLI wiring in `src/memwiz/cli.py`, command handlers in `src/memwiz/commands/`, and shared logic in focused modules such as `config.py`, `models.py`, `storage.py`, `scoring.py`, and `dedupe.py`. Tests live in `tests/` and should mirror the behavior they cover, for example `tests/test_promote.py` or `tests/test_storage.py`.

Keep `src/` as the shipped skill root. Treat `ai/` as planning and design workspace; only current-state documents belong in git. Do not commit generated artifacts such as `__pycache__/`, `*.egg-info/`, or local lockfiles unless the repo explicitly adopts them.

## Build, Test, and Development Commands
- `python3 -m pip install -e .`: install an editable local `memwiz` CLI.
- `python3 -m pytest -q`: run the full automated test suite.
- `python3 -m pytest tests/test_promote.py -q`: run a focused test slice while iterating.
- `memwiz --help`: inspect the CLI surface after editable install.

There is no separate build pipeline yet beyond setuptools packaging in `pyproject.toml`.

## Coding Style & Naming Conventions
Target Python `>=3.11`. Use 4-space indentation, type hints, and descriptive `snake_case` names for modules, functions, and tests. Keep one primary behavior per command module under `src/memwiz/commands/`. Prefer small, explicit helpers over broad utility layers, and keep file contents ASCII unless a dependency requires otherwise.

## Testing Guidelines
Use `pytest` for all coverage. Add or update tests with every behavior change, especially around CLI contracts, schema validation, storage transitions, scoring policy, and promotion rules. Name tests after observable behavior, such as `test_capture_rejects_secret_like_input_before_write`. Run `python3 -m pytest -q` before merging.

## Commit & Pull Request Guidelines
History uses Conventional Commit prefixes such as `feat:`, `fix:`, `docs:`, and `chore:`. Keep subjects imperative and scoped to one behavior change. Pull requests should summarize user-visible changes, call out CLI or schema impacts, and include the verification command used, usually `python3 -m pytest -q`. Releases follow SimVer.

## Agent-Specific Notes
This repository is an agent-agnostic memory skill. Preserve the current model: workspace capture is explicit, global memory promotion is explicit, and memory should stay lightweight rather than grow without bound.
