# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

### Added
- Describe new features here.

### Changed
- Describe behavior or compatibility changes here.

### Fixed
- Describe bug fixes here.

### Removed
- Describe removed features or deprecated behavior here.

### Performance
- Describe speed, memory, or efficiency improvements here.

### Docs
- Describe documentation-only updates here.

### Tests
- Describe test coverage or test infrastructure updates here.

### CI
- Describe workflow or release automation updates here.

### Refactor
- Describe internal-only code changes here.

### Chore
- Describe maintenance tasks, dependency updates, and release prep here.

## 2.1.5 - 2026-08-16

### Changed
- Bumped the package version across Python metadata, CLI output, docs, and website copy.
- Updated the Homebrew formula to the `2.1.5` source tarball and checksum.
- Switched the GitHub PyPI workflow to build with `twine` using `PYPI_API_TOKEN`.

### Fixed
- Improved the model selection and workspace config flow.
- Reduced the number of unnecessary clarification prompts for task execution.
- Merged generated MCP config with existing `.vscode/mcp.json` content instead of overwriting it.
