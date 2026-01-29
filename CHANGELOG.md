# Changelog

All notable changes to this project will be documented in this file.

This project does not yet backfill historical releases. Entries start at the
point the changelog was introduced.

## 0.1.1

### Changed
- Logging always writes to the configured log_file in main.conf (no CLI override).

## 0.1.0

### Added
- File logging to a configurable log file (default `/var/log/geppetto/geppetto.log`).
- `remote_file` can compare S3 ETags to skip downloads (`compare = "etag"`).

## 0.0.10

### Added
- `group` resources can specify `gid`.

## 0.0.9

### Added
- `user` resources can specify `uid` and `gid`.

## 0.0.8

### Added
- `git_pull` operation for deploying repositories to a destination path.
- Support list titles for `file` resources in the DSL.
- CLI version flag (`-V`/`--version`).

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
