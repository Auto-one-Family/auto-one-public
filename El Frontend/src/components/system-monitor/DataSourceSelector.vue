<template>
  <div class="data-source-selector">
    <!-- Content -->
    <div class="selector-content">
        <!-- Row 1: DataSource Grid -->
        <div class="filter-row">
          <span class="filter-row-label">Quellen</span>
          <div class="source-pills">
            <!-- System-Ereignisse (Audit Log) -->
            <button
              class="source-pill"
              :class="{ 'source-pill--selected': selectedSources.includes('audit_log') }"
              @click="toggleSource('audit_log')"
            >
              <div class="pill-icon pill-icon--audit">
                <AlertCircle class="icon" />
              </div>
              <span class="pill-text">System</span>
              <Check v-if="selectedSources.includes('audit_log')" class="pill-check" />
            </button>

            <!-- Sensordaten -->
            <button
              class="source-pill"
              :class="{ 'source-pill--selected': selectedSources.includes('sensor_data') }"
              @click="toggleSource('sensor_data')"
            >
              <div class="pill-icon pill-icon--sensor">
                <Activity class="icon" />
              </div>
              <span class="pill-text">Sensoren</span>
              <Check v-if="selectedSources.includes('sensor_data')" class="pill-check" />
            </button>

            <!-- ESP-Status -->
            <button
              class="source-pill"
              :class="{ 'source-pill--selected': selectedSources.includes('esp_health') }"
              @click="toggleSource('esp_health')"
            >
              <div class="pill-icon pill-icon--health">
                <Cpu class="icon" />
              </div>
              <span class="pill-text">ESP-Status</span>
              <Check v-if="selectedSources.includes('esp_health')" class="pill-check" />
            </button>

            <!-- Aktoren -->
            <button
              class="source-pill"
              :class="{ 'source-pill--selected': selectedSources.includes('actuators') }"
              @click="toggleSource('actuators')"
            >
              <div class="pill-icon pill-icon--actuator">
                <Zap class="icon" />
              </div>
              <span class="pill-text">Aktoren</span>
              <Check v-if="selectedSources.includes('actuators')" class="pill-check" />
            </button>
          </div>
        </div>

        <!-- Divider -->
        <div class="filter-divider" />

        <!-- Row 1.5: Grouping Toggle -->
        <div class="filter-row">
          <span class="filter-row-label">Ansicht</span>
          <button
            class="grouping-toggle"
            :class="{ 'grouping-toggle--active': groupingEnabled }"
            @click="emit('update:groupingEnabled', !groupingEnabled)"
            title="Events nach Zeitfenster gruppieren"
          >
            <Layers class="icon" />
            <span class="grouping-toggle__label">Gruppiert</span>
          </button>
        </div>

        <!-- Divider -->
        <div class="filter-divider" />

        <!-- Row 2: Filter Controls -->
        <div class="filter-row filter-row--wrap">
          <span class="filter-row-label">Filter</span>
          <div class="filter-controls">
            <!-- ESP Dropdown -->
            <div class="filter-dropdown">
              <label class="dropdown-label">ESP</label>
              <select
                ref="espFilterRef"
                :value="espId"
                @change="updateEspId(($event.target as HTMLSelectElement).value)"
                class="dropdown-select"
                :class="{ 'dropdown-select--highlighted': espFilterHighlighted }"
              >
                <option value="">Alle ESPs</option>
                <option v-for="id in uniqueEspIds" :key="id" :value="id">{{ id }}</option>
              </select>
            </div>

            <!-- Level Filter (Multi-Select Pills mit Labels) -->
            <div class="filter-dropdown filter-dropdown--levels">
              <label class="dropdown-label">Level</label>
              <div class="level-pills">
                <button
                  v-for="level in severityLevels"
                  :key="level"
                  class="level-pill"
                  :class="{
                    'level-pill--active': levels.has(level),
                    [`level-pill--${level}`]: levels.has(level)
                  }"
                  @click="toggleLevel(level)"
                  :title="getSeverityLabel(level)"
                >
                  <component :is="getSeverityIcon(level)" class="level-icon" />
                  <span class="level-label">{{ getLevelLabel(level) }}</span>
                </button>
              </div>
            </div>

            <!-- Zeit Segmented Control -->
            <div class="filter-dropdown filter-dropdown--time">
              <label class="dropdown-label">Zeit</label>
              <div class="time-segmented">
                <!-- Preset Buttons -->
                <button
                  v-for="(preset, index) in TIME_RANGE_PRESETS"
                  :key="preset.id"
                  class="time-segment"
                  :class="{
                    'time-segment--active': timeRange === preset.id && !hasCustomRange,
                    'time-segment--first': index === 0,
                  }"
                  @click="selectPreset(preset.id)"
                >
                  {{ preset.label }}
                </button>

                <!-- Custom Button / Active Custom Range -->
                <button
                  v-if="!hasCustomRange"
                  class="time-segment time-segment--last time-segment--icon"
                  :class="{ 'time-segment--active': showCustomPicker }"
                  @click="toggleCustomPicker"
                  title="Zeitraum wählen"
                >
                  <Calendar class="segment-icon" />
                </button>

                <button
                  v-else
                  class="time-segment time-segment--last time-segment--custom"
                  @click="toggleCustomPicker"
                >
                  <span class="custom-range-text">{{ formatCustomRange }}</span>
                  <X class="segment-clear" @click.stop="clearCustomRange" />
                </button>
              </div>

              <!-- Custom Date Picker Modal (Teleported to body) -->
              <Teleport to="body">
                <Transition name="picker-modal">
                  <div v-if="showCustomPicker" class="custom-picker-overlay" @click.self="cancelCustomPicker">
                    <div class="custom-picker-popover">
                      <div class="picker-header">
                        <Calendar class="picker-header-icon" />
                        <span>Zeitraum wählen</span>
                      </div>

                      <div class="picker-body">
                        <div class="date-field">
                          <label class="date-label">Von</label>
                          <input
                            type="date"
                            v-model="localStartDate"
                            :max="localEndDate || today"
                            class="date-input"
                          />
                        </div>

                        <div class="date-field">
                          <label class="date-label">Bis</label>
                          <input
                            type="date"
                            v-model="localEndDate"
                            :min="localStartDate"
                            :max="today"
                            class="date-input"
                          />
                        </div>
                      </div>

                      <div class="picker-footer">
                        <button class="picker-btn picker-btn--cancel" @click="cancelCustomPicker">
                          Abbrechen
                        </button>
                        <button
                          class="picker-btn picker-btn--apply"
                          @click="applyCustomRange"
                          :disabled="!localStartDate || !localEndDate"
                        >
                          Anwenden
                        </button>
                      </div>
                    </div>
                  </div>
                </Transition>
              </Teleport>
            </div>
          </div>
        </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import {
  AlertCircle,
  Activity,
  Cpu,
  Zap,
  Info,
  Check,
  AlertTriangle,
  AlertOctagon,
  Calendar,
  X,
  Layers,
} from 'lucide-vue-next'
import { getSeverityLabel } from '@/utils/errorCodeTranslator'

