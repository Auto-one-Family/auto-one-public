/**
 * useEmailPostfach — Composable for E-Mail-Postfach View
 *
 * Encapsulates API calls, filter state, and pagination for the email log.
 * Admin-only; no Pinia store (limited scope).
 */

import { ref, computed, watch } from 'vue'
import { notificationsApi } from '@/api/notifications'
import type {
  EmailLogEntry,
  EmailLogListFilters,
  EmailLogStatus,
  EmailLogStatsDTO,
  PaginationMeta,
} from '@/api/notifications'

const DEFAULT_PAGE_SIZE = 25

export function useEmailPostfach() {
  const emails = ref<EmailLogEntry[]>([])
  const stats = ref<EmailLogStatsDTO | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const pagination = ref<PaginationMeta | null>(null)
  const selectedEntry = ref<EmailLogEntry | null>(null)
  const lastLoadedAt = ref<string | null>(null)

  // Filter state
  const statusFilter = ref<EmailLogStatus | ''>('')
  const dateFrom = ref('')
  const dateTo = ref('')
  const templateFilter = ref('')
  const page = ref(1)
  const pageSize = ref(DEFAULT_PAGE_SIZE)

  const filters = computed<EmailLogListFilters>(() => {
    const f: EmailLogListFilters = {
      page: page.value,
      page_size: pageSize.value,
    }
    if (statusFilter.value) f.status = statusFilter.value as EmailLogStatus
    if (dateFrom.value) f.date_from = dateFrom.value
    if (dateTo.value) f.date_to = dateTo.value
    if (templateFilter.value.trim()) f.template = templateFilter.value.trim()
    return f
  })

  async function loadEmails(): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      const res = await notificationsApi.getEmailLog(filters.value)
      emails.value = res.data
      pagination.value = res.pagination
      lastLoadedAt.value = new Date().toISOString()
    } catch (err: unknown) {
      const axiosError = err as { response?: { data?: { detail?: string } } }
      error.value = axiosError.response?.data?.detail ?? 'E-Mail-Log konnte nicht geladen werden'
      emails.value = []
      pagination.value = null
    } finally {
      isLoading.value = false
    }
  }

  async function loadStats(): Promise<void> {
    try {
      stats.value = await notificationsApi.getEmailLogStats()
    } catch {
      stats.value = null
    }
  }

  function openDetail(entry: EmailLogEntry): void {
    selectedEntry.value = entry
  }

  function closeDetail(): void {
    selectedEntry.value = null
  }

  function goToPage(p: number): void {
    if (p >= 1 && pagination.value && p <= pagination.value.total_pages) {
      page.value = p
    }
  }

  function resetFilters(): void {
    statusFilter.value = ''
    dateFrom.value = ''
    dateTo.value = ''
    templateFilter.value = ''
    page.value = 1
  }

  watch(filters, () => loadEmails(), { deep: true })

  function setPageSize(size: number): void {
    pageSize.value = size
    page.value = 1
  }

  return {
    emails,
    stats,
    isLoading,
    error,
    pagination,
    selectedEntry,
    lastLoadedAt,
    statusFilter,
    dateFrom,
    dateTo,
    templateFilter,
    page,
    pageSize,
    loadEmails,
    loadStats,
    openDetail,
    closeDetail,
    goToPage,
    setPageSize,
    resetFilters,
  }
}
