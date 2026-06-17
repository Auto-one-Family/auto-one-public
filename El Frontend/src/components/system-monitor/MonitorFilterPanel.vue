<script setup lang="ts">
/**
 * MonitorFilterPanel - System Monitor Filter Controls
 *
 * Provides filter controls for ESP ID, severity levels, and time range.
 * Mobile-responsive with drawer-like behavior on smaller screens.
 *
 * Uses v-model pattern for reactive filter binding.
 *
 * Event-Type-Filter entfernt (Phase 5) - DataSource-Filter ist ausreichend
 */

import {
  Clock,
  AlertTriangle,
  AlertCircle,
  AlertOctagon,
  Info,
} from 'lucide-vue-next'
import { getSeverityLabel } from '@/utils/errorCodeTranslator'

// ============================================================================
// Types
// ============================================================================

type Severity = 'info' | 'warning' | 'error' | 'critical'
type TimeRange = 'all' | '1h' | '6h' | '24h'

// ============================================================================
// Props & Emits
// ============================================================================

// Event-Type-Filter Props entfernt (Phase 5) - DataSource-Filter ist ausreichend
interface Props {
  espId: string
  levels: Set<string>
  timeRange: TimeRange
  uniqueEspIds: string[]
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:espId': [value: string]
  'update:levels': [value: Set<string>]
  'update:timeRange': [value: TimeRange]
}>()

// ============================================================================
// Constants
// ============================================================================

const severityLevels: Severity[] = ['info', 'warning', 'error', 'critical']

const timeRanges: Array<{ id: TimeRange; label: string }> = [
  { id: 'all', label: 'Alle' },
  { id: '1h', label: '1 Stunde' },
  { id: '6h', label: '6 Stunden' },
  { id: '24h', label: '24 Stunden' },
]

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

function toggleLevel(level: string) {
  const newLevels = new Set(props.levels)
  if (newLevels.has(level)) {
    newLevels.delete(level)
  } else {
    newLevels.add(level)
  }
  emit('update:levels', newLevels)
}

// Event-Type-Filter Funktionen entfernt (Phase 5) - DataSource-Filter ist ausreichend

function updateEspId(value: string) {
  emit('update:espId', value)
}

function updateTimeRange(value: TimeRange) {
  emit('update:timeRange', value)
}
</script>

<template>
  <div class="filter-panel">
    <!-- ESP-ID Filter -->
    <div class="filter-section">
      <label class="filter-label">ESP-ID Filter</label>
      <div class="filter-input-group">
        <input
          :value="espId"
          @input="updateEspId(($event.target as HTMLInputElement).value)"
          type="text"
          placeholder="z.B. ESP_12AB34CD"
          class="filter-input"
        />
        <select
          v-if="uniqueEspIds.length > 0"
          :value="espId"
          @change="updateEspId(($event.target as HTMLSelectElement).value)"
          class="filter-select"
        >
          <option value="">Alle ESPs</option>
          <option v-for="id in uniqueEspIds" :key="id" :value="id">{{ id }}</option>
        </select>
      </div>
    </div>

    <!-- Level Filter -->
    <div class="filter-section">
      <label class="filter-label">Level</label>
      <div class="filter-chips">
        <button
          v-for="level in severityLevels"
          :key="level"
          class="filter-chip"
          :class="{
            'filter-chip--active': levels.has(level),
            [`filter-chip--${level}`]: levels.has(level)
          }"
          @click="toggleLevel(level)"
        >
          <component :is="getSeverityIcon(level)" class="w-3 h-3" />
          {{ getSeverityLabel(level) }}
        </button>
      </div>
    </div>

    <!-- Time Range Filter -->
    <div class="filter-section">
      <label class="filter-label">Zeitraum</label>
      <div class="filter-chips">
        <button
          v-for="range in timeRanges"
          :key="range.id"
          class="filter-chip"
          :class="{ 'filter-chip--active': timeRange === range.id }"
          @click="updateTimeRange(range.id)"
        >
          <Clock class="w-3 h-3" />
          {{ range.label }}
        </button>
      </div>
    </div>

    <!-- Event-Types Filter ENTFERNT (Phase 5) - DataSource-Filter ist ausreichend -->
  </div>
</template>

<style scoped>
/* === FILTER PANEL - GLASSMORPHISM === */
.filter-panel {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-lg);
  padding: var(--space-md) var(--space-lg);
  border-bottom: 1px solid var(--glass-border);
  background: var(--glass-bg-light);
  backdrop-filter: blur(8px);
}

.filter-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.filter-section--wide {
  flex: 1;
  min-width: 300px;
}

.filter-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.filter-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.filter-actions {
  display: flex;
  gap: var(--space-sm);
}

.filter-action {
  font-size: 0.75rem;
  color: var(--color-iridescent-1);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  transition: all var(--transition-fast);
}

.filter-action:hover {
  color: var(--color-iridescent-2);
  text-decoration: underline;
}

.filter-input-group {
  display: flex;
  gap: var(--space-sm);
}

.filter-input {
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
  font-size: 0.875rem;
  min-width: 150px;
  transition: all var(--transition-base);
}

