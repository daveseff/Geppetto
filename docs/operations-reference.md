# Operations reference

Each DSL resource maps to an operation with specific options. This reference lists the supported operations and their parameters. Unless stated otherwise, string values are required when present. Boolean flags accept `true/false/yes/no/1/0`.

## Table of contents

- [authorized_key](#authorized_key)
- [block_device](#block_device)
- [ca_cert](#ca_cert)
- [cron](#cron)
- [efs_mount](#efs_mount)
- [exec](#exec)
- [file](#file)
- [limits](#limits)
- [network_mount](#network_mount)
- [package](#package)
- [profile_env](#profile_env)
- [remote_file](#remote_file)
- [rpm](#rpm)
- [service](#service)
- [sysctl](#sysctl)
- [timezone](#timezone)
- [user](#user)
- [yum_repo](#yum_repo)
- [Plugin operations](#plugin-operations)

## authorized_key
- `user` (string): account to modify. Required.
- `key` (string): SSH public key. Required.
- `name` (string): label (used as resource name).

## block_device
- `device` (string): e.g., `/dev/xvdf` (optional if `volume_id` or `device_name` given).
- `volume_id` (string): block volume identifier (optional).
- `device_name` (string): device hint (optional).
- `mount_point` (string): absolute path. Required.
- `filesystem` (string, default `xfs`).
- `mount_options` (list|string, default `defaults`).
- `state` (present|absent, default present).
- `mkfs` (bool, default true): format if needed.
- `mount` (bool, default true): ensure mounted.
- `fstab` (string, default `/etc/fstab`).
- `wait_attempts` (int, default 60): polling attempts for device availability.
- `wait_interval` (int, default 5): seconds between polls.

## ca_cert
- `path` (string): local certificate path.
- `source` (string): URI or local path to fetch.
- `state` (present|absent, default present).
- `alias` (string): Java keystore alias (defaults to filename stem).
- `os_trust_dir` (string): override OS trust store dir.
- `java_keystore` (string): override Java cacerts path.
- `java_storepass` (string): keystore password (default `changeit`).

## cron
- `name` (string): job identifier. Required.
- `minute` `hour` `day` `month` `weekday` (strings): schedule fields (`*`, ranges, lists).
- `user` (string): run as user. Required.
- `command` (string): command line. Required.
- `state` (present|absent, default present).
- `env` (map): environment variables.

## efs_mount
- `filesystem_id` (string): EFS ID. Required.
- `mount_point` (string): absolute path. Required.
- `mount_options` (list|string, default `tls,_netdev`).
- `state` (present|absent, default present).
- `mount` (bool, default true): ensure mounted.
- `fstab` (string, default `/etc/fstab`).

## exec
- `command` (string|list): command to run. Required.
- `creates` (string): skip if path exists.
- `only_if` (string): run only if command succeeds.
- `unless` (string): skip if command succeeds.
- `cwd` (string): working directory.
- `env` (map or list of `KEY=value`): environment.
- `timeout` (int): seconds.
- `returns` (list|int): allowed exit codes.

## file
- `path` (string): target path. Required.
- `state` (present|absent|directory, default present).
- `content` (string): literal content (ignored if `template` is set).
- `template` (string): path to template (relative to plan dir if not absolute).
- `variables` (map): template variables; supports secrets.
- `mode` (int or string): file or dir mode.
- `link_target`/`target` (string): create/manage a symlink.
- `owner` (user or uid): POSIX owner.
- `group` (group or gid): POSIX group.

## limits
- `name` (string): file name (without `.conf`). Required.
- `state` (present|absent, default present).
- `entries` (list of maps): each with `domain`, `type` (soft|hard), `item` (e.g., `nofile`), `value`.
- OR single-entry shorthand: `domain`, `type`, `item`, `value`.
- `mode` (int or string, default `0644`).
- `path` (string, default `/etc/security/limits.d/<name>.conf`).

## network_mount
- `source` (string): e.g., `server:/export`. Required.
- `mount_point` (string): absolute path. Required.
- `fstype` (string, default `nfs`).
- `mount_options`/`options` (list|string, default `defaults`).
- `state` (present|absent, default present).
- `mount` (bool, default true): ensure mounted.
- `fstab` (string, default `/etc/fstab`).

## package
- `packages` (list or string): package names.
- `state` (present|absent, default present).
- `manager` (optional): force a specific package manager.

## profile_env
- `name` (string): base name. Required.
- `state` (present|absent, default present).
- `format` (profile|systemd, default profile).
- `variables` (map): key/value pairs. Required when present.
- `mode` (int or string, default `0644`).
- `path` (string, default `/etc/profile.d/<name>.sh` or `/etc/systemd/system/<name>.d/env.conf`).

## remote_file
- `source` (string): URI or local path. Required.
- `dest` (string): destination path. Required.
- `mode` (int or string): file mode.
- `variables` (map): template variables for templated sources.
- `headers` (map): HTTP headers (for http/https sources).

## rpm
- `name` (string): package name. Required.
- `source` (string): URL/path to RPM. Required.

## service
- `name` (string): service name. Required.
- `enabled` (bool): enable/disable on boot.
- `state` (running|stopped): ensure runtime state.

## sysctl
- `name` (string): key, e.g., `net.ipv4.ip_forward`. Required.
- `value` (string|int): value to set. Required.
- `persist` (bool, default true): write to `/etc/sysctl.d`.
- `path` (string, default `/etc/sysctl.d/99-geppetto.conf`).

## timezone
- `zone` (string): timezone name (e.g., `Australia/Brisbane`). Required.

## user
- `name` (string): username. Required.
- `shell` (string): login shell.
- `comment` (string): gecos/comment.
- `system` (bool): create as system user.
- `locked` (bool): lock password.
- `state` (present|absent, default present).

## yum_repo
- `name` (string): repo id. Required.
- `state` (present|absent, default present).
- `baseurl` (string): repository URL.
- `mirrorlist` (string): mirrorlist URL (baseurl or mirrorlist required when present).
- `enabled` (bool, default true).
- `gpgcheck` (bool, default true).
- `repo_gpgcheck` (bool, optional).
- `gpgkey` (string): URL/path to GPG key.
- `metadata_expire` (string): e.g., `6h`.
- `description` (string): repo name (default: name).
- `options` (map): extra key/value pairs.
- `mode` (int or string, default `0644`).
- `path` (string, default `/etc/yum.repos.d/<name>.repo`).

## Plugin operations

Plugins can add custom operations at runtime by registering with `OPERATION_REGISTRY`. See `docs/custom-plugins.md` for plugin authoring.