// ============================================================================
// Types
// ============================================================================

export type DataSource = 'audit_log' | 'sensor_data' | 'esp_health' | 'actuators'
type Severity = 'info' | 'warning' | 'error' | 'critical'
type TimeRange = 'all' | '1h' | '6h' | '24h' | '7d' | '30d' | 'custom'

// ============================================================================
// Props & Emits
// ============================================================================

interface Props {
  // Filter Props (from parent)
  espId: string
  levels: Set<string>
  timeRange: TimeRange
  uniqueEspIds: string[]
  // Custom Date Range (for 'custom' timeRange)
  customStartDate?: string
  customEndDate?: string
  // Grouping
  groupingEnabled?: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  // DataSource changes (internal state)
  change: [sources: DataSource[]]
  // Filter changes (to parent)
  'update:espId': [value: string]
  'update:levels': [value: Set<string>]
  'update:timeRange': [value: TimeRange]
  // Custom Date Range changes
  'update:customStartDate': [value: string | undefined]
  'update:customEndDate': [value: string | undefined]
  // Grouping
  'update:groupingEnabled': [value: boolean]
}>()

// ============================================================================
// Constants
// ============================================================================

const STORAGE_KEY = 'systemMonitor.dataSources'

const severityLevels: Severity[] = ['info', 'warning', 'error', 'critical']

