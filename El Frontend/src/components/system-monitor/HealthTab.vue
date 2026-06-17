<script setup lang="ts">
/**
 * HealthTab - Fleet Health Overview
 *
 * Shows aggregated health metrics for all ESP devices:
 * - Summary KPI cards (online count, heap, RSSI, errors)
 * - Per-device health list with sortable columns
 * - Problem-ESP highlighting
 * - Cross-tab navigation to Events tab
 */

import { ref, computed, onMounted } from 'vue'
import { Cpu, Wifi, AlertTriangle, HeartPulse, ArrowUpDown, ExternalLink, RefreshCw, Bell, Server, Radio, BarChart3, GitBranch, Puzzle, Play, WifiOff, Wrench } from 'lucide-vue-next'
import StatCard from '@/components/dashboard/StatCard.vue'
import AccordionSection from '@/shared/design/primitives/AccordionSection.vue'
import BaseSkeleton from '@/shared/design/primitives/BaseSkeleton.vue'
import { getFleetHealth, type FleetHealthResponse } from '@/api/health'
import { debugApi, type MaintenanceStatusResponse, type MaintenanceConfigResponse } from '@/api/debug'
import { useAlertCenterStore } from '@/shared/stores/alert-center.store'
import { useDiagnosticsStore } from '@/shared/stores/diagnostics.store'
import { useToast } from '@/composables/useToast'
import { GRAFANA_BASE_URL } from '@/composables/useGrafana'

// =============================================================================
// Props & Emits
// =============================================================================

interface Props {
  filterEspId?: string
}

const props = withDefaults(defineProps<Props>(), {
  filterEspId: '',
})

const emit = defineEmits<{
  'filter-device': [espId: string]
  'open-alerts': []
}>()

const alertStore = useAlertCenterStore()
const diagStore = useDiagnosticsStore()
const toast = useToast()

// =============================================================================
// State
// =============================================================================

const healthData = ref<FleetHealthResponse | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const sortField = ref<'device_id' | 'status' | 'uptime_seconds' | 'heap_free' | 'wifi_rssi'>('status')
const sortAsc = ref(true)

// Wartung & Cleanup (Phase 4D Konsolidierung)
const maintenanceStatus = ref<MaintenanceStatusResponse | null>(null)
const maintenanceConfig = ref<MaintenanceConfigResponse | null>(null)
const maintenanceLoading = ref(false)
const maintenanceTriggering = ref<string | null>(null)

// =============================================================================
// Computed
// =============================================================================

const filteredDevices = computed(() => {
  if (!healthData.value) return []
  let devices = healthData.value.devices
  if (props.filterEspId) {
    const q = props.filterEspId.toLowerCase()
    devices = devices.filter(
      d => d.device_id.toLowerCase().includes(q) || (d.name && d.name.toLowerCase().includes(q))
    )
  }
  return devices
})

const sortedDevices = computed(() => {
  const list = [...filteredDevices.value]
  const field = sortField.value
  const asc = sortAsc.value
  list.sort((a, b) => {
    const av = a[field]
    const bv = b[field]
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    if (typeof av === 'string' && typeof bv === 'string') {
      return asc ? av.localeCompare(bv) : bv.localeCompare(av)
    }
    return asc ? (av as number) - (bv as number) : (bv as number) - (av as number)
  })
  return list
})

const problemDevices = computed(() =>
  filteredDevices.value.filter(
    d =>
      d.status === 'offline' ||
      d.status === 'error' ||
      (d.heap_free != null && d.heap_free < 20480) ||
      (d.wifi_rssi != null && d.wifi_rssi < -80)
  )
)

const onlinePercent = computed(() => {
  if (!healthData.value || healthData.value.total_devices === 0) return 100
  return Math.round((healthData.value.online_count / healthData.value.total_devices) * 100)
})

// =============================================================================
// Methods
// =============================================================================

async function fetchHealth() {
  loading.value = true
  error.value = null
  try {
    healthData.value = await getFleetHealth()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Fehler beim Laden der Health-Daten'
  } finally {
    loading.value = false
  }
}

