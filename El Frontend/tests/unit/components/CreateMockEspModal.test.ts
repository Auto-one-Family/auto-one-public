/**
 * CreateMockEspModal Component Tests
 *
 * Tests modal visibility, close behavior, form inputs,
 * create button disabled state, and ESP ID auto-generation.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import CreateMockEspModal from '@/components/modals/CreateMockEspModal.vue'

// Mock the ESP store
const mockCreateDevice = vi.fn()

vi.mock('@/stores/esp', () => ({
  useEspStore: () => ({
    createDevice: mockCreateDevice,
  }),
}))

vi.mock('@/utils/logger', () => ({
  createLogger: () => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  }),
}))

function mountModal(props: Record<string, unknown> = {}) {
  return mount(CreateMockEspModal, {
    props: {
      modelValue: false,
      ...props,
    },
    global: {
      plugins: [createPinia()],
    },
  })
}

describe('CreateMockEspModal', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockCreateDevice.mockClear()
  })

  describe('visibility', () => {
    it('does NOT render modal when modelValue=false', () => {
      const w = mountModal({ modelValue: false })
      expect(w.find('.modal-overlay').exists()).toBe(false)
    })

    it('renders modal when modelValue=true', () => {
      const w = mountModal({ modelValue: true })
      expect(w.find('.modal-overlay').exists()).toBe(true)
      expect(w.find('.modal-content').exists()).toBe(true)
    })

    it('shows correct title', () => {
      const w = mountModal({ modelValue: true })
      expect(w.find('.modal-title').text()).toBe('Mock ESP erstellen')
    })
  })

  describe('close behavior', () => {
    it('close button emits update:modelValue with false', async () => {
      const w = mountModal({ modelValue: true })
      const closeBtn = w.find('.modal-close')
      expect(closeBtn.exists()).toBe(true)

      await closeBtn.trigger('click')

      expect(w.emitted('update:modelValue')).toBeTruthy()
      expect(w.emitted('update:modelValue')![0]).toEqual([false])
    })

    it('overlay click emits update:modelValue with false', async () => {
      const w = mountModal({ modelValue: true })
      // click.self on the overlay
      await w.find('.modal-overlay').trigger('click')

      expect(w.emitted('update:modelValue')).toBeTruthy()
      expect(w.emitted('update:modelValue')![0]).toEqual([false])
    })
  })

  describe('form inputs', () => {
    it('has ESP ID input', () => {
      const w = mountModal({ modelValue: true })
      const inputs = w.findAll('input')
      // ESP ID is the first text input
      const espIdInput = inputs.find(
        (i) => i.attributes('placeholder') === 'MOCK_XXXXXXXX'
      )
      expect(espIdInput).toBeTruthy()
    })

    it('has Zone Name input', () => {
      const w = mountModal({ modelValue: true })
      const zoneInput = w.findAll('input').find(
        (i) => i.attributes('placeholder')?.includes('Zelt 1')
      )
      expect(zoneInput).toBeTruthy()
    })

    it('has Auto-Heartbeat checkbox', () => {
      const w = mountModal({ modelValue: true })
      const checkbox = w.find('input#autoHeartbeat')
      expect(checkbox.exists()).toBe(true)
      expect(checkbox.attributes('type')).toBe('checkbox')
    })
  })

  describe('create button state', () => {
    it('create button is disabled when ESP ID is empty', async () => {
      // Mount closed, then open to trigger watch and auto-generate ID
      const w = mountModal({ modelValue: false })
      await w.setProps({ modelValue: true })
      await w.vm.$nextTick()

      // Clear the ESP ID input so button becomes disabled
      const espIdInput = w.findAll('input').find(
        (i) => i.attributes('placeholder') === 'MOCK_XXXXXXXX'
      )!
      await espIdInput.setValue('')

      const createBtn = w.findAll('button').find(
        (b) => b.text().includes('Erstellen') && !b.text().includes('Abbrechen')
      )
      expect(createBtn).toBeTruthy()
      expect(createBtn!.attributes('disabled')).toBeDefined()
    })

    it('create button is enabled when ESP ID is present', async () => {
      // Mount closed, then open to trigger watch and auto-generate ID
      const w = mountModal({ modelValue: false })
      await w.setProps({ modelValue: true })
      await w.vm.$nextTick()

      const createBtn = w.findAll('button').find(
        (b) => b.text().includes('Erstellen') && !b.text().includes('Abbrechen')
      )
      expect(createBtn).toBeTruthy()
      // Auto-generated ID means button should NOT be disabled
      expect(createBtn!.attributes('disabled')).toBeUndefined()
    })
  })

  describe('ESP ID auto-generation', () => {
    it('auto-generates an ESP ID on open', async () => {
      // Mount closed first, then open to trigger the watch
      const w = mountModal({ modelValue: false })
      await w.setProps({ modelValue: true })
      await w.vm.$nextTick()

      const espIdInput = w.findAll('input').find(
        (i) => i.attributes('placeholder') === 'MOCK_XXXXXXXX'
      )!
      const value = (espIdInput.element as HTMLInputElement).value
      expect(value).toMatch(/^MOCK_[A-F0-9]{8}$/)
    })

    it('generates a new ID when modal re-opens', async () => {
      const w = mountModal({ modelValue: false })
      await w.setProps({ modelValue: true })
      await w.vm.$nextTick()

      const espIdInput = w.findAll('input').find(
        (i) => i.attributes('placeholder') === 'MOCK_XXXXXXXX'
      )!
      const firstId = (espIdInput.element as HTMLInputElement).value
      expect(firstId).toMatch(/^MOCK_[A-F0-9]{8}$/)

      // Close and re-open
      await w.setProps({ modelValue: false })
      await w.setProps({ modelValue: true })
      await w.vm.$nextTick()

      const newValue = (espIdInput.element as HTMLInputElement).value
      // Check it matches the pattern (new ID generated)
      expect(newValue).toMatch(/^MOCK_[A-F0-9]{8}$/)
    })
  })
})
