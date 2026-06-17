/**
 * useOrbitalDragDrop Composable
 *
 * Handles all drag-and-drop related logic for the ESP orbital layout:
 * 1. DnD event handlers for adding sensors/actuators from the sidebar
 * 2. Modal state for AddSensorModal / AddActuatorModal
 * 3. Analysis drop zone auto-open when a sensor from this ESP is dragged
 *
 * Extracted from ESPOrbitalLayout.vue for maintainability.
 *
 * Used by:
 * - ESPOrbitalLayout (sole consumer)
 */

import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { useDragStateStore } from '@/shared/stores/dragState.store'
import { createLogger } from '@/utils/logger'

const logger = createLogger('OrbitalDragDrop')

export function useOrbitalDragDrop(espId: Ref<string> | ComputedRef<string>) {
  const dragStore = useDragStateStore()

  // ═══════════════════════════════════════════════════════════════════════
  // Add Sensor/Actuator Drop State
  // ═══════════════════════════════════════════════════════════════════════

  const isDragOver = ref(false)
  const showAddSensorModal = ref(false)
  const showAddActuatorModal = ref(false)
  const droppedSensorType = ref<string | null>(null)
  const droppedActuatorType = ref<string | null>(null)

  // ═══════════════════════════════════════════════════════════════════════
  // Analysis Drop Zone Auto-Open State
  // ═══════════════════════════════════════════════════════════════════════

  const analysisExpanded = ref(false)
  const wasAutoOpened = ref(false)

  /** Whether a sensor from THIS ESP is currently being dragged */
  const isSensorFromThisEspDragging = computed(() =>
    dragStore.isDraggingSensor && dragStore.draggingSensorEspId === espId.value
  )

  // ═══════════════════════════════════════════════════════════════════════
  // Debug Logger
  // ═══════════════════════════════════════════════════════════════════════

  function log(message: string, data?: Record<string, unknown>): void {
    logger.debug(message, data)
  }

  // ═══════════════════════════════════════════════════════════════════════
  // Drop Event Handlers (for adding sensors via drag from sidebar)
  // ═══════════════════════════════════════════════════════════════════════

  function onDragEnter(event: DragEvent): void {
    const types = event.dataTransfer?.types || []

    log('dragenter', {
      isDraggingSensorType: dragStore.isDraggingSensorType,
      isDraggingSensor: dragStore.isDraggingSensor,
      isDraggingActuatorType: dragStore.isDraggingActuatorType,
      types: Array.from(types),
      target: (event.target as Element)?.className?.slice?.(0, 50) || (event.target as Element)?.tagName,
    })

    // Ignore VueDraggable ESP-Card reordering events
    if (!dragStore.isDraggingSensorType && !dragStore.isDraggingSensor && !dragStore.isDraggingActuatorType) {
      log('dragenter IGNORED - likely VueDraggable ESP-Card reordering')
      return
    }

    // React visually if dragging a sensor or actuator type from sidebar
    if (dragStore.isDraggingSensorType || dragStore.isDraggingActuatorType) {
      isDragOver.value = true
      if (event.dataTransfer) {
        event.dataTransfer.dropEffect = 'copy'
      }
      logger.info('[DnD] Drag ENTER on ESP', {
        espId: espId.value,
        isSensor: dragStore.isDraggingSensorType,
        isActuator: dragStore.isDraggingActuatorType,
      })
    }
    // Sensor-Satellite-Drags (for chart) are passed through to AnalysisDropZone
  }

  function onDragOver(event: DragEvent): void {
    // Ignore VueDraggable ESP-Card reordering events
    if (!dragStore.isDraggingSensorType && !dragStore.isDraggingSensor && !dragStore.isDraggingActuatorType) {
      return
    }

    // preventDefault() is required to allow drop
    if (dragStore.isDraggingSensorType || dragStore.isDraggingActuatorType) {
      event.preventDefault()
      if (event.dataTransfer) {
        event.dataTransfer.dropEffect = 'copy'
      }
    } else if (dragStore.isDraggingSensor) {
      event.preventDefault()
      if (event.dataTransfer) {
        event.dataTransfer.dropEffect = 'copy'
      }
    }
  }

  function onDragLeave(event: DragEvent): void {
    // Ignore VueDraggable ESP-Card reordering events
    if (!dragStore.isDraggingSensorType && !dragStore.isDraggingSensor && !dragStore.isDraggingActuatorType) {
      return
    }

    // Only reset if leaving the container entirely
    const target = event.currentTarget as HTMLElement
    const related = event.relatedTarget as HTMLElement
    if (!target.contains(related)) {
      isDragOver.value = false
      log('dragleave - isDragOver = false')
    }
  }

  function onDrop(event: DragEvent): void {
    // Ignore VueDraggable ESP-Card reordering events
    if (!dragStore.isDraggingSensorType && !dragStore.isDraggingSensor && !dragStore.isDraggingActuatorType) {
      log('DROP IGNORED - likely VueDraggable ESP-Card reordering')
      return
    }

    logger.info('[DnD] DROP on ESP', {
      espId: espId.value,
      hasJsonData: !!event.dataTransfer?.getData('application/json'),
      types: event.dataTransfer?.types ? Array.from(event.dataTransfer.types) : [],
    })

    event.preventDefault()
    isDragOver.value = false

    const jsonData = event.dataTransfer?.getData('application/json')
    if (!jsonData) {
      log('DROP - no JSON data, ignoring')
      dragStore.endDrag()
      return
    }

    try {
      const payload = JSON.parse(jsonData)
      log('DROP payload parsed', payload)

      if (payload.action === 'add-sensor') {
        logger.info('[DnD] Opening AddSensorModal', { sensorType: payload.sensorType, espId: espId.value })
        droppedSensorType.value = payload.sensorType || null
        showAddSensorModal.value = true
        return
      } else if (payload.action === 'add-actuator') {
        logger.info('[DnD] Opening AddActuatorModal', { actuatorType: payload.actuatorType, espId: espId.value })
        droppedActuatorType.value = payload.actuatorType || null
        showAddActuatorModal.value = true
        return
      } else if (payload.type === 'sensor') {
        log('DROP - sensor for chart, should be handled by AnalysisDropZone')
        return
      } else {
        log('DROP - unknown payload type', { type: payload.type, action: payload.action })
        dragStore.endDrag()
        return
      }
    } catch (error) {
      log('DROP ERROR - failed to parse', { error })
      dragStore.endDrag()
      return
    }
  }

  // ═══════════════════════════════════════════════════════════════════════
  // Watchers
  // ═══════════════════════════════════════════════════════════════════════

  // Reset dropped types when modals close (prevents stale state on re-drag)
  watch(showAddSensorModal, (isOpen) => {
    if (!isOpen) {
      droppedSensorType.value = null
      // Explizites Cleanup bei Modal-Cancel/Close: verhindert hängenbleibenden globalen Drag-State.
      if (dragStore.isAnyDragActive) {
        dragStore.endDrag()
      }
      logger.info('[DnD] Sensor modal closed, droppedSensorType reset')
    }
  })
  watch(showAddActuatorModal, (isOpen) => {
    if (!isOpen) {
      droppedActuatorType.value = null
      // Explizites Cleanup bei Modal-Cancel/Close: verhindert hängenbleibenden globalen Drag-State.
      if (dragStore.isAnyDragActive) {
        dragStore.endDrag()
      }
      logger.info('[DnD] Actuator modal closed, droppedActuatorType reset')
    }
  })

  /**
   * Auto-open analysis chart when a sensor from THIS ESP is being dragged.
   * Uses overlay mode during drag to prevent layout shifts.
   */
  watch(
    () => isSensorFromThisEspDragging.value,
    (isDraggingFromThisEsp) => {
      log('isSensorFromThisEspDragging changed', {
        isDraggingFromThisEsp,
        analysisExpanded: analysisExpanded.value,
        wasAutoOpened: wasAutoOpened.value,
      })

      if (isDraggingFromThisEsp) {
        if (!analysisExpanded.value) {
          wasAutoOpened.value = true
          analysisExpanded.value = true
          log('Auto-opening chart (overlay mode)')
        }
      } else {
        // Transition from overlay to inline mode after drag ends
        if (wasAutoOpened.value) {
          log('Drag ended, transitioning from overlay to inline mode')
          setTimeout(() => {
            wasAutoOpened.value = false
            log('wasAutoOpened = false (inline mode now)')
          }, 300)
        }
      }
    }
  )

  // Reset wasAutoOpened when user manually closes the chart
  watch(
    () => analysisExpanded.value,
    (expanded) => {
      if (!expanded) {
        wasAutoOpened.value = false
      }
    }
  )

  return {
    // DnD event handlers
    onDragEnter,
    onDragOver,
    onDragLeave,
    onDrop,

    // Drop state
    isDragOver,

    // Modal state
    showAddSensorModal,
    showAddActuatorModal,
    droppedSensorType,
    droppedActuatorType,

    // Analysis auto-open state
    analysisExpanded,
    wasAutoOpened,
    isSensorFromThisEspDragging,
  }
}
