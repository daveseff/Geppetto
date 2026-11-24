# Geppetto Automation

A lightweight Python automation toolkit that covers both "server/agent" and "server-less" execution models. The current drop focuses on local (server-less) execution, laying the groundwork for daemonized agents by using executor abstractions throughout the code.

## Table of contents

- [Highlights](#highlights)
- [Project layout](#project-layout)
  - [Plans](#plans)
- [Usage](#usage)
- [Extending toward agents or server mode](#extending-toward-agents-or-server-mode)
- [Next ideas](#next-ideas)
- [Plugins](#plugins)

## Highlights

- Minimal dependencies (standard library only) for quick bootstrapping.
- Declarative plan files written in TOML describing hosts, tasks, and actions.
- Pluggable executor abstraction – today a `LocalExecutor`, with hooks for future agent/server transport.
- First-class operations for package installation/removal and file management.
- New `exec` resource to mirror Puppet's `exec` (guards, `creates`, env, cwd, allowed return codes).
- Built-in dry-run flag so you can validate idempotent behavior before touching a node.
- Resource import can inspect an existing user crontab and emit ready-to-paste DSL.
- File templates support both `$var` substitution and Jinja (`{{ }}` / `{% %}`) for loops and conditionals, including values pulled from AWS Secrets Manager.
- Optional plugins so you can ship new operations without forking core.

## Project layout

```
pyproject.toml                 # Packaging metadata and CLI entrypoint
src/geppetto_automation/       # Python package with runners, executors, operations, and DSL parser
examples/plan.fops             # Sample Puppet-like DSL plan (delegates to config/hosts/host1/plan.fops)
examples/config/               # Layered defaults/groups/hosts example hierarchy
```

### Plans

Plans can be expressed either as TOML (for compatibility) or via a Puppet-inspired DSL that favors structured resources. A DSL example (`examples/plan.fops`):

```
node 'local' {
  connection => local
}

task 'bootstrap' on ['local'] {
  package { ['git', 'python3']:
    ensure => present
  }

  service { 'sshd':
    enabled => true
    state   => running
  }

  user { 'geppetto':
    shell  => '/bin/bash'
    locked => true
  }

  authorized_key { 'geppetto-admin':
    user => 'geppetto'
    key  => 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCexample geppetto'
  }

  remote_file { 'bootstrap-script':
    source => 's3://geppetto-artifacts/bootstrap.sh'
    dest   => '/usr/local/bin/bootstrap.sh'
    mode   => '0755'
    # verify_tls => false  # optional for HTTPS sources with self-signed certs
  }

  rpm { 'amazon-ssm-agent':
    name   => 'amazon-ssm-agent'
    source => 'https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/linux_amd64/amazon-ssm-agent.rpm'
  }

  file { '/tmp/motd':
    ensure  => present
    mode    => '0644'
    template => 'examples/config/templates/motd.tmpl'
  }

  exec { 'seed-db':
    command => '/usr/local/bin/seed --once'
    creates => '/var/lib/app/.seeded'
    only_if => 'test -x /usr/local/bin/seed'
    env     => ['ENV=staging']
    timeout => 120
  }
}
```

include 'shared/common.fops'

```

`exec` runs commands through `/bin/sh -c` when given a string, supports `creates` skip files, `only_if`/`unless` guards, `cwd`, per-command `env` (list of `KEY=value` or a map), allowed `returns` codes, and `timeout` in seconds.

Each resource block becomes an action (`package`, `file`, `git_pull`, `group`, `service`, `user`, `authorized_key`, `ca_cert`, `remote_file`, `rpm`, `efs_mount`, `network_mount`, `block_device`, `timezone`, `sysctl`, `cron`, `limits`, `profile_env`, `yum_repo`, etc.). Attributes such as `ensure => present` map directly onto the corresponding operation's parameters (e.g., `state`). File resources understand optional `template` attributes or `link_target` (to manage symlinks), support `owner`/`group`, and can also ensure directories when `ensure => directory`. Actions may also carry `on_success` and `on_failure` blocks of nested actions: `on_success` runs only when the parent changes without failing; `on_failure` runs only when the parent fails. Referenced files render using host variables plus per-resource `variables`. Templates accept either `$var`/`${var}` placeholders or Jinja control flow like:

```
allowed_hosts:
{% for host in allowed_hosts %}
  - {{ host }}
{% endfor %}
```

### Importing an existing crontab

Generate a task from a user's current crontab:

```sh
geppetto-auto import cron alice
```

The command only reads the host and writes DSL to standard output. It emits one independently managed `cron` resource per job, including standard schedules and `@daily`-style entries. Environment assignments active before a job are included in that resource. Paste the task into the plan and run Geppetto normally. Because each generated entry matches a job already installed, the first run is a no-op and records the resources in Geppetto's state instead of creating duplicates.

The emitted task uses the machine's detected hostname. Use `--host HOST` only to override that node name, or `--task-name NAME` to override the generated task name. Import currently operates on the local machine.

To import every local user's crontab in one task, run as an account permitted to read them (normally root):

```sh
geppetto-auto import cron --all-users
```

Accounts without cron jobs are skipped. Any other read error stops the import rather than silently producing an incomplete plan.

Secrets can be injected at render time by pointing variables at AWS Secrets Manager:

```
file { '/etc/app/config':
  template => 'templates/app.conf.j2'
  variables => {
    db_password = { aws_secret = 'prod/db', key = 'password' }
  }
}
```

File resources can also take a list of paths to apply the same attributes:

```
file { [
  '/apps/bmg/data',
  '/apps/bmg/data/done',
  '/apps/bmg/data/error',
]:
  ensure => directory
  mode   => '0755'
}
```

With JSON secrets, set `key` to the field name; string secrets are used as-is. Requires `boto3` on the runner host.

Relative template paths resolve against the directory containing the plan file, so `/etc/geppetto/plan.fops` can naturally reference `/etc/geppetto/templates/...`. Service resources map onto `systemctl`, user resources wrap `useradd/usermod/userdel`, `authorized_key` resources keep SSH keys idempotent (with automatic base64 decoding), filesystem operations manage `/etc/fstab` entries plus `mount`/`umount` steps for both EFS and block devices, `remote_file` fetches artifacts from local paths/S3/HTTP, `rpm` downloads + installs RPMs when they aren’t already present, `timezone` sets `/etc/localtime`, `sysctl` manages kernel tunables, and `cron` manages `/etc/cron.d` jobs. DSL plans can also include additional files via `include 'relative/path.fops'` directives; include paths resolve relative to the parent plan. Resources can coordinate ordering by setting `depends_on => ['user.geppetto']`, ensuring dependent actions run after their prerequisites (and before them during cleanup).

The `examples/config/` tree shows a layered defaults -> groups -> hosts layout. With Geppetto Server, declare membership in each host's node, for example `node 'host2' { groups = ['staging', 'database'] }`. If `groups` is omitted or empty, the host has no group membership. The server always publishes defaults, publishes only the named group directories, and adds the requesting host's files. Use `on ['*']` for default tasks. A group task can target every member with `on ['host2', 'host3']`, or be limited to one member with (for example) `on ['host3']`.

An EFS mount example:

```

efs_mount { 'logs':
filesystem_id => 'fs-abc123'
mount_point => '/mnt/logs'
mount_options => ['tls', '_netdev']
}

```

And a block device formatted and mounted by UUID:

```

block_device { 'data':
volume_id => 'vol-0abc123'
device_name => 'xvdf'
mount_point => '/srv/data'
filesystem => 'xfs'
mkfs => true
}

```

Package resources accept `ensure => present` (install only if missing),
`ensure => absent` (remove), or `ensure => latest` (install or upgrade):

```
package { 'splunkforwarder':
  ensure => latest
  on_success => {
    exec { 'after-splunk-upgrade':
      command => '/usr/local/bin/configure-splunk'
    }
  }
}
```

`latest` supports apt, dnf, yum, Homebrew, and pacman. Already-current
packages report no change; successful installs or version changes trigger
`on_success`. Dry runs check for updates without installing or upgrading.
Versions follow the configured repositories and package-manager policies.
Geppetto does not explicitly refresh repository metadata: apt and pacman use
their existing indexes, while dnf, yum, and Homebrew follow their normal
metadata behavior. Manage index refreshes separately; on Arch, maintain the
normal full-system upgrade workflow rather than refreshing indexes solely for
a partial package upgrade.

Conditional follow-up actions:

```
exec { 'set-crypto-policy':
  command => '/usr/bin/update-crypto-policies --set DEFAULT:AD-SUPPORT'
  unless  => "/usr/bin/update-crypto-policies --show | /usr/bin/grep -Fq 'AD-SUPPORT'"
  on_success => {
    exec { 'apply_authselect_profile':
      command => 'authselect apply-changes'
    }
  }
  on_failure => {
    exec { 'rollback_policy':
      command => '/usr/bin/update-crypto-policies --set DEFAULT'
    }
  }
}
```

CA cert management (OS + Java):

```
ca_cert { 'corp-root':
  path          => 'files/certs/corp-root.pem'
  alias         => 'corp-root'
  java_keystore => '/etc/pki/java/cacerts'
}
```

A generic (non-EFS) network mount:

```

network_mount { 'nfs-share':
source => '10.0.0.5:/exports/app'
mount_point => '/mnt/app'
fstype => 'nfs4'
mount_options => ['_netdev', 'rw']
}

````

Block-device mounts accept either a direct `/dev/...` path or a `volume_id`/`device_name` pair; the runner waits for the attachment to appear (checking AWS-style `/dev/disk/by-id` aliases) before formatting and mounting it, which keeps the same robustness as the original shell helper.

If the loader detects a `.fops` extension (or the DSL syntax), it automatically uses the DSL parser; `.toml` continues to be supported for existing plans.

## Usage

1. Install the project (editable is convenient during development):

   ```bash
   pip install -e .
````

2. Run the CLI against a plan:

   ```bash
   geppetto-auto examples/plan.fops --dry-run
   ```

3. Drop the `--dry-run` flag when you are ready to apply changes locally.

The CLI returns zero on success and prints a concise status line per host/action pair. If you provide no path argument the runner defaults to `/etc/geppetto/plan.fops`, and relative template references resolve beneath `/etc/geppetto` (or whatever directory the plan lives in). Each run also maintains a state file (`plan.fops.state.json` by default) so that removing a resource from the plan automatically triggers the appropriate teardown (file removal, user deletion, unmounts, etc.). You can override the state location via `--state-file`. Dry-runs read this state and preview those teardown actions, but never update the state file or the managed resources. Sequential crontab changes are simulated in memory so their dry-run results match apply ordering.

Dry-run results indent dependent resources four spaces per level, along with
their matching console log lines, using `\_` and label their declared
prerequisites. Unchanged prerequisites remain visible when a dependent resource
has changes. Indentation reflects dependency depth; the labels identify every
prerequisite when a resource has more than one. Live runs keep their flat output.
Conditional hooks are also shown beneath their parent resource.

For a user followed by dependent keys, the preview includes:

```text
prd-hvr-agent::user[ansible] changed - created
    \_ prd-hvr-agent::authorized_key[ansible-exec] changed - added (after planned user creation) ... (depends on: user.ansible)
    \_ prd-hvr-agent::authorized_key[ansible-management] changed - added (after planned user creation) ... (depends on: user.ansible)
```

Successful simulated user creation is shared with later key resources on the
same host, so they can preview additions before the real account exists. This
only affects dry-run: no accounts or keys are written. A key for a missing user
still fails if no earlier user creation was successfully simulated.

To apply just one of the changes shown by a dry-run, copy the `target=` address
from its result and pass it to `--target`:

```sh
geppetto-auto --dry-run
geppetto-auto --dry-run --target 'authorized_key.ansible-exec'
geppetto-auto --target 'authorized_key.ansible-exec'
# Repeat the flag for several resources, or qualify a target with its host:
geppetto-auto --target 'prd-hvr-agent::file./etc/sudoers.d/ansible' --target 'package.jq'
```

Targets accept `TYPE.NAME`, `HOST::TYPE.NAME`, or the stable resource ID. For a
file, NAME can be its path; for a key it is the resource title. An individual
package can be selected from a package list using `package.NAME`; the displayed
ID for a whole package list selects that entire list. Multiple selected members
of one list execute together so its hooks run once. Unqualified targets must
match uniquely; specify the host when several hosts declare the same resource.

Targeted runs automatically include transitive `depends_on` prerequisites,
including across tasks on the same host. Dependencies that already match the
host are checked as no-ops. Failed prerequisites skip dependent resources and
return a nonzero exit code. Selection rejects unknown or ambiguous references
and dependency cycles before applying resources. Only declared dependencies are
followed; prerequisites implicit in commands or external services must be
expressed using `depends_on`.

A selected resource retains its `on_success`/`on_failure` hooks. Their declared
external prerequisites are included conservatively, even if a hook ultimately
does not run. Hooks cannot be targeted directly: select their parent; hook
results display that parent target. Targeted runs disable automatic cleanup and
preserve all unselected state, including resources no longer in the plan. To
target a removal, keep the resource in the plan with `ensure => absent`.
`--target` cannot be combined with `--reconcile-state`. Configuration refresh
continues to follow the normal run rules; use `--skip-sync` to use the cached
plan. Review a full dry-run afterwards to see remaining changes.

Resource tracking uses stable target identities, independent of task order and
include-file paths. Package lists and multiline authorized-key resources are
tracked per package/key. Existing state files migrate automatically in memory;
normal apply saves the migrated state and dry-run leaves the file untouched.
Packages still declared in the plan are protected from stale-state cleanup.
Resources in conditional hooks remain managed even when the hook does not run.

To repair tracking after manual host changes, use the cached plan to reconcile
state against the local host without applying resources or running cleanup:

```sh
# Preview: no configuration refresh, log file writes, state writes or backups.
geppetto-auto --reconcile-state --dry-run
# If cached config is stale, refresh it BEFORE validation (writes config cache):
geppetto-auto --reconcile-state --dry-run --refresh-config
# Save after reviewing the preview (writes state and a timestamped backup only).
geppetto-auto --reconcile-state
```

Reconciliation defaults to cached configuration. If the server has corrected a
plan that now fails validation locally, add `--refresh-config` to download the
latest configuration before validation. This explicitly permits configuration
cache writes even with `--dry-run`; managed resources and state are still only
inspected. `--refresh-config` and `--skip-sync` cannot be combined. A refresh
failure stops the run before validation or reconciliation.

Reconciliation requires a plan scoped to one local host (the config-service
agent default already does this). It probes packages, files/directories/symlinks,
remote-file destinations, users, groups and authorized keys from both the plan
and previous state, including hook resources. Missing resources are dropped from
tracking; existing ones are adopted using stable IDs. Live resources removed from
the plan remain tracked so a later normal apply can still clean them up. It does
not import unrelated host resources or claim that contents, permissions or
versions match the plan. Other resource types are reported as unsupported and
retain their existing tracking. Query failures abort without saving state.
State writes are atomic, mode 0600; reconciliation first creates a timestamped
0600 backup beside an existing state file.

`--skip-sync` also allows a normal run or dry-run against cached configuration.
Normal `--dry-run` alone still refreshes configuration and writes its log as
before. Each `authorized_key` resource must contain exactly one public key. Plan
validation rejects multiple keys (including base64-encoded bundles) before any
resources are applied, including keys inside conditional hooks. Define separate,
uniquely named resources for multiple keys:

```text
authorized_key { 'ansible-exec':
  user => 'ansible'
  key => 'ssh-rsa AAA... execution key'
}
authorized_key { 'ansible-management':
  user => 'ansible'
  key => 'ssh-ed25519 AAA... management key'
}
```

Apply repairs exact duplicates of a managed key while preserving unrelated keys,
comments and SSH options. Legacy state containing multiple keys remains readable
and migrates into individually tracked keys.


### Tests

Unit tests live under `tests/` and use `pytest`:

```bash
PYTHONPATH=src pytest
```

The suite covers the inventory loader, file and package operations, and runner plumbing so regression signals stay quick.

### System CLI script

For environments where you want a simple `/usr/bin/geppetto-auto`, ship the `scripts/geppetto-auto` helper along with the installed package. The script is a tiny Python entry point that calls `geppetto_automation.cli.main`, so placing it in your `$PATH` (or symlinking it) immediately exposes the same flags as the packaged console entry point.

### RPM packaging

To build directly from the checked-out source tree, use RPM's build-in-place mode:

```bash
rpmbuild -bb --build-in-place geppetto-automation.spec
```

The resulting RPM will land under `~/rpmbuild/RPMS/` (or whatever `%_rpmdir` is set to). The `build.sh` helper runs the same command, and `./build.sh --install` installs the built package with `rpm -Uvh --force`.

The source-tarball workflow still works for source-RPM style builds: run `python3 -m build --sdist`, copy `dist/geppetto_automation-<version>.tar.gz` to `~/rpmbuild/SOURCES/geppetto_automation-<version>.tar.gz`, then run `rpmbuild -bb geppetto-automation.spec`.

### Debian/Ubuntu packaging (quick path)

A simple fpm-based build (no distro-native packaging files yet):

```bash
python3 -m pip install --upgrade build fpm  # once per machine
python3 -m build --sdist
fpm -s python -t deb --no-python-dependencies \
  --name geppetto_automation \
  dist/geppetto_automation-*.tar.gz
```

The command emits a `.deb` in the current directory. Install with `sudo dpkg -i geppetto_automation_*.deb`.

### Arch Linux packaging (native makepkg)

A simple `makepkg` flow using the PKGBUILD under `packaging/`:

```bash
sudo pacman -S --needed base-devel python-build python-installer python-wheel python-hatchling
cd packaging
makepkg -si
```

The PKGBUILD builds from the parent checkout, so it works directly from
`Geppetto/packaging` without manually creating an sdist first. It uses system
Python tooling (hatchling backend), installs via `python -m installer`, and
seeds `/etc/geppetto` with sample config/plan/templates.

## Extending toward agents or server mode

- Executors live in `src/geppetto_automation/executors.py`. Implement a subclass that knows how to talk to your agent (gRPC, SSH, message bus, etc.) and return it from `TaskRunner._executor_for` for connection types such as `agent` or `server`.
- Operations are regular Python classes. Additional actions – service management, templating, orchestration hooks – can be registered by adding them to `OPERATION_REGISTRY`.

## Next ideas

- Inventory caching and fact gathering for agent-based runs.
- State reporting endpoint so a controller can fan out work to remote agents.
- Unit tests around the package and file operations.
- Support for templated file content (Jinja) and richer package providers (pip, npm, etc.).

### Configuration

Geppetto reads `/etc/geppetto/main.conf` (TOML) for defaults. Example:

```
[defaults]
plan = "/etc/geppetto/plan.fops"
state_file = "/var/lib/geppetto/state.json"
template_dir = "/etc/geppetto/templates"
aws_region = "ap-southeast-2"
aws_profile = "default"
log_file = "/var/log/geppetto/geppetto.log"
# If your configs live in a separate Git repo, Geppetto will clone/fetch+reset it here
# before each run (including dry-runs), discarding local edits to match origin.
# config_repo_path = "/etc/geppetto/config"
# config_repo_url  = "git@github.com:yourorg/geppetto-config.git"
# REST config service. Agents bootstrap CA/client certs into /etc/geppetto/pki
# when cert paths are omitted, then submit a CSR to the server.
# config_service_url = "https://config.example.com:8443"
# config_service_path = "/etc/geppetto/config"
# config_service_host = "host1"
# Optional plugins: modules or .py files that expose register_operations(registry)
# to add custom resources.
# plugin_modules = ["yourpackage.geppetto_plugins"]
# plugin_dirs = ["/etc/geppetto/plugins"]
# (See examples/plugins/custom_ops.py for a starter plugin.)
```

Values supplied on the CLI always win, but the config file lets you centralize shared settings (plan/state/template directories) across hosts.

Agent certificate lifecycle commands:

```
geppetto-auto cert status
geppetto-auto cert init
geppetto-auto cert clean
```

`cert init` fetches the server CA, creates `/etc/geppetto/pki/<hostname>.key`
and a CSR, then submits it to the config server. After the server signs the CSR,
rerun `geppetto-auto` or `geppetto-auto cert init` to download the signed cert.

## Plugins

Geppetto can load external Python modules to add new operations at runtime. List importable modules via `plugin_modules` or point `plugin_dirs` at folders of standalone `.py` files; each module/file should export `register_operations(registry)` to add new operation classes. See `docs/custom-plugins.md` for authoring guidance and examples. A growing catalog of ready-to-use plugins lives at https://github.com/daveseff/Geppetto_Plugins.
