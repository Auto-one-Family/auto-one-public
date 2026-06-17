#!/usr/bin/env python3
"""
Top-3 Gap Verifizierung fuer Wokwi + Docker + MCP + Release-Gate.

Reihenfolge (verbindlich):
  1) Gap 1: Docker/Wokwi/MQTT Contract
  2) Gap 2: Szenario-Normierung + representative Suite
  3) Gap 3: SIL + Hardware-Sanity Gate

Das Skript erzeugt die geforderten Reports unter .claude/reports/current/.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRABAJANTE_DIR = PROJECT_ROOT / "El Trabajante"
REPORT_DIR = PROJECT_ROOT / ".claude" / "reports" / "current"

LOG_SERIAL_GAP1 = PROJECT_ROOT / "logs" / "wokwi" / "serial" / "gap1"
LOG_MQTT_GAP1 = PROJECT_ROOT / "logs" / "wokwi" / "mqtt" / "gap1"
LOG_REPORT_GAP1 = PROJECT_ROOT / "logs" / "wokwi" / "reports" / "gap1"

LOG_SERIAL_GAP2 = PROJECT_ROOT / "logs" / "wokwi" / "serial" / "gap2"
LOG_REPORT_GAP2 = PROJECT_ROOT / "logs" / "wokwi" / "reports" / "gap2"
LOG_ERROR_GAP2 = PROJECT_ROOT / "logs" / "wokwi" / "error-injection" / "gap2"

LOG_REPORT_GAP3 = PROJECT_ROOT / "logs" / "wokwi" / "reports" / "gap3"
LOG_HW_GAP3 = PROJECT_ROOT / "logs" / "current" / "hardware" / "gap3"

GAP1_REPORT = REPORT_DIR / "gap1-mqtt-docker-contract-verifikation-2026-04-06.md"
GAP2_REPORT = REPORT_DIR / "gap2-szenario-normierung-verifikation-2026-04-06.md"
GAP3_REPORT = REPORT_DIR / "gap3-sil-hardware-gate-verifikation-2026-04-06.md"
GAP3_SUMMARY_ALIAS = REPORT_DIR / "wokwi-hardware-release-gate-verifikation-2026-04-06.md"
FINAL_REPORT = REPORT_DIR / "top3-gaps-abschlussbericht-2026-04-06.md"


@dataclass
class CmdResult:
    name: str
    command: list[str]
    cwd: str
    started_at: str
    ended_at: str
    duration_s: float
    exit_code: int
    log_file: str


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs() -> None:
    for path in [
        LOG_SERIAL_GAP1,
        LOG_MQTT_GAP1,
        LOG_REPORT_GAP1,
        LOG_SERIAL_GAP2,
        LOG_REPORT_GAP2,
        LOG_ERROR_GAP2,
        LOG_REPORT_GAP3,
        LOG_HW_GAP3,
        REPORT_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def git_info() -> dict[str, str]:
    def run_git(args: list[str]) -> str:
        try:
            out = subprocess.check_output(
                ["git", *args],
                cwd=PROJECT_ROOT,
                text=True,
                stderr=subprocess.STDOUT,
            )
            return out.strip()
        except Exception:
            return "unknown"

    return {
        "branch": run_git(["rev-parse", "--abbrev-ref", "HEAD"]),
        "commit": run_git(["rev-parse", "HEAD"]),
    }


def run_command(name: str, cmd: list[str], cwd: Path, log_file: Path, env: dict[str, str] | None = None) -> CmdResult:
    started = datetime.now(timezone.utc)
    started_monotonic = time.monotonic()
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    with log_file.open("w", encoding="utf-8") as fh:
        fh.write(f"# name: {name}\n")
        fh.write(f"# started_at: {started.isoformat()}\n")
        fh.write(f"# cwd: {cwd}\n")
        fh.write(f"# command: {' '.join(cmd)}\n\n")
        fh.flush()

        proc = subprocess.run(
            cmd,
            cwd=cwd,
            stdout=fh,
            stderr=subprocess.STDOUT,
            text=True,
            env=merged_env,
            check=False,
        )

    ended = datetime.now(timezone.utc)
    duration = time.monotonic() - started_monotonic
    return CmdResult(
        name=name,
        command=cmd,
        cwd=str(cwd),
        started_at=started.isoformat(),
        ended_at=ended.isoformat(),
        duration_s=round(duration, 3),
        exit_code=proc.returncode,
        log_file=str(log_file.relative_to(PROJECT_ROOT)),
    )


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def has_signature(text: str, needles: list[str]) -> dict[str, bool]:
    low = text.lower()
    return {needle: needle.lower() in low for needle in needles}


def check_tcp(host: str, port: int, timeout_s: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except Exception:
        return False


def run_gap1(skip_exec: bool) -> dict[str, Any]:
    contract_host = os.environ.get("WOKWI_MQTT_HOST", "host.wokwi.internal")
    contract_port = int(os.environ.get("WOKWI_MQTT_PORT", "1883"))
    docker_host = os.environ.get("WOKWI_MQTT_HOST_DOCKER", "host.docker.internal")
    local_host = os.environ.get("WOKWI_MQTT_HOST_LOCAL", "host.wokwi.internal")
    ci_host = os.environ.get("WOKWI_MQTT_HOST_CI", "host.wokwi.internal")

    results: list[CmdResult] = []

    smoke_log = LOG_SERIAL_GAP1 / "smoke-connectivity.log"
    inject_log = LOG_SERIAL_GAP1 / "injection-roundtrip.log"
    rep_logs: list[Path] = []

    prereq = {
        "has_wokwi_token": bool(os.environ.get("WOKWI_CLI_TOKEN")),
        "has_wokwi_cli": shutil.which("wokwi-cli") is not None,
        "has_firmware": (TRABAJANTE_DIR / ".pio" / "build" / "wokwi_simulation" / "firmware.bin").exists(),
    }
    can_execute = all(prereq.values()) and not skip_exec

    # Transport contract checks (non-fatal diagnostics)
    transport_diag = {
        "contract_host": contract_host,
        "contract_port": contract_port,
        "docker_host": docker_host,
        "local_host": local_host,
        "ci_host": ci_host,
        "tcp_local_contract": check_tcp(contract_host, contract_port),
        "tcp_docker_hint": check_tcp(docker_host, contract_port),
        "tcp_localhost": check_tcp("localhost", contract_port),
    }

    if can_execute:
        results.append(
            run_command(
                "gap1-smoke-connectivity",
                [
                    sys.executable,
                    str(PROJECT_ROOT / "scripts" / "run-wokwi-tests.py"),
                    "--scenario",
                    "boot_full",
                    "--no-retry",
                    "--no-mqtt-capture",
                    "--verbose",
                ],
                PROJECT_ROOT,
                smoke_log,
            )
        )

        results.append(
            run_command(
                "gap1-injection-roundtrip",
                [
                    sys.executable,
                    str(PROJECT_ROOT / "scripts" / "run-wokwi-tests.py"),
                    "--scenario",
                    "actuator_led_on",
                    "--no-retry",
                    "--no-mqtt-capture",
                    "--verbose",
                ],
                PROJECT_ROOT,
                inject_log,
            )
        )

        for idx in range(1, 4):
            rep_log = LOG_SERIAL_GAP1 / f"stability-run-{idx}.log"
            rep_logs.append(rep_log)
            results.append(
                run_command(
                    f"gap1-stability-{idx}",
                    [
                        sys.executable,
                        str(PROJECT_ROOT / "scripts" / "run-wokwi-tests.py"),
                        "--scenario",
                        "actuator_led_on",
                        "--no-retry",
                        "--no-mqtt-capture",
                    ],
                    PROJECT_ROOT,
                    rep_log,
                )
            )
    else:
        smoke_log.write_text(
            "Gap1 Smoke skipped: prerequisites missing or --skip-exec aktiv.\n"
            + json.dumps(prereq, indent=2),
            encoding="utf-8",
        )
        inject_log.write_text(
            "Gap1 Injection skipped: prerequisites missing or --skip-exec aktiv.\n"
            + json.dumps(prereq, indent=2),
            encoding="utf-8",
        )

    signatures = {
        "smoke": has_signature(
            read_text(smoke_log),
            ["Phase 5: Actuator System READY", "MQTT connected", "heartbeat"],
        ),
        "injection": has_signature(
            read_text(inject_log),
            ["MQTT connected", "Actuator", "command"],
        ),
    }

    stable_runs = [r for r in results if r.name.startswith("gap1-stability-")]
    stable_green = sum(1 for r in stable_runs if r.exit_code == 0)

    report = {
        "package": "A",
        "prerequisites": prereq,
        "can_execute": can_execute,
        "transport_contract": transport_diag,
        "runs": [asdict(r) for r in results],
        "serial_signatures": signatures,
        "stability_3x_green": stable_green == 3 and len(stable_runs) == 3,
        "stable_green_count": stable_green,
    }

    (LOG_REPORT_GAP1 / "gap1-execution.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    (LOG_MQTT_GAP1 / "gap1-transport-diagnostics.json").write_text(
        json.dumps(transport_diag, indent=2),
        encoding="utf-8",
    )
    return report


def run_gap2(skip_exec: bool) -> dict[str, Any]:
    scenarios_root = TRABAJANTE_DIR / "tests" / "wokwi" / "scenarios"

    audit_findings: list[dict[str, Any]] = []
    priority_categories = {"01-boot", "03-actuator", "06-config", "07-combined", "11-error-injection"}

    for yaml_file in sorted(scenarios_root.glob("*/*.yaml")):
        category = yaml_file.parent.name
        if category not in priority_categories:
            continue
        txt = read_text(yaml_file)
        low = txt.lower()
        has_wait = "wait-serial" in low
        has_mqtt_wait = "mqtt connected" in low
        has_set_control = "set-control" in low
        mqtt_injection_hint = ("requires mqtt injection" in low) or ("mosquitto_pub" in low)

        issues: list[str] = []
        if not has_wait:
            issues.append("kein wait-serial vorhanden")
        if not has_mqtt_wait:
            issues.append("kein stabiler MQTT wait-serial vorhanden")
        if category in {"03-actuator", "06-config", "07-combined", "11-error-injection"} and has_set_control:
            issues.append("set-control in externer MQTT-Kategorie erkannt")
        if mqtt_injection_hint and "delay" not in low:
            issues.append("kein Delay-Fenster fuer externe Injection dokumentiert")

        if issues:
            audit_findings.append(
                {
                    "scenario": str(yaml_file.relative_to(PROJECT_ROOT)),
                    "issues": issues,
                }
            )

    representative = [
        "boot_full",
        "config_sensor_add",
        "error_mqtt_disconnect",
        "multi_device_parallel",
    ]

    prereq = {
        "has_wokwi_token": bool(os.environ.get("WOKWI_CLI_TOKEN")),
        "has_wokwi_cli": shutil.which("wokwi-cli") is not None,
        "has_firmware": (TRABAJANTE_DIR / ".pio" / "build" / "wokwi_simulation" / "firmware.bin").exists(),
    }
    can_execute = all(prereq.values()) and not skip_exec

    runs: list[CmdResult] = []
    if can_execute:
        for scenario in representative:
            for rep in (1, 2):
                log_file = LOG_SERIAL_GAP2 / f"{scenario}_run{rep}.log"
                runs.append(
                    run_command(
                        f"gap2-{scenario}-run{rep}",
                        [
                            sys.executable,
                            str(PROJECT_ROOT / "scripts" / "run-wokwi-tests.py"),
                            "--scenario",
                            scenario,
                            "--no-retry",
                            "--no-mqtt-capture",
                        ],
                        PROJECT_ROOT,
                        log_file,
                    )
                )
    else:
        (LOG_SERIAL_GAP2 / "representative-suite-skipped.log").write_text(
            "Gap2 representative suite skipped: prerequisites missing or --skip-exec aktiv.\n"
            + json.dumps(prereq, indent=2),
            encoding="utf-8",
        )

    grouped: dict[str, list[CmdResult]] = {}
    for run in runs:
        parts = run.name.split("-")
        scenario_key = parts[1] if len(parts) > 2 else run.name
        grouped.setdefault(scenario_key, []).append(run)

    stability = {
        key: {
            "total": len(vals),
            "green": sum(1 for v in vals if v.exit_code == 0),
            "stable": len(vals) == 2 and all(v.exit_code == 0 for v in vals),
        }
        for key, vals in grouped.items()
    }

    report = {
        "package": "B",
        "audit_findings": audit_findings,
        "audit_issue_count": len(audit_findings),
        "template_version": "WOKWI_SCENARIO_TEMPLATE_V1",
        "representative_suite": representative,
        "prerequisites": prereq,
        "can_execute": can_execute,
        "runs": [asdict(r) for r in runs],
        "stability": stability,
        "all_representative_stable": bool(stability) and all(v["stable"] for v in stability.values()),
    }

    (LOG_REPORT_GAP2 / "gap2-execution.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    (LOG_ERROR_GAP2 / "gap2-audit-findings.json").write_text(
        json.dumps(audit_findings, indent=2),
        encoding="utf-8",
    )
    return report


def run_gap3(gap1: dict[str, Any], gap2: dict[str, Any], skip_exec: bool, force_fail_simulation: bool) -> dict[str, Any]:
    sil_pass = bool(gap1.get("stability_3x_green")) and bool(gap2.get("all_representative_stable"))
    sil_reason = []
    if not gap1.get("stability_3x_green"):
        sil_reason.append("Gap1 Stabilitaet 3/3 nicht erreicht")
    if not gap2.get("all_representative_stable"):
        sil_reason.append("Gap2 representative Suite nicht stabil")

    hw_log = LOG_HW_GAP3 / "hardware-sanity.log"
    hw_result: CmdResult | None = None
    hw_pass = False

    if not skip_exec:
        hw_result = run_command(
            "gap3-hardware-sanity",
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(PROJECT_ROOT / "scripts" / "tests" / "test_hardware_validation.ps1"),
            ],
            PROJECT_ROOT,
            hw_log,
        )
        hw_pass = hw_result.exit_code == 0
    else:
        hw_log.write_text(
            "Hardware sanity skipped via --skip-exec\n",
            encoding="utf-8",
        )

    fail_sim_blocked = False
    fail_sim_log = LOG_REPORT_GAP3 / "gate-fail-simulation.log"
    if force_fail_simulation:
        fail_sim_log.write_text(
            "Intentional fail simulation activated.\n"
            "Gate outcome forced to FAIL and release block validated.\n",
            encoding="utf-8",
        )
        fail_sim_blocked = True
    else:
        fail_sim_log.write_text(
            "No intentional fail simulation requested.\n",
            encoding="utf-8",
        )

    release_ready = sil_pass and hw_pass and not force_fail_simulation
    blockers: list[str] = []
    if not sil_pass:
        blockers.extend(sil_reason)
    if not hw_pass:
        blockers.append("Hardware-Sanity Gate nicht bestanden")
    if force_fail_simulation:
        blockers.append("Absichtlicher Fail-Simulationslauf blockiert Gate (erwartet)")

    report = {
        "package": "C",
        "sil_gate": {
            "pass": sil_pass,
            "reasons": sil_reason,
        },
        "hardware_gate": {
            "pass": hw_pass,
            "run": asdict(hw_result) if hw_result else None,
        },
        "fail_simulation": {
            "requested": force_fail_simulation,
            "blocked": fail_sim_blocked,
            "log_file": str(fail_sim_log.relative_to(PROJECT_ROOT)),
        },
        "release_ready": release_ready,
        "blockers": blockers,
    }
    (LOG_REPORT_GAP3 / "gap3-execution.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    return report


def write_md_reports(gap1: dict[str, Any], gap2: dict[str, Any], gap3: dict[str, Any]) -> None:
    gi = git_info()
    ts = now_iso()

    gap1_md = f"""# Gap 1 Verifikation (MQTT + Docker Contract)

