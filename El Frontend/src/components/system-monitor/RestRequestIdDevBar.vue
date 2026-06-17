<script setup lang="ts">
/**
 * Dev-only: zuletzt von der REST-Schicht gelieferte X-Request-ID (Server-Antwort),
 * für Korrelation mit Server-Logs / WS — keine PII, nur technische UUID.
 */
import { computed } from 'vue'
import { useLastServerRequestId } from '@/utils/lastRestRequestId'

const isDev = import.meta.env.DEV
const lastId = useLastServerRequestId()
const display = computed(() => lastId.value ?? '—')
</script>

<template>
  <div
    v-if="isDev"
    class="flex flex-wrap items-center gap-2 border-b border-[var(--glass-border-l1)] bg-[var(--color-bg-tertiary)] px-3 py-1.5 text-xs text-[var(--color-text-muted)]"
    role="status"
    aria-label="Letzte REST-Antwort Request-ID (nur Entwicklungsmodus)"
  >
    <span class="font-medium text-[var(--color-text-secondary)]">Letzte X-Request-ID (REST)</span>
    <code
      class="max-w-full truncate rounded bg-[var(--color-bg-quaternary)] px-1.5 py-0.5 font-mono text-[11px] text-[var(--color-text-primary)]"
      :title="display === '—' ? '' : display"
    >{{ display }}</code>
  </div>
</template>
