"""Tests for Loki, Promtail, and Grafana logging infrastructure (Issue #48)."""

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = REPO_ROOT / "docker-compose.observability.yml"
LOKI_CONFIG_FILE = REPO_ROOT / "observability" / "loki" / "loki-config.yml"
PROMTAIL_CONFIG_FILE = REPO_ROOT / "observability" / "promtail" / "promtail-config.yml"
GRAFANA_DATASOURCE_FILE = (
    REPO_ROOT / "observability" / "grafana" / "provisioning" / "datasources" / "loki.yml"
)
GRAFANA_DASHBOARDS_PROV_FILE = (
    REPO_ROOT / "observability" / "grafana" / "provisioning" / "dashboards" / "dashboards.yml"
)
GRAFANA_LOGS_DASHBOARD_FILE = REPO_ROOT / "observability" / "grafana" / "dashboards" / "logs.json"
LOGGING_DOC_FILE = REPO_ROOT / "docs" / "LOGGING.md"


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_observability_files_exist() -> None:
    """All required logging configuration, provisioning, dashboard, and doc files exist."""
    for path in (
        COMPOSE_FILE,
        LOKI_CONFIG_FILE,
        PROMTAIL_CONFIG_FILE,
        GRAFANA_DATASOURCE_FILE,
        GRAFANA_DASHBOARDS_PROV_FILE,
        GRAFANA_LOGS_DASHBOARD_FILE,
        LOGGING_DOC_FILE,
    ):
        assert path.is_file(), f"Missing expected observability file: {path}"


def test_docker_compose_observability_structure_and_security() -> None:
    """Compose overlay defines persistent volumes, service labels, and restricted log access."""
    compose = _load_yaml(COMPOSE_FILE)
    services = compose["services"]
    volumes = compose["volumes"]

    # Persistent named volumes for Loki, Promtail positions, and shared Grafana
    assert {"loki_data", "promtail_positions", "grafana_data"} <= set(volumes.keys())

    # All three application services are labeled for Promtail with log rotation enabled
    expected_service_map = {
        "app": "app",
        "frontend": "nginx",
        "postgres": "postgres",
    }
    for compose_svc, expected_log_service in expected_service_map.items():
        svc = services[compose_svc]
        assert svc["labels"]["logging"] == "promtail"
        assert svc["labels"]["logging_service"] == expected_log_service
        assert svc["logging"]["driver"] == "json-file"

    # Loki and Promtail must NOT publish host ports (internal Docker network only)
    loki = services["loki"]
    assert "ports" not in loki
    assert "3100" in loki["expose"]
    assert any(v.startswith("loki_data:/loki") for v in loki["volumes"])
    assert "healthcheck" in loki

    promtail = services["promtail"]
    assert "ports" not in promtail
    assert "/var/run/docker.sock:/var/run/docker.sock:ro" in promtail["volumes"]
    assert any(v.startswith("promtail_positions:") for v in promtail["volumes"])
    assert "healthcheck" in promtail

    # Grafana binds to loopback by default and disables anonymous access / sign-up
    grafana = services["grafana"]
    assert any("127.0.0.1" in port and port.endswith(":3000") for port in grafana["ports"])
    env = grafana["environment"]
    assert str(env["GF_AUTH_ANONYMOUS_ENABLED"]).lower() == "false"
    assert str(env["GF_USERS_ALLOW_SIGN_UP"]).lower() == "false"
    assert str(env["GF_USERS_ALLOW_ORG_CREATE"]).lower() == "false"
    assert "GF_SECURITY_ADMIN_USER" in env
    assert "GF_SECURITY_ADMIN_PASSWORD" in env
    assert any(v.startswith("grafana_data:/var/lib/grafana") for v in grafana["volumes"])
    assert (
        "./observability/grafana/provisioning/datasources:/etc/grafana/provisioning/datasources:ro"
        in grafana["volumes"]
    )
    assert (
        "./observability/grafana/provisioning/dashboards:/etc/grafana/provisioning/dashboards:ro"
        in grafana["volumes"]
    )
    assert "./observability/grafana/dashboards:/var/lib/grafana/dashboards:ro" in grafana["volumes"]


def test_loki_config_persistence_and_structured_metadata() -> None:
    """Loki uses persistent /loki storage, TSDB v13, retention, and structured metadata."""
    loki = _load_yaml(LOKI_CONFIG_FILE)

    assert loki["server"]["http_listen_port"] == 3100
    assert loki["common"]["path_prefix"] == "/loki"
    assert loki["common"]["storage"]["filesystem"]["chunks_directory"] == "/loki/chunks"

    schemas = loki["schema_config"]["configs"]
    assert len(schemas) >= 1
    assert schemas[0]["store"] == "tsdb"
    assert schemas[0]["schema"] == "v13"

    assert loki["compactor"]["retention_enabled"] is True
    assert loki["limits_config"]["allow_structured_metadata"] is True
    assert loki["limits_config"]["retention_period"] == "168h"


