<script setup lang="ts">
/**
 * LogManagementPanel - Log file management modal
 *
 * Features:
 * - Storage overview (total size, file count)
 * - File list with checkboxes for selection
 * - Dry-run preview before deletion
 * - Optional ZIP backup before deletion
 * - Protection for current active log file
 * - Glasmorphism design consistent with Events tab
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { logsApi, type LogFileInfo } from '@/api/logs'
import {
  X,
  FileText,
  Lock,
  Download,
  Trash2,
  RefreshCw,
  HardDrive,
  Files,
  Clock,
  AlertTriangle,
} from 'lucide-vue-next'
import { createLogger } from '@/utils/logger'

const log = createLogger('LogManagement')

const emit = defineEmits<{
  close: []
  'cleanup-success': []
}>()

// ============================================================================
// State
// ============================================================================

const isLoading = ref(false)
const error = ref<string | null>(null)
const files = ref<LogFileInfo[]>([])
const totalSizeMb = ref(0)
const fileCount = ref(0)

const selectedFiles = ref<Set<string>>(new Set())
const createBackup = ref(true)

// Cleanup state
const isDeleting = ref(false)
const cleanupResult = ref<{ deleted: number; sizeMb: number; backupUrl: string | null } | null>(null)

// Confirm dialog
const showConfirm = ref(false)
const dryRunFiles = ref<string[]>([])
const dryRunSizeMb = ref(0)

// ============================================================================
// Computed
// ============================================================================

const deletableFiles = computed(() => files.value.filter(f => !f.is_current))

const selectedCount = computed(() => selectedFiles.value.size)

const selectedSizeMb = computed(() => {
  let total = 0
  for (const fname of selectedFiles.value) {
    const file = files.value.find(f => f.name === fname)
    if (file) total += file.size_mb
  }
  return Math.round(total * 100) / 100
})

const oldestFile = computed(() => {
  if (files.value.length === 0) return null
  const nonCurrent = files.value.filter(f => !f.is_current)
  if (nonCurrent.length === 0) return null
  return nonCurrent.reduce((oldest, f) =>
    new Date(f.modified_at) < new Date(oldest.modified_at) ? f : oldest
  )
})

// ============================================================================
// Methods
// ============================================================================

async function loadStatistics() {
  isLoading.value = true
  error.value = null
  try {
    const stats = await logsApi.getStatistics()
    files.value = stats.files
    totalSizeMb.value = stats.total_size_mb
    fileCount.value = stats.file_count
  } catch (err) {
    error.value = 'Statistiken konnten nicht geladen werden'
    log.error(' Failed to load statistics:', err)
  } finally {
    isLoading.value = false
  }
}

function toggleFile(filename: string) {
  if (selectedFiles.value.has(filename)) {
    selectedFiles.value.delete(filename)
  } else {
    selectedFiles.value.add(filename)
  }
}

function selectAllDeletable() {
  if (selectedCount.value === deletableFiles.value.length) {
    selectedFiles.value.clear()
  } else {
    selectedFiles.value = new Set(deletableFiles.value.map(f => f.name))
  }
}

async function handleDeleteClick() {
  if (selectedCount.value === 0) return

  // Dry-run first
  try {
    const result = await logsApi.cleanup({
      dryRun: true,
      files: Array.from(selectedFiles.value),
    })
    dryRunFiles.value = result.files_to_delete
    dryRunSizeMb.value = result.total_size_mb
    showConfirm.value = true
  } catch (err) {
    error.value = 'Vorschau fehlgeschlagen'
    log.error(' Dry-run failed:', err)
  }
}

async function confirmDelete() {
  isDeleting.value = true
  error.value = null
  showConfirm.value = false

  try {
    const result = await logsApi.cleanup({
      dryRun: false,
      files: Array.from(selectedFiles.value),
      createBackup: createBackup.value,
    })
    cleanupResult.value = {
      deleted: result.deleted_count,
      sizeMb: result.total_size_mb,
      backupUrl: result.backup_url,
    }
    selectedFiles.value.clear()
    emit('cleanup-success')
    await loadStatistics()
  } catch (err) {
    error.value = 'Bereinigung fehlgeschlagen'
    log.error(' Cleanup failed:', err)
  } finally {
    isDeleting.value = false
  }
}

function downloadBackup(backupUrl: string) {
  const url = logsApi.getBackupDownloadUrl(backupUrl)
  window.open(url, '_blank')
}

function formatTimeAgo(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffMins < 1) return 'gerade eben'
  if (diffMins < 60) return `vor ${diffMins} Min.`
  if (diffHours < 24) return `vor ${diffHours} Std.`
  return `vor ${diffDays} Tag${diffDays > 1 ? 'en' : ''}`
}

function formatEntryCount(count: number | null): string {
  if (count === null) return '?'
  return new Intl.NumberFormat('de-DE').format(count)
}

function handleBackdropClick(e: MouseEvent) {
  if (e.target === e.currentTarget) {
    emit('close')
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    if (showConfirm.value) {
      showConfirm.value = false
    } else {
      emit('close')
    }
  }
}

// ============================================================================
// Lifecycle
// ============================================================================

onMounted(() => {
  loadStatistics()
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <div class="mgmt-overlay" @click="handleBackdropClick">
    <div class="mgmt-panel">
      <!-- Header -->
      <div class="mgmt-header">
        <div class="mgmt-header__title">
          <FileText class="w-5 h-5" />
          <div>
            <h2 class="mgmt-header__h2">Log-Verwaltung</h2>
            <p class="mgmt-header__subtitle">Server-Logs verwalten und bereinigen</p>
          </div>
        </div>
        <button class="mgmt-close" @click="emit('close')">
          <X class="w-5 h-5" />
        </button>
      </div>

      <!-- Content -->
      <div class="mgmt-content">
        <!-- Error -->
        <div v-if="error" class="mgmt-error">
          <AlertTriangle class="w-4 h-4" />
          <span>{{ error }}</span>
          <button @click="error = null">&times;</button>
        </div>

        <!-- Success Result -->
        <div v-if="cleanupResult" class="mgmt-success">
          <span>{{ cleanupResult.deleted }} Dateien gelöscht ({{ cleanupResult.sizeMb }} MB freigegeben)</span>
          <button
            v-if="cleanupResult.backupUrl"
            class="mgmt-success__download"
            @click="downloadBackup(cleanupResult.backupUrl!)"
          >
            <Download class="w-3.5 h-3.5" />
            Backup herunterladen
          </button>
          <button @click="cleanupResult = null">&times;</button>
        </div>

        <!-- Loading -->
        <div v-if="isLoading" class="mgmt-loading">
          <RefreshCw class="w-5 h-5 animate-spin" />
          <span>Lade Statistiken...</span>
        </div>

        <template v-else>
          <!-- Storage Overview -->
          <div class="mgmt-section">
            <h3 class="mgmt-section__title">Speicher&uuml;bersicht</h3>
            <div class="mgmt-stats">
              <div class="mgmt-stat">
                <HardDrive class="mgmt-stat__icon" />
                <div class="mgmt-stat__content">
                  <span class="mgmt-stat__value">{{ totalSizeMb }} MB</span>
                  <span class="mgmt-stat__label">Gesamt</span>
                </div>
              </div>
              <div class="mgmt-stat">
                <Files class="mgmt-stat__icon" />
                <div class="mgmt-stat__content">
                  <span class="mgmt-stat__value">{{ fileCount }}</span>
                  <span class="mgmt-stat__label">Dateien</span>
                </div>
              </div>
              <div class="mgmt-stat">
                <Clock class="mgmt-stat__icon" />
                <div class="mgmt-stat__content">
                  <span class="mgmt-stat__value">{{ oldestFile ? formatTimeAgo(oldestFile.modified_at) : 'N/A' }}</span>
                  <span class="mgmt-stat__label">&Auml;lteste</span>
                </div>
              </div>
            </div>
          </div>

          <!-- File List -->
          <div class="mgmt-section">
            <div class="mgmt-section__header">
              <h3 class="mgmt-section__title">Log-Dateien</h3>
              <button
                v-if="deletableFiles.length > 0"
                class="mgmt-select-all"
                @click="selectAllDeletable"
              >
                {{ selectedCount === deletableFiles.length ? 'Keine' : 'Alle' }} ausw&auml;hlen
              </button>
            </div>

            <div class="mgmt-files">
              <div
                v-for="file in files"
                :key="file.name"
                class="mgmt-file"
                :class="{
                  'mgmt-file--current': file.is_current,
                  'mgmt-file--selected': selectedFiles.has(file.name),
                }"
              >
                <label class="mgmt-file__label">
                  <input
                    type="checkbox"
                    :checked="selectedFiles.has(file.name)"
                    :disabled="file.is_current"
                    class="mgmt-file__checkbox"
                    @change="toggleFile(file.name)"
                  />

                  <FileText class="mgmt-file__icon" />

                  <div class="mgmt-file__info">
                    <span class="mgmt-file__name">{{ file.name }}</span>
                    <span class="mgmt-file__meta">
                      {{ file.size_mb }} MB &middot; {{ formatEntryCount(file.entry_count) }} Eintr&auml;ge &middot; {{ formatTimeAgo(file.modified_at) }}
                    </span>
                  </div>

                  <Lock v-if="file.is_current" class="mgmt-file__lock" />
                </label>
              </div>
            </div>

            <!-- Selection Summary -->
            <div v-if="selectedCount > 0" class="mgmt-selection">
              Ausgew&auml;hlt: {{ selectedCount }} Dateien ({{ selectedSizeMb }} MB)
            </div>
          </div>

          <!-- Actions -->
          <div class="mgmt-section">
            <h3 class="mgmt-section__title">Aktionen</h3>

            <label class="mgmt-backup-toggle">
              <input
                v-model="createBackup"
                type="checkbox"
                class="mgmt-backup-toggle__checkbox"
              />
              <span>Backup vor Löschung erstellen (ZIP-Download)</span>
            </label>

            <div class="mgmt-actions">
              <button
                class="btn-ghost btn-sm"
                @click="emit('close')"
              >
                Abbrechen
              </button>
              <button
                class="mgmt-delete-btn"
                :disabled="selectedCount === 0 || isDeleting"
                @click="handleDeleteClick"
              >
                <Trash2 class="w-4 h-4" />
                {{ isDeleting ? 'Wird gelöscht...' : `Ausgew&auml;hlte l&ouml;schen (${selectedCount})` }}
              </button>
            </div>
          </div>
        </template>
      </div>

      <!-- Confirm Dialog -->
      <Transition name="fade">
        <div v-if="showConfirm" class="mgmt-confirm-overlay" @click.self="showConfirm = false">
          <div class="mgmt-confirm">
            <AlertTriangle class="mgmt-confirm__icon" />
            <h3 class="mgmt-confirm__title">Dateien endg&uuml;ltig l&ouml;schen?</h3>
            <p class="mgmt-confirm__text">
              {{ dryRunFiles.length }} Dateien ({{ dryRunSizeMb }} MB) werden unwiderruflich gel&ouml;scht.
              <template v-if="createBackup">
                Ein Backup wird vorher erstellt.
              </template>
            </p>
            <ul class="mgmt-confirm__files">
              <li v-for="fname in dryRunFiles" :key="fname">{{ fname }}</li>
            </ul>
            <div class="mgmt-confirm__actions">
              <button class="btn-ghost btn-sm" @click="showConfirm = false">Abbrechen</button>
              <button class="mgmt-confirm__delete" @click="confirmDelete">
                <Trash2 class="w-4 h-4" />
                Endg&uuml;ltig l&ouml;schen
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </div>
  </div>
</template>

<style scoped>
/* =============================================================================
   Overlay & Panel
   ============================================================================= */
