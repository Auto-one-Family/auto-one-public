/**
 * Drag State Store (Industrial-Grade)
 *
 * Globaler State für Drag-and-Drop-Operationen.
 * Ermöglicht visuelles Feedback über Komponenten hinweg.
 *
 * Features:
 * - Sensor-Typ Drag aus Sidebar
 * - Sensor-Satellite Drag für Auto-Opening Chart
 * - ESP-Cards können auf Drag-State reagieren (dashed border)
 * - Zentrale Payload-Verwaltung
 * - Safety-Cleanup: Automatisches Reset bei hängendem State
 * - Globale Event-Listener für Edge-Cases
 *
 * @version 2.0 - Industrial-Grade mit Safety-Cleanup
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { createLogger } from '@/utils/logger'

const logger = createLogger('DragState')

// =============================================================================
// Constants
// =============================================================================

/**
 * Maximale Zeit (ms) die ein Drag-Vorgang dauern darf.
 * Nach diesem Timeout wird der State automatisch zurückgesetzt.
 * Verhindert "hängende" UI-States bei fehlgeschlagenen Drag-Events.
 */
const DRAG_TIMEOUT_MS = 30000 // 30 Sekunden

// =============================================================================
// Types
// =============================================================================

/**
 * Payload für Sensor-Typ-Drag aus der Sidebar
 */
export interface SensorTypeDragPayload {
  action: 'add-sensor'
  sensorType: string
  label: string
  defaultUnit: string
  icon: string
}

/**
 * Payload für Sensor-Satellite-Drag für Chart-Analyse
 */
export interface SensorDragPayload {
  type: 'sensor'
  espId: string
  gpio: number
  sensorType: string
  name: string
  unit: string
}

/**
 * Payload für Actuator-Typ-Drag aus der ActuatorSidebar (Phase 7)
 */
export interface ActuatorTypeDragPayload {
  action: 'add-actuator'
  actuatorType: string
  label: string
  icon: string
  isPwm: boolean
}

/**
 * Payload für Dashboard-Widget-Drag aus dem FAB (Phase 4A)
 */
export interface DashboardWidgetDragPayload {
  action: 'add-dashboard-widget'
  widgetType: string
  label: string
  defaultW: number
  defaultH: number
  minW: number
  minH: number
}

/**
 * Drag-Statistiken für Debugging
 */
interface DragStats {
  startCount: number
  endCount: number
  timeoutCount: number
  lastDragDuration: number
}

// =============================================================================
// Store
// =============================================================================

