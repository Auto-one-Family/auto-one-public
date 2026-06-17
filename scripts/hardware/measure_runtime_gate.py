#!/usr/bin/env python3
"""
Measure runtime gate hardening test on real ESP32.

Scenarios (30 runs each):
- normal
- mqtt_disconnect
- registration_pending
- queue_pressure
- timeout

Also performs replay/duplicate checks and writes a JSON report.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
import requests


BROKER_HOST = "localhost"
BROKER_PORT = 1883
API_BASE = "http://localhost:8000/api/v1"
AUTH_USER = "admin"
AUTH_PASS = "admin123"
ESP_ID = "ESP_EA5484"
GPIO = 32
RUNS_PER_SCENARIO = 30
PROBE_RUNS_PER_SCENARIO = 10
WAIT_TERMINAL_SECONDS = 8.0
STATE_GATE_RETRIES = 4
STATE_GATE_RETRY_DELAY_SECONDS = 1.0
STATE_GATE_ACCEPT_TIMEOUT = 3.0
PROGRESS_HEARTBEAT_SECONDS = 2.0

KAISER_ID = "god"
TOPIC_COMMAND = f"kaiser/{KAISER_ID}/esp/{ESP_ID}/sensor/{GPIO}/command"
TOPIC_OUTCOME = f"kaiser/{KAISER_ID}/esp/{ESP_ID}/system/intent_outcome"
TOPIC_OUTCOME_LIFECYCLE = f"kaiser/{KAISER_ID}/esp/{ESP_ID}/system/intent_outcome/lifecycle"
TOPIC_RESPONSE = f"kaiser/{KAISER_ID}/esp/{ESP_ID}/sensor/{GPIO}/response"
TOPIC_SENSOR_DATA = f"kaiser/{KAISER_ID}/esp/{ESP_ID}/sensor/{GPIO}/data"
TOPIC_HEARTBEAT_ACK = f"kaiser/{KAISER_ID}/esp/{ESP_ID}/system/heartbeat/ack"

LOG_KEYWORDS = [
    "error",
    "timeout",
    "publish failed",
    "outbox",
    "queue full",
    "expired",
]

RC_C_NOISE_PATTERNS = [
    "actionresult' object has no attribute 'get'",
    "another operation is in progress",
    "greenlet_spawn",
]

NORMAL_BLOCK_CODES = {
    "DEGRADED_MODE_BLOCKED",
    "REGISTRATION_PENDING",
    "CONFIG_PENDING_BLOCKED",
    "PENDING_APPROVAL_BLOCKED",
}
PENDING_EXPECT_CODES = {
    "PENDING_APPROVAL_BLOCKED",
}
PENDING_STRICT_EXPECT_CODE = "PENDING_APPROVAL_BLOCKED"
NORMAL_EXPECT_DEVICE_STATUS = {"approved", "online", "offline"}
PENDING_EXPECT_DEVICE_STATUS = {"pending_approval"}
CHAIN_COUNTER_KEYS = (
    "ingress_seen",
    "admission_accept",
    "admission_reject",
    "queue_enqueued",
    "execute_started",
    "execute_finished",
    "outcome_publish_attempted",
    "outcome_publish_ok",
    "outcome_publish_failed",
    "observer_seen",
)


@dataclass
class RunResult:
    run_id: str
    scenario: str
    idx: int
    intent_id: str
    correlation_id: str
    accepted_seen: bool
    accepted_effective: bool
    terminal_seen: bool
    terminal_outcome: str
    terminal_code: str
    terminal_reason: str
    root_cause_class: str
    response_success: bool | None
    response_publish_ok: bool | None
    response_measurement_ok: bool | None
    response_timeout: bool | None
    response_quality: str | None
    terminal_match_source: str | None
    chain_breakpoint: str
    confidence: str
    counters_snapshot: dict[str, int]
    accepted_source: str


class GateAbortError(RuntimeError):
    def __init__(self, error_class: str, detail: str) -> None:
        super().__init__(f"{error_class}: {detail}")
        self.error_class = error_class
        self.detail = detail


class MeasureGateRunner:
    def __init__(self) -> None:
        self.client = mqtt.Client(client_id=f"measure-gate-{int(time.time())}", protocol=mqtt.MQTTv311)
        self.client.on_message = self._on_message
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

        self.connected = threading.Event()
        self.lock = threading.Lock()

        self.terminal_by_intent: dict[str, dict[str, Any]] = {}
        self.terminal_by_correlation: dict[str, dict[str, Any]] = {}
        self.accepted_by_intent: dict[str, dict[str, Any]] = {}
        self.responses_by_intent: dict[str, dict[str, Any]] = {}
        self.responses_by_correlation: dict[str, dict[str, Any]] = {}
        self.heartbeat_ack_events: list[dict[str, Any]] = []
        self.quality_counter: Counter[str] = Counter()
        self.sensor_quality_counter: Counter[str] = Counter()
        self.terminal_events: list[dict[str, Any]] = []
        self.observer_mapping_gaps: list[dict[str, str]] = []
        self.chain_snapshot_by_intent: dict[str, dict[str, int]] = {}
        self.lifecycle_events: list[dict[str, Any]] = []

    @staticmethod
    def _default_chain_snapshot() -> dict[str, int]:
        return {key: 0 for key in CHAIN_COUNTER_KEYS}

    def _merge_chain_snapshot(self, intent_id: str, incoming: dict[str, Any]) -> None:
        current = self.chain_snapshot_by_intent.get(intent_id, self._default_chain_snapshot())
        merged = dict(current)
        for key in CHAIN_COUNTER_KEYS:
            try:
                incoming_value = int(incoming.get(key, 0))
            except Exception:
                incoming_value = 0
            merged[key] = max(merged.get(key, 0), incoming_value)
        self.chain_snapshot_by_intent[intent_id] = merged

    def _increment_chain_stage(self, intent_id: str, stage: str) -> None:
        if not intent_id or not stage:
            return
        snapshot = self.chain_snapshot_by_intent.get(intent_id, self._default_chain_snapshot())
        if stage in snapshot:
            snapshot[stage] = int(snapshot.get(stage, 0)) + 1
        self.chain_snapshot_by_intent[intent_id] = snapshot

    def _increment_observer_seen(self, intent_id: str) -> None:
        if not intent_id:
            return
        snapshot = self.chain_snapshot_by_intent.get(intent_id, self._default_chain_snapshot())
        snapshot["observer_seen"] = int(snapshot.get("observer_seen", 0)) + 1
        self.chain_snapshot_by_intent[intent_id] = snapshot

    @staticmethod
    def _is_terminal_outcome(outcome: str) -> bool:
        return outcome not in ("accepted", "processing", "")

    def _on_connect(self, client: mqtt.Client, _userdata: Any, _flags: dict[str, Any], rc: int) -> None:
        if rc == 0:
            client.subscribe(TOPIC_OUTCOME, qos=1)
            client.subscribe(TOPIC_OUTCOME_LIFECYCLE, qos=1)
            client.subscribe(TOPIC_RESPONSE, qos=1)
            client.subscribe(TOPIC_SENSOR_DATA, qos=1)
            client.subscribe(TOPIC_HEARTBEAT_ACK, qos=1)
            self.connected.set()

    def _on_disconnect(self, _client: mqtt.Client, _userdata: Any, _rc: int) -> None:
        self.connected.clear()

    def _on_message(self, _client: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8", errors="ignore"))
        except Exception:
            return
        with self.lock:
            if msg.topic == TOPIC_OUTCOME:
                intent_id = str(payload.get("intent_id") or "")
                correlation_id = str(payload.get("correlation_id") or "")
                outcome = str(payload.get("outcome") or "")
                if intent_id:
                    self._increment_observer_seen(intent_id)
                if intent_id and outcome == "accepted":
                    self.accepted_by_intent[intent_id] = payload
                if intent_id and self._is_terminal_outcome(outcome):
                    self.terminal_by_intent[intent_id] = payload
                if correlation_id and self._is_terminal_outcome(outcome):
                    self.terminal_by_correlation[correlation_id] = payload
                self.terminal_events.append(payload)
            elif msg.topic == TOPIC_OUTCOME_LIFECYCLE:
                event_type = str(payload.get("event_type") or "")
                intent_id = str(payload.get("intent_id") or "")
                if event_type == "intent_chain_stage" and intent_id:
                    stage = str(payload.get("stage") or "")
                    if stage:
                        self._increment_chain_stage(intent_id, stage)
                    raw_snapshot = payload.get("counters_snapshot")
                    if isinstance(raw_snapshot, dict):
                        self._merge_chain_snapshot(intent_id, raw_snapshot)
                    self.lifecycle_events.append(payload)
            elif msg.topic == TOPIC_RESPONSE:
                intent_id = str(payload.get("intent_id") or "")
                correlation_id = str(payload.get("correlation_id") or "")
                if intent_id:
                    self._increment_observer_seen(intent_id)
                if intent_id:
                    self.responses_by_intent[intent_id] = payload
                if correlation_id:
                    self.responses_by_correlation[correlation_id] = payload
                quality = str(payload.get("quality") or "")
                if quality:
                    self.quality_counter[quality] += 1
            elif msg.topic == TOPIC_SENSOR_DATA:
                quality = str(payload.get("quality") or "")
                if quality:
                    self.sensor_quality_counter[quality] += 1
            elif msg.topic == TOPIC_HEARTBEAT_ACK:
                payload["_seen_at_ms"] = int(time.time() * 1000)
                self.heartbeat_ack_events.append(payload)

    def start(self) -> None:
        self.client.connect(BROKER_HOST, BROKER_PORT, keepalive=30)
        self.client.loop_start()
        if not self.connected.wait(timeout=8):
            raise GateAbortError("MQTT_CONNECT_TIMEOUT", "MQTT connect timeout after 8s")

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def publish_measure(
        self,
        intent_id: str,
        correlation_id: str,
        request_id: str,
        timeout_ms: int | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "command": "measure",
            "request_id": request_id,
            "intent_id": intent_id,
            "correlation_id": correlation_id,
            "ttl_ms": 15000,
        }
        if timeout_ms is not None:
            payload["timeout_ms"] = timeout_ms
        # Defensive payload validation: detect malformed payload generation before publish.
        msg = json.dumps(payload, separators=(",", ":"))
        parsed_back = json.loads(msg)
        if parsed_back.get("command") != "measure":
            raise GateAbortError(
                "PAYLOAD_CONTRACT_INVALID",
                f"unexpected command during serialization (intent_id={intent_id})",
            )
        if parsed_back.get("intent_id") != intent_id or parsed_back.get("correlation_id") != correlation_id:
            raise GateAbortError(
                "PAYLOAD_CONTRACT_INVALID",
                f"intent/correlation mismatch before publish (intent_id={intent_id}, correlation_id={correlation_id})",
            )
        info = self.client.publish(TOPIC_COMMAND, msg, qos=1)
        info.wait_for_publish(timeout=2)
        if not info.is_published():
            raise GateAbortError(
                "PUBLISH_TIMEOUT",
                f"publish not confirmed in 2s (intent_id={intent_id}, correlation_id={correlation_id})",
            )

    def wait_outcome(
        self,
        intent_id: str,
        outcome: str,
        timeout_s: float = STATE_GATE_ACCEPT_TIMEOUT,
    ) -> dict[str, Any] | None:
        deadline = time.time() + timeout_s
        next_hb = time.time() + PROGRESS_HEARTBEAT_SECONDS
        while time.time() < deadline:
            with self.lock:
                if outcome == "accepted":
                    existing = self.accepted_by_intent.get(intent_id)
                else:
                    existing = self.terminal_by_intent.get(intent_id)
            if existing:
                return existing
            if time.time() >= next_hb:
                print(
                    f"[heartbeat] waiting outcome={outcome} intent_id={intent_id} "
                    f"remaining={max(0.0, deadline - time.time()):.2f}s",
                    flush=True,
                )
                next_hb = time.time() + PROGRESS_HEARTBEAT_SECONDS
            time.sleep(0.05)
        return None

    def wait_terminal(
        self,
        intent_id: str,
        correlation_id: str,
        timeout_s: float = WAIT_TERMINAL_SECONDS,
        require_accepted: bool = False,
    ) -> tuple[dict[str, Any] | None, str | None]:
        if require_accepted and self.wait_outcome(intent_id, "accepted", timeout_s=STATE_GATE_ACCEPT_TIMEOUT) is None:
            return None, None
        deadline = time.time() + timeout_s
        next_hb = time.time() + PROGRESS_HEARTBEAT_SECONDS
        while time.time() < deadline:
            with self.lock:
                existing = self.terminal_by_intent.get(intent_id)
                if existing is None and correlation_id:
                    existing_corr = self.terminal_by_correlation.get(correlation_id)
                    if existing_corr is not None:
                        corr_intent = str(existing_corr.get("intent_id") or "")
                        # Mapping hardening: never bind a correlation-terminal from a different intent.
                        if not corr_intent or corr_intent == intent_id:
                            return existing_corr, "correlation"
                        self.observer_mapping_gaps.append(
                            {
                                "intent_id": intent_id,
                                "correlation_id": correlation_id,
                                "seen_intent_id": corr_intent,
                            }
                        )
            if existing:
                return existing, "intent"
            if time.time() >= next_hb:
                print(
                    f"[heartbeat] waiting terminal intent_id={intent_id} "
                    f"corr_id={correlation_id} remaining={max(0.0, deadline - time.time()):.2f}s",
                    flush=True,
                )
                next_hb = time.time() + PROGRESS_HEARTBEAT_SECONDS
            time.sleep(0.05)
        return None, None

    def get_response(self, intent_id: str, correlation_id: str) -> dict[str, Any] | None:
        with self.lock:
            if intent_id in self.responses_by_intent:
                return self.responses_by_intent.get(intent_id)
            if correlation_id in self.responses_by_correlation:
                return self.responses_by_correlation.get(correlation_id)
            return None

    def was_accepted(self, intent_id: str) -> bool:
        with self.lock:
            return intent_id in self.accepted_by_intent

    def wait_heartbeat_ack_status(
        self, expected_status: set[str], since_ms: int, timeout_s: float = 8.0
    ) -> dict[str, Any] | None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            with self.lock:
                for event in reversed(self.heartbeat_ack_events):
                    seen_at = int(event.get("_seen_at_ms") or 0)
                    if seen_at < since_ms:
                        break
                    status = str(event.get("status") or "").lower()
                    if status in expected_status:
                        return event
            time.sleep(0.05)
        return None

    def clear_observation_windows(self) -> None:
        with self.lock:
            self.terminal_by_intent.clear()
            self.terminal_by_correlation.clear()
            self.accepted_by_intent.clear()
            self.responses_by_intent.clear()
            self.responses_by_correlation.clear()
            self.terminal_events.clear()
            self.observer_mapping_gaps.clear()
            self.chain_snapshot_by_intent.clear()
            self.lifecycle_events.clear()

    def has_observer_mapping_gap(self, intent_id: str, correlation_id: str) -> bool:
        with self.lock:
            for item in self.observer_mapping_gaps:
                if item.get("intent_id") == intent_id and item.get("correlation_id") == correlation_id:
                    return True
            return False

    def get_chain_snapshot(self, intent_id: str) -> dict[str, int]:
        with self.lock:
            return dict(self.chain_snapshot_by_intent.get(intent_id, self._default_chain_snapshot()))


def iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_logs_10m_window(start_iso: str, end_iso: str, keywords: list[str] | None = None) -> dict[str, Any]:
    start = datetime.fromisoformat(start_iso) - timedelta(minutes=10)
    end = datetime.fromisoformat(end_iso)
    cmd = [
        "docker",
        "logs",
        "automationone-server",
        "--since",
        start.isoformat(),
        "--until",
        end.isoformat(),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=False, check=False)
    stdout_txt = (proc.stdout or b"").decode("utf-8", errors="ignore")
    stderr_txt = (proc.stderr or b"").decode("utf-8", errors="ignore")
    lines = stdout_txt + "\n" + stderr_txt
    matches = []
    search_terms = keywords or LOG_KEYWORDS
    for line in lines.splitlines():
        low = line.lower()
        if any(k in low for k in search_terms):
            matches.append(line.strip())
    return {
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "matched_count": len(matches),
        "matched_lines": matches[:50],
    }


def api_token() -> str:
    resp = requests.post(
        f"{API_BASE}/auth/login",
        json={"username": AUTH_USER, "password": AUTH_PASS},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["tokens"]["access_token"]


def reject_device(token: str, reason: str) -> None:
    r = requests.post(
        f"{API_BASE}/esp/devices/{ESP_ID}/reject",
        headers={"Authorization": f"Bearer {token}"},
        json={"reason": reason},
        timeout=10,
    )
    if r.status_code not in (200, 400):
        r.raise_for_status()


def approve_device(token: str) -> None:
    r = requests.post(
        f"{API_BASE}/esp/devices/{ESP_ID}/approve",
        headers={"Authorization": f"Bearer {token}"},
        json={},
        timeout=10,
    )
    if r.status_code not in (200, 400):
        r.raise_for_status()


def set_device_pending(token: str) -> None:
    r = requests.post(
        f"{API_BASE}/esp/devices/{ESP_ID}/set-pending",
        headers={"Authorization": f"Bearer {token}"},
        json={},
        timeout=10,
    )
    if r.status_code not in (200, 400):
        r.raise_for_status()


def get_device_state(token: str) -> dict[str, Any]:
    r = requests.get(
        f"{API_BASE}/esp/devices/{ESP_ID}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    r.raise_for_status()
    body = r.json()
    data = body.get("data", body)
    if isinstance(data, dict) and isinstance(data.get("device"), dict):
        data = data.get("device")
    if isinstance(data, dict):
        return data
    return {}


def wait_for_device_status(token: str, expected_statuses: set[str], timeout_s: float = 8.0) -> str:
    deadline = time.time() + timeout_s
    observed = ""
    while time.time() < deadline:
        state = get_device_state(token)
        observed = str(state.get("status") or "").lower()
        if observed in expected_statuses:
            return observed
        time.sleep(0.2)
    return observed


def collect_rc_c_noise(end_iso: str | None = None) -> dict[str, Any]:
    end = end_iso or iso_utc_now()
    return fetch_logs_10m_window(end, end, keywords=RC_C_NOISE_PATTERNS)


def classify_drift_subcode(event: dict[str, Any], expect_pending: bool) -> str:
    terminal_code = str(event.get("terminal_code") or "")
    device_status = str(event.get("device_status") or "")
    accepted_seen = bool(event.get("accepted_seen"))
    terminal_seen = bool(event.get("terminal_seen"))

    if not terminal_seen:
        return "DRIFT_NO_TERMINAL"
    if terminal_code == "DEGRADED_MODE_BLOCKED":
        return "DRIFT_DEGRADED_FLAG"
    if expect_pending and device_status not in PENDING_EXPECT_DEVICE_STATUS:
        return "DRIFT_PENDING_NOT_REACHED"
    if not expect_pending and device_status not in NORMAL_EXPECT_DEVICE_STATUS:
        return "DRIFT_NORMAL_STATUS_MISMATCH"
    if not expect_pending and terminal_code in NORMAL_BLOCK_CODES:
        return "DRIFT_NORMAL_BLOCKED"
    if expect_pending and terminal_code not in PENDING_EXPECT_CODES:
        return "DRIFT_PENDING_CODE_MISMATCH"
    if not expect_pending and not accepted_seen:
        return "DRIFT_ACCEPT_NOT_SEEN"
    return "DRIFT_UNKNOWN"


def state_gate_handshake(runner: MeasureGateRunner, token: str, scenario: str) -> dict[str, Any]:
    expect_pending = scenario == "registration_pending"
    gate_events: list[dict[str, Any]] = []
    drift_counter: Counter[str] = Counter()

    for attempt in range(1, STATE_GATE_RETRIES + 1):
        correction_action = "none"
        set_pending_ts_ms = int(time.time() * 1000)
        heartbeat_ack_seen = False
        if expect_pending:
            correction_action = "set_pending"
            set_device_pending(token)
            waited_status = wait_for_device_status(token, PENDING_EXPECT_DEVICE_STATUS, timeout_s=8.0)
            ack = runner.wait_heartbeat_ack_status({"pending_approval"}, since_ms=set_pending_ts_ms, timeout_s=8.0)
            heartbeat_ack_seen = ack is not None
        else:
            correction_action = "approve"
            approve_device(token)
            waited_status = wait_for_device_status(token, NORMAL_EXPECT_DEVICE_STATUS, timeout_s=8.0)
            ack = runner.wait_heartbeat_ack_status({"approved", "online"}, since_ms=set_pending_ts_ms, timeout_s=8.0)
            heartbeat_ack_seen = ack is not None

        intent_id = f"{scenario}-state-gate-{attempt}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
        corr_id = f"{scenario}-state-gate-corr-{attempt}-{uuid.uuid4().hex[:10]}"
        req_id = f"{scenario}-state-gate-req-{attempt}"

        runner.publish_measure(intent_id, corr_id, req_id, timeout_ms=2500)
        accepted = runner.wait_outcome(intent_id, "accepted", timeout_s=STATE_GATE_ACCEPT_TIMEOUT)
        terminal, source = runner.wait_terminal(
            intent_id,
            corr_id,
            timeout_s=WAIT_TERMINAL_SECONDS,
            require_accepted=False,
        )
        device_state = get_device_state(token)
        device_status = str(device_state.get("status") or "").lower()
        terminal_code = str((terminal or {}).get("code") or "")
        terminal_outcome = str((terminal or {}).get("outcome") or "")

        event = {
            "attempt": attempt,
            "correction_action": correction_action,
            "waited_status": waited_status,
            "device_status": device_status,
            "accepted_seen": accepted is not None,
            "terminal_seen": terminal is not None,
            "terminal_outcome": terminal_outcome,
            "terminal_code": terminal_code,
            "terminal_source": source,
            "heartbeat_ack_seen": heartbeat_ack_seen,
        }

        if expect_pending:
            ok = (
                heartbeat_ack_seen
                and terminal is not None
                and terminal_code == PENDING_STRICT_EXPECT_CODE
                and terminal_outcome == "rejected"
                and (accepted is None)
                and (
                device_status in PENDING_EXPECT_DEVICE_STATUS
                )
            )
        else:
            blocked = terminal_code in NORMAL_BLOCK_CODES
            ok = accepted is not None and terminal is not None and not blocked and (
                device_status in NORMAL_EXPECT_DEVICE_STATUS
            )

        event["ok"] = ok
        if not ok:
            event["drift_subcode"] = classify_drift_subcode(event, expect_pending=expect_pending)
            drift_counter[event["drift_subcode"]] += 1
        gate_events.append(event)

        if ok:
            return {
                "ok": True,
                "expected_mode": "pending" if expect_pending else "normal",
                "events": gate_events,
                "drift_counter": dict(drift_counter),
            }

        time.sleep(STATE_GATE_RETRY_DELAY_SECONDS)

    top_subcode = drift_counter.most_common(1)[0][0] if drift_counter else "DRIFT_UNKNOWN"
    return {
        "ok": False,
        "expected_mode": "pending" if expect_pending else "normal",
        "events": gate_events,
        "error_code": "STATE_DRIFT_DETECTED",
        "drift_subcode": top_subcode,
        "drift_counter": dict(drift_counter),
    }


def broker_glitch(delay_s: float = 0.07, pause_s: float = 1.2) -> None:
    def _worker() -> None:
        time.sleep(delay_s)
        subprocess.run(["docker", "pause", "automationone-mqtt"], check=False, capture_output=True, text=True)
        time.sleep(pause_s)
        subprocess.run(["docker", "unpause", "automationone-mqtt"], check=False, capture_output=True, text=True)

    threading.Thread(target=_worker, daemon=True).start()


def enforce_scenario_reset(runner: MeasureGateRunner, token: str, scenario: str) -> dict[str, Any]:
    reset_started_ms = int(time.time() * 1000)
    approve_device(token)
    api_status = wait_for_device_status(token, NORMAL_EXPECT_DEVICE_STATUS, timeout_s=8.0)
    heartbeat_ack = runner.wait_heartbeat_ack_status({"approved", "online"}, since_ms=reset_started_ms, timeout_s=8.0)
    runtime_status = str((heartbeat_ack or {}).get("status") or "").lower()
    reset_ok = bool(api_status in NORMAL_EXPECT_DEVICE_STATUS and heartbeat_ack is not None)
    return {
        "scenario": scenario,
        "reset_ok": reset_ok,
        "api_status": api_status,
        "runtime_status": runtime_status,
        "heartbeat_ack_seen": heartbeat_ack is not None,
    }


def classify_run(
    scenario: str,
    idx: int,
    intent_id: str,
    correlation_id: str,
    terminal: dict[str, Any] | None,
    terminal_source: str | None,
    response: dict[str, Any] | None,
    accepted_seen: bool,
    observer_mapping_gap: bool,
    counters_snapshot: dict[str, int],
) -> RunResult:
    run_id = f"{scenario}:{idx}:{intent_id}"
    terminal_outcome_value = str((terminal or {}).get("outcome") or "")
    accepted_effective = accepted_seen or terminal_outcome_value in ("applied", "failed", "expired")
    chain_breakpoint = "execute_not_reached"
    confidence = "medium"
    accepted_source = "none"
    if accepted_seen:
        accepted_source = "observer.accepted_outcome"
    elif accepted_effective:
        accepted_source = "observer.terminal_inference"

    ingress_seen = int(counters_snapshot.get("ingress_seen", 0))
    admission_accept = int(counters_snapshot.get("admission_accept", 0))
    admission_reject = int(counters_snapshot.get("admission_reject", 0))
    queue_enqueued = int(counters_snapshot.get("queue_enqueued", 0))
    execute_finished = int(counters_snapshot.get("execute_finished", 0))
    outcome_publish_attempted = int(counters_snapshot.get("outcome_publish_attempted", 0))
    outcome_publish_ok = int(counters_snapshot.get("outcome_publish_ok", 0))
    outcome_publish_failed = int(counters_snapshot.get("outcome_publish_failed", 0))
    if accepted_seen and terminal is None:
        root_cause_class = "timeout_ohne_terminal_publish"
        if outcome_publish_failed > 0 or (
            outcome_publish_attempted > 0 and outcome_publish_ok == 0 and outcome_publish_failed == 0
        ):
            chain_breakpoint = "outcome_publish_missing"
            confidence = "high"
        elif outcome_publish_ok > 0:
            chain_breakpoint = "observer_mapping_gap"
            confidence = "high"
        else:
            chain_breakpoint = "counter_evidence_missing"
            confidence = "medium"
    elif terminal is None:
        root_cause_class = "lost_publish_or_unaccepted"
        if observer_mapping_gap:
            chain_breakpoint = "observer_mapping_gap"
            confidence = "high"
        elif outcome_publish_ok > 0:
            chain_breakpoint = "observer_mapping_gap"
            confidence = "high"
        elif outcome_publish_failed > 0:
            chain_breakpoint = "outcome_publish_missing"
            confidence = "high"
        elif execute_finished > 0 and outcome_publish_attempted == 0:
            chain_breakpoint = "outcome_publish_missing"
            confidence = "high"
        elif admission_reject > 0:
            chain_breakpoint = "admission_blocked"
            confidence = "high"
        elif admission_accept > 0 and queue_enqueued == 0:
            chain_breakpoint = "queue_drop_or_not_enqueued"
            confidence = "high"
        elif ingress_seen == 0:
            chain_breakpoint = "ingress_not_seen"
            confidence = "high"
        elif response is not None:
            chain_breakpoint = "observer_mapping_gap"
            confidence = "medium"
        else:
            chain_breakpoint = "counter_evidence_missing"
            confidence = "medium"
    else:
        code = str(terminal.get("code") or "")
        if code == "INVALID_JSON":
            root_cause_class = "parse_contract_reject"
            chain_breakpoint = "ingress_rejected"
            confidence = "high"
        elif code in ("QUEUE_FULL", "PUBLISH_OUTBOX_FULL"):
            root_cause_class = "queue_or_publish_backpressure"
            chain_breakpoint = "queue_drop_or_not_enqueued"
            confidence = "high"
        elif code in (
            "REGISTRATION_PENDING",
            "PENDING_APPROVAL_BLOCKED",
            "CONFIG_PENDING_BLOCKED",
            "DEGRADED_MODE_BLOCKED",
            "SAFETY_LOCKED",
        ):
            root_cause_class = "admission_blocked"
            chain_breakpoint = "admission_blocked"
            confidence = "high"
        elif code in ("TTL_EXPIRED", "MEASURE_TIMEOUT"):
            root_cause_class = "timeout_terminal"
            chain_breakpoint = "execute_not_reached"
            confidence = "high"
        elif code == "PENDING_APPROVAL_BLOCKED":
            root_cause_class = "pending_gate_blocked_expected"
            chain_breakpoint = "admission_blocked"
            confidence = "high"
        else:
            root_cause_class = "executed_terminal"
            chain_breakpoint = "execute_not_reached"
            confidence = "high"
    if terminal is None:
        return RunResult(
            run_id=run_id,
            scenario=scenario,
            idx=idx,
            intent_id=intent_id,
            correlation_id=correlation_id,
            accepted_seen=accepted_seen,
            accepted_effective=accepted_effective,
            terminal_seen=False,
            terminal_outcome="missing",
            terminal_code=(
                "MISSING_TERMINAL"
                if chain_breakpoint in {"outcome_publish_missing", "observer_mapping_gap"}
                else "MISSING_TERMINAL_UNPROVEN"
            ),
            terminal_reason="No terminal outcome received in timeout window",
            root_cause_class=root_cause_class,
            response_success=None,
            response_publish_ok=None,
            response_measurement_ok=None,
            response_timeout=None,
            response_quality=None,
            terminal_match_source=None,
            chain_breakpoint=chain_breakpoint,
            confidence=confidence,
            counters_snapshot=counters_snapshot,
            accepted_source=accepted_source,
        )
    return RunResult(
        run_id=run_id,
        scenario=scenario,
        idx=idx,
        intent_id=intent_id,
        correlation_id=correlation_id,
        accepted_seen=accepted_seen,
        accepted_effective=accepted_effective,
        terminal_seen=True,
        terminal_outcome=str(terminal.get("outcome") or "missing"),
        terminal_code=str(terminal.get("code") or "UNKNOWN"),
        terminal_reason=str(terminal.get("reason") or ""),
        root_cause_class=root_cause_class,
        response_success=(bool(response.get("success")) if response is not None else None),
        response_publish_ok=(bool(response.get("publish_ok")) if response is not None and "publish_ok" in response else None),
        response_measurement_ok=(bool(response.get("measurement_ok")) if response is not None and "measurement_ok" in response else None),
        response_timeout=(bool(response.get("timeout")) if response is not None and "timeout" in response else None),
        response_quality=(str(response.get("quality")) if response is not None and "quality" in response else None),
        terminal_match_source=terminal_source,
        chain_breakpoint=chain_breakpoint,
        confidence=confidence,
        counters_snapshot=counters_snapshot,
        accepted_source=accepted_source,
    )


def run_scenario(
    runner: MeasureGateRunner,
    token: str,
    name: str,
    runs: int,
    timeout_ms: int | None = None,
    disconnect_glitch: bool = False,
    burst_mode: bool = False,
) -> tuple[list[RunResult], dict[str, Any]]:
    started_at = iso_utc_now()
    runner.clear_observation_windows()
    scenario_reset = enforce_scenario_reset(runner, token, name)
    print(f"[scenario] start name={name} runs={runs}", flush=True)
    results: list[RunResult] = []
    if not scenario_reset.get("reset_ok", False):
        ended_at = iso_utc_now()
        logs = fetch_logs_10m_window(started_at, ended_at)
        logs["scenario_reset"] = scenario_reset
        logs["state_gate"] = {"ok": False, "error_code": "STATE_RESET_FAILED"}
        logs["state_drift"] = True
        logs["state_drift_code"] = "STATE_RESET_FAILED"
        logs["state_drift_subcode"] = "DRIFT_RESET_NOT_SYNCED"
        return results, logs
    state_gate = state_gate_handshake(runner, token, name)
    if not state_gate.get("ok", False):
        ended_at = iso_utc_now()
        logs = fetch_logs_10m_window(started_at, ended_at)
        logs["scenario_reset"] = scenario_reset
        logs["state_gate"] = state_gate
        logs["state_drift"] = True
        logs["state_drift_code"] = state_gate.get("error_code", "STATE_DRIFT_DETECTED")
        logs["state_drift_subcode"] = state_gate.get("drift_subcode", "DRIFT_UNKNOWN")
        print(f"[scenario] abort-state-drift name={name} code={logs['state_drift_code']}", flush=True)
        return results, logs

    per_run_budget_s = (WAIT_TERMINAL_SECONDS + 8.0 + 2.0) if burst_mode else (
        WAIT_TERMINAL_SECONDS + STATE_GATE_ACCEPT_TIMEOUT + 2.0
    )
    scenario_deadline = time.time() + (max(1, runs) * per_run_budget_s) + 10.0

    if burst_mode:
        intents = []
        for i in range(1, runs + 1):
            intent_id = f"{name}-intent-{i}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
            corr_id = f"{name}-corr-{i}-{uuid.uuid4().hex[:8]}"
            req_id = f"{name}-req-{i}"
            intents.append((i, intent_id, corr_id))
            print(f"[run] scenario={name} idx={i}/{runs} phase=publish", flush=True)
            runner.publish_measure(intent_id, corr_id, req_id, timeout_ms=timeout_ms)
        pending = {intent_id: (idx, corr_id) for idx, intent_id, corr_id in intents}
        timeout_base_ms = timeout_ms if timeout_ms is not None else 5000
        # Queue-pressure execution is serialized on device side.
        # Previous budget was too optimistic and caused false MISSING_TERMINAL
        # when outcomes arrived after the observer window.
        per_intent_budget_s = max((timeout_base_ms / 1000.0) + 0.75, 1.5)
        burst_terminal_budget_s = max(
            WAIT_TERMINAL_SECONDS + 20.0,
            (runs * per_intent_budget_s) + 20.0,
        )
        burst_deadline = time.time() + burst_terminal_budget_s
        next_hb = time.time() + PROGRESS_HEARTBEAT_SECONDS
        while pending and time.time() < burst_deadline:
            resolved: list[str] = []
            for intent_id, (idx, corr_id) in pending.items():
                terminal, source = runner.wait_terminal(intent_id, corr_id, timeout_s=0.05)
                if terminal is None:
                    continue
                response = runner.get_response(intent_id, corr_id)
                accepted_seen = runner.was_accepted(intent_id)
                observer_mapping_gap = runner.has_observer_mapping_gap(intent_id, corr_id)
                counters_snapshot = runner.get_chain_snapshot(intent_id)
                result = classify_run(
                    name,
                    idx,
                    intent_id,
                    corr_id,
                    terminal,
                    source,
                    response,
                    accepted_seen,
                    observer_mapping_gap,
                    counters_snapshot,
                )
                results.append(result)
                print(
                    f"[run] scenario={name} idx={idx}/{runs} outcome={result.terminal_outcome} code={result.terminal_code}",
                    flush=True,
                )
                resolved.append(intent_id)
            for rid in resolved:
                pending.pop(rid, None)
            if time.time() >= next_hb:
                print(
                    f"[heartbeat] burst pending_terminals={len(pending)} remaining={max(0.0, burst_deadline - time.time()):.2f}s",
                    flush=True,
                )
                next_hb = time.time() + PROGRESS_HEARTBEAT_SECONDS
            time.sleep(0.05)
        # Extra replay grace window: allow delayed critical-outcome recovery
        # from NVS outbox before classifying as missing terminal.
        replay_grace_deadline = time.time() + 20.0
        while pending and time.time() < replay_grace_deadline:
            resolved: list[str] = []
            for intent_id, (idx, corr_id) in pending.items():
                terminal, source = runner.wait_terminal(intent_id, corr_id, timeout_s=0.05)
                if terminal is None:
                    continue
                response = runner.get_response(intent_id, corr_id)
                accepted_seen = runner.was_accepted(intent_id)
                observer_mapping_gap = runner.has_observer_mapping_gap(intent_id, corr_id)
                counters_snapshot = runner.get_chain_snapshot(intent_id)
                result = classify_run(
                    name,
                    idx,
                    intent_id,
                    corr_id,
                    terminal,
                    source,
                    response,
                    accepted_seen,
                    observer_mapping_gap,
                    counters_snapshot,
                )
                results.append(result)
                print(
                    f"[run] scenario={name} idx={idx}/{runs} outcome={result.terminal_outcome} code={result.terminal_code}",
                    flush=True,
                )
                resolved.append(intent_id)
            for rid in resolved:
                pending.pop(rid, None)
            time.sleep(0.05)
        for intent_id, (idx, corr_id) in pending.items():
            response = runner.get_response(intent_id, corr_id)
            accepted_seen = runner.was_accepted(intent_id)
            observer_mapping_gap = runner.has_observer_mapping_gap(intent_id, corr_id)
            counters_snapshot = runner.get_chain_snapshot(intent_id)
            result = classify_run(
                name,
                idx,
                intent_id,
                corr_id,
                None,
                None,
                response,
                accepted_seen,
                observer_mapping_gap,
                counters_snapshot,
            )
            results.append(result)
            print(
                f"[run] scenario={name} idx={idx}/{runs} outcome={result.terminal_outcome} code={result.terminal_code}",
                flush=True,
            )
    else:
        for i in range(1, runs + 1):
            if time.time() > scenario_deadline:
                raise GateAbortError(
                    "SCENARIO_TIMEOUT",
                    f"scenario={name} exceeded hard timeout at run {i}/{runs}",
                )
            intent_id = f"{name}-intent-{i}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
            corr_id = f"{name}-corr-{i}-{uuid.uuid4().hex[:8]}"
            req_id = f"{name}-req-{i}"
            print(f"[run] scenario={name} idx={i}/{runs} phase=publish", flush=True)
            runner.publish_measure(intent_id, corr_id, req_id, timeout_ms=timeout_ms)
            if disconnect_glitch:
                broker_glitch()
            require_accepted = name != "registration_pending"
            terminal, source = runner.wait_terminal(
                intent_id,
                corr_id,
                require_accepted=require_accepted,
            )
            response = runner.get_response(intent_id, corr_id)
            accepted_seen = runner.was_accepted(intent_id)
            observer_mapping_gap = runner.has_observer_mapping_gap(intent_id, corr_id)
            counters_snapshot = runner.get_chain_snapshot(intent_id)
            result = classify_run(
                name,
                i,
                intent_id,
                corr_id,
                terminal,
                source,
                response,
                accepted_seen,
                observer_mapping_gap,
                counters_snapshot,
            )
            results.append(result)
            print(
                f"[run] scenario={name} idx={i}/{runs} outcome={result.terminal_outcome} code={result.terminal_code}",
                flush=True,
            )
            time.sleep(0.08)

    ended_at = iso_utc_now()
    logs = fetch_logs_10m_window(started_at, ended_at)
    logs["scenario_reset"] = scenario_reset
    logs["state_gate"] = state_gate
    logs["state_drift"] = False
    print(f"[scenario] done name={name} collected_runs={len(results)}", flush=True)
    return results, logs


def run_replay_checks(runner: MeasureGateRunner) -> dict[str, Any]:
    # Sequential duplicate intent
    seq_intent = f"replay-seq-{int(time.time() * 1000)}"
    corr = f"replay-seq-corr-{int(time.time())}"
    runner.publish_measure(seq_intent, corr, "replay-seq-1")
    runner.publish_measure(seq_intent, corr, "replay-seq-2")
    term, term_source = runner.wait_terminal(seq_intent, corr)
    resp = runner.get_response(seq_intent, corr)

    # Parallel duplicate intent
    par_intent = f"replay-par-{int(time.time() * 1000)}"
    par_corr = f"replay-par-corr-{int(time.time())}"
    t1 = threading.Thread(target=runner.publish_measure, args=(par_intent, par_corr, "replay-par-1"))
    t2 = threading.Thread(target=runner.publish_measure, args=(par_intent, par_corr, "replay-par-2"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    par_term, par_term_source = runner.wait_terminal(par_intent, par_corr)
    par_resp = runner.get_response(par_intent, par_corr)

    return {
        "sequential_same_intent": {
            "intent_id": seq_intent,
            "terminal": term,
            "terminal_source": term_source,
            "response": resp,
        },
        "parallel_same_intent": {
            "intent_id": par_intent,
            "terminal": par_term,
            "terminal_source": par_term_source,
            "response": par_resp,
        },
    }


def summarize(results: list[RunResult]) -> dict[str, Any]:
    outcome_counter: Counter[str] = Counter()
    code_counter: Counter[str] = Counter()
    false_applied = 0
    unclassified = 0
    for item in results:
        outcome_counter[item.terminal_outcome] += 1
        code_counter[item.terminal_code] += 1
        if item.terminal_outcome == "applied" and (
            item.response_publish_ok is False or item.response_measurement_ok is False
        ):
            false_applied += 1
        if item.terminal_outcome in ("missing", "") or item.terminal_code in ("", "UNKNOWN"):
            unclassified += 1
    return {
        "runs": len(results),
        "outcomes": dict(outcome_counter),
        "codes": dict(code_counter),
        "missing_terminal": code_counter.get("MISSING_TERMINAL", 0),
        "false_applied_count": false_applied,
        "unclassified_count": unclassified,
        "chain_breakpoints": dict(Counter(item.chain_breakpoint for item in results)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure runtime gate on real hardware")
    parser.add_argument("--runs", type=int, default=RUNS_PER_SCENARIO, help="Runs per scenario")
    parser.add_argument(
        "--probe-runs",
        type=int,
        default=PROBE_RUNS_PER_SCENARIO,
        help="Probe runs per scenario before full run",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runs = max(1, int(args.runs))
    probe_runs = max(1, int(args.probe_runs))
    token = api_token()
    runner = MeasureGateRunner()
    runner.start()

    probe_results: dict[str, list[RunResult]] = {}
    probe_log_windows: dict[str, dict[str, Any]] = {}
    all_results: dict[str, list[RunResult]] = {}
    log_windows: dict[str, dict[str, Any]] = {}
    replay: dict[str, Any] = {}
    abort_info: dict[str, Any] | None = None
    drift_counters: Counter[str] = Counter()
    preflight_before = collect_rc_c_noise()
    if preflight_before.get("matched_count", 0) > 0:
        raise RuntimeError(
            f"Server preflight failed: RC-C noise present ({preflight_before.get('matched_count')} matches)"
        )

    scenario_specs = [
        {"name": "normal", "kwargs": {}},
        {"name": "mqtt_disconnect", "kwargs": {"disconnect_glitch": True}},
        {"name": "queue_pressure", "kwargs": {"burst_mode": True, "timeout_ms": 250}},
        {"name": "timeout", "kwargs": {"timeout_ms": 1}},
        {"name": "registration_pending", "kwargs": {}},
    ]

    try:
        # Phase A: mandatory probe run before full gate run
        for spec in scenario_specs:
            name = spec["name"]
            res, logs = run_scenario(runner, token, name, probe_runs, **spec["kwargs"])
            probe_results[name] = res
            probe_log_windows[name] = logs
            state_gate = logs.get("state_gate", {})
            for subcode, count in (state_gate.get("drift_counter") or {}).items():
                drift_counters[subcode] += int(count)
            if logs.get("state_drift"):
                drift_counters[state_gate.get("drift_subcode", "DRIFT_UNKNOWN")] += 1

        # Phase B: full 30-run gate execution
        for spec in scenario_specs:
            name = spec["name"]
            res, logs = run_scenario(runner, token, name, runs, **spec["kwargs"])
            all_results[name] = res
            log_windows[name] = logs
            state_gate = logs.get("state_gate", {})
            for subcode, count in (state_gate.get("drift_counter") or {}).items():
                drift_counters[subcode] += int(count)
            if logs.get("state_drift"):
                drift_counters[state_gate.get("drift_subcode", "DRIFT_UNKNOWN")] += 1

        replay = run_replay_checks(runner)
    except GateAbortError as exc:
        print(f"[fail-fast] class={exc.error_class} detail={exc.detail}", flush=True)
        abort_info = {"error_class": exc.error_class, "detail": exc.detail}
    finally:
        try:
            approve_device(token)
        except Exception:
            pass
        runner.stop()

    probe_summary = {name: summarize(items) for name, items in probe_results.items()}
    summary = {name: summarize(items) for name, items in all_results.items()}
    missing_terminal_by_scenario = {
        name: data.get("missing_terminal", 0) for name, data in summary.items()
    }
    timeout_runs = summary.get("timeout", {}).get("runs", 0)
    timeout_codes = summary.get("timeout", {}).get("codes", {})
    timeout_success = int(timeout_codes.get("MEASURE_TIMEOUT", 0))
    timeout_success_rate = (timeout_success / timeout_runs) if timeout_runs else 0.0
    quality_summary = {
        "response_quality_counts": dict(runner.quality_counter),
        "sensor_data_quality_counts": dict(runner.sensor_quality_counter),
    }

    out = {
        "generated_at": iso_utc_now(),
        "esp_id": ESP_ID,
        "gpio": GPIO,
        "probe_runs_per_scenario": probe_runs,
        "runs_per_scenario": runs,
        "probe_summary": probe_summary,
        "summary": summary,
        "drift_counters": dict(drift_counters),
        "missing_terminal_by_scenario": missing_terminal_by_scenario,
        "timeout_success_rate": timeout_success_rate,
        "replay_checks": replay,
        "quality_summary": quality_summary,
        "server_preflight": {
            "before": preflight_before,
            "after": collect_rc_c_noise(),
        },
        "probe_log_windows": probe_log_windows,
        "log_windows": log_windows,
        "abort_info": abort_info,
        "details": {
            name: [item.__dict__ for item in items] for name, items in all_results.items()
        },
        "run_table": [
            {
                "run_id": item.run_id,
                "scenario": item.scenario,
                "accepted": item.accepted_effective,
                "accepted_observed": item.accepted_seen,
                "accepted_source": item.accepted_source,
                "terminal_seen": item.terminal_seen,
                "terminal_code": item.terminal_code,
                "counters_snapshot": item.counters_snapshot,
                "root_cause_class": item.root_cause_class,
                "chain_breakpoint": item.chain_breakpoint,
                "confidence": item.confidence,
            }
            for items in all_results.values()
            for item in items
        ],
    }
    queue_pressure_chain_table = [
        {
            "run_id": item.run_id,
            "accepted": item.accepted_effective,
            "accepted_observed": item.accepted_seen,
            "accepted_source": item.accepted_source,
            "terminal_seen": item.terminal_seen,
            "terminal_code": item.terminal_code,
            "counters_snapshot": item.counters_snapshot,
            "chain_breakpoint": item.chain_breakpoint,
            "confidence": item.confidence,
        }
        for item in all_results.get("queue_pressure", [])
    ]
    out["queue_pressure_chain_table"] = queue_pressure_chain_table

    reports_dir = Path("logs/current/hardware/measure-gate")
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = reports_dir / f"measure_runtime_gate_{ts}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))
    if abort_info is not None:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
