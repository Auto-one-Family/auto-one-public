<script setup lang="ts">
/**
 * ReportsTab - Diagnostic Report History
 *
 * Phase 4D.2.4: Shows past diagnostic reports in a table.
 * Allows viewing report details and downloading as Markdown.
 */

import { ref, onMounted } from 'vue'
import {
  ClipboardList, RefreshCw, Download, Eye, ChevronDown, ChevronUp,
} from 'lucide-vue-next'
import BaseSpinner from '@/shared/design/primitives/BaseSpinner.vue'
import { useDiagnosticsStore } from '@/shared/stores/diagnostics.store'
import { useToast } from '@/composables/useToast'
import { formatRelativeTime } from '@/utils/formatters'
import type { DiagnosticReport } from '@/api/diagnostics'

const store = useDiagnosticsStore()
const { error: showError } = useToast()

const expandedReportId = ref<string | null>(null)
const expandedReportData = ref<DiagnosticReport | null>(null)
const isLoadingDetail = ref(false)

function statusLabel(status: string): string {
  switch (status) {
    case 'healthy': return 'Gesund'
    case 'warning': return 'Warnung'
    case 'critical': return 'Kritisch'
    case 'error': return 'Fehler'
    default: return status
  }
}

function triggerLabel(trigger: string): string {
  switch (trigger) {
    case 'manual': return 'Manuell'
    case 'logic_rule': return 'Regel'
    case 'schedule': return 'Zeitplan'
    default: return trigger
  }
}

function statusClass(status: string): string {
  switch (status) {
    case 'healthy': return 'reports-tab__status--healthy'
    case 'warning': return 'reports-tab__status--warning'
    case 'critical': return 'reports-tab__status--critical'
    case 'error': return 'reports-tab__status--error'
    default: return ''
  }
}

function formatDuration(seconds: number): string {
  if (seconds < 1) return `${(seconds * 1000).toFixed(0)}ms`
  return `${seconds.toFixed(1)}s`
}

