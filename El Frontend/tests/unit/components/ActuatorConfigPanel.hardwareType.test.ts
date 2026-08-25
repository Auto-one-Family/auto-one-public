/**
 * ActuatorConfigPanel — hardware_type classification regression (AUT-997 / AUT-999)
 *
 * Bug: HardwareView.vue:949 seeds the edit panel from the generic `actuator_type`
 * ("digital") instead of the semantic `hardware_type` ("pump"). The panel's
 * `isRelay` computed matches 'digital', so an existing pump is misclassified as a
 * relay — `isPump=false` — and the pump-only fields (esp. the AO-1/AUT-990
 * `flow_rate_ml_s` calibration) never render.
 *
 * This test pins the DOM contract at the ActuatorConfigPanel boundary:
 *   - actuator-type="digital" (pre-fix input)  -> pump calibration field ABSENT
 *   - actuator-type="pump"    (post-fix input) -> pump calibration field PRESENT
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import ActuatorConfigPanel from '@/components/esp/ActuatorConfigPanel.vue'

const CALIBRATION_LABEL = 'Gemessene Pumpen-Fördermenge'

// --- API mocks (onMounted calls actuatorsApi.get; template binds several fns) ---
vi.mock('@/api/actuators', () => ({
  actuatorsApi: {
    get: vi.fn(async () => null),
    createOrUpdate: vi.fn(),
    delete: vi.fn(),
    emergencyStop: vi.fn(),
    getAlertConfig: vi.fn(),
    updateAlertConfig: vi.fn(),
    getRuntime: vi.fn(),
  },
}))
vi.mock('@/api/esp', () => ({
  espApi: { isMockEsp: () => false },
}))
vi.mock('@/api/device-context', () => ({
  deviceContextApi: { get: vi.fn(async () => null) },
}))

// --- store mocks (plain objects, no real Pinia state needed) ---
vi.mock('@/stores/esp', () => ({
  useEspStore: () => ({
    devices: [{ device_id: 'ESP_AEAE64', domain: 'luft', zone_id: 'z1' }],
    getDeviceId: (d: { device_id?: string }) => d?.device_id || '',
    sendActuatorCommand: vi.fn(),
    emergencyStop: vi.fn(),
  }),
}))
vi.mock('@/shared/stores/ui.store', () => ({
  useUiStore: () => ({ confirm: vi.fn(async () => false) }),
}))
vi.mock('@/shared/stores/zone.store', () => ({
  useZoneStore: () => ({
    zoneEntities: [
      { zone_id: 'z1', name: 'Zelt A', status: 'active' },
      { zone_id: 'z2', name: 'Archiv', status: 'archived' },
    ],
    fetchZoneEntities: vi.fn(async () => {}),
  }),
}))
vi.mock('@/shared/stores/actuator.store', () => ({
  useActuatorStore: () => ({
    registerConfigIntentFromRest: vi.fn(),
    waitForConfigTerminal: vi.fn(async () => null),
  }),
}))
vi.mock('@/shared/stores/logic.store', () => ({
  useLogicStore: () => ({
    rules: [],
    fetchRules: vi.fn(async () => {}),
    getRulesForActuator: () => [],
  }),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}))
vi.mock('@/composables/useGpioStatus', () => ({
  useGpioStatus: () => ({ gpioStatus: { value: null }, refresh: vi.fn() }),
}))
vi.mock('@/utils/logger', () => ({
  createLogger: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
}))

// Child components stubbed; AccordionSection must render its default slot so the
// type-specific fields (incl. the pump calibration input) are reachable in the DOM.
const globalStubs = {
  AccordionSection: { template: '<div><slot /></div>' },
  AlertConfigSection: true,
  RuntimeMaintenanceSection: true,
  DeviceMetadataSection: true,
  LinkedRulesSection: true,
  ActuatorActionTimeline: true,
  SubzoneAssignmentSection: true,
  SettingsBreadcrumb: true,
  PendingConfigBanner: true,
  RouterLink: { template: '<a><slot /></a>' },
}

async function mountPanel(actuatorType: string, activeTab = 'grundlagen') {
  const wrapper = mount(ActuatorConfigPanel, {
    props: { espId: 'ESP_AEAE64', gpio: 26, actuatorType, activeTab },
    global: { plugins: [createPinia()], stubs: globalStubs },
  })
  await flushPromises()
  return wrapper
}

describe('ActuatorConfigPanel — hardware_type classification (AUT-999)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('actuator-type "digital" (pre-fix seed) misclassifies pump → calibration field ABSENT', async () => {
    const wrapper = await mountPanel('digital')
    // AUT-1302: type select keeps the legacy token selectable when not in options.
    expect(wrapper.get('[data-testid="actuator-config-type-select"]').element).toBeTruthy()
    expect((wrapper.get('[data-testid="actuator-config-type-select"]').element as HTMLSelectElement).value).toBe('digital')
    // Pump-only calibration field must NOT be in the DOM (isPump=false, isRelay=true).
    expect(wrapper.text()).not.toContain(CALIBRATION_LABEL)
  })

  it('actuator-type "pump" (post-fix seed) classifies pump → calibration field PRESENT', async () => {
    const wrapper = await mountPanel('pump')
    expect((wrapper.get('[data-testid="actuator-config-type-select"]').element as HTMLSelectElement).value).toBe('pump')
    // Pump-only calibration field (flow_rate_ml_s, AO-1/AUT-990) must render.
    expect(wrapper.text()).toContain(CALIBRATION_LABEL)
  })

  it('should allow changing type away from pump and hide calibration (AUT-1302)', async () => {
    const wrapper = await mountPanel('pump')
    const select = wrapper.get('[data-testid="actuator-config-type-select"]')
    await select.setValue('relay')
    await flushPromises()
    expect(wrapper.text()).not.toContain(CALIBRATION_LABEL)
  })

  it('actuator-type "pump" exposes the inverted-logic toggle (relay-driven pumps, AUT-997 follow-up)', async () => {
    const wrapper = await mountPanel('pump')
    // Pumps driven via a relay module need the same inverted-logic control as a relay.
    expect(wrapper.text()).toContain('Invertierte Logik (LOW = ON)')
    const toggle = wrapper.get('button[role="switch"][aria-label="Invertierte Logik"]')
    expect(toggle.attributes('aria-checked')).toBe('false')
    await toggle.trigger('click')
    expect(toggle.attributes('aria-checked')).toBe('true')
  })
})

describe('ActuatorConfigPanel — existing fields in one surface (AUT-1535 / AUT-1523)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should show report domain and keep a single name input', async () => {
    const wrapper = await mountPanel('pump')
    expect(wrapper.text()).toContain('Auswertungs-Domäne: Luft')
    expect(wrapper.findAll('[data-testid="actuator-config-name"]')).toHaveLength(1)
    expect(wrapper.text()).not.toMatch(/\bFunktion\b/)
    expect(wrapper.findComponent({ name: 'DeviceScopeSection' }).exists()).toBe(false)
  })

  it('should keep dose_role on pump and expose localScope without DeviceScopeSection', async () => {
    const wrapper = await mountPanel('pump')
    expect(wrapper.get('#actuator-dose-role').exists()).toBe(true)
    const scope = wrapper.get('[data-testid="actuator-config-device-scope-select"]')
    expect((scope.element as HTMLSelectElement).value).toBe('zone_local')
    expect(wrapper.find('[data-testid="actuator-config-assigned-zones"]').exists()).toBe(false)
    await scope.setValue('multi_zone')
    await flushPromises()
    expect(wrapper.get('[data-testid="actuator-config-assigned-zones"]').text()).toContain('Zelt A')
    expect(wrapper.get('[data-testid="actuator-config-assigned-zones"]').text()).not.toContain('Archiv')
  })
})
