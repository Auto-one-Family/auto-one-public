#!/usr/bin/env bash
set -euo pipefail

# Orchestriert den vollständigen Disconnect-Testpfad:
# Phase 0 -> Stage 1 -> Stage 2A -> Stage 2B -> Stage 2C
# inklusive Gate-Entscheidungen und maschinenlesbarer Gesamtausgabe.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPRO_SCRIPT="${ROOT_DIR}/scripts/hardware/repro_disconnect_esp32.sh"
RUN_ROOT="${ROOT_DIR}/logs/current/hardware/disconnect-repro"
mkdir -p "${RUN_ROOT}"

PHASE0_CAPTURE_SECONDS="${PHASE0_CAPTURE_SECONDS:-90}"
STAGE_CAPTURE_SECONDS="${STAGE_CAPTURE_SECONDS:-120}"
STAGE2C_CAPTURE_SECONDS="${STAGE2C_CAPTURE_SECONDS:-180}"
STAGE2A_IDLE_SECONDS="${STAGE2A_IDLE_SECONDS:-60}"
STAGE1_FLOOD_FAST="${STAGE1_FLOOD_FAST:-30}"
STAGE1_FLOOD_SLOW="${STAGE1_FLOOD_SLOW:-20}"
STAGE1_FLOOD_DELAY_MS="${STAGE1_FLOOD_DELAY_MS:-35}"
STAGE1_IDLE_SECONDS="${STAGE1_IDLE_SECONDS:-30}"
OUTPUT_JSON="${OUTPUT_JSON:-${RUN_ROOT}/stage_chain_result_latest.json}"
OUTPUT_MD="${OUTPUT_MD:-${RUN_ROOT}/stage_chain_result_latest.md}"

python3 - "$ROOT_DIR" "$REPRO_SCRIPT" "$RUN_ROOT" "$PHASE0_CAPTURE_SECONDS" "$STAGE_CAPTURE_SECONDS" "$STAGE2C_CAPTURE_SECONDS" "$STAGE2A_IDLE_SECONDS" "$STAGE1_FLOOD_FAST" "$STAGE1_FLOOD_SLOW" "$STAGE1_FLOOD_DELAY_MS" "$STAGE1_IDLE_SECONDS" "$OUTPUT_JSON" "$OUTPUT_MD" <<'PY'
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

root_dir = Path(sys.argv[1])
repro_script = Path(sys.argv[2])
run_root = Path(sys.argv[3])
phase0_capture_seconds = int(sys.argv[4])
stage_capture_seconds = int(sys.argv[5])
stage2c_capture_seconds = int(sys.argv[6])
stage2a_idle_seconds = int(sys.argv[7])
stage1_flood_fast = int(sys.argv[8])
stage1_flood_slow = int(sys.argv[9])
stage1_flood_delay_ms = int(sys.argv[10])
stage1_idle_seconds = int(sys.argv[11])
output_json = Path(sys.argv[12])
output_md = Path(sys.argv[13])

if not repro_script.exists():
    raise SystemExit(f"Repro-Skript fehlt: {repro_script}")

run_root.mkdir(parents=True, exist_ok=True)


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def log(msg: str) -> None:
    print(f"[{ts()}] {msg}", flush=True)


def list_runs() -> list[Path]:
    return sorted(
        [p for p in run_root.iterdir() if p.is_dir() and re.match(r"^\d{8}_\d{6}$", p.name)],
        key=lambda p: p.name,
    )


def parse_run_dir(stdout_lines: list[str]) -> Path | None:
    for line in reversed(stdout_lines):
        m = re.search(r"^Output:\s+(logs/current/hardware/disconnect-repro/\d{8}_\d{6})\s*$", line.strip())
        if m:
            return root_dir / m.group(1)
    return None


