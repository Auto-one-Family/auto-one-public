/**
 * AUT-1397 [M-5]: Measure bindings under rule_metadata.measure_bindings[].
 * Observe-only — never part of trigger_conditions (M-1 schema mirror).
 */

export type MeasureBindingHook =
  | 'on_start'
  | 'after_action'
  | 'after_settle'
  | 'on_complete'

export type MeasureBindingFormulaId = 'difference' | 'delta_over_event'

export type MeasureBindingOutputTarget = 'execution_metadata' | 'ledger'

/** formula_params.ui_target for Frischwasser-(L) in Salzrechner (AUT-1397). */
export const UI_TARGET_SALT_CALCULATOR_VOLUME_ZUGABE =
  'salt_calculator_volume_zugabe' as const

export interface MeasureBindingSensorRef {
  esp_id: string
  gpio: number
  sensor_type: string
}

export interface MeasureBinding {
  sensor_refs: MeasureBindingSensorRef[]
  hooks: MeasureBindingHook[]
  formula_id: MeasureBindingFormulaId
  formula_params: Record<string, unknown>
  output_target: MeasureBindingOutputTarget
}

export const MEASURE_BINDING_HOOK_OPTIONS: ReadonlyArray<{
  id: MeasureBindingHook
  label: string
  hint: string
}> = [
  {
    id: 'on_start',
    label: 'Erste Messung',
    hint: 'wenn die Regel startet (Anfangswert)',
  },
  {
    id: 'after_action',
    label: 'Nach einem Schritt',
    hint: 'direkt nach einem Aktorschritt in der Sequenz',
  },
  {
    id: 'after_settle',
    label: 'Nach Wartezeit',
    hint: 'nach einer Pause / Beruhigung',
  },
  {
    id: 'on_complete',
    label: 'Letzte Messung',
    hint: 'wenn die Regel fertig ist (Endwert)',
  },
]

export const MEASURE_BINDING_FORMULA_OPTIONS: ReadonlyArray<{
  id: MeasureBindingFormulaId
  label: string
}> = [
  {
    id: 'difference',
    label: 'Unterschied Anfang → Ende (ein Sensor)',
  },
  {
    id: 'delta_over_event',
    label: 'Unterschied über den Vorgang',
  },
]

/** Assist / Frischwasser field source (AUT-1385 / AUT-1397). */
export type VolumeZugabeSource = 'manual' | 'measured' | 'none'