.filter-input:focus {
  outline: none;
  border-color: var(--color-iridescent-1);
  box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.15);
  background: var(--color-bg-quaternary);
}

.filter-input:hover:not(:focus) {
  border-color: var(--glass-border-hover);
}

.filter-select {
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
  font-size: 0.875rem;
  transition: all var(--transition-base);
  cursor: pointer;
}

.filter-select:focus {
  outline: none;
  border-color: var(--color-iridescent-1);
  box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.15);
}

.filter-chips {
  display: flex;
  gap: var(--space-xs);
}

.filter-chips--wrap {
  flex-wrap: wrap;
}

/* === FILTER CHIP - IRIDESCENT === */
.filter-chip {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  padding: var(--space-xs) var(--space-md);
  border-radius: var(--radius-full);
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--color-text-secondary);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  cursor: pointer;
  transition: all var(--transition-base);
  position: relative;
  overflow: hidden;
}

/* Iridescent hover shine */
.filter-chip::before {
  content: '';
  position: absolute;
  inset: 0;
  background: var(--gradient-iridescent);
  opacity: 0;
  transition: opacity var(--transition-base);
}

.filter-chip:hover::before {
  opacity: 0.1;
}

.filter-chip:hover {
  background: var(--color-bg-quaternary);
  border-color: var(--glass-border-hover);
  transform: translateY(-1px);
}

.filter-chip--active {
  background: var(--gradient-iridescent);
  color: white;
  border-color: var(--color-iridescent-1);
  box-shadow: var(--glass-shadow-glow);
}

.filter-chip--active::before {
  display: none;
}

/* Severity-specific active colors */
.filter-chip--info.filter-chip--active {
  background: linear-gradient(135deg, var(--color-info) 0%, var(--color-accent-bright) 100%);
  border-color: var(--color-info);
  box-shadow: 0 0 15px rgba(96, 165, 250, 0.4);
}

.filter-chip--warning.filter-chip--active {
  background: linear-gradient(135deg, var(--color-warning) 0%, var(--color-warning) 100%);
  border-color: var(--color-warning);
  color: var(--color-bg-tertiary);
  box-shadow: 0 0 15px rgba(251, 191, 36, 0.4);
}

.filter-chip--error.filter-chip--active,
.filter-chip--critical.filter-chip--active {
  background: linear-gradient(135deg, var(--color-error) 0%, var(--gradient-danger-end) 100%);
  border-color: var(--color-error);
  box-shadow: 0 0 15px rgba(248, 113, 113, 0.4);
}

.filter-chip--small {
  padding: var(--space-xs) var(--space-sm);
  font-size: 0.6875rem;
}

/* === MOBILE RESPONSIVE - BOTTOM SHEET === */
@media (max-width: 768px) {
  .filter-panel {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    max-height: 70vh;
    border-radius: var(--radius-2xl) var(--radius-2xl) 0 0;
    z-index: var(--z-fixed);
    overflow-y: auto;
    box-shadow:
      0 -8px 32px rgba(0, 0, 0, 0.3),
      0 0 40px rgba(96, 165, 250, 0.1);
    padding: var(--space-lg);
    padding-bottom: var(--space-xl);
    flex-direction: column;
  }

  /* Handle indicator */
  .filter-panel::before {
    content: '';
    position: absolute;
    top: var(--space-sm);
    left: 50%;
    transform: translateX(-50%);
    width: 40px;
    height: 4px;
    background: var(--color-text-muted);
    border-radius: var(--radius-full);
    opacity: 0.5;
  }

  .filter-section {
    width: 100%;
  }

  .filter-section--wide {
    min-width: auto;
  }

  .filter-input-group {
    flex-direction: column;
  }

  /* Touch-friendly inputs (44px minimum height) */
  .filter-input,
  .filter-select {
    width: 100%;
    min-height: 44px;
    padding: var(--space-md);
    font-size: 1rem;
  }

  .filter-chips {
    flex-wrap: wrap;
    gap: var(--space-sm);
  }

  /* Touch-friendly chips (44px minimum height) */
  .filter-chip {
    min-height: 44px;
    padding: var(--space-sm) var(--space-md);
    font-size: 0.8125rem;
  }

  .filter-chip--small {
    min-height: 36px;
    padding: var(--space-sm) var(--space-md);
    font-size: 0.75rem;
  }

  .filter-label {
    font-size: 0.8125rem;
    margin-bottom: var(--space-xs);
  }

  .filter-action {
    min-height: 44px;
    padding: var(--space-sm);
    font-size: 0.8125rem;
  }
}

@media (max-width: 480px) {
  .filter-panel {
    padding: var(--space-md);
    padding-bottom: var(--space-lg);
  }

  .filter-chip {
    min-height: 40px;
    padding: var(--space-sm);
    font-size: 0.75rem;
  }

  .filter-chip--small {
    min-height: 32px;
    padding: var(--space-xs) var(--space-sm);
    font-size: 0.6875rem;
  }
}

/* Icon sizes */
.w-3 { width: 0.75rem; }
.h-3 { height: 0.75rem; }
</style>