def analyze_run(run_dir: Path, profile: str, capture_exit: int) -> dict:
    summary_json = run_dir / "run_summary.json"
    serial_log = run_dir / "esp32_serial.log"
    server_log = run_dir / "server.log"
    payload: dict = {
        "profile": profile,
        "run_dir": str(run_dir),
        "run_id": run_dir.name,
        "capture_exit": capture_exit,
        "summary_json_exists": summary_json.exists(),
        "serial_exists": serial_log.exists(),
        "serial_size": serial_log.stat().st_size if serial_log.exists() else 0,
        "unusable": True,
        "unusable_reasons": ["summary_json_missing"],
        "mqtt_disconnected": 0,
        "write_timeout_classified": 0,
        "err_4062": 0,
        "tls_timeout": 0,
        "fp2_marker": 0,
    }

    if summary_json.exists():
        parsed = json.loads(summary_json.read_text(encoding="utf-8", errors="ignore") or "{}")
        counts = parsed.get("counts", {})
        serial_counts = counts.get("serial", {})
        payload["unusable"] = bool(parsed.get("unusable", True))
        payload["unusable_reasons"] = list(parsed.get("unusable_reasons", []))
        payload["mqtt_disconnected"] = int(serial_counts.get("mqtt_disconnected", 0))
        payload["write_timeout_classified"] = int(serial_counts.get("write_timeout_classified", 0))
        payload["err_4062"] = int(serial_counts.get("err_4062", 0))
        tclasses = counts.get("transport_classes", {})
        payload["tls_timeout"] = int(tclasses.get("tls_timeout", 0))

    if server_log.exists():
        server_lines = server_log.read_text(encoding="utf-8", errors="ignore").splitlines()
        payload["fp2_marker"] = sum(
            (
                "inbound_inbox_evict priority=NORMAL" in line
                or "Queue pressure event:" in line
                or ("LWT received: ESP" in line and "unexpected_disconnect" in line)
            )
            for line in server_lines
        )

    return payload