function formatTimestamp(iso: string): string {
  if (!iso) return '\u2014'
  const d = new Date(iso)
  return d.toLocaleString('de-DE', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

async function toggleReport(reportId: string) {
  if (expandedReportId.value === reportId) {
    expandedReportId.value = null
    expandedReportData.value = null
    return
  }

  expandedReportId.value = reportId
  isLoadingDetail.value = true
  expandedReportData.value = null

  try {
    const report = await store.loadReport(reportId)
    if (report) {
      expandedReportData.value = report
    }
  } catch (e) {
    showError('Report konnte nicht geladen werden')
  } finally {
    isLoadingDetail.value = false
  }
}

async function downloadReport(reportId: string) {
  const markdown = await store.exportReport(reportId)
  if (!markdown) {
    showError('Export fehlgeschlagen')
    return
  }

  // Download as .md file
  const blob = new Blob(['\uFEFF' + markdown], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `diagnostic-report-${reportId.slice(0, 8)}.md`
  document.body.appendChild(a)
  a.click()
  setTimeout(() => {
    URL.revokeObjectURL(url)
    document.body.removeChild(a)
  }, 1000)
}

onMounted(() => {
  store.loadHistory()
})
</script>

<template>
  <div class="reports-tab">
    <!-- Header -->
    <div class="reports-tab__header">
      <div class="reports-tab__title-row">
        <ClipboardList class="w-5 h-5 text-iridescent-2" />
        <h3 class="reports-tab__title">Diagnose-Reports</h3>
        <span class="reports-tab__count">{{ store.history.length }} Reports</span>
      </div>
      <button
        class="reports-tab__refresh"
        :disabled="store.isLoadingHistory"
        @click="store.loadHistory()"
      >
        <RefreshCw :class="['w-4 h-4', { 'animate-spin': store.isLoadingHistory }]" />
      </button>
    </div>

    <!-- Loading -->
    <div v-if="store.isLoadingHistory && store.history.length === 0" class="reports-tab__loading">
      <BaseSpinner size="md" />
      <span>Lade Report-Verlauf...</span>
    </div>

    <!-- Empty State -->
    <div v-else-if="store.history.length === 0" class="reports-tab__empty">
      <ClipboardList class="w-12 h-12 text-text-muted" />
      <p>Noch keine Diagnose-Reports vorhanden.</p>
      <p class="reports-tab__empty-hint">
        Starte eine Diagnose im "Diagnose"-Tab, um den ersten Report zu erstellen.
      </p>
    </div>

    <!-- Report Table -->
    <div v-else class="reports-tab__table-wrap">
      <table class="reports-tab__table">
        <thead>
          <tr>
            <th>Datum</th>
            <th>Status</th>
            <th>Dauer</th>
            <th>Ausgelöst durch</th>
            <th class="reports-tab__th-actions">Aktionen</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="report in store.history" :key="report.id">
            <tr class="reports-tab__row" @click="toggleReport(report.id)">
              <td>
                <div class="reports-tab__date">
                  <span class="reports-tab__date-full">{{ formatTimestamp(report.started_at) }}</span>
                  <span class="reports-tab__date-relative">{{ formatRelativeTime(new Date(report.started_at)) }}</span>
                </div>
              </td>
              <td>
                <span :class="['reports-tab__status', statusClass(report.overall_status)]">
                  {{ statusLabel(report.overall_status) }}
                </span>
              </td>
              <td class="reports-tab__duration">
                {{ formatDuration(report.duration_seconds) }}
              </td>
              <td class="reports-tab__trigger">
                {{ triggerLabel(report.triggered_by) }}
              </td>
              <td class="reports-tab__actions">
                <button
                  class="reports-tab__btn"
                  title="Details anzeigen"
                  @click.stop="toggleReport(report.id)"
                >
                  <Eye class="w-4 h-4" />
                </button>
                <button
                  class="reports-tab__btn"
                  title="Als Markdown herunterladen"
                  @click.stop="downloadReport(report.id)"
                >
                  <Download class="w-4 h-4" />
                </button>
                <ChevronUp v-if="expandedReportId === report.id" class="w-4 h-4 text-text-muted" />
                <ChevronDown v-else class="w-4 h-4 text-text-muted" />
              </td>
            </tr>

            <!-- Expanded Detail Row -->
            <tr v-if="expandedReportId === report.id" class="reports-tab__detail-row">
              <td colspan="5">
                <div class="reports-tab__detail">
                  <BaseSpinner v-if="isLoadingDetail" size="sm" />
                  <template v-else-if="expandedReportData">
                    <!-- Check summary -->
                    <div class="reports-tab__checks-grid">
                      <div
                        v-for="check in expandedReportData.checks"
                        :key="check.name"
                        :class="['reports-tab__check-pill', `reports-tab__check-pill--${check.status}`]"
                      >
                        <span class="reports-tab__check-dot" />
                        {{ check.name.replace(/_/g, ' ') }}
                      </div>
                    </div>
                    <!-- Summary text -->
                    <p v-if="expandedReportData.summary" class="reports-tab__detail-summary">
                      {{ expandedReportData.summary }}
                    </p>
                  </template>
                  <span v-else class="reports-tab__detail-error">Konnte nicht geladen werden</span>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.reports-tab {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.reports-tab__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.reports-tab__title-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.reports-tab__title {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}

.reports-tab__count {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  background: var(--color-bg-tertiary);
  padding: 2px var(--space-2);
  border-radius: var(--radius-full);
}

.reports-tab__refresh {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.reports-tab__refresh:hover {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

/* Loading & Empty */
.reports-tab__loading,
.reports-tab__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-8) 0;
  color: var(--color-text-muted);
}

.reports-tab__empty-hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

/* Table */
.reports-tab__table-wrap {
  overflow-x: auto;
}

.reports-tab__table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}

.reports-tab__table thead {
  border-bottom: 1px solid var(--glass-border);
}

.reports-tab__table th {
  text-align: left;
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.reports-tab__th-actions {
  text-align: right;
}

.reports-tab__row {
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.reports-tab__row:hover {
  background: var(--color-bg-tertiary);
}

.reports-tab__table td {
  padding: var(--space-2) var(--space-3);
  vertical-align: middle;
}

/* Date */
.reports-tab__date {
  display: flex;
  flex-direction: column;
}

.reports-tab__date-full {
  font-size: var(--text-sm);
  color: var(--color-text-primary);
}

.reports-tab__date-relative {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

/* Status */
.reports-tab__status {
  display: inline-block;
  padding: 2px var(--space-2);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: 500;
}

.reports-tab__status--healthy {
  background: rgba(52, 211, 153, 0.15);
  color: var(--color-success);
}

.reports-tab__status--warning {
  background: rgba(251, 191, 36, 0.15);
  color: var(--color-warning);
}

.reports-tab__status--critical,
.reports-tab__status--error {
  background: rgba(248, 113, 113, 0.15);
  color: var(--color-error);
}

.reports-tab__duration {
  font-variant-numeric: tabular-nums;
  color: var(--color-text-secondary);
}

.reports-tab__trigger {
  color: var(--color-text-secondary);
}

/* Actions */
.reports-tab__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-1);
}

.reports-tab__btn {
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

.reports-tab__btn:hover {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

/* Detail Row */
.reports-tab__detail-row td {
  padding: 0 var(--space-3) var(--space-3);
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.reports-tab__detail {
  padding: var(--space-3);
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
}

.reports-tab__checks-grid {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}

.reports-tab__check-pill {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: 2px var(--space-2);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  color: var(--color-text-secondary);
  text-transform: capitalize;
}

.reports-tab__check-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.reports-tab__check-pill--healthy .reports-tab__check-dot { background: var(--color-success); }
.reports-tab__check-pill--warning .reports-tab__check-dot { background: var(--color-warning); }
.reports-tab__check-pill--critical .reports-tab__check-dot,
.reports-tab__check-pill--error .reports-tab__check-dot { background: var(--color-error); }

.reports-tab__detail-summary {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  margin: var(--space-2) 0 0;
}

.reports-tab__detail-error {
  font-size: var(--text-xs);
  color: var(--color-error);
}
</style>
