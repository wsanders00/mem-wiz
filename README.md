# mem-wiz

This repository keeps development files at the root and is organized so the
skill bundle can be released from `src/mem-wiz/`.

- The repository root holds contributor-facing files such as `README.md`,
  `AGENTS.md`, `pyproject.toml`, `tests/`, and local planning material under
  ignored `ai/`.
- `src/mem-wiz/` is the intended release boundary. Release artifacts should
  package the contents of this directory so unpacked bundles expose `SKILL.md`
  and `memwiz/` at archive root.
- `src/mem-wiz/memwiz/` contains the runtime Python package and the `memwiz`
  CLI entrypoint used for editable installs.
- `python3 scripts/build_skill_artifact.py` writes a zip under `dist/` using
  the contents of `src/mem-wiz/` as the archive root.
