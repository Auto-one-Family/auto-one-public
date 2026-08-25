/**
 * AUT-1397 / AUT-1399: Helpers for rule_metadata.measure_bindings[].
 * Writes ONLY into measure_bindings — never trigger_conditions.
 * AUT-1399: Canvas node type remains `sensor_diff` (umgewidmet), mapped here.
 */

import {
  UI_TARGET_SALT_CALCULATOR_VOLUME_ZUGABE,
  type MeasureBinding,
  type MeasureBindingFormulaId,
  type MeasureBindingHook,
  type MeasureBindingSensorRef,
} from '@/types/measureBinding'

const MEASURE_BINDINGS_KEY = 'measure_bindings'

/** Node.data shape for umgewidmeten sensor_diff-Knoten (Mess-Bindung). */
export interface MeasureBindingNodeData {
  label: string
  formulaId: MeasureBindingFormulaId
  sensorEspId: string
  sensorGpio: number | null
  sensorType: string
  /** Optional second sensor (Klarname „Sensor B“) — nur Anzeige/Refs wenn gesetzt. */
  sensorBEspId: string
  sensorBGpio: number | null
  sensorBType: string
  hooks: MeasureBindingHook[]
  outputTarget: MeasureBinding['output_target']
  formulaParams: Record<string, unknown>
}

export function createEmptyMeasureBindingNodeData(): MeasureBindingNodeData {
  const empty = createEmptyBinding()
  return measureBindingToNodeData(empty)
}

export function measureBindingToNodeData(binding: MeasureBinding): MeasureBindingNodeData {
  const a = binding.sensor_refs[0]
  const b = binding.sensor_refs[1]
  return {
    label: '',
    formulaId: binding.formula_id,
    sensorEspId: a?.esp_id ?? '',
    sensorGpio: a != null ? a.gpio : null,
    sensorType: a?.sensor_type ?? '',
    sensorBEspId: b?.esp_id ?? '',
    sensorBGpio: b != null ? b.gpio : null,
    sensorBType: b?.sensor_type ?? '',
    hooks: [...binding.hooks],
    outputTarget: binding.output_target,
    formulaParams: { ...(binding.formula_params ?? {}) },
  }
}

export function measureBindingFromNodeData(
  data: Partial<MeasureBindingNodeData> | Record<string, unknown> | undefined,
): MeasureBinding {
  const d = data ?? {}
  const formulaId =
    d.formulaId === 'delta_over_event' || d.formulaId === 'difference'
      ? d.formulaId
      : 'difference'
  const hooks = Array.isArray(d.hooks) && d.hooks.length > 0
    ? (d.hooks as MeasureBindingHook[])
    : (['on_start', 'on_complete'] as MeasureBindingHook[])
  const outputTarget =
    d.outputTarget === 'ledger' || d.outputTarget === 'execution_metadata'
      ? d.outputTarget
      : 'execution_metadata'
  const formulaParams =
    d.formulaParams && typeof d.formulaParams === 'object'
      ? { ...(d.formulaParams as Record<string, unknown>) }
      : {}

  const sensor_refs: MeasureBindingSensorRef[] = []
  const espA = typeof d.sensorEspId === 'string' ? d.sensorEspId : ''
  const gpioA = d.sensorGpio
  const typeA = typeof d.sensorType === 'string' ? d.sensorType : ''
  if (espA && gpioA != null && Number.isFinite(Number(gpioA)) && typeA) {
    sensor_refs.push({
      esp_id: espA,
      gpio: Number(gpioA),
      sensor_type: typeA,
    })
  }
  const espB = typeof d.sensorBEspId === 'string' ? d.sensorBEspId : ''
  const gpioB = d.sensorBGpio
  const typeB = typeof d.sensorBType === 'string' ? d.sensorBType : ''
  if (espB && gpioB != null && Number.isFinite(Number(gpioB)) && typeB) {
    sensor_refs.push({
      esp_id: espB,
      gpio: Number(gpioB),
      sensor_type: typeB,
    })
  }

  return {
    sensor_refs,
    hooks,
    formula_id: formulaId,
    formula_params: formulaParams,
    output_target: outputTarget,
  }
}

/** True when node face should show two distinct sensors (B−A), not Start/Ende of one. */
export function isTwoSensorMeasureFormula(sensorRefCount: number): boolean {
  return sensorRefCount >= 2
}

export function getMeasureBindings(
  ruleMetadata: Record<string, unknown> | null | undefined,
): MeasureBinding[] {
  const raw = ruleMetadata?.[MEASURE_BINDINGS_KEY]
  if (!Array.isArray(raw)) return []
  return raw.filter(isMeasureBindingShape) as MeasureBinding[]
}

export function setMeasureBindings(
  ruleMetadata: Record<string, unknown> | null | undefined,
  bindings: MeasureBinding[],
): Record<string, unknown> {
  const next: Record<string, unknown> = { ...(ruleMetadata ?? {}) }
  if (bindings.length === 0) {
    delete next[MEASURE_BINDINGS_KEY]
  } else {
    next[MEASURE_BINDINGS_KEY] = bindings.map(normalizeBinding)
  }
  return next
}

export function createEmptyBinding(): MeasureBinding {
  return {
    sensor_refs: [],
    hooks: ['on_start', 'on_complete'],
    formula_id: 'difference',
    formula_params: {},
    output_target: 'execution_metadata',
  }
}

/**
 * Preset for first concrete binding: Flow → Frischwasser-(L) via ledger.
 * Bracket hooks = pump ON→OFF (on_start / on_complete). Sensor must be chosen.
 */
export function createFreshWaterFlowBinding(
  sensor: MeasureBindingSensorRef,
  bracket?: { esp_id: string; gpio: number },
): MeasureBinding {
  const formula_params: Record<string, unknown> = {
    ui_target: UI_TARGET_SALT_CALCULATOR_VOLUME_ZUGABE,
  }
  if (bracket) {
    formula_params.bracket_actuator_esp_id = bracket.esp_id
    formula_params.bracket_actuator_gpio = bracket.gpio
  }
  return {
    sensor_refs: [sensor],
    hooks: ['on_start', 'on_complete'],
    formula_id: 'difference',
    formula_params,
    output_target: 'ledger',
  }
}

export function sensorRefKey(ref: MeasureBindingSensorRef): string {
  return `${ref.esp_id}:${ref.gpio}:${ref.sensor_type}`
}

export function parseSensorOptionValue(
  value: string,
): MeasureBindingSensorRef | null {
  const parts = value.split(':')
  if (parts.length < 3) return null
  const gpio = Number(parts[1])
  if (!Number.isFinite(gpio)) return null
  return {
    esp_id: parts[0],
    gpio,
    sensor_type: parts.slice(2).join(':'),
  }
}

function normalizeBinding(b: MeasureBinding): MeasureBinding {
  return {
    sensor_refs: b.sensor_refs.map((r) => ({
      esp_id: r.esp_id,
      gpio: r.gpio,
      sensor_type: r.sensor_type,
    })),
    hooks: [...b.hooks] as MeasureBindingHook[],
    formula_id: b.formula_id as MeasureBindingFormulaId,
    formula_params: { ...(b.formula_params ?? {}) },
    output_target: b.output_target,
  }
}

function isMeasureBindingShape(item: unknown): boolean {
  if (!item || typeof item !== 'object') return false
  const o = item as Record<string, unknown>
  return (
    Array.isArray(o.sensor_refs) &&
    Array.isArray(o.hooks) &&
    typeof o.formula_id === 'string' &&
    typeof o.output_target === 'string'
  )
}
