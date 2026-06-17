<script setup lang="ts">
/**
 * EventDetailsPanel - Redesigned Event Detail Display Component
 *
 * Features:
 * - Iridescent Glasmorphism Design
 * - Dynamische Sections basierend auf Event-Typ
 * - Metric Cards für Gerätestatus (Speicher, Signal, Laufzeit)
 * - RSSI Visualisierung
 * - Deutsche, menschenverständliche Nachrichten
 * - Collapsible JSON Details
 * - Mobile-responsive mit Swipe-to-Close
 * - Click-Outside to close (Desktop)
 * - ESC key to close
 *
 * SECTION MAPPING:
 * - Heartbeat:      Header, Zusammenfassung, Gerätestatus, JSON
 * - Sensor Data:    Header, Zusammenfassung, Messwert-Details, JSON
 * - Device Offline: Header, Zusammenfassung, Verbindungs-Info, JSON
 * - Config Response:Header, Zusammenfassung, Fehler-Details*, JSON
 * - Actuator:       Header, Zusammenfassung, Befehl-Details, JSON
 *
 * @emits close - When close button is clicked, ESC pressed, or click outside
 */

import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import type { UnifiedEvent } from '@/types/websocket-events'
import { getSeverityLabel } from '@/utils/errorCodeTranslator'
import { getEventIcon } from '@/utils/eventTypeIcons'
import { getEventCategory, getOperatorActionGuidance, transformEventMessage, formatUptime, formatMemory } from '@/utils/eventTransformer'
import { CONTRACT_OPERATOR_ACTION, extractIntegrationIssueSnapshot } from '@/utils/contractEventMapper'
import { auditApi } from '@/api/audit'
import RssiIndicator from './RssiIndicator.vue'
import EventTimeline from './EventTimeline.vue'
import TroubleshootingPanel from '@/components/error/TroubleshootingPanel.vue'
import {
  X,
  Copy,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  AlertOctagon,
  Info,
  GripHorizontal,
  ChevronDown,
  ChevronUp,
  MemoryStick,
  Wifi,
  Clock,
  Thermometer,
  Zap,
  Filter,
  FileText,
  GitBranch,
  ChevronRight,
  Loader2,
  Check,
} from 'lucide-vue-next'
import { createLogger } from '@/utils/logger'

const log = createLogger('EventDetails')

// ============================================================================
// Props & Emits
// ============================================================================

interface Props {
  event: UnifiedEvent
}

const props = defineProps<Props>()

const emit = defineEmits<{
  close: []
  'filter-device': [espId: string]
  'show-server-logs': [event: UnifiedEvent]
  'select-event': [event: UnifiedEvent]
}>()

// ============================================================================
// State
// ============================================================================

const jsonCopied = ref(false)
const jsonExpanded = ref(false)
const panelRef = ref<HTMLElement | null>(null)
const isMobile = ref(false)

// Swipe state
const touchStartY = ref(0)
const touchCurrentY = ref(0)
const isDragging = ref(false)
const dragOffset = ref(0)

// Click-Outside state
const isVisible = ref(false)

// Correlated events state (Phase 3)
const correlatedEvents = ref<UnifiedEvent[]>([])
const isLoadingCorrelated = ref(false)
const correlatedError = ref<string | null>(null)
const isCorrelatedSectionOpen = ref(true)

const hasCorrelationId = computed(() => Boolean(props.event?.correlation_id))


const correlationLatency = computed(() => {
  if (correlatedEvents.value.length < 2) return null
  const timestamps = correlatedEvents.value
    .map(e => new Date(e.timestamp).getTime())
    .sort((a, b) => a - b)
  return timestamps[timestamps.length - 1] - timestamps[0]
})

// ============================================================================
// Computed - Event Analysis
// ============================================================================

const eventCategory = computed(() => getEventCategory(props.event))
const transformedMessage = computed(() => transformEventMessage(props.event))
const operatorGuidance = computed(() => getOperatorActionGuidance(props.event))
const eventData = computed(() => (props.event.data || {}) as Record<string, unknown>)
const integrationIssue = computed(() => extractIntegrationIssueSnapshot(props.event))
const isNonFinalizableContractDrift = computed(() => {
  if (!integrationIssue.value.isIntegrationIssue) return false
  if (integrationIssue.value.issueType !== 'schema_mismatch') return false
  return integrationIssue.value.originalEventType === 'config_response'
    || integrationIssue.value.originalEventType === 'config_failed'
})

/**
 * Determine which sections to show based on event type
 */
const showDeviceStatus = computed(() => {
  return props.event.event_type === 'esp_health'
})

const showSensorData = computed(() => {
  return props.event.event_type === 'sensor_data' || props.event.event_type === 'sensor_health'
})

// Reserved for future use - actuator and connection sections
// const showActuatorData = computed(() => {
//   return ['actuator_status', 'actuator_response', 'actuator_alert'].includes(props.event.event_type)
// })
// const showConnectionInfo = computed(() => {
//   return ['device_offline', 'device_online', 'lwt_received'].includes(props.event.event_type)
// })

const showErrorDetails = computed(() => {
  const status = eventData.value.status as string | undefined
  return status === 'error' || status === 'failed' || props.event.error_code !== undefined
})

const showIntegrationIssue = computed(() => integrationIssue.value.isIntegrationIssue)
const showOperatorGuidance = computed(() => Boolean(operatorGuidance.value))

/**
 * Device Status Metrics (for heartbeat events)
 */
const deviceMetrics = computed(() => {
  if (!showDeviceStatus.value) return null

  const data = eventData.value
  return {
    heapFree: typeof data.heap_free === 'number' ? data.heap_free : 0,
    heapTotal: 320 * 1024, // ESP32 has ~320KB RAM
    wifiRssi: typeof data.wifi_rssi === 'number' ? data.wifi_rssi : 0,
    uptime: typeof data.uptime === 'number' ? data.uptime : 0,
    sensorCount: typeof data.sensor_count === 'number' ? data.sensor_count : 0,
    actuatorCount: typeof data.actuator_count === 'number' ? data.actuator_count : 0,
  }
})

