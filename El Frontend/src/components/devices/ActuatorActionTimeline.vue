<script setup lang="ts">
/**
 * ActuatorActionTimeline — Last N switching events for an actuator (AUT-256)
 *
 * Datenquelle (bevorzugt): GET /api/v1/actuators/{esp_id}/{gpio}/history
 *   → ActuatorHistoryEntry[] mit timestamp, command_type, value, issued_by, success.
 * Keine Server-Aenderung erforderlich; Endpoint existiert bereits (P8-A6b).
 *
 * Anzeige (max 5):
 *   2026-05-05 14:23  AN   Heizungs-Hysterese (priority 50)
 *   2026-05-05 14:00  AN   Robin (manuell, priority -1000)
 *
 * Trigger-Quelle wird best-effort aus issued_by/metadata abgeleitet:
 *   - issued_by === 'logic' / 'rule' → Regelname aus metadata.rule_name + priority
 *   - issued_by sieht aus wie User → "<user> (manuell, priority -1000)"
 *   - 'system'/'safety' → "System / Safety"
 *   - leer → "—"
 *
 * Ladeverhalten:
 *   - onMounted: load()
 *   - bei (espId, gpio)-Wechsel: reload via watch
 *   - AbortController, kein Polling (Lifecycle-Updates kommen via WS in das Logic-Store-Lifecycle,
 *     aber operative History wird bewusst beim Oeffnen des Panels frisch geholt).
 */
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { History } from 'lucide-vue-next'
import { actuatorsApi } from '@/api/actuators'
import type { ActuatorHistoryEntry } from '@/api/actuators'
import { isActuatorOn } from '@/composables/useActuatorHistory'
import { formatDateTime } from '@/utils/formatters'

interface Props {
  espId: string
  gpio: number
  limit?: number
}

const props = withDefaults(defineProps<Props>(), {
  limit: 5,
})

const entries = ref<ActuatorHistoryEntry[]>([])
const isLoading = ref(false)
const error = ref<string | null>(null)
let abortCtrl: AbortController | null = null

// =============================================================================
// Trigger source resolution
// =============================================================================

interface TriggerLabel {
  /** Short label rendered after the state (e.g. "Heizungs-Hysterese") */
  label: string
  /** Optional suffix in parentheses, e.g. "(priority 50)" or "(manuell, priority -1000)" */
  suffix?: string
}

const SYSTEM_SOURCES = new Set(['system', 'safety', 'safety_manager', 'auto', 'autoops', 'state_sync'])
const RULE_SOURCES = new Set(['logic', 'rule', 'logic_engine', 'rule_engine'])

function resolveTrigger(entry: ActuatorHistoryEntry): TriggerLabel {
  const meta = entry.metadata ?? {}
  const issuedBy = (entry.issued_by ?? '').trim()
  const issuedByLower = issuedBy.toLowerCase()

  const ruleName = typeof meta.rule_name === 'string' ? meta.rule_name : null

  // Logic engine / rule trigger — also handles "logic:UUID" prefix form
  if (RULE_SOURCES.has(issuedByLower) || issuedByLower.startsWith('logic:') || ruleName) {
    return { label: ruleName ?? 'Automatikregel' }
  }

  // ESP confirmation response
  if (issuedByLower.startsWith('esp32_resp') || issuedByLower.startsWith('esp_resp')) {
    return { label: 'ESP-Bestätigung' }
  }

  // state_sync and other system sources
  if (issuedByLower === 'state_sync') return { label: 'Statusabgleich' }
  if (SYSTEM_SOURCES.has(issuedByLower)) return { label: 'System' }

  // Manual user command
  if (issuedBy.length > 0) {
    return { label: 'Manuell' }
  }

  return { label: '—' }
}

function formatStateBadge(entry: ActuatorHistoryEntry): { text: string; on: boolean } {
  const on = isActuatorOn(entry)
  const cmd = (entry.command_type ?? '').toLowerCase()
  if (cmd === 'pwm' || cmd === 'set') {
    if (on) return { text: 'AN', on: true }
    return { text: 'AUS', on: false }
  }
  if (cmd === 'emergency_stop') return { text: 'STOPP', on: false }
  return { text: on ? 'AN' : 'AUS', on }
}

