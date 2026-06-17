<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Activity, BookOpen, LineChart } from 'lucide-vue-next'
import BaseModal from '@/shared/design/primitives/BaseModal.vue'
import SensorConfigPanel from '@/components/esp/SensorConfigPanel.vue'
import ActuatorConfigPanel from '@/components/esp/ActuatorConfigPanel.vue'
import { useLogicStore } from '@/shared/stores/logic.store'
import { useEspStore } from '@/stores/esp'
import { sensorsApi } from '@/api/sensors'
import { extractSensorConditions } from '@/types/logic'
import type { SensorCondition } from '@/types/logic'
import type { SensorReading, SensorStats, SensorDataResolution } from '@/types'

type WizardMode = 'sensor' | 'actuator'
type WizardTab = 'settings' | 'rules' | 'history'

const props = defineProps<{
  open: boolean
  espId: string
  gpio: number
  sensorType?: string
  unit?: string
  configId?: string
  actuatorType?: string
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'close'): void
  (e: 'deleted'): void
  (e: 'saved'): void
  (e: 'open-esp-settings', payload: { espId: string }): void
}>()

const logicStore = useLogicStore()
const espStore = useEspStore()

const mode = computed<WizardMode>(() => props.actuatorType ? 'actuator' : 'sensor')
const activeTab = ref<WizardTab>('settings')

const actuatorName = computed<string | null>(() => {
  if (mode.value !== 'actuator') return null
  const device = espStore.devices.find(d => espStore.getDeviceId(d) === props.espId)
  const actuators = (device?.actuators as { gpio: number; name?: string | null }[]) || []
  const act = actuators.find(a => a.gpio === props.gpio)
  const name = typeof act?.name === 'string' ? act.name.trim() : ''
  return name || null
})

const modalTitle = computed(() => {
  if (mode.value === 'sensor') return `GPIO ${props.gpio} · ${props.sensorType ?? 'Sensor'}`
  return actuatorName.value ?? `GPIO ${props.gpio} · ${props.actuatorType ?? 'Aktor'}`
})

watch(() => props.open, (open) => {
  if (open) {
    activeTab.value = 'settings'
    if (mode.value === 'sensor') loadHistory()
  } else {
    historyReadings.value = []
    historyStats.value = null
    historyError.value = null
  }
})

// =============================================================================
// Tab 2 — Logic Rules
// =============================================================================

const relevantRules = computed(() =>
  logicStore.rules.filter(rule =>
    extractSensorConditions(rule.conditions).some(
      (c: SensorCondition) => c.esp_id === props.espId && c.gpio === props.gpio
    )
  )
)

// =============================================================================
// Tab 3 — Sensor History
// =============================================================================

const RESOLUTIONS: { value: SensorDataResolution; label: string }[] = [
  { value: 'raw', label: 'Raw' },
  { value: '5m', label: '5m' },
  { value: '1h', label: '1h' },
  { value: '1d', label: '1d' },
]

const historyResolution = ref<SensorDataResolution>('1h')
const historyReadings = ref<SensorReading[]>([])
const historyStats = ref<SensorStats | null>(null)
const historyLoading = ref(false)
const historyError = ref<string | null>(null)

async function loadHistory() {
  if (mode.value !== 'sensor') return
  historyLoading.value = true
  historyError.value = null
  try {
    const [dataRes, statsRes] = await Promise.all([
      sensorsApi.queryData({
        esp_id: props.espId,
        gpio: props.gpio,
        sensor_type: props.sensorType,
        resolution: historyResolution.value,
        limit: 200,
      }),
      sensorsApi.getStats(props.espId, props.gpio, {
        sensor_type: props.sensorType,
      }),
    ])
    historyReadings.value = dataRes.readings
    historyStats.value = statsRes.stats
  } catch (e) {
    historyError.value = e instanceof Error ? e.message : 'Fehler beim Laden'
  } finally {
    historyLoading.value = false
  }
}

watch(historyResolution, () => {
  if (props.open && mode.value === 'sensor') loadHistory()
})

// SVG Sparkline
const SPARK_W = 360
const SPARK_H = 64

