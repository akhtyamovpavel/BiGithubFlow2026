"""Tests for Nginx JSON access log format and X-Request-ID propagation (#61)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from schedule_service.core.logging import _SAFE_REQUEST_ID_RE

ROOT = Path(__file__).resolve().parent.parent
NGINX_TEMPLATE = ROOT / "frontend" / "nginx.conf.template"


def _read_template() -> str:
    return NGINX_TEMPLATE.read_text(encoding="utf-8")


def test_nginx_request_id_map_matches_backend_validation() -> None:
    conf = _read_template()
    match = re.search(
        r"map\s+\$http_x_request_id\s+\$resolved_request_id\s*\{(.*?)\n\}",
        conf,
        flags=re.DOTALL,
    )
    assert match is not None
    map_body = match.group(1)
    assert f'"~{_SAFE_REQUEST_ID_RE.pattern}"' in map_body
    assert "default $request_id;" in map_body


def test_nginx_json_log_format_fields_and_no_secret_leakage() -> None:
    conf = _read_template()
    assert "log_format json_access escape=json" in conf
    assert "access_log /dev/stdout json_access;" in conf

    for field in (
        '"request_id":"$resolved_request_id"',
        '"method":"$request_method"',
        '"uri":"$uri"',
    ):
        assert field in conf
    assert '"status":$status' in conf
    assert '"duration_s":$request_time' in conf

    for forbidden in (
        "$request_uri",
        "$args",
        "$query_string",
        "$http_authorization",
        "$http_cookie",
    ):
        assert forbidden not in conf


def test_nginx_json_log_template_produces_valid_json() -> None:
    conf = _read_template()
    match = re.search(r"log_format\s+json_access\s+escape=json\s+(.*?);", conf, flags=re.DOTALL)
    assert match is not None
    raw_template = "".join(re.findall(r"'([^']*)'", match.group(1)))

    replacements = {
        "$time_iso8601": "2026-11-21T20:20:00+03:00",
        "$resolved_request_id": "req-abc-123",
        "$request_method": "POST",
        "$uri": "/api/v1/lessons/",
        "$status": "409",
        "$request_time": "0.015",
        "$upstream_response_time": "0.014",
        "$body_bytes_sent": "256",
        "$remote_addr": "172.18.0.1",
    }
    rendered = raw_template
    for var, val in replacements.items():
        rendered = rendered.replace(var, val)

    payload = json.loads(rendered)
    assert payload["service"] == "nginx"
    assert payload["request_id"] == "req-abc-123"
    assert payload["method"] == "POST"
    assert payload["uri"] == "/api/v1/lessons/"
    assert payload["status"] == 409
    assert payload["duration_s"] == 0.015


def test_nginx_propagates_and_deduplicates_request_id_header() -> None:
    conf = _read_template()
    public_server = conf.split("server {")[1]
    assert "add_header X-Request-ID $resolved_request_id always;" in public_server

    proxy_locations = [
        block
        for block in re.findall(r"location\s+[^{]+\{.*?\n    \}", public_server, flags=re.DOTALL)
        if "proxy_pass" in block
    ]
    assert len(proxy_locations) == 3
    for block in proxy_locations:
        assert "proxy_set_header X-Request-ID $resolved_request_id;" in block
        assert "proxy_hide_header X-Request-ID;" in block

    # Locations defining their own add_header must also preserve X-Request-ID
    for loc_header in ("location /assets/", "location / {"):
        loc_match = re.search(
            re.escape(loc_header) + r".*?\n    \}", public_server, flags=re.DOTALL
        )
        assert loc_match is not None
        assert "add_header X-Request-ID $resolved_request_id always;" in loc_match.group(0)
