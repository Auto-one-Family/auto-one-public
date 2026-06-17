<script setup lang="ts">
/**
 * AutoCleanupStatusBanner - Status-Anzeige für Auto-Cleanup System
 *
 * Zeigt klar und transparent:
 * - Ob Auto-Cleanup aktiv/inaktiv ist
 * - Wann der nächste/letzte Lauf war
 * - Was beim nächsten Lauf gelöscht wird
 *
 * Design: Industrial-Grade, Iridescent, Glassmorphism
 *
 * @see El Servador/god_kaiser_server/src/api/v1/audit.py
 */

import { computed } from 'vue'
import {
  Clock,
  CheckCircle,
  AlertCircle,
  AlertTriangle,
  Power,
  Zap,
  XCircle,
  RefreshCw,
} from 'lucide-vue-next'

import type { AutoCleanupStatus } from '@/api/audit'

// ============================================================================
// Props & Emits
// ============================================================================

interface Props {
  status: AutoCleanupStatus | null
  loading?: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'enable-auto-cleanup': []
  refresh: []
}>()

// ============================================================================
// Computed
// ============================================================================

const bannerClass = computed(() => ({
  'banner-active': props.status?.enabled,
  'banner-inactive': props.status && !props.status.enabled,
  'banner-loading': props.loading,
}))

const statusIcon = computed(() => {
  if (props.loading) return RefreshCw
  if (!props.status) return Clock
  return props.status.enabled ? Zap : XCircle
})

const statusTitle = computed(() => {
  if (props.loading) return 'Status wird geladen...'
  if (!props.status) return 'Status nicht verfügbar'
  if (props.status.enabled) {
    return 'Automatische Bereinigung ist AKTIV'
  }
  return 'Automatische Bereinigung ist INAKTIV'
})

// ============================================================================
// Methods
// ============================================================================

function formatNextRun(isoString: string | null): string {
  if (!isoString) return 'Nicht geplant'

  const next = new Date(isoString)
  const now = new Date()
  const diffMs = next.getTime() - now.getTime()

  if (diffMs <= 0) return 'Jetzt'

  const diffMins = Math.floor(diffMs / (1000 * 60))
  const diffHours = Math.floor(diffMins / 60)
  const remainingMins = diffMins % 60

  if (diffHours < 1) {
    return `in ${diffMins} Minuten`
  } else if (diffHours < 24) {
    return `in ${diffHours}h ${remainingMins}m`
  } else {
    const diffDays = Math.floor(diffHours / 24)
    return `in ${diffDays} Tag${diffDays > 1 ? 'en' : ''}`
  }
}

function formatLastRun(isoString: string | null): string {
  if (!isoString) return 'Noch nie'

  const last = new Date(isoString)
  const now = new Date()
  const diffMs = now.getTime() - last.getTime()

  if (diffMs < 0) return 'Unbekannt'

  const diffMins = Math.floor(diffMs / (1000 * 60))
  const diffHours = Math.floor(diffMins / 60)

  if (diffMins < 1) {
    return 'gerade eben'
  } else if (diffMins < 60) {
    return `vor ${diffMins} Minuten`
  } else if (diffHours < 24) {
    return `vor ${diffHours} Stunden`
  } else {
    const diffDays = Math.floor(diffHours / 24)
    return `vor ${diffDays} Tag${diffDays > 1 ? 'en' : ''}`
  }
}

function formatNumber(num: number): string {
  return new Intl.NumberFormat('de-DE').format(num)
}
</script>