function toggleSort(field: typeof sortField.value) {
  if (sortField.value === field) {
    sortAsc.value = !sortAsc.value
  } else {
    sortField.value = field
    sortAsc.value = true
  }
}

function formatUptime(seconds: number | null): string {
  if (seconds == null) return '—'
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

function formatHeap(bytes: number | null): string {
  if (bytes == null) return '—'
  return `${(bytes / 1024).toFixed(1)} KB`
}

function formatRssi(rssi: number | null): string {
  if (rssi == null) return '—'
  return `${rssi} dBm`
}

function formatLastSeen(iso: string | null): string {
  if (!iso) return '—'
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (diff < 60) return `vor ${diff}s`
  if (diff < 3600) return `vor ${Math.floor(diff / 60)}m`
  if (diff < 86400) return `vor ${Math.floor(diff / 3600)}h`
  return `vor ${Math.floor(diff / 86400)}d`
}

function statusClass(status: string): string {
  switch (status) {
    case 'online': return 'status-online'
    case 'offline': return 'status-offline'
    case 'error': return 'status-error'
    default: return 'status-unknown'
  }
}

function heapSeverity(bytes: number | null): string {
  if (bytes == null) return ''
  if (bytes < 20480) return 'heap-critical'
  if (bytes < 40960) return 'heap-warning'
  return ''
}

function rssiSeverity(rssi: number | null): string {
  if (rssi == null) return ''
  if (rssi < -80) return 'rssi-critical'
  if (rssi < -70) return 'rssi-warning'
  return ''
}

function showEventsForEsp(espId: string) {
  emit('filter-device', espId)
}

/** Run full diagnostic from Health tab (1-click access) */
async function runQuickDiagnose(): Promise<void> {
  const report = await diagStore.runDiagnostic()
  if (report) {
    toast.success(`Diagnose: ${report.overall_status}`)
  } else if (diagStore.error) {
    toast.error(diagStore.error)
  }
}

/** Wartung: Lade Status + Config */
async function loadMaintenanceData(): Promise<void> {
  maintenanceLoading.value = true
  try {
    const [statusData, configData] = await Promise.all([
      debugApi.getMaintenanceStatus(),
      debugApi.getMaintenanceConfig(),
    ])
    maintenanceStatus.value = statusData
    maintenanceConfig.value = configData
  } catch (e) {
    toast.error('Wartungsdaten konnten nicht geladen werden')
  } finally {
    maintenanceLoading.value = false
  }
}

/** Wartung: Job manuell ausführen */
async function triggerMaintenanceJob(jobId: string): Promise<void> {
  maintenanceTriggering.value = jobId
  try {
    const result = await debugApi.triggerMaintenanceJob(jobId)
    toast.success(result.message || `Job ${jobId} ausgeführt`)
    await loadMaintenanceData()
  } catch (e) {
    toast.error(`Job ${jobId} fehlgeschlagen`)
  } finally {
    maintenanceTriggering.value = null
  }
}

function formatMaintenanceDate(dateStr: string | null): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleString('de-DE')
}

function formatJobName(jobId: string): string {
  return jobId.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
}

/** Grafana availability check */
const grafanaOffline = ref(false)

async function checkGrafana(): Promise<void> {
  try {
    const grafanaHealthUrl = import.meta.env.DEV
      ? '/grafana/api/health'
      : `${GRAFANA_BASE_URL}/api/health`
    const res = await fetch(grafanaHealthUrl, {
      method: 'GET',
      signal: AbortSignal.timeout(3000),
    })
    grafanaOffline.value = !res.ok
  } catch {
    grafanaOffline.value = true
  }
}

const monitoringUnhealthy = computed(() => {
  const check = diagStore.checksByName.monitoring
  return check && check.status !== 'healthy'
})

// =============================================================================
// Lifecycle
// =============================================================================

onMounted(() => {
  fetchHealth()
  checkGrafana()
  loadMaintenanceData()
})
</script>

