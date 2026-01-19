# Changelog

All notable changes to this project will be documented in this file.

This project does not yet backfill historical releases. Entries start at the
point the changelog was introduced.

## 0.0.7

### Added
- CA certificate management for OS trust stores and Java cacerts (with rollback support).
- Conditional nested actions via `on_success` and `on_failure`.
- File resources can ensure directories.

### Changed
- Rollback actions now appear in CLI results/summary.

### Fixed
- Suppress stack traces in non-debug runs and clean progress output on errors.
- Log failed exec commands when `--log-level DEBUG` is enabled.

## 0.0.6

- Historical release (changes not documented).
