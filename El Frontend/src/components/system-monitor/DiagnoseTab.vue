<script setup lang="ts">
/**
 * DiagnoseTab - 10 Diagnostic Check Cards
 *
 * Phase 4D.2.3: Shows all available diagnostic checks as cards.
 * Each card displays status, can be run individually, and expands
 * to show metrics + recommendations.
 */

import { ref, onMounted } from 'vue'
import {
  Server, Database, Radio, Cpu, Thermometer, Zap,
  BarChart3, GitBranch, Bell, Puzzle,
  Play, RefreshCw, ChevronDown, ChevronUp,
} from 'lucide-vue-next'
import BaseSpinner from '@/shared/design/primitives/BaseSpinner.vue'
import { useDiagnosticsStore } from '@/shared/stores/diagnostics.store'
import { useToast } from '@/composables/useToast'
import type { CheckStatusValue } from '@/api/diagnostics'

const store = useDiagnosticsStore()
const { success: showSuccess, error: showError } = useToast()

// Use a plain object as map for Vue reactivity (Set mutations are not tracked by Vue 3)
const expandedChecks = ref<Record<string, boolean>>({})

// Map check names to icons
const CHECK_ICONS: Record<string, typeof Server> = {
  server: Server,
  database: Database,
  mqtt: Radio,
  esp_devices: Cpu,
  sensors: Thermometer,
  actuators: Zap,
  monitoring: BarChart3,
  logic_engine: GitBranch,
  alerts: Bell,
  plugins: Puzzle,
}

// Status colors
function statusDotClass(status: CheckStatusValue): string {
  switch (status) {
    case 'healthy': return 'check-card__dot--healthy'
    case 'warning': return 'check-card__dot--warning'
    case 'critical': return 'check-card__dot--critical'
    case 'error': return 'check-card__dot--error'
    default: return ''
  }
}

function statusLabel(status: CheckStatusValue): string {
  switch (status) {
    case 'healthy': return 'Gesund'
    case 'warning': return 'Warnung'
    case 'critical': return 'Kritisch'
    case 'error': return 'Fehler'
    default: return 'Unbekannt'
  }
}

function toggleExpand(name: string) {
  if (expandedChecks.value[name]) {
    expandedChecks.value = { ...expandedChecks.value, [name]: false }
  } else {
    expandedChecks.value = { ...expandedChecks.value, [name]: true }
  }
}

async function runFullDiagnostic() {
  const report = await store.runDiagnostic()
  if (report) {
    showSuccess(`Diagnose abgeschlossen: ${statusLabel(report.overall_status)}`)
  } else if (store.error) {
    showError(store.error)
  }
}

async function runSingleCheck(checkName: string) {
  const result = await store.runCheck(checkName)
  if (result) {
    showSuccess(`${checkName}: ${statusLabel(result.status)}`)
    expandedChecks.value = { ...expandedChecks.value, [checkName]: true }
  } else if (store.error) {
    showError(store.error)
  }
}