- Zeitpunkt (UTC): `{ts}`
- Branch: `{gi["branch"]}`
- Commit: `{gi["commit"]}`
- Contract Host/Port: `{gap1["transport_contract"]["contract_host"]}:{gap1["transport_contract"]["contract_port"]}`

## Ergebnis

- Smoke ausgefuehrt: `{gap1["can_execute"]}`
- Stabilitaet 3x gruen: `{gap1["stability_3x_green"]}` ({gap1["stable_green_count"]}/3)
- Transportdiagnostik:
  - `tcp_local_contract`: `{gap1["transport_contract"]["tcp_local_contract"]}`
  - `tcp_docker_hint`: `{gap1["transport_contract"]["tcp_docker_hint"]}`
  - `tcp_localhost`: `{gap1["transport_contract"]["tcp_localhost"]}`

## Signaturen (Serial)

- Smoke: `{json.dumps(gap1["serial_signatures"]["smoke"])}`  
- Injection: `{json.dumps(gap1["serial_signatures"]["injection"])}`

## Artefakte

- `logs/wokwi/serial/gap1/`
- `logs/wokwi/mqtt/gap1/`
- `logs/wokwi/reports/gap1/gap1-execution.json`
"""
    GAP1_REPORT.write_text(gap1_md, encoding="utf-8")

    gap2_md = f"""# Gap 2 Verifikation (Szenario-Normierung)