export const useDragStateStore = defineStore('dragState', () => {
  // ============================================
  // State
  // ============================================

  /** True wenn ein Sensor-Typ aus der Sidebar gedraggt wird */
  const isDraggingSensorType = ref(false)

  /** Aktueller Drag-Payload (Sensor-Typ-Daten) */
  const sensorTypePayload = ref<SensorTypeDragPayload | null>(null)

  /** True wenn ein Sensor-Satellite für Chart-Analyse gedraggt wird */
  const isDraggingSensor = ref(false)

  /** Aktueller Sensor-Drag-Payload */
  const sensorPayload = ref<SensorDragPayload | null>(null)

  /** ESP-ID des aktuell gedraggten Sensors (für Auto-Open Chart) */
  const draggingSensorEspId = ref<string | null>(null)

  /** True wenn eine ESP-Card zwischen Zonen gedraggt wird (VueDraggable) */
  const isDraggingEspCard = ref(false)

  /** True wenn ein Actuator-Typ aus der ActuatorSidebar gedraggt wird (Phase 7) */
  const isDraggingActuatorType = ref(false)

  /** Aktueller Actuator-Drag-Payload (Phase 7) */
  const actuatorTypePayload = ref<ActuatorTypeDragPayload | null>(null)

  /** True wenn ein Dashboard-Widget aus dem FAB gedraggt wird (Phase 4A) */
  const isDraggingDashboardWidget = ref(false)

  /** Aktueller Dashboard-Widget-Drag-Payload (Phase 4A) */
  const dashboardWidgetPayload = ref<DashboardWidgetDragPayload | null>(null)

  /** True wenn die CameraCard per HTML5-Drag einer Zone zugewiesen wird */
  const isDraggingCamera = ref(false)

  /** Zeitpunkt des Drag-Starts (für Timeout-Detection) */
  const dragStartTime = ref<number | null>(null)

  /** Safety-Timeout Timer ID */
  let safetyTimeoutId: ReturnType<typeof setTimeout> | null = null

  /** Statistiken für Debugging */
  const stats = ref<DragStats>({
    startCount: 0,
    endCount: 0,
    timeoutCount: 0,
    lastDragDuration: 0,
  })

  // ============================================
  // Computed
  // ============================================

  /** True wenn irgendein Drag aktiv ist */
  const isAnyDragActive = computed(() =>
    isDraggingSensorType.value || isDraggingSensor.value || isDraggingEspCard.value || isDraggingActuatorType.value || isDraggingDashboardWidget.value || isDraggingCamera.value
  )

  /** Aktuelle Drag-Dauer in ms (für Debugging) */
  const currentDragDuration = computed(() => {
    if (!dragStartTime.value) return 0
    return Date.now() - dragStartTime.value
  })

  // ============================================
  // Internal Methods
  // ============================================

  /**
   * Startet den Safety-Timeout.
   * Resettet den State automatisch falls dragend nie aufgerufen wird.
   */
  function startSafetyTimeout(): void {
    clearSafetyTimeout()

    safetyTimeoutId = setTimeout(() => {
      if (isAnyDragActive.value) {
        logger.warn('Safety timeout triggered - resetting stuck drag state')
        stats.value.timeoutCount++
        endDrag()
      }
    }, DRAG_TIMEOUT_MS)
  }

  /**
   * Löscht den Safety-Timeout.
   */
  function clearSafetyTimeout(): void {
    if (safetyTimeoutId) {
      clearTimeout(safetyTimeoutId)
      safetyTimeoutId = null
    }
  }


  // ============================================
  // Actions
  // ============================================

  /**
   * Startet einen Sensor-Typ-Drag aus der Sidebar
   */
  function startSensorTypeDrag(payload: SensorTypeDragPayload): void {
    logger.debug('Starting sensor type drag', { sensorType: payload.sensorType })

    // Reset vorheriger State (Sicherheit)
    if (isAnyDragActive.value) {
      logger.debug('Warning: Starting new drag while previous drag active - resetting')
      endDrag()
    }

    isDraggingSensorType.value = true
    sensorTypePayload.value = payload
    dragStartTime.value = Date.now()
    stats.value.startCount++

    startSafetyTimeout()
  }

  /**
   * Startet einen ESP-Card-Drag (VueDraggable zwischen Zonen)
   */
  function startEspCardDrag(): void {
    logger.debug('Starting ESP card drag')

    // Reset vorheriger State (Sicherheit)
    if (isAnyDragActive.value) {
      logger.debug('Warning: Starting new drag while previous drag active - resetting')
      endDrag()
    }

    isDraggingEspCard.value = true
    dragStartTime.value = Date.now()
    stats.value.startCount++

    startSafetyTimeout()
  }

  /**
   * Beendet einen ESP-Card-Drag
   */
  function endEspCardDrag(): void {
    logger.debug('Ending ESP card drag')
    isDraggingEspCard.value = false

    // Berechne Drag-Dauer für Statistiken
    if (dragStartTime.value) {
      stats.value.lastDragDuration = Date.now() - dragStartTime.value
    }

    dragStartTime.value = null
    stats.value.endCount++
    clearSafetyTimeout()
  }

  /**
   * Startet einen Camera-Drag (HTML5, kein VueDraggable)
   */
  function startCameraDrag(): void {
    logger.debug('Starting camera drag')
    if (isAnyDragActive.value) {
      logger.debug('Warning: Starting camera drag while previous drag active - resetting')
      endDrag()
    }
    isDraggingCamera.value = true
    dragStartTime.value = Date.now()
    stats.value.startCount++
    startSafetyTimeout()
  }

  /**
   * Beendet einen Camera-Drag
   */
  function endCameraDrag(): void {
    logger.debug('Ending camera drag')
    isDraggingCamera.value = false
    if (dragStartTime.value) {
      stats.value.lastDragDuration = Date.now() - dragStartTime.value
    }
    dragStartTime.value = null
    stats.value.endCount++
    clearSafetyTimeout()
  }

  /**
   * Startet einen Sensor-Satellite-Drag für Chart-Analyse
   */
  function startSensorDrag(payload: SensorDragPayload): void {
    logger.debug('Starting sensor drag', { espId: payload.espId, gpio: payload.gpio })

    // Reset vorheriger State (Sicherheit)
    if (isAnyDragActive.value) {
      logger.debug('Warning: Starting new drag while previous drag active - resetting')
      endDrag()
    }

    isDraggingSensor.value = true
    sensorPayload.value = payload
    draggingSensorEspId.value = payload.espId
    dragStartTime.value = Date.now()
    stats.value.startCount++

    startSafetyTimeout()
  }

  /**
   * Startet einen Actuator-Typ-Drag aus der ActuatorSidebar (Phase 7)
   */
  function startActuatorTypeDrag(payload: ActuatorTypeDragPayload): void {
    logger.debug('Starting actuator type drag', { actuatorType: payload.actuatorType })

    // Reset vorheriger State (Sicherheit)
    if (isAnyDragActive.value) {
      logger.debug('Warning: Starting new drag while previous drag active - resetting')
      endDrag()
    }

    isDraggingActuatorType.value = true
    actuatorTypePayload.value = payload
    dragStartTime.value = Date.now()
    stats.value.startCount++

    startSafetyTimeout()
  }

  /**
   * Startet einen Dashboard-Widget-Drag aus dem FAB (Phase 4A)
   */
  function startDashboardWidgetDrag(payload: DashboardWidgetDragPayload): void {
    logger.debug('Starting dashboard widget drag', { widgetType: payload.widgetType })

    if (isAnyDragActive.value) {
      logger.debug('Warning: Starting new drag while previous drag active - resetting')
      endDrag()
    }

    isDraggingDashboardWidget.value = true
    dashboardWidgetPayload.value = payload
    dragStartTime.value = Date.now()
    stats.value.startCount++

    startSafetyTimeout()
  }

  /**
   * Beendet den aktuellen Drag-Vorgang.
   * Wird sowohl von Components als auch vom Safety-Timeout aufgerufen.
   */
  function endDrag(): void {
    // Log current state BEFORE reset
    logger.debug('endDrag() called', {
      wasDraggingSensorType: isDraggingSensorType.value,
      wasDraggingSensor: isDraggingSensor.value,
      wasDraggingEspCard: isDraggingEspCard.value,
      wasDraggingActuatorType: isDraggingActuatorType.value,
      wasDraggingDashboardWidget: isDraggingDashboardWidget.value,
      sensorPayload: sensorPayload.value,
      draggingSensorEspId: draggingSensorEspId.value,
      actuatorTypePayload: actuatorTypePayload.value,
      dashboardWidgetPayload: dashboardWidgetPayload.value,
    })

    // Berechne Drag-Dauer für Statistiken
    if (dragStartTime.value) {
      stats.value.lastDragDuration = Date.now() - dragStartTime.value
      logger.debug('Drag duration', { duration: `${stats.value.lastDragDuration}ms` })
    }

    // State zurücksetzen
    isDraggingSensorType.value = false
    sensorTypePayload.value = null
    isDraggingSensor.value = false
    sensorPayload.value = null
    draggingSensorEspId.value = null
    isDraggingEspCard.value = false
    isDraggingActuatorType.value = false
    actuatorTypePayload.value = null
    isDraggingDashboardWidget.value = false
    dashboardWidgetPayload.value = null
    isDraggingCamera.value = false
    dragStartTime.value = null
    stats.value.endCount++

    clearSafetyTimeout()
    logger.debug('State reset complete', { stats: stats.value })
  }

  /**
   * Forciert einen Reset (für manuelle Intervention)
   */
  function forceReset(): void {
    logger.debug('Force reset triggered')
    endDrag()
  }

  /**
   * Gibt Debug-Statistiken zurück
   */
  function getStats(): DragStats {
    return { ...stats.value }
  }

  // ============================================
  // Global Event Listeners (Safety Net)
  // ISSUE-003 fix: Proper cleanup to prevent memory leaks during HMR
  // ============================================

  /** Flag to track if listeners are registered (prevents duplicates during HMR) */
  let listenersRegistered = false

  /**
   * Globaler dragend Listener als Safety-Net.
   * Fängt dragend Events ab die nicht von Components behandelt werden.
   *
   * WICHTIG: Nur für native HTML5 Drags (SensorSatellite, SensorTypeDrag).
   * VueDraggable/SortableJS verwendet KEINE nativen drag events - es verwendet
   * Mouse-Events. Daher dürfen wir bei isDraggingEspCard NICHT eingreifen!
   */
  function handleGlobalDragEnd(event: DragEvent): void {
    // Nur für native HTML5 Drags reagieren, NICHT für SortableJS/VueDraggable
    // isDraggingEspCard wird von VueDraggable verwaltet (@choose/@end Events)
    if (isDraggingEspCard.value) {
      logger.debug('Global dragend ignored - ESP card drag is managed by VueDraggable', {
        target: (event.target as HTMLElement)?.tagName,
      })
      return
    }

    // Nur bei nativen Drags (Sensor-Typ aus Sidebar, Sensor-Satellite für Chart, Actuator-Typ aus Sidebar, Dashboard-Widget aus FAB)
    if (isDraggingSensorType.value || isDraggingSensor.value || isDraggingActuatorType.value || isDraggingDashboardWidget.value || isDraggingCamera.value) {
      logger.debug('Global dragend caught for native drag - ensuring state cleanup', {
        target: (event.target as HTMLElement)?.tagName,
        isDraggingSensorType: isDraggingSensorType.value,
        isDraggingSensor: isDraggingSensor.value,
        isDraggingActuatorType: isDraggingActuatorType.value,
        isDraggingDashboardWidget: isDraggingDashboardWidget.value,
        isDraggingCamera: isDraggingCamera.value,
      })
      // Kleine Verzögerung um Component-Handler Zeit zu geben
      setTimeout(() => {
        if (isDraggingSensorType.value || isDraggingSensor.value || isDraggingActuatorType.value || isDraggingDashboardWidget.value || isDraggingCamera.value) {
          logger.debug('State still active after global dragend - forcing cleanup')
          endDrag()
        }
      }, 100)
    }
  }

  /**
   * Keydown Handler für Escape-Taste.
   * Ermöglicht manuelles Abbrechen eines Drags.
   */
  function handleKeyDown(event: KeyboardEvent): void {
    if (event.key === 'Escape' && isAnyDragActive.value) {
      logger.debug('Escape pressed - canceling drag')
      endDrag()
    }
  }

  /**
   * Register global event listeners.
   * Safe to call multiple times - will only register once.
   */
  function registerListeners(): void {
    if (typeof window === 'undefined' || listenersRegistered) return

    window.addEventListener('dragend', handleGlobalDragEnd, { capture: true })
    window.addEventListener('keydown', handleKeyDown)
    listenersRegistered = true
    logger.debug('Global event listeners registered')
  }

  /**
   * Cleanup global event listeners.
   * Exportiert für Tests und explizites Cleanup bei Bedarf.
   */
  function cleanup(): void {
    if (typeof window === 'undefined' || !listenersRegistered) return

    window.removeEventListener('dragend', handleGlobalDragEnd, { capture: true })
    window.removeEventListener('keydown', handleKeyDown)
    listenersRegistered = false
    clearSafetyTimeout()
    logger.debug('Global event listeners cleaned up')
  }

  // Auto-register listeners on store creation
  registerListeners()

  // ============================================
  // Return
  // ============================================

  return {
    // State (readonly für Components)
    isDraggingSensorType,
    sensorTypePayload,
    isDraggingSensor,
    sensorPayload,
    draggingSensorEspId,
    isDraggingEspCard,
    isDraggingActuatorType,
    actuatorTypePayload,
    isDraggingDashboardWidget,
    dashboardWidgetPayload,
    isDraggingCamera,

    // Computed
    isAnyDragActive,
    currentDragDuration,

    // Actions
    startSensorTypeDrag,
    startSensorDrag,
    startActuatorTypeDrag,
    startDashboardWidgetDrag,
    startEspCardDrag,
    endEspCardDrag,
    startCameraDrag,
    endCameraDrag,
    endDrag,
    forceReset,
    getStats,

    // Lifecycle (ISSUE-003 fix)
    cleanup,
  }
})
