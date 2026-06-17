<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import {
  loadTestApi,
  type MetricsResponse,
  type LoadTestCapabilities,
  type LoadTestPreflightResponse,
} from '@/api/loadtest'
import {
  Zap, Plus, Play, Square, RefreshCw, AlertCircle, Check, X,
  Server, Thermometer, Power, MessageSquare, Clock, Info
} from 'lucide-vue-next'
import { createLogger } from '@/utils/logger'
import { useOpsLifecycleStore } from '@/shared/stores/ops-lifecycle.store'

const logger = createLogger('LoadTest')
const opsLifecycle = useOpsLifecycleStore()

// State
const metrics = ref<MetricsResponse | null>(null)
const isLoading = ref(false)
const error = ref<string | null>(null)
const successMessage = ref<string | null>(null)
const capabilities = ref<LoadTestCapabilities | null>(null)
const preflight = ref<LoadTestPreflightResponse | null>(null)
const typedConfirm = ref('')
const lastSummary = ref<string | null>(null)

// Bulk create form
const bulkCount = ref(10)
const bulkPrefix = ref('LOAD_TEST')
const bulkSensors = ref(2)
const bulkActuators = ref(1)

// Simulation form
const simInterval = ref(1000)
const simDuration = ref(60)

// Metrics refresh
const metricsInterval = ref<ReturnType<typeof setInterval> | null>(null)
const isSimulating = ref(false)
const activeSimulationLifecycleId = ref<string | null>(null)

const preflightPayload = computed(() => ({
  bulk_count: bulkCount.value,
  sensors_per_device: bulkSensors.value,
  actuators_per_device: bulkActuators.value,
  interval_ms: simInterval.value,
  duration_seconds: simDuration.value,
}))

const needsTypedConfirm = computed(() =>
  (preflight.value?.impact === 'high') || bulkCount.value >= 50,
)

const canRunHighRiskAction = computed(() => {
  if (!preflight.value?.allowed) return false
  if (!needsTypedConfirm.value) return true
  return typedConfirm.value.trim().toUpperCase() === 'START'
})

// Methods
async function loadMetrics(): Promise<void> {
  try {
    metrics.value = await loadTestApi.getMetrics()
  } catch (err) {
    logger.error('Failed to load metrics', err)
  }
}

async function loadCapabilities(): Promise<void> {
  capabilities.value = await loadTestApi.getCapabilities()
  bulkCount.value = Math.min(bulkCount.value, capabilities.value.max_bulk_count)
  bulkSensors.value = Math.min(bulkSensors.value, capabilities.value.max_sensors_per_device)
  bulkActuators.value = Math.min(bulkActuators.value, capabilities.value.max_actuators_per_device)
  simInterval.value = Math.max(simInterval.value, capabilities.value.min_interval_ms)
  simInterval.value = Math.min(simInterval.value, capabilities.value.max_interval_ms)
  simDuration.value = Math.max(simDuration.value, capabilities.value.min_duration_seconds)
  simDuration.value = Math.min(simDuration.value, capabilities.value.max_duration_seconds)
}

async function runPreflight(): Promise<void> {
  preflight.value = await loadTestApi.preflight(preflightPayload.value)
  if (preflight.value.allowed) {
    successMessage.value = 'Preflight erfolgreich.'
    setTimeout(() => successMessage.value = null, 2500)
  } else {
    error.value = preflight.value.message
  }
}