/**
 * Calculate heap percentage used
 */
const heapPercentage = computed(() => {
  if (!deviceMetrics.value) return 0
  const used = deviceMetrics.value.heapTotal - deviceMetrics.value.heapFree
  return Math.round((used / deviceMetrics.value.heapTotal) * 100)
})

/**
 * Get heap status class
 */
const heapStatusClass = computed(() => {
  const pct = heapPercentage.value
  if (pct < 50) return 'good'
  if (pct < 75) return 'warning'
  return 'critical'
})

/**
 * Get RSSI quality class
 */
const rssiQualityClass = computed(() => {
  if (!deviceMetrics.value) return 'good'
  const rssi = deviceMetrics.value.wifiRssi
  if (rssi > -50) return 'good'
  if (rssi > -70) return 'fair'
  return 'weak'
})

/**
 * Sensor Data (for sensor events)
 */
const sensorData = computed(() => {
  if (!showSensorData.value) return null

  const data = eventData.value
  return {
    sensorType: (data.sensor_type || props.event.device_type || 'sensor') as string,
    value: typeof data.value === 'number' ? data.value : 0,
    unit: (data.unit || '') as string,
    quality: typeof data.quality === 'number' ? data.quality : undefined,
    rawMode: data.raw_mode as boolean | undefined,
  }
})

/**
 * Error Details (for error events)
 */
const errorDetails = computed(() => {
  if (!showErrorDetails.value) return null

  const data = eventData.value
  return {
    errorCode: props.event.error_code || data.error_code,
    configType: (data.type || data.config_type || 'Config') as string,
    status: (data.status || 'error') as string,
    message: (data.message || props.event.message || 'Unbekannter Fehler') as string,
    failedCount: typeof data.failed_count === 'number' ? data.failed_count : undefined,
    failures: data.failures as Array<{ gpio?: number; reason?: string }> | undefined,
    // Phase 3: Troubleshooting from enriched error_event
    troubleshooting: data.troubleshooting as string[] | undefined,
    userActionRequired: data.user_action_required as boolean | undefined,
    title: data.title as string | undefined,
  }
})

// ============================================================================
// Methods
// ============================================================================

function getSeverityIcon(severity: string) {
  switch (severity) {
    case 'critical': return AlertOctagon
    case 'error': return AlertCircle
    case 'warning': return AlertTriangle
    default: return Info
  }
}

