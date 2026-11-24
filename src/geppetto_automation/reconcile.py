"""Rebuild tracking from live, plan-scoped resources without applying operations."""
from __future__ import annotations

from pathlib import Path
import grp
import pwd

from .executors import LocalExecutor
from .identity import plan_actions, state_actions
from .operations.authorized_key import AuthorizedKeyOperation
from .operations.package import PackageManagerFactory
from .state import DESTROY_BUILDERS
from .types import ActionResult, ActionSpec


class ProbeExecutor(LocalExecutor):
    """Reject mutation and distinguish failed inventory queries from missing packages."""

    def run(self, command, *, mutable=True, **kwargs):
        if mutable:
            raise RuntimeError("Reconciliation attempted a mutable command")
        result = super().run(command, mutable=False, **kwargs)
        if result.returncode not in (0, 1) or (command[0] == "rpm" and result.stderr.strip()):
            raise RuntimeError(f"Live query failed: {result.stderr.strip() or result.stdout.strip()}")
        return result


def live_spec(action, executor):
    """Return an observed spec, or None for a missing resource.

    Unknown resource types are deliberately not guessed: their tracking is retained.
    Only existence is reconciled; desired content/permissions remain plan inputs.
    """
    spec = dict(action.data)
    kind = action.type
    if kind == "package":
        manager = PackageManagerFactory.create(spec.get("manager"))
        exists = manager.is_installed(executor, spec["name"])
    elif kind in {"file", "remote_file"}:
        path = Path(spec.get("dest") or spec.get("path"))
        exists = path.exists() or path.is_symlink()
        if exists and kind == "file" and path.is_dir() and not path.is_symlink():
            spec["state"] = "directory"
    elif kind in {"user", "group"}:
        try:
            (pwd.getpwnam if kind == "user" else grp.getgrnam)(spec["name"])
            exists = True
        except KeyError:
            exists = False
    elif kind == "authorized_key":
        operation = AuthorizedKeyOperation(spec)
        try:
            record = operation.manager.get_user(operation.user)
        except ValueError:
            return None
        existing = operation._split_keys(operation.manager.read(record.home / ".ssh" / "authorized_keys"))
        exists = all(key in existing for key in operation.keys)
    else:
        raise NotImplementedError(f"live probe unavailable for {kind}; existing tracking retained")
    if not exists:
        return None
    if spec.get("state") != "directory":
        spec["state"] = "present"
    return spec


def reconcile_state(plan, store, *, dry_run=False):
    """Probe plan and prior state, preserving live orphans for future cleanup.

    Hooks are inspected as resources but never executed. No unmanaged host inventory
    is adopted: only resources in the plan or already tracked are considered.
    """
    if len(plan.hosts) != 1:
        raise ValueError("State reconciliation requires a plan scoped to exactly one local host")
    candidates = {}
    for host, entries in store.previous.items():
        candidates[host] = {
            key: ActionSpec(entry["action"], dict(entry["spec"]), entry.get("depends_on", []))
            for key, entry in entries.items()
        }
    for host, action in plan_actions(plan):
        if action.type not in DESTROY_BUILDERS:
            continue
        for item in state_actions(action):
            candidates.setdefault(host, {})[item.data["_resource_id"]] = item
    results = []
    failed = False
    for host, entries in candidates.items():
        if host not in plan.hosts:
            store.current[host] = dict(store.previous.get(host, {}))
            continue
        if plan.hosts[host].connection != "local":
            raise ValueError(f"State reconciliation requires a local host: {host}")
        executor = ProbeExecutor(plan.hosts[host], dry_run=True)
        for key, action in entries.items():
            try:
                observed = live_spec(action, executor)
            except NotImplementedError as exc:
                previous = store.previous.get(host, {}).get(key)
                if previous is not None:
                    store.current.setdefault(host, {})[key] = previous
                results.append(ActionResult(host, action.type, False, str(exc), resource=key))
                continue
            except Exception as exc:
                failed = True
                results.append(ActionResult(host, action.type, False, str(exc), failed=True, resource=key))
                continue
            if observed is not None:
                store.record(host, ActionSpec(action.type, observed, action.depends_on))
            results.append(ActionResult(host, action.type, False,
                "live: tracked" if observed is not None else "missing: not tracked", resource=key))
    if failed:
        raise RuntimeError("Live probes failed; state file was not changed: " +
                           "; ".join(f"{r.host}/{r.resource}: {r.details}" for r in results if r.failed))
    if not dry_run:
        store._write(backup=True)
    return results