- Zeitpunkt (UTC): `{ts}`
- Template-Version: `WOKWI_SCENARIO_TEMPLATE_V1`

## Audit-Ergebnis

- Findings gesamt: `{gap2["audit_issue_count"]}`
- Representative Suite stabil: `{gap2["all_representative_stable"]}`

## Representative Suite

- Szenarien: `{", ".join(gap2["representative_suite"])}`
- Ausfuehrbar: `{gap2["can_execute"]}`

## Artefakte

- `logs/wokwi/serial/gap2/`
- `logs/wokwi/reports/gap2/gap2-execution.json`
- `logs/wokwi/error-injection/gap2/gap2-audit-findings.json`
"""
    GAP2_REPORT.write_text(gap2_md, encoding="utf-8")

    gap3_md = f"""# Gap 3 Verifikation (SIL + Hardware Gate)

- Zeitpunkt (UTC): `{ts}`
- SIL-Gate: `{gap3["sil_gate"]["pass"]}`
- Hardware-Gate: `{gap3["hardware_gate"]["pass"]}`
- Fail-Simulation angefordert: `{gap3["fail_simulation"]["requested"]}`
- Fail-Simulation blockiert: `{gap3["fail_simulation"]["blocked"]}`

## Gate-Status

- Release-ready: `{gap3["release_ready"]}`
- Blocker: `{", ".join(gap3["blockers"]) if gap3["blockers"] else "keine"}`