<template>
  <div class="health-tab">
    <!-- Error State -->
    <div v-if="error" class="health-error">
      <AlertTriangle class="health-error__icon" />
      <span>{{ error }}</span>
      <button class="health-error__retry" @click="fetchHealth">Erneut versuchen</button>
    </div>

    <!-- Grafana Offline Banner -->
    <div v-if="grafanaOffline || monitoringUnhealthy" class="health-grafana-banner">
      <WifiOff class="health-grafana-banner__icon" />
      <div class="health-grafana-banner__text">
        <span class="health-grafana-banner__title">Monitoring-Stack nicht erreichbar</span>
        <span class="health-grafana-banner__sub">
          Grafana, Prometheus oder Loki sind offline. Starten mit: <code>make monitor-up</code>
        </span>
      </div>
    </div>

    <!-- Summary Cards -->
    <section class="health-summary grid-auto-sm">
      <StatCard
        title="Geräte Online"
        :value="loading ? '...' : `${healthData?.online_count ?? 0}/${healthData?.total_devices ?? 0}`"
        :subtitle="loading ? undefined : `${onlinePercent}% erreichbar`"
        :icon="HeartPulse"
        :icon-color="onlinePercent < 80 ? 'text-error' : 'text-success'"
        :icon-bg-color="onlinePercent < 80 ? 'bg-error/10' : 'bg-success/10'"
        :loading="loading"
      />
      <StatCard
        title="Durchschn. Heap"
        :value="loading ? '...' : formatHeap(healthData?.avg_heap_free ?? null)"
        subtitle="Freier Speicher"
        :icon="Cpu"
        :loading="loading"
      />
      <StatCard
        title="Durchschn. RSSI"
        :value="loading ? '...' : formatRssi(healthData?.avg_wifi_rssi ?? null)"
        subtitle="Signal-Qualität"
        :icon="Wifi"
        :loading="loading"
      />
      <StatCard
        title="Probleme"
        :value="loading ? '...' : problemDevices.length"
        :subtitle="loading ? undefined : problemDevices.length > 0 ? 'Geräte mit Auffälligkeiten' : 'Alles in Ordnung'"
        :icon="AlertTriangle"
        :icon-color="problemDevices.length > 0 ? 'text-warning' : 'text-success'"
        :icon-bg-color="problemDevices.length > 0 ? 'bg-warning/10' : 'bg-success/10'"
        :loading="loading"
      />
      <StatCard
        title="Aktive Alerts"
        :value="alertStore.unresolvedCount"
        :subtitle="alertStore.hasCritical ? `${alertStore.criticalCount} kritisch` : alertStore.unresolvedCount > 0 ? `${alertStore.warningCount} Warnungen` : 'Keine aktiven Alerts'"
        :icon="Bell"
        :icon-color="alertStore.hasCritical ? 'text-error' : alertStore.unresolvedCount > 0 ? 'text-warning' : 'text-success'"
        :icon-bg-color="alertStore.hasCritical ? 'bg-error/10' : alertStore.unresolvedCount > 0 ? 'bg-warning/10' : 'bg-success/10'"
        class="stat-card--clickable"
        @click="emit('open-alerts')"
      />
    </section>

    <!-- Diagnostics KPI Cards (from last diagnostic run) -->
    <section v-if="diagStore.currentReport" class="health-summary health-summary--diagnostics grid-auto-sm">
      <StatCard
        title="Server"
        :value="diagStore.checksByName.server?.metrics?.cpu_percent != null ? `${diagStore.checksByName.server.metrics.cpu_percent}%` : '—'"
        :subtitle="diagStore.checksByName.server?.metrics?.memory_percent != null ? `RAM: ${diagStore.checksByName.server.metrics.memory_percent}%` : undefined"
        :icon="Server"
        :icon-color="diagStore.checksByName.server?.status === 'healthy' ? 'text-success' : 'text-warning'"
        :icon-bg-color="diagStore.checksByName.server?.status === 'healthy' ? 'bg-success/10' : 'bg-warning/10'"
      />
      <StatCard
        title="MQTT"
        :value="diagStore.checksByName.mqtt?.status === 'healthy' ? 'Verbunden' : diagStore.checksByName.mqtt?.status === 'warning' ? 'Warnung' : 'Offline'"
        :subtitle="diagStore.checksByName.mqtt?.metrics?.stale_devices != null ? `${diagStore.checksByName.mqtt.metrics.stale_devices} stale` : undefined"
        :icon="Radio"
        :icon-color="diagStore.checksByName.mqtt?.status === 'healthy' ? 'text-success' : 'text-warning'"
        :icon-bg-color="diagStore.checksByName.mqtt?.status === 'healthy' ? 'bg-success/10' : 'bg-warning/10'"
      />
      <StatCard
        title="Monitoring"
        :value="diagStore.checksByName.monitoring?.status === 'healthy' ? 'Aktiv' : diagStore.checksByName.monitoring?.status ?? '—'"
        subtitle="Grafana / Prometheus / Loki"
        :icon="BarChart3"
        :icon-color="diagStore.checksByName.monitoring?.status === 'healthy' ? 'text-success' : 'text-warning'"
        :icon-bg-color="diagStore.checksByName.monitoring?.status === 'healthy' ? 'bg-success/10' : 'bg-warning/10'"
      />
      <StatCard
        title="Logic Engine"
        :value="diagStore.checksByName.logic_engine?.metrics?.active_rules != null ? String(diagStore.checksByName.logic_engine.metrics.active_rules) : '—'"
        :subtitle="diagStore.checksByName.logic_engine?.metrics?.executions_24h != null ? `${diagStore.checksByName.logic_engine.metrics.executions_24h} Ausfuehrungen/24h` : 'Regeln'"
        :icon="GitBranch"
        :icon-color="diagStore.checksByName.logic_engine?.status === 'healthy' ? 'text-success' : 'text-warning'"
        :icon-bg-color="diagStore.checksByName.logic_engine?.status === 'healthy' ? 'bg-success/10' : 'bg-warning/10'"
      />
      <StatCard
        title="Plugins"
        :value="diagStore.checksByName.plugins?.metrics?.total != null ? String(diagStore.checksByName.plugins.metrics.total) : '—'"
        :subtitle="diagStore.checksByName.plugins?.metrics?.enabled != null ? `${diagStore.checksByName.plugins.metrics.enabled} aktiv` : 'Registriert'"
        :icon="Puzzle"
        :icon-color="diagStore.checksByName.plugins?.status === 'healthy' ? 'text-success' : 'text-iridescent-2'"
        :icon-bg-color="diagStore.checksByName.plugins?.status === 'healthy' ? 'bg-success/10' : 'bg-iridescent-2/10'"
      />
    </section>

    <!-- Wartung & Cleanup (Phase 4D) -->
    <AccordionSection
      title="Wartung & Cleanup"
      storage-key="health-tab-maintenance"
      :default-open="false"
      :icon="Wrench"
    >
      <div v-if="maintenanceLoading && !maintenanceStatus" class="maintenance-loading">
        <BaseSkeleton text="Lade Wartungsstatus..." />
      </div>
      <template v-else-if="maintenanceStatus && maintenanceConfig">
        <!-- Cleanup Config (kompakt) -->
        <div class="maintenance-config">
          <div class="maintenance-config__item">
            <span class="maintenance-config__label">Sensor-Daten:</span>
            <span :class="['maintenance-config__value', maintenanceConfig.sensor_data_retention_enabled ? 'enabled' : 'disabled']">
              {{ maintenanceConfig.sensor_data_retention_enabled ? `${maintenanceConfig.sensor_data_retention_days}d` : 'Aus' }}
            </span>
          </div>
          <div class="maintenance-config__item">
            <span class="maintenance-config__label">Befehlsverlauf:</span>
            <span :class="['maintenance-config__value', maintenanceConfig.command_history_retention_enabled ? 'enabled' : 'disabled']">
              {{ maintenanceConfig.command_history_retention_enabled ? `${maintenanceConfig.command_history_retention_days}d` : 'Aus' }}
            </span>
          </div>
          <div class="maintenance-config__item">
            <span class="maintenance-config__label">Orphan Mocks:</span>
            <span :class="['maintenance-config__value', maintenanceConfig.orphaned_mock_cleanup_enabled ? 'enabled' : 'disabled']">
              {{ maintenanceConfig.orphaned_mock_cleanup_enabled ? 'Aktiv' : 'Aus' }}
            </span>
          </div>
        </div>
        <!-- Jobs mit Run-Button -->
        <div class="maintenance-jobs">
          <div
            v-for="job in maintenanceStatus.jobs"
            :key="job.job_id"
            class="maintenance-job"
          >
            <div class="maintenance-job__info">
              <span class="maintenance-job__name">{{ formatJobName(job.job_id) }}</span>
              <span class="maintenance-job__meta">
                Letzte: {{ formatMaintenanceDate(job.last_run) }}
              </span>
            </div>
            <button
              class="maintenance-job__run"
              :disabled="maintenanceTriggering !== null"
              @click="triggerMaintenanceJob(job.job_id)"
            >
              <RefreshCw v-if="maintenanceTriggering === job.job_id" class="w-4 h-4 animate-spin" />
              <Play v-else class="w-4 h-4" />
              {{ maintenanceTriggering === job.job_id ? 'Läuft...' : 'Ausführen' }}
            </button>
          </div>
        </div>
      </template>
    </AccordionSection>

    <!-- Actions -->
    <div class="health-actions">
      <button
        class="diagnose-btn"
        :disabled="diagStore.isRunning"
        @click="runQuickDiagnose"
      >
        <Play v-if="!diagStore.isRunning" class="diagnose-btn__icon" />
        <RefreshCw v-else class="diagnose-btn__icon refresh-icon--spinning" />
        System-Check starten
      </button>
      <span v-if="diagStore.lastRunAge" class="health-actions__last-run">
        Letzter Check: {{ diagStore.lastRunAge }}
      </span>
      <button class="refresh-btn" :disabled="loading" @click="fetchHealth">
        <RefreshCw class="refresh-icon" :class="{ 'refresh-icon--spinning': loading }" />
        Aktualisieren
      </button>
    </div>

    <!-- Problem Devices -->
    <section v-if="!loading && problemDevices.length > 0" class="health-problems">
      <h3 class="section-title section-title--warning">
        <AlertTriangle class="section-icon" />
        Problem-Geräte ({{ problemDevices.length }})
      </h3>
      <div class="problem-list">
        <div
          v-for="device in problemDevices"
          :key="device.device_id"
          class="problem-item"
          @click="showEventsForEsp(device.device_id)"
        >
          <span class="problem-item__id">{{ device.name || device.device_id }}</span>
          <span :class="['status-badge', statusClass(device.status)]">{{ device.status }}</span>
          <span v-if="device.heap_free != null && device.heap_free < 20480" class="problem-tag problem-tag--error">
            Heap {{ formatHeap(device.heap_free) }}
          </span>
          <span v-if="device.wifi_rssi != null && device.wifi_rssi < -80" class="problem-tag problem-tag--warning">
            RSSI {{ device.wifi_rssi }} dBm
          </span>
          <ExternalLink class="problem-item__link" />
        </div>
      </div>
    </section>

    <!-- Device Health List -->
    <section v-if="!loading" class="health-list-section">
      <h3 class="section-title">
        Alle Geräte ({{ filteredDevices.length }})
      </h3>

      <div class="health-table-wrap">
        <table class="health-table">
          <thead>
            <tr>
              <th class="col-sortable" @click="toggleSort('device_id')">
                ESP-ID
                <ArrowUpDown v-if="sortField === 'device_id'" class="sort-icon" />
              </th>
              <th class="col-sortable" @click="toggleSort('status')">
                Status
                <ArrowUpDown v-if="sortField === 'status'" class="sort-icon" />
              </th>
              <th class="col-sortable" @click="toggleSort('uptime_seconds')">
                Uptime
                <ArrowUpDown v-if="sortField === 'uptime_seconds'" class="sort-icon" />
              </th>
              <th class="col-sortable" @click="toggleSort('heap_free')">
                Heap
                <ArrowUpDown v-if="sortField === 'heap_free'" class="sort-icon" />
              </th>
              <th class="col-sortable" @click="toggleSort('wifi_rssi')">
                RSSI
                <ArrowUpDown v-if="sortField === 'wifi_rssi'" class="sort-icon" />
              </th>
              <th>Sensoren</th>
              <th>Zuletzt gesehen</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="device in sortedDevices"
              :key="device.device_id"
              class="health-row"
              :class="{ 'health-row--problem': device.status === 'offline' || device.status === 'error' }"
            >
              <td class="col-id">
                <div class="device-id-cell">
                  <span class="device-name">{{ device.name || device.device_id }}</span>
                  <span v-if="device.name" class="device-id-sub">{{ device.device_id }}</span>
                </div>
              </td>
              <td>
                <span :class="['status-badge', statusClass(device.status)]">{{ device.status }}</span>
              </td>
              <td>{{ formatUptime(device.uptime_seconds) }}</td>
              <td :class="heapSeverity(device.heap_free)">{{ formatHeap(device.heap_free) }}</td>
              <td :class="rssiSeverity(device.wifi_rssi)">{{ formatRssi(device.wifi_rssi) }}</td>
              <td>{{ device.sensor_count }} / {{ device.actuator_count }}</td>
              <td>{{ formatLastSeen(device.last_seen) }}</td>
              <td>
                <button class="events-link" @click="showEventsForEsp(device.device_id)" title="Events anzeigen">
                  <ExternalLink class="events-link__icon" />
                </button>
              </td>
            </tr>
            <tr v-if="sortedDevices.length === 0">
              <td colspan="8" class="empty-state">
                {{ props.filterEspId ? 'Kein Gerät entspricht dem Filter' : 'Keine Geräte registriert' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Loading skeleton for table -->
    <section v-if="loading" class="health-list-section">
      <div v-for="i in 5" :key="i" class="skeleton-row">
        <div class="skeleton skeleton--sm" />
        <div class="skeleton skeleton--xs" />
        <div class="skeleton skeleton--xs" />
        <div class="skeleton skeleton--xs" />
      </div>
    </section>
  </div>
</template>

<style scoped>
/* =============================================================================
   Layout
   ============================================================================= */
.health-tab {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  padding: 1.5rem;
}

/* =============================================================================
   Summary Cards
   ============================================================================= */
.health-summary {
  gap: 1rem;
}

.health-summary--diagnostics {
  padding-top: 0.75rem;
  border-top: 1px solid var(--glass-border);
}

/* =============================================================================
   Grafana Offline Banner
   ============================================================================= */
.health-grafana-banner {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.875rem 1.25rem;
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.2);
  border-radius: var(--radius-lg);
}

.health-grafana-banner__icon {
  width: 1.25rem;
  height: 1.25rem;
  color: var(--color-warning);
  flex-shrink: 0;
  margin-top: 1px;
}

.health-grafana-banner__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.health-grafana-banner__title {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-warning);
}