def test_promtail_config_docker_sd_and_pipeline() -> None:
    """Promtail scrapes app, nginx/frontend, postgres, normalizes level, and tracks request_id."""
    promtail = _load_yaml(PROMTAIL_CONFIG_FILE)

    assert promtail["positions"]["filename"] == "/var/lib/promtail/positions.yaml"
    assert promtail["clients"][0]["url"] == "http://loki:3100/loki/api/v1/push"

    scrape_cfg = promtail["scrape_configs"][0]
    docker_sd = scrape_cfg["docker_sd_configs"][0]
    assert docker_sd["host"] == "unix:///var/run/docker.sock"
    assert {"name": "label", "values": ["logging=promtail"]} in docker_sd["filters"]

    relabel_targets = {rule.get("target_label") for rule in scrape_cfg["relabel_configs"]}
    assert {"service", "container", "stream"} <= relabel_targets

    stages = scrape_cfg["pipeline_stages"]
    stage_names = [next(iter(stage.keys())) for stage in stages]
    assert "replace" in stage_names
    assert "json" in stage_names
    assert "labels" in stage_names
    assert "structured_metadata" in stage_names

    json_stage = next(stage["json"] for stage in stages if "json" in stage)
    assert "json_request_id" in json_stage["expressions"]
    assert json_stage["expressions"]["json_request_id"] == "request_id"

    labels_stage = next(stage["labels"] for stage in stages if "labels" in stage)
    assert "level" in labels_stage
    assert "request_id" not in labels_stage  # Avoid high-cardinality index explosion

    sm_stage = next(
        stage["structured_metadata"] for stage in stages if "structured_metadata" in stage
    )
    assert "request_id" in sm_stage


@pytest.mark.parametrize(
    ("service", "sample_line", "expected_group", "expected_value"),
    [
        (
            "postgres",
            "2026-11-21 19:30:00.123 UTC [1] LOG:  database system is ready to accept connections",
            "pg_level",
            "LOG",
        ),
        (
            "postgres",
            "2026-11-21 19:31:02.456 UTC [42] ERROR:  duplicate key violates unique constraint",
            "pg_level",
            "ERROR",
        ),
        (
            "nginx",
            "2026/11/21 19:31:05 [error] 12#12: *4 connect() failed (111: Connection refused)",
            "nginx_err_level",
            "error",
        ),
        (
            "app",
            "WARNING:  Schedule conflict detected for lesson 42",
            "uvicorn_level",
            "WARNING",
        ),
    ],
)
def test_promtail_fallback_regexes_extract_service_levels(
    service: str,
    sample_line: str,
    expected_group: str,
    expected_value: str,
) -> None:
    """Promtail fallback regex stages match realistic Postgres, Nginx, and Uvicorn log lines."""
    promtail = _load_yaml(PROMTAIL_CONFIG_FILE)
    stages = promtail["scrape_configs"][0]["pipeline_stages"]

    match_stage = next(
        stage["match"]
        for stage in stages
        if "match" in stage and stage["match"]["selector"] == f'{{service="{service}"}}'
    )
    pattern = match_stage["stages"][0]["regex"]["expression"]
    matched = re.search(pattern, sample_line)
    assert matched is not None
    assert matched.group(expected_group) == expected_value


def test_promtail_redaction_regexes_mask_sensitive_values() -> None:
    """Promtail replace stage regexes identify bearer tokens, passwords, and session IDs."""
    promtail = _load_yaml(PROMTAIL_CONFIG_FILE)
    stages = promtail["scrape_configs"][0]["pipeline_stages"]
    replace_exprs = [stage["replace"]["expression"] for stage in stages if "replace" in stage]

    samples = [
        ('{"authorization": "Bearer super-secret-jwt-123"}', "super-secret-jwt-123"),
        ('{"password": "my-secret-password", "user": "admin"}', "my-secret-password"),
        ('{"session_id": "sess_abc123xyz", "path": "/api/v1/lessons"}', "sess_abc123xyz"),
    ]
    for line, secret in samples:
        captured = []
        for expr in replace_exprs:
            for match in re.finditer(expr, line):
                captured.extend(match.groups())
        assert secret in captured, f"Secret {secret!r} was not captured by redaction regexes"


def test_grafana_provisioning_and_logs_dashboard() -> None:
    """Grafana provisions Loki datasource and dashboard with service/level/request_id filters."""
    ds_cfg = _load_yaml(GRAFANA_DATASOURCE_FILE)
    loki_ds = ds_cfg["datasources"][0]
    assert loki_ds["uid"] == "loki"
    assert loki_ds["type"] == "loki"
    assert loki_ds["url"] == "http://loki:3100"
    assert loki_ds["editable"] is False
    derived = loki_ds["jsonData"]["derivedFields"][0]
    assert derived["datasourceUid"] == "loki"
    assert "request_id" in derived["matcherRegex"]
    assert "app|nginx" in derived["url"]

    prov_cfg = _load_yaml(GRAFANA_DASHBOARDS_PROV_FILE)
    provider = prov_cfg["providers"][0]
    assert provider["options"]["path"] == "/var/lib/grafana/dashboards"

    dashboard = json.loads(GRAFANA_LOGS_DASHBOARD_FILE.read_text(encoding="utf-8"))
    assert dashboard["uid"] == "schedule-service-logs"

    var_names = {var["name"]: var for var in dashboard["templating"]["list"]}
    assert {"service", "level", "request_id", "search"} <= set(var_names.keys())

    service_options = {opt["value"] for opt in var_names["service"]["options"]}
    assert {"app", "nginx", "postgres"} <= service_options

    level_options = {opt["value"] for opt in var_names["level"]["options"]}
    assert {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"} <= level_options

    panels = dashboard["panels"]
    assert len(panels) >= 4
    exprs = [target["expr"] for panel in panels for target in panel.get("targets", [])]
    for panel in panels:
        assert panel["datasource"]["uid"] == "loki"

    assert any('service=~"app|nginx"' in expr and "$request_id" in expr for expr in exprs)
    assert any(
        'service=~"$service"' in expr and 'level=~"$level"' in expr and "$request_id" in expr
        for expr in exprs
    )
