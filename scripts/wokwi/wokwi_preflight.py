#!/usr/bin/env python3
"""Cross-platform Wokwi preflight checks."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def cli_version() -> str:
    for cmd in (["wokwi-cli", "--short-version"], ["wokwi-cli", "--version"]):
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            text = result.stdout.strip()
            if text:
                match = re.search(r"(\d+\.\d+\.\d+)", text)
                if match:
                    return match.group(1)
                return text.split()[0]
        except Exception:
            continue
    return ""


def append_line(report: Path | None, line: str) -> None:
    if report is None:
        return
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("a", encoding="utf-8") as handle:
        handle.write(f"{line}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Wokwi preflight")
    parser.add_argument("--expected-version", default=os.environ.get("WOKWI_CLI_VERSION", ""))
    parser.add_argument("--report-file", default="")
    args = parser.parse_args()

    report = Path(args.report_file) if args.report_file else None
    expected = args.expected_version.strip()

    append_line(report, "# Wokwi Preflight")
    append_line(report, "")
    append_line(report, f"- Start: {now_iso()}")

    if shutil.which("wokwi-cli") is None:
        print("[FAIL] wokwi-cli missing")
        append_line(report, "- CLI present: no")
        return 10

    version = cli_version()
    print(f"[INFO] CLI version: {version}")
    append_line(report, "- CLI present: yes")
    append_line(report, f"- CLI version: {version or 'unknown'}")

    if expected and version != expected:
        print(f"[FAIL] Version mismatch expected={expected}, got={version}")
        append_line(report, f"- Version check: fail (expected {expected})")
        return 11

    if expected:
        append_line(report, f"- Version check: ok ({expected})")
    else:
        append_line(report, "- Version check: skipped")

    token = os.environ.get("WOKWI_CLI_TOKEN", "")
    if not token:
        print("[FAIL] WOKWI_CLI_TOKEN missing")
        append_line(report, "- Token present: no")
        return 12

    append_line(report, f"- Token present: yes (prefix {token[:4]}***, len {len(token)})")
    append_line(report, "- Result: PASS")
    append_line(report, f"- End: {now_iso()}")
    print("[PASS] Preflight passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
