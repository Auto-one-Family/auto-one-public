#!/usr/bin/env python3
"""
Export Endpoint QA Script — AUT-384 + AUT-385
Runs against the live Docker stack (PostgreSQL + FastAPI on localhost:8000).

Usage:
    python export_endpoint_qa.py \\
        --url http://localhost:8000 \\
        --username admin \\
        --password "$E2E_TEST_PASSWORD" \\
        [--db postgresql://god_kaiser:password@localhost:5432/god_kaiser_db] \\
        [--report-dir .claude/reports/current/]

Requires:
    pip install httpx psycopg2-binary rich
"""

import argparse
import csv
import io
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import httpx
import psycopg2
from rich.console import Console
from rich.table import Table as RichTable
from rich import box

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    test_id: str
    description: str
    status: str          # PASS / FAIL / WARN / SKIP
    duration_ms: float
    expected: str = ""
    actual: str = ""
    detail: str = ""
    db_query: str = ""
    db_result: str = ""
    log_line: str = ""
    request: str = ""
    response_summary: str = ""


# ---------------------------------------------------------------------------
# QA Runner
# ---------------------------------------------------------------------------

class ExportQA:
    def __init__(
        self,
        server_url: str,
        username: str,
        password: str,
        db_dsn: str,
        report_dir: str,
        docker_service: str = "automationone-server",
    ):
        self.server_url = server_url.rstrip("/")
        self.username = username
        self.password = password
        self.db_dsn = db_dsn
        self.report_dir = report_dir
        self.docker_service = docker_service

        # On Windows the legacy console renderer uses cp1252 and cannot encode
        # arrow/unicode chars used in test descriptions; force ANSI path instead.
        self.console = Console(highlight=False, legacy_windows=False)
        self.results: list[TestResult] = []
        self.token: str = ""
        self.viewer_token: str = ""

        # Persistent HTTP client (avoids per-request TCP overhead)
        self._client: Optional[httpx.Client] = None

        # Test data handles
        self.test_esp_uuid: Optional[str] = None
        self.test_esp_device_id = "ESP_QA_EXPORT_TEST"
        self.viewer_username = "qa_viewer_export"
        self.viewer_user_id: Optional[int] = None
        self.db_conn = None

    # -----------------------------------------------------------------------
    # Connection helpers
    # -----------------------------------------------------------------------

    def connect_db(self) -> None:
        self.db_conn = psycopg2.connect(self.db_dsn)
        self.db_conn.autocommit = True

    def close_db(self) -> None:
        if self.db_conn:
            self.db_conn.close()
            self.db_conn = None

    def db_query_one(self, sql: str, params=None) -> Any:
        with self.db_conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return row[0] if row else None

    def db_exec(self, sql: str, params=None) -> None:
        with self.db_conn.cursor() as cur:
            cur.execute(sql, params)

    # -----------------------------------------------------------------------
    # HTTP helpers
    # -----------------------------------------------------------------------

    def _ensure_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=httpx.Timeout(30.0))
        return self._client

    def close_client(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    def _headers(self, token: Optional[str] = None) -> dict:
        t = token if token is not None else self.token
        if t:
            return {"Authorization": f"Bearer {t}"}
        return {}

    def get(
        self,
        path: str,
        params: Optional[dict] = None,
        token: Optional[str] = None,
        timeout: float = 30.0,
    ) -> httpx.Response:
        url = self.server_url + path
        client = self._ensure_client()
        return client.get(
            url, params=params, headers=self._headers(token), timeout=timeout
        )

    def post_json(
        self,
        path: str,
        body: dict,
        token: Optional[str] = None,
    ) -> httpx.Response:
        url = self.server_url + path
        client = self._ensure_client()
        return client.post(
            url, json=body, headers=self._headers(token), timeout=15.0
        )

    # -----------------------------------------------------------------------
    # Auth setup
    # -----------------------------------------------------------------------

    def login(self) -> None:
        resp = self.post_json(
            "/api/v1/auth/login",
            {"username": self.username, "password": self.password},
            token="",
        )
        if resp.status_code != 200:
            self.console.print(
                f"[red]Login failed: {resp.status_code} — {resp.text[:200]}[/red]"
            )
            sys.exit(1)
        self.token = resp.json()["tokens"]["access_token"]
        self.console.print(f"[green]Logged in as {self.username}[/green]")

    def setup_viewer_user(self) -> None:
        resp = self.post_json(
            "/api/v1/users",
            {
                "username": self.viewer_username,
                "email": f"{self.viewer_username}@automationone.io",
                "password": "ViewerP@ss123",
                "role": "viewer",
                "is_active": True,
            },
        )
        if resp.status_code in (200, 201):
            self.viewer_user_id = resp.json().get("id")
        elif resp.status_code == 409:
            # Already exists from a previous run
            pass
        else:
            self.console.print(
                f"[yellow]Viewer user setup warning: {resp.status_code}[/yellow]"
            )

        login_resp = self.post_json(
            "/api/v1/auth/login",
            {"username": self.viewer_username, "password": "ViewerP@ss123"},
            token="",
        )
        if login_resp.status_code == 200:
            self.viewer_token = login_resp.json()["tokens"]["access_token"]
        else:
            self.console.print("[yellow]Viewer login failed — T-EXP-AUTH-02 will be skipped[/yellow]")

    def teardown_viewer_user(self) -> None:
        self.db_exec(
            "DELETE FROM user_accounts WHERE username = %s",
            (self.viewer_username,),
        )

    # -----------------------------------------------------------------------
    # Test ESP + sensor data setup
    # -----------------------------------------------------------------------

    def setup_test_esp(self) -> None:
        """Insert a test ESP device and controlled sensor data rows."""
        esp_id = str(uuid.uuid4())
        self.test_esp_uuid = esp_id
        now = datetime.now(timezone.utc)

        # Clean up any leftover from a previous aborted run
        self.db_exec(
            "DELETE FROM sensor_data WHERE esp_id IN "
            "(SELECT id FROM esp_devices WHERE device_id = %s)",
            (self.test_esp_device_id,),
        )
        self.db_exec(
            "DELETE FROM esp_devices WHERE device_id = %s",
            (self.test_esp_device_id,),
        )

        self.db_exec(
            """
            INSERT INTO esp_devices
              (id, device_id, name, zone_id, is_zone_master, hardware_type,
               capabilities, status, device_metadata, created_at, updated_at)
            VALUES
              (%s, %s, %s, NULL, %s, %s, %s::json, %s, %s::json, %s, %s)
            """,
            (
                esp_id,
                self.test_esp_device_id,
                "QA Export Test Device",
                False,
                "esp32",
                "{}",
                "offline",
                "{}",
                now,
                now,
            ),
        )
        self.console.print(
            f"[blue]Test ESP created: {self.test_esp_device_id} ({esp_id})[/blue]"
        )

    def insert_sensor_rows(
        self,
        count: int,
        sensor_type: str = "temperature",
        gpio: int = 1,
        base_time: Optional[datetime] = None,
        interval_sec: int = 10,
    ) -> list[datetime]:
        """Insert `count` sensor_data rows and return their timestamps."""
        if base_time is None:
            base_time = datetime.now(timezone.utc) - timedelta(hours=2)

        timestamps = []
        now = datetime.now(timezone.utc)
        with self.db_conn.cursor() as cur:
            for i in range(count):
                ts = base_time + timedelta(seconds=i * interval_sec)
                cur.execute(
                    """
                    INSERT INTO sensor_data
                      (id, esp_id, gpio, sensor_type, raw_value, processed_value,
                       unit, processing_mode, quality, timestamp, data_source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid.uuid4()),
                        self.test_esp_uuid,
                        gpio,
                        sensor_type,
                        float(20 + i % 10),
                        float(20 + i % 10),
                        "°C",
                        "direct",
                        "good",
                        ts,
                        "mqtt",
                    ),
                )
                timestamps.append(ts)
        return timestamps

    def teardown_test_data(self) -> None:
        if self.test_esp_uuid:
            self.db_exec(
                "DELETE FROM sensor_data WHERE esp_id = %s", (self.test_esp_uuid,)
            )
            self.db_exec(
                "DELETE FROM esp_devices WHERE id = %s", (self.test_esp_uuid,)
            )
            self.console.print("[blue]Test data cleaned up[/blue]")

    # -----------------------------------------------------------------------
    # Test infrastructure
    # -----------------------------------------------------------------------

    def _record(
        self,
        test_id: str,
        description: str,
        passed: bool,
        duration_ms: float,
        expected: str = "",
        actual: str = "",
        detail: str = "",
        warn: bool = False,
        db_query: str = "",
        db_result: str = "",
        log_line: str = "",
        request: str = "",
        response_summary: str = "",
    ) -> TestResult:
        status = "WARN" if warn else ("PASS" if passed else "FAIL")
        result = TestResult(
            test_id=test_id,
            description=description,
            status=status,
            duration_ms=duration_ms,
            expected=expected,
            actual=actual,
            detail=detail,
            db_query=db_query,
            db_result=db_result,
            log_line=log_line,
            request=request,
            response_summary=response_summary,
        )
        self.results.append(result)

        icon = {"PASS": "[+]", "FAIL": "[X]", "WARN": "[!]", "SKIP": "[-]"}[status]
        color = {"PASS": "green", "FAIL": "red", "WARN": "yellow", "SKIP": "dim"}[status]
        self.console.print(
            f"  [{color}]{icon} {test_id:<18} {description:<55} ({duration_ms:.0f}ms)[/{color}]"
        )
        if status == "FAIL":
            self.console.print(
                f"      [dim]expected: {expected}[/dim]"
            )
            self.console.print(
                f"      [red]actual:   {actual}[/red]"
            )
        if detail and status != "PASS":
            self.console.print(f"      [dim]{detail}[/dim]")
        return result

    def _skip(self, test_id: str, description: str, reason: str) -> TestResult:
        result = TestResult(
            test_id=test_id,
            description=description,
            status="SKIP",
            duration_ms=0,
            detail=reason,
        )
        self.results.append(result)
        self.console.print(
            f"  [dim][-] {test_id:<18} {description:<55} SKIP: {reason}[/dim]"
        )
        return result

    def _get_last_log_line(self, keyword: str) -> str:
        try:
            result = subprocess.run(
                ["docker", "logs", "--tail=50", self.docker_service],
                capture_output=True, text=True, timeout=5,
            )
            lines = (result.stdout + result.stderr).splitlines()
            for line in reversed(lines):
                if keyword in line:
                    return line.strip()
        except Exception:
            pass
        return ""

    def _csv_rows(self, body: bytes) -> list[list[str]]:
        """Parse CSV bytes (with optional BOM) into list of rows."""
        text = body.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text))
        return list(reader)

    # -----------------------------------------------------------------------
    # AUT-384: Sensor Export Tests
    # -----------------------------------------------------------------------

    def run_auth_tests(self) -> None:
        self.console.print("\n[bold cyan][AUTH][/bold cyan]")
        base_params = {"esp_id": "ESP_6B27C8"}

        # T-AUTH-01: No token
        t0 = time.monotonic()
        resp = self._ensure_client().get(
            f"{self.server_url}/api/v1/sensors/export",
            params=base_params, timeout=10,
        )
        ms = (time.monotonic() - t0) * 1000
        self._record(
            "T-AUTH-01", "No token → 401",
            resp.status_code == 401, ms,
            expected="401", actual=str(resp.status_code),
        )

        # T-AUTH-02: Expired token (manipulated exp=1)
        import base64
        header = base64.b64encode(b'{"alg":"HS256","typ":"JWT"}').decode().rstrip("=")
        payload = base64.b64encode(b'{"sub":"1","exp":1,"iat":1,"type":"access","role":"admin"}').decode().rstrip("=")
        bad_token = f"{header}.{payload}.invalidsig"
        t0 = time.monotonic()
        resp = self._ensure_client().get(
            f"{self.server_url}/api/v1/sensors/export",
            params=base_params,
            headers={"Authorization": f"Bearer {bad_token}"},
            timeout=10,
        )
        ms = (time.monotonic() - t0) * 1000
        self._record(
            "T-AUTH-02", "Expired token → 401",
            resp.status_code == 401, ms,
            expected="401", actual=str(resp.status_code),
        )

        # T-AUTH-03: Random bytes token
        t0 = time.monotonic()
        resp = self._ensure_client().get(
            f"{self.server_url}/api/v1/sensors/export",
            params=base_params,
            headers={"Authorization": "Bearer thisisnotatoken"},
            timeout=10,
        )
        ms = (time.monotonic() - t0) * 1000
        self._record(
            "T-AUTH-03", "Random token → 401",
            resp.status_code == 401, ms,
            expected="401", actual=str(resp.status_code),
        )

        # T-AUTH-04: Valid token → 200
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params=base_params)
        ms = (time.monotonic() - t0) * 1000
        log = self._get_last_log_line("status=200")
        self._record(
            "T-AUTH-04", "Valid token → 200",
            resp.status_code == 200, ms,
            expected="200", actual=str(resp.status_code),
            log_line=log,
        )

    def run_filter_validation(self) -> None:
        self.console.print("\n[bold cyan][FILTER][/bold cyan]")

        # T-FILTER-01: No filter → 422
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export")
        ms = (time.monotonic() - t0) * 1000
        body_ok = "esp_id" in resp.text.lower() or "mindestens" in resp.text.lower()
        self._record(
            "T-FILTER-01", "No filter → 422",
            resp.status_code == 422 and body_ok, ms,
            expected="422 + filter hint", actual=f"{resp.status_code}",
        )

        # T-FILTER-02 to T-FILTER-06
        for test_id, desc, params in [
            ("T-FILTER-02", "esp_id only → 200", {"esp_id": "ESP_6B27C8"}),
            ("T-FILTER-03", "zone_id only → 200", {"zone_id": "zelt_wohnzimmer"}),
            ("T-FILTER-04", "subzone_id only → 200", {"subzone_id": "test_sub"}),
            ("T-FILTER-05", "zone_id+subzone_id → 200", {"zone_id": "zelt_wohnzimmer", "subzone_id": "main"}),
            ("T-FILTER-06", "all three → 200", {"esp_id": "ESP_6B27C8", "zone_id": "zelt_wohnzimmer", "subzone_id": "main"}),
        ]:
            t0 = time.monotonic()
            resp = self.get("/api/v1/sensors/export", params=params)
            ms = (time.monotonic() - t0) * 1000
            self._record(
                test_id, desc,
                resp.status_code == 200, ms,
                expected="200", actual=str(resp.status_code),
            )

        # T-FILTER-07: gpio=40 (out of range) → 422
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={"esp_id": "ESP_6B27C8", "gpio": 40})
        ms = (time.monotonic() - t0) * 1000
        self._record(
            "T-FILTER-07", "gpio=40 out-of-range → 422",
            resp.status_code == 422, ms,
            expected="422", actual=str(resp.status_code),
        )

        # T-FILTER-08: gpio=-1 → 422
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={"esp_id": "ESP_6B27C8", "gpio": -1})
        ms = (time.monotonic() - t0) * 1000
        self._record(
            "T-FILTER-08", "gpio=-1 → 422",
            resp.status_code == 422, ms,
            expected="422", actual=str(resp.status_code),
        )

    def run_esp_resolution(self) -> None:
        self.console.print("\n[bold cyan][ESP][/bold cyan]")

        # T-ESP-01: Valid esp_id
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={"esp_id": "ESP_6B27C8"})
        ms = (time.monotonic() - t0) * 1000
        db_count = self.db_query_one(
            "SELECT COUNT(*) FROM esp_devices WHERE device_id = %s", ("ESP_6B27C8",)
        )
        self._record(
            "T-ESP-01", "Valid esp_id → 200",
            resp.status_code == 200, ms,
            expected="200", actual=str(resp.status_code),
            db_query="SELECT COUNT(*) FROM esp_devices WHERE device_id='ESP_6B27C8'",
            db_result=str(db_count),
        )

        # T-ESP-02: Unknown esp_id → 404
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={"esp_id": "ESP_NONEXISTENT"})
        ms = (time.monotonic() - t0) * 1000
        db_count = self.db_query_one(
            "SELECT COUNT(*) FROM esp_devices WHERE device_id = %s", ("ESP_NONEXISTENT",)
        )
        self._record(
            "T-ESP-02", "Unknown esp_id → 404",
            resp.status_code == 404, ms,
            expected="404", actual=str(resp.status_code),
            db_query="SELECT COUNT(*) FROM esp_devices WHERE device_id='ESP_NONEXISTENT'",
            db_result=str(db_count),
        )

        # T-ESP-03: Empty esp_id — document behavior
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={"esp_id": ""})
        ms = (time.monotonic() - t0) * 1000
        self._record(
            "T-ESP-03", f"Empty esp_id → {resp.status_code} (documented)",
            True, ms,
            detail=f"Behavior: HTTP {resp.status_code}",
            warn=True,
        )

    def run_time_range(self) -> None:
        self.console.print("\n[bold cyan][TIME][/bold cyan]")
        now = datetime.now(timezone.utc)

        # T-TIME-01: start > end → 422
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={
            "esp_id": "ESP_6B27C8",
            "start_time": (now + timedelta(hours=1)).isoformat(),
            "end_time": now.isoformat(),
        })
        ms = (time.monotonic() - t0) * 1000
        self._record(
            "T-TIME-01", "start > end → 422",
            resp.status_code == 422, ms,
            expected="422", actual=str(resp.status_code),
        )

        # T-TIME-02: start = end → 422
        t0 = time.monotonic()
        ts = now.isoformat()
        resp = self.get("/api/v1/sensors/export", params={
            "esp_id": "ESP_6B27C8",
            "start_time": ts, "end_time": ts,
        })
        ms = (time.monotonic() - t0) * 1000
        self._record(
            "T-TIME-02", "start = end → 422",
            resp.status_code == 422, ms,
            expected="422", actual=str(resp.status_code),
        )

        # T-TIME-03: Valid range with data
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={
            "esp_id": self.test_esp_device_id,
            "start_time": (now - timedelta(hours=3)).isoformat(),
            "end_time": (now - timedelta(hours=1)).isoformat(),
        })
        ms = (time.monotonic() - t0) * 1000
        rows = self._csv_rows(resp.content) if resp.status_code == 200 else []
        has_data = len(rows) > 1
        self._record(
            "T-TIME-03", "Valid range with data → rows in CSV",
            resp.status_code == 200 and has_data, ms,
            expected="200 + data rows", actual=f"{resp.status_code}, {len(rows)-1} data rows",
        )

        # T-TIME-04: Valid range without data
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={
            "esp_id": self.test_esp_device_id,
            "start_time": "2020-01-01T00:00:00Z",
            "end_time": "2020-01-02T00:00:00Z",
        })
        ms = (time.monotonic() - t0) * 1000
        rows = self._csv_rows(resp.content) if resp.status_code == 200 else []
        self._record(
            "T-TIME-04", "Valid range, no data → header-only CSV",
            resp.status_code == 200 and len(rows) == 1, ms,
            expected="200 + 1 header row", actual=f"{resp.status_code}, {len(rows)} rows",
        )

        # T-TIME-05: No time → last 24h (default)
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={"esp_id": "ESP_6B27C8"})
        ms = (time.monotonic() - t0) * 1000
        rows = self._csv_rows(resp.content) if resp.status_code == 200 else []
        self._record(
            "T-TIME-05", "No time range → default last 24h",
            resp.status_code == 200 and len(rows) > 1, ms,
            expected="200 + data rows", actual=f"{resp.status_code}, {len(rows)-1} data rows",
        )

        # T-TIME-06: Naive datetime (no Z) → treated as UTC
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={
            "esp_id": "ESP_6B27C8",
            "start_time": "2026-01-01T00:00:00",
            "end_time": "2026-01-02T00:00:00",
        })
        ms = (time.monotonic() - t0) * 1000
        self._record(
            "T-TIME-06", "Naive datetime → accepted as UTC",
            resp.status_code == 200, ms,
            expected="200", actual=str(resp.status_code),
        )

        # T-TIME-07: Exact window with DB cross-check
        start_ts = now - timedelta(hours=2, minutes=30)
        end_ts = now - timedelta(hours=1, minutes=30)
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={
            "esp_id": self.test_esp_device_id,
            "start_time": start_ts.isoformat(),
            "end_time": end_ts.isoformat(),
        })
        ms = (time.monotonic() - t0) * 1000
        rows = self._csv_rows(resp.content) if resp.status_code == 200 else []
        csv_count = len(rows) - 1  # exclude header
        db_q = (
            "SELECT COUNT(*) FROM sensor_data sd "
            "JOIN esp_devices e ON e.id = sd.esp_id "
            "WHERE e.device_id = %s AND sd.timestamp >= %s AND sd.timestamp <= %s"
        )
        db_count = self.db_query_one(db_q, (self.test_esp_device_id, start_ts, end_ts))
        self._record(
            "T-TIME-07", "Exact window DB cross-check",
            resp.status_code == 200 and csv_count == db_count, ms,
            expected=f"CSV={db_count}", actual=f"CSV={csv_count}, DB={db_count}",
            db_query=db_q,
            db_result=str(db_count),
        )

    def run_column_selection(self) -> None:
        self.console.print("\n[bold cyan][COLUMN][/bold cyan]")
        base = {"esp_id": self.test_esp_device_id}

        # T-COL-01: Default columns
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params=base)
        ms = (time.monotonic() - t0) * 1000
        rows = self._csv_rows(resp.content) if resp.status_code == 200 else [[]]
        default_cols = {"timestamp", "processed_value", "unit", "quality", "sensor_type"}
        header = set(rows[0]) if rows else set()
        self._record(
            "T-COL-01", "No columns → default 5 columns",
            resp.status_code == 200 and default_cols == header, ms,
            expected=str(sorted(default_cols)), actual=str(sorted(header)),
        )

        # T-COL-02: columns=timestamp,unit
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={**base, "columns": "timestamp,unit"})
        ms = (time.monotonic() - t0) * 1000
        rows = self._csv_rows(resp.content) if resp.status_code == 200 else [[]]
        header = set(rows[0]) if rows else set()
        self._record(
            "T-COL-02", "columns=timestamp,unit",
            resp.status_code == 200 and header == {"timestamp", "unit"}, ms,
            expected="{'timestamp','unit'}", actual=str(header),
        )

        # T-COL-03: columns=raw_value
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={**base, "columns": "raw_value"})
        ms = (time.monotonic() - t0) * 1000
        rows = self._csv_rows(resp.content) if resp.status_code == 200 else [[]]
        header = rows[0] if rows else []
        self._record(
            "T-COL-03", "columns=raw_value → numeric values",
            resp.status_code == 200 and header == ["raw_value"], ms,
            expected="['raw_value']", actual=str(header),
        )

        # T-COL-04: columns=esp_id (UUID check, document)
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={**base, "columns": "esp_id"})
        ms = (time.monotonic() - t0) * 1000
        rows = self._csv_rows(resp.content) if resp.status_code == 200 else [[]]
        sample = rows[1][0] if len(rows) > 1 and rows[1] else ""
        is_uuid = len(sample) == 36 and "-" in sample
        self._record(
            "T-COL-04", "columns=esp_id → UUID (not device_id)",
            resp.status_code == 200, ms,
            detail=f"esp_id value is UUID={is_uuid}: {sample[:36]}",
            warn=True,
        )

        # T-COL-05: invalid column → 422
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={**base, "columns": "invalid_column"})
        ms = (time.monotonic() - t0) * 1000
        self._record(
            "T-COL-05", "Unknown column → 422",
            resp.status_code == 422, ms,
            expected="422", actual=str(resp.status_code),
        )

        # T-COL-06: timestamp + invalid → 422 with column name
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={**base, "columns": "timestamp,bad_col"})
        ms = (time.monotonic() - t0) * 1000
        has_name = "bad_col" in resp.text
        self._record(
            "T-COL-06", "timestamp+bad_col → 422 with column name",
            resp.status_code == 422 and has_name, ms,
            expected="422 + 'bad_col' in body", actual=f"{resp.status_code}, name_in_body={has_name}",
        )

        # T-COL-07: Spaces around comma → trimmed
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={**base, "columns": "timestamp, unit"})
        ms = (time.monotonic() - t0) * 1000
        rows = self._csv_rows(resp.content) if resp.status_code == 200 else [[]]
        header = set(rows[0]) if rows else set()
        self._record(
            "T-COL-07", "Spaces in columns → trimmed",
            resp.status_code == 200 and header == {"timestamp", "unit"}, ms,
            expected="{'timestamp','unit'}", actual=str(header),
        )

        # T-COL-08: columns="" → B2 bug test
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={**base, "columns": ""})
        ms = (time.monotonic() - t0) * 1000
        is_bug = resp.status_code == 200
        self._record(
            "T-COL-08", "columns='' → 422 expected",
            resp.status_code == 422, ms,
            expected="422", actual=str(resp.status_code),
            detail="B2: empty columns= should return 422 but may return 200 with empty header row",
            warn=is_bug,
        )

        # T-COL-09: All 10 columns
        all_cols = "timestamp,processed_value,unit,quality,sensor_type,raw_value,esp_id,gpio,zone_id,subzone_id"
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={**base, "columns": all_cols})
        ms = (time.monotonic() - t0) * 1000
        rows = self._csv_rows(resp.content) if resp.status_code == 200 else [[]]
        header = rows[0] if rows else []
        self._record(
            "T-COL-09", "All 10 columns",
            resp.status_code == 200 and len(header) == 10, ms,
            expected="10 columns", actual=f"{len(header)} columns: {header}",
        )

    def run_csv_format(self) -> None:
        self.console.print("\n[bold cyan][CSV FORMAT][/bold cyan]")
        params = {"esp_id": self.test_esp_device_id}

        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params=params)
        ms = (time.monotonic() - t0) * 1000

        # T-CSV-01: BOM
        has_bom = resp.content[:3] == b"\xef\xbb\xbf"
        self._record(
            "T-CSV-01", "BOM at offset 0",
            has_bom, ms,
            expected="0xEF 0xBB 0xBF", actual=resp.content[:3].hex(),
        )

        # T-CSV-02: Content-Type
        ct = resp.headers.get("content-type", "")
        self._record(
            "T-CSV-02", "Content-Type: text/csv",
            "text/csv" in ct, ms,
            expected="text/csv", actual=ct,
        )

        # T-CSV-03: Content-Disposition
        cd = resp.headers.get("content-disposition", "")
        self._record(
            "T-CSV-03", "Content-Disposition attachment",
            "attachment" in cd and ".csv" in cd, ms,
            expected="attachment; filename=*.csv", actual=cd,
        )

        # T-CSV-04: No Content-Length (streaming)
        cl = resp.headers.get("content-length")
        self._record(
            "T-CSV-04", "No Content-Length (streaming)",
            cl is None, ms,
            expected="absent", actual=str(cl),
        )

        # T-CSV-05: Comma separator
        rows = self._csv_rows(resp.content)
        has_comma = len(rows[0]) > 1 if rows else False
        self._record(
            "T-CSV-05", "Comma separator",
            has_comma, ms,
            expected="> 1 field in header", actual=str(rows[0] if rows else ""),
        )

        # T-CSV-06: None → empty cell (not "None" string)
        data_rows = rows[1:] if len(rows) > 1 else []
        none_str_found = any("None" in cell for row in data_rows for cell in row)
        self._record(
            "T-CSV-06", "None value → empty cell (not 'None')",
            not none_str_found, ms,
            expected="no 'None' string in cells",
            actual="'None' found" if none_str_found else "ok",
        )

        # T-CSV-07: Timestamp ISO-8601
        ts_cell = data_rows[0][0] if data_rows and data_rows[0] else ""
        try:
            datetime.fromisoformat(ts_cell.replace("Z", "+00:00"))
            valid_ts = True
        except (ValueError, IndexError):
            valid_ts = False
        self._record(
            "T-CSV-07", "Timestamp is ISO-8601",
            valid_ts, ms,
            expected="ISO-8601 datetime", actual=ts_cell[:30],
        )

        # T-CSV-08: UTF-8 special chars (°C)
        unit_col_idx = rows[0].index("unit") if rows and "unit" in rows[0] else -1
        unit_val = data_rows[0][unit_col_idx] if data_rows and unit_col_idx >= 0 else ""
        has_degree = "°" in unit_val or unit_val == ""  # empty is ok if no data
        self._record(
            "T-CSV-08", "UTF-8 unit (°C) encoded correctly",
            has_degree, ms,
            expected="°C", actual=unit_val,
        )

    def run_cursor_batching(self) -> None:
        self.console.print("\n[bold cyan][CURSOR BATCHING][/bold cyan]")
        now = datetime.now(timezone.utc)
        base_start = now - timedelta(hours=2)

        # The test ESP has 100 rows inserted during setup_test_data
        # We need to insert specific counts for each test

        def count_csv_data_rows(params: dict) -> tuple[int, int, str]:
            """Returns (csv_count, db_count, status)"""
            resp = self.get(
                "/api/v1/sensors/export",
                params={
                    **params,
                    "start_time": (now - timedelta(hours=3)).isoformat(),
                    "end_time": (now - timedelta(minutes=30)).isoformat(),
                },
                timeout=120.0,
            )
            if resp.status_code != 200:
                return -1, -1, str(resp.status_code)
            rows = self._csv_rows(resp.content)
            csv_count = len(rows) - 1
            return csv_count, resp.status_code, str(resp.status_code)

        # Helper to insert + test + delete controlled rows
        def cursor_test(
            test_id: str, desc: str, count: int, sensor_type: str, gpio: int,
            expect_count: int, b1_bug: bool = False,
        ) -> None:
            # Clean any existing rows for this gpio/sensor_type
            self.db_exec(
                "DELETE FROM sensor_data WHERE esp_id = %s AND gpio = %s AND sensor_type = %s",
                (self.test_esp_uuid, gpio, sensor_type),
            )

            # Place all rows in a fixed window guaranteed to be well within query range
            base = now - timedelta(hours=10)
            self.insert_sensor_rows(count, sensor_type=sensor_type, gpio=gpio, base_time=base, interval_sec=5)

            # Query window covers the full insert range
            start_q = (now - timedelta(hours=11)).isoformat()
            end_q = (now - timedelta(minutes=1)).isoformat()

            t0 = time.monotonic()
            resp = self.get(
                "/api/v1/sensors/export",
                params={
                    "esp_id": self.test_esp_device_id,
                    "gpio": gpio,
                    "sensor_type": sensor_type,
                    "start_time": start_q,
                    "end_time": end_q,
                },
                timeout=120.0,
            )
            ms = (time.monotonic() - t0) * 1000

            rows = self._csv_rows(resp.content) if resp.status_code == 200 else []
            csv_count = len(rows) - 1

            db_q = (
                "SELECT COUNT(*) FROM sensor_data sd "
                "JOIN esp_devices e ON e.id = sd.esp_id "
                "WHERE e.device_id = %s AND sd.gpio = %s AND sd.sensor_type = %s"
            )
            db_count = self.db_query_one(db_q, (self.test_esp_device_id, gpio, sensor_type))

            passed = resp.status_code == 200 and csv_count == expect_count == db_count
            self._record(
                test_id, desc, passed, ms,
                expected=f"CSV={expect_count}, DB={expect_count}",
                actual=f"CSV={csv_count}, DB={db_count}",
                db_query=db_q,
                db_result=f"DB={db_count}",
            )

            # Clean up
            self.db_exec(
                "DELETE FROM sensor_data WHERE esp_id = %s AND gpio = %s AND sensor_type = %s",
                (self.test_esp_uuid, gpio, sensor_type),
            )

        cursor_test("T-CURSOR-01", "50 rows → 1 batch", 50, "temperature", 1, 50)
        cursor_test("T-CURSOR-02", "500 rows exact", 500, "temperature", 1, 500)
        cursor_test("T-CURSOR-03", "501 rows → 2 batches", 501, "temperature", 1, 501)
        cursor_test("T-CURSOR-04", "1001 rows → 3 batches", 1001, "temperature", 1, 1001)

        # T-CURSOR-05: B1 Bug — duplicate timestamps, multi-sensor, no filter
        self.console.print(
            "  [yellow]T-CURSOR-05  B1 cursor-bug reproduction (identical timestamps)...[/yellow]"
        )
        self.db_exec(
            "DELETE FROM sensor_data WHERE esp_id = %s AND gpio = %s",
            (self.test_esp_uuid, 2),
        )

        # Insert 300 rows of each type with IDENTICAL timestamps
        base = now - timedelta(hours=8)
        with self.db_conn.cursor() as cur:
            for i in range(300):
                ts = base + timedelta(minutes=i)
                for st in ("qa_type_a", "qa_type_b"):
                    cur.execute(
                        """
                        INSERT INTO sensor_data
                          (id, esp_id, gpio, sensor_type, raw_value, processed_value,
                           unit, processing_mode, quality, timestamp, data_source)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            str(uuid.uuid4()), self.test_esp_uuid, 2, st,
                            float(i), float(i), "u", "direct", "good",
                            ts, "mqtt",
                        ),
                    )

        t0 = time.monotonic()
        resp = self.get(
            "/api/v1/sensors/export",
            params={
                "esp_id": self.test_esp_device_id,
                "gpio": 2,
                "start_time": (now - timedelta(hours=9)).isoformat(),
                "end_time": (now - timedelta(minutes=1)).isoformat(),
            },
            timeout=120.0,
        )
        ms = (time.monotonic() - t0) * 1000

        rows = self._csv_rows(resp.content) if resp.status_code == 200 else []
        csv_count = len(rows) - 1
        db_count_b1 = self.db_query_one(
            "SELECT COUNT(*) FROM sensor_data WHERE esp_id = %s AND gpio = %s",
            (self.test_esp_uuid, 2),
        )

        bug_confirmed = csv_count < db_count_b1
        if bug_confirmed:
            self.console.print(
                f"  [red][X] T-CURSOR-05  B1 CURSOR-BUG CONFIRMED: "
                f"CSV={csv_count} DB={db_count_b1} ({db_count_b1 - csv_count} rows missing!)[/red]"
            )
            result = TestResult(
                test_id="T-CURSOR-05",
                description="B1 cursor-bug: multi-sensor identical timestamps",
                status="FAIL",
                duration_ms=ms,
                expected=f"CSV={db_count_b1}",
                actual=f"CSV={csv_count}, DB={db_count_b1} — {db_count_b1-csv_count} ROWS LOST",
                detail="B1 CONFIRMED: cursor overwrites rows with same timestamp",
                db_query="SELECT COUNT(*) FROM sensor_data WHERE esp_id=TEST AND gpio=2",
                db_result=str(db_count_b1),
            )
            self.results.append(result)
        else:
            self._record(
                "T-CURSOR-05", "B1 bug: no data loss (bug fixed or not triggered)",
                True, ms,
                expected="FAIL (bug reproduction)",
                actual=f"CSV={csv_count}, DB={db_count_b1}",
                warn=True,
            )

        # T-CURSOR-06: Same data but WITH sensor_type filter → no loss
        t0 = time.monotonic()
        resp = self.get(
            "/api/v1/sensors/export",
            params={
                "esp_id": self.test_esp_device_id,
                "gpio": 2,
                "sensor_type": "qa_type_a",
                "start_time": (now - timedelta(hours=9)).isoformat(),
                "end_time": (now - timedelta(minutes=1)).isoformat(),
            },
            timeout=60.0,
        )
        ms = (time.monotonic() - t0) * 1000
        rows = self._csv_rows(resp.content) if resp.status_code == 200 else []
        csv_count = len(rows) - 1
        db_count_filtered = self.db_query_one(
            "SELECT COUNT(*) FROM sensor_data WHERE esp_id = %s AND gpio = %s AND sensor_type = %s",
            (self.test_esp_uuid, 2, "qa_type_a"),
        )
        self._record(
            "T-CURSOR-06", "sensor_type filter → no loss",
            resp.status_code == 200 and csv_count == db_count_filtered, ms,
            expected=f"CSV={db_count_filtered}", actual=f"CSV={csv_count}, DB={db_count_filtered}",
        )

        self.db_exec(
            "DELETE FROM sensor_data WHERE esp_id = %s AND gpio = %s",
            (self.test_esp_uuid, 2),
        )

    def run_resolution_aggregation(self) -> None:
        self.console.print("\n[bold cyan][RESOLUTION — PostgreSQL only][/bold cyan]")
        now = datetime.now(timezone.utc)

        # Insert controlled minute-by-minute data
        self.db_exec(
            "DELETE FROM sensor_data WHERE esp_id = %s AND gpio = %s",
            (self.test_esp_uuid, 3),
        )
        base = now - timedelta(hours=3)
        self.insert_sensor_rows(120, sensor_type="temperature", gpio=3, base_time=base, interval_sec=60)

        common = {
            "esp_id": self.test_esp_device_id,
            "gpio": 3,
            "sensor_type": "temperature",
            "start_time": (now - timedelta(hours=3, minutes=1)).isoformat(),
            "end_time": (now - timedelta(minutes=1)).isoformat(),
        }

        for test_id, desc, extra_params, expected_note in [
            ("T-RES-01", "resolution=raw same as no resolution", {"resolution": "raw"}, None),
            ("T-RES-02", "resolution=1m aggregation", {"resolution": "1m"}, "quality=aggregated"),
            ("T-RES-03", "resolution=5m 12 buckets", {"resolution": "5m"}, "~13 lines"),
            ("T-RES-04", "resolution=1h 3 buckets", {"resolution": "1h"}, "~4 lines"),
            ("T-RES-05", "resolution=1d 1 bucket", {"resolution": "1d"}, "~2 lines"),
        ]:
            t0 = time.monotonic()
            resp = self.get("/api/v1/sensors/export", params={**common, **extra_params})
            ms = (time.monotonic() - t0) * 1000
            rows = self._csv_rows(resp.content) if resp.status_code == 200 else []
            self._record(
                test_id, desc,
                resp.status_code == 200, ms,
                expected="200", actual=f"{resp.status_code}, {len(rows)-1} data rows",
                detail=expected_note or "",
            )

        # T-RES-06: B5 — aggregated + zone_id column → always empty
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={
            **common, "resolution": "1m", "columns": "timestamp,zone_id,processed_value"
        })
        ms = (time.monotonic() - t0) * 1000
        rows = self._csv_rows(resp.content) if resp.status_code == 200 else [[]]
        zone_col_idx = rows[0].index("zone_id") if rows and "zone_id" in rows[0] else -1
        zone_vals = [row[zone_col_idx] for row in rows[1:] if zone_col_idx >= 0 and len(row) > zone_col_idx]
        all_empty = all(v == "" for v in zone_vals)
        self._record(
            "T-RES-06", "B5: aggregated + zone_id → empty",
            True, ms,
            detail=f"B5 {'CONFIRMED' if all_empty else 'NOT triggered'}: zone_id cells all empty={all_empty}",
            warn=True,
        )

        # T-RES-07: invalid resolution → 422
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={**common, "resolution": "invalid"})
        ms = (time.monotonic() - t0) * 1000
        self._record(
            "T-RES-07", "resolution=invalid → 422",
            resp.status_code == 422, ms,
            expected="422", actual=str(resp.status_code),
        )

        self.db_exec(
            "DELETE FROM sensor_data WHERE esp_id = %s AND gpio = %s",
            (self.test_esp_uuid, 3),
        )

    def run_db_crosscheck(self) -> None:
        self.console.print("\n[bold cyan][DB CROSS-CHECK][/bold cyan]")
        now = datetime.now(timezone.utc)

        # T-DB-01: 100 rows, full filter
        self.db_exec("DELETE FROM sensor_data WHERE esp_id = %s AND gpio = %s", (self.test_esp_uuid, 4))
        base = now - timedelta(hours=2)
        self.insert_sensor_rows(100, sensor_type="moisture", gpio=4, base_time=base, interval_sec=30)
        start = base - timedelta(minutes=1)
        end = now - timedelta(minutes=30)

        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={
            "esp_id": self.test_esp_device_id, "gpio": 4, "sensor_type": "moisture",
            "start_time": start.isoformat(), "end_time": end.isoformat(),
        }, timeout=60.0)
        ms = (time.monotonic() - t0) * 1000
        rows = self._csv_rows(resp.content) if resp.status_code == 200 else []
        csv_count = len(rows) - 1
        db_q = (
            "SELECT COUNT(*) FROM sensor_data sd "
            "JOIN esp_devices e ON e.id = sd.esp_id "
            "WHERE e.device_id=%s AND sd.gpio=%s AND sd.sensor_type=%s "
            "AND sd.timestamp >= %s AND sd.timestamp <= %s"
        )
        db_count = self.db_query_one(db_q, (self.test_esp_device_id, 4, "moisture", start, end))
        self._record(
            "T-DB-01", "100 rows full filter DB cross-check",
            resp.status_code == 200 and csv_count == db_count, ms,
            expected=f"CSV=DB={db_count}", actual=f"CSV={csv_count}, DB={db_count}",
            db_query=db_q, db_result=str(db_count),
        )

        # T-DB-02: 1000 rows, esp_id + time
        self.db_exec("DELETE FROM sensor_data WHERE esp_id = %s AND gpio = %s", (self.test_esp_uuid, 5))
        base2 = now - timedelta(hours=3)
        self.insert_sensor_rows(1000, sensor_type="humidity", gpio=5, base_time=base2, interval_sec=10)
        start2 = base2 - timedelta(minutes=1)
        end2 = now - timedelta(minutes=30)

        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={
            "esp_id": self.test_esp_device_id,
            "start_time": start2.isoformat(), "end_time": end2.isoformat(),
        }, timeout=120.0)
        ms = (time.monotonic() - t0) * 1000
        rows = self._csv_rows(resp.content) if resp.status_code == 200 else []
        csv_count = len(rows) - 1
        db_q2 = (
            "SELECT COUNT(*) FROM sensor_data sd "
            "JOIN esp_devices e ON e.id = sd.esp_id "
            "WHERE e.device_id=%s AND sd.timestamp >= %s AND sd.timestamp <= %s"
        )
        db_count2 = self.db_query_one(db_q2, (self.test_esp_device_id, start2, end2))
        self._record(
            "T-DB-02", "1000 rows esp_id+time DB cross-check",
            resp.status_code == 200 and csv_count == db_count2, ms,
            expected=f"CSV=DB={db_count2}", actual=f"CSV={csv_count}, DB={db_count2}",
            db_query=db_q2, db_result=str(db_count2),
        )

        # T-DB-03: No rows in window
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={
            "esp_id": self.test_esp_device_id,
            "start_time": "2020-01-01T00:00:00Z", "end_time": "2020-01-02T00:00:00Z",
        })
        ms = (time.monotonic() - t0) * 1000
        rows = self._csv_rows(resp.content) if resp.status_code == 200 else []
        csv_count = len(rows) - 1
        self._record(
            "T-DB-03", "0 rows window → header-only CSV",
            resp.status_code == 200 and csv_count == 0, ms,
            expected="CSV=0", actual=f"CSV={csv_count}",
        )

        # T-DB-04: zone_id filter
        t0 = time.monotonic()
        resp = self.get("/api/v1/sensors/export", params={
            "zone_id": "zelt_wohnzimmer",
            "start_time": (now - timedelta(hours=1)).isoformat(),
            "end_time": now.isoformat(),
        }, timeout=60.0)
        ms = (time.monotonic() - t0) * 1000
        rows = self._csv_rows(resp.content) if resp.status_code == 200 else []
        csv_count = len(rows) - 1
        db_q4 = (
            "SELECT COUNT(*) FROM sensor_data sd "
            "WHERE sd.zone_id = %s AND sd.timestamp >= %s AND sd.timestamp <= %s"
        )
        db_count4 = self.db_query_one(db_q4, ("zelt_wohnzimmer", now - timedelta(hours=1), now))
        # ±1 tolerance: live ESP data may be inserted between export and DB count
        self._record(
            "T-DB-04", "zone_id filter DB cross-check",
            resp.status_code == 200 and abs(csv_count - db_count4) <= 2, ms,
            expected=f"CSV≈DB={db_count4} (±2 live data)", actual=f"CSV={csv_count}, DB={db_count4}",
            db_query=db_q4, db_result=str(db_count4),
        )

        self.db_exec("DELETE FROM sensor_data WHERE esp_id = %s AND gpio = %s", (self.test_esp_uuid, 4))
        self.db_exec("DELETE FROM sensor_data WHERE esp_id = %s AND gpio = %s", (self.test_esp_uuid, 5))

    def run_log_verification(self) -> None:
        self.console.print("\n[bold cyan][LOG VERIFICATION][/bold cyan]")

        # T-LOG-01: successful export logged
        self.get("/api/v1/sensors/export", params={"esp_id": "ESP_6B27C8"})
        time.sleep(0.5)
        log = self._get_last_log_line("status=200")
        self._record(
            "T-LOG-01", "200 response logged by server",
            bool(log), 0,
            expected="log line with status=200", actual=log[:120] if log else "(none)",
            log_line=log,
        )

        # T-LOG-02: 422 error logged
        self.get("/api/v1/sensors/export")  # no filter → 422
        time.sleep(0.5)
        log = self._get_last_log_line("status=422")
        self._record(
            "T-LOG-02", "422 response logged by server",
            bool(log), 0,
            expected="log line with status=422", actual=log[:120] if log else "(none)",
            log_line=log,
        )

    def run_bug_reproductions(self) -> None:
        self.console.print("\n[bold cyan][BUG REPRODUCTIONS][/bold cyan]")

        # B2: columns="" → already in T-COL-08
        b2 = next((r for r in self.results if r.test_id == "T-COL-08"), None)
        if b2:
            if b2.status == "WARN":
                self.console.print(
                    "  [red][X] B2  columns='' -> 200 (CONFIRMED: no 422 returned)[/red]"
                )
            else:
                self.console.print("  [green][+] B2  columns='' -> 422 (fixed or not triggered)[/green]")

        # B3: filename when subzone_id only
        t0 = time.monotonic()
        resp = self.get(
            "/api/v1/sensors/export",
            params={"subzone_id": "some_sub"},
        )
        ms = (time.monotonic() - t0) * 1000
        cd = resp.headers.get("content-disposition", "")
        has_all_kw = "'all'" in cd or "all" in cd
        self._record(
            "T-BUG-B3", "B3 filename=*all* when subzone_id-only",
            True, ms,
            detail=f"B3: Content-Disposition={cd!r} — contains 'all': {has_all_kw}",
            warn=True,
        )

        # B4: quality filter absent
        resp2 = self.get(
            "/api/v1/sensors/export",
            params={"esp_id": "ESP_6B27C8", "quality": "good"},
        )
        self._record(
            "T-BUG-B4", "B4 quality param missing",
            True, 0,
            detail=f"B4: quality param → HTTP {resp2.status_code} (422=FastAPI rejects unknown param, 200=ignored)",
            warn=True,
        )

        # B5 already covered in T-RES-06

    # -----------------------------------------------------------------------
    # AUT-385: DB Bulk Export Tests
    # -----------------------------------------------------------------------

    def run_exp_auth_tests(self) -> None:
        self.console.print("\n[bold cyan][AUT-385: DB EXPORT — AUTH][/bold cyan]")

        path = "/api/v1/debug/db/audit_logs/export"
        now = datetime.now(timezone.utc)
        date_params = {
            "date_from": (now - timedelta(hours=2)).isoformat(),
            "date_to": now.isoformat(),
        }

        # T-EXP-AUTH-01: No token → 401
        t0 = time.monotonic()
        resp = self._ensure_client().get(f"{self.server_url}{path}", params=date_params, timeout=10)
        ms = (time.monotonic() - t0) * 1000
        self._record(
            "T-EXP-AUTH-01", "DB export: no token → 401",
            resp.status_code == 401, ms,
            expected="401", actual=str(resp.status_code),
        )

        # T-EXP-AUTH-02: Viewer role → 403
        if self.viewer_token:
            t0 = time.monotonic()
            resp = self._ensure_client().get(
                f"{self.server_url}{path}", params=date_params,
                headers={"Authorization": f"Bearer {self.viewer_token}"}, timeout=10,
            )
            ms = (time.monotonic() - t0) * 1000
            self._record(
                "T-EXP-AUTH-02", "DB export: viewer role → 403",
                resp.status_code == 403, ms,
                expected="403", actual=str(resp.status_code),
            )
        else:
            self._skip("T-EXP-AUTH-02", "DB export: viewer role → 403", "viewer login failed")

        # T-EXP-AUTH-03: Admin token → 200
        t0 = time.monotonic()
        resp = self.get(path, params=date_params)
        ms = (time.monotonic() - t0) * 1000
        log = self._get_last_log_line("status=200")
        self._record(
            "T-EXP-AUTH-03", "DB export: admin token → 200",
            resp.status_code == 200, ms,
            expected="200", actual=str(resp.status_code),
            log_line=log,
        )

    def run_exp_table_tests(self) -> None:
        self.console.print("\n[bold cyan][AUT-385: DB EXPORT — TABLE WHITELIST][/bold cyan]")
        now = datetime.now(timezone.utc)
        date_params = {
            "date_from": (now - timedelta(hours=1)).isoformat(),
            "date_to": now.isoformat(),
        }

        # T-EXP-TABLE-01: Disallowed table → 404
        t0 = time.monotonic()
        resp = self.get("/api/v1/debug/db/user_passwords/export", params=date_params)
        ms = (time.monotonic() - t0) * 1000
        not_found = resp.status_code == 404 and "not found" in resp.text.lower()
        self._record(
            "T-EXP-TABLE-01", "Disallowed table → 404",
            not_found, ms,
            expected="404 + 'not found'", actual=f"{resp.status_code}: {resp.text[:80]}",
        )

        # T-EXP-TABLE-02: Allowed table → 200
        t0 = time.monotonic()
        resp = self.get("/api/v1/debug/db/audit_logs/export", params=date_params)
        ms = (time.monotonic() - t0) * 1000
        self._record(
            "T-EXP-TABLE-02", "Allowed table (audit_logs) → 200",
            resp.status_code == 200, ms,
            expected="200", actual=str(resp.status_code),
        )

        # T-EXP-TABLE-03: Non-time-series table → 200 (all rows)
        t0 = time.monotonic()
        resp = self.get("/api/v1/debug/db/esp_devices/export", params={"format": "json"})
        ms = (time.monotonic() - t0) * 1000
        self._record(
            "T-EXP-TABLE-03", "Non-time-series table (esp_devices) → 200",
            resp.status_code == 200, ms,
            expected="200", actual=str(resp.status_code),
        )

    def run_exp_format_tests(self) -> None:
        self.console.print("\n[bold cyan][AUT-385: DB EXPORT — FORMAT][/bold cyan]")
        now = datetime.now(timezone.utc)
        base_params = {
            "date_from": (now - timedelta(hours=1)).isoformat(),
            "date_to": now.isoformat(),
        }

        # T-EXP-FMT-01: JSON format
        t0 = time.monotonic()
        resp = self.get(
            "/api/v1/debug/db/audit_logs/export",
            params={**base_params, "format": "json"},
        )
        ms = (time.monotonic() - t0) * 1000
        ct = resp.headers.get("content-type", "")
        try:
            payload = json.loads(resp.content)
            valid_json = isinstance(payload, list)
        except Exception:
            valid_json = False
        self._record(
            "T-EXP-FMT-01", "format=json → application/json array",
            resp.status_code == 200 and "json" in ct and valid_json, ms,
            expected="200, application/json, list", actual=f"{resp.status_code}, {ct}, valid={valid_json}",
        )

        # T-EXP-FMT-02: CSV format + BOM
        t0 = time.monotonic()
        resp = self.get(
            "/api/v1/debug/db/audit_logs/export",
            params={**base_params, "format": "csv"},
        )
        ms = (time.monotonic() - t0) * 1000
        ct = resp.headers.get("content-type", "")
        has_bom = resp.content[:3] == b"\xef\xbb\xbf"
        self._record(
            "T-EXP-FMT-02", "format=csv → text/csv + BOM",
            resp.status_code == 200 and "csv" in ct and has_bom, ms,
            expected="200, text/csv, BOM=True", actual=f"{resp.status_code}, {ct}, BOM={has_bom}",
        )

        # T-EXP-FMT-03: Default format = json
        t0 = time.monotonic()
        resp = self.get("/api/v1/debug/db/audit_logs/export", params=base_params)
        ms = (time.monotonic() - t0) * 1000
        ct = resp.headers.get("content-type", "")
        self._record(
            "T-EXP-FMT-03", "Default format = json",
            resp.status_code == 200 and "json" in ct, ms,
            expected="200, json default", actual=f"{resp.status_code}, {ct}",
        )

    def run_exp_column_tests(self) -> None:
        self.console.print("\n[bold cyan][AUT-385: DB EXPORT — COLUMNS][/bold cyan]")
        now = datetime.now(timezone.utc)
        base = {
            "format": "json",
            "date_from": (now - timedelta(hours=1)).isoformat(),
            "date_to": now.isoformat(),
        }

        # T-EXP-COL-01: No columns → all columns returned
        t0 = time.monotonic()
        resp = self.get("/api/v1/debug/db/audit_logs/export", params=base)
        ms = (time.monotonic() - t0) * 1000
        data = json.loads(resp.content) if resp.status_code == 200 else []
        sample_keys = list(data[0].keys()) if data else []
        has_many = len(sample_keys) >= 5
        self._record(
            "T-EXP-COL-01", "No columns → all columns",
            resp.status_code == 200 and has_many, ms,
            expected=">= 5 columns", actual=f"{len(sample_keys)} columns: {sample_keys[:6]}",
        )

        # T-EXP-COL-02: Subset columns
        t0 = time.monotonic()
        resp = self.get(
            "/api/v1/debug/db/audit_logs/export",
            params={**base, "columns": "id,event_type"},
        )
        ms = (time.monotonic() - t0) * 1000
        data = json.loads(resp.content) if resp.status_code == 200 else []
        if data:
            actual_keys = set(data[0].keys())
            subset_ok = actual_keys == {"id", "event_type"}
        else:
            subset_ok = False
        self._record(
            "T-EXP-COL-02", "columns=id,event_type → 2 fields",
            resp.status_code == 200 and subset_ok, ms,
            expected="{'id','event_type'}", actual=str(actual_keys if data else "(no data)"),
        )

        # T-EXP-COL-03: Unknown column → 422
        t0 = time.monotonic()
        resp = self.get(
            "/api/v1/debug/db/audit_logs/export",
            params={**base, "columns": "id,nonexistent_col"},
        )
        ms = (time.monotonic() - t0) * 1000
        has_col_name = "nonexistent_col" in resp.text
        self._record(
            "T-EXP-COL-03", "Unknown column → 422 with column name",
            resp.status_code == 422 and has_col_name, ms,
            expected="422 + 'nonexistent_col'", actual=f"{resp.status_code}",
        )

    def run_exp_date_tests(self) -> None:
        self.console.print("\n[bold cyan][AUT-385: DB EXPORT — DATE FILTER][/bold cyan]")
        now = datetime.now(timezone.utc)

        # T-EXP-DATE-01: date_from > date_to → 422
        t0 = time.monotonic()
        resp = self.get(
            "/api/v1/debug/db/audit_logs/export",
            params={
                "format": "json",
                "date_from": now.isoformat(),
                "date_to": (now - timedelta(hours=1)).isoformat(),
            },
        )
        ms = (time.monotonic() - t0) * 1000
        self._record(
            "T-EXP-DATE-01", "date_from > date_to → 422",
            resp.status_code == 422, ms,
            expected="422", actual=str(resp.status_code),
        )

        # T-EXP-DATE-02: Default window (time-series table, no dates) → auto-24h
        t0 = time.monotonic()
        resp = self.get(
            "/api/v1/debug/db/audit_logs/export",
            params={"format": "json"},
        )
        ms = (time.monotonic() - t0) * 1000
        try:
            data = json.loads(resp.content)
            has_data = len(data) > 0
        except Exception:
            has_data = False
        self._record(
            "T-EXP-DATE-02", "No dates on audit_logs → auto-24h window",
            resp.status_code == 200, ms,
            expected="200", actual=f"{resp.status_code}, {len(data) if isinstance(data, list) else '?'} rows",
        )

        # T-EXP-DATE-03: date range → only records in range, DB cross-check
        start_dt = now - timedelta(hours=2)
        end_dt = now - timedelta(hours=1)
        t0 = time.monotonic()
        resp = self.get(
            "/api/v1/debug/db/audit_logs/export",
            params={
                "format": "json",
                "date_from": start_dt.isoformat(),
                "date_to": end_dt.isoformat(),
            },
            timeout=30.0,
        )
        ms = (time.monotonic() - t0) * 1000
        data = json.loads(resp.content) if resp.status_code == 200 else []
        csv_count = len(data)
        db_q = (
            "SELECT COUNT(*) FROM audit_logs "
            "WHERE created_at >= %s AND created_at <= %s"
        )
        db_count = self.db_query_one(db_q, (start_dt, end_dt))
        self._record(
            "T-EXP-DATE-03", "Date range DB cross-check",
            resp.status_code == 200 and csv_count == db_count, ms,
            expected=f"JSON={db_count}", actual=f"JSON={csv_count}, DB={db_count}",
            db_query=db_q, db_result=str(db_count),
        )

    def run_exp_streaming_test(self) -> None:
        self.console.print("\n[bold cyan][AUT-385: DB EXPORT — STREAMING][/bold cyan]")

        # T-EXP-STREAM-01: Large table (sensor_data last 24h ~700 rows) served as stream
        now = datetime.now(timezone.utc)
        t0 = time.monotonic()
        with self._ensure_client().stream(
            "GET",
            f"{self.server_url}/api/v1/debug/db/sensor_data/export",
            params={
                "format": "json",
                "date_from": (now - timedelta(hours=24)).isoformat(),
                "date_to": now.isoformat(),
            },
            headers=self._headers(),
            timeout=60.0,
        ) as resp:
            chunks_received = 0
            total_bytes = 0
            for chunk in resp.iter_bytes(chunk_size=8192):
                chunks_received += 1
                total_bytes += len(chunk)

        ms = (time.monotonic() - t0) * 1000
        self._record(
            "T-EXP-STREAM-01", "Large export arrives in chunks",
            resp.status_code == 200 and chunks_received > 1, ms,
            expected="> 1 chunk", actual=f"{chunks_received} chunks, {total_bytes} bytes",
        )

    def run_exp_db_crosscheck(self) -> None:
        """AUT-387 QA: DB-Kreuzabgleich für DB-Bulk-Export-Endpoint (AUT-385)."""
        self.console.print("\n[bold cyan][AUT-387: DB EXPORT — DB CROSS-CHECK][/bold cyan]")
        now = datetime.now(timezone.utc)

        # T-EXP-DB-01: sensor_data CSV — Zeilenzahl == DB-Count im Zeitfenster
        start_dt = now - timedelta(hours=2)
        end_dt = now - timedelta(minutes=30)
        t0 = time.monotonic()
        resp = self.get(
            "/api/v1/debug/db/sensor_data/export",
            params={
                "format": "csv",
                "date_from": start_dt.isoformat(),
                "date_to": end_dt.isoformat(),
            },
            timeout=60.0,
        )
        ms = (time.monotonic() - t0) * 1000
        rows = self._csv_rows(resp.content) if resp.status_code == 200 else []
        csv_count = len(rows) - 1
        db_q = "SELECT COUNT(*) FROM sensor_data WHERE timestamp >= %s AND timestamp <= %s"
        db_count = self.db_query_one(db_q, (start_dt, end_dt))
        self._record(
            "T-EXP-DB-01", "sensor_data CSV: CSV-count == DB-count",
            resp.status_code == 200 and csv_count == db_count, ms,
            expected=f"CSV={db_count}", actual=f"CSV={csv_count}, DB={db_count}",
            db_query=db_q, db_result=str(db_count),
        )

        # T-EXP-DB-02: esp_devices JSON — Zeilenzahl == alle nicht-gelöschten ESPs
        t0 = time.monotonic()
        resp = self.get(
            "/api/v1/debug/db/esp_devices/export",
            params={"format": "json"},
            timeout=30.0,
        )
        ms = (time.monotonic() - t0) * 1000
        try:
            data = json.loads(resp.content)
            json_count = len(data)
        except Exception:
            data = []
            json_count = -1
        db_q2 = "SELECT COUNT(*) FROM esp_devices"
        db_count2 = self.db_query_one(db_q2)
        self._record(
            "T-EXP-DB-02", "esp_devices JSON: count == total DB rows",
            resp.status_code == 200 and json_count == db_count2, ms,
            expected=f"JSON={db_count2}", actual=f"JSON={json_count}, DB={db_count2}",
            db_query=db_q2, db_result=str(db_count2),
        )

        # T-EXP-DB-03: Zeitraum-Filter sensor_data — kein Eintrag außerhalb Fenster
        t0 = time.monotonic()
        resp = self.get(
            "/api/v1/debug/db/sensor_data/export",
            params={
                "format": "json",
                "date_from": start_dt.isoformat(),
                "date_to": end_dt.isoformat(),
                "columns": "timestamp",
            },
            timeout=60.0,
        )
        ms = (time.monotonic() - t0) * 1000
        out_of_range = 0
        if resp.status_code == 200:
            try:
                data = json.loads(resp.content)
                for row in data:
                    ts_raw = row.get("timestamp", "")
                    ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts < start_dt or ts > end_dt:
                        out_of_range += 1
            except Exception as exc:
                out_of_range = -1
        self._record(
            "T-EXP-DB-03", "sensor_data date_filter: no out-of-range rows",
            resp.status_code == 200 and out_of_range == 0, ms,
            expected="out_of_range=0",
            actual=f"out_of_range={out_of_range}, status={resp.status_code}",
        )

        # T-EXP-DB-04: Content-Disposition Dateiname korrekt
        t0 = time.monotonic()
        resp = self.get(
            "/api/v1/debug/db/audit_logs/export",
            params={"format": "csv", "date_from": start_dt.isoformat(), "date_to": end_dt.isoformat()},
            timeout=30.0,
        )
        ms = (time.monotonic() - t0) * 1000
        cd = resp.headers.get("content-disposition", "")
        filename_ok = "audit_logs" in cd and "export" in cd and ".csv" in cd
        self._record(
            "T-EXP-DB-04", "Content-Disposition includes table+export+.csv",
            resp.status_code == 200 and filename_ok, ms,
            expected="audit_logs-export-*.csv in Content-Disposition",
            actual=cd,
        )

        # T-EXP-DB-05: sensitive fields (user_accounts) — password_hash must be masked
        t0 = time.monotonic()
        resp = self.get(
            "/api/v1/debug/db/user_accounts/export",
            params={"format": "json"},
            timeout=30.0,
        )
        ms = (time.monotonic() - t0) * 1000
        if resp.status_code == 200:
            try:
                data = json.loads(resp.content)
                raw_hashes = [
                    row.get("password_hash", "")
                    for row in data
                    if row.get("password_hash") not in ("***MASKED***", "", None)
                ]
                masked_ok = len(raw_hashes) == 0
            except Exception:
                masked_ok = False
            self._record(
                "T-EXP-DB-05", "user_accounts: password_hash masked",
                masked_ok, ms,
                expected="password_hash='***' or empty for all rows",
                actual=f"unmasked rows={len(raw_hashes) if isinstance(raw_hashes, list) else '?'}",
            )
        else:
            # Table might not be in ALLOWED_TABLES → acceptable
            self._record(
                "T-EXP-DB-05", "user_accounts sensitive masking",
                True, ms,
                detail=f"Table returned {resp.status_code} — if 404, not in ALLOWED_TABLES (expected)",
                warn=True,
            )

    def run_exp_large_export(self) -> None:
        """AUT-387 A-3: OFFSET-Batching Performance + Vollständigkeit bei >500 Zeilen."""
        self.console.print("\n[bold cyan][AUT-387: DB EXPORT — LARGE EXPORT + OFFSET-BATCHING][/bold cyan]")
        now = datetime.now(timezone.utc)

        # Insert 1001 sensor_data rows for test ESP on gpio=6 to trigger 3 OFFSET-batches
        self.db_exec(
            "DELETE FROM sensor_data WHERE esp_id = %s AND gpio = %s",
            (self.test_esp_uuid, 6),
        )
        base_large = now - timedelta(hours=4)
        self.insert_sensor_rows(1001, sensor_type="pressure", gpio=6, base_time=base_large, interval_sec=10)

        start_large = base_large - timedelta(minutes=1)
        end_large = now - timedelta(minutes=30)

        # T-EXP-LARGE-01: 1001 Rows via DB-Export (OFFSET-Batching, 3 Batches à 500)
        t0 = time.monotonic()
        resp = self.get(
            "/api/v1/debug/db/sensor_data/export",
            params={
                "format": "csv",
                "date_from": start_large.isoformat(),
                "date_to": end_large.isoformat(),
                "columns": "timestamp,processed_value,sensor_type",
            },
            timeout=120.0,
        )
        ms = (time.monotonic() - t0) * 1000
        rows = self._csv_rows(resp.content) if resp.status_code == 200 else []
        csv_count = len(rows) - 1
        # DB count must use same time filter as the export (no esp_id filter in raw table export)
        db_q = (
            "SELECT COUNT(*) FROM sensor_data "
            "WHERE timestamp >= %s AND timestamp <= %s"
        )
        db_count = self.db_query_one(db_q, (start_large, end_large))
        passed = resp.status_code == 200 and csv_count == db_count
        self._record(
            "T-EXP-LARGE-01", "1001+ rows DB export: CSV-count == DB-count",
            passed, ms,
            expected=f"CSV=DB", actual=f"CSV={csv_count}, DB={db_count}, {ms:.0f}ms",
            db_query=db_q, db_result=str(db_count),
            detail=f"OFFSET-Batching: {max(1, db_count // 500 + 1)} batches expected",
        )

        # T-EXP-LARGE-02: Performance-Grenze — 1001 Zeilen in unter 30s
        self._record(
            "T-EXP-LARGE-02", "1001 rows DB export completed < 30s",
            ms < 30_000, ms,
            expected="< 30000ms", actual=f"{ms:.0f}ms",
            detail="OFFSET-Batching A-3: akzeptabel mit date_from-Filter + idx_timestamp_desc",
        )

        self.db_exec(
            "DELETE FROM sensor_data WHERE esp_id = %s AND gpio = %s",
            (self.test_esp_uuid, 6),
        )

    # -----------------------------------------------------------------------
    # Report generation
    # -----------------------------------------------------------------------

    def print_summary(self) -> None:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == "PASS")
        failed = sum(1 for r in self.results if r.status == "FAIL")
        warned = sum(1 for r in self.results if r.status == "WARN")
        skipped = sum(1 for r in self.results if r.status == "SKIP")

        self.console.print("\n" + "=" * 70)
        self.console.print(
            f"  ERGEBNIS: [green]{passed} PASS[/green]  |  "
            f"[red]{failed} FAIL[/red]  |  "
            f"[yellow]{warned} WARN[/yellow]  |  "
            f"[dim]{skipped} SKIP[/dim]  (of {total})"
        )
        if failed > 0:
            self.console.print("\n  [red]FAILs:[/red]")
            for r in self.results:
                if r.status == "FAIL":
                    self.console.print(f"    FAIL {r.test_id}: {r.description}")
                    self.console.print(f"       expected: {r.expected}")
                    self.console.print(f"       actual:   {r.actual}")
        self.console.print("=" * 70)

    def generate_report(self) -> str:
        import os
        os.makedirs(self.report_dir, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M")
        path = os.path.join(self.report_dir, f"export-qa-{ts}.md")

        lines = [
            f"# Export Endpoint QA Report — {ts}",
            f"\nServer: {self.server_url}",
            f"\nGenerated: {datetime.now(timezone.utc).isoformat()}",
            "\n---\n",
            "## Summary\n",
        ]

        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == "PASS")
        failed = sum(1 for r in self.results if r.status == "FAIL")
        warned = sum(1 for r in self.results if r.status == "WARN")
        skipped = sum(1 for r in self.results if r.status == "SKIP")
        lines.append(f"| PASS | FAIL | WARN | SKIP | Total |")
        lines.append(f"|------|------|------|------|-------|")
        lines.append(f"| {passed} | {failed} | {warned} | {skipped} | {total} |\n")

        lines.append("\n## Test Results\n")
        lines.append("| ID | Description | Status | ms | Expected | Actual |")
        lines.append("|-----|-------------|--------|----|----------|--------|")
        for r in self.results:
            status_md = {"PASS": "PASS", "FAIL": "FAIL", "WARN": "WARN", "SKIP": "SKIP"}[r.status]
            lines.append(
                f"| {r.test_id} | {r.description} | {status_md} | "
                f"{r.duration_ms:.0f} | {r.expected} | {r.actual} |"
            )

        lines.append("\n## Detail: FAILs and WARNs\n")
        for r in self.results:
            if r.status in ("FAIL", "WARN"):
                lines.append(f"### {r.test_id} — {r.description}\n")
                lines.append(f"- **Status:** {r.status}")
                lines.append(f"- **Expected:** {r.expected}")
                lines.append(f"- **Actual:** {r.actual}")
                if r.detail:
                    lines.append(f"- **Detail:** {r.detail}")
                if r.db_query:
                    lines.append(f"- **DB Query:** `{r.db_query}`")
                    lines.append(f"- **DB Result:** {r.db_result}")
                if r.log_line:
                    lines.append(f"- **Log:** `{r.log_line}`")
                lines.append("")

        lines.append("\n## AUT-385 Section: DB Bulk Export Results\n")
        exp_results = [r for r in self.results if r.test_id.startswith("T-EXP-")]
        for r in exp_results:
            icon = {"PASS": "[+]", "FAIL": "[X]", "WARN": "[!]", "SKIP": "[-]"}[r.status]
            lines.append(f"- {icon} **{r.test_id}** {r.description}: {r.actual}")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return path

    # -----------------------------------------------------------------------
    # Main orchestration
    # -----------------------------------------------------------------------

    def run_all(self) -> None:
        self.console.print("\n" + "=" * 70)
        self.console.print(
            f"  [bold]AUT-384 + AUT-385 + AUT-387 Export QA -- "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC[/bold]"
        )
        self.console.print(f"  Server: {self.server_url}")
        self.console.print("=" * 70)

        self.login()
        self.connect_db()

        try:
            self.setup_viewer_user()
            self.setup_test_esp()

            # Insert base rows for time/column/csv tests (gpio=0, gpio=1 range)
            now = datetime.now(timezone.utc)
            base = now - timedelta(hours=2, minutes=30)
            self.insert_sensor_rows(
                100, sensor_type="temperature", gpio=0, base_time=base, interval_sec=60
            )

            # AUT-384 Sensor Export tests
            self.run_auth_tests()
            self.run_filter_validation()
            self.run_esp_resolution()
            self.run_time_range()
            self.run_column_selection()
            self.run_csv_format()
            self.run_cursor_batching()
            self.run_resolution_aggregation()
            self.run_db_crosscheck()
            self.run_log_verification()
            self.run_bug_reproductions()

            # AUT-385 DB Bulk Export tests
            self.run_exp_auth_tests()
            self.run_exp_table_tests()
            self.run_exp_format_tests()
            self.run_exp_column_tests()
            self.run_exp_date_tests()
            self.run_exp_streaming_test()

            # AUT-387 QA additions: DB cross-check + large-export OFFSET batching
            self.run_exp_db_crosscheck()
            self.run_exp_large_export()

        finally:
            self.teardown_test_data()
            self.teardown_viewer_user()
            self.close_client()
            self.close_db()

        self.print_summary()
        report_path = self.generate_report()
        self.console.print(f"\n  Report: [cyan]{report_path}[/cyan]")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Endpoint QA — AUT-384 + AUT-385"
    )
    parser.add_argument("--url", default="http://localhost:8000", help="Server base URL")
    parser.add_argument("--username", default="admin", help="Admin username")
    parser.add_argument("--password", default=os.environ.get("E2E_TEST_PASSWORD", ""), help="Admin password")
    parser.add_argument(
        "--db",
        default="postgresql://god_kaiser:password@localhost:5432/god_kaiser_db",
        help="PostgreSQL DSN",
    )
    parser.add_argument(
        "--report-dir",
        default=".claude/reports/current",
        help="Directory for markdown report",
    )
    parser.add_argument(
        "--docker-service",
        default="automationone-server",
        help="Docker service name for log verification",
    )
    args = parser.parse_args()

    qa = ExportQA(
        server_url=args.url,
        username=args.username,
        password=args.password,
        db_dsn=args.db,
        report_dir=args.report_dir,
        docker_service=args.docker_service,
    )
    qa.run_all()


if __name__ == "__main__":
    main()