.health-grafana-banner__sub {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.health-grafana-banner__sub code {
  font-family: var(--font-mono);
  background: rgba(255, 255, 255, 0.06);
  padding: 1px 4px;
  border-radius: var(--radius-xs);
  font-size: 0.6875rem;
}

/* =============================================================================
   Wartung & Cleanup
   ============================================================================= */
.maintenance-loading {
  padding: var(--space-4) 0;
}

.maintenance-config {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
  padding: var(--space-2) 0;
}

.maintenance-config__item {
  display: flex;
  gap: var(--space-2);
  font-size: var(--text-sm);
}

.maintenance-config__label {
  color: var(--color-text-muted);
}

.maintenance-config__value.enabled {
  color: var(--color-success);
}

.maintenance-config__value.disabled {
  color: var(--color-text-muted);
}

.maintenance-jobs {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.maintenance-job {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
}

.maintenance-job__info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.maintenance-job__name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-primary);
}

.maintenance-job__meta {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.maintenance-job__run {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-sm);
  background: var(--color-iridescent-1);
  color: white;
  border: none;
  font-size: var(--text-xs);
  font-weight: 500;
  cursor: pointer;
  transition: opacity var(--transition-fast);
}

.maintenance-job__run:hover:not(:disabled) {
  opacity: 0.9;
}

