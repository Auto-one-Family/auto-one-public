<script setup lang="ts">
/**
 * HealthProblemChip - Clickable chip showing a problem ESP device
 *
 * Displays device name, problem type badge, and detail info.
 * Click navigates to filtered event view for that device.
 */

import { computed } from 'vue'
import { ExternalLink } from 'lucide-vue-next'
import type { FleetHealthDevice } from '@/api/health'
import { formatRelativeTime } from '@/utils/formatters'

export type ProblemType = 'offline' | 'low-heap' | 'weak-signal' | 'high-errors'

interface Props {
  device: FleetHealthDevice
  problemType: ProblemType
}

const props = defineProps<Props>()

defineEmits<{
  click: [espId: string]
}>()

const problemLabel = computed(() => {
  switch (props.problemType) {
    case 'offline': return 'Offline'
    case 'low-heap': return 'Heap kritisch'
    case 'weak-signal': return 'Signal schwach'
    case 'high-errors': return 'Fehlerrate hoch'
  }
})

const detailText = computed(() => {
  const d = props.device
  switch (props.problemType) {
    case 'offline':
      return d.last_seen ? `Letzter Kontakt: ${formatRelativeTime(d.last_seen)}` : 'Nie gesehen'
    case 'low-heap':
      return d.heap_free != null ? `Freier Heap: ${Math.round(d.heap_free / 1024)} KB` : '—'
    case 'weak-signal':
      return d.wifi_rssi != null ? `Signal: ${d.wifi_rssi} dBm` : '—'
    case 'high-errors':
      return 'Hohe Fehlerrate'
  }
})

const displayName = computed(() =>
  props.device.name || props.device.device_id
)

</script>

<template>
  <button
    class="problem-chip"
    :class="[`problem-chip--${problemType}`]"
    @click="$emit('click', device.device_id)"
  >
    <span class="problem-chip__dot" />
    <div class="problem-chip__content">
      <span class="problem-chip__name">{{ displayName }}</span>
      <span class="problem-chip__status">{{ problemLabel }}</span>
      <span class="problem-chip__detail">{{ detailText }}</span>
    </div>
    <ExternalLink :size="12" class="problem-chip__icon" />
  </button>
</template>

<style scoped>
.problem-chip {
  display: inline-flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border-radius: var(--radius-md);
  font-size: 0.8125rem;
  cursor: pointer;
  transition: all 0.15s ease;
  border: 1px solid;
  background: none;
  font-family: inherit;
  text-align: left;
}

.problem-chip__content {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.problem-chip__dot {
  flex-shrink: 0;
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  margin-top: 0.25rem;
}

/* Offline */
.problem-chip--offline {
  background: rgba(248, 113, 113, 0.08);
  border-color: rgba(248, 113, 113, 0.2);
}

.problem-chip--offline:hover {
  background: rgba(248, 113, 113, 0.15);
  border-color: rgba(248, 113, 113, 0.35);
  transform: translateY(-1px);
}

.problem-chip--offline .problem-chip__dot {
  background: var(--color-error);
}

.problem-chip--offline .problem-chip__status {
  color: var(--color-error);
}

/* Warning types */
.problem-chip--low-heap,
.problem-chip--weak-signal,
.problem-chip--high-errors {
  background: rgba(251, 191, 36, 0.08);
  border-color: rgba(251, 191, 36, 0.2);
}

.problem-chip--low-heap:hover,
.problem-chip--weak-signal:hover,
.problem-chip--high-errors:hover {
  background: rgba(251, 191, 36, 0.15);
  border-color: rgba(251, 191, 36, 0.35);
  transform: translateY(-1px);
}

.problem-chip--low-heap .problem-chip__dot,
.problem-chip--weak-signal .problem-chip__dot,
.problem-chip--high-errors .problem-chip__dot {
  background: var(--color-warning);
}

.problem-chip--low-heap .problem-chip__status,
.problem-chip--weak-signal .problem-chip__status,
.problem-chip--high-errors .problem-chip__status {
  color: var(--color-warning);
}

.problem-chip__name {
  font-weight: 500;
  color: var(--color-text-primary);
}

.problem-chip__status {
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.problem-chip__detail {
  color: var(--color-text-muted);
  font-size: 0.75rem;
}

.problem-chip__icon {
  flex-shrink: 0;
  opacity: 0;
  color: var(--color-text-muted);
  margin-top: 0.25rem;
  transition: opacity 0.15s;
}

.problem-chip:hover .problem-chip__icon {
  opacity: 1;
}
</style>