function formatTimestamp(timestamp: string): string {
  return new Date(timestamp).toLocaleString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function formatEventTime(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString('de-DE', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function getSourceLabel(source: string): string {
  const labels: Record<string, string> = {
    esp: 'ESP via MQTT',
    mqtt: 'MQTT',
    server: 'Server',
    user: 'Benutzer',
    logic: 'Automation',
  }
  return labels[source] || source
}

// ============================================================================
// Mobile Detection & Swipe Handlers
// ============================================================================

function checkMobile() {
  isMobile.value = window.innerWidth < 768
}

function handleTouchStart(e: TouchEvent) {
  if (!isMobile.value) return

  const target = e.target as HTMLElement
  if (!target.closest('.details-panel__drag-handle')) return

  touchStartY.value = e.touches[0].clientY
  touchCurrentY.value = touchStartY.value
  isDragging.value = true
  dragOffset.value = 0
}

function handleTouchMove(e: TouchEvent) {
  if (!isDragging.value || !isMobile.value) return

  touchCurrentY.value = e.touches[0].clientY
  const deltaY = touchCurrentY.value - touchStartY.value

  if (deltaY > 0) {
    dragOffset.value = deltaY
    e.preventDefault()
  }
}

function handleTouchEnd() {
  if (!isDragging.value || !isMobile.value) return

  const deltaY = touchCurrentY.value - touchStartY.value

  if (deltaY > 150) {
    emit('close')
  }

  isDragging.value = false
  dragOffset.value = 0
}

function copyJson() {
  navigator.clipboard.writeText(JSON.stringify(props.event.data, null, 2))
  jsonCopied.value = true
  setTimeout(() => {
    jsonCopied.value = false
  }, 2000)
}

function copyEspId() {
  if (props.event.esp_id) {
    navigator.clipboard.writeText(props.event.esp_id)
  }
}

function handleClose() {
  emit('close')
}

function toggleJson() {
  jsonExpanded.value = !jsonExpanded.value
}

/**
 * Handle click on backdrop (outside panel)
 */
function handleBackdropClick(e: MouseEvent) {
  // Only close if clicking on the backdrop itself, not its children
  if (e.target === e.currentTarget) {
    handleClose()
  }
}

/**
 * Handle ESC key to close panel
 */
function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    handleClose()
  }
}

// ============================================================================
// Correlated Events (Phase 3)
// ============================================================================

async function loadCorrelatedEvents() {
  if (!props.event?.correlation_id) {
    correlatedEvents.value = []
    return
  }

  isLoadingCorrelated.value = true
  correlatedError.value = null

  try {
    const auditLogs = await auditApi.getCorrelatedEvents(props.event.correlation_id)
    // Transform AuditLog to minimal UnifiedEvent for display
    correlatedEvents.value = auditLogs.map(log => ({
      id: log.id,
      timestamp: log.created_at,
      event_type: log.event_type,
      severity: log.severity,
      source: log.source_type === 'esp' ? 'esp' as const : 'server' as const,
      esp_id: log.source_id || undefined,
      message: log.message || '',
      correlation_id: log.correlation_id || undefined,
      data: log.details || {},
    }))
  } catch {
    correlatedError.value = 'Fehler beim Laden der zugehörigen Events'
  } finally {
    isLoadingCorrelated.value = false
  }
}

function toggleCorrelatedSection() {
  isCorrelatedSectionOpen.value = !isCorrelatedSectionOpen.value
}

function formatLatency(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60000).toFixed(1)}min`
}

// State for copy feedback
const copiedCorrelationId = ref(false)

// Latenz-Badge Farbklasse
function getLatencyBadgeClass(ms: number): string {
  if (ms < 100) return 'latency-badge--fast'
  if (ms <= 500) return 'latency-badge--medium'
  return 'latency-badge--slow'
}

// Timeline Event-Auswahl
function handleTimelineEventSelect(selectedEvt: UnifiedEvent) {
  emit('select-event', selectedEvt)
}

// Korrelations-ID kopieren
async function copyCorrelationId() {
  if (!props.event?.correlation_id) return
  try {
    await navigator.clipboard.writeText(props.event.correlation_id)
    copiedCorrelationId.value = true
    setTimeout(() => {
      copiedCorrelationId.value = false
    }, 2000)
  } catch (err) {
    log.error('Failed to copy', err)
  }
}

watch(
  () => props.event?.correlation_id,
  (newId) => {
    if (newId) {
      loadCorrelatedEvents()
    } else {
      correlatedEvents.value = []
    }
  },
  { immediate: true }
)

// ============================================================================
// Lifecycle
// ============================================================================

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
  window.addEventListener('keydown', handleKeydown)

  // Delay visibility for animation
  requestAnimationFrame(() => {
    isVisible.value = true
  })
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <div class="event-details-wrapper">
  <!-- Backdrop for click-outside (Desktop only) -->
  <div
    v-if="!isMobile"
    class="details-backdrop"
    :class="{ 'details-backdrop--visible': isVisible }"
    @click="handleBackdropClick"
  />

  <!-- Panel -->
  <div
    ref="panelRef"
    class="details-panel"
    :class="[
      { 'is-dragging': isDragging },
      `details-panel--category-${eventCategory}`,
    ]"
    :style="{ transform: dragOffset > 0 ? `translateY(${dragOffset}px)` : undefined }"
    @touchstart="handleTouchStart"
    @touchmove="handleTouchMove"
    @touchend="handleTouchEnd"
  >
    <!-- Mobile: Drag Handle -->
    <div v-if="isMobile" class="details-panel__drag-handle">
      <GripHorizontal class="w-6 h-6" />
      <span class="details-panel__drag-hint">Nach unten wischen zum Schließen</span>
    </div>

    <!-- =========================================================================
         HEADER SECTION
         ========================================================================= -->
    <div class="panel-header">
      <div class="panel-header__left">
        <span class="severity-badge" :class="`severity-badge--${event.severity}`">
          <component :is="getSeverityIcon(event.severity)" class="w-3 h-3" />
          {{ getSeverityLabel(event.severity as any) }}
        </span>
        <div class="panel-header__title">
          <component :is="getEventIcon(event.event_type)" class="w-5 h-5" />
          <span>{{ transformedMessage.titleDE }}</span>
        </div>
      </div>
      <button class="panel-close" @click="handleClose">
        <X class="w-5 h-5" />
      </button>
    </div>

    <div class="panel-body">
      <!-- =========================================================================
           ZUSAMMENFASSUNG SECTION
           ========================================================================= -->
      <section class="panel-section" :class="{ 'panel-section--error': showErrorDetails }">
        <div class="section-header">
          <span class="section-title">Zusammenfassung</span>
        </div>
        <p class="summary-text" :class="{ 'summary-text--error': showErrorDetails }">
          <component
            v-if="showErrorDetails"
            :is="getSeverityIcon(event.severity)"
            class="w-4 h-4 inline-block mr-2"
          />
          {{ transformedMessage.description }}
        </p>
      </section>

      <section
        v-if="showOperatorGuidance && operatorGuidance"
        class="panel-section panel-section--operator"
        :class="`panel-section--operator-${operatorGuidance.classification}`"
      >
        <div class="section-header">
          <span class="section-title">Operator-Entscheidung</span>
        </div>
        <div class="operator-grid">
          <div class="operator-item">
            <span class="operator-label">Problemtyp</span>
            <span class="operator-value">
              {{ operatorGuidance.classification === 'integrationsproblem' ? 'Integrationsproblem' : 'Betriebsproblem' }}
            </span>
          </div>
          <div class="operator-item">
            <span class="operator-label">Prioritaet</span>
            <span class="operator-priority" :class="`operator-priority--${operatorGuidance.priority}`">
              {{ operatorGuidance.priority.toUpperCase() }}
            </span>
          </div>
          <div class="operator-item operator-item--full">
            <span class="operator-label">Ursache</span>
            <span class="operator-value">{{ operatorGuidance.cause }}</span>
          </div>
          <div class="operator-item operator-item--full">
            <span class="operator-label">Naechster Schritt</span>
            <span class="operator-action">{{ operatorGuidance.nextAction }}</span>
          </div>
        </div>
      </section>

      <!-- =========================================================================
           DETAILS SECTION (Zeitpunkt, Quelle, ESP-ID)
           ========================================================================= -->
      <section class="panel-section">
        <div class="section-header">
          <span class="section-title">Details</span>
        </div>
        <div class="details-grid">
          <div class="detail-item">
            <span class="detail-label">Zeitpunkt</span>
            <span class="detail-value">{{ formatTimestamp(event.timestamp) }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">Quelle</span>
            <span class="detail-value">{{ getSourceLabel(event.source) }}</span>
          </div>
          <div v-if="event.esp_id" class="detail-item detail-item--full">
            <span class="detail-label">ESP-ID</span>
            <div class="detail-value detail-value--copyable" @click="copyEspId">
              <span class="font-mono">{{ event.esp_id }}</span>
              <Copy class="w-3.5 h-3.5 copy-icon" />
            </div>
          </div>
          <div v-if="event.zone_name" class="detail-item">
            <span class="detail-label">Zone</span>
            <span class="detail-value">{{ event.zone_name }}</span>
          </div>
          <div v-if="event.gpio !== undefined" class="detail-item">
            <span class="detail-label">GPIO</span>
            <span class="detail-value font-mono">{{ event.gpio }}</span>
          </div>

          <!-- Action Buttons -->
          <div v-if="event.esp_id" class="detail-item detail-item--full detail-item--actions">
            <button
              class="action-btn action-btn--filter"
              @click="emit('filter-device', event.esp_id!)"
            >
              <Filter :size="14" />
              Alle Events von {{ event.esp_id }}
            </button>
            <button
              class="action-btn action-btn--logs"
              @click="emit('show-server-logs', event)"
            >
              <FileText :size="14" />
              {{ event.request_id ? 'Server-Logs (Request-ID)' : `Server-Logs um ${formatEventTime(event.timestamp)}` }}
            </button>
          </div>
        </div>
      </section>

      <section v-if="showIntegrationIssue" class="panel-section panel-section--integration">
        <div class="section-header">
          <span class="section-title">Integrationssignal</span>
        </div>
        <div class="integration-grid">
          <div class="integration-item">
            <span class="integration-label">Signaltyp</span>
            <span class="integration-value">
              {{ integrationIssue.issueType === 'schema_mismatch' ? 'Schema-Mismatch' : 'Unbekannter Event-Typ' }}
            </span>
          </div>
          <div v-if="isNonFinalizableContractDrift" class="integration-item">
            <span class="integration-label">Zustand</span>
            <span class="integration-action">Nicht finalisierbar wegen Contract-Verletzung</span>
          </div>
          <div v-if="integrationIssue.originalEventType" class="integration-item">
            <span class="integration-label">Original-Event</span>
            <span class="integration-value font-mono">{{ integrationIssue.originalEventType }}</span>
          </div>
          <div v-if="integrationIssue.reason" class="integration-item integration-item--full">
            <span class="integration-label">Grund</span>
            <span class="integration-value">{{ integrationIssue.reason }}</span>
          </div>
          <div class="integration-item integration-item--full">
            <span class="integration-label">Operator-Aktion</span>
            <span class="integration-action">{{ integrationIssue.operatorAction || CONTRACT_OPERATOR_ACTION }}</span>
          </div>
          <div v-if="integrationIssue.correlationId" class="integration-item integration-item--full">
            <span class="integration-label">Korrelations-ID</span>
            <span class="integration-value font-mono">{{ integrationIssue.correlationId }}</span>
          </div>
          <div v-if="integrationIssue.requestId" class="integration-item integration-item--full">
            <span class="integration-label">Request-ID</span>
            <span class="integration-value font-mono">{{ integrationIssue.requestId }}</span>
          </div>
          <div v-if="integrationIssue.rawContext" class="integration-item integration-item--full">
            <span class="integration-label">Rohkontext</span>
            <pre class="integration-json">{{ JSON.stringify(integrationIssue.rawContext, null, 2) }}</pre>
          </div>
        </div>
      </section>

      <!-- =========================================================================
           GERÄTESTATUS SECTION (Heartbeat Events)
           ========================================================================= -->
      <section v-if="showDeviceStatus && deviceMetrics" class="panel-section">
        <div class="section-header">
          <span class="section-title">Gerätestatus</span>
        </div>

        <!-- Metric Cards Row 1 -->
        <div class="metric-grid">
          <!-- Speicher Card -->
          <div class="metric-card">
            <div class="metric-header">
              <MemoryStick class="w-4 h-4" />
              <span>Speicher</span>
            </div>
            <div class="metric-value">{{ formatMemory(deviceMetrics.heapFree) }} frei</div>
            <div class="metric-bar">
              <div
                class="metric-bar__fill"
                :class="`metric-bar__fill--${heapStatusClass}`"
                :style="{ width: `${100 - heapPercentage}%` }"
              />
            </div>
            <div class="metric-sublabel">{{ 100 - heapPercentage }}% verfügbar</div>
          </div>

          <!-- Signal Card -->
          <div class="metric-card">
            <div class="metric-header">
              <Wifi class="w-4 h-4" />
              <span>Signal</span>
            </div>
            <div class="metric-value">
              <RssiIndicator :rssi="deviceMetrics.wifiRssi" :show-value="true" />
            </div>
            <div class="metric-sublabel" :class="`text-${rssiQualityClass}`">
              {{ rssiQualityClass === 'good' ? 'Ausgezeichnet' : rssiQualityClass === 'fair' ? 'Gut' : 'Schwach' }}
            </div>
          </div>

          <!-- Laufzeit Card -->
          <div class="metric-card">
            <div class="metric-header">
              <Clock class="w-4 h-4" />
              <span>Laufzeit</span>
            </div>
            <div class="metric-value">{{ formatUptime(deviceMetrics.uptime) }}</div>
          </div>
        </div>

        <!-- Metric Cards Row 2 -->
        <div class="metric-grid metric-grid--small">
          <div class="metric-card metric-card--compact">
            <div class="metric-header">
              <Thermometer class="w-4 h-4" />
              <span>Sensoren</span>
            </div>
            <div class="metric-value">{{ deviceMetrics.sensorCount }} aktiv</div>
          </div>

          <div class="metric-card metric-card--compact">
            <div class="metric-header">
              <Zap class="w-4 h-4" />
              <span>Aktoren</span>
            </div>
            <div class="metric-value">{{ deviceMetrics.actuatorCount }} aktiv</div>
          </div>
        </div>
      </section>

      <!-- =========================================================================
           SENSOR DATA SECTION
           ========================================================================= -->
      <section v-if="showSensorData && sensorData" class="panel-section">
        <div class="section-header">
          <span class="section-title">Messwert-Details</span>
        </div>
        <div class="sensor-display">
          <div class="sensor-value-large">
            {{ sensorData.value.toFixed(sensorData.sensorType === 'ph' ? 2 : 1) }}
            <span class="sensor-unit">{{ sensorData.unit }}</span>
          </div>
          <div class="sensor-meta">
            <span class="sensor-type">{{ sensorData.sensorType }}</span>
            <span v-if="sensorData.quality !== undefined" class="sensor-quality">
              Qualität: {{ sensorData.quality }}%
            </span>
            <span v-if="sensorData.rawMode" class="sensor-raw-badge">RAW</span>
          </div>
        </div>
      </section>

      <!-- =========================================================================
           ERROR DETAILS SECTION
           ========================================================================= -->
      <section v-if="showErrorDetails && errorDetails" class="panel-section panel-section--error-details">
        <div class="section-header">
          <span class="section-title">Fehler-Details</span>
        </div>

        <div v-if="errorDetails.errorCode" class="error-code-display">
          <span class="error-code-label">Fehler-Code</span>
          <span class="error-code-badge">{{ errorDetails.errorCode }}</span>
        </div>

        <div class="error-info">
          <div class="error-info-row">
            <span class="error-info-label">Beschreibung</span>
            <p class="error-info-text">{{ errorDetails.message }}</p>
          </div>

          <div v-if="errorDetails.configType" class="error-info-row">
            <span class="error-info-label">Config-Typ</span>
            <span class="error-info-value">{{ errorDetails.configType }}</span>
          </div>

          <div class="error-info-row">
            <span class="error-info-label">Status</span>
            <span class="error-status-badge error-status-badge--failed">
              Fehlgeschlagen
            </span>
          </div>

          <!-- Failed Items List -->
          <div v-if="errorDetails.failures && errorDetails.failures.length > 0" class="error-failures">
            <span class="error-info-label">Fehlgeschlagene Elemente</span>
            <ul class="failure-list">
              <li v-for="(failure, i) in errorDetails.failures" :key="i" class="failure-item">
                <span v-if="failure.gpio !== undefined" class="failure-gpio">GPIO {{ failure.gpio }}</span>
                <span v-if="failure.reason" class="failure-reason">{{ failure.reason }}</span>
              </li>
            </ul>
          </div>

          <!-- Phase 3: Troubleshooting Steps -->
          <TroubleshootingPanel
            v-if="errorDetails.troubleshooting && errorDetails.troubleshooting.length > 0"
            :steps="errorDetails.troubleshooting"
            :user-action-required="errorDetails.userActionRequired ?? false"
            :severity="event.severity"
            class="error-troubleshooting"
          />
        </div>
      </section>

      <!-- =========================================================================
           EVENT-VERLAUF (TIMELINE) SECTION (Phase 5.1)
           ========================================================================= -->
      <section v-if="hasCorrelationId" class="panel-section panel-section--correlated">
        <div class="correlated-header" @click="toggleCorrelatedSection">
          <div class="correlated-header__left">
            <GitBranch class="w-4 h-4" style="color: var(--color-info);" />
            <span class="correlated-header__title">Event-Verlauf</span>
            <span v-if="correlatedEvents.length > 1" class="correlated-header__count">
              {{ correlatedEvents.length }}
            </span>
          </div>
          <div class="correlated-header__right">
            <span
              v-if="correlationLatency !== null"
              class="latency-badge"
              :class="getLatencyBadgeClass(correlationLatency)"
            >
              <Clock class="w-3 h-3" />
              {{ formatLatency(correlationLatency) }}
            </span>
            <ChevronRight
              class="w-4 h-4 correlated-chevron"
              :class="{ 'correlated-chevron--open': isCorrelatedSectionOpen }"
            />
          </div>
        </div>

        <Transition name="slide">
          <div v-if="isCorrelatedSectionOpen" class="correlated-content">
            <!-- Loading -->
            <div v-if="isLoadingCorrelated" class="correlated-state">
              <Loader2 class="w-4 h-4 animate-spin" />
              <span>Lade Event-Verlauf...</span>
            </div>

            <!-- Error -->
            <div v-else-if="correlatedError" class="correlated-state correlated-state--error">
              <AlertCircle class="w-4 h-4" />
              <span>{{ correlatedError }}</span>
              <button class="retry-btn" @click="loadCorrelatedEvents">
                Erneut versuchen
              </button>
            </div>

            <!-- Timeline -->
            <EventTimeline
              v-else
              :events="correlatedEvents"
              :current-event-id="event.id"
              :total-latency-ms="correlationLatency"
              @select-event="handleTimelineEventSelect"
            />

            <!-- Correlation ID Footer -->
            <div class="correlation-id-footer">
              <span class="correlation-id-label">Korrelations-ID:</span>
              <code class="correlation-id-value">{{ event.correlation_id }}</code>
              <button
                class="copy-correlation-btn"
                @click="copyCorrelationId"
                :title="copiedCorrelationId ? 'Kopiert!' : 'ID kopieren'"
              >
                <Check v-if="copiedCorrelationId" class="w-3 h-3" />
                <Copy v-else class="w-3 h-3" />
              </button>
            </div>
          </div>
        </Transition>
      </section>

      <!-- =========================================================================
           TECHNISCHE DETAILS (JSON) SECTION
           ========================================================================= -->
      <section class="panel-section panel-section--json">
        <div class="json-toggle" role="button" tabindex="0" @click="toggleJson" @keydown.enter="toggleJson">
          <span class="json-toggle__label">
            <component :is="jsonExpanded ? ChevronUp : ChevronDown" class="w-4 h-4" />
            <span>Technische Details (JSON)</span>
          </span>
          <button class="json-copy-btn" @click.stop="copyJson">
            <component :is="jsonCopied ? CheckCircle2 : Copy" class="w-4 h-4" />
            {{ jsonCopied ? 'Kopiert!' : 'Kopieren' }}
          </button>
        </div>

        <Transition name="slide">
          <div v-if="jsonExpanded" class="json-content">
            <pre class="json-pre">{{ JSON.stringify(event.data, null, 2) }}</pre>
          </div>
        </Transition>
      </section>
    </div>
  </div>
  </div>
</template>

<style scoped>
/* ============================================================================
   DETAIL PANEL - Iridescent Glassmorphism Design
   ============================================================================ */
.details-panel {
  position: fixed;
  bottom: 0;
  left: 16rem;
  right: 0;
  max-height: 65vh;
  z-index: var(--z-modal);
  overflow-y: auto;
  transition: transform 0.15s ease-out;

  /* Iridescent Glassmorphism */
  background: rgba(15, 15, 20, 0.95);
  backdrop-filter: blur(20px);
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  box-shadow:
    0 -4px 24px rgba(0, 0, 0, 0.3),
    inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

.details-panel.is-dragging {
  transition: none;
}

/* Category-based top border accent */
.details-panel--category-esp-status {
  border-top-color: rgba(59, 130, 246, 0.3);
}

.details-panel--category-sensors {
  border-top-color: rgba(16, 185, 129, 0.3);
}

.details-panel--category-actuators {
  border-top-color: rgba(245, 158, 11, 0.3);
}

.details-panel--category-system {
  border-top-color: rgba(139, 92, 246, 0.3);
}

/* Drag Handle (Mobile only) */
.details-panel__drag-handle {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  padding: 0.75rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  cursor: grab;
  touch-action: none;
  color: var(--color-text-muted);
}

.details-panel__drag-handle:active {
  cursor: grabbing;
}

.details-panel__drag-hint {
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* ============================================================================
   HEADER
   ============================================================================ */
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  position: sticky;
  top: 0;
  background: rgba(15, 15, 20, 0.98);
  backdrop-filter: blur(12px);
  z-index: var(--z-dropdown);
}

.panel-header__left {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.panel-header__title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  font-size: 1rem;
  color: var(--color-text-primary);
}

.severity-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.625rem;
  border-radius: var(--radius-full);
  font-size: 0.6875rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.severity-badge--info {
  background: rgba(96, 165, 250, 0.15);
  color: var(--color-info);
  border: 1px solid rgba(96, 165, 250, 0.25);
}

.severity-badge--warning {
  background: rgba(245, 158, 11, 0.15);
  color: var(--color-warning);
  border: 1px solid rgba(245, 158, 11, 0.25);
}

.severity-badge--error {
  background: rgba(239, 68, 68, 0.15);
  color: var(--color-error);
  border: 1px solid rgba(239, 68, 68, 0.25);
}

.severity-badge--critical {
  background: rgba(220, 38, 38, 0.2);
  color: var(--color-error);
  border: 2px solid rgba(220, 38, 38, 0.4);
  animation: critical-badge-pulse 2s ease-in-out infinite;
}

@keyframes critical-badge-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.75; }
}

.panel-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.2s ease;
}

.panel-close:hover {
  background: rgba(255, 255, 255, 0.08);
  color: var(--color-text-primary);
  transform: rotate(90deg);
}

/* ============================================================================
   BODY & SECTIONS
   ============================================================================ */
.panel-body {
  padding: 1rem 1.5rem 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.panel-section {
  padding: 1rem;
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.panel-section--error {
  background: rgba(239, 68, 68, 0.05);
  border-color: rgba(239, 68, 68, 0.15);
}

.panel-section--error-details {
  background: rgba(239, 68, 68, 0.03);
  border-color: rgba(239, 68, 68, 0.12);
}

.panel-section--integration {
  background: rgba(139, 92, 246, 0.08);
  border-color: rgba(139, 92, 246, 0.25);
}

.panel-section--operator {
  background: rgba(255, 255, 255, 0.03);
}

.panel-section--operator-integrationsproblem {
  border-color: rgba(168, 85, 247, 0.35);
  background: rgba(168, 85, 247, 0.08);
}

.panel-section--operator-betriebsproblem {
  border-color: rgba(239, 68, 68, 0.24);
  background: rgba(239, 68, 68, 0.06);
}

.section-header {
  margin-bottom: 0.75rem;
}

.section-title {
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
}

.summary-text {
  font-size: 0.9375rem;
  color: var(--color-text-primary);
  line-height: 1.5;
  margin: 0;
}

.summary-text--error {
  color: var(--color-error);
}

/* ============================================================================
   DETAILS GRID
   ============================================================================ */
.details-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.75rem;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.625rem 0.75rem;
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.04);
}

.detail-item--full {
  grid-column: 1 / -1;
}

.detail-label {
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.detail-value {
  font-size: 0.875rem;
  color: var(--color-text-primary);
}

.detail-value--copyable {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  transition: color 0.15s;
}

.detail-value--copyable:hover {
  color: var(--color-info);
}

.detail-value--copyable .copy-icon {
  opacity: 0;
  transition: opacity 0.15s;
}

.detail-value--copyable:hover .copy-icon {
  opacity: 1;
}

.operator-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

.operator-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.625rem 0.75rem;
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.operator-item--full {
  grid-column: 1 / -1;
}

.operator-label {
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.operator-value {
  font-size: 0.875rem;
  color: var(--color-text-primary);
}

.operator-action {
  display: inline-flex;
  width: fit-content;
  padding: 0.25rem 0.5rem;
  border-radius: var(--radius-sm);
  background: rgba(239, 68, 68, 0.18);
  color: var(--color-text-primary);
  border: 1px solid rgba(239, 68, 68, 0.4);
  font-size: 0.8125rem;
  font-weight: 600;
}

.operator-priority {
  display: inline-flex;
  width: fit-content;
  padding: 0.1875rem 0.5rem;
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.03em;
}

.operator-priority--warning {
  background: rgba(251, 191, 36, 0.16);
  border: 1px solid rgba(251, 191, 36, 0.35);
  color: var(--color-warning);
}

.operator-priority--error {
  background: rgba(248, 113, 113, 0.16);
  border: 1px solid rgba(248, 113, 113, 0.35);
  color: var(--color-error);
}

.operator-priority--critical {
  background: rgba(220, 38, 38, 0.24);
  border: 1px solid rgba(248, 113, 113, 0.45);
  color: var(--color-error);
}

.integration-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

.integration-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.625rem 0.75rem;
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.integration-item--full {
  grid-column: 1 / -1;
}

.integration-label {
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.integration-value {
  font-size: 0.875rem;
  color: var(--color-text-primary);
}

.integration-action {
  display: inline-flex;
  width: fit-content;
  padding: 0.25rem 0.5rem;
  border-radius: var(--radius-sm);
  background: rgba(139, 92, 246, 0.2);
  color: var(--color-iridescent-3);
  border: 1px solid rgba(139, 92, 246, 0.35);
  font-size: 0.75rem;
  font-weight: 600;
}

.integration-json {
  margin: 0;
  padding: 0.625rem;
  border-radius: var(--radius-md);
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: var(--color-text-secondary);
  font-size: 0.75rem;
  line-height: 1.45;
  overflow-x: auto;
}

/* ============================================================================
   METRIC CARDS (Device Status)
   ============================================================================ */
.metric-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.metric-grid--small {
  grid-template-columns: repeat(2, 1fr);
  margin-bottom: 0;
}

.metric-card {
  padding: 0.875rem;
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.metric-card--compact {
  padding: 0.75rem;
}

.metric-header {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.metric-value {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.metric-bar {
  height: 4px;
  border-radius: var(--radius-xs);
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
  margin-top: 0.25rem;
}

.metric-bar__fill {
  height: 100%;
  border-radius: var(--radius-xs);
  transition: width 0.5s ease;
}

.metric-bar__fill--good { background: var(--color-success); }
.metric-bar__fill--warning { background: var(--color-warning); }
.metric-bar__fill--critical { background: var(--color-error); }

.metric-sublabel {
  font-size: 0.6875rem;
  color: var(--color-text-muted);
}

.text-good { color: var(--color-success); }
.text-fair { color: var(--color-warning); }
.text-weak { color: var(--color-error); }

/* ============================================================================
   SENSOR DATA DISPLAY
   ============================================================================ */
.sensor-display {
  text-align: center;
  padding: 1rem;
}

.sensor-value-large {
  font-size: 2.5rem;
  font-weight: 700;
  color: var(--color-text-primary);
  line-height: 1;
}

.sensor-unit {
  font-size: 1.25rem;
  font-weight: 500;
  color: var(--color-text-muted);
  margin-left: 0.25rem;
}

.sensor-meta {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  margin-top: 0.75rem;
}

.sensor-type {
  font-size: 0.75rem;
  color: var(--color-text-muted);
  text-transform: capitalize;
}

.sensor-quality {
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.sensor-raw-badge {
  font-size: 0.625rem;
  font-weight: 700;
  padding: 0.125rem 0.375rem;
  border-radius: var(--radius-xs);
  background: rgba(139, 92, 246, 0.15);
  color: var(--color-mock);
  text-transform: uppercase;
}

/* ============================================================================
   ERROR DETAILS
   ============================================================================ */
.error-code-display {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  margin-bottom: 1rem;
}

.error-code-label {
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--color-text-muted);
}

.error-code-badge {
  display: inline-block;
  padding: 0.5rem 0.75rem;
  border-radius: var(--radius-md);
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
  font-family: var(--font-mono, monospace);
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-error);
}

.error-info {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.error-info-row {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.error-info-label {
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--color-text-muted);
}

.error-info-text {
  font-size: 0.875rem;
  color: var(--color-text-secondary);
  margin: 0;
  line-height: 1.5;
}

.error-info-value {
  font-size: 0.875rem;
  color: var(--color-text-primary);
}

.error-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.5rem;
  border-radius: var(--radius-xs);
  font-size: 0.75rem;
  font-weight: 600;
}

.error-status-badge--failed {
  background: rgba(239, 68, 68, 0.15);
  color: var(--color-error);
}

.error-failures {
  margin-top: 0.5rem;
}

.failure-list {
  list-style: none;
  margin: 0.5rem 0 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.failure-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  border-radius: var(--radius-sm);
  background: rgba(239, 68, 68, 0.05);
  border: 1px solid rgba(239, 68, 68, 0.1);
  font-size: 0.8125rem;
}

.failure-gpio {
  font-family: var(--font-mono, monospace);
  color: var(--color-error);
  font-weight: 600;
}

.failure-reason {
  color: var(--color-text-secondary);
}

/* ============================================================================
   JSON SECTION
   ============================================================================ */
.panel-section--json {
  padding: 0;
  background: transparent;
  border: none;
}

.json-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 0.75rem 1rem;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.15s;
}

.json-toggle:hover {
  background: rgba(255, 255, 255, 0.04);
}

.json-toggle__label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.json-copy-btn {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.625rem;
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  cursor: pointer;
  transition: all 0.15s;
}

.json-copy-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: var(--color-text-primary);
}

/* === ACTION BUTTONS === */
.detail-item--actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding-top: 0.75rem;
  margin-top: 0.5rem;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 0.75rem;
  border-radius: var(--radius-sm);
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--color-text-secondary);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  cursor: pointer;
  transition: all 0.15s;
}

.action-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: var(--color-text-primary);
}

.action-btn--filter:hover {
  border-color: rgba(96, 165, 250, 0.3);
  color: var(--color-info);
}

.action-btn--logs:hover {
  border-color: rgba(139, 92, 246, 0.3);
  color: var(--color-mock);
}

@media (max-width: 480px) {
  .detail-item--actions {
    flex-direction: column;
  }

  .action-btn {
    width: 100%;
    justify-content: center;
  }
}

.json-content {
  margin-top: 0.5rem;
  border-radius: var(--radius-md);
  overflow: hidden;
}

.json-pre {
  margin: 0;
  padding: 1rem;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: var(--radius-md);
  font-family: var(--font-mono, monospace);
  font-size: 0.75rem;
  line-height: 1.5;
  color: var(--color-text-secondary);
  overflow-x: auto;
  white-space: pre;
}

/* Slide Transition */
.slide-enter-active,
.slide-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  max-height: 0;
}

.slide-enter-to,
.slide-leave-from {
  max-height: 500px;
}

/* ============================================================================
   UTILITY CLASSES
   ============================================================================ */
.font-mono {
  font-family: var(--font-mono, monospace);
}

/* ============================================================================
   MOBILE RESPONSIVE
   ============================================================================ */
@media (max-width: 768px) {
  .details-panel {
    position: fixed;
    inset: 0;
    left: 0;
    max-height: 100vh;
    border-radius: 0;
    border-top-left-radius: 1rem;
    border-top-right-radius: 1rem;
  }

  .panel-body {
    padding: 1rem;
    max-height: calc(100vh - 120px);
    overflow-y: auto;
  }

  .details-grid {
    grid-template-columns: 1fr;
  }

  .integration-grid {
    grid-template-columns: 1fr;
  }

  .operator-grid {
    grid-template-columns: 1fr;
  }

  .metric-grid {
    grid-template-columns: 1fr;
  }

  .metric-grid--small {
    grid-template-columns: repeat(2, 1fr);
  }

  .panel-close {
    width: 44px;
    height: 44px;
  }

  .sensor-value-large {
    font-size: 2rem;
  }
}

@media (max-width: 480px) {
  .panel-header {
    padding: 0.75rem 1rem;
  }

  .panel-header__title {
    font-size: 0.875rem;
    gap: 0.375rem;
  }

  .severity-badge {
    font-size: 0.625rem;
    padding: 0.1875rem 0.5rem;
  }

  .metric-card {
    padding: 0.625rem;
  }

  .metric-value {
    font-size: 1rem;
  }
}

/* ============================================================================
   BACKDROP (Click-Outside) - Desktop only
   ============================================================================ */
.details-backdrop {
  position: fixed;
  inset: 0;
  left: 16rem; /* Offset for sidebar */
  z-index: var(--z-modal-backdrop);
  background: transparent;
  opacity: 0;
  transition: opacity 0.2s ease, background-color 0.2s ease;
  cursor: pointer;
}

.details-backdrop--visible {
  opacity: 1;
  background: rgba(0, 0, 0, 0.15);
}

/* Sidebar adjustments for backdrop */
@media (max-width: 1024px) {
  .details-backdrop {
    left: 4rem; /* Collapsed sidebar width */
  }
}

@media (max-width: 768px) {
  .details-backdrop {
    display: none; /* Mobile uses swipe-to-close instead */
  }
}

/* ============================================================================
   CORRELATED EVENTS SECTION (Phase 3)
   ============================================================================ */
.correlated-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.15s;
}

.correlated-header:hover {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.08);
}

.correlated-header__left {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.correlated-header__title {
  font-weight: 500;
  font-size: 0.875rem;
}

.correlated-header__count {
  padding: 0.125rem 0.5rem;
  background: rgba(96, 165, 250, 0.15);
  border-radius: var(--radius-full);
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-info);
}

.correlated-header__right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

/* Latenz-Badge mit Farbcodierung */
.latency-badge {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.5rem;
  border-radius: var(--radius-xs);
  font-size: 0.75rem;
  font-weight: 600;
  font-family: monospace;
}

.latency-badge--fast {
  background: rgba(52, 211, 153, 0.15);
  color: var(--color-success);
}

.latency-badge--medium {
  background: rgba(251, 191, 36, 0.15);
  color: var(--color-warning);
}

.latency-badge--slow {
  background: rgba(248, 113, 113, 0.15);
  color: var(--color-error);
}

.correlated-chevron {
  color: var(--color-text-muted);
  transition: transform 0.2s;
}

.correlated-chevron--open {
  transform: rotate(90deg);
}

.correlated-content {
  padding: 0.75rem;
}

.correlated-state {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 1rem;
  font-size: 0.875rem;
  color: var(--color-text-muted);
}

.correlated-state--error {
  color: var(--color-error);
}

.correlation-id-footer {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  font-size: 0.75rem;
}

.correlation-id-label {
  color: var(--color-text-muted);
}

.correlation-id-value {
  flex: 1;
  padding: 0.125rem 0.375rem;
  background: rgba(255, 255, 255, 0.05);
  border-radius: var(--radius-xs);
  font-family: monospace;
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  word-break: break-all;
}

.copy-correlation-btn {
  padding: 0.375rem;
  background: rgba(255, 255, 255, 0.05);
  border: none;
  border-radius: var(--radius-xs);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  align-items: center;
}

.copy-correlation-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: var(--color-text-primary);
}

.retry-btn {
  margin-left: auto;
  padding: 0.25rem 0.75rem;
  font-size: 0.75rem;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: var(--radius-xs);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}

.retry-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: var(--color-text-primary);
}

</style>
