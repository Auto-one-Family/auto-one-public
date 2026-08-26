/**
 * PlantsView — Pflanzen-Tab ist pflanzen-only (Struktur, kein Tank/Tabelle).
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PlantsView from '@/views/PlantsView.vue'

const replace = vi.fn()
const routeQuery: Record<string, unknown> = {}

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: routeQuery, params: {} }),
  useRouter: () => ({ replace, push: vi.fn() }),
}))

vi.mock('@/shared/stores/plants.store', () => ({
  usePlantsStore: () => ({
    plants: [],
    isLoading: false,
    error: null,
    fetchPlants: vi.fn(),
  }),
}))

vi.mock('@/shared/stores/zone.store', () => ({
  useZoneStore: () => ({
    activeZones: [],
    zoneEntities: [],
    isLoadingZones: false,
    fetchZoneEntities: vi.fn(),
  }),
}))

vi.mock('@/stores/esp', () => ({
  useEspStore: () => ({
    devices: [{ device_id: 'ESP_1' }],
    fetchAll: vi.fn(),
  }),
}))

vi.mock('@/composables/usePlantDragDrop', () => ({
  usePlantDragDrop: () => ({
    canUndo: { value: false },
    canRedo: { value: false },
    undo: vi.fn(),
    redo: vi.fn(),
    handlePlantSubzoneChange: vi.fn(),
  }),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn() }),
}))

describe('PlantsView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    replace.mockReset()
    for (const key of Object.keys(routeQuery)) {
      delete routeQuery[key]
    }
  })

  it('should show plant actions and hide tank/table chrome', () => {
    const wrapper = mount(PlantsView, {
      global: {
        stubs: {
          SlideOver: true,
          PlantDetailPanel: true,
          PlantCreateModal: true,
          PlantBatchCreateModal: true,
          PlantSubzoneArea: true,
        },
      },
    })

    expect(wrapper.text()).toContain('Pflanzen-Inventar')
    expect(wrapper.text()).toContain('Neue Pflanze')
    expect(wrapper.text()).toContain('N Pflanzen')
    expect(wrapper.text()).not.toContain('Tank')
    expect(wrapper.text()).not.toContain('Bilanz')
    expect(wrapper.text()).not.toContain('Vorfall')
    expect(wrapper.text()).not.toContain('Tank für Ist/Soll')
    expect(wrapper.find('.plants-view-toggle').exists()).toBe(false)
    expect(wrapper.find('.plants-table').exists()).toBe(false)
  })

  it('should redirect legacy /plants?tank= bookmarks to the nutrient-solution tab', () => {
    routeQuery.tank = 'tank-abc'
    mount(PlantsView, {
      global: {
        stubs: {
          SlideOver: true,
          PlantDetailPanel: true,
          PlantCreateModal: true,
          PlantBatchCreateModal: true,
          PlantSubzoneArea: true,
        },
      },
    })
    expect(replace).toHaveBeenCalledWith('/nutrient-solution/tank-abc')
  })
})