// Preset time ranges for segmented control
const TIME_RANGE_PRESETS: Array<{ id: TimeRange; label: string }> = [
  { id: 'all', label: 'Alle' },
  { id: '1h', label: '1h' },
  { id: '6h', label: '6h' },
  { id: '24h', label: '24h' },
  { id: '7d', label: '7d' },
  { id: '30d', label: '30d' },
]

// ============================================================================
// Local State (DataSource selection - persisted to localStorage)
// ============================================================================

const getInitialSources = (): DataSource[] => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      const parsed = JSON.parse(stored)
      if (Array.isArray(parsed) && parsed.length > 0) {
        return parsed
      }
    }
  } catch {
    // Ignore parse errors
  }
  return ['audit_log', 'sensor_data', 'esp_health', 'actuators']
}

const selectedSources = ref<DataSource[]>(getInitialSources())

// ESP Filter Highlight State
const espFilterHighlighted = ref(false)
const espFilterRef = ref<HTMLSelectElement | null>(null)

// Custom Date Picker State
const showCustomPicker = ref(false)
const localStartDate = ref('')
const localEndDate = ref('')

// ============================================================================
// Computed
// ============================================================================

/**
 * Today's date in YYYY-MM-DD format for date input max constraint
 */
const today = computed(() => new Date().toISOString().split('T')[0])

/**
 * Check if we have an active custom date range
 */
const hasCustomRange = computed(() =>
  props.timeRange === 'custom' && props.customStartDate && props.customEndDate
)

/**
 * Format the custom date range for display (DD.MM - DD.MM)
 */
const formatCustomRange = computed(() => {
  if (!props.customStartDate || !props.customEndDate) return ''

  const start = new Date(props.customStartDate)
  const end = new Date(props.customEndDate)

  const formatDate = (d: Date) =>
    `${d.getDate().toString().padStart(2, '0')}.${(d.getMonth() + 1).toString().padStart(2, '0')}`

  return `${formatDate(start)} - ${formatDate(end)}`
})

// ============================================================================
// Methods
// ============================================================================

function toggleSource(source: DataSource) {
  const index = selectedSources.value.indexOf(source)
  if (index >= 0) {
    // Don't allow deselecting all sources
    if (selectedSources.value.length > 1) {
      selectedSources.value = selectedSources.value.filter(s => s !== source)
    }
  } else {
    selectedSources.value = [...selectedSources.value, source]
  }
}

function getSeverityIcon(severity: string) {
  switch (severity) {
    case 'critical': return AlertOctagon
    case 'error': return AlertCircle
    case 'warning': return AlertTriangle
    default: return Info
  }
}

function getLevelLabel(level: string): string {
  switch (level) {
    case 'critical': return 'Kritisch'
    case 'error': return 'Fehler'
    case 'warning': return 'Warnung'
    case 'info': return 'Info'
    default: return level
  }
}

function toggleLevel(level: string) {
  const newLevels = new Set(props.levels)
  if (newLevels.has(level)) {
    newLevels.delete(level)
  } else {
    newLevels.add(level)
  }
  emit('update:levels', newLevels)
}

function updateEspId(value: string) {
  emit('update:espId', value)
}

/**
 * Select a preset time range (clears custom range)
 */
function selectPreset(id: TimeRange) {
  emit('update:timeRange', id)
  emit('update:customStartDate', undefined)
  emit('update:customEndDate', undefined)
  showCustomPicker.value = false
}