<template>
  <div class="auto-cleanup-banner" :class="bannerClass">
    <!-- Icon -->
    <div class="banner-icon">
      <component
        :is="statusIcon"
        class="w-6 h-6"
        :class="{ 'animate-spin': loading }"
      />
    </div>

    <!-- Content -->
    <div class="banner-content">
      <div class="banner-title">
        {{ statusTitle }}
      </div>

      <div class="banner-details">
        <template v-if="status?.enabled">
          <!-- Nächster Lauf -->
          <div class="detail-item">
            <Clock class="w-4 h-4" />
            <span>Nächster Lauf: <strong>{{ formatNextRun(status.next_run) }}</strong></span>
          </div>

          <!-- Letzter Lauf -->
          <div v-if="status.last_run" class="detail-item">
            <CheckCircle class="w-4 h-4" />
            <span>Letzter Lauf: {{ formatLastRun(status.last_run) }}</span>
          </div>

          <!-- Preview: Was wird gelöscht -->
          <div
            v-if="status.next_cleanup_preview.would_delete > 0"
            class="detail-item preview"
          >
            <AlertCircle class="w-4 h-4" />
            <span>
              Beim nächsten Lauf werden ca.
              <strong>{{ formatNumber(status.next_cleanup_preview.would_delete) }} Events</strong>
              automatisch gelöscht
            </span>
          </div>
          <div v-else class="detail-item success">
            <CheckCircle class="w-4 h-4" />
            <span>Alle Events entsprechen den Aufbewahrungsregeln</span>
          </div>
        </template>

        <template v-else-if="status && !status.enabled">
          <div class="detail-item warning">
            <AlertTriangle class="w-4 h-4" />
            <span>
              Events werden <strong>nicht automatisch</strong> gelöscht.
              Manuelle Bereinigung erforderlich.
            </span>
          </div>
        </template>

        <template v-else-if="loading">
          <div class="detail-item">
            <span>Lade Auto-Cleanup Status...</span>
          </div>
        </template>
      </div>
    </div>

    <!-- Action-Buttons -->
    <div class="banner-actions">
      <button
        class="refresh-btn"
        @click="emit('refresh')"
        :disabled="loading"
        title="Status aktualisieren"
      >
        <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': loading }" />
      </button>

      <button
        v-if="status && !status.enabled"
        class="enable-btn"
        @click="emit('enable-auto-cleanup')"
      >
        <Power class="w-4 h-4" />
        Aktivieren
      </button>
    </div>
  </div>
</template>

<style scoped>
.auto-cleanup-banner {
  display: flex;
  gap: 1rem;
  padding: 1.25rem;
  border-radius: var(--radius-md);
  transition: all 0.3s ease;
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
}

.banner-active {
  background: linear-gradient(
    135deg,
    rgba(34, 197, 94, 0.08) 0%,
    rgba(34, 197, 94, 0.03) 100%
  );
  border-color: rgba(34, 197, 94, 0.3);
}

.banner-inactive {
  background: linear-gradient(
    135deg,
    rgba(251, 191, 36, 0.08) 0%,
    rgba(251, 191, 36, 0.03) 100%
  );
  border-color: rgba(251, 191, 36, 0.3);
}

.banner-loading {
  opacity: 0.7;
}

.banner-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: var(--radius-md);
}

.banner-active .banner-icon {
  background: rgba(34, 197, 94, 0.15);
  color: var(--color-success);
}

.banner-inactive .banner-icon {
  background: rgba(251, 191, 36, 0.15);
  color: var(--color-warning);
}

.banner-loading .banner-icon {
  background: var(--color-bg-quaternary);
  color: var(--color-text-muted);
}

.banner-content {
  flex: 1;
  min-width: 0;
}

.banner-title {
  font-size: 1rem;
  font-weight: 600;
  margin-bottom: 0.5rem;
}

.banner-active .banner-title {
  color: var(--color-success);
}

.banner-inactive .banner-title {
  color: var(--color-warning);
}

.banner-loading .banner-title {
  color: var(--color-text-muted);
}

.banner-details {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.detail-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.detail-item strong {
  color: var(--color-text-primary);
}

.detail-item.preview {
  padding: 0.5rem 0.75rem;
  margin-top: 0.25rem;
  background: rgba(251, 191, 36, 0.1);
  border: 1px solid rgba(251, 191, 36, 0.2);
  border-radius: var(--radius-md);
  color: var(--color-warning);
}

.detail-item.preview strong {
  color: var(--color-warning);
}

.detail-item.success {
  color: var(--color-success);
}

.detail-item.warning {
  color: var(--color-warning);
}

.banner-actions {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  align-self: center;
}

.refresh-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-quaternary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.2s ease;
}

.refresh-btn:hover:not(:disabled) {
  color: var(--color-text-primary);
  border-color: var(--glass-border-hover);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.enable-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 1rem;
  background: var(--gradient-iridescent);
  border: none;
  border-radius: var(--radius-md);
  color: white;
  font-weight: 500;
  font-size: 0.8125rem;
  cursor: pointer;
  transition: all 0.3s ease;
  white-space: nowrap;
}

.enable-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(102, 126, 234, 0.4);
}

/* Icon sizing */
.w-4 {
  width: 1rem;
}
.h-4 {
  height: 1rem;
}
.w-6 {
  width: 1.5rem;
}
.h-6 {
  height: 1.5rem;
}

/* Mobile Responsive */
@media (max-width: 640px) {
  .auto-cleanup-banner {
    flex-direction: column;
  }

  .banner-icon {
    width: 40px;
    height: 40px;
  }

  .banner-actions {
    flex-direction: row;
    width: 100%;
    justify-content: flex-end;
    margin-top: 0.5rem;
  }

  .enable-btn {
    flex: 1;
    justify-content: center;
  }
}
</style>
