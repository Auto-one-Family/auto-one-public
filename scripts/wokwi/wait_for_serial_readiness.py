#!/usr/bin/env python3
"""Wait for a readiness marker in a serial logfile."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def append_report(report_file: Path | None, line: str) -> None:
    if report_file is None:
        return
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with report_file.open("a", encoding="utf-8") as handle:
        handle.write(f"{line}\n")


def build_tail_excerpt(text: str, tail_lines: int) -> str:
    if tail_lines <= 0:
        return ""
    lines = text.splitlines()
    if not lines:
        return "(log file is empty)"
    excerpt = lines[-tail_lines:]
    return "\n".join(excerpt)


def resolve_log_path(explicit: str | None, auto_latest: bool) -> Path | None:
    if explicit:
        return Path(explicit)
    if not auto_latest:
        return None
    logs = sorted(Path(".").glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    return logs[0] if logs else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Wait for serial readiness pattern")
    parser.add_argument("--log-file")
    parser.add_argument("--auto-latest-log", action="store_true")
    parser.add_argument("--pattern", default="MQTT connected successfully")
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--tail-lines", type=int, default=40)
    # Legacy argument kept for backward compatibility, but fixed fallback sleeps are disabled.
    parser.add_argument("--fallback-sleep-seconds", type=int, default=0)
    parser.add_argument("--report-file")
    args = parser.parse_args()

    report_path = Path(args.report_file) if args.report_file else None
    log_file = resolve_log_path(args.log_file, args.auto_latest_log)
    if log_file is None or not log_file.exists():
        print(f"[ERROR] Log file not found: {log_file}", file=sys.stderr)
        return 20

    append_report(report_path, f"- Logfile: {log_file}")
    append_report(report_path, f"- Readiness pattern: `{args.pattern}`")
    append_report(report_path, f"- Wait start: {now_iso()}")

    deadline = time.time() + max(args.timeout_seconds, 0)
    latest_text = ""
    while time.time() <= deadline:
        try:
            latest_text = log_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            latest_text = ""
        if args.pattern in latest_text:
            ts = now_iso()
            print(f"[READY] Pattern matched in {log_file}")
            print(ts)
            append_report(report_path, f"- Readiness matched: {ts}")
            return 0
        time.sleep(max(args.poll_seconds, 0.1))

    if args.fallback_sleep_seconds > 0:
        print(
            "[WARN] --fallback-sleep-seconds is deprecated and ignored; "
            "readiness falls back to hard timeout."
        )

    print(f"[ERROR] Readiness timeout after {args.timeout_seconds}s for {log_file}", file=sys.stderr)
    excerpt = build_tail_excerpt(latest_text, args.tail_lines)
    if excerpt:
        print(f"[ERROR] Last {args.tail_lines} log lines before timeout:", file=sys.stderr)
        print(excerpt, file=sys.stderr)
        append_report(report_path, f"- Timeout excerpt ({args.tail_lines} lines):")
        for line in excerpt.splitlines():
            append_report(report_path, f"  {line}")
    return 21


if __name__ == "__main__":
    raise SystemExit(main())