const sparklinePoints = computed<string>(() => {
  const readings = historyReadings.value
  if (readings.length < 2) return ''
  const values = readings.map(r => r.processed_value ?? r.raw_value)
  const minVal = Math.min(...values)
  const maxVal = Math.max(...values)
  const range = maxVal - minVal || 1
  return readings.map((r, i) => {
    const x = (i / (readings.length - 1)) * SPARK_W
    const val = r.processed_value ?? r.raw_value
    const y = SPARK_H - ((val - minVal) / range) * (SPARK_H - 4) - 2
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
})

function fmt(v: number | null | undefined): string {
  if (v == null) return '—'
  return v.toFixed(2)
}

function handleClose() {
  emit('update:open', false)
  emit('close')
}

function handleDeleted() {
  emit('deleted')
  handleClose()
}

function handleSaved() {
  emit('saved')
  handleClose()
}
</script>

<template>
  <BaseModal
    :open="open"
    :title="modalTitle"
    max-width="max-w-3xl"
    show-close
    close-on-overlay
    close-on-escape
    @update:open="emit('update:open', $event)"
    @close="handleClose"
  >
    <!-- Actuator subtitle: ESP · GPIO (secondary context below name title) -->
    <p v-if="mode === 'actuator' && actuatorName" class="cwm-subtitle">
      {{ espId }} · GPIO {{ gpio }}
    </p>

    <!-- Tab Bar -->
    <div class="cwm-tabs">
      <button
        class="cwm-tab"
        :class="{ 'cwm-tab--active': activeTab === 'settings' }"
        @click="activeTab = 'settings'"
      >
        <Activity class="cwm-tab__icon" :size="14" />
        Einstellungen
      </button>
      <button
        class="cwm-tab"
        :class="{ 'cwm-tab--active': activeTab === 'rules' }"
        @click="activeTab = 'rules'"
      >
        <BookOpen class="cwm-tab__icon" :size="14" />
        Regeln
        <span v-if="relevantRules.length > 0" class="cwm-tab__badge">{{ relevantRules.length }}</span>
      </button>
      <button
        v-if="mode === 'sensor'"
        class="cwm-tab"
        :class="{ 'cwm-tab--active': activeTab === 'history' }"
        @click="activeTab = 'history'"
      >
        <LineChart class="cwm-tab__icon" :size="14" />
        Verlauf
      </button>
    </div>

    <!-- Tab 1: Settings -->
    <div v-show="activeTab === 'settings'" class="cwm-panel">
      <SensorConfigPanel
        v-if="mode === 'sensor' && espId && gpio !== undefined"
        :esp-id="espId"
        :gpio="gpio"
        :sensor-type="sensorType ?? ''"
        :unit="unit"
        :config-id="configId"
        :show-metadata="false"
        @deleted="handleDeleted"
        @saved="handleSaved"
        @open-esp-settings="emit('open-esp-settings', $event)"
      />
      <ActuatorConfigPanel
        v-else-if="mode === 'actuator' && espId && gpio !== undefined"
        :esp-id="espId"
        :gpio="gpio"
        :actuator-type="actuatorType ?? 'relay'"
        :show-metadata="false"
        @deleted="handleDeleted"
        @saved="handleSaved"
        @open-esp-settings="emit('open-esp-settings', $event)"
      />
    </div>

    <!-- Tab 2: Logic Rules -->
    <div v-show="activeTab === 'rules'" class="cwm-panel cwm-panel--rules">
      <div v-if="relevantRules.length === 0" class="cwm-empty">
        <p>Keine Automatisierungsregeln für {{ mode === 'actuator' ? 'diesen Aktor' : 'diesen Sensor' }} gefunden.</p>
        <p class="cwm-empty-hint">Regeln können unter <strong>Regeln</strong> im Hauptmenü angelegt werden.</p>
      </div>
      <ul v-else class="cwm-rule-list">
        <li
          v-for="rule in relevantRules"
          :key="rule.id"
          class="cwm-rule-item"
          :class="{ 'cwm-rule-item--disabled': !rule.enabled }"
        >
          <div class="cwm-rule-item__header">
            <span
              class="cwm-rule-status"
              :class="rule.enabled ? 'cwm-rule-status--enabled' : 'cwm-rule-status--disabled'"
            />
            <span class="cwm-rule-item__name">{{ rule.name }}</span>
            <span v-if="rule.is_critical" class="cwm-rule-critical">kritisch</span>
          </div>
          <p v-if="rule.description" class="cwm-rule-item__desc">{{ rule.description }}</p>
        </li>
      </ul>
    </div>

    <!-- Tab 3: History (sensors only) -->
    <div v-if="mode === 'sensor'" v-show="activeTab === 'history'" class="cwm-panel cwm-panel--history">
      <!-- Resolution Selector -->
      <div class="cwm-resolution">
        <button
          v-for="r in RESOLUTIONS"
          :key="r.value"
          class="cwm-resolution__btn"
          :class="{ 'cwm-resolution__btn--active': historyResolution === r.value }"
          @click="historyResolution = r.value"
        >
          {{ r.label }}
        </button>
      </div>

      <!-- Loading / Error -->
      <div v-if="historyLoading" class="cwm-history-loading">Lade Verlauf…</div>
      <div v-else-if="historyError" class="cwm-history-error">{{ historyError }}</div>
      <div v-else-if="historyReadings.length === 0" class="cwm-empty">Keine Daten vorhanden.</div>
      <template v-else>
        <!-- Sparkline -->
        <div class="cwm-sparkline-wrap">
          <svg
            class="cwm-sparkline"
            :viewBox="`0 0 ${SPARK_W} ${SPARK_H}`"
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            <polyline
              class="cwm-sparkline__line"
              :points="sparklinePoints"
              fill="none"
            />
          </svg>
        </div>

        <!-- Stats Row -->
        <div v-if="historyStats" class="cwm-stats">
          <div class="cwm-stat">
            <span class="cwm-stat__label">Min</span>
            <span class="cwm-stat__value">{{ fmt(historyStats.min_value) }} {{ unit }}</span>
          </div>
          <div class="cwm-stat">
            <span class="cwm-stat__label">Avg</span>
            <span class="cwm-stat__value">{{ fmt(historyStats.avg_value) }} {{ unit }}</span>
          </div>
          <div class="cwm-stat">
            <span class="cwm-stat__label">Max</span>
            <span class="cwm-stat__value">{{ fmt(historyStats.max_value) }} {{ unit }}</span>
          </div>
          <div class="cwm-stat">
            <span class="cwm-stat__label">Messungen</span>
            <span class="cwm-stat__value">{{ historyStats.reading_count }}</span>
          </div>
        </div>
      </template>
    </div>
  </BaseModal>
</template>

<style scoped>
/* ── Actuator subtitle (GPIO context line below name title) ─────────────── */
.cwm-subtitle {
  padding: 0 1rem var(--space-2);
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  font-family: var(--font-mono);
}

/* ── Tab Bar ─────────────────────────────────────────────────────────────── */
.cwm-tabs {
  display: flex;
  gap: 0;
  padding: 0 1rem;
  border-bottom: 1px solid var(--glass-border);
  background: var(--glass-bg-l1);
  flex-shrink: 0;
}

.cwm-tab {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.625rem 1rem;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-muted);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: color var(--transition-fast), border-color var(--transition-fast), background var(--transition-fast);
  white-space: nowrap;
  position: relative;
  min-height: 44px;
}

.cwm-tab:hover {
  color: var(--color-text-secondary);
  background: rgba(255, 255, 255, 0.03);
}

.cwm-tab--active {
  color: var(--color-iridescent-1);
  border-bottom-color: var(--color-iridescent-1);
  background: rgba(96, 165, 250, 0.04);
}

.cwm-tab__icon {
  flex-shrink: 0;
  opacity: 0.7;
}

.cwm-tab--active .cwm-tab__icon {
  opacity: 1;
}

.cwm-tab__badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 0.3rem;
  font-size: 0.65rem;
  font-weight: 700;
  color: var(--color-bg-primary);
  background: var(--color-iridescent-1);
  border-radius: var(--radius-full);
}

