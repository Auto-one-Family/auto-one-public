<script setup lang="ts">
/**
 * ErrorDetailsModal - Modal für detaillierte Fehlerinformationen
 *
 * Zeigt:
 * - Menschenlesbare Fehlerbeschreibung (Deutsch)
 * - Troubleshooting-Schritte (nummeriert)
 * - Handlungsbedarf-Indikator
 * - Technische Details (aufklappbar für Entwickler)
 *
 * Wird geöffnet via:
 * 1. Toast "Details"-Button (CustomEvent 'show-error-details')
 * 2. EventDetailsPanel für error_event Typ
 *
 * Server-Centric: Alle Übersetzungen kommen vom Server.
 */

import { ref, nextTick, onUnmounted, computed, watch } from 'vue'
import { useScrollLock } from '@/composables/useScrollLock'
import {
  X,
  AlertTriangle,
  AlertCircle,
  AlertOctagon,
  Info,
  ChevronDown,
  ChevronUp,
  ExternalLink,
} from 'lucide-vue-next'
import TroubleshootingPanel from './TroubleshootingPanel.vue'
import { getCategoryLabel, detectCategory, shouldPulse } from '@/utils/errorCodeTranslator'
import type { ErrorSeverity } from '@/utils/errorCodeTranslator'
import { translateErrorCode } from '@/api/errors'

export interface ErrorDetailsData {
  error_code?: number
  title: string
  description: string
  severity: string
  troubleshooting: string[]
  user_action_required: boolean
  recoverable?: boolean
  esp_id?: string
  esp_name?: string
  docs_link?: string | null
  context?: Record<string, unknown>
  timestamp?: string
  raw_message?: string
}

interface Props {
  error?: ErrorDetailsData | null
  open: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{ close: [] }>()

const showTechnicalDetails = ref(false)
const backdropRef = ref<HTMLElement | null>(null)
const modalRef = ref<HTMLElement | null>(null)
let previouslyFocused: HTMLElement | null = null
const scrollLock = useScrollLock()

// Auto-enrichment: fetch troubleshooting from server when error_code is present but data is missing
const enrichedTroubleshooting = ref<string[]>([])
const enrichedDescription = ref<string | null>(null)
const enrichedDocsLink = ref<string | null>(null)

const effectiveTroubleshooting = computed(() => {
  const original = props.error?.troubleshooting ?? []
  return original.length > 0 ? original : enrichedTroubleshooting.value
})

const effectiveDescription = computed(() => {
  return props.error?.description || enrichedDescription.value || ''
})

const effectiveDocsLink = computed(() => {
  return props.error?.docs_link ?? enrichedDocsLink.value
})

const severityLevel = computed((): ErrorSeverity => {
  const s = props.error?.severity
  if (s === 'info' || s === 'warning' || s === 'error' || s === 'critical') return s
  return 'error'
})

const categoryLabel = computed(() => {
  if (!props.error?.error_code) return ''
  const cat = detectCategory(props.error.error_code)
  return getCategoryLabel(cat)
})

const severityIcon = computed(() => {
  const icons: Record<ErrorSeverity, typeof AlertCircle> = {
    info: Info,
    warning: AlertTriangle,
    error: AlertCircle,
    critical: AlertOctagon,
  }
  return icons[severityLevel.value] ?? AlertCircle
})

const formattedTimestamp = computed(() => {
  if (!props.error?.timestamp) return null
  try {
    const ts = typeof props.error.timestamp === 'number'
      ? new Date(props.error.timestamp * 1000)
      : new Date(props.error.timestamp)
    return ts.toLocaleString('de-DE', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    })
  } catch { return String(props.error.timestamp) }
})

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.open) {
    emit('close')
    return
  }
  if (e.key === 'Tab' && props.open && modalRef.value) {
    const focusable = modalRef.value.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    )
    if (focusable.length === 0) return
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault()
      first.focus()
    }
  }
}

function handleBackdropClick(e: MouseEvent) {
  if (e.target === backdropRef.value) emit('close')
}

