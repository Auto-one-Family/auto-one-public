<script setup lang="ts">
import { computed } from 'vue'
import type { ColumnSchema, SortOrder } from '@/api/database'
import { ArrowUp, ArrowDown, ArrowUpDown, Eye } from 'lucide-vue-next'
import { formatRelativeTime } from '@/utils/formatters'

const props = defineProps<{
  columns: ColumnSchema[]
  data: Record<string, unknown>[]
  loading?: boolean
  sortBy?: string
  sortOrder?: SortOrder
}>()

const emit = defineEmits<{
  sort: [column: string]
  rowClick: [record: Record<string, unknown>]
}>()

/**
 * Visible columns - uses pre-filtered columns from parent component
 *
 * The parent (DatabaseTab) is responsible for filtering columns
 * based on defaultVisible from databaseColumnTranslator.
 *
 * Robin's Prinzipien:
 * - Timestamps FIRST (created_at, last_seen)
 * - IDs NEVER visible (id, zone_id, user_id)
 * - Limit to 8 columns to prevent horizontal overflow
 */
const visibleColumns = computed(() => {
  // Parent already filtered/ordered, just limit count
  return props.columns.slice(0, 8)
})

/**
 * Check if a string looks like a UUID
 */
function isUuid(str: string): boolean {
  // UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx (36 chars)
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
  return uuidRegex.test(str)
}

/**
 * Format UUID for display (shortened)
 */
function formatUuid(uuid: string): string {
  return uuid.substring(0, 8) + '...'
}

interface FormattedValue {
  display: string
  tooltip?: string  // Full value for hover
}

function formatValue(value: unknown, type: string): FormattedValue {
  if (value === null || value === undefined) {
    return { display: '—' }
  }

  if (value === '***MASKED***') {
    return { display: '••••••••', tooltip: 'Masked for security' }
  }

  // Handle datetime with relative time
  if (type === 'datetime' && typeof value === 'string') {
    try {
      const date = new Date(value)
      const relative = formatRelativeTime(date)
      const full = date.toLocaleString('de-DE', {
        dateStyle: 'medium',
        timeStyle: 'medium'
      })
      return { display: relative, tooltip: full }
    } catch {
      return { display: String(value) }
    }
  }

  if (type === 'boolean') {
    return { display: value ? 'true' : 'false' }
  }

  if (type === 'json') {
    const jsonStr = JSON.stringify(value)
    return { display: '{...}', tooltip: jsonStr.substring(0, 200) + (jsonStr.length > 200 ? '...' : '') }
  }

  const str = String(value)

  // Handle UUIDs - shorten for readability
  if (isUuid(str)) {
    return { display: formatUuid(str), tooltip: str }
  }

  // Truncate long values
  if (str.length > 50) {
    return { display: str.substring(0, 47) + '...', tooltip: str }
  }
  return { display: str }
}

function getValueClass(value: unknown, type: string): string {
  if (value === null || value === undefined) {
    return 'text-dark-500 italic'
  }
  
  if (value === '***MASKED***') {
    return 'text-yellow-400'
  }
  
  if (type === 'boolean') {
    return value ? 'text-green-400' : 'text-red-400'
  }
  
  return 'text-dark-200'
}

function getSortIcon(column: string) {
  if (props.sortBy !== column) {
    return ArrowUpDown
  }
  return props.sortOrder === 'asc' ? ArrowUp : ArrowDown
}

function getPrimaryKeyValue(record: Record<string, unknown>): string {
  const pkColumn = props.columns.find(c => c.primary_key)
  if (pkColumn) {
    return String(record[pkColumn.name] || '')
  }
  // Fallback to id
  return String(record['id'] || '')
}
</script>

<template>
  <div class="card overflow-hidden">
    <div class="overflow-x-auto">
      <table class="w-full">
        <thead>
          <tr class="border-b border-dark-700">
            <th
              v-for="column in visibleColumns"
              :key="column.name"
              class="text-left p-3 text-xs font-medium text-dark-400 uppercase tracking-wider cursor-pointer hover:bg-dark-800 transition-colors"
              @click="emit('sort', column.name)"
            >
              <div class="flex items-center gap-1">
                <span :title="column.label ? column.name : undefined">{{ column.label || column.name }}</span>
                <component
                  :is="getSortIcon(column.name)"
                  :class="[
                    'w-3 h-3',
                    sortBy === column.name ? 'text-purple-400' : 'text-dark-500'
                  ]"
                />
              </div>
            </th>
            <th class="w-10 p-3"></th>
          </tr>
        </thead>
        <tbody v-if="!loading && data.length > 0">
          <tr
            v-for="(record, index) in data"
            :key="getPrimaryKeyValue(record)"
            :class="[
              'border-b border-dark-800 hover:bg-dark-800/50 transition-colors cursor-pointer',
              index % 2 === 0 ? 'bg-dark-900/30' : ''
            ]"
            @click="emit('rowClick', record)"
          >
            <td
              v-for="column in visibleColumns"
              :key="column.name"
              class="p-3 text-sm font-mono"
            >
              <span
                :class="getValueClass(record[column.name], column.type)"
                :title="formatValue(record[column.name], column.type).tooltip"
              >
                {{ formatValue(record[column.name], column.type).display }}
              </span>
            </td>
            <td class="p-3">
              <button
                class="p-1 rounded hover:bg-dark-700 transition-colors"
                title="View Details"
                @click.stop="emit('rowClick', record)"
              >
                <Eye class="w-4 h-4 text-dark-400" />
              </button>
            </td>
          </tr>
        </tbody>
        <tbody v-else-if="loading">
          <tr>
            <td :colspan="visibleColumns.length + 1" class="p-8 text-center text-dark-400">
              <div class="flex items-center justify-center gap-2">
                <div class="w-4 h-4 border-2 border-purple-500 border-t-transparent rounded-full animate-spin"></div>
                Loading data...
              </div>
            </td>
          </tr>
        </tbody>
        <tbody v-else>
          <tr>
            <td :colspan="visibleColumns.length + 1" class="p-8 text-center text-dark-400">
              No data found
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>





















