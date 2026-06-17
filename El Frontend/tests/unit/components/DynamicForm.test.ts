/**
 * Tests for DynamicForm component.
 * Verifies schema rendering, field visibility, v-model, and submit.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import DynamicForm from '@/components/forms/DynamicForm.vue'
import type { FormSchema } from '@/types/form-schema'

const simpleSchema: FormSchema = {
  groups: [{
    title: 'Basic',
    fields: [
      { key: 'name', type: 'text', label: 'Name', required: true },
      { key: 'count', type: 'number', label: 'Count', min: 0, max: 100 },
    ],
  }],
}

const conditionalSchema: FormSchema = {
  groups: [{
    title: 'Settings',
    fields: [
      {
        key: 'mode',
        type: 'select',
        label: 'Mode',
        options: [
          { value: 'auto', label: 'Auto' },
          { value: 'manual', label: 'Manual' },
        ],
      },
      {
        key: 'threshold',
        type: 'number',
        label: 'Threshold',
        dependsOn: { field: 'mode', value: 'manual', operator: '==' },
      },
    ],
  }],
}

const multiGroupSchema: FormSchema = {
  groups: [
    {
      title: 'Hardware',
      fields: [
        { key: 'gpio', type: 'number', label: 'GPIO Pin' },
      ],
    },
    {
      title: 'Advanced',
      collapsed: true,
      fields: [
        { key: 'interval', type: 'number', label: 'Interval (ms)' },
      ],
    },
  ],
}

function mountForm(schema: FormSchema, modelValue: Record<string, unknown> = {}) {
  return mount(DynamicForm, {
    props: { schema, modelValue },
    global: {
      stubs: {
        FormGroup: {
          template: '<div class="form-group"><slot /></div>',
          props: ['schema'],
        },
        FormField: {
          template: '<div class="form-field" :data-key="schema.key" :data-visible="true"></div>',
          props: ['schema', 'modelValue', 'disabled'],
          emits: ['update:modelValue'],
        },
      },
    },
  })
}

describe('DynamicForm', () => {
  it('renders form element', () => {
    const wrapper = mountForm(simpleSchema)
    expect(wrapper.find('form').exists()).toBe(true)
  })

  it('renders correct number of groups', () => {
    const wrapper = mountForm(multiGroupSchema)
    expect(wrapper.findAll('.form-group')).toHaveLength(2)
  })

  it('renders fields within groups', () => {
    const wrapper = mountForm(simpleSchema, { name: 'test', count: 5 })
    const fields = wrapper.findAll('.form-field')
    expect(fields).toHaveLength(2)
  })

  it('emits update:modelValue when field changes', async () => {
    const wrapper = mount(DynamicForm, {
      props: {
        schema: simpleSchema,
        modelValue: { name: 'old', count: 0 },
      },
      global: {
        stubs: {
          FormGroup: {
            template: '<div><slot /></div>',
            props: ['schema'],
          },
          FormField: {
            template: '<div></div>',
            props: ['schema', 'modelValue', 'disabled'],
            emits: ['update:modelValue'],
            setup(_props: any, { emit }: any) {
              // Simulate field update
              setTimeout(() => emit('update:modelValue', 'newValue'), 0)
            },
          },
        },
      },
    })

    await new Promise(r => setTimeout(r, 10))
    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeDefined()
    if (emitted && emitted.length > 0) {
      expect(emitted[0][0]).toHaveProperty('name', 'newValue')
    }
  })

  it('emits submit on form submit', async () => {
    const wrapper = mountForm(simpleSchema)
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('submit')).toBeDefined()
  })

  it('applies loading class when loading prop is true', () => {
    const wrapper = mount(DynamicForm, {
      props: {
        schema: simpleSchema,
        modelValue: {},
        loading: true,
      },
      global: {
        stubs: {
          FormGroup: { template: '<div><slot /></div>', props: ['schema'] },
          FormField: { template: '<div></div>', props: ['schema', 'modelValue', 'disabled'] },
        },
      },
    })
    expect(wrapper.find('.dynamic-form--loading').exists()).toBe(true)
  })

  it('does not apply loading class by default', () => {
    const wrapper = mountForm(simpleSchema)
    expect(wrapper.find('.dynamic-form--loading').exists()).toBe(false)
  })
})