function formatMetricLabel(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function formatMetricValue(value: unknown): string {
  if (typeof value === 'number') {
    return value >= 1000 ? value.toLocaleString('de-DE') : value.toLocaleString('de-DE', { maximumFractionDigits: 2 })
  }
  if (typeof value === 'boolean') return value ? 'Ja' : 'Nein'
  return String(value)
}

onMounted(() => {
  store.loadAvailableChecks()
  if (store.history.length === 0) store.loadHistory()
})
</script>

<template>
  <div class="diagnose-tab">
    <!-- Header -->
    <div class="diagnose-tab__header">
      <div class="diagnose-tab__title-row">
        <h3 class="diagnose-tab__title">System-Diagnose</h3>
        <span v-if="store.lastRunAge" class="diagnose-tab__last-run">
          Letzte Diagnose: {{ store.lastRunAge }}
        </span>
      </div>
      <button
        class="diagnose-tab__run-all"
        :disabled="store.isRunning"
        @click="runFullDiagnostic"
      >
        <BaseSpinner v-if="store.isRunning && !store.runningCheck" size="sm" />
        <Play v-else class="w-4 h-4" />
        <span>Volle Diagnose starten</span>
      </button>
    </div>

    <!-- Overall status banner -->
    <div
      v-if="store.currentReport"
      :class="['diagnose-tab__status-banner', `diagnose-tab__status-banner--${store.overallStatus}`]"
    >
      <div class="diagnose-tab__status-counts">
        <span v-if="store.statusCounts.healthy" class="diagnose-tab__count diagnose-tab__count--healthy">
          {{ store.statusCounts.healthy }} Gesund
        </span>
        <span v-if="store.statusCounts.warning" class="diagnose-tab__count diagnose-tab__count--warning">
          {{ store.statusCounts.warning }} Warnung
        </span>
        <span v-if="store.statusCounts.critical" class="diagnose-tab__count diagnose-tab__count--critical">
          {{ store.statusCounts.critical }} Kritisch
        </span>
        <span v-if="store.statusCounts.error" class="diagnose-tab__count diagnose-tab__count--error">
          {{ store.statusCounts.error }} Fehler
        </span>
      </div>
      <span class="diagnose-tab__duration">
        {{ store.currentReport.duration_seconds.toFixed(1) }}s
      </span>
    </div>

    <!-- Check Cards Grid -->
    <div class="diagnose-tab__grid grid-auto-lg">
      <div
        v-for="check in store.availableChecks"
        :key="check.name"
        class="check-card"
      >
        <!-- Card Header -->
        <div class="check-card__header">
          <div class="check-card__icon">
            <component :is="CHECK_ICONS[check.name] || Server" class="w-5 h-5" />
          </div>
          <div class="check-card__info">
            <span class="check-card__name">{{ check.display_name }}</span>
            <div v-if="store.checksByName[check.name]" class="check-card__status">
              <span
                :class="['check-card__dot', statusDotClass(store.checksByName[check.name].status)]"
              />
              <span class="check-card__status-label">
                {{ statusLabel(store.checksByName[check.name].status) }}
              </span>
            </div>
            <span v-else class="check-card__no-data">Nicht geprueft</span>
          </div>
          <div class="check-card__actions">
            <button
              class="check-card__btn"
              :disabled="store.isRunning"
              :title="`${check.display_name} pruefen`"
              @click.stop="runSingleCheck(check.name)"
            >
              <BaseSpinner v-if="store.runningCheck === check.name" size="sm" />
              <RefreshCw v-else class="w-4 h-4" />
            </button>
            <button
              v-if="store.checksByName[check.name]"
              class="check-card__btn"
              :title="expandedChecks[check.name] ? 'Zuklappen' : 'Details'"
              @click.stop="toggleExpand(check.name)"
            >
              <ChevronUp v-if="expandedChecks[check.name]" class="w-4 h-4" />
              <ChevronDown v-else class="w-4 h-4" />
            </button>
          </div>
        </div>

        <!-- Message -->
        <div v-if="store.checksByName[check.name]" class="check-card__message">
          {{ store.checksByName[check.name].message }}
        </div>

        <!-- Expanded Detail -->
        <div
          v-if="expandedChecks[check.name] && store.checksByName[check.name]"
          class="check-card__detail"
        >
          <!-- Metrics -->
          <div
            v-if="Object.keys(store.checksByName[check.name].metrics).length > 0"
            class="check-card__metrics"
          >
            <div
              v-for="(value, key) in store.checksByName[check.name].metrics"
              :key="key"
              class="check-card__metric"
            >
              <span class="check-card__metric-label">{{ formatMetricLabel(String(key)) }}</span>
              <span class="check-card__metric-value">{{ formatMetricValue(value) }}</span>
            </div>
          </div>

          <!-- Recommendations -->
          <div
            v-if="store.checksByName[check.name].recommendations.length > 0"
            class="check-card__recommendations"
          >
            <span class="check-card__rec-title">Empfehlungen:</span>
            <ul class="check-card__rec-list">
              <li
                v-for="(rec, idx) in store.checksByName[check.name].recommendations"
                :key="idx"
              >
                {{ rec }}
              </li>
            </ul>
          </div>

          <!-- Duration -->
          <span class="check-card__timing">
            {{ store.checksByName[check.name].duration_ms.toFixed(0) }}ms
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.diagnose-tab {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.diagnose-tab__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
}

.diagnose-tab__title-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
}

