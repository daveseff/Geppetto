"""Select explicit resources and their transitive prerequisites before execution."""
from __future__ import annotations

from dataclasses import dataclass, replace

from .identity import resource_id, state_actions
from .types import ActionSpec


@dataclass
class TargetNode:
    host: str
    task: str
    action: ActionSpec
    aliases: set[str]
    original: ActionSpec


def aliases(action):
    names = {resource_id(action)}
    for field in ('resource', 'name', 'path', 'dest', 'mount_point', 'service', 'user'):
        if action.data.get(field):
            names.add(f'{action.type}.{action.data[field]}')
    return names


def children(action):
    for child in action.on_success + action.on_failure:
        yield child
        yield from children(child)


def select_targets(plan, targets):
    nodes = []
    hook_aliases = set()
    for task in plan.tasks:
        for host in task.hosts:
            if host not in plan.hosts:
                raise ValueError(f'Unknown host {host!r} in task {task.name!r}')
            for action in task.actions:
                # A package list can be targeted by an individual member name.
                items = list(state_actions(action)) if action.type == 'package' else [action]
                for item in items:
                    node = TargetNode(host, task.name, item, aliases(item) | aliases(action), action)
                    # Do not make one member's name an alias for the entire list.
                    nodes.append(node)
                for child in children(action):
                    hook_aliases.update(aliases(child))
    selected = set()
    requirements = {}
    visiting = set()
    order = []

    def resolve(value, *, host=None, task=None):
        explicit_host, separator, selector = value.partition('::')
        if separator:
            if host is not None and explicit_host != host:
                raise ValueError(f'Cross-host dependency is unsupported: {value}')
            host = explicit_host
        else:
            selector = value
        matches = [i for i, node in enumerate(nodes)
                   if selector in node.aliases and (host is None or node.host == host)]
        if task is not None:
            local = [i for i in matches if nodes[i].task == task]
            if local:
                matches = local
        # A canonical bulk package ID intentionally selects all its members.
        bulk = matches and all(nodes[i].action.type == 'package' for i in matches)
        if not matches:
            if selector in hook_aliases:
                raise ValueError(f'{value!r} is a conditional hook; target its parent resource instead')
            raise ValueError(f'Unknown target or dependency: {value!r}')
        if len(matches) > 1 and not (bulk and len({(nodes[i].host, nodes[i].task) for i in matches}) == 1):
            raise ValueError(f'Ambiguous target or dependency: {value!r}; qualify the host or give resources unique names')
        return matches

    def validate_hooks(action):
        for branch in (action.on_success, action.on_failure):
            active = set()
            done = set()
            def walk(index):
                if index in active:
                    raise ValueError('Dependency cycle in conditional hooks')
                if index in done:
                    return
                active.add(index)
                child = branch[index]
                for dep in child.depends_on:
                    matches = [i for i, candidate in enumerate(branch) if dep in aliases(candidate)]
                    if len(matches) > 1:
                        raise ValueError(f'Ambiguous hook dependency: {dep!r}')
                    for prerequisite in matches:
                        walk(prerequisite)
                validate_hooks(child)
                active.remove(index)
                done.add(index)
            for index in range(len(branch)):
                walk(index)

    def visit(index):
        if index in visiting:
            raise ValueError('Dependency cycle in targeted resources')
        if index in selected:
            return
        visiting.add(index)
        node = nodes[index]
        requirements[index] = set()
        validate_hooks(node.action)
        nested = list(children(node.action))
        internal = set().union(*(aliases(child) for child in nested)) if nested else set()
        for action in [node.action] + nested:
            for dep in action.depends_on:
                if action is not node.action and dep in internal:
                    continue
                for prerequisite in resolve(dep, host=node.host, task=node.task):
                    if prerequisite == index and action is not node.action:
                        continue  # Hooks already execute after their parent.
                    requirements[index].add(prerequisite)
                    visit(prerequisite)
        visiting.remove(index)
        selected.add(index)
        order.append(index)

    for target in targets:
        for index in resolve(target):
            visit(index)
    # Selected members of one package block remain one operation, so its hooks
    # fire once even when several members were selected.
    groups = {}
    remap = {}
    for index in order:
        node = nodes[index]
        group = (node.host, id(node.original))
        groups.setdefault(group, []).append(index)
    for indices in groups.values():
        first = indices[0]
        for index in indices:
            remap[index] = first
        node = nodes[first]
        if node.action.type == 'package' and not node.original.data.get('name'):
            names = [nodes[index].action.data['name'] for index in indices]
            data = {**node.original.data, 'packages': names}
            data.pop('_resource_id', None)
            node.action = replace(node.original, data=data)
    collapsed = {}
    for index in order:
        collapsed.setdefault(remap[index], set()).update(remap[dep] for dep in requirements[index])
    ordered = []
    pending = list(collapsed)
    while pending:
        ready = [index for index in pending if collapsed[index].issubset(set(ordered))]
        if not ready:
            raise ValueError('Dependency cycle between targeted package blocks')
        for index in ready:
            ordered.append(index)
            pending.remove(index)
    return nodes, ordered, collapsed
