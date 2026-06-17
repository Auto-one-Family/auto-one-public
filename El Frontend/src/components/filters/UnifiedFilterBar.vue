<script setup lang="ts">
/**
 * UnifiedFilterBar
 *
 * Wiederverwendbare Filter-Komponente basierend auf Robin's Favorit-Pattern vom Dashboard.
 * Unterstützt Status-Badges (Multi-Select), Type-Tabs und Time-Range.
 *
 * Usage:
 * <UnifiedFilterBar
 *   v-model:active-status-filters="statusFilters"
 *   v-model:type-filter="typeFilter"
 *   v-model:time-range="timeRange"
 *   :counts="{ online: 5, offline: 2, warning: 1, all: 7, mock: 3, real: 4 }"
 *   :show-status="true"
 *   :show-type="true"
 *   :show-time-range="true"
 * />
 */
import { computed } from 'vue'

import type { StatusFilter, TypeFilter, TimeRange, FilterCounts } from './types'
export type { StatusFilter, TypeFilter, TimeRange, FilterCounts }

interface Props {
  // Filter States (v-model)
  activeStatusFilters?: Set<StatusFilter>
  typeFilter?: TypeFilter
  timeRange?: TimeRange

  // Counts for badges
  counts?: FilterCounts

  // Feature Flags
  showStatus?: boolean
  showType?: boolean
  showTimeRange?: boolean

  // Custom labels (optional, default German)
  statusLabels?: Record<StatusFilter, string>
  typeLabels?: Record<TypeFilter, string>
  timeRangeLabels?: Record<TimeRange, string>
}

const props = withDefaults(defineProps<Props>(), {
  activeStatusFilters: () => new Set<StatusFilter>(),
  typeFilter: 'all',
  timeRange: 'all',
  counts: () => ({}),
  showStatus: true,
  showType: true,
  showTimeRange: true,
  statusLabels: () => ({
    online: 'Online',
    offline: 'Offline',
    warning: 'Fehler',
    safemode: 'Safe Mode'
  }),
  typeLabels: () => ({
    all: 'Alle',
    mock: 'Mock',
    real: 'Echt'
  }),
  timeRangeLabels: () => ({
    '1h': 'Letzte Stunde',
    '6h': 'Letzte 6 Std.',
    '24h': 'Letzte 24 Std.',
    '7d': 'Letzte 7 Tage',
    'all': 'Alle'
  })
})

const emit = defineEmits<{
  'update:activeStatusFilters': [filters: Set<StatusFilter>]
  'update:typeFilter': [filter: TypeFilter]
  'update:timeRange': [range: TimeRange]
  'reset': []
}>()

// Status filter configuration
const statusConfig: Record<StatusFilter, { dot: string; activeBg: string; hoverBg: string; text: string }> = {
  online: {
    dot: 'bg-emerald-500',
    activeBg: 'bg-emerald-500/20 border-emerald-500/50',
    hoverBg: 'hover:bg-emerald-500/10',
    text: 'text-emerald-400'
  },
  offline: {
    dot: 'bg-red-500',
    activeBg: 'bg-red-500/20 border-red-500/50',
    hoverBg: 'hover:bg-red-500/10',
    text: 'text-red-400'
  },
  warning: {
    dot: 'bg-amber-500',
    activeBg: 'bg-amber-500/20 border-amber-500/50',
    hoverBg: 'hover:bg-amber-500/10',
    text: 'text-amber-400'
  },
  safemode: {
    dot: 'bg-orange-500',
    activeBg: 'bg-orange-500/20 border-orange-500/50',
    hoverBg: 'hover:bg-orange-500/10',
    text: 'text-orange-400'
  }
}

// Computed: Available status filters (only show if count > 0 or always show online/offline)
const availableStatusFilters = computed((): StatusFilter[] => {
  const filters: StatusFilter[] = ['online', 'offline']

  if ((props.counts.warning ?? 0) > 0) {
    filters.push('warning')
  }
  if ((props.counts.safemode ?? 0) > 0) {
    filters.push('safemode')
  }

  return filters
})

// Type options
const typeOptions: TypeFilter[] = ['all', 'mock', 'real']

// Time range options
const timeRangeOptions: TimeRange[] = ['1h', '6h', '24h', '7d', 'all']

// Check if a status filter is active
function isStatusActive(filter: StatusFilter): boolean {
  return props.activeStatusFilters.has(filter)
}

// Toggle status filter
function toggleStatusFilter(filter: StatusFilter) {
  const newFilters = new Set(props.activeStatusFilters)
  if (newFilters.has(filter)) {
    newFilters.delete(filter)
  } else {
    newFilters.add(filter)
  }
  emit('update:activeStatusFilters', newFilters)
}

// Get status pill classes
function getStatusPillClasses(filter: StatusFilter): string {
  const base = 'flex items-center gap-2 px-3 py-1.5 rounded-full border transition-all duration-200 cursor-pointer select-none'
  const config = statusConfig[filter]

  if (isStatusActive(filter)) {
    return `${base} ${config.activeBg}`
  }

  return `${base} border-gray-700 ${config.hoverBg}`
}

