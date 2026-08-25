/**
 * S4 / AUT-1388: Fertigation inflow/runoff empty option is enabled
 * so the pair can be cleared without deleting the widget.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import WidgetConfigPanel from '@/components/dashboard-widgets/WidgetConfigPanel.vue'

vi.mock('@/shared/design/primitives', () => ({
  SlideOver: {
    name: 'SlideOver',
    template: '<div class="slide-over-stub"><slot /></div>',
    props: ['open', 'title', 'width'],
  },
}))

vi.mock('@/stores/esp', () => ({
  useEspStore: () => ({
    devices: [],
    getDeviceId: () => 'ESP_TEST',
  }),
}))

vi.mock('@/api/sensors', () => ({
  sensorsApi: {
    get: vi.fn(),
  },
}))

const INFLOW_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const RUNOFF_ID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'

describe('WidgetConfigPanel fertigation empty', () => {
  it('should enable empty inflow/runoff options and emit empty ids', async () => {
    const wrapper = mount(WidgetConfigPanel, {
      props: {
        open: true,
        widgetId: 'w-fert-1',
        widgetType: 'fertigation-pair',
        config: {
          inflowSensorId: INFLOW_ID,
          runoffSensorId: RUNOFF_ID,
          sensorType: 'ec',
        },
      },
    })

    const selects = wrapper.findAll('select.widget-config-panel__select')
    const inflow = selects[0]
    const runoff = selects[1]
    expect(inflow).toBeDefined()
    expect(runoff).toBeDefined()

    const inflowEmpty = inflow!.find('option[value=""]')
    const runoffEmpty = runoff!.find('option[value=""]')
    expect(inflowEmpty.exists()).toBe(true)
    expect(runoffEmpty.exists()).toBe(true)
    expect(inflowEmpty.attributes('disabled')).toBeUndefined()
    expect(runoffEmpty.attributes('disabled')).toBeUndefined()
    expect(inflowEmpty.text()).toBe('— keiner —')
    expect(runoffEmpty.text()).toBe('— keiner —')

    await inflow!.setValue('')
    const emitted = wrapper.emitted('update:config')
    expect(emitted).toBeTruthy()
    const last = emitted![emitted!.length - 1][0] as { inflowSensorId: string }
    expect(last.inflowSensorId).toBe('')
    expect(wrapper.exists()).toBe(true)
  })
})
