from __future__ import annotations

import io
import json
import logging
import shutil
import ssl
import socket
import tempfile
import zipfile
from pathlib import Path
from urllib import error, request


LOGGER = logging.getLogger(__name__)


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
