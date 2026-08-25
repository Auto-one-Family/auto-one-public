/**
 * AUT-1397: MeasureBindingEditor writes only rule_metadata.measure_bindings.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { computed } from 'vue'
import { setActivePinia, createPinia } from 'pinia'
import MeasureBindingEditor from '@/components/rules/MeasureBindingEditor.vue'

vi.mock('@/composables/useSensorOptions', () => ({
  useSensorOptions: () => ({
    groupedSensorOptions: computed(() => [
      {
        label: 'Zone A',
        zoneId: 'z1',
        subgroups: [
          {
            label: '',
            subzoneId: null,
            options: [
              {
                label: 'Durchflusssensor',
                value: 'ESP_57E1D4:14:flow',
                sensorType: 'flow',
                espId: 'ESP_57E1D4',
                gpio: 14,
              },
            ],
          },
        ],
      },
    ]),
    flatSensorOptions: computed(() => []),
  }),
}))

vi.mock('@/stores/esp', () => ({
  useEspStore: () => ({
    devices: [
      {
        device_id: 'ESP_57E1D4',
        name: 'Nachfüll-ESP',
        sensors: [{ gpio: 14, sensor_type: 'flow', name: 'Durchflusssensor' }],
      },
    ],
    getDeviceId: (d: { device_id?: string }) => d.device_id || '',
  }),
}))

describe('<MeasureBindingEditor>', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should emit measure_bindings only (never trigger_conditions)', async () => {
    const wrapper = mount(MeasureBindingEditor, {
      props: {
        ruleMetadata: { dose_config: { volume_l: 20 } },
      },
    })

    await wrapper.get('[data-testid="measure-binding-add"]').trigger('click')
    const emitted = wrapper.emitted('update:rule-metadata')
    expect(emitted).toBeTruthy()
    const meta = emitted![0][0] as Record<string, unknown>
    expect(meta.dose_config).toEqual({ volume_l: 20 })
    expect(Array.isArray(meta.measure_bindings)).toBe(true)
    expect(meta).not.toHaveProperty('trigger_conditions')
  })

  it('should apply Frischwasser preset into measure_bindings', async () => {
    const wrapper = mount(MeasureBindingEditor, {
      props: {
        ruleMetadata: {},
        refillPumpHint: { espId: 'ESP_57E1D4', gpio: 25, name: 'Nachfüllpumpe' },
      },
    })

    await wrapper.get('[data-testid="measure-binding-add"]').trigger('click')
    const afterAdd = wrapper.emitted('update:rule-metadata')!.at(-1)![0] as Record<
      string,
      unknown
    >
    await wrapper.setProps({ ruleMetadata: afterAdd })

    const select = wrapper.get('[data-testid="measure-binding-sensor"]')
    await select.setValue('ESP_57E1D4:14:flow')
    await select.trigger('change')
    const afterSensor = wrapper.emitted('update:rule-metadata')!.at(-1)![0] as Record<
      string,
      unknown
    >
    await wrapper.setProps({ ruleMetadata: afterSensor })
    await wrapper.vm.$nextTick()

    await wrapper.get('[data-testid="measure-binding-freshwater-preset"]').trigger('click')
    const final = wrapper.emitted('update:rule-metadata')!.at(-1)![0] as Record<
      string,
      unknown
    >
    const bindings = final.measure_bindings as Array<Record<string, unknown>>
    expect(bindings[0].output_target).toBe('ledger')
    expect(
      (bindings[0].formula_params as Record<string, unknown>).ui_target,
    ).toBe('salt_calculator_volume_zugabe')
    expect(final).not.toHaveProperty('trigger_conditions')
  })
})
