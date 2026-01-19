from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from .base import Operation
from .remote import RemoteFetcher
from ..executors import CommandResult, Executor
from ..types import ActionResult, HostConfig

logger = logging.getLogger(__name__)


class CaCertOperation(Operation):
    """Install or remove CA certs in OS trust store and Java keystore."""

    def __init__(self, spec: dict[str, Any]):
        super().__init__(spec)
        raw_name = spec.get("name")
        self.name = str(raw_name) if raw_name else None
        self.state = str(spec.get("state", "present"))
        if self.state not in {"present", "absent"}:
            raise ValueError("ca_cert state must be 'present' or 'absent'")

        self.path = Path(str(spec["path"])) if spec.get("path") else None
        self.source = str(spec["source"]) if spec.get("source") else None
        if not self.path and not self.source:
            raise ValueError("ca_cert requires a path or source")

        self.alias = str(spec["alias"]) if spec.get("alias") else None
        self.os_trust_dir = Path(str(spec["os_trust_dir"])) if spec.get("os_trust_dir") else None
        self.java_keystore = Path(str(spec["java_keystore"])) if spec.get("java_keystore") else None
        self.java_storepass = str(spec.get("java_storepass", "changeit"))

    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
        cert_text, filename = self._load_cert(executor)
        os_family = self._detect_os_family()
        trust_dir = self._resolve_trust_dir(os_family)
        target_name = self._normalize_cert_name(filename, os_family)
        os_target = trust_dir / target_name

        changed_os = False
        changed_java = False

        executor.ensure_directory(trust_dir, mode=0o755)

        if self.state == "present":
            changed_os, _ = executor.write_file(os_target, content=cert_text, mode=0o644)
            if changed_os and not executor.dry_run:
                self._update_os_store(os_family, executor)
            changed_java = self._ensure_java_cert(os_target, cert_text, os_family, executor)
        else:
            removed = executor.remove_path(os_target)
            changed_os = removed
            if removed and not executor.dry_run:
                self._update_os_store(os_family, executor)
            changed_java = self._remove_java_cert(os_family, executor)

        detail = self._detail(changed_os, changed_java)
        return ActionResult(host=host.name, action="ca_cert", changed=changed_os or changed_java, details=detail)

    def _load_cert(self, executor: Executor) -> tuple[str, str]:
        if self.path:
            if not self.path.exists():
                raise FileNotFoundError(f"ca_cert path {self.path} does not exist")
            return self.path.read_text(), self.path.name

        fetcher = RemoteFetcher(executor)
        tmp_path = fetcher.fetch(self.source or "")
        try:
            name = self._filename_from_source(self.source or tmp_path.name)
            return tmp_path.read_text(), name
        finally:
            RemoteFetcher.cleanup(tmp_path)

    def _ensure_java_cert(
        self,
        os_target: Path,
        cert_text: str,
        os_family: str,
        executor: Executor,
    ) -> bool:
        alias = self._alias_from_name(os_target.name)
        keystore = self._resolve_java_keystore(os_family)
        existing = self._read_java_cert(alias, keystore, executor)
        if existing and self._normalize_pem(existing) == self._normalize_pem(cert_text):
            return False
        if executor.dry_run:
            return True
        if existing:
            self._run_keytool(["-delete", "-alias", alias], keystore, executor)
        self._run_keytool(["-importcert", "-noprompt", "-alias", alias, "-file", str(os_target)], keystore, executor)
        return True

    def _remove_java_cert(self, os_family: str, executor: Executor) -> bool:
        alias = self._alias_from_name(self._default_alias_name())
        keystore = self._resolve_java_keystore(os_family)
        existing = self._read_java_cert(alias, keystore, executor)
        if not existing:
            return False
        if executor.dry_run:
            return True
        self._run_keytool(["-delete", "-alias", alias], keystore, executor)
        return True

    def _read_java_cert(self, alias: str, keystore: Path, executor: Executor) -> Optional[str]:
        list_result = self._run_keytool(["-list", "-alias", alias], keystore, executor, check=False)
        if list_result.returncode != 0:
            return None
        export_result = self._run_keytool(["-exportcert", "-rfc", "-alias", alias], keystore, executor, check=False)
        if export_result.returncode != 0:
            return None
        return export_result.stdout

    def _run_keytool(
        self,
        args: list[str],
        keystore: Path,
        executor: Executor,
        *,
        check: bool = True,
    ) -> CommandResult:
        cmd = ["keytool", *args, "-keystore", str(keystore), "-storepass", self.java_storepass]
        return executor.run(cmd, check=check, mutable=True)

    def _resolve_java_keystore(self, os_family: str) -> Path:
        if self.java_keystore:
            return self.java_keystore
        candidates = self._java_keystore_candidates(os_family)
        for path in candidates:
            if path.exists():
                return path
        raise ValueError("java keystore not found; set java_keystore")

    @staticmethod
    def _java_keystore_candidates(os_family: str) -> list[Path]:
        if os_family == "debian":
            return [Path("/etc/ssl/certs/java/cacerts"), Path("/usr/lib/jvm/default-java/lib/security/cacerts")]
        return [Path("/etc/pki/java/cacerts"), Path("/usr/lib/jvm/default-java/lib/security/cacerts")]

    def _alias_from_name(self, filename: str) -> str:
        if self.alias:
            return self.alias
        stem = Path(filename).stem
        if stem:
            return stem
        if self.name:
            return self.name
        raise ValueError("ca_cert alias could not be determined")

    def _default_alias_name(self) -> str:
        if self.alias:
            return self.alias
        if self.path:
            return self.path.name
        if self.source:
            return self._filename_from_source(self.source)
        if self.name:
            return self.name
        return "ca-cert"

    @staticmethod
    def _detect_os_family() -> str:
        if shutil.which("update-ca-trust"):
            return "rhel"
        if shutil.which("update-ca-certificates"):
            return "debian"
        os_release = Path("/etc/os-release")
        if os_release.exists():
            text = os_release.read_text().lower()
            if "debian" in text or "ubuntu" in text:
                return "debian"
        return "rhel"

    def _resolve_trust_dir(self, os_family: str) -> Path:
        if self.os_trust_dir:
            return self.os_trust_dir
        if os_family == "debian":
            return Path("/usr/local/share/ca-certificates")
        return Path("/etc/pki/ca-trust/source/anchors")

    @staticmethod
    def _update_os_store(os_family: str, executor: Executor) -> None:
        if os_family == "debian":
            executor.run(["update-ca-certificates"], mutable=True)
        else:
            executor.run(["update-ca-trust", "extract"], mutable=True)

    @staticmethod
    def _normalize_cert_name(name: str, os_family: str) -> str:
        filename = name or "ca-cert.pem"
        if os_family == "debian" and not filename.endswith(".crt"):
            return f"{filename}.crt"
        return filename

    @staticmethod
    def _filename_from_source(source: str) -> str:
        if source.startswith("s3://"):
            return Path(source[5:]).name
        if source.startswith("file://"):
            return Path(source[7:]).name
        parsed = urlparse(source)
        if parsed.scheme:
            return Path(parsed.path).name or "ca-cert.pem"
        return Path(source).name

    @staticmethod
    def _normalize_pem(value: str) -> str:
        lines = []
        for line in value.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("-----BEGIN"):
                continue
            if stripped.startswith("-----END"):
                continue
            lines.append(stripped)
        return "".join(lines)

    def _detail(self, changed_os: bool, changed_java: bool) -> str:
        if not changed_os and not changed_java:
            return "noop"
        action = "removed" if self.state == "absent" else "updated"
        parts = []
        if changed_os:
            parts.append(f"os-{action}")
        if changed_java:
            parts.append(f"java-{action}")
        return ", ".join(parts)