watch(() => props.open, (isOpen) => {
  showTechnicalDetails.value = false
  enrichedTroubleshooting.value = []
  enrichedDescription.value = null
  enrichedDocsLink.value = null

  if (isOpen) {
    scrollLock.lock()
    previouslyFocused = document.activeElement as HTMLElement | null
    document.addEventListener('keydown', handleKeydown)
    nextTick(() => {
      const closeBtn = modalRef.value?.querySelector<HTMLElement>('.error-modal__close')
      closeBtn?.focus()
    })

    // Auto-enrich: fetch from server when error_code present but troubleshooting empty
    const err = props.error
    if (err?.error_code && (!err.troubleshooting || err.troubleshooting.length === 0)) {
      translateErrorCode(err.error_code).then((translated) => {
        enrichedTroubleshooting.value = translated.troubleshooting ?? []
        if (!err.description && translated.message) {
          enrichedDescription.value = translated.message
        }
        if (!err.docs_link && translated.docs_link) {
          enrichedDocsLink.value = translated.docs_link
        }
      })
    }
  } else {
    scrollLock.unlock()
    document.removeEventListener('keydown', handleKeydown)
    previouslyFocused?.focus()
    previouslyFocused = null
  }
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  scrollLock.unlock()
})
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="open && error"
        ref="backdropRef"
        class="error-modal-backdrop"
        @click="handleBackdropClick"
      >
        <div
          ref="modalRef"
          class="error-modal"
          :class="[`error-modal--${severityLevel}`, { 'error-modal--pulse': shouldPulse(severityLevel) }]"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="'error-modal-title'"
        >
          <!-- Header -->
          <div class="error-modal__header">
            <div class="error-modal__title-row">
              <component
                :is="severityIcon"
                :size="20"
                class="error-modal__icon"
                :class="`error-modal__icon--${severityLevel}`"
              />
              <h2 id="error-modal-title" class="error-modal__title">{{ error.title }}</h2>
              <button class="error-modal__close" @click="emit('close')" aria-label="Schließen">
                <X :size="18" />
              </button>
            </div>
            <div class="error-modal__meta">
              <span v-if="error.error_code" class="error-modal__code">Fehler {{ error.error_code }}</span>
              <span v-if="categoryLabel" class="error-modal__category">{{ categoryLabel }}</span>
              <span v-if="error.esp_name" class="error-modal__device">{{ error.esp_name }}</span>
              <span v-if="formattedTimestamp" class="error-modal__time">{{ formattedTimestamp }}</span>
            </div>
          </div>

          <!-- Description -->
          <div class="error-modal__body">
            <p class="error-modal__description">{{ effectiveDescription }}</p>

            <!-- Troubleshooting -->
            <TroubleshootingPanel
              v-if="effectiveTroubleshooting.length > 0"
              :steps="effectiveTroubleshooting"
              :user-action-required="error.user_action_required"
              :severity="severityLevel"
            />

            <!-- Docs Link -->
            <a
              v-if="effectiveDocsLink"
              :href="effectiveDocsLink"
              target="_blank"
              rel="noopener"
              class="error-modal__docs-link"
            >
              <ExternalLink :size="14" />
              Dokumentation öffnen
            </a>

            <!-- Technical Details (collapsible) -->
            <div class="error-modal__technical">
              <button
                class="error-modal__toggle"
                @click="showTechnicalDetails = !showTechnicalDetails"
              >
                <component :is="showTechnicalDetails ? ChevronUp : ChevronDown" :size="16" />
                Technische Details
              </button>
              <Transition name="slide">
                <div v-if="showTechnicalDetails" class="error-modal__details">
                  <div v-if="error.raw_message" class="detail-row">
                    <span class="detail-label">Raw Message</span>
                    <span class="detail-value">{{ error.raw_message }}</span>
                  </div>
                  <div v-if="error.esp_id" class="detail-row">
                    <span class="detail-label">ESP-ID</span>
                    <span class="detail-value">{{ error.esp_id }}</span>
                  </div>
                  <div v-if="error.error_code" class="detail-row">
                    <span class="detail-label">Error-Code</span>
                    <span class="detail-value">{{ error.error_code }}</span>
                  </div>
                  <div class="detail-row">
                    <span class="detail-label">Wiederherstellbar</span>
                    <span class="detail-value">{{ error.recoverable !== false ? 'Ja' : 'Nein' }}</span>
                  </div>
                  <div v-if="error.context && Object.keys(error.context).length > 0" class="detail-row">
                    <span class="detail-label">Kontext</span>
                    <pre class="detail-json">{{ JSON.stringify(error.context, null, 2) }}</pre>
                  </div>
                </div>
              </Transition>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.error-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: var(--z-tooltip);
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--backdrop-color-light);
  -webkit-backdrop-filter: blur(var(--backdrop-blur-light));
  backdrop-filter: blur(var(--backdrop-blur-light));
}

