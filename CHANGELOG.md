# Changelog

All notable changes to this project will be documented in this file.

This project does not yet backfill historical releases. Entries start at the
point the changelog was introduced.

## 0.2.1

### Fixed
- Suppressed `INFO geppetto - ... changed=False details=noop` lines for
  unchanged operations at the default log level. Noop results now log at
  `DEBUG`, while changed results remain at `INFO` and failures remain at
  `ERROR`.

## 0.2.0

### Added
- REST-backed config synchronization via `config_service_url` and
  `config_service_path`. Agents can download host-specific config bundles before
  loading the plan.
- mTLS support for the REST config service, including CA trust, client
  certificate, and client key configuration.
- Puppet-style agent certificate enrollment:
  - fetch the server CA into `/etc/geppetto/pki/ca.crt` by default
  - generate `/etc/geppetto/pki/<hostname>.key`
  - generate and submit `/etc/geppetto/pki/<hostname>.csr`
  - download the signed client certificate after server approval
- Agent certificate CLI commands:
  - `geppetto-auto cert init`
  - `geppetto-auto cert status`
  - `geppetto-auto cert clean`
- `config_service_host` to override the hostname used for bundle selection and
  certificate enrollment.
- Default REST/mTLS PKI paths under `/etc/geppetto/pki` when explicit
  certificate paths are omitted.
- Root-level Arch Linux packaging under `packaging/`, allowing `makepkg -si`
  directly from `Geppetto/packaging`.

### Changed
- Bumped the agent package version to `0.2.0`.
- Documented REST config service enrollment and root-level packaging in the
  README and sample config.
- Config source validation now rejects simultaneous use of Git-backed config
  sync and REST-backed config service sync.

### Fixed
- Missing CA/client certificate files now trigger certificate bootstrap instead
  of a raw `FileNotFoundError` from TLS context creation.

## 0.1.3

### Fixed
- `remote_file` supports `verify_tls` for HTTPS sources; set `verify_tls = false` to allow self-signed certificates.

## 0.1.2

### Fixed
- Clear previous progress line before printing a shorter pending status line.

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
