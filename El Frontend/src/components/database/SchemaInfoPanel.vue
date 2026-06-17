<script setup lang="ts">
import { ref } from 'vue'
import type { TableSchema } from '@/api/database'
import { ChevronDown, ChevronRight, Key, Link, Hash, Type, Calendar, ToggleLeft, Braces } from 'lucide-vue-next'

const props = defineProps<{
  schema: TableSchema | null
}>()

void props // Used in template
const isCollapsed = ref(true)

function getTypeIcon(type: string) {
  switch (type) {
    case 'integer':
    case 'float':
      return Hash
    case 'string':
    case 'uuid':
      return Type
    case 'datetime':
      return Calendar
    case 'boolean':
      return ToggleLeft
    case 'json':
      return Braces
    default:
      return Type
  }
}

function getTypeColor(type: string): string {
  switch (type) {
    case 'integer':
    case 'float':
      return 'text-blue-400'
    case 'string':
      return 'text-green-400'
    case 'uuid':
      return 'text-purple-400'
    case 'datetime':
      return 'text-yellow-400'
    case 'boolean':
      return 'text-orange-400'
    case 'json':
      return 'text-pink-400'
    default:
      return 'text-dark-300'
  }
}
</script>

<template>
  <div v-if="schema" class="card">
    <button
      class="w-full px-4 py-3 flex items-center justify-between hover:bg-dark-800 transition-colors rounded-lg"
      @click="isCollapsed = !isCollapsed"
    >
      <div class="flex items-center gap-2">
        <component :is="isCollapsed ? ChevronRight : ChevronDown" class="w-4 h-4 text-dark-400" />
        <span class="font-medium text-dark-100">Schema</span>
        <span class="text-xs text-dark-400">{{ schema.columns.length }} columns</span>
      </div>
      <span class="text-xs text-dark-500">
        Primary Key: <code class="text-purple-400">{{ schema.primary_key }}</code>
      </span>
    </button>
    
    <div v-if="!isCollapsed" class="px-4 pb-4">
      <div class="border-t border-dark-700 pt-3">
        <div class="grid gap-2">
          <div
            v-for="column in schema.columns"
            :key="column.name"
            class="flex items-center gap-3 p-2 rounded bg-dark-800/50 text-sm"
          >
            <!-- Column name -->
            <div class="flex items-center gap-2 min-w-[180px]">
              <Key v-if="column.primary_key" class="w-3 h-3 text-yellow-400" title="Primary Key" />
              <Link v-else-if="column.foreign_key" class="w-3 h-3 text-blue-400" title="Foreign Key" />
              <span v-else class="w-3" />
              <code class="text-dark-100 font-mono text-xs">{{ column.name }}</code>
            </div>
            
            <!-- Type -->
            <div class="flex items-center gap-1.5 min-w-[100px]">
              <component :is="getTypeIcon(column.type)" :class="['w-3 h-3', getTypeColor(column.type)]" />
              <span :class="['text-xs', getTypeColor(column.type)]">{{ column.type }}</span>
            </div>
            
            <!-- Nullable -->
            <span :class="['text-xs', column.nullable ? 'text-dark-500' : 'text-red-400']">
              {{ column.nullable ? 'nullable' : 'required' }}
            </span>
            
            <!-- Foreign key reference -->
            <span v-if="column.foreign_key" class="text-xs text-blue-400 ml-auto">
              → {{ column.foreign_key }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>





















