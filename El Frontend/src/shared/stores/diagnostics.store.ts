/**
 * Diagnostics Store (Phase 4D)
 *
 * Manages diagnostic check results, report history, and running state.
 *
 * Data flow:
 * - Run diagnostic: REST API → currentReport
 * - History: REST API → history[]
 * - Export: REST API → Markdown string
 * - Available checks: REST API → availableChecks[]
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  runFullDiagnostic,
  runSingleCheck,
  getDiagnosticHistory,
  getDiagnosticReport,
  exportReportAsMarkdown,
  listAvailableChecks,
  type DiagnosticReport,
  type CheckResult,
  type ReportHistoryItem,
  type AvailableCheck,
  type CheckStatusValue,
} from '@/api/diagnostics'
import { createLogger } from '@/utils/logger'

const logger = createLogger('DiagnosticsStore')

export const useDiagnosticsStore = defineStore('diagnostics', () => {
  // ═══════════════════════════════════════════════════════════════════════════
  // State
  // ═══════════════════════════════════════════════════════════════════════════

  const currentReport = ref<DiagnosticReport | null>(null)
  const history = ref<ReportHistoryItem[]>([])
  const availableChecks = ref<AvailableCheck[]>([])
  const isRunning = ref(false)
  const runningCheck = ref<string | null>(null)
  const isLoadingHistory = ref(false)
  const error = ref<string | null>(null)

  // ═══════════════════════════════════════════════════════════════════════════
  // Computed
  // ═══════════════════════════════════════════════════════════════════════════

  /** Overall status of the latest report */
  const overallStatus = computed<CheckStatusValue | null>(
    () => currentReport.value?.overall_status ?? null,
  )

  /** Check results from current report, keyed by name */
  const checksByName = computed<Record<string, CheckResult>>(() => {
    if (!currentReport.value) return {}
    const map: Record<string, CheckResult> = {}
    for (const check of currentReport.value.checks) {
      map[check.name] = check
    }
    return map
  })

  /** Count of checks by status in current report */
  const statusCounts = computed(() => {
    if (!currentReport.value) return { healthy: 0, warning: 0, critical: 0, error: 0 }
    const counts = { healthy: 0, warning: 0, critical: 0, error: 0 }
    for (const check of currentReport.value.checks) {
      const s = check.status as keyof typeof counts
      if (s in counts) counts[s]++
    }
    return counts
  })

  /** Whether there's any critical or error check */
  const hasProblems = computed(
    () => statusCounts.value.critical > 0 || statusCounts.value.error > 0,
  )

  /** Time since last report in human-readable form (currentReport oder neuester aus History) */
  const lastRunAge = computed<string | null>(() => {
    const report = currentReport.value ?? history.value[0]
    if (!report) return null
    const finished = new Date(report.finished_at)
    const diffMs = Date.now() - finished.getTime()
    const diffMin = Math.floor(diffMs / 60_000)
    if (diffMin < 1) return 'gerade eben'
    if (diffMin < 60) return `vor ${diffMin}m`
    const diffH = Math.floor(diffMin / 60)
    if (diffH < 24) return `vor ${diffH}h`
    return `vor ${Math.floor(diffH / 24)}d`
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Actions
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * Run all 10 diagnostic checks.
   */
  async function runDiagnostic(): Promise<DiagnosticReport | null> {
    if (isRunning.value) return null
    isRunning.value = true
    runningCheck.value = null
    error.value = null

    try {
      const report = await runFullDiagnostic()
      currentReport.value = report
      logger.info(`Diagnostic complete: ${report.overall_status} (${report.duration_seconds.toFixed(1)}s)`)
      return report
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Diagnostic failed'
      error.value = msg
      logger.error('Full diagnostic failed', err)
      return null
    } finally {
      isRunning.value = false
      runningCheck.value = null
    }
  }

  /**
   * Run a single diagnostic check by name.
   */
  async function runCheck(checkName: string): Promise<CheckResult | null> {
    if (isRunning.value) return null
    isRunning.value = true
    runningCheck.value = checkName
    error.value = null

    try {
      const result = await runSingleCheck(checkName)

      // Update the check in current report if present
      if (currentReport.value) {
        const idx = currentReport.value.checks.findIndex((c) => c.name === checkName)
        if (idx >= 0) {
          currentReport.value.checks[idx] = result
        }
      }

      logger.info(`Check '${checkName}' complete: ${result.status}`)
      return result
    } catch (err) {
      const msg = err instanceof Error ? err.message : `Check '${checkName}' failed`
      error.value = msg
      logger.error(`Single check '${checkName}' failed`, err)
      return null
    } finally {
      isRunning.value = false
      runningCheck.value = null
    }
  }

  /**
   * Load report history.
   */
  async function loadHistory(limit: number = 20): Promise<void> {
    if (isLoadingHistory.value) return
    isLoadingHistory.value = true

    try {
      history.value = await getDiagnosticHistory(limit)
      logger.debug(`Loaded ${history.value.length} history entries`)
    } catch (err) {
      logger.error('Failed to load diagnostic history', err)
    } finally {
      isLoadingHistory.value = false
    }
  }

  /**
   * Load a specific report by ID.
   */
  async function loadReport(reportId: string): Promise<DiagnosticReport | null> {
    try {
      const report = await getDiagnosticReport(reportId)
      return report
    } catch (err) {
      logger.error(`Failed to load report ${reportId}`, err)
      return null
    }
  }

  /**
   * Export a report as Markdown.
   */
  async function exportReport(reportId: string): Promise<string | null> {
    try {
      const result = await exportReportAsMarkdown(reportId)
      return result.markdown
    } catch (err) {
      logger.error(`Failed to export report ${reportId}`, err)
      return null
    }
  }

  /**
   * Load available check names.
   */
  async function loadAvailableChecks(): Promise<void> {
    try {
      availableChecks.value = await listAvailableChecks()
    } catch (err) {
      logger.error('Failed to load available checks', err)
    }
  }

  return {
    // State
    currentReport,
    history,
    availableChecks,
    isRunning,
    runningCheck,
    isLoadingHistory,
    error,

    // Computed
    overallStatus,
    checksByName,
    statusCounts,
    hasProblems,
    lastRunAge,

    // Actions
    runDiagnostic,
    runCheck,
    loadHistory,
    loadReport,
    exportReport,
    loadAvailableChecks,
  }
})
