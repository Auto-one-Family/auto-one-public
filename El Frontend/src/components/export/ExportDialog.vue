<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import BaseModal from '@/shared/design/primitives/BaseModal.vue'
import { Download, AlertTriangle, ChevronRight, ChevronLeft, Check } from 'lucide-vue-next'
import { useAuthStore } from '@/shared/stores/auth.store'
import type { SensorDataResolution } from '@/types'

// ──────────────────────────────────────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────────────────────────────────────

interface ColumnOption {
  key: string
  label: string
  visible: boolean
}

interface Props {
  open: boolean
  mode: 'sensor' | 'table'
  // sensor mode
  espId?: string
  gpio?: number
  sensorType?: string
  sensorName?: string
  zoneName?: string
  defaultStartTime?: string
  defaultEndTime?: string
  // table mode
  tableName?: string
  tableDisplayName?: string
  hasTimestamp?: boolean
  tableColumns?: ColumnOption[]
}

// ──────────────────────────────────────────────────────────────────────────────
// Constants
// ──────────────────────────────────────────────────────────────────────────────

const TIME_PRESETS = [
  { label: 'Letzte 1 Stunde', hours: 1 },
  { label: 'Letzte 6 Stunden', hours: 6 },
  { label: 'Letzte 24 Stunden', hours: 24 },
  { label: 'Letzte 7 Tage', hours: 168 },
  { label: 'Letzte 30 Tage', hours: 720 },
] as const

const RESOLUTION_OPTIONS: Array<{ label: string; value: SensorDataResolution }> = [
  { label: 'Rohdaten', value: 'raw' },
  { label: '5 Minuten', value: '5m' },
  { label: '1 Stunde', value: '1h' },
  { label: '1 Tag', value: '1d' },
]

const SENSOR_COLUMNS: ColumnOption[] = [
  { key: 'timestamp', label: 'Zeitstempel', visible: true },
  { key: 'processed_value', label: 'Messwert', visible: true },
  { key: 'raw_value', label: 'Rohwert', visible: false },
  { key: 'unit', label: 'Einheit', visible: true },
  { key: 'quality', label: 'Qualität', visible: true },
  { key: 'zone_id', label: 'Zone-ID', visible: false },
  { key: 'subzone_id', label: 'Subzone-ID', visible: false },
  { key: 'esp_id', label: 'ESP-ID', visible: false },
]

// Tables that carry a timestamp column (matches server auto-default logic)
const TIMESTAMP_TABLES = new Set([
  'sensor_data',
  'actuator_history',
  'logic_execution_history',
  'audit_logs',
  'esp_heartbeat_logs',
  'diagnostic_reports',
])

// ──────────────────────────────────────────────────────────────────────────────
// Setup
// ──────────────────────────────────────────────────────────────────────────────

const props = withDefaults(defineProps<Props>(), {
  hasTimestamp: undefined,
})

const emit = defineEmits<{
  close: []
  'update:open': [value: boolean]
  exported: []
}>()

const authStore = useAuthStore()

// ──────────────────────────────────────────────────────────────────────────────
// Step management
// ──────────────────────────────────────────────────────────────────────────────

const showTimeStep = computed((): boolean =>
  props.mode === 'sensor' ||
  (props.mode === 'table' &&
    (props.hasTimestamp ?? TIMESTAMP_TABLES.has(props.tableName ?? '')))
)

const stepLabels = computed((): string[] =>
  showTimeStep.value
    ? ['Zeitraum', 'Felder', 'Format']
    : ['Felder', 'Format']
)

const totalSteps = computed((): number => stepLabels.value.length)

const currentStep = ref(1)

// Map visual step index to logical step (1=time, 2=fields, 3=format)
const logicalStep = computed((): number =>
  showTimeStep.value ? currentStep.value : currentStep.value + 1
)

// ──────────────────────────────────────────────────────────────────────────────
// Step 1: Time range
// ──────────────────────────────────────────────────────────────────────────────

const selectedPresetIndex = ref(2) // default: Letzte 24 Stunden

const selectedResolution = ref<SensorDataResolution>('1h')

watch(selectedPresetIndex, (idx) => {
  if (props.mode !== 'sensor') return
  const hours = TIME_PRESETS[idx].hours
  if (hours <= 6) selectedResolution.value = '5m'
  else if (hours <= 168) selectedResolution.value = '1h'
  else selectedResolution.value = '1d'
})

const availableResolutions = computed(() =>
  TIME_PRESETS[selectedPresetIndex.value].hours > 24
    ? RESOLUTION_OPTIONS.filter((r) => r.value !== 'raw')
    : RESOLUTION_OPTIONS
)