/**
 * Toggle the custom date picker popover
 */
function toggleCustomPicker() {
  showCustomPicker.value = !showCustomPicker.value
  if (showCustomPicker.value) {
    // Initialize with current custom range or defaults
    localStartDate.value = props.customStartDate || ''
    localEndDate.value = props.customEndDate || today.value
  }
}

/**
 * Apply the custom date range
 */
function applyCustomRange() {
  if (!localStartDate.value || !localEndDate.value) return

  emit('update:timeRange', 'custom')
  emit('update:customStartDate', localStartDate.value)
  emit('update:customEndDate', localEndDate.value)
  showCustomPicker.value = false
}

/**
 * Cancel the custom date picker
 */
function cancelCustomPicker() {
  showCustomPicker.value = false
}

/**
 * Clear the custom date range (revert to "Alle")
 */
function clearCustomRange() {
  emit('update:timeRange', 'all')
  emit('update:customStartDate', undefined)
  emit('update:customEndDate', undefined)
}

// ============================================================================
// Watchers
// ============================================================================

// Highlight ESP filter when value is set programmatically (from parent)
watch(() => props.espId, (newVal, oldVal) => {
  if (newVal && newVal !== oldVal) {
    espFilterHighlighted.value = true
    nextTick(() => {
      espFilterRef.value?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    })
    setTimeout(() => {
      espFilterHighlighted.value = false
    }, 2000)
  }
})

// Persist DataSource selection to localStorage
watch(selectedSources, (newSources) => {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(newSources))
  emit('change', newSources)
}, { deep: true })

// ============================================================================
// Lifecycle
// ============================================================================

onMounted(() => {
  emit('change', selectedSources.value)
})
</script>

<style scoped>
/* =============================================================================
   DATA SOURCE SELECTOR - Integrated Filter Card (Industrial Design)
   ============================================================================= */

.data-source-selector {
  overflow: hidden;
}

/* =============================================================================
   Content - Iridescent Glassmorphism Card
   ============================================================================= */

.selector-content {
  padding: 1.25rem;                        /* Consistent inner padding */
  margin: 0.75rem 1rem 1rem;               /* More breathing room around card */
  display: flex;
  flex-direction: column;
  gap: 1rem;                               /* Consistent 16px gap between sections */

  /* Iridescent Glassmorphism */
  background: rgba(255, 255, 255, 0.02);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: var(--radius-md);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.02),
    0 4px 16px rgba(0, 0, 0, 0.15),
    inset 0 1px 0 rgba(255, 255, 255, 0.04); /* Subtle top highlight */
}

/* =============================================================================
   Filter Rows
   ============================================================================= */

.filter-row {
  display: flex;
  align-items: center;
  gap: 1rem;                               /* 16px gap between label and content */
}

.filter-row--wrap {
  flex-wrap: wrap;
  gap: 1rem 1.5rem;                        /* row-gap: 16px, column-gap: 24px */
}

.filter-row-label {
  font-size: 0.6875rem;                    /* 11px - smaller section label */
  font-weight: 600;
  color: var(--color-text-muted);          /* Slightly more muted */
  text-transform: uppercase;
  letter-spacing: 0.08em;
  width: 52px;                             /* Slightly narrower for compact design */
  flex-shrink: 0;
}

.filter-divider {
  height: 1px;
  margin: 0.25rem 0;                       /* Subtle spacing around divider */
  background: linear-gradient(
    to right,
    transparent,
    rgba(255, 255, 255, 0.06) 10%,
    rgba(255, 255, 255, 0.06) 90%,
    transparent
  );
}

/* =============================================================================
   Source Pills (DataSource Selection) - Enhanced Touch Targets
   ============================================================================= */

.source-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;                             /* 8px gap between pills */
}

.source-pill {
  display: flex;
  align-items: center;
  gap: 0.5rem;                             /* 8px gap between icon and text */
  padding: 0.5rem 0.875rem;                /* Larger padding for better touch */
  border-radius: var(--radius-md);                   /* Slightly less round - modern look */
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--color-text-secondary);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
  overflow: hidden;
}

