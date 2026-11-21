"""Tests for Prometheus configuration, alert rules, and Grafana datasource (Part of #50)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
OBS = ROOT / "observability"


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_prometheus_service_and_networks_in_observability_compose() -> None:
    compose = _load_yaml(ROOT / "docker-compose.observability.yml")
    prom = compose["services"]["prometheus"]
    grafana = compose["services"]["grafana"]

    assert "ports" not in prom
    assert "9090" in prom["expose"]
    assert "monitoring" in prom["networks"]
    assert "healthcheck" in prom
    assert "prometheus_data" in compose["volumes"]
    assert {"default", "monitoring"} <= set(grafana["networks"])
    assert "prometheus" in grafana["depends_on"]


def test_prometheus_scrape_targets_and_rule_files() -> None:
    cfg = _load_yaml(OBS / "prometheus" / "prometheus.yml")
    assert "/etc/prometheus/alerts.yml" in cfg["rule_files"]

    targets_by_job = {
        job["job_name"]: job["static_configs"][0]["targets"] for job in cfg["scrape_configs"]
    }
    assert targets_by_job["schedule-app"] == ["app:8000"]
    assert targets_by_job["postgres-exporter"] == ["postgres-exporter:9187"]
    assert targets_by_job["nginx-exporter"] == ["nginx-exporter:9113"]


def test_prometheus_alert_rules_cover_availability_errors_and_latency() -> None:
    alerts_cfg = _load_yaml(OBS / "prometheus" / "alerts.yml")
    rules = {r["alert"]: r for g in alerts_cfg["groups"] for r in g["rules"]}

    for name in (
        "ServiceTargetDown",
        "PostgreSQLDown",
        "NginxDown",
        "HighHttp5xxErrorRate",
        "HighHttpP95Latency",
    ):
        assert name in rules
        assert rules[name]["for"]
        assert rules[name]["annotations"]["summary"]

    assert 'status_class="5xx"' in rules["HighHttp5xxErrorRate"]["expr"]
    assert "[5m]" in rules["HighHttp5xxErrorRate"]["expr"]
    assert "> 0.05" in rules["HighHttp5xxErrorRate"]["expr"]
    assert "histogram_quantile(0.95" in rules["HighHttpP95Latency"]["expr"]
    assert "[5m]" in rules["HighHttpP95Latency"]["expr"]
    assert "> 0.5" in rules["HighHttpP95Latency"]["expr"]


def test_grafana_prometheus_datasource_provisioned() -> None:
    ds_cfg = _load_yaml(OBS / "grafana" / "provisioning" / "datasources" / "prometheus.yml")
    ds = ds_cfg["datasources"][0]
    assert ds["uid"] == "prometheus"
    assert ds["type"] == "prometheus"
    assert ds["url"] == "http://prometheus:9090"
    assert ds["isDefault"] is True


def test_grafana_metrics_dashboard_and_runbook_cover_all_signals() -> None:
    dashboard_path = OBS / "grafana" / "dashboards" / "metrics.json"
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    assert dashboard["uid"] == "schedule-service-metrics"
    assert len(dashboard["panels"]) >= 10

    exprs = " ".join(
        t["expr"] for p in dashboard["panels"] for t in p.get("targets", []) if "expr" in t
    )
    for required in (
        'up{job="schedule-app"}',
        "pg_up",
        "nginx_up",
        "http_requests_total",
        'status_class="5xx"',
        "histogram_quantile(0.50",
        "histogram_quantile(0.95",
        "histogram_quantile(0.99",
        "schedule_lessons_created_total",
        "schedule_conflicts_detected_total",
        "schedule_exports_total",
        "schedule_db_entities_count",
        "pg_stat_activity_count",
        "nginx_connections_active",
    ):
        assert required in exprs, f"Missing PromQL expression fragment: {required}"

    runbook = (ROOT / "docs" / "MONITORING.md").read_text(encoding="utf-8")
    for section in ("api/v1/targets", "api/v1/alerts", "NginxDown", "HighHttp5xxErrorRate"):
        assert section in runbook
