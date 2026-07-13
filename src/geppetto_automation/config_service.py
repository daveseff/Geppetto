from __future__ import annotations

import io
import json
import logging
import os
import shutil
import ssl
import socket
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from urllib import error, request


LOGGER = logging.getLogger(__name__)
DEFAULT_PKI_DIR = Path("/etc/geppetto/pki")


def resolve_config_service_host(cfg) -> str:
    configured = getattr(cfg, "config_service_host", None)
    if configured:
        return str(configured)
    return socket.gethostname()


def sync_config_service(cfg) -> None:
    service_url = getattr(cfg, "config_service_url", None)
    destination = getattr(cfg, "config_service_path", None)
    if not service_url or not destination:
        raise RuntimeError("config_service_url requires config_service_path")

    host_name = resolve_config_service_host(cfg)
    _ensure_mtls_material(cfg, host_name, str(service_url).rstrip("/"))
    bundle_url = f"{str(service_url).rstrip('/')}/v1/configs/{host_name}/bundle"
    headers = {
        "Accept": "application/zip",
        "User-Agent": "geppetto-auto/0.1",
    }
    req = request.Request(bundle_url, headers=headers)
    opener = _build_https_opener(cfg)
    try:
        with opener.open(req) as response:
            body = response.read()
    except error.HTTPError as exc:
        detail = _http_error_detail(exc)
        raise RuntimeError(f"config service request failed for {host_name}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"config service request failed for {host_name}: {exc.reason}") from exc

    repo_path = Path(destination)
    LOGGER.info("Updating host config %s from %s into %s", host_name, bundle_url, repo_path)
    _extract_bundle(body, repo_path)


def ensure_agent_certificate(cfg) -> None:
    service_url = getattr(cfg, "config_service_url", None)
    if not service_url:
        raise RuntimeError("config_service_url is required for certificate enrollment")
    host_name = resolve_config_service_host(cfg)
    _ensure_mtls_material(cfg, host_name, str(service_url).rstrip("/"))


def agent_certificate_status(cfg) -> dict[str, str]:
    host_name = resolve_config_service_host(cfg)
    ca_cert, client_cert, client_key = _resolve_mtls_paths(cfg, host_name)
    csr_path = client_cert.with_suffix(".csr")
    return {
        "host": host_name,
        "ca_cert": _cert_path_state(ca_cert),
        "client_cert": _cert_path_state(client_cert),
        "client_key": _path_state(client_key),
        "csr": _path_state(csr_path),
    }


def clean_agent_certificate(cfg) -> list[Path]:
    host_name = resolve_config_service_host(cfg)
    ca_cert, client_cert, client_key = _resolve_mtls_paths(cfg, host_name)
    removed: list[Path] = []
    for path in (client_cert.with_suffix(".csr"), client_cert, client_key, ca_cert):
        if path.exists():
            path.unlink()
            removed.append(path)
    return removed


def _build_https_opener(cfg):
    client_cert = getattr(cfg, "config_service_client_cert", None)
    client_key = getattr(cfg, "config_service_client_key", None)
    if client_cert or client_key:
        if not (client_cert and client_key):
            raise RuntimeError("config service mTLS requires both config_service_client_cert and config_service_client_key")
    context = ssl.create_default_context(cafile=_optional_str(getattr(cfg, "config_service_ca_cert", None)))
    if client_cert and client_key:
        context.load_cert_chain(certfile=str(client_cert), keyfile=str(client_key))
    else:
        raise RuntimeError("config service mTLS requires both config_service_client_cert and config_service_client_key")
    return request.build_opener(request.HTTPSHandler(context=context))


def _optional_str(path: Path | None) -> str | None:
    return str(path) if path else None


def _ensure_mtls_material(cfg, host_name: str, service_url: str) -> None:
    ca_cert, client_cert, client_key = _resolve_mtls_paths(cfg, host_name)

    if not ca_cert.exists():
        _fetch_ca_cert(service_url, ca_cert)
    if client_cert.exists() and client_key.exists():
        return
    if client_cert.exists() and not client_key.exists():
        raise RuntimeError(f"client certificate exists but private key is missing: {client_key}")

    csr_path = client_cert.with_suffix(".csr")
    if not client_key.exists() or not csr_path.exists():
        _generate_client_csr(host_name, client_key, csr_path)
    _submit_csr(cfg, host_name, service_url, ca_cert, client_cert, csr_path)


def _resolve_mtls_paths(cfg, host_name: str) -> tuple[Path, Path, Path]:
    ca_cert = Path(getattr(cfg, "config_service_ca_cert", None) or DEFAULT_PKI_DIR / "ca.crt")
    client_cert = Path(getattr(cfg, "config_service_client_cert", None) or DEFAULT_PKI_DIR / f"{host_name}.crt")
    client_key = Path(getattr(cfg, "config_service_client_key", None) or DEFAULT_PKI_DIR / f"{host_name}.key")
    cfg.config_service_ca_cert = ca_cert
    cfg.config_service_client_cert = client_cert
    cfg.config_service_client_key = client_key
    return ca_cert, client_cert, client_key


def _path_state(path: Path) -> str:
    return f"present:{path}" if path.exists() else f"missing:{path}"


def _cert_path_state(path: Path) -> str:
    if not path.exists():
        return f"missing:{path}"
    if _certificate_expired(path):
        return f"expired:{path}"
    return f"present:{path}"


def _certificate_expired(path: Path) -> bool:
    try:
        result = subprocess.run(
            ["openssl", "x509", "-enddate", "-noout", "-in", str(path)],
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    if result.returncode != 0:
        return False
    prefix = "notAfter="
    enddate = result.stdout.strip()
    if not enddate.startswith(prefix):
        return False
    try:
        return ssl.cert_time_to_seconds(enddate.removeprefix(prefix)) <= time.time()
    except ValueError:
        return False


def _fetch_ca_cert(service_url: str, ca_cert: Path) -> None:
    ca_url = f"{service_url}/v1/ca"
    ca_cert.parent.mkdir(parents=True, exist_ok=True)
    context = ssl._create_unverified_context()  # noqa: SLF001
    opener = request.build_opener(request.HTTPSHandler(context=context))
    try:
        with opener.open(request.Request(ca_url, headers={"Accept": "application/x-pem-file"})) as response:
            payload = response.read()
    except error.URLError as exc:
        raise RuntimeError(f"failed to fetch config service CA from {ca_url}: {exc.reason}") from exc
    ca_cert.write_bytes(payload)


def _generate_client_csr(host_name: str, client_key: Path, csr_path: Path) -> None:
    client_key.parent.mkdir(parents=True, exist_ok=True)
    csr_path.parent.mkdir(parents=True, exist_ok=True)
    if not client_key.exists():
        cmd = [
            "openssl",
            "req",
            "-new",
            "-newkey",
            "rsa:4096",
            "-nodes",
            "-keyout",
            str(client_key),
            "-subj",
            f"/CN={host_name}",
            "-out",
            str(csr_path),
        ]
    else:
        cmd = [
            "openssl",
            "req",
            "-new",
            "-key",
            str(client_key),
            "-subj",
            f"/CN={host_name}",
            "-out",
            str(csr_path),
        ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"failed to generate client CSR: {detail}")
    try:
        os.chmod(client_key, 0o600)
    except OSError:
        LOGGER.warning("Unable to chmod private key %s", client_key)


def _submit_csr(cfg, host_name: str, service_url: str, ca_cert: Path, client_cert: Path, csr_path: Path) -> None:
    csr_url = f"{service_url}/v1/csr/{host_name}"
    context = ssl.create_default_context(cafile=str(ca_cert))
    opener = request.build_opener(request.HTTPSHandler(context=context))
    req = request.Request(
        csr_url,
        data=csr_path.read_bytes(),
        headers={"Content-Type": "application/pkcs10", "Accept": "application/x-pem-file, application/json"},
        method="POST",
    )
    try:
        with opener.open(req) as response:
            payload = response.read()
            status = getattr(response, "status", response.getcode())
    except error.HTTPError as exc:
        detail = _http_error_detail(exc)
        raise RuntimeError(f"CSR submission failed for {host_name}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"CSR submission failed for {host_name}: {exc.reason}") from exc

    if status == 200:
        client_cert.parent.mkdir(parents=True, exist_ok=True)
        client_cert.write_bytes(payload)
        return
    if status == 202:
        detail = _json_detail(payload) or "certificate signing request is pending approval"
        raise RuntimeError(detail)
    raise RuntimeError(f"unexpected CSR response status: HTTP {status}")


def _json_detail(payload: bytes) -> str:
    try:
        parsed = json.loads(payload.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return ""
    if isinstance(parsed, dict):
        return str(parsed.get("detail") or "")
    return ""


def _http_error_detail(exc: error.HTTPError) -> str:
    body = ""
    try:
        payload = exc.read().decode("utf-8", errors="replace")
        parsed = json.loads(payload)
        if isinstance(parsed, dict) and parsed.get("detail"):
            body = str(parsed["detail"])
        elif payload:
            body = payload.strip()
    except Exception:
        body = ""
    return body or f"HTTP {exc.code}"


def _extract_bundle(bundle: bytes, destination: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="geppetto-config-") as temp_dir:
        temp_root = Path(temp_dir)
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            _validate_zip_members(archive)
            archive.extractall(temp_root)
        extracted_items = list(temp_root.iterdir())
        if not extracted_items:
            raise RuntimeError("config service returned an empty bundle")
        destination.parent.mkdir(parents=True, exist_ok=True)
        replacement = temp_root / "bundle"
        if replacement.exists():
            source_root = replacement
        elif len(extracted_items) == 1 and extracted_items[0].is_dir():
            source_root = extracted_items[0]
        else:
            source_root = temp_root
        _replace_tree(source_root, destination)


def _validate_zip_members(archive: zipfile.ZipFile) -> None:
    for member in archive.namelist():
        member_path = Path(member)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise RuntimeError(f"unsafe bundle member: {member}")


def _replace_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
