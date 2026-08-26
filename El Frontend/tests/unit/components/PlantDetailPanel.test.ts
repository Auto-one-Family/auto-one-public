/**
 * PlantDetailPanel — Notiz oben, kein Phasenverlauf/Audit-Trail.
 */

import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PlantDetailPanel from '@/components/plants/PlantDetailPanel.vue'
import type { Plant } from '@/types'

vi.mock('@/shared/stores/plants.store', () => ({
  usePlantsStore: () => ({
    fetchPlantDetail: vi.fn(async () => plant),
    fetchMeasurements: vi.fn(async () => []),
    addLifecycleEvent: vi.fn(),
  }),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('@/api/plants', () => ({
  plantsApi: { downloadQRCode: vi.fn() },
}))

const plant: Plant = {
  plant_id: 'p1',
  qr_code: 'QR-1',
  genotype_label: 'Test',
  batch_label: 'C1',
  phase: 'vegetative',
  planting_date: '2026-06-01',
} as Plant

describe('PlantDetailPanel', () => {
  it('should put the note form first and hide phase/audit sections', () => {
    setActivePinia(createPinia())
    const wrapper = mount(PlantDetailPanel, {
      props: { plant },
      global: {
        stubs: {
          AccordionSection: { template: '<div><slot /></div>' },
          Scatter: true,
          PlantPhaseChangeModal: true,
          PlantCreateModal: true,
        },
      },
    })

    const text = wrapper.text()
    expect(wrapper.find('.plant-detail__note').exists()).toBe(true)
    expect(wrapper.get('.plant-detail__note').find('textarea').attributes('placeholder')).toBe(
      'Notiz hinzufügen...',
    )
    expect(text).toContain('Notiz hinzufügen')
    expect(text).not.toContain('Phasenverlauf')
    expect(text).not.toContain('Audit-Trail')
    expect(text).not.toContain('Zurücknehmen')
    expect(text).not.toContain('Lifecycle-Events')

    const firstSection = wrapper.find('.plant-detail > .plant-detail__section')
    expect(firstSection.classes()).toContain('plant-detail__note')
  })
})
