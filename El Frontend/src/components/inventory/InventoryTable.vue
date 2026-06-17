<script setup lang="ts">
/**
 * InventoryTable — Flat Hardware Inventory Table
 *
 * Displays all sensors and actuators in a single, searchable, filterable table.
 * Features: column visibility toggle, sorting, pagination, conditional row styling.
 */

import { computed } from 'vue'
import {
  ArrowUp, ArrowDown, ChevronLeft, ChevronRight,
  Circle, Wrench,
} from 'lucide-vue-next'
import { useInventoryStore, INVENTORY_COLUMNS } from '@/shared/stores/inventory.store'
import { formatSensorValue } from '@/utils/formatters'
import { getSensorLabel } from '@/utils/sensorDefaults'
import { ACTUATOR_TYPE_LABELS } from '@/utils/labels'
import type { ComponentItem, SortKey } from '@/shared/stores/inventory.store'

const store = useInventoryStore()

const emit = defineEmits<{
  (e: 'select', item: ComponentItem): void
}>()

// Visible column definitions (ordered)
const activeColumns = computed(() =>
  INVENTORY_COLUMNS.filter(c => store.visibleColumns.includes(c.key))
)

// Status dot color
function statusColor(item: ComponentItem): string {
  if (item.status === 'offline') return 'var(--color-error)'
  if (item.maintenanceOverdue) return 'var(--color-warning)'
  return 'var(--color-success)'
}

// Format display value
function displayValue(item: ComponentItem): string {
  if (item.type === 'actuator') return item.currentValue
  if (item.currentValue === '—') return '—'
  const num = parseFloat(item.currentValue)
  if (isNaN(num)) return item.currentValue
  return formatSensorValue(num, item.unit)
}

// Device type label
function deviceTypeLabel(item: ComponentItem): string {
  if (item.type === 'sensor') return getSensorLabel(item.deviceType)
  return ACTUATOR_TYPE_LABELS[item.deviceType] ?? item.deviceType
}

// Cell value rendering
function cellValue(item: ComponentItem, key: string): string {
  switch (key) {
    case 'name': return item.name
    case 'type': return item.type === 'sensor' ? 'Sensor' : 'Aktor'
    case 'deviceType': return deviceTypeLabel(item)
    case 'zone': return item.zone
    case 'currentValue': return displayValue(item)
    case 'espId': return item.espId
    case 'lastSeen': return item.lastSeen ?? '—'
    case 'nextMaintenance': return item.nextMaintenance ?? '—'
    case 'scope': return item.scope === 'multi_zone' ? 'Multi-Zone' : item.scope === 'mobile' ? 'Mobil' : item.scope === 'zone_local' ? 'Lokal' : '—'
    case 'activeZone': return item.activeZone ?? '—'
    default: return ''
  }
}

// Pagination helpers
const pageNumbers = computed(() => {
  const total = store.totalPages
  const current = store.currentPage
  const pages: number[] = []
  const maxVisible = 5

  if (total <= maxVisible) {
    for (let i = 1; i <= total; i++) pages.push(i)
  } else {
    pages.push(1)
    let start = Math.max(2, current - 1)
    let end = Math.min(total - 1, current + 1)
    if (current <= 2) { start = 2; end = 4 }
    if (current >= total - 1) { start = total - 3; end = total - 1 }
    if (start > 2) pages.push(-1) // ellipsis
    for (let i = start; i <= end; i++) pages.push(i)
    if (end < total - 1) pages.push(-1) // ellipsis
    pages.push(total)
  }
  return pages
})
</script>

