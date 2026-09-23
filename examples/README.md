# Examples layout

This directory mirrors a defaults -> groups -> hosts layering so you can ship all host configs in Git without clobbering each other.

- `config/defaults/` - tasks shared everywhere; target `'*'` to apply them to every host.
- `config/groups/<group>/` - environment/role-specific overlays (e.g., `staging/` hardening).
- `config/hosts/<hostname>/` - host entrypoints for host-specific definitions such as SSH keys. Declare one or more memberships in the node with `groups = ['staging', 'database']`; omit `groups` or use `groups = []` for no membership. Geppetto Server adds named groups automatically.
- `config/templates/` - templates referenced from plans (set `template_dir` to this path).
- `plan.fops` - convenience entrypoint used by docs/tests; it simply includes `config/hosts/host1/plan.fops`.

To run the example plan in dry-run mode:

```
geppetto-auto examples/plan.fops --dry-run
```