const effectiveStartTime = computed((): string => {
  const hours = TIME_PRESETS[selectedPresetIndex.value].hours
  return new Date(Date.now() - hours * 3_600_000).toISOString()
})

const effectiveEndTime = computed((): string => new Date().toISOString())

const estimatedRows = computed((): number => {
  const hours = TIME_PRESETS[selectedPresetIndex.value].hours
  const ratePerHour: Record<string, number> = { '5m': 12, '1h': 1, '1d': 1 / 24, raw: 60 }
  return Math.round(hours * (ratePerHour[selectedResolution.value] ?? 1))
})

const showLargeDataWarning = computed((): boolean => estimatedRows.value > 10_000)

// ──────────────────────────────────────────────────────────────────────────────
// Step 2: Fields
// ──────────────────────────────────────────────────────────────────────────────

const activeColumns = computed((): ColumnOption[] =>
  props.mode === 'sensor' ? SENSOR_COLUMNS : (props.tableColumns ?? [])
)

const selectedFields = ref<string[]>([])

const isFieldsValid = computed((): boolean =>
  props.mode === 'table' || selectedFields.value.length >= 2
)

// ──────────────────────────────────────────────────────────────────────────────
// Step 3: Format + download
// ──────────────────────────────────────────────────────────────────────────────

const selectedFormat = ref<'csv' | 'json'>('csv')
const isExporting = ref(false)
const exportError = ref<string | null>(null)

const exportFilename = computed((): string => {
  const ext = selectedFormat.value
  if (props.mode === 'sensor') {
    const esp = props.espId ?? 'sensor'
    const start = effectiveStartTime.value.slice(0, 10)
    const end = effectiveEndTime.value.slice(0, 10)
    return `sensor-export_${esp}_${start}_${end}.${ext}`
  }
  const table = props.tableName ?? 'table'
  const date = new Date().toISOString().slice(0, 10)
  return `${table}-export-${date}.${ext}`
})

// ──────────────────────────────────────────────────────────────────────────────
// Dialog title
// ──────────────────────────────────────────────────────────────────────────────

const dialogTitle = computed((): string => {
  if (props.mode === 'sensor') {
    const label = props.sensorName ?? props.sensorType ?? 'Sensor'
    return `Export · ${label}`
  }
  return `Export · ${props.tableDisplayName ?? props.tableName ?? 'Tabelle'}`
})

// ──────────────────────────────────────────────────────────────────────────────
// Reset on open
// ──────────────────────────────────────────────────────────────────────────────

watch(
  () => props.open,
  (isOpen) => {
    if (!isOpen) return
    currentStep.value = 1
    selectedPresetIndex.value = 2
    selectedResolution.value = '1h'
    selectedFormat.value = 'csv'
    exportError.value = null
    selectedFields.value = activeColumns.value
      .filter((c) => c.visible)
      .map((c) => c.key)
  }
)

// ──────────────────────────────────────────────────────────────────────────────
// Navigation
// ──────────────────────────────────────────────────────────────────────────────

const canGoNext = computed((): boolean => {
  if (logicalStep.value === 2) return isFieldsValid.value
  return true
})

function goNext(): void {
  if (currentStep.value < totalSteps.value) currentStep.value++
}

function goPrev(): void {
  if (currentStep.value > 1) currentStep.value--
}

// ──────────────────────────────────────────────────────────────────────────────
// Download
// ──────────────────────────────────────────────────────────────────────────────

function buildRequestUrl(): string {
  const params = new URLSearchParams()

  if (props.mode === 'sensor') {
    if (props.espId) params.set('esp_id', props.espId)
    if (props.gpio !== undefined) params.set('gpio', String(props.gpio))
    if (props.sensorType) params.set('sensor_type', props.sensorType)
    if (showTimeStep.value) {
      params.set('start_time', effectiveStartTime.value)
      params.set('end_time', effectiveEndTime.value)
    }
    if (selectedResolution.value !== 'raw') params.set('resolution', selectedResolution.value)
    if (selectedFields.value.length) params.set('columns', selectedFields.value.join(','))
    return `/api/v1/sensors/export?${params}`
  }

  if (showTimeStep.value) {
    params.set('date_from', effectiveStartTime.value)
    params.set('date_to', effectiveEndTime.value)
  }
  if (selectedFields.value.length) params.set('columns', selectedFields.value.join(','))
  params.set('format', selectedFormat.value)
  return `/api/v1/debug/db/${props.tableName}/export?${params}`
}