<template>
  <div class="inventory-table-wrapper">
    <!-- Table -->
    <div class="inventory-table-scroll">
      <table class="inventory-table">
        <thead>
          <tr>
            <th v-for="col in activeColumns" :key="col.key" :class="['inventory-th', { 'inventory-th--sortable': col.sortable }]">
              <button
                v-if="col.sortable"
                class="inventory-th__btn"
                @click="store.toggleSort(col.key as SortKey)"
              >
                <span>{{ col.label }}</span>
                <template v-if="store.sortKey === col.key">
                  <ArrowUp v-if="store.sortDirection === 'asc'" class="w-3 h-3" />
                  <ArrowDown v-else class="w-3 h-3" />
                </template>
              </button>
              <span v-else>{{ col.label }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in store.paginatedComponents"
            :key="item.id"
            :class="[
              'inventory-row',
              { 'inventory-row--offline': item.status === 'offline' },
              { 'inventory-row--maintenance': item.maintenanceOverdue },
            ]"
            @click="emit('select', item)"
          >
            <td v-for="col in activeColumns" :key="col.key" class="inventory-td">
              <!-- Status column: colored dot -->
              <template v-if="col.key === 'status'">
                <div class="inventory-status">
                  <Circle
                    class="inventory-status__dot"
                    :style="{ color: statusColor(item), fill: statusColor(item) }"
                  />
                  <Wrench
                    v-if="item.maintenanceOverdue"
                    class="inventory-status__wrench"
                  />
                </div>
              </template>

              <!-- Name column: clickable -->
              <template v-else-if="col.key === 'name'">
                <span class="inventory-name">{{ item.name }}</span>
                <span v-if="item.isMock" class="inventory-mock-badge">MOCK</span>
              </template>

              <!-- Default cell -->
              <template v-else>
                {{ cellValue(item, col.key) }}
              </template>
            </td>
          </tr>

          <!-- Empty state -->
          <tr v-if="store.paginatedComponents.length === 0">
            <td :colspan="activeColumns.length" class="inventory-td inventory-td--empty">
              Keine Komponenten gefunden
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div v-if="store.totalPages > 1 || store.totalCount > 10" class="inventory-pagination">
      <div class="inventory-pagination__info">
        {{ (store.currentPage - 1) * store.pageSize + 1 }}–{{ Math.min(store.currentPage * store.pageSize, store.totalCount) }}
        von {{ store.totalCount }}
      </div>

      <div class="inventory-pagination__controls">
        <button
          class="inventory-pagination__btn"
          :disabled="store.currentPage <= 1"
          @click="store.setPage(store.currentPage - 1)"
        >
          <ChevronLeft class="w-4 h-4" />
        </button>

        <template v-for="(page, idx) in pageNumbers" :key="idx">
          <span v-if="page === -1" class="inventory-pagination__ellipsis">…</span>
          <button
            v-else
            :class="['inventory-pagination__btn', { 'inventory-pagination__btn--active': page === store.currentPage }]"
            @click="store.setPage(page)"
          >
            {{ page }}
          </button>
        </template>

        <button
          class="inventory-pagination__btn"
          :disabled="store.currentPage >= store.totalPages"
          @click="store.setPage(store.currentPage + 1)"
        >
          <ChevronRight class="w-4 h-4" />
        </button>
      </div>

      <div class="inventory-pagination__size">
        <select
          :value="store.pageSize"
          class="inventory-pagination__select"
          @change="store.pageSize = Number(($event.target as HTMLSelectElement).value); store.currentPage = 1"
        >
          <option :value="10">10</option>
          <option :value="25">25</option>
          <option :value="50">50</option>
        </select>
        <span class="text-xs text-secondary">pro Seite</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.inventory-table-wrapper {
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.inventory-table-scroll {
  overflow-x: auto;
}

.inventory-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}

/* Header */
.inventory-th {
  text-align: left;
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--glass-border);
  white-space: nowrap;
  background: var(--color-bg-secondary);
}

.inventory-th__btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
  font: inherit;
  text-transform: inherit;
  letter-spacing: inherit;
  padding: 0;
  transition: color var(--transition-fast);
}

.inventory-th__btn:hover {
  color: var(--color-text-primary);
}

/* Rows */
.inventory-row {
  cursor: pointer;
  transition: background var(--transition-fast);
  border-bottom: 1px solid rgba(255, 255, 255, 0.03);
}

.inventory-row:hover {
  background: rgba(255, 255, 255, 0.03);
}

.inventory-row--offline {
  opacity: 0.7;
}

.inventory-row--maintenance {
  border-left: 3px solid var(--color-warning);
}

/* Cells */
.inventory-td {
  padding: var(--space-2) var(--space-3);
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.inventory-td--empty {
  text-align: center;
  padding: var(--space-8);
  color: var(--color-text-muted);
}

/* Status dot */
.inventory-status {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.inventory-status__dot {
  width: 8px;
  height: 8px;
  flex-shrink: 0;
}

.inventory-status__wrench {
  width: 12px;
  height: 12px;
  color: var(--color-warning);
}

/* Name */
.inventory-name {
  color: var(--color-text-primary);
  font-weight: 500;
}

.inventory-mock-badge {
  display: inline-block;
  margin-left: var(--space-2);
  padding: 1px 6px;
  font-size: var(--text-xxs);
  font-weight: 600;
  border-radius: var(--radius-full);
  background: rgba(167, 139, 250, 0.15);
  color: var(--color-mock);
  vertical-align: middle;
}

/* Pagination */
.inventory-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  border-top: 1px solid var(--glass-border);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  gap: var(--space-4);
  flex-wrap: wrap;
}

.inventory-pagination__controls {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.inventory-pagination__btn {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 28px;
  padding: 0 var(--space-1);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: var(--text-xs);
  transition: all var(--transition-fast);
}

.inventory-pagination__btn:hover:not(:disabled) {
  border-color: var(--color-accent);
  color: var(--color-text-primary);
}

.inventory-pagination__btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.inventory-pagination__btn--active {
  background: var(--color-accent);
  border-color: var(--color-accent);
  color: white;
}

.inventory-pagination__ellipsis {
  padding: 0 var(--space-1);
}

.inventory-pagination__size {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.inventory-pagination__select {
  padding: var(--space-1) var(--space-2);
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

.inventory-pagination__info {
  min-width: 80px;
}
</style>
