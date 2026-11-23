# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
`package.xml`.

## [Unreleased]

### Added
- Tooling: ruff and pytest configuration (`pyproject.toml`), pre-commit hooks,
  `.gitattributes`, this changelog.
- Test fixtures generator (`tests/fixtures/build_fixtures.py`) and frozen
  legacy files of version 0.1.0 (`tests/fixtures/legacy/v0.1.0`).

### Changed
- The version is read from `package.xml` only (`version.py`); the unused
  `VERSION = "1.0"` constants are gone.

## [0.1.0] - 2026-11-20

### Added
- First workbench release: freeze / relink, diagnostic, repair, visual
  insertion, local explorer, alignment, selection sets.