.source-pill::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg,
    rgba(99, 102, 241, 0.15) 0%,
    rgba(168, 85, 247, 0.1) 100%
  );
  opacity: 0;
  transition: opacity 0.2s ease;
}

.source-pill:hover::before {
  opacity: 1;
}

.source-pill:hover {
  border-color: rgba(255, 255, 255, 0.12);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.source-pill--selected {
  background: linear-gradient(135deg,
    rgba(96, 165, 250, 0.15) 0%,
    rgba(129, 140, 248, 0.1) 100%
  );
  border-color: rgba(96, 165, 250, 0.35);
  color: var(--color-text-primary);
}

.source-pill--selected::before {
  display: none;
}

.pill-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;                           /* 24px */
  height: 1.5rem;
  border-radius: var(--radius-sm);                 /* 6px radius */
  flex-shrink: 0;
}

.pill-icon .icon {
  width: 0.875rem;
  height: 0.875rem;
}

.pill-icon--audit {
  background: rgba(248, 113, 113, 0.2);
  color: var(--color-error);
}

.pill-icon--sensor {
  background: rgba(96, 165, 250, 0.2);
  color: var(--color-info);
}

.pill-icon--health {
  background: rgba(34, 197, 94, 0.2);
  color: var(--color-success);
}

.pill-icon--actuator {
  background: rgba(251, 191, 36, 0.2);
  color: var(--color-warning);
}

.pill-text {
  white-space: nowrap;
}

.pill-check {
  width: 1rem;
  height: 1rem;
  color: var(--color-info);
  margin-left: 0.125rem;
}

/* =============================================================================
   Filter Controls (ESP, Level, Zeit)
   ============================================================================= */

.filter-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;                             /* 24px gap between filter groups */
  flex: 1;
}

.filter-dropdown {
  display: flex;
  align-items: center;
  gap: 0.625rem;                           /* 10px gap between label and control */
}

.filter-dropdown--levels {
  flex-direction: row;
}

.dropdown-label {
  font-size: 0.75rem;                      /* 12px - consistent label size */
  font-weight: 500;
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.dropdown-select {
  height: 2.25rem;                         /* 36px */
  padding: 0 0.875rem;
  padding-right: 2rem;                     /* Space for dropdown arrow */
  border-radius: var(--radius-md);
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  color: var(--color-text-primary);
  font-size: 0.8125rem;
  transition: all 0.2s ease;
  cursor: pointer;
  min-width: 120px;
}

.dropdown-select:focus {
  outline: none;
  border-color: rgba(96, 165, 250, 0.5);
  box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.1);
}

.dropdown-select:hover:not(:focus) {
  border-color: rgba(255, 255, 255, 0.15);
  background: rgba(255, 255, 255, 0.06);
}

.dropdown-select--highlighted {
  animation: filter-highlight 2s ease-out;
}

@keyframes filter-highlight {
  0% {
    box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.5);
    border-color: var(--color-info);
    background: rgba(96, 165, 250, 0.12);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(96, 165, 250, 0);
    border-color: rgba(255, 255, 255, 0.08);
    background: rgba(255, 255, 255, 0.04);
  }
}

/* =============================================================================
   Level Pills (Multi-Select mit Icon + Label) - Enhanced
   ============================================================================= */

.level-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;                             /* 8px gap - clearer separation */
}

.level-pill {
  display: flex;
  align-items: center;
  gap: 0.375rem;                           /* 6px between icon and label */
  height: 2.25rem;                         /* 36px */
  padding: 0 1rem;
  border-radius: var(--radius-md);                   /* Match other buttons */
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  cursor: pointer;
  transition: all 0.2s ease;
  color: var(--color-text-muted);
  font-size: 0.8125rem;
  font-weight: 500;
}