.maintenance-job__run:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* =============================================================================
   Actions
   ============================================================================= */
.health-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  justify-content: flex-end;
}

.diagnose-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-radius: var(--radius-lg);
  background: linear-gradient(135deg, var(--color-iridescent-1), var(--color-iridescent-3));
  border: none;
  color: white;
  font-size: 0.8125rem;
  font-weight: 500;
  cursor: pointer;
  transition: opacity var(--transition-fast);
  margin-right: auto;
}

.diagnose-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.diagnose-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.diagnose-btn__icon {
  width: 0.875rem;
  height: 0.875rem;
}

.health-actions__last-run {
  font-size: 0.6875rem;
  color: var(--color-text-muted);
  white-space: nowrap;
}

.refresh-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-radius: var(--radius-lg);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  color: var(--color-text-secondary);
  font-size: 0.8125rem;
  cursor: pointer;
  transition: all var(--transition-base);
}

.refresh-btn:hover:not(:disabled) {
  background: var(--glass-bg-light);
  color: var(--color-text-primary);
  border-color: var(--glass-border-hover);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.refresh-icon {
  width: 0.875rem;
  height: 0.875rem;
}

.refresh-icon--spinning {
  animation: spin 1s linear infinite;
}

/* =============================================================================
   Error State
   ============================================================================= */
.health-error {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem 1.25rem;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.25);
  border-radius: var(--radius-lg);
  color: var(--color-error);
  font-size: 0.875rem;
}

