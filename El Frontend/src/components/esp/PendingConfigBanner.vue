<script setup lang="ts">
/**
 * PendingConfigBanner — Inline status surface for pending config orders.
 *
 * Shows when a config order is still awaiting terminal device response
 * (pending, accepted) or has timed out without definitive failure.
 * Replaces hard-fail error toasts with a persistent, actionable banner.
 *
 * Features:
 * - Spinner for active pending, warning icon for timeout
 * - correlation_id display
 * - Deep-link to SystemMonitorView (events tab)
 * - Retry button (emits retry event)
 * - Dismiss button for timed-out orders
 * - aria-live="polite" for screen readers
 */

import { computed } from 'vue'
import { Loader2, AlertTriangle, ExternalLink, RefreshCw, X } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { useActuatorStore } from '@/shared/stores/actuator.store'

interface Props {
  subjectId: string | null
  correlationId?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  correlationId: null,
})

const emit = defineEmits<{
  retry: []
}>()

const router = useRouter()
const actuatorStore = useActuatorStore()

const intent = computed(() => {
  if (!props.subjectId) return null
  return actuatorStore.findConfigIntentBySubject(
    props.subjectId,
    props.correlationId ?? undefined,
  ) ?? null
})

const isVisible = computed(() => {
  if (!intent.value) return false
  const s = intent.value.state
  return s === 'accepted' || s === 'pending' || s === 'terminal_timeout'
})

const isTimeout = computed(() => intent.value?.state === 'terminal_timeout')
const isPending = computed(() => !isTimeout.value)
const queueHint = computed(() => {
  const hints = intent.value?.nonTerminalHints
  if (!hints || hints.length === 0) return null
  // Last hint is the freshest signal from config_published handling.
  const latest = hints[hints.length - 1]?.trim()
  return latest || null
})
const isQueuedOffline = computed(() => {
  const hint = queueHint.value?.toLowerCase()
  if (!hint) return false
  return hint.includes('gequeued') || hint.includes('offline')
})

const displayCorrelationId = computed(() => {
  const cid = intent.value?.correlationId
  if (!cid) return null
  if (cid.startsWith('unknown:')) return cid
  return cid.length > 16 ? `${cid.slice(0, 8)}…${cid.slice(-4)}` : cid
})

const elapsedLabel = computed(() => {
  if (!intent.value) return ''
  const elapsed = Date.now() - intent.value.createdAt
  const seconds = Math.floor(elapsed / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  return `${minutes}m ${seconds % 60}s`
})

function openSystemMonitor() {
  router.push({ path: '/system-monitor', query: { tab: 'events' } })
}

function handleRetry() {
  if (props.subjectId) {
    actuatorStore.dismissConfigTimeout(
      props.subjectId,
      props.correlationId ?? undefined,
    )
  }
  emit('retry')
}

function handleDismiss() {
  if (props.subjectId) {
    actuatorStore.dismissConfigTimeout(
      props.subjectId,
      props.correlationId ?? undefined,
    )
  }
}
</script>

<template>
  <div
    v-if="isVisible"
    :class="[
      'pending-config-banner',
      isTimeout ? 'pending-config-banner--timeout' : 'pending-config-banner--pending',
    ]"
    role="status"
    aria-live="polite"
  >
    <div class="pending-config-banner__icon">
      <AlertTriangle v-if="isTimeout" class="pending-config-banner__icon-svg pending-config-banner__icon-svg--warn" />
      <Loader2 v-else class="pending-config-banner__icon-svg pending-config-banner__icon-svg--spin" />
    </div>

    <div class="pending-config-banner__content">
      <span class="pending-config-banner__title">
        {{ isTimeout ? 'Konfigurationsauftrag ausstehend' : 'Konfigurationsauftrag läuft' }}
      </span>
      <span class="pending-config-banner__detail">
        {{
          isPending
            ? (isQueuedOffline ? 'Auftrag gequeued (Gerät offline) — warte auf Reconnect' : 'Warte auf Geräte-Rückmeldung')
            : 'Gerät hat nicht innerhalb der Frist geantwortet'
        }}
        <template v-if="elapsedLabel"> · {{ elapsedLabel }}</template>
      </span>
      <span v-if="isPending && queueHint" class="pending-config-banner__hint">
        {{ queueHint }}
      </span>
      <span v-if="displayCorrelationId" class="pending-config-banner__correlation">
        Korrelation: {{ displayCorrelationId }}
      </span>
    </div>

    <div class="pending-config-banner__actions">
      <button
        v-if="isTimeout"
        class="pending-config-banner__btn pending-config-banner__btn--retry"
        title="Konfiguration erneut senden (neue Korrelations-ID)"
        @click="handleRetry"
      >
        <RefreshCw class="w-3.5 h-3.5" />
        Erneut
      </button>
      <button
        class="pending-config-banner__btn pending-config-banner__btn--link"
        title="Im System-Monitor prüfen"
        @click="openSystemMonitor"
      >
        <ExternalLink class="w-3.5 h-3.5" />
      </button>
      <button
        v-if="isTimeout"
        class="pending-config-banner__btn pending-config-banner__btn--dismiss"
        title="Ausstehenden Auftrag verwerfen"
        @click="handleDismiss"
      >
        <X class="w-3.5 h-3.5" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.pending-config-banner {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  line-height: var(--leading-normal);
}

.pending-config-banner--pending {
  background: var(--color-info-bg);
  border: 1px solid var(--color-info-border);
}

.pending-config-banner--timeout {
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning-border);
}

.pending-config-banner__icon {
  flex-shrink: 0;
  margin-top: 1px;
}

.pending-config-banner__icon-svg {
  width: 16px;
  height: 16px;
}

.pending-config-banner__icon-svg--warn {
  color: var(--color-warning);
}

.pending-config-banner__icon-svg--spin {
  color: var(--color-info);
  animation: spin 1.2s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.pending-config-banner__content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.pending-config-banner__title {
  font-weight: 600;
  color: var(--color-text-primary);
}

.pending-config-banner--timeout .pending-config-banner__title {
  color: var(--color-warning);
}

.pending-config-banner__detail {
  color: var(--color-text-secondary);
}

.pending-config-banner__hint {
  color: var(--color-text-secondary);
  font-size: var(--text-xxs);
}

.pending-config-banner__correlation {
  font-family: var(--font-mono);
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
}

.pending-config-banner__actions {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  flex-shrink: 0;
}

.pending-config-banner__btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: 3px var(--space-2);
  border-radius: var(--radius-xs);
  font-size: var(--text-xxs);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  border: 1px solid transparent;
  background: transparent;
}

.pending-config-banner__btn--retry {
  color: var(--color-warning);
  border-color: var(--color-warning-border);
}

.pending-config-banner__btn--retry:hover {
  background: var(--color-warning-bg-hover);
}

.pending-config-banner__btn--link {
  color: var(--color-text-muted);
}

.pending-config-banner__btn--link:hover {
  color: var(--color-text-secondary);
}

.pending-config-banner__btn--dismiss {
  color: var(--color-text-muted);
}

.pending-config-banner__btn--dismiss:hover {
  color: var(--color-text-secondary);
}
</style>
