from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional
import logging
import shutil

from .base import Operation
from ..executors import Executor
from ..types import ActionResult, HostConfig

logger = logging.getLogger(__name__)


class PackageOperation(Operation):
    """Install or remove packages using the detected package manager."""

    def __init__(self, spec: dict[str, object]):
        super().__init__(spec)
        packages = spec.get("name") or spec.get("packages")
        if isinstance(packages, str):
            self.packages = [packages]
        else:
            self.packages = list(packages or [])
        if not self.packages:
            raise ValueError("package operation requires at least one package")
        self.state = str(spec.get("state", "present"))
        if self.state not in {"present", "absent"}:
            raise ValueError("package operation state must be 'present' or 'absent'")
        self.preferred_manager = spec.get("manager")

    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
        manager = PackageManagerFactory.create(self.preferred_manager)
        logger.debug(
            "package-manager=%s host=%s packages=%s", manager.name, host.name, self.packages
        )
        if self.state == "present":
            changed, details = manager.ensure_present(executor, self.packages)
        else:
            changed, details = manager.ensure_absent(executor, self.packages)
        detail_msg = f"manager={manager.name} {details}" if details else f"manager={manager.name}"
        return ActionResult(host=host.name, action="package", changed=changed, details=detail_msg)


class PackageManagerFactory:
    _MANAGERS = [
        ("apt-get", "apt", lambda: AptPackageManager()),
        ("dnf", "dnf", lambda: DnfPackageManager()),
        ("yum", "yum", lambda: YumPackageManager()),
        ("brew", "brew", lambda: BrewPackageManager()),
        ("pacman", "pacman", lambda: PacmanPackageManager()),
    ]

    @classmethod
    def create(cls, preferred: Optional[object]) -> "PackageManager":
        if isinstance(preferred, str):
            preferred = preferred.lower()
            for _, key, factory in cls._MANAGERS:
                if key == preferred:
                    return factory()
            raise ValueError(f"Unknown package manager '{preferred}'")
        for binary, _, factory in cls._MANAGERS:
            if shutil.which(binary):
                return factory()
        raise RuntimeError("No supported package manager found on PATH")


class PackageManager:
    name = "generic"

    def ensure_present(self, executor: Executor, packages: Iterable[str]) -> tuple[bool, str]:
        needed = [pkg for pkg in packages if not self.is_installed(executor, pkg)]
        if not needed:
            return False, "already-installed"
        self.install(executor, needed)
        return True, f"installed={','.join(needed)}"

    def ensure_absent(self, executor: Executor, packages: Iterable[str]) -> tuple[bool, str]:
        removable = [pkg for pkg in packages if self.is_installed(executor, pkg)]
        if not removable:
            return False, "already-removed"
        self.remove(executor, removable)
        return True, f"removed={','.join(removable)}"

    def install(self, executor: Executor, packages: list[str]) -> None:
        raise NotImplementedError

    def remove(self, executor: Executor, packages: list[str]) -> None:
        raise NotImplementedError

    def is_installed(self, executor: Executor, package: str) -> bool:
        raise NotImplementedError


@dataclass
class DpkgQuery:
    executable: str = "dpkg-query"

    def check(self, executor: Executor, package: str) -> bool:
        result = executor.run(
            [self.executable, "-W", "-f", "${Status}", package],
            check=False,
            mutable=False,
        )
        return result.returncode == 0 and "installed" in result.stdout


class AptPackageManager(PackageManager):
    name = "apt"

    def __init__(self) -> None:
        self.query = DpkgQuery()

    def install(self, executor: Executor, packages: list[str]) -> None:
        executor.run(["apt-get", "install", "-y", *packages])

    def remove(self, executor: Executor, packages: list[str]) -> None:
        executor.run(["apt-get", "remove", "-y", *packages])

    def is_installed(self, executor: Executor, package: str) -> bool:
        return self.query.check(executor, package)


class DnfPackageManager(PackageManager):
    name = "dnf"

    def install(self, executor: Executor, packages: list[str]) -> None:
        executor.run(["dnf", "install", "-y", *packages])

    def remove(self, executor: Executor, packages: list[str]) -> None:
        executor.run(["dnf", "remove", "-y", *packages])

    def is_installed(self, executor: Executor, package: str) -> bool:
        result = executor.run(["rpm", "-q", package], check=False, mutable=False)
        return result.returncode == 0


class YumPackageManager(DnfPackageManager):
    name = "yum"

    def install(self, executor: Executor, packages: list[str]) -> None:  # type: ignore[override]
        executor.run(["yum", "install", "-y", *packages])

    def remove(self, executor: Executor, packages: list[str]) -> None:  # type: ignore[override]
        executor.run(["yum", "remove", "-y", *packages])


class BrewPackageManager(PackageManager):
    name = "brew"

    def install(self, executor: Executor, packages: list[str]) -> None:
        executor.run(["brew", "install", *packages])

    def remove(self, executor: Executor, packages: list[str]) -> None:
        executor.run(["brew", "uninstall", *packages])

    def is_installed(self, executor: Executor, package: str) -> bool:
        result = executor.run(["brew", "list", package], check=False, mutable=False)
        return result.returncode == 0


class PacmanPackageManager(PackageManager):
    name = "pacman"

    def install(self, executor: Executor, packages: list[str]) -> None:
        executor.run(["pacman", "-S", "--noconfirm", *packages])

    def remove(self, executor: Executor, packages: list[str]) -> None:
        executor.run(["pacman", "-R", "--noconfirm", *packages])

    def is_installed(self, executor: Executor, package: str) -> bool:
        result = executor.run(["pacman", "-Qi", package], check=False, mutable=False)
        return result.returncode == 0
