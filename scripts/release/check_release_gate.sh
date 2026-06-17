#!/usr/bin/env bash
# ============================================
# Release Gate Status Check
# ============================================
# Prueft ob SIL-Gate und Hardware-Gate bestanden sind.
# Erzeugt den finalen Gate-Report.
#
# Usage:
#   bash scripts/release/check_release_gate.sh
#   bash scripts/release/check_release_gate.sh --sil-only

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPORT_DIR="$PROJECT_ROOT/.claude/reports/current"
TIMESTAMP=$(date +%Y-%m-%d)
BRANCH=$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
COMMIT=$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")
SIL_ONLY=false

[[ "${1:-}" == "--sil-only" ]] && SIL_ONLY=true

log_info()  { echo "[INFO]  $*"; }
log_pass()  { echo "[PASS]  $*"; }
log_fail()  { echo "[FAIL]  $*"; }

# --- SIL-Gate pruefen ---
log_info "=== Release Gate Check ==="
log_info "Branch: $BRANCH | Commit: $COMMIT"

SIL_STATUS="NICHT_GETESTET"
SIL_DETAIL=""

# Pruefe ob Gap-1-Testskript-Report existiert
GAP1_REPORTS=$(find "$PROJECT_ROOT/logs/wokwi/reports/gap1/" -name "*.md" 2>/dev/null | sort -r | head -1)
if [ -n "$GAP1_REPORTS" ]; then
  if grep -q "^\*\*BESTANDEN\*\*" "$GAP1_REPORTS" 2>/dev/null; then
    SIL_STATUS="PASS"
    SIL_DETAIL="Letzer Report: $GAP1_REPORTS"
  else
    SIL_STATUS="FAIL"
    SIL_DETAIL="Letzer Report: $GAP1_REPORTS (NICHT BESTANDEN)"
  fi
else
  SIL_STATUS="NICHT_GETESTET"
  SIL_DETAIL="Kein SIL-Report gefunden. Bitte ausfuehren: bash scripts/wokwi/gap1_mqtt_contract_test.sh"
fi

log_info "SIL-Gate: $SIL_STATUS ($SIL_DETAIL)"

# --- Hardware-Gate pruefen ---
HW_STATUS="NICHT_GETESTET"
HW_DETAIL=""

if [ "$SIL_ONLY" = true ]; then
  HW_STATUS="UEBERSPRUNGEN"
  HW_DETAIL="--sil-only Modus"
else
  HW_REPORTS=$(find "$PROJECT_ROOT/logs/current/hardware/gap3/" -name "*.md" 2>/dev/null | sort -r | head -1)
  if [ -n "$HW_REPORTS" ]; then
    if grep -q "HARDWARE-GATE: PASS" "$HW_REPORTS" 2>/dev/null; then
      HW_STATUS="PASS"
      HW_DETAIL="Letzer Report: $HW_REPORTS"
    else
      HW_STATUS="FAIL"
      HW_DETAIL="Letzer Report: $HW_REPORTS (BLOCKIERT)"
    fi
  else
    HW_STATUS="NICHT_GETESTET"
    HW_DETAIL="Kein HW-Report gefunden. Bitte ausfuehren: bash scripts/hardware/release_gate_hw_test.sh"
  fi
fi

log_info "Hardware-Gate: $HW_STATUS ($HW_DETAIL)"

# --- Entscheidung ---
GATE_REPORT="$REPORT_DIR/wokwi-hardware-release-gate-verifikation-${TIMESTAMP}.md"

cat > "$GATE_REPORT" << EOF
# Release Gate Verifikation

**Datum:** $(date -Iseconds)
**Branch:** $BRANCH
**Commit:** $COMMIT

## Gate-Status

| Gate | Status | Detail |
|------|--------|--------|
| SIL (Wokwi) | $SIL_STATUS | $SIL_DETAIL |
| Hardware | $HW_STATUS | $HW_DETAIL |

## Entscheidung

EOF

if [ "$SIL_STATUS" = "PASS" ] && [ "$HW_STATUS" = "PASS" ]; then
  echo "**RELEASE: FREIGEGEBEN**" >> "$GATE_REPORT"
  echo "" >> "$GATE_REPORT"
  echo "Beide Gates bestanden. Keine Blocker." >> "$GATE_REPORT"
  log_pass "=== RELEASE: FREIGEGEBEN ==="
elif [ "$SIL_STATUS" = "PASS" ] && [ "$HW_STATUS" = "UEBERSPRUNGEN" ]; then
  echo "**RELEASE: BEDINGT (SIL-only)**" >> "$GATE_REPORT"
  echo "" >> "$GATE_REPORT"
  echo "SIL bestanden. Hardware-Gate uebersprungen (--sil-only)." >> "$GATE_REPORT"
  echo "Fuer vollstaendige Freigabe: Hardware-Gate nachholen." >> "$GATE_REPORT"
  log_info "=== RELEASE: BEDINGT (nur SIL) ==="
else
  BLOCKERS=""
  [ "$SIL_STATUS" != "PASS" ] && BLOCKERS="${BLOCKERS}- SIL: $SIL_STATUS ($SIL_DETAIL)\n"
  [ "$HW_STATUS" != "PASS" ] && [ "$HW_STATUS" != "UEBERSPRUNGEN" ] && BLOCKERS="${BLOCKERS}- Hardware: $HW_STATUS ($HW_DETAIL)\n"
  echo "**RELEASE: BLOCKIERT**" >> "$GATE_REPORT"
  echo "" >> "$GATE_REPORT"
  echo "Blocker:" >> "$GATE_REPORT"
  echo -e "$BLOCKERS" >> "$GATE_REPORT"
  log_fail "=== RELEASE: BLOCKIERT ==="
fi

cat >> "$GATE_REPORT" << EOF

## Naechste Schritte

1. SIL-Gate ausfuehren: \`bash scripts/wokwi/gap1_mqtt_contract_test.sh\`
2. Hardware-Gate ausfuehren: \`bash scripts/hardware/release_gate_hw_test.sh\`
3. Release-Gate pruefen: \`bash scripts/release/check_release_gate.sh\`
EOF

log_info "Report: $GATE_REPORT"

# Exit code reflects gate decision
if [ "$SIL_STATUS" = "PASS" ] && { [ "$HW_STATUS" = "PASS" ] || [ "$HW_STATUS" = "UEBERSPRUNGEN" ]; }; then
  exit 0
else
  exit 1
fi