.diagnose-tab__title {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}

.diagnose-tab__last-run {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.diagnose-tab__run-all {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  background: linear-gradient(135deg, var(--color-iridescent-1), var(--color-iridescent-3));
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: opacity var(--transition-fast);
}

.diagnose-tab__run-all:hover:not(:disabled) {
  opacity: 0.9;
}

.diagnose-tab__run-all:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Status Banner */
.diagnose-tab__status-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: var(--color-bg-tertiary);
}

.diagnose-tab__status-banner--healthy {
  border-color: rgba(52, 211, 153, 0.3);
}

.diagnose-tab__status-banner--warning {
  border-color: rgba(251, 191, 36, 0.3);
}

.diagnose-tab__status-banner--critical,
.diagnose-tab__status-banner--error {
  border-color: rgba(248, 113, 113, 0.3);
}

.diagnose-tab__status-counts {
  display: flex;
  gap: var(--space-3);
}

.diagnose-tab__count {
  font-size: var(--text-sm);
  font-weight: 500;
}

.diagnose-tab__count--healthy { color: var(--color-success); }
.diagnose-tab__count--warning { color: var(--color-warning); }
.diagnose-tab__count--critical { color: var(--color-error); }
.diagnose-tab__count--error { color: var(--color-error); }

.diagnose-tab__duration {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

/* Grid */
.diagnose-tab__grid {
  gap: var(--space-3);
}

/* Check Card */
.check-card {
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  transition: border-color var(--transition-fast);
}

.check-card:hover {
  border-color: rgba(96, 165, 250, 0.2);
}

.check-card__header {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
}

.check-card__icon {
  padding: var(--space-2);
  border-radius: var(--radius-sm);
  background: rgba(96, 165, 250, 0.1);
  color: var(--color-iridescent-1);
  flex-shrink: 0;
}

.check-card__info {
  flex: 1;
  min-width: 0;
}

.check-card__name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-primary);
}

.check-card__status {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  margin-top: 2px;
}

.check-card__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.check-card__dot--healthy { background: var(--color-success); }
.check-card__dot--warning { background: var(--color-warning); }
.check-card__dot--critical { background: var(--color-error); }
.check-card__dot--error { background: var(--color-error); }

.check-card__status-label {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.check-card__no-data {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-style: italic;
}

.check-card__actions {
  display: flex;
  gap: var(--space-1);
  flex-shrink: 0;
}

.check-card__btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.check-card__btn:hover:not(:disabled) {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.check-card__btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.check-card__message {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  margin-top: var(--space-2);
  padding-left: calc(var(--space-2) + 20px + var(--space-3));
}

/* Detail Section */
.check-card__detail {
  margin-top: var(--space-3);
  padding-top: var(--space-3);
  border-top: 1px solid var(--glass-border);
}

.check-card__metrics {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}

.check-card__metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.check-card__metric-label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.check-card__metric-value {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-primary);
}

.check-card__recommendations {
  margin-top: var(--space-2);
}

.check-card__rec-title {
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-warning);
}

.check-card__rec-list {
  list-style: none;
  padding: 0;
  margin: var(--space-1) 0 0;
}

.check-card__rec-list li {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  padding: 2px 0;
  padding-left: var(--space-3);
  position: relative;
}

.check-card__rec-list li::before {
  content: '\2022';
  position: absolute;
  left: var(--space-1);
  color: var(--color-warning);
}

.check-card__timing {
  display: block;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  text-align: right;
  margin-top: var(--space-2);
}
</style>