.error-modal {
  width: 95%;
  max-width: 520px;
  max-height: 85vh;
  overflow-y: auto;
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 24px 48px rgba(0, 0, 0, 0.4);
}

.error-modal--critical {
  border-color: rgba(220, 38, 38, 0.4);
  box-shadow: 0 24px 48px rgba(0, 0, 0, 0.4), 0 0 20px rgba(220, 38, 38, 0.1);
}

.error-modal--error {
  border-color: rgba(239, 68, 68, 0.25);
}

.error-modal--warning {
  border-color: rgba(245, 158, 11, 0.25);
}

.error-modal--pulse {
  animation: critical-pulse 2s ease-in-out infinite;
}

@keyframes critical-pulse {
  0%, 100% { border-color: rgba(220, 38, 38, 0.4); }
  50% { border-color: rgba(220, 38, 38, 0.7); }
}

/* Header */
.error-modal__header {
  padding: 1.25rem 1.25rem 0.75rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.error-modal__title-row {
  display: flex;
  align-items: center;
  gap: 0.625rem;
}

.error-modal__icon--info { color: var(--color-info); }
.error-modal__icon--warning { color: var(--color-warning); }
.error-modal__icon--error { color: var(--color-error); }
.error-modal__icon--critical { color: var(--color-error); }

.error-modal__title {
  flex: 1;
  font-size: 1rem;
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0;
  line-height: 1.3;
}

.error-modal__close {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.2s ease;
}

.error-modal__close:hover {
  background: rgba(255, 255, 255, 0.08);
  color: var(--color-text-primary);
}

.error-modal__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;
  font-size: 0.6875rem;
  color: var(--color-text-muted);
}

.error-modal__meta > span {
  display: inline-flex;
  align-items: center;
}

.error-modal__code {
  font-family: var(--font-mono, monospace);
  font-weight: 600;
}

.error-modal__meta > span:not(:last-child)::after {
  content: '•';
  margin-left: 0.5rem;
  opacity: 0.4;
}

/* Body */
.error-modal__body {
  padding: 1rem 1.25rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.error-modal__description {
  font-size: 0.875rem;
  line-height: 1.6;
  color: var(--color-text-secondary);
  margin: 0;
}

/* Docs Link */
.error-modal__docs-link {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.8125rem;
  color: var(--color-info);
  text-decoration: none;
  transition: color 0.2s;
}

.error-modal__docs-link:hover {
  color: var(--color-accent-bright);
}

/* Technical Details */
.error-modal__technical {
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  padding-top: 0.75rem;
}

.error-modal__toggle {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  background: none;
  border: none;
  color: var(--color-text-muted);
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  padding: 0.25rem 0;
  transition: color 0.2s;
}

.error-modal__toggle:hover {
  color: var(--color-text-secondary);
}

.error-modal__details {
  margin-top: 0.625rem;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.detail-row {
  display: flex;
  gap: 0.75rem;
  font-size: 0.75rem;
}

.detail-label {
  flex-shrink: 0;
  width: 120px;
  color: var(--color-text-muted);
  font-weight: 600;
}

.detail-value {
  color: var(--color-text-secondary);
  font-family: var(--font-mono, monospace);
  word-break: break-all;
}

.detail-json {
  margin: 0;
  font-size: 0.6875rem;
  line-height: 1.5;
  color: var(--color-text-secondary);
  background: rgba(0, 0, 0, 0.2);
  border-radius: var(--radius-sm);
  padding: 0.5rem;
  overflow-x: auto;
  max-height: 150px;
}

/* Transitions */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}
.modal-enter-active .error-modal,
.modal-leave-active .error-modal {
  transition: transform 0.2s ease, opacity 0.2s ease;
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
.modal-enter-from .error-modal,
.modal-leave-to .error-modal {
  transform: scale(0.95);
  opacity: 0;
}

.slide-enter-active,
.slide-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}
.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  max-height: 0;
}
.slide-enter-to,
.slide-leave-from {
  max-height: 300px;
}
</style>
