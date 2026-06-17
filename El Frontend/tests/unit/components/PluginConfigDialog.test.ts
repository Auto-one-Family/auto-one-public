/**
 * PluginConfigDialog Unit Tests
 *
 * Tests for dynamic config rendering: boolean, number, string, select fields.
 * Verifies label priority (label > description > key) and save behavior.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import PluginConfigDialog from '@/components/plugins/PluginConfigDialog.vue'

// =============================================================================
// Test Helpers
// =============================================================================

/**
 * Mount dialog with visible=false first, then set visible=true
 * to trigger the watch that syncs config into localConfig.
 */
async function mountDialog(props: Record<string, unknown> = {}) {
  const { visible: _ignored, ...restProps } = props
  const wrapper = mount(PluginConfigDialog, {
    props: {
      pluginId: 'test_plugin',
      pluginName: 'Test Plugin',
      config: {},
      configSchema: {},
      ...restProps,
      visible: false,
    },
    global: {
      stubs: {
        BaseModal: {
          template: '<div class="mock-modal"><slot /><slot name="footer" /></div>',
          props: ['open', 'title', 'maxWidth'],
        },
        Teleport: true,
      },
    },
  })

  // Open the dialog to trigger the watch that syncs config → localConfig
  await wrapper.setProps({ visible: true })

  return wrapper
}

// =============================================================================
// FIELD RENDERING
// =============================================================================

describe('PluginConfigDialog - Field Rendering', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders boolean fields as checkboxes', async () => {
    const wrapper = await mountDialog({
      configSchema: {
        dry_run: { type: 'boolean', default: false, label: 'Nur simulieren' },
      },
      config: { dry_run: false },
    })

    const checkbox = wrapper.find('input[type="checkbox"]')
    expect(checkbox.exists()).toBe(true)
  })

  it('renders number/integer fields as number inputs', async () => {
    const wrapper = await mountDialog({
      configSchema: {
        max_age: { type: 'integer', default: 30, label: 'Max Alter' },
      },
      config: { max_age: 30 },
    })

    const input = wrapper.find('input[type="number"]')
    expect(input.exists()).toBe(true)
    expect(input.element.value).toBe('30')
  })

  it('renders string fields as text inputs', async () => {
    const wrapper = await mountDialog({
      configSchema: {
        name: { type: 'string', default: 'default', label: 'Name' },
      },
      config: { name: 'custom' },
    })

    const input = wrapper.find('input[type="text"]')
    expect(input.exists()).toBe(true)
    expect(input.element.value).toBe('custom')
  })

  it('renders select fields as dropdowns', async () => {
    const wrapper = await mountDialog({
      configSchema: {
        device_mode: {
          type: 'select',
          options: ['mock', 'real', 'hybrid'],
          default: 'mock',
          label: 'Geräte-Modus',
        },
      },
      config: { device_mode: 'mock' },
    })

    const select = wrapper.find('select')
    expect(select.exists()).toBe(true)

    const options = select.findAll('option')
    expect(options).toHaveLength(3)
    expect(options[0].text()).toBe('mock')
    expect(options[1].text()).toBe('real')
    expect(options[2].text()).toBe('hybrid')
  })

  it('shows empty state when no schema provided', async () => {
    const wrapper = await mountDialog({
      configSchema: {},
      config: {},
    })

    expect(wrapper.text()).toContain('Keine konfigurierbaren Parameter')
  })
})

// =============================================================================
// LABEL PRIORITY
// =============================================================================

describe('PluginConfigDialog - Label Priority', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('uses label field as primary label text', async () => {
    const wrapper = await mountDialog({
      configSchema: {
        my_field: {
          type: 'boolean',
          label: 'Mein Label',
          description: 'Eine Beschreibung',
          default: false,
        },
      },
      config: { my_field: false },
    })

    const label = wrapper.find('.config-dialog__label')
    expect(label.text()).toContain('Mein Label')
  })

  it('falls back to description when label is missing', async () => {
    const wrapper = await mountDialog({
      configSchema: {
        my_field: {
          type: 'boolean',
          description: 'Beschreibung als Label',
          default: false,
        },
      },
      config: { my_field: false },
    })

    const label = wrapper.find('.config-dialog__label')
    expect(label.text()).toContain('Beschreibung als Label')
  })

  it('falls back to key when both label and description are missing', async () => {
    const wrapper = await mountDialog({
      configSchema: {
        my_field: {
          type: 'boolean',
          default: false,
        },
      },
      config: { my_field: false },
    })

    const label = wrapper.find('.config-dialog__label')
    expect(label.text()).toContain('my_field')
  })
})

// =============================================================================
// CONFIG SAVE
// =============================================================================

describe('PluginConfigDialog - Save', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('emits save with current config on save click', async () => {
    const wrapper = await mountDialog({
      configSchema: {
        flag: { type: 'boolean', default: false, label: 'Flag' },
      },
      config: { flag: true },
    })

    const saveBtn = wrapper.find('.config-dialog__btn--save')
    await saveBtn.trigger('click')

    expect(wrapper.emitted('save')).toBeTruthy()
    expect(wrapper.emitted('save')![0][0]).toEqual({ flag: true })
  })

  it('emits close on cancel click', async () => {
    const wrapper = await mountDialog({
      configSchema: {},
      config: {},
    })

    const cancelBtn = wrapper.find('.config-dialog__btn--cancel')
    await cancelBtn.trigger('click')

    expect(wrapper.emitted('close')).toBeTruthy()
  })
})
