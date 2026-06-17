#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCENARIOS_DIR="$PROJECT_ROOT/El Trabajante/tests/wokwi/scenarios"
REPORT_DIR="$PROJECT_ROOT/logs/wokwi/reports/gap2"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$REPORT_DIR"

export GAP2_SCENARIOS_DIR="$SCENARIOS_DIR"
export GAP2_REPORT_DIR="$REPORT_DIR"
export GAP2_TIMESTAMP="$TIMESTAMP"

PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1 || ! "$PYTHON_BIN" --version >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

"$PYTHON_BIN" - <<'PY'
import csv
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path

scenarios_dir = Path(os.environ["GAP2_SCENARIOS_DIR"])
report_dir = Path(os.environ["GAP2_REPORT_DIR"])
timestamp = os.environ["GAP2_TIMESTAMP"]

required_categories = {
    "02-sensor", "03-actuator", "04-zone", "05-emergency",
    "06-config", "07-combined", "09-hardware", "11-error-injection",
    "12-correlation",
}
boot_gpio_only = {"01-boot", "gpio"}


@dataclass
class Row:
    scenario: str
    category: str
    mqtt_wait: str
    registration_gate: bool
    heartbeat_gate: bool
    template_compliance: str
    risiko: str
    injection_type: str


def detect_mqtt_wait(text: str) -> str:
    specific = '- wait-serial: "MQTT connected successfully"' in text
    generic = '- wait-serial: "MQTT connected"' in text
    if specific and generic:
        return "mixed"
    if specific:
        return "specific"
    if generic:
        return "generic"
    return "none"


rows = []
for path in sorted(scenarios_dir.rglob("*.yaml")):
    if "TEMPLATE" in path.name:
        continue
    rel = path.relative_to(scenarios_dir).as_posix()
    category = rel.split("/", 1)[0]
    text = path.read_text(encoding="utf-8", errors="replace")

    mqtt_wait = detect_mqtt_wait(text)
    registration_gate = '- wait-serial: "REGISTRATION"' in text or "REGISTRATION CONFIRMED" in text
    heartbeat_gate = '- wait-serial: "heartbeat"' in text or '- wait-serial: "Initial heartbeat sent"' in text

    injection_type = ""
    if category == "11-error-injection":
        injection_type = Path(rel).stem.replace("error_", "")

    compliance = "PASS"
    risiko = "none"

    if category == "11-error-injection":
        if mqtt_wait != "specific" or not registration_gate or not heartbeat_gate:
            compliance = "FAIL"
            risiko = "P0"
    elif category in required_categories:
        if mqtt_wait == "generic" or mqtt_wait == "mixed":
            compliance = "WARN"
            risiko = "P1"
    elif category in boot_gpio_only:
        if mqtt_wait == "none":
            compliance = "PASS_EXCEPTION"
            risiko = "none"

    rows.append(
        Row(
            scenario=rel,
            category=category,
            mqtt_wait=mqtt_wait,
            registration_gate=registration_gate,
            heartbeat_gate=heartbeat_gate,
            template_compliance=compliance,
            risiko=risiko,
            injection_type=injection_type,
        )
    )

counts = Counter(r.risiko for r in rows)
by_category = defaultdict(lambda: Counter())
for row in rows:
    by_category[row.category][row.risiko] += 1

status = "PASS" if counts["P0"] == 0 else "FAIL"

json_path = report_dir / f"audit_{timestamp}.json"
csv_path = report_dir / f"matrix_{timestamp}.csv"
md_path = report_dir / f"audit_{timestamp}.md"

with csv_path.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "scenario",
            "category",
            "mqtt_wait",
            "registration_gate",
            "heartbeat_gate",
            "template_compliance",
            "risiko",
            "injection_type",
        ],
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(asdict(row))

payload = {
    "status": status,
    "summary": {
        "total": len(rows),
        "p0": counts["P0"],
        "p1": counts["P1"],
        "none": counts["none"],
    },
    "artifacts": {
        "matrix_csv": str(csv_path),
        "report_md": str(md_path),
    },
    "rows": [asdict(row) for row in rows],
}
json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

lines = [
    "# Gap 2 Scenario Audit",
    "",
    f"- Status: **{status}**",
    f"- Total scenarios: **{len(rows)}**",
    f"- P0 findings: **{counts['P0']}**",
    f"- P1 findings: **{counts['P1']}**",
    "",
    "## Category Findings",
    "",
    "| category | p0 | p1 | none |",
    "|---|---:|---:|---:|",
]
for category in sorted(by_category.keys()):
    lines.append(
        f"| {category} | {by_category[category]['P0']} | {by_category[category]['P1']} | {by_category[category]['none']} |"
    )

lines.extend(
    [
        "",
        "## Contract Compliance Matrix",
        "",
        "| scenario | category | mqtt_wait | registration_gate | heartbeat_gate | template_compliance | risiko |",
        "|---|---|---|---|---|---|---|",
    ]
)
for row in rows:
    lines.append(
        f"| `{row.scenario}` | {row.category} | {row.mqtt_wait} | {str(row.registration_gate).lower()} | {str(row.heartbeat_gate).lower()} | {row.template_compliance} | {row.risiko} |"
    )

md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

print(f"GAP2_AUDIT_STATUS={status}")
print(f"GAP2_AUDIT_JSON={json_path}")
print(f"GAP2_AUDIT_MD={md_path}")
print(f"GAP2_AUDIT_MATRIX={csv_path}")
PY
