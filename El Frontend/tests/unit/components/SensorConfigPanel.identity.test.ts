/**
 * SensorConfig identity (AUT-1514)
 *
 * One visible address: human word. config_id stays internal.
 * GPIO / chip-key / URL / raw ESP-ID are not extra labels in this window.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { setActivePinia, createPinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import SensorConfigPanel from '@/components/esp/SensorConfigPanel.vue'
import type { SensorConfigResponse } from '@/types'
import { sensorsApi } from '@/api/sensors'

vi.mock('@/api/sensors', () => ({
  sensorsApi: {
    getByConfigId: vi.fn(),
    get: vi.fn(),
    createOrUpdate: vi.fn(),
    delete: vi.fn(),
    getAlertConfig: vi.fn(),
    getRuntime: vi.fn(),
  },
}))
vi.mock('@/api/esp', () => ({
  espApi: { isMockEsp: () => false },
}))
vi.mock('@/api/device-context', () => ({
  deviceContextApi: { getContext: vi.fn(async () => ({ active_zone_id: null })) },
}))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/stores/esp', () => ({
  useEspStore: () => ({
    devices: [{
      device_id: 'ESP_AEAE64',
      name: 'Test-ESP',
      zone_id: 'z1',
      zone_name: 'Zelt A',
      sensors: [{
        gpio: 0,
        sensor_type: 'sht31_temp',
        name: 'Luft',
        config_id: 'cfg-temp',
      }],
    }],
    getDeviceId: (d: { device_id?: string }) => d?.device_id || '',
  }),
}))
vi.mock('@/shared/stores/ui.store', () => ({
  useUiStore: () => ({ confirm: vi.fn(async () => false) }),
}))
vi.mock('@/shared/stores/zone.store', () => ({
  useZoneStore: () => ({
    zoneEntities: [{ zone_id: 'z1', name: 'Zelt A', status: 'active' }],
    fetchZoneEntities: vi.fn(async () => {}),
  }),
}))
vi.mock('@/shared/stores/actuator.store', () => ({
  useActuatorStore: () => ({
    registerConfigIntentFromRest: vi.fn(),
    waitForConfigTerminal: vi.fn(async () => ({ state: 'terminal_success' })),
  }),
}))
vi.mock('@/shared/stores/logic.store', () => ({
  useLogicStore: () => ({
    rules: [],
    fetchRules: vi.fn(async () => {}),
  }),
}))
vi.mock('@/shared/stores/dashboard.store', () => ({
  useDashboardStore: () => ({ layouts: [] }),
}))
vi.mock('@/shared/stores/plants.store', () => ({
  usePlantsStore: () => ({
    plants: [],
    fetchPlants: vi.fn(async () => {}),
  }),
}))
vi.mock('@/shared/stores/alert-center.store', () => ({
  useAlertCenterStore: () => ({
    activeAlertsFromInbox: [],
  }),
}))
vi.mock('@/shared/stores/sensor.store', () => ({
  useSensorStore: () => ({
    sensors: [],
  }),
}))
vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}))
vi.mock('@/composables/useBoardLayout', () => ({
  useBoardLayout: () => ({
    layout: ref({ label: 'ESP32-WROOM-32' }),
    normalizedType: ref('ESP32_WROOM'),
    isKnownBoard: ref(true),
    i2cDefaultLabel: ref('SDA 21 / SCL 22'),
    isReserved: () => false,
    isSafe: () => true,
    adc1Pins: ref([32, 33, 34, 35, 36, 39]),
  }),
}))
vi.mock('@/utils/logger', () => ({
  createLogger: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
}))

const globalStubs = {
  AccordionSection: { template: '<div><slot /></div>' },
  AlertConfigSection: true,
  RuntimeMaintenanceSection: true,
  DeviceMetadataSection: true,
  SubzoneAssignmentSection: true,
  PendingConfigBanner: true,
  RangeSlider: true,
}

function baseConfig(overrides: Partial<SensorConfigResponse> = {}): SensorConfigResponse {
  return {
    id: 'cfg-1',
    esp_id: 'ESP_AEAE64',
    gpio: 34,
    sensor_type: 'ph',
    name: 'pH Tank',
    enabled: true,
    interval_ms: 30000,
    processing_mode: 'pi_enhanced',
    calibration: null,
    threshold_min: null,
    threshold_max: null,
    warning_min: null,
    warning_max: null,
    metadata: null,
    device_scope: 'zone_local',
    assigned_zones: null,
    created_at: '2026-08-25T10:00:00.000Z',
    updated_at: '2026-08-25T10:00:00.000Z',
    mount_height_cm: null,
    mount_medium: null,
    mount_angle_deg: null,
    ...overrides,
  }
}

async function mountPanel(
  config: SensorConfigResponse = baseConfig(),
  props: { activeTab?: string; sensorType?: string; gpio?: number; configId?: string } = {},
) {
  vi.mocked(sensorsApi.getByConfigId).mockResolvedValue(config)
  vi.mocked(sensorsApi.get).mockResolvedValue(config)
  const wrapper = mount(SensorConfigPanel, {
    props: {
      espId: 'ESP_AEAE64',
      gpio: props.gpio ?? 34,
      sensorType: props.sensorType ?? 'ph',
      configId: props.configId ?? 'cfg-1',
      activeTab: props.activeTab ?? 'grundlagen',
    },
    global: { plugins: [createPinia()], stubs: globalStubs },
  })
  await flushPromises()
  return wrapper
}

function assertNoExtraAddresses(text: string): void {
  expect(text).not.toContain('GPIO')
  expect(text).not.toContain('ESP_AEAE64')
  expect(text).not.toContain('cfg-1')
  expect(text).not.toMatch(/\/monitor\//)
  expect(text).not.toContain('measurement_role')
}

describe('<SensorConfigPanel> identity (AUT-1514)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should show a human word and hide gpio/chip/URL in Grundlagen', async () => {
    const wrapper = await mountPanel()

    const nameField = wrapper.findAll('.sensor-config__field').find((field) =>
      field.find('.sensor-config__label').text() === 'Name',
    )
    expect(nameField).toBeDefined()
    expect((nameField!.find('input').element as HTMLInputElement).value).toBe('pH Tank')
    expect(wrapper.text()).toContain('Zelt A')
    expect(wrapper.get('.settings-breadcrumb').text()).toContain('Zelt A')
    expect(wrapper.get('.settings-breadcrumb').text()).not.toContain('GPIO')
    expect(wrapper.get('.settings-breadcrumb').text()).not.toContain('ESP_')
    assertNoExtraAddresses(wrapper.text())
  })

  it('should not repeat GPIO as a second address on the Hardware tab', async () => {
    const wrapper = await mountPanel(baseConfig(), { activeTab: 'hardware' })

    expect(wrapper.text()).toContain('Board: ESP32-WROOM-32')
    expect(wrapper.text()).not.toContain('GPIO Pin')
    expect(wrapper.text()).not.toContain('GPIO 34')
    expect(wrapper.text()).not.toContain('gpio=0')
    assertNoExtraAddresses(wrapper.text())
  })

  it('should not show gpio=0 as the SHT31 measurement address', async () => {
    const wrapper = await mountPanel(
      baseConfig({
        id: 'cfg-temp',
        gpio: 0,
        sensor_type: 'sht31_temp',
        name: 'Luft',
      }),
      { activeTab: 'hardware', sensorType: 'sht31_temp', gpio: 0, configId: 'cfg-temp' },
    )

    expect(wrapper.text()).not.toContain('GPIO 0')
    expect(wrapper.text()).not.toContain('GPIO Pin')
    expect(wrapper.text()).not.toContain('cfg-temp')
    expect(wrapper.text()).not.toContain('sht31_temp')
  })
})
