# ForgeOps Automation

A lightweight Python automation toolkit that covers both "server/agent" and "server-less" execution models. The current drop focuses on local (server-less) execution, laying the groundwork for daemonized agents by using executor abstractions throughout the code.

## Highlights

- Minimal dependencies (standard library only) for quick bootstrapping.
- Declarative plan files written in TOML describing hosts, tasks, and actions.
- Pluggable executor abstraction – today a `LocalExecutor`, with hooks for future agent/server transport.
- First-class operations for package installation/removal and file management.
- Built-in dry-run flag so you can validate idempotent behavior before touching a node.

## Project layout

```
pyproject.toml                 # Packaging metadata and CLI entrypoint
src/forgeops_automation/       # Python package with runners, executors, operations, and DSL parser
examples/base_plan.fops        # Sample Puppet-like DSL plan
examples/base_plan.toml        # Legacy TOML plan definition
```

### Plans

Plans can be expressed either as TOML (for compatibility) or via a Puppet-inspired DSL that favors structured resources. A DSL example (`examples/base_plan.fops`):

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

  user { 'forgeops':
    shell  => '/bin/bash'
    locked => true
  }

  authorized_key { 'forgeops-admin':
    user => 'forgeops'
    key  => 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCexample forgeops'
  }

  file { '/tmp/motd':
    ensure  => present
    mode    => '0644'
    template => 'examples/templates/motd.tmpl'
  }
}
```

Each resource block becomes an action (`package`, `file`, `service`, `user`, `authorized_key`, etc.). Attributes such as `ensure => present` map directly onto the corresponding operation's parameters (e.g., `state`). File resources understand optional `template` attributes: the referenced file (relative or absolute path) is rendered via Python's `string.Template` using host variables (from the `node` definition) plus any per-resource `variables` (available in TOML plans). Relative template paths resolve against the directory containing the plan file, so `/etc/forgeops/plan.fops` can naturally reference `/etc/forgeops/templates/...`. Service resources map onto `systemctl`, user resources wrap `useradd/usermod/userdel`, and `authorized_key` resources keep SSH keys idempotent (with automatic base64 decoding). If the loader detects a `.fops` extension (or the DSL syntax), it automatically uses the DSL parser; `.toml` continues to be supported for existing plans.

## Usage

1. Install the project (editable is convenient during development):

   ```bash
   pip install -e .
   ```

2. Run the CLI against a plan:

   ```bash
   forgeops-auto examples/plan.fops --dry-run
   ```

3. Drop the `--dry-run` flag when you are ready to apply changes locally.

The CLI returns zero on success and prints a concise status line per host/action pair. If you provide no path argument the runner defaults to `/etc/forgeops/plan.fops`, and relative template references resolve beneath `/etc/forgeops` (or whatever directory the plan lives in).

### Tests

Unit tests live under `tests/` and use `pytest`:

```bash
PYTHONPATH=src pytest
```

The suite covers the inventory loader, file and package operations, and runner plumbing so regression signals stay quick.

### System CLI script

For environments where you want a simple `/usr/bin/forgeops-auto`, ship the `scripts/forgeops-auto` helper along with the installed package. The script is a tiny Python entry point that calls `forgeops_automation.cli.main`, so placing it in your `$PATH` (or symlinking it) immediately exposes the same flags as the packaged console entry point.

### RPM packaging helper

Need to ship your automation bits as an RPM (RHEL 8 / Amazon Linux 2023)? First build a payload that mirrors `/usr/bin` + `/usr/lib` by running:

```bash
scripts/build_payload.sh --payload build/payload
```

The helper builds the wheel (plus dependencies) and installs it into `build/payload/usr/...`, so the CLI and library files are staged exactly where the RPM expects them.

Then wrap the payload:

```bash
scripts/build_rpm.sh --name forgeops-auto --version 0.1.0 --payload build/payload \
  --summary "ForgeOps CLI" --description "Lightweight automation helper" \
  --dist-tag .amzn2023
```

The script wraps `rpmbuild`, autogenerates a spec file, and drops the finished RPM in `./dist/`. Additional flags let you set release numbers, scriptlets, vendor/URL metadata, distro suffixes (e.g. `--dist-tag .amzn2023`), and custom work/output directories.

## Extending toward agents or server mode

- Executors live in `src/forgeops_automation/executors.py`. Implement a subclass that knows how to talk to your agent (gRPC, SSH, message bus, etc.) and return it from `TaskRunner._executor_for` for connection types such as `agent` or `server`.
- Operations are regular Python classes. Additional actions – service management, templating, orchestration hooks – can be registered by adding them to `OPERATION_REGISTRY`.

## Next ideas

- Inventory caching and fact gathering for agent-based runs.
- State reporting endpoint so a controller can fan out work to remote agents.
- Unit tests around the package and file operations.
- Support for templated file content (Jinja) and richer package providers (pip, npm, etc.).
