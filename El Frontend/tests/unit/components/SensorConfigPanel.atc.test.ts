/**
 * SensorConfig ATC row (AUT-1511 / AUT-1514)
 *
 * Existing dropdown — human title, config_id value, one temp row, no gpio/chip/URL.
 * No new overlay. One source row. Dead always-on ATC badges stay off.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import SensorConfigPanel from '@/components/esp/SensorConfigPanel.vue'

const devices = [
  {
    device_id: 'ESP_AEAE64',
    name: 'Board',
    hardware_type: 'ESP32_WROOM',
    sensors: [
      { sensor_type: 'ph', name: 'Becken', gpio: 32, config_id: 'cfg-ph' },
      { sensor_type: 'ds18b20', name: null, gpio: 4, config_id: 'cfg-ds' },
      { sensor_type: 'sht31_temp', name: 'Temp&Hum', gpio: 0, config_id: 'cfg-sht' },
      { sensor_type: 'bme280_temp', name: 'Luft', gpio: 0, config_id: 'cfg-bme' },
    ],
  },
]

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/api/sensors', () => ({
  sensorsApi: {
    get: vi.fn(async () => null),
    getByConfigId: vi.fn(async () => null),
    getRuntime: vi.fn(),
    createOrUpdate: vi.fn(),
    delete: vi.fn(),
  },
}))
vi.mock('@/api/esp', () => ({
  espApi: { isMockEsp: () => false },
}))
vi.mock('@/api/device-context', () => ({
  deviceContextApi: { getContext: vi.fn(async () => ({ active_zone_id: null })) },
}))
vi.mock('@/stores/esp', () => ({
  useEspStore: () => ({
    devices,
    getDeviceId: (d: { device_id?: string }) => d?.device_id || '',
    removeSensor: vi.fn(),
  }),
}))
vi.mock('@/shared/stores/ui.store', () => ({
  useUiStore: () => ({ confirm: vi.fn() }),
}))
vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}))
vi.mock('@/shared/stores/dashboard.store', () => ({
  useDashboardStore: () => ({ layouts: [] }),
}))
vi.mock('@/shared/stores/logic.store', () => ({
  useLogicStore: () => ({ rules: [], fetchRules: vi.fn(async () => []) }),
}))
vi.mock('@/shared/stores/plants.store', () => ({
  usePlantsStore: () => ({ plants: [], fetchPlants: vi.fn(async () => []) }),
}))
vi.mock('@/shared/stores/zone.store', () => ({
  useZoneStore: () => ({ zoneEntities: [], fetchZoneEntities: vi.fn(async () => []) }),
}))
vi.mock('@/shared/stores/actuator.store', () => ({
  useActuatorStore: () => ({
    registerConfigIntentFromRest: vi.fn(),
    waitForConfigTerminal: vi.fn(),
  }),
}))
vi.mock('@/shared/stores/alert-center.store', () => ({
  useAlertCenterStore: () => ({ activeAlertsFromInbox: [] }),
}))
vi.mock('@/shared/stores/sensor.store', () => ({
  useSensorStore: () => ({ getAtcDegradedTimestamp: vi.fn(() => null) }),
}))

const stubs = {
  SettingsBreadcrumb: true,
  SubzoneAssignmentSection: true,
  AccordionSection: true,
  RangeSlider: true,
  AlertConfigSection: true,
  RuntimeMaintenanceSection: true,
  DeviceMetadataSection: true,
  PendingConfigBanner: true,
}

describe('SensorConfigPanel — ATC row (AUT-1511 / AUT-1514)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  async function mountPanel() {
    const wrapper = mount(SensorConfigPanel, {
      props: {
        espId: 'ESP_AEAE64',
        gpio: 32,
        sensorType: 'ph',
        configId: 'cfg-ph',
        activeTab: 'grundlagen',
        hideActions: true,
      },
      global: { plugins: [createPinia()], stubs },
    })
    await flushPromises()
    return wrapper
  }

  it('should show one ATC select with human titles and persist config_id', async () => {
    const wrapper = await mountPanel()
    const select = wrapper.get('[data-testid="sensor-config-atc-source"]')
    const options = select.findAll('option')
    const labels = options.map((o) => o.text())
    const values = options.map((o) => o.attributes('value') ?? (o.element as HTMLOptionElement).value)

    expect(wrapper.findAll('[data-testid="sensor-config-atc-source"]')).toHaveLength(1)
    expect(select.classes()).toContain('sensor-config__select--atc')
    expect(labels).toContain('Temperatur')
    expect(labels).toContain('Temp&Hum (Temperatur)')
    expect(values).toContain('cfg-ds')
    expect(values).toContain('cfg-sht')
    expect(labels.join(' ')).not.toContain('GPIO')
    expect(labels.join(' ')).not.toContain('bme280_temp')
    expect(values).not.toContain('cfg-bme')
    expect(wrapper.text()).not.toContain('Temperaturkompensation aktiv')
    expect(wrapper.text()).not.toContain('Kein Sensor verknüpft')
  })
})
