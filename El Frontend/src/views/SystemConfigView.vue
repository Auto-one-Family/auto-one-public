<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { configApi, type ConfigEntry } from '@/api/config'
import { formatUiApiError, toUiApiError } from '@/api/uiApiError'
import { useOpsLifecycleStore } from '@/shared/stores/ops-lifecycle.store'
import {
  Settings, RefreshCw, Save, AlertCircle, Check, X, Edit, Lock, Eye, EyeOff
} from 'lucide-vue-next'

// State
const configs = ref<ConfigEntry[]>([])
const isLoading = ref(false)
const error = ref<string | null>(null)
const successMessage = ref<string | null>(null)
const saveLifecycleState = ref<'idle' | 'saved' | 'applied' | 'saved_only'>('idle')
const typedConfirm = ref('')

// Edit state
const editingKey = ref<string | null>(null)
const editValue = ref<string>('')
const showSecretValues = ref<Set<string>>(new Set())

// Filter state
const selectedType = ref<string>('')
const router = useRouter()
const opsLifecycle = useOpsLifecycleStore()

// Computed
const configTypes = computed(() => {
  const types = new Set(configs.value.map(c => c.config_type))
  return Array.from(types).sort()
})

const filteredConfigs = computed(() => {
  if (!selectedType.value) return configs.value
  return configs.value.filter(c => c.config_type === selectedType.value)
})

const groupedConfigs = computed(() => {
  const groups: Record<string, ConfigEntry[]> = {}
  for (const config of filteredConfigs.value) {
    if (!groups[config.config_type]) {
      groups[config.config_type] = []
    }
    groups[config.config_type].push(config)
  }
  return groups
})

const isForbiddenError = computed(() => (error.value ?? '').includes('Zugriff verweigert'))

const activeEditConfig = computed(() =>
  editingKey.value
    ? configs.value.find((entry) => entry.config_key === editingKey.value) ?? null
    : null,
)

const parsedEditValue = computed(() => {
  try {
    return JSON.parse(editValue.value)
  } catch {
    return editValue.value
  }
})

const editDiff = computed(() => {
  if (!activeEditConfig.value) return null
  const before = activeEditConfig.value.config_value
  const after = parsedEditValue.value
  if (JSON.stringify(before) === JSON.stringify(after)) {
    return null
  }
  return {
    key: activeEditConfig.value.config_key,
    before,
    after,
  }
})

const editRisk = computed<'low' | 'medium' | 'high'>(() => {
  const key = activeEditConfig.value?.config_key.toLowerCase() ?? ''
  if (!key) return 'low'
  if (/(jwt|secret|password|token|database|mqtt|auth|broker|security)/.test(key)) return 'high'
  if (/(cache|timeout|retry|poll|interval|threshold)/.test(key)) return 'medium'
  return 'low'
})

const requiresTypedConfirm = computed(() => editRisk.value === 'high')

const canSaveEdit = computed(() => {
  if (!editDiff.value) return false
  if (!requiresTypedConfirm.value) return true
  return typedConfirm.value.trim().toUpperCase() === 'APPLY'
})

function goBack(): void {
  router.back()
}

function goHome(): void {
  router.push('/')
}

// Methods
async function loadConfigs(): Promise<void> {
  isLoading.value = true
  error.value = null

  try {
    configs.value = await configApi.listConfig()
  } catch (err: unknown) {
    error.value = formatUiApiError(toUiApiError(err, 'Konfiguration konnte nicht geladen werden'))
  } finally {
    isLoading.value = false
  }
}

function startEdit(config: ConfigEntry): void {
  if (config.is_secret) return
  editingKey.value = config.config_key
  editValue.value = typeof config.config_value === 'string' 
    ? config.config_value 
    : JSON.stringify(config.config_value, null, 2)
  typedConfirm.value = ''
  saveLifecycleState.value = 'idle'
}

function cancelEdit(): void {
  editingKey.value = null
  editValue.value = ''
  typedConfirm.value = ''
  saveLifecycleState.value = 'idle'
}