.health-error__icon {
  width: 1.25rem;
  height: 1.25rem;
  flex-shrink: 0;
}

.health-error__retry {
  margin-left: auto;
  padding: 0.375rem 0.75rem;
  background: rgba(239, 68, 68, 0.15);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: var(--radius-md);
  color: var(--color-error);
  font-size: 0.75rem;
  cursor: pointer;
  transition: background var(--transition-base);
}

.health-error__retry:hover {
  background: rgba(239, 68, 68, 0.25);
}

/* =============================================================================
   Section Titles
   ============================================================================= */
.section-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 0.75rem;
}

.section-title--warning {
  color: var(--color-warning);
}

.section-icon {
  width: 1rem;
  height: 1rem;
}

/* =============================================================================
   Problem Devices
   ============================================================================= */
.health-problems {
  padding: 1rem 1.25rem;
  background: rgba(245, 158, 11, 0.05);
  border: 1px solid rgba(245, 158, 11, 0.15);
  border-radius: var(--radius-lg);
}

.problem-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.problem-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.625rem 0.875rem;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-base);
}

.problem-item:hover {
  background: var(--glass-bg-light);
  border-color: var(--glass-border-hover);
}

.problem-item__id {
  font-weight: 500;
  color: var(--color-text-primary);
  font-size: 0.8125rem;
}

