/**
 * SubzoneAssignmentSection — zone-scoped subzone options on initial sensor config
 *
 * Bug: loadSubzones only called GET …/devices/{espId}/subzones. A fresh ESP in a
 * zone that already has Topf 1/2 on a sibling device showed only "Keine Subzone".
 * zoneId was passed but unused; options must merge espStore sibling subzones.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import SubzoneAssignmentSection from '@/components/devices/SubzoneAssignmentSection.vue'

const getSubzones = vi.fn()

vi.mock('@/api/subzones', () => ({
  subzonesApi: {
    getSubzones: (...args: unknown[]) => getSubzones(...args),
    getSensorAssignments: vi.fn(async () => ({ assignments: [] })),
    getActuatorAssignments: vi.fn(async () => ({ assignments: [] })),
    assignSubzone: vi.fn(),
    assignSensor: vi.fn(),
    assignActuator: vi.fn(),
    removeSensor: vi.fn(),
    removeActuator: vi.fn(),
  },
}))

vi.mock('@/stores/esp', () => ({
  useEspStore: () => ({
    devices: [
      {
        device_id: 'ESP_FRESH',
        zone_id: 'zelt_wohnzimmer',
        subzones: [],
      },
      {
        device_id: 'ESP_SIBLING',
        zone_id: 'zelt_wohnzimmer',
        subzones: [
          {
            subzone_id: 'topf_1',
            subzone_name: 'Topf 1',
            assigned_gpios: [32],
            sensor_count: 1,
            actuator_count: 0,
          },
          {
            subzone_id: 'topf_2',
            subzone_name: 'Topf 2',
            assigned_gpios: [33],
            sensor_count: 1,
            actuator_count: 0,
          },
        ],
      },
      {
        device_id: 'ESP_OTHER_ZONE',
        zone_id: 'andere_zone',
        subzones: [
          {
            subzone_id: 'fremd',
            subzone_name: 'Fremd',
            assigned_gpios: [],
            sensor_count: 0,
            actuator_count: 0,
          },
        ],
      },
    ],
    getDeviceId: (d: { device_id?: string }) => d?.device_id || '',
    fetchAll: vi.fn(),
  }),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}))

describe('SubzoneAssignmentSection', () => {
  beforeEach(() => {
    getSubzones.mockReset()
    getSubzones.mockResolvedValue({
      device_id: 'ESP_FRESH',
      zone_id: 'zelt_wohnzimmer',
      subzones: [],
      total_count: 0,
    })
  })

  it('should list zone sibling subzones when current ESP has none', async () => {
    const wrapper = mount(SubzoneAssignmentSection, {
      props: {
        espId: 'ESP_FRESH',
        gpio: 0,
        modelValue: null,
        zoneId: 'zelt_wohnzimmer',
      },
    })
    await flushPromises()

    const options = wrapper.findAll('[data-testid="subzone-gpio-select"] option')
    const labels = options.map((o) => o.text())

    expect(labels).toContain('Keine Subzone')
    expect(labels).toContain('Topf 1')
    expect(labels).toContain('Topf 2')
    expect(labels).toContain('+ Neue Subzone erstellen...')
    expect(labels).not.toContain('Fremd')
  })

  it('should prefer current-ESP API subzones and keep zone siblings', async () => {
    getSubzones.mockResolvedValue({
      device_id: 'ESP_FRESH',
      zone_id: 'zelt_wohnzimmer',
      subzones: [
        {
          subzone_id: 'topf_1',
          subzone_name: 'Topf 1',
          position_label: 'links',
          parent_zone_id: 'zelt_wohnzimmer',
          assigned_gpios: [21],
          safe_mode_active: true,
          sensor_count: 0,
          actuator_count: 0,
          custom_data: {},
        },
      ],
      total_count: 1,
    })

    const wrapper = mount(SubzoneAssignmentSection, {
      props: {
        espId: 'ESP_FRESH',
        gpio: 21,
        modelValue: null,
        zoneId: 'zelt_wohnzimmer',
      },
    })
    await flushPromises()

    const labels = wrapper
      .findAll('[data-testid="subzone-gpio-select"] option')
      .map((o) => o.text())

    expect(labels).toContain('Topf 1 · links')
    expect(labels).toContain('Topf 2')
  })

  it('should prefer zone sibling Klarname over local auto Subzone N', async () => {
    getSubzones.mockResolvedValue({
      device_id: 'ESP_FRESH',
      zone_id: 'zelt_wohnzimmer',
      subzones: [
        {
          subzone_id: 'topf_1',
          subzone_name: 'Subzone 2',
          parent_zone_id: 'zelt_wohnzimmer',
          assigned_gpios: [0],
          safe_mode_active: true,
          sensor_count: 1,
          actuator_count: 0,
          custom_data: {},
        },
      ],
      total_count: 1,
    })

    const wrapper = mount(SubzoneAssignmentSection, {
      props: {
        espId: 'ESP_FRESH',
        gpio: 0,
        modelValue: null,
        zoneId: 'zelt_wohnzimmer',
      },
    })
    await flushPromises()

    const labels = wrapper
      .findAll('[data-testid="subzone-gpio-select"] option')
      .map((o) => o.text())

    expect(labels).toContain('Topf 1')
    expect(labels).not.toContain('Subzone 2')
  })
})