.level-pill:hover:not(.level-pill--active) {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.12);
  color: var(--color-text-secondary);
}

.level-pill--active {
  color: white;
}

.level-pill--info.level-pill--active {
  background: linear-gradient(135deg, var(--color-accent) 0%, var(--color-accent-bright) 100%);
  border-color: var(--color-accent);
  box-shadow: 0 0 12px rgba(59, 130, 246, 0.35);
}

.level-pill--warning.level-pill--active {
  background: linear-gradient(135deg, var(--color-warning) 0%, var(--color-warning) 100%);
  border-color: var(--color-warning);
  color: var(--color-bg-tertiary);
  box-shadow: 0 0 12px rgba(245, 158, 11, 0.35);
}

.level-pill--error.level-pill--active {
  background: linear-gradient(135deg, var(--color-error) 0%, var(--color-error) 100%);
  border-color: var(--color-error);
  box-shadow: 0 0 12px rgba(239, 68, 68, 0.35);
}

.level-pill--critical.level-pill--active {
  background: linear-gradient(135deg, var(--color-error) 0%, var(--gradient-danger-end) 100%);
  border-color: var(--color-error);
  box-shadow: 0 0 12px rgba(220, 38, 38, 0.4);
}

.level-icon {
  width: 0.875rem;
  height: 0.875rem;
  flex-shrink: 0;
}

.level-label {
  white-space: nowrap;
}

/* =============================================================================
   Time Segmented Control - Modern Design
   ============================================================================= */

.filter-dropdown--time {
  position: relative;
}

.time-segmented {
  display: inline-flex;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: var(--radius-md);
  padding: 0.125rem;                       /* Inner padding for "floating" effect */
}

.time-segment {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 2rem;                            /* 32px - slightly smaller for segmented */
  padding: 0 0.75rem;
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--color-text-secondary);
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);                 /* Inner segments have radius */
  cursor: pointer;
  transition: all 0.15s ease;
  position: relative;
}

.time-segment:hover:not(.time-segment--active) {
  color: var(--color-text-primary);
  background: rgba(255, 255, 255, 0.06);
}

.time-segment--active {
  background: rgba(96, 165, 250, 0.2);
  color: var(--color-text-primary);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.time-segment--icon {
  padding: 0 0.625rem;
}

.segment-icon {
  width: 1rem;
  height: 1rem;
}

.time-segment--custom {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0 0.625rem;
  background: rgba(129, 140, 248, 0.2);
  color: var(--color-iridescent-2);
}

.time-segment--custom:hover {
  background: rgba(129, 140, 248, 0.25);
}

.custom-range-text {
  font-size: 0.75rem;
  white-space: nowrap;
}

.segment-clear {
  width: 0.75rem;
  height: 0.75rem;
  opacity: 0.7;
  cursor: pointer;
  transition: opacity 0.15s ease;
}

.segment-clear:hover {
  opacity: 1;
}

/* =============================================================================
   Custom Date Picker Overlay & Popover
   ============================================================================= */

.custom-picker-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  z-index: var(--z-modal);
  display: flex;
  align-items: center;
  justify-content: center;
}

.custom-picker-popover {
  width: 300px;
  padding: var(--space-lg);
  border-radius: var(--radius-lg);
  background: rgba(20, 20, 30, 0.98);
  backdrop-filter: blur(20px);
  border: 1px solid var(--glass-border);
  box-shadow: 0 25px 50px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(255, 255, 255, 0.05);
}

.picker-header {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-bottom: var(--space-lg);
  color: var(--color-text-primary);
  font-size: 0.875rem;
  font-weight: 600;
}

.picker-header-icon {
  width: 1rem;
  height: 1rem;
  color: var(--color-iridescent-1);
}

