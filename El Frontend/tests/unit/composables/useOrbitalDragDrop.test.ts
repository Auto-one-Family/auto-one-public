import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { ref, nextTick } from 'vue'
import { useDragStateStore } from '@/shared/stores/dragState.store'
import { useOrbitalDragDrop } from '@/composables/useOrbitalDragDrop'

vi.mock('@/utils/logger', () => ({
  createLogger: () => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  }),
}))

describe('useOrbitalDragDrop', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('beendet globalen drag-state bei modal-cancel', async () => {
    const dragStore = useDragStateStore()
    dragStore.startSensorTypeDrag({
      action: 'add-sensor',
      sensorType: 'ds18b20',
      label: 'DS18B20',
      defaultUnit: '°C',
      icon: 'Thermometer',
    })

    const { showAddSensorModal } = useOrbitalDragDrop(ref('ESP_1'))
    showAddSensorModal.value = true
    await nextTick()
    showAddSensorModal.value = false
    await nextTick()

    expect(dragStore.isAnyDragActive).toBe(false)
  })

  it('führt cleanup bei unbekanntem drop-payload aus', () => {
    const dragStore = useDragStateStore()
    dragStore.startSensorTypeDrag({
      action: 'add-sensor',
      sensorType: 'ds18b20',
      label: 'DS18B20',
      defaultUnit: '°C',
      icon: 'Thermometer',
    })

    const { onDrop } = useOrbitalDragDrop(ref('ESP_1'))
    onDrop({
      preventDefault: vi.fn(),
      dataTransfer: {
        getData: () => JSON.stringify({ action: 'unsupported-action' }),
        types: ['application/json'],
      },
    } as unknown as DragEvent)

    expect(dragStore.isAnyDragActive).toBe(false)
  })
})
