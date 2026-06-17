<script setup lang="ts">
/**
 * ExportCsvDialog — Compact dialog for CSV export configuration.
 *
 * Allows selecting time range preset and aggregation resolution
 * before triggering a browser CSV download.
 */
import { ref, computed, watch } from 'vue'
import BaseModal from '@/shared/design/primitives/BaseModal.vue'
import { useExportCsv } from '@/composables/useExportCsv'
import { parseSensorId } from '@/composables/useSensorId'
import { getSensorLabel } from '@/utils/sensorDefaults'
import { Download, AlertTriangle } from 'lucide-vue-next'
import type { SensorDataResolution } from '@/types'

interface Props {
  open: boolean
  sensorId: string            // "espId:gpio:sensorType"
  sensorName?: string
  zoneName?: string
  defaultFrom?: Date
  defaultTo?: Date
}

const props = defineProps<Props>()

const emit = defineEmits<{
  close: []
  'update:open': [value: boolean]
}>()

const { isExporting, exportError, exportSensorCsv } = useExportCsv()

// --- Time presets ---
const TIME_PRESETS = [
  { label: 'Letzte 1 Stunde', hours: 1 },
  { label: 'Letzte 6 Stunden', hours: 6 },
  { label: 'Letzte 24 Stunden', hours: 24 },
  { label: 'Letzte 7 Tage', hours: 168 },
  { label: 'Letzte 30 Tage', hours: 720 },
] as const

const RESOLUTION_OPTIONS: { label: string; value: SensorDataResolution }[] = [
  { label: 'Rohdaten', value: 'raw' },
  { label: '5 Minuten', value: '5m' },
  { label: '1 Stunde', value: '1h' },
  { label: '1 Tag', value: '1d' },
]

const selectedPresetIndex = ref(2) // Default: "Letzte 24 Stunden"
const selectedResolution = ref<SensorDataResolution>('1h')

// Auto-set resolution when preset changes
watch(selectedPresetIndex, (idx) => {
  const hours = TIME_PRESETS[idx].hours
  if (hours <= 6) selectedResolution.value = '5m'
  else if (hours <= 168) selectedResolution.value = '1h'
  else selectedResolution.value = '1d'
})

// Disable raw for ranges > 24h (browser crash risk)
const availableResolutions = computed(() =>
  TIME_PRESETS[selectedPresetIndex.value].hours > 24
    ? RESOLUTION_OPTIONS.filter(r => r.value !== 'raw')
    : RESOLUTION_OPTIONS
)

// Estimated row count for warning
const estimatedRows = computed(() => {
  const hours = TIME_PRESETS[selectedPresetIndex.value].hours
  const pointsPerHour: Record<string, number> = { '5m': 12, '1h': 1, '1d': 1 / 24, raw: 60 }
  return Math.round(hours * (pointsPerHour[selectedResolution.value] ?? 1))
})

const showLargeDataWarning = computed(() => estimatedRows.value > 10000)

// Dialog title
const dialogTitle = computed(() => {
  const parsed = parseSensorId(props.sensorId)
  const label = props.sensorName || (parsed.sensorType ? getSensorLabel(parsed.sensorType) : 'Sensor')
  return `CSV Export · ${label}`
})

async function handleDownload() {
  const parsed = parseSensorId(props.sensorId)
  if (!parsed.isValid || parsed.espId === null || parsed.gpio === null) return

  const hours = TIME_PRESETS[selectedPresetIndex.value].hours
  const endTime = new Date()
  const startTime = new Date(endTime.getTime() - hours * 60 * 60 * 1000)

  await exportSensorCsv({
    espId: parsed.espId,
    gpio: parsed.gpio,
    sensorType: parsed.sensorType ?? '',
    sensorName: props.sensorName ?? parsed.sensorType ?? '',
    zoneName: props.zoneName,
    startTime,
    endTime,
    resolution: selectedResolution.value,
  })

  if (!exportError.value) {
    emit('update:open', false)
    emit('close')
  }
}

function handleClose() {
  emit('update:open', false)
  emit('close')
}
</script>

<template>
  <BaseModal
    :open="open"
    :title="dialogTitle"
    max-width="max-w-sm"
    @update:open="(v) => emit('update:open', v)"
    @close="handleClose"
  >
    <div class="export-dialog">
      <!-- Time range -->
      <label class="export-dialog__label">Zeitraum</label>
      <select
        v-model.number="selectedPresetIndex"
        class="export-dialog__select"
      >
        <option
          v-for="(preset, idx) in TIME_PRESETS"
          :key="idx"
          :value="idx"
        >{{ preset.label }}</option>
      </select>

      <!-- Resolution -->
      <label class="export-dialog__label">Aggregation</label>
      <select
        v-model="selectedResolution"
        class="export-dialog__select"
      >
        <option
          v-for="opt in availableResolutions"
          :key="opt.value"
          :value="opt.value"
        >{{ opt.label }}</option>
      </select>

      <!-- Large data warning -->
      <p v-if="showLargeDataWarning" class="export-dialog__warning">
        <AlertTriangle :size="14" />
        Grosse Datenmenge (~{{ estimatedRows.toLocaleString('de-DE') }} Zeilen) — kann einige Sekunden dauern
      </p>

      <!-- Export error -->
      <p v-if="exportError" class="export-dialog__error">
        {{ exportError }}
      </p>
    </div>

    <template #footer>
      <div class="export-dialog__actions">
        <button class="export-dialog__btn export-dialog__btn--cancel" @click="handleClose">
          Abbrechen
        </button>
        <button
          class="export-dialog__btn export-dialog__btn--download"
          :disabled="isExporting"
          @click="handleDownload"
        >
          <Download :size="14" />
          {{ isExporting ? 'Exportiere...' : 'Download CSV' }}
        </button>
      </div>
    </template>
  </BaseModal>
</template>

<style scoped>
.export-dialog {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.export-dialog__label {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  font-weight: 500;
}

.export-dialog__label:not(:first-child) {
  margin-top: var(--space-1);
}

.export-dialog__select {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  min-height: 44px;
}

.export-dialog__warning {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  color: var(--color-warning);
}

.export-dialog__error {
  font-size: var(--text-xs);
  color: var(--color-error);
}

.export-dialog__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}

.export-dialog__btn {
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

.export-dialog__btn--cancel {
  background: transparent;
  border: 1px solid var(--glass-border);
  color: var(--color-text-secondary);
}

.export-dialog__btn--cancel:hover {
  background: var(--glass-bg);
}

.export-dialog__btn--download {
  background: var(--color-accent);
  border: none;
  color: var(--color-text-inverse);
}

.export-dialog__btn--download:hover {
  opacity: 0.9;
}

.export-dialog__btn--download:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
