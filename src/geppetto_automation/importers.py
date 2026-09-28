from __future__ import annotations

import re
import socket
import subprocess
from pathlib import PurePath
from typing import Optional


def import_crontab(user: str, *, host: Optional[str] = None, task_name: Optional[str] = None) -> str:
    """Read a user's crontab and render an adoptable Geppetto task."""
    result = subprocess.run(
        ["crontab", "-u", user, "-l"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no crontab found"
        raise RuntimeError(f"unable to read crontab for {user}: {detail}")

    jobs = _parse_crontab(result.stdout)
    if not jobs:
        raise RuntimeError(f"no cron jobs found for {user}")

    host = host or socket.gethostname()
    name = task_name or f"imported-crontab-{user}"
    output = [f"task {_dsl_quote(name)} on [{_dsl_quote(host)}] {{"]
    used_names: dict[str, int] = {}
    for job in jobs:
        base_name = f"{user}-{_command_name(job['command'])}"
        used_names[base_name] = used_names.get(base_name, 0) + 1
        resource_name = base_name
        if used_names[base_name] > 1:
            resource_name += f"-{used_names[base_name]}"
        output.extend(_render_job(resource_name, user, job))
    output.append("}")
    return "\n".join(output) + "\n"


def _parse_crontab(content: str) -> list[dict[str, object]]:
    jobs: list[dict[str, object]] = []
    env: dict[str, str] = {}
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        env_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
        if env_match:
            env[env_match.group(1)] = env_match.group(2)
            continue
        if line.startswith("@"):
            parts = line.split(None, 1)
            if len(parts) != 2:
                raise RuntimeError(f"invalid crontab entry on line {line_number}: {raw_line}")
            jobs.append({"special": parts[0], "command": parts[1], "env": dict(env)})
            continue
        parts = line.split(None, 5)
        if len(parts) != 6:
            raise RuntimeError(f"invalid crontab entry on line {line_number}: {raw_line}")
        jobs.append(
            {
                "minute": parts[0],
                "hour": parts[1],
                "day": parts[2],
                "month": parts[3],
                "weekday": parts[4],
                "command": parts[5],
                "env": dict(env),
            }
        )
    return jobs


def _render_job(resource_name: str, user: str, job: dict[str, object]) -> list[str]:
    lines = [
        f"  cron {{ {_dsl_quote(resource_name)}:",
        "    target  => 'crontab_entry'",
        f"    user    => {_dsl_quote(user)}",
    ]
    if "special" in job:
        lines.append(f"    special => {_dsl_quote(str(job['special']))}")
    else:
        for key in ("minute", "hour", "day", "month", "weekday"):
            lines.append(f"    {key:<7} => {_dsl_quote(str(job[key]))}")
    lines.append(f"    command => {_dsl_quote(str(job['command']))}")
    env = job.get("env")
    if isinstance(env, dict) and env:
        rendered_env = ", ".join(
            f"{_dsl_quote(str(key))} => {_dsl_quote(str(value))}" for key, value in env.items()
        )
        lines.append(f"    env     => {{ {rendered_env} }}")
    lines.append("  }")
    return lines


def _command_name(command: object) -> str:
    executable = str(command).split(None, 1)[0]
    name = PurePath(executable).name or "job"
    return re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower() or "job"


def _dsl_quote(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f"'{escaped}'"
