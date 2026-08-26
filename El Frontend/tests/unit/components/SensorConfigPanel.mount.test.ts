/**
 * SensorConfigPanel — Montagefelder im bestehenden Grundlagen-Tab (AUT-1556)
 *
 * Pins the DOM + save contract at the existing panel:
 *   - Höhe / Medium / Winkel sitzen neben Subzone + device_scope
 *   - Leere Werte bleiben gültig (null im bestehenden createOrUpdate)
 *   - Kein zweites Fenster, device_scope bleibt Zonen-Reichweite
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import SensorConfigPanel from '@/components/esp/SensorConfigPanel.vue'
import type { SensorConfigCreate, SensorConfigResponse } from '@/types'
import { sensorsApi } from '@/api/sensors'

const createOrUpdate = vi.fn(async (_espId: string, _gpio: number, config: SensorConfigCreate) => ({
  id: 'cfg-1',
  ...config,
}))

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
    devices: [{ device_id: 'ESP_AEAE64', name: 'Test-ESP', zone_id: 'z1', zone_name: 'Zelt A' }],
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
    layout: { value: null },
    normalizedType: { value: 'ESP32_WROOM' },
    isKnownBoard: { value: true },
    i2cDefaultLabel: { value: 'SDA 21 / SCL 22' },
    isReserved: () => false,
    isSafe: () => true,
    adc1Pins: { value: [32, 33, 34, 35, 36, 39] },
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
  SettingsBreadcrumb: true,
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

async function mountPanel(config: SensorConfigResponse = baseConfig()) {
  vi.mocked(sensorsApi.getByConfigId).mockResolvedValue(config)
  vi.mocked(sensorsApi.get).mockResolvedValue(config)
  vi.mocked(sensorsApi.createOrUpdate).mockImplementation(createOrUpdate)
  const wrapper = mount(SensorConfigPanel, {
    props: {
      espId: 'ESP_AEAE64',
      gpio: 34,
      sensorType: 'ph',
      configId: 'cfg-1',
      activeTab: 'grundlagen',
    },
    global: { plugins: [createPinia()], stubs: globalStubs },
  })
  await flushPromises()
  return wrapper
}

describe('<SensorConfigPanel> mount geometry (AUT-1556)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    createOrUpdate.mockClear()
  })

  it('should show height, medium and angle next to device_scope in Grundlagen', async () => {
    const wrapper = await mountPanel()

    expect(wrapper.get('[data-testid="sensor-config-device-scope"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="sensor-config-mount-height"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="sensor-config-mount-angle"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="sensor-config-mount-medium-select"]').exists()).toBe(true)
    expect(wrapper.findAll('.sensor-config__tab-panel').length).toBeGreaterThan(0)
    expect(wrapper.find('[data-testid="sensor-config-device-scope-select"]').exists()).toBe(true)
  })

  it('should hydrate A1 fields from the existing config GET', async () => {
    const wrapper = await mountPanel(baseConfig({
      mount_height_cm: 120.5,
      mount_medium: 'canopy',
      mount_angle_deg: 45,
    }))

    expect((wrapper.get('[data-testid="sensor-config-mount-height"]').element as HTMLInputElement).value).toBe('120.5')
    expect((wrapper.get('[data-testid="sensor-config-mount-angle"]').element as HTMLInputElement).value).toBe('45')
    expect((wrapper.get('[data-testid="sensor-config-mount-medium-select"]').element as HTMLSelectElement).value).toBe('canopy')
  })

  it('should save empty mount fields as null through the existing createOrUpdate', async () => {
    const wrapper = await mountPanel()

    await wrapper.get('.sensor-config__save').trigger('click')
    await flushPromises()

    expect(createOrUpdate).toHaveBeenCalledTimes(1)
    const payload = createOrUpdate.mock.calls[0][2] as SensorConfigCreate
    expect(payload.mount_height_cm).toBeNull()
    expect(payload.mount_medium).toBeNull()
    expect(payload.mount_angle_deg).toBeNull()
    expect(payload.device_scope).toBe('zone_local')
  })

  it('should persist filled mount fields through the existing save', async () => {
    const wrapper = await mountPanel()

    await wrapper.get('[data-testid="sensor-config-mount-height"]').setValue(15)
    await wrapper.get('[data-testid="sensor-config-mount-angle"]').setValue(0)
    await wrapper.get('[data-testid="sensor-config-mount-medium-select"]').setValue('solution')
    await wrapper.get('.sensor-config__save').trigger('click')
    await flushPromises()

    const payload = createOrUpdate.mock.calls[0][2] as SensorConfigCreate
    expect(payload.mount_height_cm).toBe(15)
    expect(payload.mount_angle_deg).toBe(0)
    expect(payload.mount_medium).toBe('solution')
  })

  it('should hydrate 0° as 0 and keep it 0 on save', async () => {
    const wrapper = await mountPanel(baseConfig({
      mount_height_cm: 0,
      mount_medium: 'air',
      mount_angle_deg: 0,
    }))

    expect((wrapper.get('[data-testid="sensor-config-mount-height"]').element as HTMLInputElement).value).toBe('0')
    expect((wrapper.get('[data-testid="sensor-config-mount-angle"]').element as HTMLInputElement).value).toBe('0')

    await wrapper.get('.sensor-config__save').trigger('click')
    await flushPromises()

    const payload = createOrUpdate.mock.calls[0][2] as SensorConfigCreate
    expect(payload.mount_height_cm).toBe(0)
    expect(payload.mount_angle_deg).toBe(0)
    expect(payload.mount_medium).toBe('air')
  })
})
