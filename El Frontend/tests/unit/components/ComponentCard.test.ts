/**
 * ComponentCard Component Tests
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ComponentCard from '@/components/dashboard/ComponentCard.vue'
import type { ComponentCardItem } from '@/components/dashboard/ComponentCard.vue'

// lucide-vue-next is mocked globally in tests/setup.ts

const sensorItem: ComponentCardItem = {
  type: 'sensor',
  gpio: 4,
  sensorType: 'DS18B20',
  name: 'Wassertemperatur',
  value: 23.5,
  unit: '°C',
  quality: 'good',
  espId: 'ESP_TEST_001',
  espName: 'Test ESP',
  zoneName: 'Gewächshaus',
  zoneId: 'gewaechshaus',
  subzoneName: null,
  subzoneId: null,
}

const actuatorItem: ComponentCardItem = {
  type: 'actuator',
  gpio: 16,
  actuatorType: 'relay',
  name: 'Pumpe 1',
  value: null,
  unit: '',
  state: true,
  emergencyStopped: false,
  espId: 'ESP_TEST_002',
  espName: 'Pump ESP',
  zoneName: 'Bewässerung',
  zoneId: 'bewaesserung',
  subzoneName: null,
  subzoneId: null,
}

describe('ComponentCard', () => {
  describe('Sensor Card', () => {
    it('renders sensor name', () => {
      const wrapper = mount(ComponentCard, { props: { item: sensorItem } })
      expect(wrapper.text()).toContain('Wassertemperatur')
    })

    it('renders sensor value with unit', () => {
      const wrapper = mount(ComponentCard, { props: { item: sensorItem } })
      expect(wrapper.text()).toContain('23.5 °C')
    })

    it('renders ESP name', () => {
      const wrapper = mount(ComponentCard, { props: { item: sensorItem } })
      expect(wrapper.text()).toContain('Test ESP')
    })

    it('renders zone name', () => {
      const wrapper = mount(ComponentCard, { props: { item: sensorItem } })
      expect(wrapper.text()).toContain('Gewächshaus')
    })

    it('has sensor border class', () => {
      const wrapper = mount(ComponentCard, { props: { item: sensorItem } })
      expect(wrapper.find('.component-card--sensor').exists()).toBe(true)
    })

    it('shows dash for null value', () => {
      const item = { ...sensorItem, value: null }
      const wrapper = mount(ComponentCard, { props: { item } })
      expect(wrapper.text()).toContain('—')
    })

    it('applies stale class when stale', () => {
      const item = { ...sensorItem, isStale: true }
      const wrapper = mount(ComponentCard, { props: { item } })
      expect(wrapper.find('.component-card--stale').exists()).toBe(true)
    })
  })

  describe('Actuator Card', () => {
    it('renders actuator name', () => {
      const wrapper = mount(ComponentCard, { props: { item: actuatorItem } })
      expect(wrapper.text()).toContain('Pumpe 1')
    })

    it('shows Ein for active actuator', () => {
      const wrapper = mount(ComponentCard, { props: { item: actuatorItem } })
      expect(wrapper.text()).toContain('Ein')
    })

    it('shows Aus for inactive actuator', () => {
      const item = { ...actuatorItem, state: false }
      const wrapper = mount(ComponentCard, { props: { item } })
      expect(wrapper.text()).toContain('Aus')
    })

    it('shows Not-Stopp for emergency stopped', () => {
      const item = { ...actuatorItem, emergencyStopped: true }
      const wrapper = mount(ComponentCard, { props: { item } })
      expect(wrapper.text()).toContain('Not-Stopp')
    })

    it('has actuator border class', () => {
      const wrapper = mount(ComponentCard, { props: { item: actuatorItem } })
      expect(wrapper.find('.component-card--actuator').exists()).toBe(true)
    })
  })

  describe('Fallback Display', () => {
    it('uses GPIO as name when no name given', () => {
      const item = { ...sensorItem, name: null, sensorType: undefined }
      const wrapper = mount(ComponentCard, { props: { item } })
      expect(wrapper.text()).toContain('GPIO 4')
    })

    it('uses ESP ID when no ESP name', () => {
      const item = { ...sensorItem, espName: null }
      const wrapper = mount(ComponentCard, { props: { item } })
      expect(wrapper.text()).toContain('ESP_TEST_001')
    })
  })
})
