/**
 * Tests for CommandPalette component accessibility and rendering.
 * Verifies ARIA attributes, keyboard navigation hints, search input.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import CommandPalette from '@/components/command/CommandPalette.vue'
import { useCommandPalette } from '@/composables/useCommandPalette'

// Mock uiStore
const mockUiStore = {
  commandPaletteOpen: true,
  closeCommandPalette: vi.fn(),
}

vi.mock('@/shared/stores', () => ({
  useUiStore: () => mockUiStore,
}))

function mountPalette(open = true) {
  mockUiStore.commandPaletteOpen = open
  return mount(CommandPalette, {
    attachTo: document.body,
  })
}

describe('CommandPalette', () => {
  beforeEach(() => {
    const palette = useCommandPalette()
    palette.unregisterByPrefix('test:')
    palette.resetQuery()
    mockUiStore.closeCommandPalette.mockClear()
  })

  it('renders listbox with aria-label when open', () => {
    const palette = useCommandPalette()
    palette.registerCommands([{
      id: 'test:1',
      label: 'Test',
      category: 'actions',
      action: () => {},
    }])

    const wrapper = mountPalette()
    const listbox = wrapper.find('[role="listbox"]')
    expect(listbox.exists()).toBe(true)
    expect(listbox.attributes('aria-label')).toBe('Suchergebnisse')
    wrapper.unmount()
  })

  it('renders search input with placeholder', () => {
    const wrapper = mountPalette()
    const input = wrapper.find('input[type="text"]')
    expect(input.exists()).toBe(true)
    expect(input.attributes('placeholder')).toContain('Suche')
    wrapper.unmount()
  })

  it('renders keyboard navigation hints in footer', () => {
    const wrapper = mountPalette()
    expect(wrapper.text()).toContain('Navigieren')
    expect(wrapper.text()).toContain('Auswählen')
    expect(wrapper.text()).toContain('Schließen')
    wrapper.unmount()
  })

  it('does not render content when closed', () => {
    const wrapper = mountPalette(false)
    expect(wrapper.find('[role="listbox"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('renders Esc kbd hint', () => {
    const wrapper = mountPalette()
    expect(wrapper.text()).toContain('Esc')
    wrapper.unmount()
  })
})
