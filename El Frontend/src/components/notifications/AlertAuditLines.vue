<script setup lang="ts">
/**
 * AlertAuditLines — ISA-18.2–Audit: Ack (Zeit + optional User-ID), Resolve nur Zeit.
 * Kein resolved_by in der API/DB (AUT-196 Paket D).
 */
import { formatRelativeTime, formatDateTime } from '@/utils/formatters'

interface Props {
  acknowledgedAt?: string | null
  acknowledgedBy?: number | null
  resolvedAt?: string | null
}

defineProps<Props>()
</script>

<template>
  <div class="alert-audit">
    <div v-if="acknowledgedAt" class="alert-audit__row alert-audit__row--full">
      <span class="alert-audit__label">Bestätigt</span>
      <span
        class="alert-audit__value"
        :title="formatDateTime(acknowledgedAt)"
      >
        am {{ formatDateTime(acknowledgedAt) }}
        <template v-if="acknowledgedBy != null">
          von User-ID {{ acknowledgedBy }}
        </template>
        <span class="alert-audit__relative">
          ({{ formatRelativeTime(acknowledgedAt) }})
        </span>
      </span>
    </div>
    <div v-if="resolvedAt" class="alert-audit__row alert-audit__row--full">
      <span class="alert-audit__label">Erledigt</span>
      <span
        class="alert-audit__value"
        :title="formatDateTime(resolvedAt)"
      >
        am {{ formatDateTime(resolvedAt) }}
        <span class="alert-audit__relative">
          ({{ formatRelativeTime(resolvedAt) }})
        </span>
      </span>
    </div>
  </div>
</template>

<style scoped>
/**
 * Volle Breite im Drawer-Grid sowie im FAB-Flex (flex-wrap): neue Zeile oben.
 */
.alert-audit {
  width: 100%;
  flex-basis: 100%;
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-bottom: var(--space-1);
}

.alert-audit__row {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.alert-audit__label {
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.alert-audit__value {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  font-family: var(--font-mono);
}

.alert-audit__relative {
  margin-left: var(--space-1);
  color: var(--color-text-muted);
}
</style>
