/**
 * AddActuatorModal Component Tests
 *
 * Covers:
 * - Basic rendering (open/closed)
 * - Actuator type dropdown with all types (relay, pump, valve, pwm)
 * - Name input field
 * - GPIO validation via @validation-change enabling/disabling "Hinzufügen" button
 * - Conditional fields: PWM slider, max runtime, cooldown, inverted logic, aux GPIO
 * - initialActuatorType pre-selection from drag-and-drop
 * - Form reset on modal open
 * - addActuator call and emit on submit
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount, VueWrapper } from '@vue/test-utils'
import { nextTick, defineComponent, h } from 'vue'
import AddActuatorModal from '@/components/esp/AddActuatorModal.vue'

// ── Mocks ──────────────────────────────────────────────────────────────

const mockAddActuator = vi.fn().mockResolvedValue(undefined)
const mockFetchGpioStatus = vi.fn()

vi.mock('@/stores/esp', () => ({
  useEspStore: () => ({
    devices: [],
    getDeviceId: (d: any) => d.device_id || '',
    isMock: () => true,
    addActuator: mockAddActuator,
    fetchGpioStatus: mockFetchGpioStatus,
    fetchDevice: vi.fn(),
  }),
}))

const mockToastSuccess = vi.fn()
const mockToastError = vi.fn()

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    success: mockToastSuccess,
    error: mockToastError,
    warning: vi.fn(),
    info: vi.fn(),
  }),
}))

vi.mock('@/utils/logger', () => ({
  createLogger: () => ({
    debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn(),
  }),
}))

// ── GpioPicker Stub ────────────────────────────────────────────────────
// Emits 'validation-change' on mount with valid=true to simulate a selected GPIO pin.
// This is the critical behavior that was broken before the fix.

const GpioPickerStub = defineComponent({
  name: 'GpioPicker',
  props: {
    modelValue: { type: Number, default: 0 },
    espId: { type: String, default: '' },
    actuatorType: { type: String, default: '' },
    sensorType: { type: String, default: '' },
    variant: { type: String, default: 'dropdown' },
    disabled: { type: Boolean, default: false },
  },
  emits: ['update:modelValue', 'validation-change'],
  setup(_props, { emit }) {
    // Emit valid by default (simulates a mock ESP where any GPIO is valid)
    emit('validation-change', true, null)
    return () => h('div', { class: 'gpio-picker-stub' }, 'GPIO Picker')
  },
})

// GpioPicker stub that stays invalid (does NOT emit validation-change)
const GpioPickerInvalidStub = defineComponent({
  name: 'GpioPicker',
  props: {
    modelValue: { type: Number, default: 0 },
    espId: { type: String, default: '' },
    actuatorType: { type: String, default: '' },
    sensorType: { type: String, default: '' },
    variant: { type: String, default: 'dropdown' },
    disabled: { type: Boolean, default: false },
  },
  emits: ['update:modelValue', 'validation-change'],
  setup(_props, { emit }) {
    // Emit invalid
    emit('validation-change', false, 'No GPIO selected')
    return () => h('div', { class: 'gpio-picker-stub' }, 'GPIO Picker')
  },
})

// ── Helpers ────────────────────────────────────────────────────────────

function mountModal(
  propsOverrides: Record<string, unknown> = {},
  gpioStub: any = GpioPickerStub,
) {
  return mount(AddActuatorModal, {
    props: { modelValue: true, espId: 'ESP_MOCK_001', ...propsOverrides },
    global: {
      plugins: [createPinia()],
      stubs: { Teleport: true, GpioPicker: gpioStub },
    },
  })
}

function findAddButton(wrapper: VueWrapper): VueWrapper | undefined {
  return wrapper.findAll('button').find(b => b.text().includes('Hinzufügen'))
}

function findCancelButton(wrapper: VueWrapper): VueWrapper | undefined {
  return wrapper.findAll('button').find(b => b.text().includes('Abbrechen'))
}

// ── Tests ──────────────────────────────────────────────────────────────

describe('AddActuatorModal', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  // ── Rendering ─────────────────────────────────────────────────────

  describe('rendering', () => {
    it('does not render when modelValue is false', () => {
      const wrapper = mount(AddActuatorModal, {
        props: { modelValue: false, espId: 'ESP_001' },
        global: { plugins: [createPinia()], stubs: { Teleport: true, GpioPicker: true } },
      })
      expect(wrapper.find('.modal-overlay').exists()).toBe(false)
    })

    it('renders title when modelValue is true', () => {
      const wrapper = mountModal()
      expect(wrapper.text()).toContain('Aktor hinzufügen')
    })

    it('shows actuator type dropdown with all types', () => {
      const wrapper = mountModal()
      const select = wrapper.find('select')
      expect(select.exists()).toBe(true)
      const options = select.findAll('option')
      const labels = options.map(o => o.text())
      expect(labels).toContain('Relais')
      expect(labels).toContain('Pumpe')
      expect(labels).toContain('Ventil')
      expect(labels).toContain('PWM')
    })

    it('shows name input field', () => {
      const wrapper = mountModal()
      expect(wrapper.text()).toContain('Name')
      const input = wrapper.find('input[type="text"]')
      expect(input.exists()).toBe(true)
      expect(input.attributes('placeholder')).toContain('Wasserpumpe')
    })

    it('has Hinzufügen and Abbrechen buttons', () => {
      const wrapper = mountModal()
      expect(findAddButton(wrapper)).toBeDefined()
      expect(findCancelButton(wrapper)).toBeDefined()
    })
  })

  // ── GPIO Validation → Button Enable/Disable ──────────────────────
  // This is the CRITICAL test section for the @validation-change fix

  describe('GPIO validation (bug fix verification)', () => {
    it('enables Hinzufügen button when GpioPicker emits validation-change(true)', async () => {
      const wrapper = mountModal({}, GpioPickerStub)
      await nextTick()

      const addBtn = findAddButton(wrapper)
      expect(addBtn).toBeDefined()
      // Button should NOT be disabled because GpioPickerStub emits valid=true
      expect(addBtn!.attributes('disabled')).toBeUndefined()
    })

    it('disables Hinzufügen button when GpioPicker emits validation-change(false)', async () => {
      const wrapper = mountModal({}, GpioPickerInvalidStub)
      await nextTick()

      const addBtn = findAddButton(wrapper)
      expect(addBtn).toBeDefined()
      // Button should be disabled because GpioPickerInvalidStub emits valid=false
      expect(addBtn!.attributes('disabled')).toBeDefined()
    })

    it('button starts disabled with default GpioPicker stub (no validation event)', async () => {
      // Use a bare stub that emits nothing — simulates the OLD broken behavior
      const wrapper = mount(AddActuatorModal, {
        props: { modelValue: true, espId: 'ESP_001' },
        global: { plugins: [createPinia()], stubs: { Teleport: true, GpioPicker: true } },
      })
      await nextTick()

      const addBtn = findAddButton(wrapper)
      expect(addBtn).toBeDefined()
      // With no validation event, button should remain disabled (actuatorGpioValid=false)
      expect(addBtn!.attributes('disabled')).toBeDefined()
    })
  })

  // ── Close / Cancel ────────────────────────────────────────────────

  describe('close and cancel', () => {
    it('emits update:modelValue(false) on close button', async () => {
      const wrapper = mountModal()
      await wrapper.find('.modal-close-btn').trigger('click')
      expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([false])
    })

    it('emits update:modelValue(false) on cancel button', async () => {
      const wrapper = mountModal()
      const cancelBtn = findCancelButton(wrapper)
      expect(cancelBtn).toBeDefined()
      await cancelBtn!.trigger('click')
      expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([false])
    })
  })

  // ── Conditional Fields ────────────────────────────────────────────

  describe('conditional fields per actuator type', () => {
    it('shows inverted logic checkbox for relay type (default)', () => {
      const wrapper = mountModal()
      expect(wrapper.text()).toContain('Invertierte Logik')
    })

    it('shows PWM slider when type is pwm', async () => {
      const wrapper = mountModal()
      await wrapper.find('select').setValue('pwm')
      await nextTick()
      expect(wrapper.text()).toContain('PWM-Wert')
      expect(wrapper.find('input[type="range"]').exists()).toBe(true)
    })

    it('does NOT show PWM slider for relay type', () => {
      const wrapper = mountModal()
      expect(wrapper.find('input[type="range"]').exists()).toBe(false)
    })

    it('shows max runtime and cooldown for pump type', async () => {
      const wrapper = mountModal()
      await wrapper.find('select').setValue('pump')
      await nextTick()
      expect(wrapper.text()).toContain('Sicherheitslimit')
      expect(wrapper.text()).toContain('Cooldown')
    })

    it('does NOT show max runtime/cooldown for relay type', () => {
      const wrapper = mountModal()
      expect(wrapper.text()).not.toContain('Max. Laufzeit')
      expect(wrapper.text()).not.toContain('Cooldown')
    })

    it('does NOT show inverted logic for pwm type', async () => {
      const wrapper = mountModal()
      await wrapper.find('select').setValue('pwm')
      await nextTick()
      expect(wrapper.text()).not.toContain('Invertierte Logik')
    })
  })

  // ── Add Actuator Submission ───────────────────────────────────────

  describe('add actuator submission', () => {
    it('calls espStore.addActuator on submit', async () => {
      const wrapper = mountModal({}, GpioPickerStub)
      await nextTick()

      const addBtn = findAddButton(wrapper)
      await addBtn!.trigger('click')
      await nextTick()

      expect(mockAddActuator).toHaveBeenCalledWith('ESP_MOCK_001', expect.objectContaining({
        actuator_type: 'relay',
        gpio: 0,
      }))
    })

    it('shows success toast after adding', async () => {
      const wrapper = mountModal({}, GpioPickerStub)
      await nextTick()

      const addBtn = findAddButton(wrapper)
      await addBtn!.trigger('click')
      await nextTick()

      expect(mockToastSuccess).toHaveBeenCalledWith('Aktor erfolgreich hinzugefügt')
    })

    it('emits added event after successful add', async () => {
      const wrapper = mountModal({}, GpioPickerStub)
      await nextTick()

      const addBtn = findAddButton(wrapper)
      await addBtn!.trigger('click')
      await nextTick()

      expect(wrapper.emitted('added')).toBeTruthy()
    })

    it('closes modal after successful add', async () => {
      const wrapper = mountModal({}, GpioPickerStub)
      await nextTick()

      const addBtn = findAddButton(wrapper)
      await addBtn!.trigger('click')
      await nextTick()

      expect(wrapper.emitted('update:modelValue')).toBeTruthy()
      const closeEvents = wrapper.emitted('update:modelValue')!
      expect(closeEvents[closeEvents.length - 1]).toEqual([false])
    })

    it('fetches GPIO status after adding', async () => {
      const wrapper = mountModal({}, GpioPickerStub)
      await nextTick()

      const addBtn = findAddButton(wrapper)
      await addBtn!.trigger('click')
      await nextTick()

      expect(mockFetchGpioStatus).toHaveBeenCalledWith('ESP_MOCK_001')
    })
  })

  // ── initialActuatorType (Drag & Drop) ─────────────────────────────

  describe('initialActuatorType from drag and drop', () => {
    // The watcher only fires on modelValue CHANGE, so we must mount closed then open.

    it('pre-selects actuator type when modal opens with initialActuatorType', async () => {
      const wrapper = mountModal({ modelValue: false, initialActuatorType: 'pump' })
      await wrapper.setProps({ modelValue: true })
      await nextTick()

      const select = wrapper.find('select')
      expect((select.element as HTMLSelectElement).value).toBe('pump')
    })

    it('shows pump-specific fields when pre-selected via drag', async () => {
      const wrapper = mountModal({ modelValue: false, initialActuatorType: 'pump' })
      await wrapper.setProps({ modelValue: true })
      await nextTick()

      expect(wrapper.text()).toContain('Sicherheitslimit')
      expect(wrapper.text()).toContain('Cooldown')
    })

    it('ignores unknown actuator type gracefully', async () => {
      const wrapper = mountModal({ modelValue: false, initialActuatorType: 'unknown_type' })
      await wrapper.setProps({ modelValue: true })
      await nextTick()

      // Should fall back to default (relay)
      const select = wrapper.find('select')
      expect((select.element as HTMLSelectElement).value).toBe('relay')
    })

    it('is case-insensitive for type matching', async () => {
      const wrapper = mountModal({ modelValue: false, initialActuatorType: 'PUMP' })
      await wrapper.setProps({ modelValue: true })
      await nextTick()

      const select = wrapper.find('select')
      expect((select.element as HTMLSelectElement).value).toBe('pump')
    })
  })
})
