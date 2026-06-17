<script setup lang="ts">
import { computed } from 'vue'
import type { TableSchema } from '@/api/database'
import { Database, ChevronDown } from 'lucide-vue-next'

const props = defineProps<{
  tables: TableSchema[]
  selectedTable: string | null
  loading?: boolean
}>()

const emit = defineEmits<{
  select: [tableName: string]
}>()

const sortedTables = computed(() => {
  return [...props.tables].sort((a, b) => a.table_name.localeCompare(b.table_name))
})

function formatRowCount(count: number): string {
  if (count >= 1000000) {
    return `${(count / 1000000).toFixed(1)}M`
  } else if (count >= 1000) {
    return `${(count / 1000).toFixed(1)}K`
  }
  return count.toString()
}
</script>

<template>
  <div class="relative">
    <label class="label text-sm text-dark-400 mb-1">Select Table</label>
    <div class="relative">
      <select
        :value="selectedTable || ''"
        :disabled="loading"
        class="input w-full pr-10 appearance-none cursor-pointer"
        @change="emit('select', ($event.target as HTMLSelectElement).value)"
      >
        <option value="" disabled>
          {{ loading ? 'Loading tables...' : 'Choose a table to explore' }}
        </option>
        <option
          v-for="table in sortedTables"
          :key="table.table_name"
          :value="table.table_name"
        >
          {{ table.table_name }} ({{ formatRowCount(table.row_count) }} rows)
        </option>
      </select>
      <div class="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none">
        <ChevronDown class="w-4 h-4 text-dark-400" />
      </div>
    </div>
    
    <!-- Quick stats when table is selected -->
    <div v-if="selectedTable" class="mt-2 flex items-center gap-4 text-xs text-dark-400">
      <span class="flex items-center gap-1">
        <Database class="w-3 h-3" />
        {{ tables.find(t => t.table_name === selectedTable)?.columns.length || 0 }} columns
      </span>
      <span>
        {{ formatRowCount(tables.find(t => t.table_name === selectedTable)?.row_count || 0) }} total rows
      </span>
    </div>
  </div>
</template>





















