/**
 * Tests for FormField component.
 * Verifies field type mapping and value conversion.
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FormField from '@/components/forms/FormField.vue'
import type { FormFieldSchema } from '@/types/form-schema'

// Stubs for the design primitives
const stubs = {
  BaseInput: {
    template: '<div class="base-input"><input :type="type" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" /></div>',
    props: ['modelValue', 'type', 'label', 'disabled', 'min', 'max', 'step', 'placeholder', 'error', 'helper'],
    emits: ['update:modelValue'],
  },
  BaseSelect: {
    template: '<div class="base-select"><select @change="$emit(\'update:modelValue\', $event.target.value)"><option v-for="o in options" :key="o.value" :value="o.value">{{ o.label }}</option></select></div>',
    props: ['modelValue', 'options', 'label', 'disabled', 'error', 'helper'],
    emits: ['update:modelValue'],
  },
  BaseToggle: {
    template: '<div class="base-toggle"><button @click="$emit(\'update:modelValue\', !modelValue)">Toggle</button></div>',
    props: ['modelValue', 'label', 'description', 'disabled'],
    emits: ['update:modelValue'],
  },
}

function mountField(schema: Partial<FormFieldSchema> = {}, modelValue: unknown = '') {
  const fullSchema: FormFieldSchema = {
    key: 'test',
    type: 'text',
    label: 'Test Field',
    ...schema,
  }
  return mount(FormField, {
    props: { schema: fullSchema, modelValue },
    global: { stubs },
  })
}

describe('FormField', () => {
  it('renders BaseInput for text type', () => {
    const wrapper = mountField({ type: 'text' })
    expect(wrapper.find('.base-input').exists()).toBe(true)
  })

  it('renders BaseInput for number type', () => {
    const wrapper = mountField({ type: 'number' }, 42)
    expect(wrapper.find('.base-input').exists()).toBe(true)
  })

  it('renders BaseSelect for select type', () => {
    const wrapper = mountField({
      type: 'select',
      options: [{ value: 'a', label: 'Option A' }],
    })
    expect(wrapper.find('.base-select').exists()).toBe(true)
  })

  it('renders BaseSelect for gpio-select type', () => {
    const wrapper = mountField({
      type: 'gpio-select',
      options: [{ value: '4', label: 'GPIO 4' }],
    })
    expect(wrapper.find('.base-select').exists()).toBe(true)
  })

  it('renders BaseToggle for toggle type', () => {
    const wrapper = mountField({ type: 'toggle' }, false)
    expect(wrapper.find('.base-toggle').exists()).toBe(true)
  })

  it('renders range slider for range type', () => {
    const wrapper = mountField({ type: 'range', min: 0, max: 100 }, 50)
    expect(wrapper.find('input[type="range"]').exists()).toBe(true)
  })

  it('converts string to number for number fields', async () => {
    const wrapper = mountField({ type: 'number' }, 0)
    const input = wrapper.find('.base-input input')
    await input.setValue('42')
    await input.trigger('input')

    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeDefined()
    if (emitted && emitted.length > 0) {
      expect(typeof emitted[0][0]).toBe('number')
      expect(emitted[0][0]).toBe(42)
    }
  })

  it('shows helper text for range fields', () => {
    const wrapper = mountField({ type: 'range', helper: 'Slide me' }, 50)
    expect(wrapper.text()).toContain('Slide me')
  })

  it('shows label for range fields', () => {
    const wrapper = mountField({ type: 'range', label: 'Speed' }, 50)
    expect(wrapper.text()).toContain('Speed')
  })
})
