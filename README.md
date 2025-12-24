# Geppetto Automation

A lightweight Python automation toolkit that covers both "server/agent" and "server-less" execution models. The current drop focuses on local (server-less) execution, laying the groundwork for daemonized agents by using executor abstractions throughout the code.

## Highlights

- Minimal dependencies (standard library only) for quick bootstrapping.
- Declarative plan files written in TOML describing hosts, tasks, and actions.
- Pluggable executor abstraction – today a `LocalExecutor`, with hooks for future agent/server transport.
- First-class operations for package installation/removal and file management.
- New `exec` resource to mirror Puppet's `exec` (guards, `creates`, env, cwd, allowed return codes).
- Built-in dry-run flag so you can validate idempotent behavior before touching a node.
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

Each resource block becomes an action (`package`, `file`, `service`, `user`, `authorized_key`, `remote_file`, `rpm`, `efs_mount`, `network_mount`, `block_device`, `timezone`, `sysctl`, `cron`, `limits`, `profile_env`, `yum_repo`, etc.). Attributes such as `ensure => present` map directly onto the corresponding operation's parameters (e.g., `state`). File resources understand optional `template` attributes or `link_target` (to manage symlinks), support `owner`/`group`, and can also ensure directories when `ensure => directory`. Actions may also carry `on_success` and `on_failure` blocks of nested actions: `on_success` runs only when the parent changes without failing; `on_failure` runs only when the parent fails. Referenced files render using host variables plus per-resource `variables`. Templates accept either `$var`/`${var}` placeholders or Jinja control flow like:

```
allowed_hosts:
{% for host in allowed_hosts %}
  - {{ host }}
{% endfor %}
```

Secrets can be injected at render time by pointing variables at AWS Secrets Manager:

```
file { '/etc/app/config':
  template => 'templates/app.conf.j2'
  variables => {
    db_password = { aws_secret = 'prod/db', key = 'password' }
  }
}
```

With JSON secrets, set `key` to the field name; string secrets are used as-is. Requires `boto3` on the runner host.

Relative template paths resolve against the directory containing the plan file, so `/etc/geppetto/plan.fops` can naturally reference `/etc/geppetto/templates/...`. Service resources map onto `systemctl`, user resources wrap `useradd/usermod/userdel`, `authorized_key` resources keep SSH keys idempotent (with automatic base64 decoding), filesystem operations manage `/etc/fstab` entries plus `mount`/`umount` steps for both EFS and block devices, `remote_file` fetches artifacts from local paths/S3/HTTP, `rpm` downloads + installs RPMs when they aren’t already present, `timezone` sets `/etc/localtime`, `sysctl` manages kernel tunables, and `cron` manages `/etc/cron.d` jobs. DSL plans can also include additional files via `include 'relative/path.fops'` directives; include paths resolve relative to the parent plan. Resources can coordinate ordering by setting `depends_on => ['user.geppetto']`, ensuring dependent actions run after their prerequisites (and before them during cleanup).

The `examples/config/` tree shows a layered defaults -> groups -> hosts layout; the top-level `examples/plan.fops` simply includes `config/hosts/host1/plan.fops` to keep CLI examples stable.

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

The CLI returns zero on success and prints a concise status line per host/action pair. If you provide no path argument the runner defaults to `/etc/geppetto/plan.fops`, and relative template references resolve beneath `/etc/geppetto` (or whatever directory the plan lives in). Each run also maintains a state file (`plan.fops.state.json` by default) so that removing a resource from the plan automatically triggers the appropriate teardown (file removal, user deletion, unmounts, etc.). You can override the state location via `--state-file`.

### Tests

Unit tests live under `tests/` and use `pytest`:

```bash
PYTHONPATH=src pytest
```

The suite covers the inventory loader, file and package operations, and runner plumbing so regression signals stay quick.

### System CLI script

For environments where you want a simple `/usr/bin/geppetto-auto`, ship the `scripts/geppetto-auto` helper along with the installed package. The script is a tiny Python entry point that calls `geppetto_automation.cli.main`, so placing it in your `$PATH` (or symlinking it) immediately exposes the same flags as the packaged console entry point.

### RPM packaging

Current workflow (no helper scripts):

1. Build a source tarball:

   ```bash
   python3 -m pip install --upgrade build  # once per machine
   python3 -m build --sdist
   ```

   This produces `dist/geppetto_automation-<version>.tar.gz`.

2. On your RPM build host, place the tarball where `rpmbuild` expects it and rename to match `Source0` in `geppetto_automation.spec` (underscores):

   ```bash
   cp dist/geppetto_automation-<version>.tar.gz ~/rpmbuild/SOURCES/geppetto_automation-<version>.tar.gz
   ```

3. Build the RPM:

   ```bash
   rpmbuild -bb geppetto_automation.spec
   ```

The resulting RPM will land under `~/rpmbuild/RPMS/` (or whatever `%_rpmdir` is set to). Adjust version/release inside `geppetto_automation.spec` before building.

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

A simple `makepkg` flow using the sample PKGBUILD under `examples/packaging/`:

```bash
sudo pacman -S --needed base-devel python-build python-installer python-wheel python-hatchling
python3 -m build --sdist                     # creates dist/geppetto-automation-<ver>.tar.gz
cp dist/geppetto_automation-*.tar.gz examples/packaging/
cd examples/packaging
makepkg -sf                                  # builds a .pkg.tar.zst (run as a normal user)
sudo pacman -U ./*.pkg.tar.zst               # install system-wide
```

Adjust `pkgver` in `examples/packaging/PKGBUILD` to match the sdist. The PKGBUILD uses system Python tooling (hatchling backend) and installs via `python -m installer`, and it seeds `/etc/geppetto` with sample config/plan/templates.

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
# If your configs live in a separate Git repo, Geppetto will clone/fetch+reset it here
# before each run (including dry-runs), discarding local edits to match origin.
# config_repo_path = "/etc/geppetto/config"
# config_repo_url  = "git@github.com:yourorg/geppetto-config.git"
# Optional plugins: modules or .py files that expose register_operations(registry)
# to add custom resources.
# plugin_modules = ["yourpackage.geppetto_plugins"]
# plugin_dirs = ["/etc/geppetto/plugins"]
# (See examples/plugins/custom_ops.py for a starter plugin.)
```

Values supplied on the CLI always win, but the config file lets you centralize shared settings (plan/state/template directories) across hosts.

## Plugins

Geppetto can load external Python modules to add new operations at runtime. List importable modules via `plugin_modules` or point `plugin_dirs` at folders of standalone `.py` files; each module/file should export `register_operations(registry)` to add new operation classes. See `docs/custom-plugins.md` for authoring guidance and examples. A growing catalog of ready-to-use plugins lives at https://github.com/daveseff/Geppetto_Plugins.
