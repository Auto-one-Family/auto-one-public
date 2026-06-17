#!/usr/bin/env python3
"""
Contract governance gate for PR validation.

Blocks PRs when:
1) new CONTRACT_* codes are added without lexicon coverage,
2) mandatory contract attributes are missing in the lexicon matrix,
3) contract-related source changes have no matching test updates,
4) fallback/healing additions are made without explicit contract signaling.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LEXICON_PATH = REPO_ROOT / ".claude" / "reference" / "errors" / "ERROR_CODES.md"
MANDATORY_MATRIX_HEADER = "## 13b. Contract-Code Governance Matrix"
MANDATORY_COLUMNS = [
    "Code",
    "Domain",
    "Severity",
    "Terminality",
    "Retry-Policy",
    "Operator-Action",
]

CONTRACT_CODE_RE = re.compile(r"\bCONTRACT_[A-Z0-9_]+\b")
FALLBACK_RE = re.compile(r"\b(fallback|heal|healing|self[-_ ]?heal|default(?:ed)?|normalize[sd]?|coerce[sd]?)\b", re.IGNORECASE)
CONTRACT_SIGNAL_RE = re.compile(r"(contract_|contract\b|correlation_id|contract_violation)", re.IGNORECASE)


class GateResult:
    def __init__(self, errors: list[str] | None = None, warnings: list[str] | None = None):
        self.errors = errors or []
        self.warnings = warnings or []

    def fail(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def run_git(args: list[str]) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout


def extract_changed_files(base_ref: str) -> list[str]:
    out = run_git(["diff", "--name-only", f"{base_ref}...HEAD"])
    return [line.strip() for line in out.splitlines() if line.strip()]


def extract_added_lines(base_ref: str) -> list[tuple[str, str]]:
    """
    Return list of (file_path, added_line_content) from git diff.
    """
    out = run_git(["diff", "--unified=0", "--no-color", f"{base_ref}...HEAD"])
    added: list[tuple[str, str]] = []
    current_file = ""
    for line in out.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:].strip()
            continue
        if line.startswith("+") and not line.startswith("+++"):
            added.append((current_file, line[1:]))
    return added


def parse_contract_codes_from_text(text: str) -> set[str]:
    return set(CONTRACT_CODE_RE.findall(text))


def validate_lexicon_contract_matrix(result: GateResult, lexicon_content: str) -> None:
    if MANDATORY_MATRIX_HEADER not in lexicon_content:
        result.fail(
            f"Lexikon fehlt Pflichtsektion '{MANDATORY_MATRIX_HEADER}' mit Contract-Attributen."
        )
        return

    section = lexicon_content.split(MANDATORY_MATRIX_HEADER, 1)[1]
    lines = section.splitlines()
    table_lines: list[str] = []
    for line in lines:
        if line.startswith("## ") and table_lines:
            break
        if line.strip().startswith("|"):
            table_lines.append(line.rstrip())
        elif table_lines and not line.strip():
            # allow empty line inside section after table has started
            continue

    if len(table_lines) < 3:
        result.fail("Contract-Code Governance Matrix ist leer oder unvollständig.")
        return

    header_cells = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    if header_cells != MANDATORY_COLUMNS:
        result.fail(
            "Contract-Code Governance Matrix Header ist ungültig. "
            f"Erwartet: {MANDATORY_COLUMNS}, gefunden: {header_cells}"
        )
        return

    for row in table_lines[2:]:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        if len(cells) != len(MANDATORY_COLUMNS):
            result.fail(f"Ungültige Matrix-Zeile (Spaltenzahl): {row}")
            continue
        if any(not value for value in cells):
            result.fail(f"Leeres Pflichtfeld in Contract-Matrix: {row}")


def validate_new_contract_codes_covered(
    result: GateResult,
    added_lines: list[tuple[str, str]],
    lexicon_content: str,
) -> None:
    added_code_candidates: set[str] = set()
    for file_path, line in added_lines:
        if not file_path:
            continue
        # ignore tests and docs; gate targets source additions
        if "/tests/" in file_path.replace("\\", "/"):
            continue
        if line.lstrip().startswith("#"):
            continue
        added_code_candidates.update(parse_contract_codes_from_text(line))

    if not added_code_candidates:
        return

    missing = sorted(code for code in added_code_candidates if code not in lexicon_content)
    for code in missing:
        result.fail(
            f"Neuer Contract-Code ohne Lexikon-Eintrag: {code} ({LEXICON_PATH.as_posix()})"
        )


def validate_contract_test_coverage(result: GateResult, changed_files: list[str]) -> None:
    normalized = [path.replace("\\", "/") for path in changed_files]
    contract_source_changed = any(
        (
            path.startswith("El Servador/god_kaiser_server/src/")
            and "contract" in path.lower()
        )
        or (
            path.startswith("El Frontend/src/")
            and "contract" in path.lower()
        )
        for path in normalized
    )
    if not contract_source_changed:
        return

    has_contract_test_change = any(
        ("/tests/" in path and "contract" in path.lower()) for path in normalized
    )
    if not has_contract_test_change:
        result.fail(
            "Contract-bezogene Source-Änderungen ohne angepasste Contract-Tests "
            "(Pflicht: mindestens eine geänderte Testdatei mit 'contract' im Pfad/Namen)."
        )


def validate_fallback_has_contract_signal(
    result: GateResult,
    added_lines: list[tuple[str, str]],
) -> None:
    violations: list[str] = []
    for file_path, line in added_lines:
        normalized_file = file_path.replace("\\", "/")
        if not normalized_file:
            continue
        if "/tests/" in normalized_file:
            continue
        if not (
            normalized_file.startswith("El Servador/god_kaiser_server/src/")
            or normalized_file.startswith("El Frontend/src/")
            or normalized_file.startswith("El Trabajante/src/")
        ):
            continue
        if FALLBACK_RE.search(line) and not CONTRACT_SIGNAL_RE.search(line):
            violations.append(f"{normalized_file}: +{line.strip()}")

    for violation in violations:
        result.fail(
            "Fallback/Heilung ohne Contract-Signal erkannt: "
            f"{violation}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run contract governance CI gate.")
    parser.add_argument(
        "--base-ref",
        default="origin/master",
        help="Git base ref used for diff (default: origin/master)",
    )
    args = parser.parse_args()

    result = GateResult(errors=[], warnings=[])

    if not LEXICON_PATH.exists():
        print(f"::error::{LEXICON_PATH.as_posix()} fehlt.")
        return 1

    lexicon_content = LEXICON_PATH.read_text(encoding="utf-8")
    validate_lexicon_contract_matrix(result, lexicon_content)

    changed_files = extract_changed_files(args.base_ref)
    added_lines = extract_added_lines(args.base_ref)

    validate_new_contract_codes_covered(result, added_lines, lexicon_content)
    validate_contract_test_coverage(result, changed_files)
    validate_fallback_has_contract_signal(result, added_lines)

    for warning in result.warnings:
        print(f"::warning::{warning}")
    for error in result.errors:
        print(f"::error::{error}")

    if result.errors:
        print(f"Contract governance gate FAILED with {len(result.errors)} error(s).")
        return 1

    print("Contract governance gate PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
