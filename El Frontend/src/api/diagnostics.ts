/**
 * Diagnostics API Client
 *
 * Phase 4D.2.1: REST-API client for System Diagnostics Hub.
 * Provides functions to run checks, view history, and export reports.
 */

import api from './index'

// =============================================================================
// Types
// =============================================================================

export type CheckStatusValue = 'healthy' | 'warning' | 'critical' | 'error'

export interface CheckResult {
  name: string
  status: CheckStatusValue
  message: string
  details: Record<string, unknown>
  metrics: Record<string, unknown>
  recommendations: string[]
  duration_ms: number
}

export interface DiagnosticReport {
  id: string
  overall_status: CheckStatusValue
  started_at: string
  finished_at: string
  duration_seconds: number
  checks: CheckResult[]
  summary: string
  triggered_by: string
}

export interface ReportHistoryItem {
  id: string
  overall_status: CheckStatusValue
  started_at: string
  finished_at: string
  duration_seconds: number
  triggered_by: string
  summary: string | null
}

export interface AvailableCheck {
  name: string
  display_name: string
}

export interface ExportResponse {
  markdown: string
  report_id: string
}

// =============================================================================
// API Functions
// =============================================================================

export async function runFullDiagnostic(): Promise<DiagnosticReport> {
  const response = await api.post<DiagnosticReport>('/diagnostics/run')
  return response.data
}

export async function runSingleCheck(checkName: string): Promise<CheckResult> {
  const response = await api.post<CheckResult>(`/diagnostics/run/${checkName}`)
  return response.data
}

export async function getDiagnosticHistory(
  limit: number = 20,
  offset: number = 0,
): Promise<ReportHistoryItem[]> {
  const response = await api.get<ReportHistoryItem[]>('/diagnostics/history', {
    params: { limit, offset },
  })
  return response.data
}

export async function getDiagnosticReport(reportId: string): Promise<DiagnosticReport> {
  const response = await api.get<DiagnosticReport>(`/diagnostics/history/${reportId}`)
  return response.data
}

export async function exportReportAsMarkdown(reportId: string): Promise<ExportResponse> {
  const response = await api.post<ExportResponse>(`/diagnostics/export/${reportId}`)
  return response.data
}

export async function listAvailableChecks(): Promise<AvailableCheck[]> {
  const response = await api.get<AvailableCheck[]>('/diagnostics/checks')
  return response.data
}