async function handleDownload(): Promise<void> {
  isExporting.value = true
  exportError.value = null

  try {
    const response = await fetch(buildRequestUrl(), {
      headers: { Authorization: `Bearer ${authStore.accessToken}` },
    })

    if (!response.ok) {
      const body = await response.text().catch(() => '')
      throw new Error(`HTTP ${response.status}: ${body || response.statusText}`)
    }

    const blob = await response.blob()
    const objectUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = exportFilename.value
    link.click()
    URL.revokeObjectURL(objectUrl)

    emit('exported')
    handleClose()
  } catch (e) {
    exportError.value = e instanceof Error ? e.message : 'Export fehlgeschlagen'
  } finally {
    isExporting.value = false
  }
}

function handleClose(): void {
  emit('update:open', false)
  emit('close')
}
</script>

<template>
  <BaseModal
    :open="open"
    :title="dialogTitle"
    max-width="max-w-lg"
    @update:open="(v) => emit('update:open', v)"
    @close="handleClose"
  >
    <!-- Stepper indicator -->
    <div class="export-stepper">
      <template v-for="(label, idx) in stepLabels" :key="idx">
        <div
          class="export-stepper__item"
          :class="{
            'export-stepper__item--active': idx + 1 === currentStep,
            'export-stepper__item--done': idx + 1 < currentStep,
          }"
        >
          <div class="export-stepper__dot">
            <Check v-if="idx + 1 < currentStep" :size="12" />
            <span v-else>{{ idx + 1 }}</span>
          </div>
          <span class="export-stepper__label">{{ label }}</span>
        </div>
        <div v-if="idx < stepLabels.length - 1" class="export-stepper__line" />
      </template>
    </div>

    <!-- Step body -->
    <div class="export-step">

      <!-- Step 1: Zeit­raum -->
      <template v-if="logicalStep === 1">
        <label class="export-step__label">Zeitraum</label>
        <select v-model.number="selectedPresetIndex" class="export-step__select">
          <option v-for="(preset, idx) in TIME_PRESETS" :key="idx" :value="idx">
            {{ preset.label }}
          </option>
        </select>

        <template v-if="mode === 'sensor'">
          <label class="export-step__label">Aggregation</label>
          <select v-model="selectedResolution" class="export-step__select">
            <option
              v-for="opt in availableResolutions"
              :key="opt.value"
              :value="opt.value"
            >
              {{ opt.label }}
            </option>
          </select>

          <p v-if="showLargeDataWarning" class="export-step__warning">
            <AlertTriangle :size="14" />
            Grosse Datenmenge (~{{ estimatedRows.toLocaleString('de-DE') }} Zeilen) — kann einige Sekunden dauern
          </p>
        </template>
      </template>

      <!-- Step 2: Felder -->
      <template v-if="logicalStep === 2">
        <p class="export-step__label">Spalten für den Export</p>
        <p v-if="mode === 'sensor' && !isFieldsValid" class="export-step__hint">
          Bitte mindestens 2 Felder auswählen.
        </p>
        <div class="export-step__fields">
          <label
            v-for="col in activeColumns"
            :key="col.key"
            class="export-step__field"
          >
            <input
              type="checkbox"
              :value="col.key"
              v-model="selectedFields"
              class="export-step__checkbox"
            />
            <span class="export-step__field-label">{{ col.label }}</span>
          </label>
        </div>
      </template>

      <!-- Step 3: Format + Download -->
      <template v-if="logicalStep === 3">
        <p class="export-step__label">Format auswählen</p>
        <div class="export-step__formats">
          <button
            class="export-step__format-btn"
            :class="{ 'export-step__format-btn--active': selectedFormat === 'csv' }"
            @click="selectedFormat = 'csv'"
          >
            CSV
          </button>
          <button
            class="export-step__format-btn"
            :class="{
              'export-step__format-btn--active': selectedFormat === 'json',
              'export-step__format-btn--secondary': mode === 'sensor',
            }"
            @click="selectedFormat = 'json'"
          >
            JSON
          </button>
        </div>

        <p class="export-step__filename">
          <span class="export-step__filename-label">Datei:</span>
          {{ exportFilename }}
        </p>

        <p v-if="exportError" class="export-step__error">{{ exportError }}</p>
      </template>

    </div>

    <!-- Footer -->
    <template #footer>
      <div class="export-footer">
        <button
          v-if="currentStep > 1"
          class="export-footer__btn export-footer__btn--back"
          :disabled="isExporting"
          @click="goPrev"
        >
          <ChevronLeft :size="16" />
          Zurück
        </button>

        <div class="export-footer__spacer" />

        <button
          class="export-footer__btn export-footer__btn--cancel"
          :disabled="isExporting"
          @click="handleClose"
        >
          Abbrechen
        </button>

        <button
          v-if="currentStep < totalSteps"
          class="export-footer__btn export-footer__btn--next"
          :disabled="!canGoNext"
          @click="goNext"
        >
          Weiter
          <ChevronRight :size="16" />
        </button>

        <button
          v-else
          class="export-footer__btn export-footer__btn--download"
          :disabled="isExporting || !isFieldsValid"
          @click="handleDownload"
        >
          <Download :size="14" />
          {{ isExporting ? 'Exportiere...' : 'Download' }}
        </button>
      </div>
    </template>
  </BaseModal>