// Get status count
function getStatusCount(filter: StatusFilter): number {
  return props.counts[filter] ?? 0
}

// Get type count
function getTypeCount(type: TypeFilter): number {
  return props.counts[type] ?? 0
}

// Check if any filters are active
const hasActiveFilters = computed(() => {
  return props.activeStatusFilters.size > 0 ||
         props.typeFilter !== 'all' ||
         props.timeRange !== 'all'
})

// Reset all filters
function resetFilters() {
  emit('update:activeStatusFilters', new Set())
  emit('update:typeFilter', 'all')
  emit('update:timeRange', 'all')
  emit('reset')
}
</script>

<template>
  <div class="unified-filter-bar">
    <!-- Status Badges (Multi-Select Pills) -->
    <div v-if="showStatus" class="filter-section filter-section--status">
      <button
        v-for="status in availableStatusFilters"
        :key="status"
        type="button"
        :class="getStatusPillClasses(status)"
        @click="toggleStatusFilter(status)"
      >
        <span
          class="w-2 h-2 rounded-full"
          :class="statusConfig[status].dot"
        />
        <span
          class="text-sm font-medium"
          :class="isStatusActive(status) ? statusConfig[status].text : 'text-gray-300'"
        >
          {{ getStatusCount(status) }}
        </span>
        <span class="text-sm text-gray-400 hidden sm:inline">
          {{ statusLabels[status] }}
        </span>
      </button>
    </div>

    <!-- Type Tabs -->
    <div v-if="showType" class="filter-section filter-section--type">
      <button
        v-for="type in typeOptions"
        :key="type"
        type="button"
        :class="[
          'type-tab',
          typeFilter === type ? 'type-tab--active' : ''
        ]"
        @click="emit('update:typeFilter', type)"
      >
        {{ typeLabels[type] }}
        <span v-if="getTypeCount(type) > 0" class="type-tab__count">
          ({{ getTypeCount(type) }})
        </span>
      </button>
    </div>

    <!-- Time Range -->
    <div v-if="showTimeRange" class="filter-section filter-section--time">
      <select
        :value="timeRange"
        class="time-select"
        @change="emit('update:timeRange', ($event.target as HTMLSelectElement).value as TimeRange)"
      >
        <option v-for="range in timeRangeOptions" :key="range" :value="range">
          {{ timeRangeLabels[range] }}
        </option>
      </select>
    </div>

    <!-- Reset Button (only when filters active) -->
    <div v-if="hasActiveFilters" class="filter-section filter-section--reset">
      <button
        type="button"
        class="reset-btn"
        @click="resetFilters"
      >
        Filter zurücksetzen
      </button>
    </div>
  </div>
</template>

<style scoped>
.unified-filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem;
  background: rgba(31, 41, 55, 0.5);
  border: 1px solid rgba(75, 85, 99, 0.5);
  border-radius: var(--radius-md);
}

.filter-section {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

/* Status Section: Horizontal scroll on mobile */
.filter-section--status {
  flex-wrap: wrap;
}

/* Type Tabs */
.type-tab {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.375rem 0.75rem;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--color-text-secondary);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.2s ease;
}

.type-tab:hover {
  color: var(--color-text-primary);
  background: rgba(255, 255, 255, 0.05);
}

.type-tab--active {
  color: var(--color-text-primary);
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.2);
}

.type-tab__count {
  color: var(--color-text-tertiary);
}

.type-tab--active .type-tab__count {
  color: var(--color-text-secondary);
}

/* Time Select */
.time-select {
  padding: 0.375rem 2rem 0.375rem 0.75rem;
  font-size: 0.875rem;
  color: var(--color-text-primary);
  background-color: var(--color-bg-tertiary);
  border: 1px solid rgba(75, 85, 99, 0.5);
  border-radius: var(--radius-md);
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%239ca3af' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 0.5rem center;
  background-size: 1rem;
}

.time-select:hover {
  border-color: rgba(107, 114, 128, 0.7);
}

.time-select:focus {
  outline: none;
  border-color: var(--color-iridescent-1);
  box-shadow: 0 0 0 2px rgba(96, 165, 250, 0.2);
}

/* Reset Button */
.reset-btn {
  padding: 0.375rem 0.75rem;
  font-size: 0.875rem;
  color: var(--color-success);
  background: transparent;
  border: none;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
  transition: color 0.2s ease;
}

.reset-btn:hover {
  color: var(--color-success);
}

/* Mobile Responsive */
@media (max-width: 768px) {
  .unified-filter-bar {
    flex-direction: column;
    align-items: stretch;
    gap: 0.5rem;
  }

  .filter-section {
    width: 100%;
  }

  /* Status: Horizontal scroll */
  .filter-section--status {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    flex-wrap: nowrap;
    padding-bottom: 0.25rem;
  }

  /* Type: Full-width buttons */
  .filter-section--type {
    justify-content: stretch;
  }

  .filter-section--type .type-tab {
    flex: 1;
    justify-content: center;
  }

  /* Time: Full-width */
  .time-select {
    width: 100%;
  }

  /* Reset: Center */
  .filter-section--reset {
    justify-content: center;
  }
}
</style>