async function bulkCreate(): Promise<void> {
  if (!canRunHighRiskAction.value) {
    error.value = 'Preflight/Bestätigung unvollständig. Bitte Guardrail-Schritte abschließen.'
    return
  }
  isLoading.value = true
  error.value = null
  const lifecycleId = opsLifecycle.startLifecycle({
    scope: 'loadtest_bulk_create',
    title: 'Loadtest: Bulk-Create Mock-ESPs',
    risk: 'high',
    summary: 'Bulk-Create initiiert',
  })
  opsLifecycle.markRunning(lifecycleId, 'Bulk-Create läuft')

  try {
    const response = await loadTestApi.bulkCreate({
      count: bulkCount.value,
      prefix: bulkPrefix.value,
      with_sensors: bulkSensors.value,
      with_actuators: bulkActuators.value
    })
    
    successMessage.value = response.message
    lastSummary.value = `Bulk-Create: ${response.created_count} Geräte erstellt. Nächster sicherer Schritt: Metriken prüfen und erst danach Simulation starten.`
    opsLifecycle.markSuccess(lifecycleId, lastSummary.value)
    await loadMetrics()
    setTimeout(() => successMessage.value = null, 5000)
  } catch (err: unknown) {
    const axiosError = err as { response?: { data?: { detail?: string } } }
    error.value = axiosError.response?.data?.detail || 'Failed to create mock ESPs'
    opsLifecycle.markFailed(lifecycleId, error.value, 'loadtest_bulk_create_failed')
  } finally {
    isLoading.value = false
  }
}

async function startSimulation(): Promise<void> {
  if (!canRunHighRiskAction.value) {
    error.value = 'Preflight/Bestätigung unvollständig. Bitte Guardrail-Schritte abschließen.'
    return
  }
  isLoading.value = true
  error.value = null
  const lifecycleId = opsLifecycle.startLifecycle({
    scope: 'loadtest_simulation',
    title: 'Loadtest: Simulation starten',
    risk: 'high',
    summary: 'Simulation initiiert',
  })
  activeSimulationLifecycleId.value = lifecycleId
  opsLifecycle.markRunning(lifecycleId, 'Simulation läuft')

  try {
    const response = await loadTestApi.startSimulation({
      interval_ms: simInterval.value,
      duration_seconds: simDuration.value
    })
    
    isSimulating.value = true
    successMessage.value = response.message
    lastSummary.value = `Simulation gestartet${response.simulation_id ? ` (ID: ${response.simulation_id})` : ''}. Kill-Switch bleibt aktiv.`
    opsLifecycle.markPartial(lifecycleId, 'Simulation aktiv - manuelles Stop erforderlich')
    await loadMetrics()
    
    // Start metrics refresh
    if (metricsInterval.value) clearInterval(metricsInterval.value)
    metricsInterval.value = setInterval(loadMetrics, 2000)
    
    setTimeout(() => successMessage.value = null, 3000)
  } catch (err: unknown) {
    const axiosError = err as { response?: { data?: { detail?: string } } }
    error.value = axiosError.response?.data?.detail || 'Failed to start simulation'
    opsLifecycle.markFailed(lifecycleId, error.value, 'loadtest_start_failed')
  } finally {
    isLoading.value = false
  }
}

async function stopSimulation(): Promise<void> {
  isLoading.value = true
  error.value = null

  try {
    const response = await loadTestApi.stopSimulation()
    
    isSimulating.value = false
    successMessage.value = response.message
    lastSummary.value = 'Simulation gestoppt. Nächster sicherer Schritt: Metriken/Logs auf Nebenwirkungen prüfen.'
    if (activeSimulationLifecycleId.value) {
      opsLifecycle.markSuccess(activeSimulationLifecycleId.value, lastSummary.value)
      activeSimulationLifecycleId.value = null
    }
    
    // Stop metrics refresh
    if (metricsInterval.value) {
      clearInterval(metricsInterval.value)
      metricsInterval.value = null
    }
    
    await loadMetrics()
    setTimeout(() => successMessage.value = null, 3000)
  } catch (err: unknown) {
    const axiosError = err as { response?: { data?: { detail?: string } } }
    error.value = axiosError.response?.data?.detail || 'Failed to stop simulation'
    if (activeSimulationLifecycleId.value) {
      opsLifecycle.markFailed(activeSimulationLifecycleId.value, error.value, 'loadtest_stop_failed')
    }
  } finally {
    isLoading.value = false
  }
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  return `${(seconds / 3600).toFixed(1)}h`
}