def run_capture(profile: str, capture_s: int, flood_fast: int, flood_slow: int, flood_delay_ms: int) -> dict:
    before = {p.name for p in list_runs()}
    env = os.environ.copy()
    actuator_gpios = env.get("ACTUATOR_GPIOS", "").strip()
    env.update(
        {
            "RUN_PROFILE": profile,
            "CAPTURE_SECONDS": str(capture_s),
            "FLOOD_COUNT_FAST": str(flood_fast),
            "FLOOD_COUNT_SLOW": str(flood_slow),
            "FLOOD_DELAY_SLOW_MS": str(flood_delay_ms),
            "ACTUATOR_GPIOS": actuator_gpios,
        }
    )

    cmd = ["bash", str(repro_script)]
    gpio_info = actuator_gpios if actuator_gpios else "single(GPIO)"
    log(
        f"Starte {profile} (capture={capture_s}s, fast={flood_fast}, slow={flood_slow}, "
        f"delay={flood_delay_ms}ms, actuator_gpios={gpio_info})"
    )
    proc = subprocess.Popen(
        cmd,
        cwd=str(root_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    stdout_lines: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        print(line, end="", flush=True)
        stdout_lines.append(line.rstrip("\n"))
    capture_exit = proc.wait()

    run_dir = parse_run_dir(stdout_lines)
    if run_dir is None:
        after = list_runs()
        new_runs = [p for p in after if p.name not in before]
        run_dir = new_runs[-1] if new_runs else (after[-1] if after else None)
    if run_dir is None:
        raise RuntimeError(f"Kein Run-Verzeichnis auffindbar für Profil {profile}")

    result = analyze_run(run_dir, profile=profile, capture_exit=capture_exit)
    log(
        f"Fertig {profile} -> run={result['run_id']} unusable={result['unusable']} "
        f"dis={result['mqtt_disconnected']} wt={result['write_timeout_classified']} "
        f"4062={result['err_4062']} tls={result['tls_timeout']} fp2={result['fp2_marker']}"
    )
    return result


def gate_phase0(run: dict) -> bool:
    return run["capture_exit"] == 0 and not run["unusable"] and run["serial_size"] > 0


def gate_stage1(run: dict) -> bool:
    return (
        run["capture_exit"] == 0
        and not run["unusable"]
        and run["mqtt_disconnected"] <= 1
        and run["write_timeout_classified"] <= 1
        and run["err_4062"] <= 30
        and run["tls_timeout"] == 0
        and run["fp2_marker"] > 0
    )


def gate_stage2a(run: dict) -> bool:
    reconnect_ok = run["mqtt_disconnected"] == 0 or run["serial_size"] > 0
    return (
        run["capture_exit"] == 0
        and not run["unusable"]
        and run["mqtt_disconnected"] <= 1
        and run["write_timeout_classified"] <= 1
        and run["err_4062"] <= 80
        and reconnect_ok
    )


def gate_stage2b(run: dict) -> bool:
    reconnect_ok = run["mqtt_disconnected"] == 0 or run["serial_size"] > 0
    return (
        run["capture_exit"] == 0
        and not run["unusable"]
        and run["mqtt_disconnected"] <= 1
        and run["write_timeout_classified"] <= 1
        and run["err_4062"] <= 150
        and reconnect_ok
    )


report: dict = {
    "started_at": datetime.now().isoformat(),
    "phase0": {},
    "stages": {},
    "stop_reason": None,
}

# Phase 0
phase0_run = run_capture("stage-chain-phase0", phase0_capture_seconds, 40, 30, 30)
phase0_go = gate_phase0(phase0_run)
report["phase0"] = {"run": phase0_run, "gate": "Go" if phase0_go else "No-Go"}
if not phase0_go:
    report["stop_reason"] = "phase0_no_go"
    report["finished_at"] = datetime.now().isoformat()
else:
    # Stage 1
    s1_runs = [run_capture("stage-chain-stage1-run1", stage_capture_seconds, stage1_flood_fast, stage1_flood_slow, stage1_flood_delay_ms)]
    if stage1_idle_seconds > 0:
        log(f"Stage 1 Recovery-Idle: {stage1_idle_seconds}s")
        time.sleep(stage1_idle_seconds)
    s1_runs.append(run_capture("stage-chain-stage1-run2", stage_capture_seconds, stage1_flood_fast, stage1_flood_slow, stage1_flood_delay_ms))
    s1_go = all(gate_stage1(run) for run in s1_runs)
    report["stages"]["1"] = {"runs": s1_runs, "gate": "Go" if s1_go else "No-Go"}

    if not s1_go:
        report["stop_reason"] = "stage1_no_go"
    else:
        # Stage 2A
        s2a_run1 = run_capture("stage-chain-stage2a-run1", stage_capture_seconds, 320, 220, 15)
        log(f"Pflicht-Idle Stage 2A: {stage2a_idle_seconds}s")
        for remaining in range(stage2a_idle_seconds, 0, -10):
            shown = remaining if remaining < 10 else remaining
            log(f"Idle verbleibend: {shown}s")
            time.sleep(10 if remaining >= 10 else remaining)
        s2a_run2 = run_capture("stage-chain-stage2a-run2", stage_capture_seconds, 320, 220, 15)
        s2a_runs = [s2a_run1, s2a_run2]
        s2a_go = all(gate_stage2a(run) for run in s2a_runs)
        report["stages"]["2A"] = {"runs": s2a_runs, "gate": "Go" if s2a_go else "No-Go"}

        if not s2a_go:
            report["stop_reason"] = "stage2a_no_go"
        else:
            # Stage 2B
            s2b_runs = [
                run_capture("stage-chain-stage2b-run1", stage_capture_seconds, 420, 300, 12),
                run_capture("stage-chain-stage2b-run2", stage_capture_seconds, 420, 300, 12),
            ]
            s2b_go = all(gate_stage2b(run) for run in s2b_runs)
            report["stages"]["2B"] = {"runs": s2b_runs, "gate": "Go" if s2b_go else "No-Go"}

            if not s2b_go:
                report["stop_reason"] = "stage2b_no_go"
            else:
                # Stage 2C (beobachtend)
                s2c_run = run_capture("stage-chain-stage2c-run1", stage2c_capture_seconds, 520, 360, 10)
                report["stages"]["2C"] = {"runs": [s2c_run], "gate": "Observe"}
                report["stop_reason"] = "completed_through_2c"

report["finished_at"] = datetime.now().isoformat()
output_json.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

lines = []
lines.append("# Disconnect Stage Chain Report")
lines.append("")
lines.append(f"- Start: `{report['started_at']}`")
lines.append(f"- Ende: `{report['finished_at']}`")
lines.append(f"- Stop-Grund: `{report['stop_reason']}`")
lines.append("")
lines.append("## Gate-Ergebnisse")
lines.append(f"- Phase 0: `{report.get('phase0', {}).get('gate', 'n/a')}`")
for stage in ["1", "2A", "2B", "2C"]:
    gate = report.get("stages", {}).get(stage, {}).get("gate")
    if gate:
        lines.append(f"- Stage {stage}: `{gate}`")
lines.append("")
lines.append("## Letzte Runs")
for stage_name, payload in report.get("stages", {}).items():
    runs = payload.get("runs", [])
    if not runs:
        continue
    last = runs[-1]
    lines.append(
        f"- Stage {stage_name}: `{last['run_id']}` "
        f"(unusable={last['unusable']}, dis={last['mqtt_disconnected']}, "
        f"wt={last['write_timeout_classified']}, 4062={last['err_4062']}, tls={last['tls_timeout']})"
    )
output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

log(f"Stage-Report JSON: {output_json}")
log(f"Stage-Report MD:   {output_md}")
PY
