<script setup lang="ts">
import { computed, ref } from 'vue'
import { X, Copy, Check, ExternalLink } from 'lucide-vue-next'
import { createLogger } from '@/utils/logger'

const log = createLogger('RecordDetail')

const props = defineProps<{
  tableName: string
  record: Record<string, unknown>
}>()

const emit = defineEmits<{
  close: []
  navigateToForeignKey: [table: string, id: string]
}>()

const copied = ref(false)

const formattedJson = computed(() => {
  return JSON.stringify(props.record, null, 2)
})

// Detect foreign key references in the data
const foreignKeyLinks = computed(() => {
  const links: { key: string; table: string; id: string }[] = []
  
  for (const [key, value] of Object.entries(props.record)) {
    // Look for common FK patterns
    if (key.endsWith('_id') && value) {
      const tableName = key.replace('_id', '') + 's'
      links.push({ key, table: tableName, id: String(value) })
    }
  }
  
  return links
})

async function copyJson(): Promise<void> {
  try {
    await navigator.clipboard.writeText(formattedJson.value)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 2000)
  } catch (err) {
    log.error('Failed to copy', err)
  }
}

function formatValue(value: unknown): string {
  if (value === null) return 'null'
  if (value === undefined) return 'undefined'
  if (value === '***MASKED***') return '••••••••'
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

function getValueClass(value: unknown): string {
  if (value === null || value === undefined) return 'text-dark-500'
  if (value === '***MASKED***') return 'text-yellow-400'
  if (typeof value === 'boolean') return value ? 'text-green-400' : 'text-red-400'
  if (typeof value === 'number') return 'text-blue-400'
  if (typeof value === 'string') return 'text-green-300'
  return 'text-dark-200'
}

function isObject(value: unknown): boolean {
  return typeof value === 'object' && value !== null
}
</script>

<template>
  <div class="fixed inset-0 flex items-center justify-center p-4" style="z-index: var(--z-modal); background: var(--backdrop-color); backdrop-filter: blur(var(--backdrop-blur)); -webkit-backdrop-filter: blur(var(--backdrop-blur))">
    <div class="card w-full max-w-3xl max-h-[90vh] flex flex-col">
      <!-- Header -->
      <div class="flex items-center justify-between p-4 border-b border-dark-700">
        <div>
          <h3 class="text-lg font-semibold text-dark-100">Record Details</h3>
          <p class="text-sm text-dark-400">{{ tableName }}</p>
        </div>
        <div class="flex items-center gap-2">
          <button
            class="btn-secondary btn-sm"
            @click="copyJson"
          >
            <component :is="copied ? Check : Copy" class="w-4 h-4 mr-1" />
            {{ copied ? 'Copied!' : 'Copy JSON' }}
          </button>
          <button
            class="p-2 rounded-lg hover:bg-dark-700 transition-colors"
            @click="emit('close')"
          >
            <X class="w-5 h-5 text-dark-400" />
          </button>
        </div>
      </div>
      
      <!-- Content -->
      <div class="flex-1 overflow-y-auto p-4">
        <div class="space-y-3">
          <div
            v-for="(value, key) in record"
            :key="String(key)"
            class="flex gap-4 p-3 rounded-lg bg-dark-800/50"
          >
            <!-- Key -->
            <div class="w-40 flex-shrink-0">
              <code class="text-sm text-purple-400 font-mono">{{ key }}</code>
            </div>
            
            <!-- Value -->
            <div class="flex-1 overflow-hidden">
              <pre
                v-if="isObject(value)"
                class="text-xs font-mono text-dark-200 whitespace-pre-wrap overflow-x-auto bg-dark-900 rounded p-2"
              >{{ formatValue(value) }}</pre>
              <span
                v-else
                :class="['text-sm font-mono break-all', getValueClass(value)]"
              >{{ formatValue(value) }}</span>
              
              <!-- Foreign key link -->
              <div
                v-if="foreignKeyLinks.find(l => l.key === key)"
                class="mt-1"
              >
                <button
                  class="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
                  @click="emit('navigateToForeignKey', foreignKeyLinks.find(l => l.key === key)!.table, foreignKeyLinks.find(l => l.key === key)!.id)"
                >
                  <ExternalLink class="w-3 h-3" />
                  View in {{ foreignKeyLinks.find(l => l.key === key)!.table }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <!-- Footer -->
      <div class="p-4 border-t border-dark-700 flex justify-end">
        <button class="btn-secondary" @click="emit('close')">
          Close
        </button>
      </div>
    </div>
  </div>
</template>





















