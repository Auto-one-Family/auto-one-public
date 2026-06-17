/**
 * AccordionSection Component Tests
 *
 * Tests for the reusable expandable/collapsible section component.
 * Covers: toggle, modelValue prop (v-model), #header slot scope, storage-key persistence.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import AccordionSection from '@/shared/design/primitives/AccordionSection.vue'

// Spy on native localStorage (works with happy-dom and jsdom)
const getItemSpy = vi.spyOn(Storage.prototype, 'getItem')
const setItemSpy = vi.spyOn(Storage.prototype, 'setItem')

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
})

describe('AccordionSection', () => {
  describe('open/close toggle', () => {
    it('starts closed by default', () => {
      const wrapper = mount(AccordionSection, {
        props: { title: 'Test Section' },
      })
      expect(wrapper.find('.accordion--open').exists()).toBe(false)
      wrapper.unmount()
    })

    it('starts open when defaultOpen is true', () => {
      const wrapper = mount(AccordionSection, {
        props: { title: 'Test Section', defaultOpen: true },
      })
      expect(wrapper.find('.accordion--open').exists()).toBe(true)
      wrapper.unmount()
    })

    it('toggles open when trigger button is clicked', async () => {
      const wrapper = mount(AccordionSection, {
        props: { title: 'Test Section' },
      })
      expect(wrapper.find('.accordion--open').exists()).toBe(false)

      await wrapper.find('.accordion__trigger').trigger('click')
      expect(wrapper.find('.accordion--open').exists()).toBe(true)

      await wrapper.find('.accordion__trigger').trigger('click')
      expect(wrapper.find('.accordion--open').exists()).toBe(false)

      wrapper.unmount()
    })

    it('renders title text in the trigger button', () => {
      const wrapper = mount(AccordionSection, {
        props: { title: 'Meine Section' },
      })
      expect(wrapper.find('.accordion__title').text()).toBe('Meine Section')
      wrapper.unmount()
    })

    it('renders default slot content', () => {
      const wrapper = mount(AccordionSection, {
        props: { title: 'Test' },
        slots: { default: '<p class="test-content">Content</p>' },
      })
      expect(wrapper.find('.test-content').exists()).toBe(true)
      wrapper.unmount()
    })
  })

  describe('modelValue prop (v-model)', () => {
    it('uses modelValue when provided (open)', () => {
      const wrapper = mount(AccordionSection, {
        props: { title: 'Test', modelValue: true },
      })
      expect(wrapper.find('.accordion--open').exists()).toBe(true)
      wrapper.unmount()
    })

    it('uses modelValue when provided (closed)', () => {
      const wrapper = mount(AccordionSection, {
        props: { title: 'Test', modelValue: false },
      })
      expect(wrapper.find('.accordion--open').exists()).toBe(false)
      wrapper.unmount()
    })

    it('emits update:modelValue on toggle click', async () => {
      const wrapper = mount(AccordionSection, {
        props: { title: 'Test', modelValue: false },
      })
      await wrapper.find('.accordion__trigger').trigger('click')
      expect(wrapper.emitted('update:modelValue')).toBeTruthy()
      expect(wrapper.emitted('update:modelValue')![0]).toEqual([true])
      wrapper.unmount()
    })

    it('emits false when toggling open -> closed', async () => {
      const wrapper = mount(AccordionSection, {
        props: { title: 'Test', modelValue: true },
      })
      await wrapper.find('.accordion__trigger').trigger('click')
      expect(wrapper.emitted('update:modelValue')![0]).toEqual([false])
      wrapper.unmount()
    })
  })

  describe('#header slot with scope', () => {
    it('provides isOpen and toggle via #header slot scope', async () => {
      let slotIsOpen: boolean | undefined
      let slotToggle: (() => void) | undefined

      const wrapper = mount(AccordionSection, {
        props: {},
        slots: {
          header: (scope: { isOpen: boolean; toggle: () => void }) => {
            slotIsOpen = scope.isOpen
            slotToggle = scope.toggle
            return `<div class="custom-header">Custom Header (open: ${scope.isOpen})</div>`
          },
        },
      })

      expect(slotIsOpen).toBe(false)
      expect(typeof slotToggle).toBe('function')

      wrapper.unmount()
    })

    it('hides default trigger when #header slot is used', () => {
      const wrapper = mount(AccordionSection, {
        props: { title: 'Should be hidden' },
        slots: {
          header: '<div class="custom-trigger">Custom</div>',
        },
      })
      // Default trigger should not render when #header slot is provided
      expect(wrapper.find('.accordion__trigger').exists()).toBe(false)
      expect(wrapper.find('.custom-trigger').exists()).toBe(true)
      wrapper.unmount()
    })
  })

  describe('storage-key localStorage persistence', () => {
    it('reads stored value on mount', async () => {
      localStorage.setItem('accordion:test-key', '1')

      const wrapper = mount(AccordionSection, {
        props: { title: 'Test', storageKey: 'test-key' },
      })
      await nextTick() // onMounted sets internalOpen, DOM needs tick to update

      expect(getItemSpy).toHaveBeenCalledWith('accordion:test-key')
      expect(wrapper.find('.accordion--open').exists()).toBe(true)
      wrapper.unmount()
    })

    it('reads stored "0" as closed', async () => {
      localStorage.setItem('accordion:test-key', '0')

      const wrapper = mount(AccordionSection, {
        props: { title: 'Test', storageKey: 'test-key', defaultOpen: true },
      })
      await nextTick() // onMounted overrides defaultOpen, DOM needs tick to update

      expect(wrapper.find('.accordion--open').exists()).toBe(false)
      wrapper.unmount()
    })

    it('persists state to localStorage on toggle', async () => {
      const wrapper = mount(AccordionSection, {
        props: { title: 'Test', storageKey: 'persist-key' },
      })

      await wrapper.find('.accordion__trigger').trigger('click')
      expect(setItemSpy).toHaveBeenCalledWith('accordion:persist-key', '1')

      await wrapper.find('.accordion__trigger').trigger('click')
      expect(setItemSpy).toHaveBeenCalledWith('accordion:persist-key', '0')

      wrapper.unmount()
    })

    it('does not read localStorage when modelValue is provided', () => {
      localStorage.setItem('accordion:mv-key', '1')

      const wrapper = mount(AccordionSection, {
        props: { title: 'Test', storageKey: 'mv-key', modelValue: false },
      })

      // Should stay closed because modelValue controls state
      expect(wrapper.find('.accordion--open').exists()).toBe(false)
      wrapper.unmount()
    })

    it('does not touch localStorage when no storageKey is provided', async () => {
      const wrapper = mount(AccordionSection, {
        props: { title: 'Test' },
      })

      await wrapper.find('.accordion__trigger').trigger('click')

      // setItem should not have been called with accordion: prefix by the component
      const calls = setItemSpy.mock.calls.filter(
        (call: unknown[]) => (call[0] as string).startsWith('accordion:')
      )
      expect(calls.length).toBe(0)

      wrapper.unmount()
    })
  })
})
