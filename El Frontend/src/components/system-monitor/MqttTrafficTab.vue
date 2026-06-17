<script setup lang="ts">
/**
 * MqttTrafficTab - MQTT Traffic Tab for System Monitor
 *
 * Features:
 * - Real-time MQTT message stream via WebSocket
 * - Topic pattern filter with MQTT wildcards (+ and #)
 * - Independent pause/resume state
 * - Buffer limit (1000 messages)
 * - JSON export functionality
 * - Mobile-responsive design
 *
 * @see El Trabajante/docs/Mqtt_Protocoll.md - MQTT Protocol Specification
 */

import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'
import type { WebSocketMessage } from '@/services/websocket'
import {
  Play,
  Pause,
  Trash2,
  Download,
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
  Radio,
  Filter,
  X
} from 'lucide-vue-next'
import { createLogger } from '@/utils/logger'

const log = createLogger('MqttTrafficTab')

// ============================================================================
// Types
// ============================================================================

interface MqttMessage {
  id: string
  timestamp: string
  type: string
  topic: string
  esp_id?: string
  gpio?: number
  payload: Record<string, unknown>
}

// ============================================================================
// Props
// ============================================================================

interface Props {
  espId?: string | null
}

const props = defineProps<Props>()

// ============================================================================
// Constants
// ============================================================================

const MAX_MESSAGES = 1000

// Message types from WebSocket (Server broadcasts)
const MESSAGE_TYPES = [
  'sensor_data',
  'actuator_status',
  'actuator_response',
  'actuator_alert',
  'esp_health',
  'config_response',
  'zone_assignment',
  'logic_execution',
  'system_event',
  'error_event',
] as const

// German labels for message types
const TYPE_LABELS: Record<string, string> = {
  sensor_data: 'Sensordaten',
  actuator_status: 'Aktor-Status',
  actuator_response: 'Aktor-Antwort',
  actuator_alert: 'Aktor-Alarm',
  esp_health: 'ESP-Heartbeat',
  config_response: 'Konfig-Antwort',
  zone_assignment: 'Zonen-Zuweisung',
  logic_execution: 'Regel-Ausf.',
  system_event: 'System',
  error_event: 'Fehler',
}

// ============================================================================
// State
// ============================================================================

const messages = ref<MqttMessage[]>([])
const isPaused = ref(false)
const expandedIds = ref<Set<string>>(new Set())
const copiedId = ref<string | null>(null)

// Filter state (independent from SystemMonitorView filters)
const showFilters = ref(false)
const filterEspId = ref('')
const filterTopicPattern = ref('')
const filterTypes = ref<Set<string>>(new Set(MESSAGE_TYPES))

// ============================================================================
// WebSocket
// ============================================================================

const { on, isConnected } = useWebSocket({
  autoConnect: true,
  autoReconnect: true,
})

const wsUnsubscribers: (() => void)[] = []

// ============================================================================
// Computed
// ============================================================================

const filteredMessages = computed(() => {
  let result = messages.value

  // Filter by ESP ID
  const espFilter = filterEspId.value || props.espId
  if (espFilter) {
    const espLower = espFilter.toLowerCase()
    result = result.filter(m => m.esp_id?.toLowerCase().includes(espLower))
  }

  // Filter by message type
  if (filterTypes.value.size < MESSAGE_TYPES.length) {
    result = result.filter(m => filterTypes.value.has(m.type))
  }

  // Filter by topic pattern (MQTT wildcards)
  if (filterTopicPattern.value) {
    const regex = mqttPatternToRegex(filterTopicPattern.value)
    result = result.filter(m => regex.test(m.topic))
  }

  return result
})

// ============================================================================
// Methods - MQTT Pattern Matching
// ============================================================================

/**
 * Convert MQTT topic pattern to JavaScript RegExp
 *
 * MQTT Wildcards:
 * - + (plus) = single-level wildcard, matches exactly one level
 * - # (hash) = multi-level wildcard, matches zero or more levels (must be at end)
 *
 * Examples:
 * - "kaiser/+/esp/+/sensor" → matches "kaiser/god/esp/ESP_12AB/sensor"
 * - "kaiser/god/esp/#" → matches "kaiser/god/esp/ESP_12AB/sensor/34/data"
 */
