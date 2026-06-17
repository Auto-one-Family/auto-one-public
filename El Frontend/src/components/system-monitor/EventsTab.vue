<script setup lang="ts">
/**
 * EventsTab - Events Tab for System Monitor
 *
 * Features:
 * - Unified event stream (Sensor, Actuator, System, Error events)
 * - Integrated DataSourceSelector with Filter controls
 * - Mobile-responsive design
 *
 * Layout Pattern:
 * - Consistent with ServerLogsTab, DatabaseTab, MqttTrafficTab
 * - One root container with flex-column
 * - Filter section fixed at top (flex-shrink: 0)
 * - Content section scrollable (flex: 1, overflow-y: auto)
 *
 * @see SystemMonitorView.vue - Parent component
 */

// No icons needed - status bar removed
import DataSourceSelector from './DataSourceSelector.vue'
import UnifiedEventList from './UnifiedEventList.vue'
import type { UnifiedEvent } from '@/types'
import type { DataSource } from '@/api/audit'
import type { EventOrGroup } from '@/types/event-grouping'

// ============================================================================
// Types
// ============================================================================

type TimeRange = 'all' | '1h' | '6h' | '24h' | '7d' | '30d' | 'custom'

// ============================================================================
// Props
// ============================================================================

interface Props {
  // Event data
  filteredEvents: UnifiedEvent[]
  groupedEvents: EventOrGroup[]
  totalAvailableEvents: number
  hasMoreEvents: boolean
  isLoadingMore: boolean
  isPaused: boolean
  restoredEventIds: Set<string>
  // Filter props (passed to DataSourceSelector)
  filterEspId: string
  filterLevels: Set<string>
  filterTimeRange: TimeRange
  uniqueEspIds: string[]
  // Custom Date Range (for 'custom' timeRange)
  customStartDate?: string
  customEndDate?: string
  // Grouping
  groupingEnabled: boolean
}

defineProps<Props>()

// ============================================================================
// Emits
// ============================================================================

const emit = defineEmits<{
  // DataSource changes
  'data-sources-change': [sources: DataSource[]]
  // Filter changes (from DataSourceSelector)
  'update:filterEspId': [value: string]
  'update:filterLevels': [value: Set<string>]
  'update:filterTimeRange': [value: TimeRange]
  // Custom Date Range changes
  'update:customStartDate': [value: string | undefined]
  'update:customEndDate': [value: string | undefined]
  // Actions
  'load-more': []
  'select': [event: UnifiedEvent]
  // Grouping
  'update:groupingEnabled': [value: boolean]
}>()

// ============================================================================
// Handlers
// ============================================================================

function handleDataSourcesChange(sources: DataSource[]) {
  emit('data-sources-change', sources)
}

function handleEspIdChange(value: string) {
  emit('update:filterEspId', value)
}

function handleLevelsChange(value: Set<string>) {
  emit('update:filterLevels', value)
}

function handleTimeRangeChange(value: TimeRange) {
  emit('update:filterTimeRange', value)
}

function handleCustomStartDateChange(value: string | undefined) {
  emit('update:customStartDate', value)
}

function handleCustomEndDateChange(value: string | undefined) {
  emit('update:customEndDate', value)
}

function selectEvent(event: UnifiedEvent) {
  emit('select', event)
}

</script>

<template>
  <div class="events-tab">
    <p
      class="events-tab__stream-hint"
      data-testid="system-monitor-events-stream-hint"
    >
      Echtzeit-Stream inkl. Fehler — Inbox/Ack im Meldungs-Panel (Glocke).
    </p>
    <!-- Filter Section (fixed at top) - DataSourceSelector now includes all filters -->
    <div class="events-filters">
      <DataSourceSelector
        :esp-id="filterEspId"
        :levels="filterLevels"
        :time-range="filterTimeRange"
        :unique-esp-ids="uniqueEspIds"
        :custom-start-date="customStartDate"
        :custom-end-date="customEndDate"
        :grouping-enabled="groupingEnabled"
        @change="handleDataSourcesChange"
        @update:esp-id="handleEspIdChange"
        @update:levels="handleLevelsChange"
        @update:time-range="handleTimeRangeChange"
        @update:custom-start-date="handleCustomStartDateChange"
        @update:custom-end-date="handleCustomEndDateChange"
        @update:grouping-enabled="(v: boolean) => emit('update:groupingEnabled', v)"
      />
    </div>

    <!-- Event List (direkter Scroll-Container) -->
    <div class="events-list">
      <UnifiedEventList
        :events="filteredEvents"
        :grouped-events="groupedEvents"
        :grouping-enabled="groupingEnabled"
        :is-paused="isPaused"
        :restored-event-ids="restoredEventIds"
        :has-active-filters="filterEspId !== '' || filterLevels.size > 0 || filterTimeRange !== 'all'"
        @select="selectEvent"
      />
    </div>
  </div>
</template>

<style scoped>
/* =============================================================================
   Events Tab - Main Container
   ============================================================================= */
.events-tab {
  display: flex;
  flex-direction: column;
  flex: 1;  /* ⭐ FIX: Nutze flex: 1 statt height: 100% für korrekte Flexbox-Hierarchie */
  /* ⭐ Page-Scroll: Kein overflow: hidden - Seite scrollt als Ganzes */
}

.events-tab__stream-hint {
  flex-shrink: 0;
  margin: 0 0 var(--space-2);
  padding: 0 var(--space-1);
  font-size: var(--text-sm);
  line-height: 1.35;
  color: var(--color-text-secondary);
}

/* =============================================================================
   Filter Section (fixed at top)
   ============================================================================= */
.events-filters {
  flex-shrink: 0;  /* ⭐ Bleibt oben fixiert, scrollt NICHT mit */
  /* No overflow-y, no height - just auto-size */
}

/* =============================================================================
   Events List (Container für UnifiedEventList)
   ============================================================================= */
.events-list {
  flex: 1;
  /* ⭐ Page-Scroll: Kein overflow - Events fließen natürlich in die Seite */
  display: flex;
  flex-direction: column;
}

</style>