.mgmt-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
}

.mgmt-panel {
  width: 100%;
  max-width: 40rem;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  border-radius: var(--radius-lg);
  background: rgba(15, 15, 20, 0.95);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow:
    0 24px 48px rgba(0, 0, 0, 0.4),
    0 0 60px rgba(96, 165, 250, 0.08);
  overflow: hidden;
}

/* =============================================================================
   Header
   ============================================================================= */
.mgmt-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.25rem 1.5rem;
  background: linear-gradient(135deg, rgba(96, 165, 250, 0.06) 0%, transparent 100%);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.mgmt-header__title {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  color: var(--color-text-primary);
}

.mgmt-header__h2 {
  font-size: 1rem;
  font-weight: 600;
  margin: 0;
  color: var(--color-text-primary);
}

.mgmt-header__subtitle {
  font-size: 0.75rem;
  color: var(--color-text-muted);
  margin: 0;
}

.mgmt-close {
  padding: 0.375rem;
  color: var(--color-text-muted);
  background: none;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.15s;
}

.mgmt-close:hover {
  color: var(--color-text-primary);
  background-color: rgba(255, 255, 255, 0.08);
}

/* =============================================================================
   Content
   ============================================================================= */
.mgmt-content {
  flex: 1;
  overflow-y: auto;
  padding: 1.25rem 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

/* =============================================================================
   Error & Success
   ============================================================================= */
.mgmt-error {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 0.75rem;
  font-size: 0.8125rem;
  color: rgb(248, 113, 113);
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: var(--radius-md);
}

.mgmt-error button {
  margin-left: auto;
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
  font-size: 1.125rem;
}

.mgmt-success {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 0.75rem;
  font-size: 0.8125rem;
  color: rgb(74, 222, 128);
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.2);
  border-radius: var(--radius-md);
}

