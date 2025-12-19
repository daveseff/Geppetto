# Examples layout

This directory mirrors a defaults -> groups -> hosts layering so you can ship all host configs in Git without clobbering each other.

- `config/defaults/` - tasks shared everywhere (packages, baseline users).
- `config/groups/<group>/` - environment/role-specific overlays (e.g., `staging/` hardening).
- `config/hosts/<hostname>/` - host entrypoints that include defaults, then groups, then host-specific bits like SSH keys.
- `config/templates/` - templates referenced from plans (set `template_dir` to this path).
- `plan.fops` - convenience entrypoint used by docs/tests; it simply includes `config/hosts/host1/plan.fops`.

To run the example plan in dry-run mode:

```
geppetto-auto examples/plan.fops --dry-run
```
