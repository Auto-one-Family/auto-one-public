/**
 * AUT-1376 A2.3 / AUT-1379 W1 / AUT-1390 — Anzeige-Helfer Dosis ↔ Laufzeit + Modus-Intent.
 * Server-Präzedenz (logic_engine._enrich_actions_with_duration):
 * dose_ml > 0 überschreibt duration_seconds; sonst gilt gespeicherte Laufzeit.
 * AUT-1384: fehlendes flow_rate_ml_s + duration > 0 → laufzeit-Fallback (WARNING).
 */

/** Wirksamer Drive — spiegelt Server-Präzedenz (keine zweite Wahrheit). */
export type DoseDriveMode = 'ml_driven' | 'duration_driven'

/**
 * FE-Intent am Sequenz-Schritt (AUT-1390).
 * Persistiert als Meta-Flag `dose_mode` am Step — kein neuer Server-Dosier-Pfad.
 */
export type StepDoseMode = 'duration' | 'ml' | 'target_optimal'

/**
 * Runtime-Zustand nur fuer Modus target_optimal (Zustands-Matrix AUT-1390 PASS):
 * flow_rate fehlt → duration_fallback
 * concentration fehlt (flow_rate ok) → auto_calibrating
 * beide da → concentration_exact
 */
export type TargetOptimalRuntimeState =
  | 'duration_fallback'
  | 'auto_calibrating'
  | 'concentration_exact'

export function resolveDoseDriveMode(
  doseMl: number | null | undefined,
): DoseDriveMode {
  return doseMl != null && doseMl > 0 ? 'ml_driven' : 'duration_driven'
}

export function doseDriveModeLabel(mode: DoseDriveMode): string {
  return mode === 'ml_driven' ? 'ml-getrieben' : 'laufzeit-getrieben'
}

/** Legacy ohne Flag: dose_ml>0 → ml, sonst duration (AUT-1379). */
export function resolveStepDoseMode(
  doseMode: StepDoseMode | string | null | undefined,
  doseMl: number | null | undefined,
): StepDoseMode {
  if (doseMode === 'duration' || doseMode === 'ml' || doseMode === 'target_optimal') {
    return doseMode
  }
  return doseMl != null && doseMl > 0 ? 'ml' : 'duration'
}

export function stepDoseModeOptionLabel(mode: StepDoseMode): string {
  switch (mode) {
    case 'duration':
      return 'Sekunden (laufzeit-getrieben)'
    case 'ml':
      return 'Feste Konzentration (ml-getrieben)'
    case 'target_optimal':
      return 'Zielwert-optimal'
  }
}

/** Kurze Alltagssprache je Modus (Selektor-Hilfe). */
export function stepDoseModeHelp(mode: StepDoseMode): string {
  switch (mode) {
    case 'duration':
      return 'Die Pumpe laeuft eine feste Zeit. Gut als einfacher Start oder Notloesung.'
    case 'ml':
      return 'Feste Menge in Millilitern. Der Server rechnet daraus die Laufzeit (Foerderrate noetig).'
    case 'target_optimal':
      return 'Dosiert exakt, sobald Foerderrate und Konzentration stimmen; bis die Foerderrate da ist sekundenbasiert; fehlende Konzentration kalibriert sich beim Dosieren selbst.'
  }
}

export function resolveTargetOptimalRuntimeState(
  flowRateMlS: number | null | undefined,
  concentration: number | null | undefined,
): TargetOptimalRuntimeState {
  const flowOk = flowRateMlS != null && flowRateMlS > 0
  const concOk = concentration != null && concentration > 0
  if (!flowOk) return 'duration_fallback'
  if (!concOk) return 'auto_calibrating'
  return 'concentration_exact'
}

export function targetOptimalRuntimeLabel(state: TargetOptimalRuntimeState): string {
  switch (state) {
    case 'duration_fallback':
      return 'laeuft laufzeit-getrieben bis kalibriert'
    case 'auto_calibrating':
      return 'Zielwert-optimal — misst Konzentration / kalibriert sich'
    case 'concentration_exact':
      return 'konzentrations-exakt'
  }
}

/** Badge-Text fuer wirksamen Zustand (Modus-Intent + Runtime). */
export function stepEffectiveModeBadgeLabel(
  doseMode: StepDoseMode | string | null | undefined,
  doseMl: number | null | undefined,
  flowRateMlS: number | null | undefined,
  concentration: number | null | undefined,
): string {
  const mode = resolveStepDoseMode(doseMode, doseMl)
  if (mode === 'target_optimal') {
    return targetOptimalRuntimeLabel(
      resolveTargetOptimalRuntimeState(flowRateMlS, concentration),
    )
  }
  if (mode === 'ml') {
    return doseDriveModeLabel('ml_driven')
  }
  return doseDriveModeLabel('duration_driven')
}

/**
 * Laufzeit-Feld read-only?
 * duration → immer editierbar
 * ml → read-only wenn dose_ml>0 (Server-Präzedenz)
 * target_optimal → read-only wenn flow_rate ok und dose_ml>0 (sonst Fallback editierbar)
 */
export function isStepDurationReadonly(
  doseMode: StepDoseMode | string | null | undefined,
  doseMl: number | null | undefined,
  flowRateMlS: number | null | undefined,
): boolean {
  const mode = resolveStepDoseMode(doseMode, doseMl)
  if (mode === 'duration') return false
  if (mode === 'ml') return resolveDoseDriveMode(doseMl) === 'ml_driven'
  const flowOk = flowRateMlS != null && flowRateMlS > 0
  return flowOk && doseMl != null && doseMl > 0
}

/** ml → s (Anzeige; Server rechnet autoritativ ceil). */
export function doseMlToDurationSeconds(
  doseMl: number | null | undefined,
  flowRateMlS: number | null | undefined,
): number | null {
  if (doseMl == null || doseMl <= 0 || flowRateMlS == null || flowRateMlS <= 0) return null
  return Math.ceil(doseMl / flowRateMlS)
}

/** s → ml-Äquivalent (Anzeige; kein Persistenz-Write). */
export function durationSecondsToMlEquivalent(
  durationSeconds: number | null | undefined,
  flowRateMlS: number | null | undefined,
): number | null {
  if (
    durationSeconds == null ||
    durationSeconds <= 0 ||
    flowRateMlS == null ||
    flowRateMlS <= 0
  ) {
    return null
  }
  // Eine Nachkommastelle — Förderrate ist typisch 0.x–few ml/s.
  return Math.round(durationSeconds * flowRateMlS * 10) / 10
}