.problem-item__link {
  width: 0.875rem;
  height: 0.875rem;
  color: var(--color-text-muted);
  margin-left: auto;
  flex-shrink: 0;
}

.problem-tag {
  font-size: 0.6875rem;
  padding: 0.125rem 0.5rem;
  border-radius: var(--radius-full);
  font-weight: 500;
}

.problem-tag--error {
  background: rgba(239, 68, 68, 0.15);
  color: var(--color-error);
}

.problem-tag--warning {
  background: rgba(245, 158, 11, 0.15);
  color: var(--color-warning);
}

/* =============================================================================
   Status Badge
   ============================================================================= */
.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 0.125rem 0.625rem;
  border-radius: var(--radius-full);
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.status-online {
  background: rgba(34, 197, 94, 0.15);
  color: var(--color-success);
}

.status-offline {
  background: rgba(239, 68, 68, 0.15);
  color: var(--color-error);
}

.status-error {
  background: rgba(220, 38, 38, 0.15);
  color: var(--color-error);
}

.status-unknown {
  background: rgba(112, 112, 128, 0.15);
  color: var(--color-text-muted);
}

/* =============================================================================
   Health Table
   ============================================================================= */
.health-table-wrap {
  overflow-x: auto;
  border-radius: var(--radius-lg);
  border: 1px solid var(--glass-border);
}

