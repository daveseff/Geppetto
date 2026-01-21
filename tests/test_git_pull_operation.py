from pathlib import Path

from geppetto_automation.executors import CommandResult, LocalExecutor
from geppetto_automation.operations.git_pull import GitPullOperation
from geppetto_automation.types import HostConfig


class FakeExecutor(LocalExecutor):
    def __init__(self, host: HostConfig, *, advance: bool = True):
        super().__init__(host)
        self.commands: list[list[str]] = []
        self.rev = "a"
        self.advance = advance

    def run(  # type: ignore[override]
        self,
        command,
        *,
        check: bool = True,
        mutable: bool = True,  # noqa: ARG002
        env=None,  # noqa: ARG002
        cwd=None,  # noqa: ARG002
        timeout=None,  # noqa: ARG002
    ):
        cmd = list(command)
        self.commands.append(cmd)
        if cmd[0] == "git":
            return self._handle_git(cmd, check)
        return CommandResult(cmd, "", "", 0)

    def _handle_git(self, cmd: list[str], check: bool) -> CommandResult:
        if cmd[1] == "clone":
            dest = Path(cmd[3])
            dest.mkdir(parents=True, exist_ok=True)
            (dest / ".git").mkdir()
            return CommandResult(cmd, "", "", 0)
        if cmd[1] == "-C" and cmd[3] == "rev-parse":
            return CommandResult(cmd, f"{self.rev}\n", "", 0)
        if cmd[1] == "-C" and cmd[3] == "pull":
            if self.advance:
                self.rev = "b"
            return CommandResult(cmd, "", "", 0)
        result = CommandResult(cmd, "", "", 0)
        if check and result.returncode != 0:
            raise RuntimeError("command failed")
        return result


def test_git_pull_clones_when_missing(tmp_path: Path) -> None:
    host = HostConfig("local")
    dest = tmp_path / "repo"
    exec = FakeExecutor(host)

    op = GitPullOperation({"source": "git@example.com/repo.git", "dest": str(dest)})
    result = op.apply(host, exec)

    assert result.changed is True
    assert "cloned" in result.details
    assert (dest / ".git").exists()


def test_git_pull_pulls_when_repo_exists(tmp_path: Path) -> None:
    host = HostConfig("local")
    dest = tmp_path / "repo"
    (dest / ".git").mkdir(parents=True)
    exec = FakeExecutor(host, advance=True)

    op = GitPullOperation({"source": "git@example.com/repo.git", "dest": str(dest)})
    result = op.apply(host, exec)

    assert result.changed is True
    assert "pulled" in result.details
    assert exec.rev == "b"


def test_git_pull_absent_removes(tmp_path: Path) -> None:
    host = HostConfig("local")
    dest = tmp_path / "repo"
    dest.mkdir()

    op = GitPullOperation({"source": "git@example.com/repo.git", "dest": str(dest), "state": "absent"})
    result = op.apply(host, LocalExecutor(host))

    assert result.changed is True
    assert not dest.exists()
