#!/usr/bin/env bash
# System Health Aggregator - Bash wrapper for debug-status.ps1 (Windows).
# Run from project root: ./scripts/debug/debug-status.sh
# Output: JSON to stdout. Agents call this for a single-command system status.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
exec powershell.exe -NoProfile -File "$PROJECT_ROOT/scripts/debug/debug-status.ps1" -ProjectRoot "$PROJECT_ROOT"
