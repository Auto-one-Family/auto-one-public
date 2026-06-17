/**
 * Tests for FormGroup component.
 * Verifies collapse behavior, title rendering, and description.
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FormGroup from '@/components/forms/FormGroup.vue'
import type { FormGroupSchema } from '@/types/form-schema'

function mountGroup(schema: Partial<FormGroupSchema> = {}, slotContent = '<div class="child">Field</div>') {
  const fullSchema: FormGroupSchema = {
    title: 'Test Group',
    fields: [],
    ...schema,
  }
  return mount(FormGroup, {
    props: { schema: fullSchema },
    slots: { default: slotContent },
  })
}

describe('FormGroup', () => {
  it('renders group title', () => {
    const wrapper = mountGroup({ title: 'Hardware' })
    expect(wrapper.text()).toContain('Hardware')
  })

  it('renders description when provided', () => {
    const wrapper = mountGroup({ title: 'Test', description: 'Some helper text' })
    expect(wrapper.text()).toContain('Some helper text')
  })

  it('does not render description when not provided', () => {
    const wrapper = mountGroup({ title: 'Test' })
    expect(wrapper.find('.form-group__description').exists()).toBe(false)
  })

  it('starts expanded by default', () => {
    const wrapper = mountGroup()
    expect(wrapper.find('.form-group__body--collapsed').exists()).toBe(false)
  })

  it('starts collapsed when schema.collapsed is true', () => {
    const wrapper = mountGroup({ collapsed: true })
    expect(wrapper.find('.form-group__body--collapsed').exists()).toBe(true)
  })

  it('toggles collapse on header click', async () => {
    const wrapper = mountGroup()
    expect(wrapper.find('.form-group__body--collapsed').exists()).toBe(false)

    await wrapper.find('.form-group__header').trigger('click')
    expect(wrapper.find('.form-group__body--collapsed').exists()).toBe(true)

    await wrapper.find('.form-group__header').trigger('click')
    expect(wrapper.find('.form-group__body--collapsed').exists()).toBe(false)
  })

  it('sets aria-expanded correctly', async () => {
    const wrapper = mountGroup()
    const header = wrapper.find('.form-group__header')

    expect(header.attributes('aria-expanded')).toBe('true')
    await header.trigger('click')
    expect(header.attributes('aria-expanded')).toBe('false')
  })

  it('renders slot content', () => {
    const wrapper = mountGroup({}, '<span class="test-slot">Hello</span>')
    expect(wrapper.find('.test-slot').exists()).toBe(true)
    expect(wrapper.text()).toContain('Hello')
  })

  it('header button has type="button" to prevent form submit', () => {
    const wrapper = mountGroup()
    const header = wrapper.find('.form-group__header')
    expect(header.attributes('type')).toBe('button')
  })
})