async function saveConfig(): Promise<void> {
  if (!editingKey.value) return
  if (!canSaveEdit.value) {
    error.value = 'Änderung nicht freigegeben. Diff prüfen und ggf. typed confirm setzen.'
    return
  }

  isLoading.value = true
  error.value = null
  const configKey = editingKey.value
  const saveLifecycleId = opsLifecycle.startLifecycle({
    scope: 'system_config_save',
    title: `SystemConfig speichern: ${configKey}`,
    risk: editRisk.value === 'high' ? 'high' : 'medium',
    summary: 'Save initiiert',
  })
  opsLifecycle.markRunning(saveLifecycleId, 'Konfiguration wird persistiert')

  try {
    // Try to parse as JSON, fall back to string
    let value: unknown
    try {
      value = JSON.parse(editValue.value)
    } catch {
      value = editValue.value
    }

    const response = await configApi.updateConfig(editingKey.value, value)
    opsLifecycle.markSuccess(saveLifecycleId, 'Konfiguration persistent gespeichert')
    saveLifecycleState.value = 'saved'

    const applyLifecycleId = opsLifecycle.startLifecycle({
      scope: 'system_config_apply',
      title: `SystemConfig anwenden: ${configKey}`,
      risk: editRisk.value === 'high' ? 'high' : 'medium',
      summary: 'Runtime-Übernahme wird geprüft',
    })
    opsLifecycle.markRunning(applyLifecycleId, 'Prüfe Runtime-Übernahme')

    const runtimeApplied = Boolean((response as unknown as { runtime_applied?: boolean }).runtime_applied)
    if (runtimeApplied) {
      opsLifecycle.markSuccess(applyLifecycleId, 'Änderung runtime-seitig aktiv')
      saveLifecycleState.value = 'applied'
    } else {
      opsLifecycle.markPartial(applyLifecycleId, 'Nur gespeichert; Runtime-Anwendung nicht bestätigt')
      saveLifecycleState.value = 'saved_only'
    }
    
    editingKey.value = null
    editValue.value = ''
    typedConfirm.value = ''
    successMessage.value = runtimeApplied
      ? 'Konfiguration gespeichert und angewendet.'
      : 'Konfiguration gespeichert. Runtime-Anwendung noch nicht bestätigt.'
    await loadConfigs()
    setTimeout(() => successMessage.value = null, 3000)
  } catch (err: unknown) {
    error.value = formatUiApiError(toUiApiError(err, 'Konfiguration konnte nicht gespeichert werden'))
    opsLifecycle.markFailed(saveLifecycleId, error.value, 'system_config_save_failed')
    saveLifecycleState.value = 'idle'
  } finally {
    isLoading.value = false
  }
}

function toggleSecretVisibility(key: string): void {
  if (showSecretValues.value.has(key)) {
    showSecretValues.value.delete(key)
  } else {
    showSecretValues.value.add(key)
  }
}

function formatValue(config: ConfigEntry): string {
  if (config.is_secret && !showSecretValues.value.has(config.config_key)) {
    return '••••••••'
  }
  
  if (typeof config.config_value === 'object') {
    return JSON.stringify(config.config_value, null, 2)
  }
  return String(config.config_value)
}

function getTypeColor(type: string): string {
  const colors: Record<string, string> = {
    mqtt: 'text-blue-400',
    database: 'text-green-400',
    api: 'text-purple-400',
    security: 'text-red-400',
    pi_enhanced: 'text-yellow-400'
  }
  return colors[type] || 'text-dark-400'
}

onMounted(() => {
  loadConfigs()
})
</script>