.mgmt-success button {
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
}

.mgmt-success__download {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.5rem;
  font-size: 0.75rem;
  border: 1px solid rgba(34, 197, 94, 0.3) !important;
  border-radius: var(--radius-xs);
}

.mgmt-success__download:hover {
  background: rgba(34, 197, 94, 0.15) !important;
}

/* =============================================================================
   Loading
   ============================================================================= */
.mgmt-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  padding: 3rem;
  color: var(--color-text-muted);
}

/* =============================================================================
   Section
   ============================================================================= */
.mgmt-section {
  padding: 1rem;
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.mgmt-section__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}

.mgmt-section__title {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
  margin: 0 0 0.75rem;
}

.mgmt-section__header .mgmt-section__title {
  margin-bottom: 0;
}

/* =============================================================================
   Stats
   ============================================================================= */
.mgmt-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.75rem;
}

.mgmt-stat {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  padding: 0.75rem;
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.mgmt-stat__icon {
  width: 1.25rem;
  height: 1.25rem;
  color: rgb(96, 165, 250);
  flex-shrink: 0;
}

.mgmt-stat__content {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.mgmt-stat__value {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.mgmt-stat__label {
  font-size: 0.6875rem;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

/* =============================================================================
   Select All
   ============================================================================= */
.mgmt-select-all {
  font-size: 0.75rem;
  color: rgb(96, 165, 250);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  border-radius: var(--radius-xs);
}

.mgmt-select-all:hover {
  background: rgba(96, 165, 250, 0.1);
}

/* =============================================================================
   Files
   ============================================================================= */
.mgmt-files {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.mgmt-file {
  border-radius: var(--radius-md);
  transition: background-color 0.15s;
}

.mgmt-file:hover {
  background-color: rgba(255, 255, 255, 0.04);
}

.mgmt-file--selected {
  background-color: rgba(96, 165, 250, 0.06);
}

.mgmt-file--current {
  opacity: 0.6;
}

.mgmt-file__label {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  padding: 0.625rem 0.75rem;
  cursor: pointer;
}

.mgmt-file--current .mgmt-file__label {
  cursor: default;
}

.mgmt-file__checkbox {
  flex-shrink: 0;
  width: 1rem;
  height: 1rem;
  accent-color: rgb(96, 165, 250);
}

.mgmt-file__icon {
  width: 1rem;
  height: 1rem;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.mgmt-file__info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.mgmt-file__name {
  font-size: 0.8125rem;
  font-family: var(--font-mono);
  color: var(--color-text-primary);
}

.mgmt-file__meta {
  font-size: 0.6875rem;
  color: var(--color-text-muted);
}

.mgmt-file__lock {
  width: 0.875rem;
  height: 0.875rem;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

/* =============================================================================
   Selection Summary
   ============================================================================= */
.mgmt-selection {
  margin-top: 0.5rem;
  padding-top: 0.5rem;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  font-size: 0.75rem;
  color: rgb(96, 165, 250);
}

/* =============================================================================
   Backup Toggle
   ============================================================================= */
.mgmt-backup-toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  cursor: pointer;
  margin-bottom: 1rem;
}

.mgmt-backup-toggle__checkbox {
  width: 1rem;
  height: 1rem;
  accent-color: rgb(96, 165, 250);
}

/* =============================================================================
   Actions
   ============================================================================= */
.mgmt-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.75rem;
}

.mgmt-delete-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 1rem;
  font-size: 0.8125rem;
  font-weight: 500;
  color: white;
  background-color: rgb(220, 38, 38);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.15s;
}

.mgmt-delete-btn:hover:not(:disabled) {
  background-color: rgb(239, 68, 68);
}

.mgmt-delete-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* =============================================================================
   Confirm Dialog
   ============================================================================= */
.mgmt-confirm-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  border-radius: var(--radius-lg);
}

.mgmt-confirm {
  width: 90%;
  max-width: 24rem;
  padding: 1.5rem;
  border-radius: var(--radius-md);
  background: rgba(25, 25, 30, 0.98);
  border: 1px solid rgba(239, 68, 68, 0.2);
  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.3);
  text-align: center;
}

.mgmt-confirm__icon {
  width: 2.5rem;
  height: 2.5rem;
  color: rgb(245, 158, 11);
  margin: 0 auto 0.75rem;
}

.mgmt-confirm__title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0 0 0.5rem;
}

.mgmt-confirm__text {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  margin: 0 0 0.75rem;
  line-height: 1.5;
}

.mgmt-confirm__files {
  text-align: left;
  margin: 0 0 1rem;
  padding: 0.625rem 0.75rem;
  list-style: none;
  font-size: 0.75rem;
  font-family: var(--font-mono);
  color: var(--color-text-muted);
  background: rgba(0, 0, 0, 0.3);
  border-radius: var(--radius-sm);
  max-height: 8rem;
  overflow-y: auto;
}

.mgmt-confirm__files li {
  padding: 0.125rem 0;
}

.mgmt-confirm__actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
}

.mgmt-confirm__delete {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 1rem;
  font-size: 0.8125rem;
  font-weight: 500;
  color: white;
  background-color: rgb(220, 38, 38);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background-color 0.15s;
}

.mgmt-confirm__delete:hover {
  background-color: rgb(239, 68, 68);
}

/* =============================================================================
   Transitions
   ============================================================================= */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