function mqttPatternToRegex(pattern: string): RegExp {
  // Escape special regex characters except + and #
  let regexPattern = pattern
    .replace(/[.*?^${}()|[\]\\]/g, '\\$&')
    // Replace + with single-level wildcard
    .replace(/\+/g, '[^/]+')
    // Replace # with multi-level wildcard
    .replace(/#/g, '.*')

  return new RegExp(`^${regexPattern}$`, 'i')
}

// ============================================================================
// Methods - Message Handling
// ============================================================================

function handleWebSocketMessage(message: WebSocketMessage) {
  if (isPaused.value) return

  try {
    const data = message.data as Record<string, unknown>

    const msg: MqttMessage = {
      id: `mqtt_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`,
      timestamp: new Date(message.timestamp * 1000).toISOString(),
      type: message.type || 'system_event',
      topic: buildTopic(message.type, data),
      esp_id: (data.esp_id as string) || (data.device_id as string) || undefined,
      gpio: typeof data.gpio === 'number' ? data.gpio : undefined,
      payload: data,
    }

    messages.value.unshift(msg)

    // Limit to MAX_MESSAGES
    if (messages.value.length > MAX_MESSAGES) {
      messages.value = messages.value.slice(0, MAX_MESSAGES)
    }
  } catch (e) {
    log.error(' Failed to process message:', e)
  }
}

/**
 * Reconstruct approximate MQTT topic from message data
 */
function buildTopic(type: string, data: Record<string, unknown>): string {
  const kaiserId = 'god' // Default kaiser_id
  const espId = (data.esp_id as string) || (data.device_id as string) || 'unknown'
  const gpio = data.gpio

  switch (type) {
    case 'sensor_data':
      return `kaiser/${kaiserId}/esp/${espId}/sensor/${gpio ?? '?'}/data`
    case 'actuator_status':
      return `kaiser/${kaiserId}/esp/${espId}/actuator/${gpio ?? '?'}/status`
    case 'actuator_response':
      return `kaiser/${kaiserId}/esp/${espId}/actuator/${gpio ?? '?'}/response`
    case 'actuator_alert':
      return `kaiser/${kaiserId}/esp/${espId}/actuator/${gpio ?? '?'}/alert`
    case 'esp_health':
      return `kaiser/${kaiserId}/esp/${espId}/system/heartbeat`
    case 'config_response':
      return `kaiser/${kaiserId}/esp/${espId}/config_response`
    case 'zone_assignment':
      return `kaiser/${kaiserId}/esp/${espId}/zone/ack`
    default:
      return `kaiser/${kaiserId}/system/${type}`
  }
}

// ============================================================================
// Methods - UI Actions
// ============================================================================

function togglePause() {
  isPaused.value = !isPaused.value
}

function clearMessages() {
  messages.value = []
  expandedIds.value.clear()
}

function toggleExpand(id: string) {
  if (expandedIds.value.has(id)) {
    expandedIds.value.delete(id)
  } else {
    expandedIds.value.add(id)
  }
}

function toggleTypeFilter(type: string) {
  if (filterTypes.value.has(type)) {
    filterTypes.value.delete(type)
  } else {
    filterTypes.value.add(type)
  }
}

function selectAllTypes() {
  filterTypes.value = new Set(MESSAGE_TYPES)
}

function clearTypeFilter() {
  filterTypes.value.clear()
}

async function copyPayload(msg: MqttMessage) {
  try {
    await navigator.clipboard.writeText(JSON.stringify(msg.payload, null, 2))
    copiedId.value = msg.id
    setTimeout(() => {
      copiedId.value = null
    }, 2000)
  } catch (e) {
    log.error(' Failed to copy:', e)
  }
}

function exportToJson() {
  const data = filteredMessages.value.map(m => ({
    timestamp: m.timestamp,
    type: m.type,
    topic: m.topic,
    esp_id: m.esp_id,
    gpio: m.gpio,
    payload: m.payload,
  }))

  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `mqtt-traffic-${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.json`
  a.click()
  URL.revokeObjectURL(url)
}

// ============================================================================
// Methods - Formatting
// ============================================================================

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('de-DE', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function getTypeColor(type: string): string {
  switch (type) {
    case 'sensor_data':
      return 'mqtt-badge--info'
    case 'actuator_status':
    case 'actuator_response':
      return 'mqtt-badge--success'
    case 'actuator_alert':
    case 'error_event':
      return 'mqtt-badge--danger'
    case 'esp_health':
      return 'mqtt-badge--gray'
    case 'config_response':
    case 'logic_execution':
      return 'mqtt-badge--warning'
    default:
      return 'mqtt-badge--gray'
  }
}

// ============================================================================
// Lifecycle
// ============================================================================

onMounted(() => {
  // Subscribe to all message types via WebSocket
  MESSAGE_TYPES.forEach(type => {
    wsUnsubscribers.push(on(type, handleWebSocketMessage))
  })
})

onUnmounted(() => {
  wsUnsubscribers.forEach(unsub => unsub())
  wsUnsubscribers.length = 0
})

// Sync ESP filter from props
watch(
  () => props.espId,
  (newEspId) => {
    if (newEspId) {
      filterEspId.value = newEspId
    }
  },
  { immediate: true }
)
</script>

<template>
  <div class="mqtt-traffic-tab">
    <!-- Header / Toolbar -->
    <div class="mqtt-toolbar">
      <div class="mqtt-toolbar__left">
        <!-- Connection Status -->
        <div class="mqtt-status">
          <Radio :class="['mqtt-status__icon', isConnected ? 'mqtt-status__icon--online' : 'mqtt-status__icon--offline']" />
          <span class="mqtt-status__text">{{ isConnected ? 'Live' : 'Offline' }}</span>
        </div>

        <!-- Message Count -->
        <span class="mqtt-toolbar__count">
          {{ filteredMessages.length }} / {{ messages.length }}
          <span v-if="isPaused" class="mqtt-toolbar__paused">(Pausiert)</span>
        </span>
      </div>

      <div class="mqtt-toolbar__right">
        <!-- Filter Toggle -->
        <button
          class="btn-ghost btn-sm"
          :class="{ 'btn-ghost--active': showFilters }"
          @click="showFilters = !showFilters"
        >
          <Filter class="w-4 h-4" />
          <span class="btn-label">Filter</span>
        </button>

        <!-- Pause/Resume -->
        <button
          class="btn-ghost btn-sm"
          :class="{ 'btn-ghost--active': isPaused }"
          @click="togglePause"
        >
          <component :is="isPaused ? Play : Pause" class="w-4 h-4" />
          <span class="btn-label">{{ isPaused ? 'Fortsetzen' : 'Pause' }}</span>
        </button>

        <!-- Export -->
        <button
          class="btn-ghost btn-sm"
          :disabled="filteredMessages.length === 0"
          @click="exportToJson"
        >
          <Download class="w-4 h-4" />
          <span class="btn-label">Export</span>
        </button>

        <!-- Clear -->
        <button
          class="btn-ghost btn-sm btn-ghost--danger"
          :disabled="messages.length === 0"
          @click="clearMessages"
        >
          <Trash2 class="w-4 h-4" />
          <span class="btn-label">Leeren</span>
        </button>
      </div>
    </div>

    <!-- Filter Panel -->
    <Transition name="slide-down">
      <div v-if="showFilters" class="mqtt-filters">
        <div class="mqtt-filters__header">
          <h4 class="mqtt-filters__title">Filter</h4>
          <button class="mqtt-filters__close" @click="showFilters = false">
            <X class="w-4 h-4" />
          </button>
        </div>

        <div class="mqtt-filters__grid">
          <!-- ESP ID Filter -->
          <div class="mqtt-filter-group">
            <label class="mqtt-filter-label">ESP-ID</label>
            <input
              v-model="filterEspId"
              type="text"
              class="mqtt-filter-input"
              placeholder="z.B. ESP_12AB"
            />
          </div>

          <!-- Topic Pattern Filter -->
          <div class="mqtt-filter-group">
            <label class="mqtt-filter-label">
              Topic-Pattern
              <span class="mqtt-filter-hint">(+ = ein Level, # = alle)</span>
            </label>
            <input
              v-model="filterTopicPattern"
              type="text"
              class="mqtt-filter-input"
              placeholder="z.B. kaiser/+/esp/+/sensor"
            />
          </div>

          <!-- Type Filter -->
          <div class="mqtt-filter-group mqtt-filter-group--full">
            <label class="mqtt-filter-label">
              Nachrichtentypen
              <span class="mqtt-filter-actions">
                <button @click="selectAllTypes">Alle</button>
                <button @click="clearTypeFilter">Keine</button>
              </span>
            </label>
            <div class="mqtt-type-chips">
              <button
                v-for="type in MESSAGE_TYPES"
                :key="type"
                :class="['mqtt-type-chip', filterTypes.has(type) && 'mqtt-type-chip--active']"
                @click="toggleTypeFilter(type)"
              >
                {{ TYPE_LABELS[type] || type }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Message List -->
    <div class="mqtt-messages">
      <!-- Empty State -->
      <div v-if="messages.length === 0" class="mqtt-empty">
        <Radio class="mqtt-empty__icon" />
        <p class="mqtt-empty__text">Warte auf Nachrichten...</p>
      </div>

      <!-- No Results -->
      <div v-else-if="filteredMessages.length === 0" class="mqtt-empty">
        <Filter class="mqtt-empty__icon" />
        <p class="mqtt-empty__text">Keine Nachrichten entsprechen den Filtern</p>
      </div>

      <!-- Message Items -->
      <div
        v-for="msg in filteredMessages"
        :key="msg.id"
        class="mqtt-message"
      >
        <!-- Message Header -->
        <div class="mqtt-message__header" @click="toggleExpand(msg.id)">
          <button class="mqtt-message__expand">
            <component :is="expandedIds.has(msg.id) ? ChevronDown : ChevronRight" class="w-4 h-4" />
          </button>

          <span class="mqtt-message__time">{{ formatTime(msg.timestamp) }}</span>

          <span :class="['mqtt-badge', getTypeColor(msg.type)]">
            {{ TYPE_LABELS[msg.type] || msg.type }}
          </span>

          <span v-if="msg.esp_id" class="mqtt-message__esp">
            {{ msg.esp_id }}
          </span>

          <span class="mqtt-message__topic">{{ msg.topic }}</span>
        </div>

        <!-- Expanded Payload -->
        <Transition name="expand">
          <div v-if="expandedIds.has(msg.id)" class="mqtt-message__payload">
            <div class="mqtt-payload__header">
              <span class="mqtt-payload__label">Payload</span>
              <button
                class="mqtt-payload__copy"
                @click.stop="copyPayload(msg)"
              >
                <component :is="copiedId === msg.id ? Check : Copy" class="w-3.5 h-3.5" />
                {{ copiedId === msg.id ? 'Kopiert!' : 'Kopieren' }}
              </button>
            </div>
            <pre class="mqtt-payload__content">{{ JSON.stringify(msg.payload, null, 2) }}</pre>
          </div>
        </Transition>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mqtt-traffic-tab {
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* =============================================================================
   Toolbar
   ============================================================================= */
.mqtt-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.75rem 1rem;
  background-color: var(--color-bg-secondary);
  border-bottom: 1px solid var(--glass-border);
  flex-wrap: wrap;
}

.mqtt-toolbar__left,
.mqtt-toolbar__right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.mqtt-status {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.mqtt-status__icon {
  width: 1rem;
  height: 1rem;
}

.mqtt-status__icon--online {
  color: var(--color-success);
}

.mqtt-status__icon--offline {
  color: var(--color-danger);
}

.mqtt-status__text {
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--color-text-secondary);
}

.mqtt-toolbar__count {
  font-size: 0.8125rem;
  color: var(--color-text-muted);
}

.mqtt-toolbar__paused {
  color: var(--color-warning);
  margin-left: 0.25rem;
}

.btn-ghost--active {
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.btn-ghost--danger:hover {
  color: var(--color-danger);
}

.btn-label {
  display: none;
}

@media (min-width: 768px) {
  .btn-label {
    display: inline;
    margin-left: 0.375rem;
  }
}

/* =============================================================================
   Filter Panel
   ============================================================================= */
.mqtt-filters {
  padding: 1rem;
  background-color: var(--color-bg-tertiary);
  border-bottom: 1px solid var(--glass-border);
}

.mqtt-filters__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}

.mqtt-filters__title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}

.mqtt-filters__close {
  padding: 0.25rem;
  color: var(--color-text-muted);
  background: none;
  border: none;
  cursor: pointer;
}

.mqtt-filters__close:hover {
  color: var(--color-text-primary);
}

.mqtt-filters__grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.75rem;
}

@media (min-width: 768px) {
  .mqtt-filters__grid {
    grid-template-columns: 1fr 1fr;
  }
}

.mqtt-filter-group {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.mqtt-filter-group--full {
  grid-column: 1 / -1;
}

.mqtt-filter-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.025em;
}

.mqtt-filter-hint {
  font-weight: 400;
  text-transform: none;
  color: var(--color-text-muted);
}

.mqtt-filter-actions {
  margin-left: auto;
  display: flex;
  gap: 0.5rem;
}

.mqtt-filter-actions button {
  font-size: 0.6875rem;
  color: var(--color-primary);
  background: none;
  border: none;
  cursor: pointer;
  text-transform: none;
}

.mqtt-filter-actions button:hover {
  text-decoration: underline;
}

.mqtt-filter-input {
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  background-color: var(--color-bg-primary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
}

.mqtt-filter-input::placeholder {
  color: var(--color-text-muted);
}

.mqtt-filter-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px var(--color-primary-alpha);
}

.mqtt-type-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}

.mqtt-type-chip {
  padding: 0.25rem 0.625rem;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--color-text-muted);
  background-color: var(--color-bg-primary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-full);
  cursor: pointer;
  transition: all 0.15s;
}