// Lifecycle
onMounted(() => {
  loadCapabilities()
  loadMetrics()
})

onUnmounted(() => {
  if (metricsInterval.value) {
    clearInterval(metricsInterval.value)
  }
})
</script>

<template>
  <div class="h-full overflow-auto space-y-6">
    <!-- Intro / Anleitung (sichtbar wenn keine Mock-ESPs aktiv) -->
    <div v-if="!metrics || metrics.mock_esp_count === 0" class="loadtest-intro">
      <div class="loadtest-intro__icon-wrap">
        <Info class="loadtest-intro__icon" />
      </div>
      <div class="loadtest-intro__body">
        <h3 class="loadtest-intro__title">Lasttest noch nicht gestartet</h3>
        <p class="loadtest-intro__text">
          Hier kannst du das System mit virtuellen Mock-ESPs unter Last setzen, um
          Server, MQTT-Broker und Datenbank zu validieren. Drei Schritte:
        </p>
        <ol class="loadtest-intro__steps">
          <li><strong>Preflight pruefen</strong> &mdash; das System schaetzt Geraete-Anzahl, Nachrichten-Volumen und Last/Sekunde ab.</li>
          <li><strong>Mock-ESPs erstellen</strong> &mdash; ueber das Formular &bdquo;Bulk Create&ldquo; (Anzahl, Sensoren, Aktoren).</li>
          <li><strong>Simulation starten</strong> &mdash; legt Intervall und Dauer fest. Bei High-Risk: getippte Bestaetigung erforderlich.</li>
        </ol>
        <p class="loadtest-intro__hint">
          Hinweis: Lasttests erzeugen echte MQTT-Nachrichten und DB-Schreibvorgaenge.
          Verwende sie nicht waehrend produktiver Beobachtungen.
        </p>
      </div>
    </div>

    <!-- Header Actions -->
    <div class="flex justify-end">
      <button
        class="btn-secondary"
        :disabled="isLoading"
        @click="loadMetrics"
      >
        <RefreshCw :class="['w-4 h-4 mr-2', isLoading && 'animate-spin']" />
        Refresh Metrics
      </button>
    </div>

    <!-- Alerts -->
    <div
      v-if="error"
      class="p-4 rounded-lg bg-red-500/10 border border-red-500/30 flex items-start gap-3"
    >
      <AlertCircle class="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
      <p class="text-sm text-red-400 flex-1">{{ error }}</p>
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

    <!-- Guardrail -->
    <div class="card p-4 space-y-3">
      <div class="flex items-center justify-between gap-3">
        <div>
          <h3 class="text-sm font-semibold text-dark-100">Guardrail (Preflight → Confirm → Tracking)</h3>
          <p class="text-xs text-dark-400">
            High-Risk-Aktionen starten erst nach Preflight und expliziter Bestätigung.
          </p>
        </div>
        <button class="btn-secondary" :disabled="isLoading" @click="runPreflight">
          Preflight prüfen
        </button>
      </div>

      <div v-if="preflight" class="grid grid-cols-1 md:grid-cols-4 gap-3 text-sm">
        <div class="p-2 rounded bg-dark-800/60 border border-dark-700">
          <div class="text-dark-400 text-xs">Impact</div>
          <div class="font-medium capitalize" :class="preflight.impact === 'high' ? 'text-red-400' : preflight.impact === 'medium' ? 'text-yellow-400' : 'text-green-400'">
            {{ preflight.impact }}
          </div>
        </div>
        <div class="p-2 rounded bg-dark-800/60 border border-dark-700">
          <div class="text-dark-400 text-xs">Forecast Geräte</div>
          <div class="font-medium text-dark-100">{{ preflight.forecast.estimated_devices }}</div>
        </div>
        <div class="p-2 rounded bg-dark-800/60 border border-dark-700">
          <div class="text-dark-400 text-xs">Forecast Messages</div>
          <div class="font-medium text-dark-100">{{ preflight.forecast.estimated_messages }}</div>
        </div>
        <div class="p-2 rounded bg-dark-800/60 border border-dark-700">
          <div class="text-dark-400 text-xs">Load/s</div>
          <div class="font-medium text-dark-100">{{ preflight.forecast.expected_load_per_second }}</div>
        </div>
      </div>

      <div v-if="needsTypedConfirm" class="space-y-2">
        <label class="label">Typed Confirm (High-Risk): Tippe <code>START</code></label>
        <input v-model="typedConfirm" type="text" class="input w-full md:w-72" placeholder="START" />
      </div>

      <div v-if="lastSummary" class="p-3 rounded bg-blue-500/10 border border-blue-500/30 text-xs text-blue-300">
        {{ lastSummary }}
      </div>
    </div>

    <!-- Metrics Cards -->
    <div class="grid grid-cols-2 md:grid-cols-5 gap-4">
      <div class="card p-4">
        <div class="flex items-center gap-2 text-dark-400 mb-2">
          <Server class="w-4 h-4" />
          <span class="text-xs uppercase tracking-wider">Mock ESPs</span>
        </div>
        <p class="text-2xl font-bold text-dark-100">
          {{ metrics?.mock_esp_count || 0 }}
        </p>
      </div>
      
      <div class="card p-4">
        <div class="flex items-center gap-2 text-dark-400 mb-2">
          <Thermometer class="w-4 h-4" />
          <span class="text-xs uppercase tracking-wider">Sensors</span>
        </div>
        <p class="text-2xl font-bold text-blue-400">
          {{ metrics?.total_sensors || 0 }}
        </p>
      </div>
      
      <div class="card p-4">
        <div class="flex items-center gap-2 text-dark-400 mb-2">
          <Power class="w-4 h-4" />
          <span class="text-xs uppercase tracking-wider">Actuators</span>
        </div>
        <p class="text-2xl font-bold text-green-400">
          {{ metrics?.total_actuators || 0 }}
        </p>
      </div>
      
      <div class="card p-4">
        <div class="flex items-center gap-2 text-dark-400 mb-2">
          <MessageSquare class="w-4 h-4" />
          <span class="text-xs uppercase tracking-wider">Messages</span>
        </div>
        <p class="text-2xl font-bold text-purple-400">
          {{ (metrics?.messages_published || 0).toLocaleString() }}
        </p>
      </div>
      
      <div class="card p-4">
        <div class="flex items-center gap-2 text-dark-400 mb-2">
          <Clock class="w-4 h-4" />
          <span class="text-xs uppercase tracking-wider">Uptime</span>
        </div>
        <p class="text-2xl font-bold text-yellow-400">
          {{ formatUptime(metrics?.uptime_seconds || 0) }}
        </p>
      </div>
    </div>

    <div class="grid md:grid-cols-2 gap-6">
      <!-- Bulk Create Card -->
      <div class="card">
        <div class="px-4 py-3 border-b border-dark-700">
          <h3 class="font-semibold text-dark-100 flex items-center gap-2">
            <Plus class="w-4 h-4 text-blue-400" />
            Bulk Create Mock ESPs
          </h3>
        </div>
        
        <div class="p-4 space-y-4">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="label">Count</label>
              <input
                v-model.number="bulkCount"
                type="number"
                min="1"
                :max="capabilities?.max_bulk_count ?? 100"
                class="input w-full"
              />
            </div>
            <div>
              <label class="label">Prefix</label>
              <input
                v-model="bulkPrefix"
                type="text"
                class="input w-full"
              />
            </div>
          </div>
          
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="label">Sensors per ESP</label>
              <input
                v-model.number="bulkSensors"
                type="number"
                min="0"
                :max="capabilities?.max_sensors_per_device ?? 10"
                class="input w-full"
              />
            </div>
            <div>
              <label class="label">Actuators per ESP</label>
              <input
                v-model.number="bulkActuators"
                type="number"
                min="0"
                :max="capabilities?.max_actuators_per_device ?? 10"
                class="input w-full"
              />
            </div>
          </div>
          
          <button
            class="btn-primary w-full"
            :disabled="isLoading || !canRunHighRiskAction"
            @click="bulkCreate"
          >
            <Plus class="w-4 h-4 mr-2" />
            Create {{ bulkCount }} Mock ESPs
          </button>
        </div>
      </div>

      <!-- Simulation Control Card -->
      <div class="card">
        <div class="px-4 py-3 border-b border-dark-700">
          <h3 class="font-semibold text-dark-100 flex items-center gap-2">
            <Zap class="w-4 h-4 text-orange-400" />
            Simulation Control
          </h3>
        </div>
        
        <div class="p-4 space-y-4">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="label">Interval (ms)</label>
              <input
                v-model.number="simInterval"
                type="number"
                :min="capabilities?.min_interval_ms ?? 100"
                :max="capabilities?.max_interval_ms ?? 60000"
                step="100"
                class="input w-full"
              />
            </div>
            <div>
              <label class="label">Duration (seconds)</label>
              <input
                v-model.number="simDuration"
                type="number"
                :min="capabilities?.min_duration_seconds ?? 10"
                :max="capabilities?.max_duration_seconds ?? 3600"
                class="input w-full"
              />
            </div>
          </div>
          
          <div class="flex items-center gap-2 p-3 rounded bg-dark-800/50">
            <div
              :class="[
                'w-3 h-3 rounded-full',
                isSimulating ? 'bg-green-500 animate-pulse' : 'bg-dark-500'
              ]"
            />
            <span class="text-sm text-dark-300">
              {{ isSimulating ? 'Simulation running...' : 'Simulation stopped' }}
            </span>
          </div>
          
          <div class="grid grid-cols-2 gap-4">
            <button
              class="btn-primary"
              :disabled="isLoading || isSimulating || !canRunHighRiskAction"
              @click="startSimulation"
            >
              <Play class="w-4 h-4 mr-2" />
              Start
            </button>
            <button
              class="btn-danger"
              :disabled="isLoading || !isSimulating"
              @click="stopSimulation"
            >
              <Square class="w-4 h-4 mr-2" />
              Kill Switch / Stop
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Info Card -->
    <div class="card p-4">
      <h4 class="font-medium text-dark-200 mb-2">About Load Testing</h4>
      <p class="text-sm text-dark-400">
        Use this tool to create multiple mock ESP devices and simulate sensor activity.
        This is useful for stress testing the system, validating MQTT throughput,
        and testing the UI under load. Mock ESPs are identified by
        <code class="text-purple-400">hardware_type = "MOCK_ESP32"</code>.
      </p>
    </div>
  </div>
</template>

<style scoped>
.loadtest-intro {
  display: flex;
  gap: var(--space-4);
  padding: var(--space-5);
  border-radius: var(--radius-lg);
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
}

.loadtest-intro__icon-wrap {
  flex-shrink: 0;
  width: 2.75rem;
  height: 2.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-full);
  background: var(--color-bg-tertiary);
}

.loadtest-intro__icon {
  width: 1.5rem;
  height: 1.5rem;
  color: var(--color-iridescent-1);
}

.loadtest-intro__body {
  flex: 1;
  min-width: 0;
}

.loadtest-intro__title {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: var(--space-2);
}

.loadtest-intro__text {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  line-height: 1.5;
  margin-bottom: var(--space-3);
}

.loadtest-intro__steps {
  list-style: decimal;
  padding-left: var(--space-5);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  line-height: 1.7;
  margin-bottom: var(--space-3);
}

.loadtest-intro__steps strong {
  color: var(--color-text-primary);
  font-weight: 600;
}

.loadtest-intro__hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-style: italic;
  line-height: 1.5;
}
</style>





