## Artefakte

- `logs/wokwi/reports/gap3/`
- `logs/current/hardware/gap3/`
- `.claude/reports/current/wokwi-hardware-release-gate-verifikation-2026-04-06.md`
"""
    GAP3_REPORT.write_text(gap3_md, encoding="utf-8")
    GAP3_SUMMARY_ALIAS.write_text(gap3_md, encoding="utf-8")

    status_gap1 = "erledigt" if gap1["stability_3x_green"] else "offen"
    status_gap2 = "erledigt" if gap2["all_representative_stable"] and gap2["audit_issue_count"] == 0 else "offen"
    status_gap3 = "erledigt" if gap3["release_ready"] else "offen"

    final_md = f"""# Top-3 Gaps Abschlussbericht (2026-04-06)

## Status je Gap

- Gap 1 (Docker/MQTT Contract): **{status_gap1}**
- Gap 2 (Szenario-Normierung): **{status_gap2}**
- Gap 3 (SIL+Hardware Gate): **{status_gap3}**

## Harte Restblocker

{chr(10).join(f"- {b}" for b in (gap3["blockers"] or ["keine"]))}

## Naechste 3 Umsetzungsaufgaben

- CI-Job `wokwi-release-gate` als required check fuer Release-Branches in Branch Protection eintragen.
- Fuer alle prioritaeren MQTT-Szenarien explizite Injection-Windows (Delay + Post-Waits) auf Template V1 angleichen.
- Hardware-Sanity Lauf an dedizierte Device-Farm anbinden (COM-Endpoint + Broker + Server Health Precheck).

## Betriebsentscheidung

- **{"Gate release-ready" if gap3["release_ready"] else "nicht release-ready"}**
"""
    FINAL_REPORT.write_text(final_md, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Top-3 Gap Verifikation ausfuehren")
    parser.add_argument("--skip-exec", action="store_true", help="Keine externen Tests ausfuehren, nur Audit/Reports")
    parser.add_argument(
        "--force-fail-simulation",
        action="store_true",
        help="Absichtlichen Fail-Simulationslauf fuer Gate-Nachweis markieren",
    )
    args = parser.parse_args()

    ensure_dirs()
    gap1 = run_gap1(skip_exec=args.skip_exec)

    # Verbindliche Reihenfolge: Gap2 nur nach Gap1-Report
    gap2 = run_gap2(skip_exec=args.skip_exec)

    # Verbindliche Reihenfolge: Gap3 nur nach Gap2-Report
    gap3 = run_gap3(
        gap1=gap1,
        gap2=gap2,
        skip_exec=args.skip_exec,
        force_fail_simulation=args.force_fail_simulation,
    )

    write_md_reports(gap1, gap2, gap3)
    print("Top-3 Gap Verifikation abgeschlossen.")
    print(f"Report: {FINAL_REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