.mqtt-type-chip:hover {
  border-color: var(--color-text-muted);
}

.mqtt-type-chip--active {
  color: var(--color-primary);
  background-color: var(--color-primary-alpha);
  border-color: var(--color-primary);
}

/* =============================================================================
   Message List
   ============================================================================= */
.mqtt-messages {
  flex: 1;
  overflow-y: auto;
}

.mqtt-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 2rem;
  text-align: center;
}

.mqtt-empty__icon {
  width: 3rem;
  height: 3rem;
  color: var(--color-text-muted);
  opacity: 0.3;
  margin-bottom: 0.75rem;
}

.mqtt-empty__text {
  font-size: 0.875rem;
  color: var(--color-text-muted);
  margin: 0;
}

.mqtt-message {
  border-bottom: 1px solid var(--glass-border);
}

.mqtt-message:hover {
  background-color: var(--color-bg-secondary);
}

.mqtt-message__header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 1rem;
  cursor: pointer;
}

.mqtt-message__expand {
  padding: 0;
  color: var(--color-text-muted);
  background: none;
  border: none;
  cursor: pointer;
  flex-shrink: 0;
}

.mqtt-message__time {
  font-size: 0.75rem;
  font-family: var(--font-mono);
  color: var(--color-text-muted);
  flex-shrink: 0;
  width: 4.5rem;
}