/* ── Panel ─────────────────────────────────────────────────────────────── */
.cwm-panel {
  overflow-y: auto;
  max-height: calc(90vh - 160px);
}

.cwm-panel--rules,
.cwm-panel--history {
  padding: 1rem;
}

/* ── Empty / Loading / Error ───────────────────────────────────────────── */
.cwm-empty {
  padding: 2rem;
  text-align: center;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.cwm-empty p {
  margin: 0;
}

.cwm-empty-hint {
  margin-top: var(--space-2) !important;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.cwm-history-loading,
.cwm-history-error {
  padding: 1.5rem;
  text-align: center;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.cwm-history-error {
  color: var(--color-danger);
}

/* ── Rules List ──────────────────────────────────────────────────────── */
.cwm-rule-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  list-style: none;
  padding: 0;
  margin: 0;
}

.cwm-rule-item {
  padding: 0.625rem 0.75rem;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
}

.cwm-rule-item--disabled {
  opacity: 0.5;
}

.cwm-rule-item__header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.cwm-rule-item__name {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  flex: 1;
  min-width: 0;
}

.cwm-rule-item__desc {
  margin: 0.25rem 0 0 1.125rem;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  line-height: 1.4;
}

.cwm-rule-status {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
}

.cwm-rule-status--enabled {
  background: var(--color-success);
  box-shadow: 0 0 4px var(--color-success);
}

.cwm-rule-status--disabled {
  background: var(--color-text-muted);
}

.cwm-rule-critical {
  font-size: 0.6rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-danger);
  padding: 0.1rem 0.375rem;
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}

/* ── History ─────────────────────────────────────────────────────────── */
.cwm-resolution {
  display: flex;
  gap: 0.25rem;
  margin-bottom: 0.75rem;
}

.cwm-resolution__btn {
  padding: 0.25rem 0.625rem;
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-muted);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.cwm-resolution__btn:hover {
  color: var(--color-text-primary);
}

.cwm-resolution__btn--active {
  color: var(--color-iridescent-1);
  border-color: var(--color-iridescent-1);
  background: rgba(167, 139, 250, 0.1);
}

.cwm-sparkline-wrap {
  width: 100%;
  height: 96px;
  background: var(--glass-bg-l1);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  overflow: hidden;
  margin-bottom: 1rem;
}

.cwm-sparkline {
  width: 100%;
  height: 100%;
}

.cwm-sparkline__line {
  stroke: var(--color-iridescent-2);
  stroke-width: 1.5;
  vector-effect: non-scaling-stroke;
}

/* ── Stats Row ──────────────────────────────────────────────────────── */
.cwm-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.625rem;
}

.cwm-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0.75rem 0.5rem;
  background: var(--glass-bg-l1);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  gap: 0.25rem;
}

.cwm-stat__label {
  font-size: 0.6rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
}

.cwm-stat__value {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  margin-top: 0.125rem;
}
</style>
