from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load_compose(filename: str) -> dict[str, Any]:
    data = yaml.safe_load((ROOT / filename).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


@pytest.mark.parametrize("filename", ["docker-compose.yml", "docker-compose.prod.yml"])
def test_exporters_and_monitoring_network_configured(filename: str) -> None:
    compose = _load_compose(filename)
    services = compose["services"]
    assert "monitoring" in compose.get("networks", {})

    for name in ("postgres-exporter", "nginx-exporter"):
        svc = services[name]
        assert "ports" not in svc
        assert "monitoring" in svc.get("networks", [])

    pg_env = services["postgres-exporter"]["environment"]
    assert "postgres:5432/" in pg_env["DATA_SOURCE_URI"]
    assert {"DATA_SOURCE_USER", "DATA_SOURCE_PASS"}.issubset(pg_env)
    cmd = services["nginx-exporter"]["command"]
    assert "--nginx.scrape-uri=http://frontend:8081/stub_status" in cmd
    assert all("monitoring" in services[s].get("networks", []) for s in ("frontend", "app"))


def test_prod_postgres_exporter_has_no_default_password() -> None:
    compose = _load_compose("docker-compose.prod.yml")
    pg_pass = str(compose["services"]["postgres-exporter"]["environment"]["DATA_SOURCE_PASS"])
    assert ":?" in pg_pass and ":-postgres" not in pg_pass


def test_nginx_stub_status_isolated_from_public_port() -> None:
    nginx_conf = (ROOT / "frontend" / "nginx.conf.template").read_text(encoding="utf-8")
    blocks = nginx_conf.split("server {")
    assert len(blocks) == 3
    public_srv, internal_srv = blocks[1], blocks[2]

    assert "listen 80;" in public_srv and "stub_status;" not in public_srv
    assert "location = /stub_status" in public_srv and "return 404;" in public_srv
    assert "listen 8081;" in internal_srv and "location = /stub_status" in internal_srv
    assert "stub_status;" in internal_srv and "deny all;" in internal_srv