.mqtt-badge {
  display: inline-flex;
  align-items: center;
  padding: 0.125rem 0.5rem;
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.025em;
  border-radius: var(--radius-full);
  flex-shrink: 0;
}

.mqtt-badge--info {
  background-color: var(--color-info-bg);
  color: var(--color-info);
}

.mqtt-badge--success {
  background-color: var(--color-success-bg);
  color: var(--color-success);
}

.mqtt-badge--warning {
  background-color: var(--color-warning-bg);
  color: var(--color-warning);
}

.mqtt-badge--danger {
  background-color: var(--color-error-bg);
  color: var(--color-error);
}

.mqtt-badge--gray {
  background-color: color-mix(in srgb, var(--color-text-muted) 15%, transparent);
  color: var(--color-text-muted);
}

.mqtt-message__esp {
  font-size: 0.75rem;
  font-family: var(--font-mono);
  color: var(--color-text-secondary);
  flex-shrink: 0;
}

.mqtt-message__topic {
  flex: 1;
  font-size: 0.8125rem;
  font-family: var(--font-mono);
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* =============================================================================
   Payload
   ============================================================================= */
.mqtt-message__payload {
  padding: 0 1rem 0.75rem 2.5rem;
}

.mqtt-payload__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.375rem;
}

.mqtt-payload__label {
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
}