// =============================================================================
// Loader
// =============================================================================

async function load(): Promise<void> {
  if (abortCtrl) abortCtrl.abort()
  abortCtrl = new AbortController()
  isLoading.value = true
  error.value = null
  try {
    const res = await actuatorsApi.getHistory(
      props.espId,
      props.gpio,
      { limit: props.limit, include_aggregation: false },
      abortCtrl.signal,
    )
    // Server returns chronological-asc or -desc depending on backend; sort defensively.
    entries.value = (res.entries ?? [])
      .slice()
      .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
      .slice(0, props.limit)
  } catch (e: unknown) {
    if ((e as { name?: string })?.name === 'AbortError') return
    const msg = e instanceof Error ? e.message : 'Unbekannter Fehler'
    error.value = msg
    entries.value = []
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  load()
})

watch(
  () => [props.espId, props.gpio] as const,
  () => {
    load()
  },
)

onUnmounted(() => {
  if (abortCtrl) abortCtrl.abort()
})
</script>

<template>
  <div class="action-timeline">
    <div v-if="isLoading && entries.length === 0" class="action-timeline__loading">
      Lade Verlauf…
    </div>

    <div v-else-if="error" class="action-timeline__error" role="alert">
      Verlauf konnte nicht geladen werden: {{ error }}
    </div>

    <div v-else-if="entries.length === 0" class="action-timeline__empty">
      <History class="w-5 h-5" style="color: var(--color-text-muted)" />
      <p class="action-timeline__empty-text">Noch keine Schaltvorgänge protokolliert</p>
    </div>

    <ol v-else class="action-timeline__list">
      <li
        v-for="entry in entries"
        :key="entry.id"
        class="action-timeline__item"
      >
        <span class="action-timeline__time">
          {{ formatDateTime(entry.timestamp) }}
        </span>
        <span
          :class="[
            'action-timeline__state',
            formatStateBadge(entry).on
              ? 'action-timeline__state--on'
              : 'action-timeline__state--off',
          ]"
        >
          {{ formatStateBadge(entry).text }}
        </span>
        <span class="action-timeline__source">
          <span class="action-timeline__source-label">{{ resolveTrigger(entry).label }}</span>
          <span
            v-if="resolveTrigger(entry).suffix"
            class="action-timeline__source-suffix"
          >
            ({{ resolveTrigger(entry).suffix }})
          </span>
        </span>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.action-timeline {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.action-timeline__loading,
.action-timeline__error,
.action-timeline__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-3);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  text-align: center;
}

.action-timeline__error {
  color: var(--color-warning);
}

.action-timeline__empty {
  flex-direction: column;
}

.action-timeline__empty-text {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.action-timeline__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.action-timeline__item {
  display: grid;
  grid-template-columns: minmax(0, auto) auto minmax(0, 1fr);
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-xs);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  font-size: var(--text-xs);
}

.action-timeline__time {
  font-family: var(--font-mono);
  color: var(--color-text-muted);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.action-timeline__state {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 38px;
  padding: 1px 6px;
  border-radius: var(--radius-xs);
  font-weight: 700;
  letter-spacing: 0.04em;
  font-size: var(--text-xxs);
}

.action-timeline__state--on {
  color: var(--color-success);
  background: color-mix(in srgb, var(--color-success) 12%, transparent);
}

.action-timeline__state--off {
  color: var(--color-text-muted);
  background: var(--color-bg-quaternary, rgba(255, 255, 255, 0.04));
}

.action-timeline__source {
  display: flex;
  align-items: baseline;
  gap: var(--space-1);
  min-width: 0;
  overflow: hidden;
}

.action-timeline__source-label {
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.action-timeline__source-suffix {
  color: var(--color-text-muted);
  white-space: nowrap;
}
</style>