</template>

<style scoped>
/* ── Stepper ─────────────────────────────────────────────────────────────── */
.export-stepper {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.export-stepper__item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.export-stepper__dot {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xs);
  font-weight: 600;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  color: var(--color-text-secondary);
  transition: background 0.2s, border-color 0.2s, color 0.2s;
}

.export-stepper__item--active .export-stepper__dot {
  background: var(--color-accent);
  border-color: var(--color-accent);
  color: var(--color-text-inverse);
}

.export-stepper__item--done .export-stepper__dot {
  background: var(--color-success);
  border-color: var(--color-success);
  color: var(--color-text-inverse);
}

.export-stepper__label {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.export-stepper__item--active .export-stepper__label {
  color: var(--color-text-primary);
  font-weight: 500;
}

.export-stepper__line {
  flex: 1;
  height: 1px;
  background: var(--glass-border);
  min-width: var(--space-4);
}

/* ── Step body ───────────────────────────────────────────────────────────── */
.export-step {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.export-step__label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-secondary);
  margin-top: var(--space-1);
}

.export-step__label:first-child {
  margin-top: 0;
}

.export-step__select {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  min-height: 44px;
}

.export-step__warning {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  color: var(--color-warning);
}

.export-step__hint {
  font-size: var(--text-xs);
  color: var(--color-warning);
}

.export-step__fields {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-2);
}

@media (max-width: 480px) {
  .export-step__fields {
    grid-template-columns: 1fr;
  }
}

.export-step__field {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: border-color 0.15s;
}

.export-step__field:hover {
  border-color: var(--color-accent);
}

.export-step__checkbox {
  accent-color: var(--color-accent);
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.export-step__field-label {
  font-size: var(--text-sm);
  color: var(--color-text-primary);
}

.export-step__formats {
  display: flex;
  gap: var(--space-3);
}

.export-step__format-btn {
  flex: 1;
  padding: var(--space-3) var(--space-4);
  border: 2px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: var(--glass-bg);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: 600;
  min-height: 48px;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}

.export-step__format-btn:hover {
  border-color: var(--color-accent);
  color: var(--color-text-primary);
}

.export-step__format-btn--active {
  border-color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  color: var(--color-text-primary);
}

.export-step__format-btn--secondary {
  opacity: 0.7;
}

.export-step__filename {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  word-break: break-all;
  padding: var(--space-2) var(--space-3);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
}

.export-step__filename-label {
  font-weight: 500;
  color: var(--color-text-secondary);
  margin-right: var(--space-1);
}

.export-step__error {
  font-size: var(--text-xs);
  color: var(--color-error);
}

/* ── Footer ──────────────────────────────────────────────────────────────── */
.export-footer {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.export-footer__spacer {
  flex: 1;
}

.export-footer__btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  font-weight: 500;
  min-height: 44px;
  cursor: pointer;
  transition: background 0.15s, opacity 0.15s;
}

.export-footer__btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.export-footer__btn--back,
.export-footer__btn--cancel {
  background: transparent;
  border: 1px solid var(--glass-border);
  color: var(--color-text-secondary);
}

.export-footer__btn--back:hover:not(:disabled),
.export-footer__btn--cancel:hover:not(:disabled) {
  background: var(--glass-bg);
}

.export-footer__btn--next {
  background: var(--glass-bg);
  border: 1px solid var(--color-accent);
  color: var(--color-accent);
}

.export-footer__btn--next:hover:not(:disabled) {
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
}

.export-footer__btn--download {
  background: var(--color-accent);
  border: none;
  color: var(--color-text-inverse);
}

.export-footer__btn--download:hover:not(:disabled) {
  opacity: 0.9;
}
</style>