.picker-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.date-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.date-label {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.date-input {
  width: 100%;
  height: 40px;
  padding: 0 var(--space-md);
  border-radius: var(--radius-md);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  color: var(--color-text-primary);
  font-size: 0.875rem;
  transition: all var(--transition-base);
  color-scheme: dark;
}

.date-input:focus {
  outline: none;
  border-color: var(--color-iridescent-1);
  box-shadow: 0 0 0 2px rgba(96, 165, 250, 0.15);
}

.date-input:hover:not(:focus) {
  border-color: var(--glass-border-hover);
}

.picker-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-sm);
  margin-top: var(--space-lg);
  padding-top: var(--space-md);
  border-top: 1px solid var(--glass-border);
}

.picker-btn {
  height: 36px;
  padding: 0 var(--space-md);
  font-size: 0.8125rem;
  font-weight: 500;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-base);
}

.picker-btn--cancel {
  background: transparent;
  border: none;
  color: var(--color-text-secondary);
}

.picker-btn--cancel:hover {
  color: var(--color-text-primary);
}

.picker-btn--apply {
  background: var(--gradient-iridescent);
  border: none;
  color: white;
}

.picker-btn--apply:hover:not(:disabled) {
  opacity: 0.9;
  transform: translateY(-1px);
}

.picker-btn--apply:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Picker Modal Animation */
.picker-modal-enter-active,
.picker-modal-leave-active {
  transition: opacity 0.2s ease-out;
}

.picker-modal-enter-active .custom-picker-popover,
.picker-modal-leave-active .custom-picker-popover {
  transition: all 0.2s ease-out;
}

.picker-modal-enter-from,
.picker-modal-leave-to {
  opacity: 0;
}

.picker-modal-enter-from .custom-picker-popover,
.picker-modal-leave-to .custom-picker-popover {
  transform: scale(0.95);
}

/* =============================================================================
   Mobile Responsive
   ============================================================================= */

@media (max-width: 768px) {
  .selector-content {
    padding: 1rem;
    margin: 0.5rem;
  }

  .filter-row {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.75rem;
  }

  .filter-row-label {
    width: auto;
    margin-bottom: 0;
  }

  .source-pills {
    width: 100%;
  }

  .filter-controls {
    width: 100%;
    flex-direction: column;
    gap: 1rem;
  }

  .filter-dropdown {
    width: 100%;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .filter-dropdown--levels {
    flex-direction: column;
  }

  .dropdown-select {
    width: 100%;
    min-height: 44px;                      /* 44px touch target */
  }

  .level-pills {
    width: 100%;
    justify-content: flex-start;
  }

  .level-pill {
    height: 44px;                          /* 44px touch target */
    padding: 0 1rem;
  }

  /* Time Segmented Control Mobile */
  .time-segmented {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
    padding: 0.25rem;
    width: 100%;
  }

  .time-segment {
    height: 40px;
    flex: 1;
    min-width: 48px;
  }

  .custom-picker-popover {
    width: calc(100% - 32px);
    max-width: 320px;
  }
}

@media (max-width: 480px) {
  .source-pill {
    padding: 0.5rem 0.75rem;
    font-size: 0.75rem;
  }

  .pill-icon {
    width: 1.25rem;
    height: 1.25rem;
  }

  .pill-icon .icon {
    width: 0.75rem;
    height: 0.75rem;
  }

  .level-pill {
    height: 40px;
    padding: 0 0.75rem;
    font-size: 0.75rem;
  }

  .level-icon {
    width: 0.75rem;
    height: 0.75rem;
  }
}

/* =============================================================================
   Grouping Toggle
   ============================================================================= */

.grouping-toggle {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 0.75rem;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  font-size: 0.8125rem;
  cursor: pointer;
  transition: all 0.15s;
}

.grouping-toggle .icon {
  width: 1rem;
  height: 1rem;
}

.grouping-toggle:hover {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.12);
}

.grouping-toggle--active {
  background: rgba(96, 165, 250, 0.1);
  border-color: rgba(96, 165, 250, 0.3);
  color: var(--color-info);
}

.grouping-toggle__label {
  font-weight: 500;
}

@media (max-width: 640px) {
  .grouping-toggle__label {
    display: none;
  }
}
</style>