.health-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8125rem;
}

.health-table thead {
  background: var(--glass-bg);
  position: sticky;
  top: 0;
  z-index: var(--z-dropdown);
}

.health-table th {
  text-align: left;
  padding: 0.75rem 1rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--glass-border);
  white-space: nowrap;
}

.col-sortable {
  cursor: pointer;
  user-select: none;
  transition: color var(--transition-base);
}

.col-sortable:hover {
  color: var(--color-text-primary);
}

.sort-icon {
  width: 0.75rem;
  height: 0.75rem;
  display: inline-block;
  vertical-align: middle;
  margin-left: 0.25rem;
  color: var(--color-iridescent-1);
}

.health-table td {
  padding: 0.625rem 1rem;
  color: var(--color-text-primary);
  border-bottom: 1px solid var(--glass-border);
  white-space: nowrap;
}

.health-row {
  transition: background var(--transition-base);
}

.health-row:hover {
  background: var(--glass-bg-light);
}

.health-row--problem {
  background: rgba(239, 68, 68, 0.04);
}

.health-row--problem:hover {
  background: rgba(239, 68, 68, 0.08);
}

/* Device ID cell */
.device-id-cell {
  display: flex;
  flex-direction: column;
}

.device-name {
  font-weight: 500;
}

.device-id-sub {
  font-size: 0.6875rem;
  color: var(--color-text-muted);
}

/* Heap severity */
.heap-critical {
  color: var(--color-error);
  font-weight: 600;
}

.heap-warning {
  color: var(--color-warning);
}

/* RSSI severity */
.rssi-critical {
  color: var(--color-error);
  font-weight: 600;
}

.rssi-warning {
  color: var(--color-warning);
}

/* Events link button */
.events-link {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.75rem;
  height: 1.75rem;
  border-radius: var(--radius-md);
  background: transparent;
  border: 1px solid transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all var(--transition-base);
}

.events-link:hover {
  background: var(--glass-bg);
  border-color: var(--glass-border);
  color: var(--color-iridescent-1);
}

.events-link__icon {
  width: 0.875rem;
  height: 0.875rem;
}

/* Empty state */
.empty-state {
  text-align: center;
  color: var(--color-text-muted);
  padding: 2rem 1rem !important;
}

/* =============================================================================
   Skeleton Loading
   ============================================================================= */
.skeleton-row {
  display: flex;
  gap: 1rem;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--glass-border);
}

.skeleton {
  background: linear-gradient(90deg, var(--glass-bg) 25%, var(--glass-bg-light) 50%, var(--glass-bg) 75%);
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.5s infinite;
  border-radius: var(--radius-sm);
}

.skeleton--sm {
  width: 120px;
  height: 1rem;
}

.skeleton--xs {
  width: 60px;
  height: 1rem;
}

@keyframes skeleton-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* =============================================================================
   Responsive
   ============================================================================= */
@media (max-width: 768px) {
  .health-tab {
    padding: 1rem;
    gap: 1rem;
  }

  .health-summary {
    grid-template-columns: repeat(2, 1fr);
  }

  .health-table th:nth-child(n+6),
  .health-table td:nth-child(n+6) {
    display: none;
  }
}

@media (max-width: 480px) {
  .health-summary {
    grid-template-columns: 1fr;
  }

  .health-table th:nth-child(n+4),
  .health-table td:nth-child(n+4) {
    display: none;
  }
}

/* Utility classes for StatCard icon colors */
:deep(.text-success) { color: var(--color-success); }
:deep(.text-error) { color: var(--color-error); }
:deep(.text-warning) { color: var(--color-warning); }
:deep(.bg-success\/10) { background: rgba(34, 197, 94, 0.1); }
:deep(.bg-error\/10) { background: rgba(239, 68, 68, 0.1); }
:deep(.bg-warning\/10) { background: rgba(245, 158, 11, 0.1); }
</style>
