/**
 * Kanonische Intent-Signale (intent_outcome / intent_outcome_lifecycle) — P0-B.
 *
 * Policy:
 * - Terminal intent_outcome ist idempotent: wiederholtes Event überschreibt mit gleichem Text (kein Flackern).
 * - Lifecycle-Events werden ignoriert, sobald für dasselbe Gerät ein terminaler Outcome gesetzt ist
 *   (kein Überschreiben des Endergebnisses durch spätere Zwischenstände).
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface IntentSignalsDisplay {
  /** Kurze Korrelations-/Intent-ID für die UI */
  correlationShort: string
  /** Zwischenstand (Konfiguration) — nur wenn noch kein Ergebnis */
  lifecycleSummary: string | null
  /** Terminaler Outcome-Text */
  resultSummary: string | null
  /** Firmware-/Contract-Code (nicht als pauschaler Vertragsfehler labeln) */
  firmwareCode: string | null
  /** Letzter Flow war terminal — blockiert weitere Lifecycle-Texte bis ein nicht-terminaler Outcome kommt */
  hasTerminalResult: boolean
  updatedAt: number
}

function shortId(correlationId: string | undefined, intentId: string | undefined): string {
  const raw = (correlationId || intentId || '').trim()
  if (!raw) return '—'
  return raw.length <= 12 ? raw : `…${raw.slice(-10)}`
}

function isTerminalOutcome(data: Record<string, unknown>): boolean {
  if (data.is_final === true) return true
  const t = String(data.terminality ?? '')
  return t.includes('terminal')
}

export const useIntentSignalsStore = defineStore('intentSignals', () => {
  const byEspId = ref<Record<string, IntentSignalsDisplay>>({})

  const displayForSelectedEsp = computed(() => (espId: string) => byEspId.value[espId] ?? null)

  function ingestLifecycle(data: Record<string, unknown>, messageCorrelationId?: string): void {
    const espId = (typeof data.esp_id === 'string' && data.esp_id) || ''
    if (!espId) return
    const prev = byEspId.value[espId]
    if (prev?.hasTerminalResult) return

    const eventType = String(data.event_type ?? '')
    const reason = String(data.reason_code ?? '')
    const line = `Zwischenstand (Konfiguration): ${eventType}${reason ? ` — ${reason}` : ''}`

    const boot = typeof data.boot_sequence_id === 'string' ? data.boot_sequence_id : undefined
    byEspId.value = {
      ...byEspId.value,
      [espId]: {
        correlationShort: shortId(messageCorrelationId, boot),
        lifecycleSummary: line,
        resultSummary: prev?.resultSummary ?? null,
        firmwareCode: prev?.firmwareCode ?? null,
        hasTerminalResult: prev?.hasTerminalResult ?? false,
        updatedAt: Date.now(),
      },
    }
  }

  function ingestOutcome(data: Record<string, unknown>): void {
    const espId = (typeof data.esp_id === 'string' && data.esp_id) || ''
    if (!espId) return

    const flow = String(data.flow ?? '')
    const outcome = String(data.outcome ?? '')
    const codeRaw = data.code
    const code = codeRaw != null && String(codeRaw).trim().length > 0 ? String(codeRaw) : null
    const reason = typeof data.reason === 'string' && data.reason.trim() ? data.reason.trim() : ''
    const cid = typeof data.correlation_id === 'string' ? data.correlation_id : undefined
    const iid = typeof data.intent_id === 'string' ? data.intent_id : undefined

    const terminal = isTerminalOutcome(data)
    const resultLine =
      flow === 'config' && outcome === 'rejected'
        ? `Konfiguration abgelehnt${code ? ` (${code})` : ''}${reason ? ` — ${reason}` : ''}`
        : `Ergebnis: ${flow || '?'}/${outcome || '?'}${reason ? ` — ${reason}` : ''}`

    const prev = byEspId.value[espId]
    const next: IntentSignalsDisplay = {
      correlationShort: shortId(cid, iid),
      lifecycleSummary: terminal ? null : (prev?.lifecycleSummary ?? null),
      resultSummary: terminal ? resultLine : (prev?.resultSummary ?? resultLine),
      firmwareCode: code,
      hasTerminalResult: terminal,
      updatedAt: Date.now(),
    }

    byEspId.value = { ...byEspId.value, [espId]: next }
  }

  function getDisplayForEsp(espId: string): IntentSignalsDisplay | null {
    return byEspId.value[espId] ?? null
  }

  /** Session-Reset (z. B. Logout) */
  function clearAll(): void {
    byEspId.value = {}
  }

  return {
    byEspId,
    displayForSelectedEsp,
    ingestLifecycle,
    ingestOutcome,
    getDisplayForEsp,
    clearAll,
  }
})