<template>
  <div class="h-full overflow-auto space-y-6">
    <!-- Header Actions -->
    <div class="flex flex-wrap items-center gap-2 justify-end">
        <select v-model="selectedType" class="input">
          <option value="">All Types</option>
          <option v-for="type in configTypes" :key="type" :value="type">
            {{ type }}
          </option>
        </select>
        <button
          class="btn-secondary"
          :disabled="isLoading"
          @click="loadConfigs"
        >
          <RefreshCw :class="['w-4 h-4 mr-2', isLoading && 'animate-spin']" />
          Refresh
        </button>
    </div>

    <!-- Alerts -->
    <div
      v-if="error"
      class="p-4 rounded-lg bg-red-500/10 border border-red-500/30 flex items-start gap-3"
    >
      <AlertCircle class="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
      <div class="flex-1">
        <p class="text-sm text-red-400">{{ error }}</p>
        <div v-if="isForbiddenError" class="mt-3 flex flex-wrap gap-2">
          <button class="btn-secondary text-xs" @click="goBack">Zurück</button>
          <button class="btn-secondary text-xs" @click="goHome">Zur Startansicht</button>
          <button class="btn-secondary text-xs" @click="loadConfigs">Erneut versuchen</button>
        </div>
      </div>
      <button class="text-red-400 hover:text-red-300" @click="error = null">
        <X class="w-4 h-4" />
      </button>
    </div>

    <div
      v-if="successMessage"
      class="p-4 rounded-lg bg-green-500/10 border border-green-500/30 flex items-start gap-3"
    >
      <Check class="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
      <p class="text-sm text-green-400">{{ successMessage }}</p>
    </div>

    <!-- Config Groups -->
    <div class="space-y-6">
      <div v-for="(groupConfigs, groupName) in groupedConfigs" :key="groupName" class="card">
        <div class="px-4 py-3 border-b border-dark-700">
          <h3 :class="['font-semibold uppercase tracking-wider text-sm', getTypeColor(groupName)]">
            {{ groupName }}
          </h3>
        </div>
        
        <div class="divide-y divide-dark-800">
          <div
            v-for="config in groupConfigs"
            :key="config.config_key"
            class="p-4 hover:bg-dark-800/30"
          >
            <div class="flex items-start justify-between gap-4">
              <div class="flex-1">
                <div class="flex items-center gap-2">
                  <code class="text-sm font-mono text-dark-100">{{ config.config_key }}</code>
                  <Lock v-if="config.is_secret" class="w-3 h-3 text-yellow-400" title="Secret value" />
                </div>
                <p v-if="config.description" class="text-xs text-dark-500 mt-1">
                  {{ config.description }}
                </p>
              </div>
              
              <!-- Actions -->
              <div class="flex items-center gap-1">
                <button
                  v-if="config.is_secret"
                  class="p-1.5 rounded hover:bg-dark-700 text-dark-400"
                  @click="toggleSecretVisibility(config.config_key)"
                >
                  <component :is="showSecretValues.has(config.config_key) ? EyeOff : Eye" class="w-4 h-4" />
                </button>
                <button
                  v-if="!config.is_secret"
                  class="p-1.5 rounded hover:bg-dark-700 text-dark-400 hover:text-blue-400"
                  @click="startEdit(config)"
                >
                  <Edit class="w-4 h-4" />
                </button>
              </div>
            </div>
            
            <!-- Value Display/Edit -->
            <div class="mt-2">
              <template v-if="editingKey === config.config_key">
                <textarea
                  v-model="editValue"
                  class="input w-full font-mono text-sm"
                  rows="3"
                  placeholder="Enter value (JSON or string)"
                />
                <div
                  v-if="editDiff"
                  class="mt-2 p-2 rounded border text-xs"
                  :class="editRisk === 'high' ? 'border-red-500/40 bg-red-500/10 text-red-300'
                    : editRisk === 'medium' ? 'border-yellow-500/40 bg-yellow-500/10 text-yellow-300'
                      : 'border-green-500/40 bg-green-500/10 text-green-300'"
                >
                  <p><strong>Preflight:</strong> Diff erkannt für <code>{{ editDiff.key }}</code> (Risk: {{ editRisk }})</p>
                  <p class="mt-1"><strong>Before:</strong> {{ JSON.stringify(editDiff.before) }}</p>
                  <p><strong>After:</strong> {{ JSON.stringify(editDiff.after) }}</p>
                </div>
                <div v-if="requiresTypedConfirm" class="mt-2">
                  <label class="text-xs text-dark-400">Typed Confirm: <code>APPLY</code></label>
                  <input
                    v-model="typedConfirm"
                    type="text"
                    class="input w-full font-mono text-sm mt-1"
                    placeholder="APPLY"
                  />
                </div>
                <div v-if="saveLifecycleState !== 'idle'" class="mt-2 text-xs text-dark-300">
                  <span v-if="saveLifecycleState === 'saved'" class="text-blue-300">Status: saved</span>
                  <span v-else-if="saveLifecycleState === 'applied'" class="text-green-300">Status: saved + applied</span>
                  <span v-else-if="saveLifecycleState === 'saved_only'" class="text-yellow-300">
                    Status: saved, applied noch offen - bitte Runtime/Services prüfen.
                  </span>
                </div>
                <div class="flex justify-end gap-2 mt-2">
                  <button class="btn-ghost btn-sm" @click="cancelEdit">
                    Cancel
                  </button>
                  <button class="btn-primary btn-sm" :disabled="isLoading || !canSaveEdit" @click="saveConfig">
                    <Save class="w-3 h-3 mr-1" />
                    Save
                  </button>
                </div>
              </template>
              <template v-else>
                <pre
                  :class="[
                    'p-2 rounded bg-dark-800 text-sm font-mono overflow-x-auto',
                    config.is_secret ? 'text-yellow-400' : 'text-dark-200'
                  ]"
                >{{ formatValue(config) }}</pre>
              </template>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div v-if="!isLoading && configs.length === 0" class="card p-12 text-center">
      <Settings class="w-16 h-16 mx-auto mb-4 text-dark-600" />
      <h3 class="text-lg font-medium text-dark-300 mb-2">No Configuration</h3>
      <p class="text-sm text-dark-500">
        No system configuration entries found
      </p>
    </div>
  </div>
</template>





















