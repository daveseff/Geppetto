from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from urllib.error import HTTPError

import pytest

from geppetto_automation.config import DEFAULT_PLAN, GeppettoConfig
from geppetto_automation.config_service import _build_https_opener, resolve_config_service_host, sync_config_service
from geppetto_automation.cli import _resolve_plan_path, _validate_config_sources


def _build_bundle(files: dict[str, str]) -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        for name, content in files.items():
            archive.writestr(f"bundle/{name}", content)
    return payload.getvalue()


def test_sync_config_service_writes_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "config"
    cfg = GeppettoConfig(
        config_service_url="https://config.example.invalid",
        config_service_path=target,
        config_service_host="host1",
    )
    bundle = _build_bundle(
        {
            "hosts/host1/plan.fops": "task 'demo' on ['host1'] {}",
            "templates/motd.tmpl": "hi",
        }
    )

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return bundle

    class FakeOpener:
        def open(self, req):
            return FakeResponse()

    monkeypatch.setattr("geppetto_automation.config_service._build_https_opener", lambda cfg: FakeOpener())

    sync_config_service(cfg)

    assert (target / "hosts/host1/plan.fops").read_text() == "task 'demo' on ['host1'] {}"
    assert (target / "templates/motd.tmpl").read_text() == "hi"


def test_sync_config_service_replaces_existing_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "config"
    (target / "stale").mkdir(parents=True)
    (target / "stale/old.txt").write_text("old")
    cfg = GeppettoConfig(
        config_service_url="https://config.example.invalid",
        config_service_path=target,
        config_service_host="host1",
    )
    bundle = _build_bundle({"hosts/host1/plan.fops": "task 'demo' on ['host1'] {}"})

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return bundle

    class FakeOpener:
        def open(self, req):
            return FakeResponse()

    monkeypatch.setattr("geppetto_automation.config_service._build_https_opener", lambda cfg: FakeOpener())

    sync_config_service(cfg)

    assert not (target / "stale").exists()
    assert (target / "hosts/host1/plan.fops").exists()


def test_sync_config_service_surfaces_http_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = GeppettoConfig(
        config_service_url="https://config.example.invalid",
        config_service_path=tmp_path / "config",
        config_service_host="host1",
    )
    err = HTTPError(
        url="https://config.example.invalid/v1/configs/host1/bundle",
        code=404,
        msg="Not Found",
        hdrs=None,
        fp=io.BytesIO(json.dumps({"detail": "host not found"}).encode()),
    )

    class FakeOpener:
        def open(self, req):
            raise err

    monkeypatch.setattr("geppetto_automation.config_service._build_https_opener", lambda cfg: FakeOpener())

    with pytest.raises(RuntimeError, match="host not found"):
        sync_config_service(cfg)


def test_build_https_opener_requires_cert_and_key(tmp_path: Path) -> None:
    cfg = GeppettoConfig(
        config_service_ca_cert=tmp_path / "ca.crt",
        config_service_client_cert=tmp_path / "client.crt",
    )
    cfg.config_service_ca_cert.write_text("ca")
    cfg.config_service_client_cert.write_text("cert")

    with pytest.raises(RuntimeError, match="requires both"):
        _build_https_opener(cfg)


def test_build_https_opener_uses_client_material(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ca = tmp_path / "ca.crt"
    cert = tmp_path / "client.crt"
    key = tmp_path / "client.key"
    for path in (ca, cert, key):
        path.write_text("placeholder")
    cfg = GeppettoConfig(
        config_service_ca_cert=ca,
        config_service_client_cert=cert,
        config_service_client_key=key,
    )
    loaded: dict[str, str] = {}

    class FakeContext:
        def load_cert_chain(self, certfile: str, keyfile: str) -> None:
            loaded["certfile"] = certfile
            loaded["keyfile"] = keyfile

    fake_context = FakeContext()

    monkeypatch.setattr("geppetto_automation.config_service.ssl.create_default_context", lambda cafile=None: fake_context)
    monkeypatch.setattr(
        "geppetto_automation.config_service.request.HTTPSHandler",
        lambda context=None: ("https-handler", context),
    )
    monkeypatch.setattr(
        "geppetto_automation.config_service.request.build_opener",
        lambda handler: ("opener", handler),
    )

    opener = _build_https_opener(cfg)

    assert opener[0] == "opener"
    assert loaded == {"certfile": str(cert), "keyfile": str(key)}


def test_resolve_plan_path_uses_service_bundle_by_default(tmp_path: Path) -> None:
    cfg = GeppettoConfig(
        plan=DEFAULT_PLAN,
        config_service_path=tmp_path / "config",
        config_service_host="host1",
    )
    assert _resolve_plan_path(None, cfg) == tmp_path / "config/hosts/host1/plan.fops"


def test_resolve_plan_path_keeps_explicit_plan(tmp_path: Path) -> None:
    cfg = GeppettoConfig(
        plan=tmp_path / "custom.fops",
        config_service_path=tmp_path / "config",
        config_service_host="host1",
    )
    assert _resolve_plan_path(None, cfg) == tmp_path / "custom.fops"


def test_validate_config_sources_rejects_repo_and_service(tmp_path: Path) -> None:
    cfg = GeppettoConfig(
        config_repo_path=tmp_path / "repo",
        config_service_url="https://config.example.invalid",
    )
    with pytest.raises(RuntimeError, match="either config_repo_path or config_service_url"):
        _validate_config_sources(cfg)


def test_resolve_config_service_host_prefers_configured_value() -> None:
    cfg = GeppettoConfig(config_service_host="host1")
    assert resolve_config_service_host(cfg) == "host1"
