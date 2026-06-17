<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { ColumnSchema } from '@/api/database'
import { Filter, X, Plus, Search } from 'lucide-vue-next'

const props = defineProps<{
  columns: ColumnSchema[]
  currentFilters?: Record<string, unknown>
}>()

const emit = defineEmits<{
  apply: [filters: Record<string, unknown>]
  clear: []
}>()

interface FilterEntry {
  id: number
  column: string
  operator: string
  value: string
}

const filterIdCounter = ref(0)
const filters = ref<FilterEntry[]>([])
const isExpanded = ref(false)

// Filterable columns (exclude json type)
const filterableColumns = computed(() => 
  props.columns.filter(c => c.type !== 'json')
)

// Available operators based on column type
function getOperators(columnType: string): { value: string; label: string }[] {
  switch (columnType) {
    case 'integer':
    case 'float':
      return [
        { value: 'eq', label: '=' },
        { value: 'gte', label: '>=' },
        { value: 'lte', label: '<=' },
        { value: 'gt', label: '>' },
        { value: 'lt', label: '<' }
      ]
    case 'datetime':
      return [
        { value: 'gte', label: 'After' },
        { value: 'lte', label: 'Before' }
      ]
    case 'boolean':
      return [
        { value: 'eq', label: '=' }
      ]
    case 'string':
    case 'uuid':
    default:
      return [
        { value: 'eq', label: '=' },
        { value: 'contains', label: 'contains' }
      ]
  }
}

function getColumnType(columnName: string): string {
  return props.columns.find(c => c.name === columnName)?.type || 'string'
}

function addFilter(): void {
  if (filterableColumns.value.length === 0) return
  
  filters.value.push({
    id: ++filterIdCounter.value,
    column: filterableColumns.value[0].name,
    operator: 'eq',
    value: ''
  })
  isExpanded.value = true
}

function removeFilter(id: number): void {
  filters.value = filters.value.filter(f => f.id !== id)
}

function applyFilters(): void {
  const result: Record<string, unknown> = {}
  
  for (const filter of filters.value) {
    if (!filter.value) continue
    
    const columnType = getColumnType(filter.column)
    let value: unknown = filter.value
    
    // Convert value based on type
    if (columnType === 'integer') {
      value = parseInt(filter.value, 10)
    } else if (columnType === 'float') {
      value = parseFloat(filter.value)
    } else if (columnType === 'boolean') {
      value = filter.value === 'true'
    }
    
    // Build filter key
    const key = filter.operator === 'eq' 
      ? filter.column 
      : `${filter.column}__${filter.operator}`
    
    result[key] = value
  }
  
  emit('apply', result)
}

function clearFilters(): void {
  filters.value = []
  emit('clear')
}

// Watch for external filter changes
watch(() => props.currentFilters, (newFilters) => {
  if (!newFilters || Object.keys(newFilters).length === 0) {
    filters.value = []
  }
}, { immediate: true })

const hasActiveFilters = computed(() => 
  props.currentFilters && Object.keys(props.currentFilters).length > 0
)
</script>

<template>
  <div class="card">
    <div class="px-4 py-3 flex items-center justify-between">
      <div class="flex items-center gap-2">
        <Filter class="w-4 h-4 text-dark-400" />
        <span class="font-medium text-dark-100 text-sm">Filters</span>
        <span v-if="hasActiveFilters" class="badge badge-primary text-xs">
          {{ Object.keys(currentFilters || {}).length }} active
        </span>
      </div>
      <div class="flex items-center gap-2">
        <button
          v-if="hasActiveFilters"
          class="btn-ghost btn-sm text-red-400"
          @click="clearFilters"
        >
          <X class="w-3 h-3 mr-1" />
          Clear
        </button>
        <button
          class="btn-secondary btn-sm"
          @click="addFilter"
        >
          <Plus class="w-3 h-3 mr-1" />
          Add Filter
        </button>
      </div>
    </div>
    
    <div v-if="filters.length > 0" class="px-4 pb-4 space-y-3">
      <div
        v-for="filter in filters"
        :key="filter.id"
        class="flex items-center gap-2"
      >
        <!-- Column selector -->
        <select
          v-model="filter.column"
          class="input text-sm flex-1"
          @change="filter.operator = getOperators(getColumnType(filter.column))[0].value"
        >
          <option
            v-for="col in filterableColumns"
            :key="col.name"
            :value="col.name"
          >
            {{ col.name }}
          </option>
        </select>
        
        <!-- Operator selector -->
        <select
          v-model="filter.operator"
          class="input text-sm w-24"
        >
          <option
            v-for="op in getOperators(getColumnType(filter.column))"
            :key="op.value"
            :value="op.value"
          >
            {{ op.label }}
          </option>
        </select>
        
        <!-- Value input -->
        <template v-if="getColumnType(filter.column) === 'boolean'">
          <select v-model="filter.value" class="input text-sm flex-1">
            <option value="true">true</option>
            <option value="false">false</option>
          </select>
        </template>
        <template v-else-if="getColumnType(filter.column) === 'datetime'">
          <input
            v-model="filter.value"
            type="datetime-local"
            class="input text-sm flex-1"
          />
        </template>
        <template v-else>
          <input
            v-model="filter.value"
            :type="getColumnType(filter.column) === 'integer' || getColumnType(filter.column) === 'float' ? 'number' : 'text'"
            :step="getColumnType(filter.column) === 'float' ? '0.01' : undefined"
            placeholder="Value..."
            class="input text-sm flex-1"
          />
        </template>
        
        <!-- Remove button -->
        <button
          class="btn-ghost btn-sm text-red-400 p-1"
          @click="removeFilter(filter.id)"
        >
          <X class="w-4 h-4" />
        </button>
      </div>
      
      <!-- Apply button -->
      <button
        class="btn-primary btn-sm w-full"
        @click="applyFilters"
      >
        <Search class="w-3 h-3 mr-1" />
        Apply Filters
      </button>
    </div>
  </div>
</template>





















