import { describe, it, expect } from 'vitest'
import {
  createEmptyBinding,
  createFreshWaterFlowBinding,
  getMeasureBindings,
  setMeasureBindings,
  parseSensorOptionValue,
  measureBindingFromNodeData,
  measureBindingToNodeData,
  isTwoSensorMeasureFormula,
} from '@/utils/measureBindings'
import { UI_TARGET_SALT_CALCULATOR_VOLUME_ZUGABE } from '@/types/measureBinding'

describe('measureBindings', () => {
  it('should read empty list when measure_bindings absent', () => {
    expect(getMeasureBindings({})).toEqual([])
    expect(getMeasureBindings(undefined)).toEqual([])
  })

  it('should write only measure_bindings key — never invent trigger_conditions', () => {
    const next = setMeasureBindings(
      { dose_config: { volume_l: 20 } },
      [createEmptyBinding()],
    )
    expect(next.dose_config).toEqual({ volume_l: 20 })
    expect(Array.isArray(next.measure_bindings)).toBe(true)
    expect(next).not.toHaveProperty('trigger_conditions')
  })

  it('should remove measure_bindings when list emptied', () => {
    const next = setMeasureBindings(
      { measure_bindings: [createEmptyBinding()], paired_rule_id: 'x' },
      [],
    )
    expect(next).not.toHaveProperty('measure_bindings')
    expect(next.paired_rule_id).toBe('x')
  })

  it('should build Frischwasser preset with ledger + ui_target', () => {
    const binding = createFreshWaterFlowBinding(
      { esp_id: 'ESP_57E1D4', gpio: 14, sensor_type: 'flow' },
      { esp_id: 'ESP_57E1D4', gpio: 25 },
    )
    expect(binding.output_target).toBe('ledger')
    expect(binding.formula_id).toBe('difference')
    expect(binding.hooks).toEqual(['on_start', 'on_complete'])
    expect(binding.formula_params.ui_target).toBe(
      UI_TARGET_SALT_CALCULATOR_VOLUME_ZUGABE,
    )
    expect(binding.formula_params.bracket_actuator_gpio).toBe(25)
    expect(binding.sensor_refs[0]?.sensor_type).toBe('flow')
  })

  it('should parse sensor option values by name path', () => {
    expect(parseSensorOptionValue('ESP_AA:14:flow')).toEqual({
      esp_id: 'ESP_AA',
      gpio: 14,
      sensor_type: 'flow',
    })
    expect(parseSensorOptionValue('bad')).toBeNull()
  })

  it('should round-trip node data ↔ measure_bindings without trigger fields', () => {
    const binding = createFreshWaterFlowBinding({
      esp_id: 'ESP_57E1D4',
      gpio: 14,
      sensor_type: 'flow',
    })
    const nodeData = measureBindingToNodeData(binding)
    expect(nodeData).not.toHaveProperty('operator')
    expect(nodeData).not.toHaveProperty('threshold')
    const back = measureBindingFromNodeData(nodeData)
    expect(back.sensor_refs[0]?.gpio).toBe(14)
    expect(back.output_target).toBe('ledger')
    expect(back).not.toHaveProperty('type')
  })

  it('should detect two-sensor B−A face mode by sensor_refs count', () => {
    expect(isTwoSensorMeasureFormula(1)).toBe(false)
    expect(isTwoSensorMeasureFormula(2)).toBe(true)
  })
})