.mqtt-payload__copy {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.5rem;
  font-size: 0.6875rem;
  color: var(--color-text-muted);
  background: none;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-xs);
  cursor: pointer;
  transition: all 0.15s;
}

.mqtt-payload__copy:hover {
  color: var(--color-text-primary);
  border-color: var(--color-text-muted);
}

.mqtt-payload__content {
  padding: 0.75rem;
  font-size: 0.75rem;
  font-family: var(--font-mono);
  line-height: 1.5;
  color: var(--color-text-secondary);
  background-color: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}

/* =============================================================================
   Transitions
   ============================================================================= */
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all 0.2s ease-out;
}

.slide-down-enter-from,
.slide-down-leave-to {
  opacity: 0;
  transform: translateY(-0.5rem);
}

.expand-enter-active,
.expand-leave-active {
  transition: all 0.15s ease-out;
}

.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  transform: translateY(-0.25rem);
}

/* =============================================================================
   Mobile Responsive
   ============================================================================= */
@media (max-width: 640px) {
  .mqtt-toolbar {
    padding: 0.5rem;
  }

  .mqtt-message__header {
    padding: 0.5rem;
    flex-wrap: wrap;
  }

  .mqtt-message__time {
    order: 1;
    width: auto;
  }

  .mqtt-badge {
    order: 2;
  }

  .mqtt-message__expand {
    order: 0;
  }

  .mqtt-message__esp {
    display: none;
  }

  .mqtt-message__topic {
    order: 3;
    width: 100%;
    margin-top: 0.25rem;
    padding-left: 1.5rem;
    font-size: 0.75rem;
  }

  .mqtt-message__payload {
    padding-left: 1rem;
    padding-right: 0.5rem;
  }
}
</style>
