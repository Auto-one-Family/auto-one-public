<script setup lang="ts">
/**
 * DomainGapBanner — actionable gap exactly once (AUT-1321).
 *
 * Neutral empty ≠ gap. This banner is only for incomplete assignment
 * (device without domain, or Wasser device without tank).
 * One primary action → existing config via ?openSettings=.
 */

import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { AlertTriangle } from 'lucide-vue-next'

export interface DomainGapItem {
  deviceId: string
  deviceName: string
  kind: 'missing_domain' | 'wasser_without_tank'
}

interface Props {
  gaps: DomainGapItem[]
}

const props = defineProps<Props>()
const router = useRouter()

const primary = computed(() => props.gaps[0] ?? null)

const message = computed(() => {
  if (!primary.value) return ''
  const count = props.gaps.length
  if (primary.value.kind === 'wasser_without_tank') {
    return count === 1
      ? `„${primary.value.deviceName}“ ist der Domäne Wasser zugeordnet, hat aber keinen Tank.`
      : `${count} Zuordnungen sind unvollständig (Domäne oder Tank fehlt).`
  }
  return count === 1
    ? `„${primary.value.deviceName}“ hat noch keine Domäne.`
    : `${count} Geräte haben noch keine Domäne oder Tank-Zuordnung.`
})

function openSettings(): void {
  if (!primary.value) return
  void router.push({
    name: 'hardware',
    query: { openSettings: primary.value.deviceId },
  })
}
</script>

<template>
  <div
    v-if="primary"
    class="flex flex-wrap items-center justify-between gap-3 rounded-md border border-[var(--color-warning)] bg-[color-mix(in_srgb,var(--color-warning)_12%,transparent)] p-4"
    role="status"
    aria-label="Fehlende Domänen-Zuordnung"
  >
    <div class="flex min-w-0 flex-1 items-start gap-3">
      <AlertTriangle
        class="mt-0.5 h-5 w-5 shrink-0 text-[var(--color-warning)]"
        aria-hidden="true"
      />
      <div class="min-w-0">
        <p class="m-0 text-sm font-semibold text-[var(--color-text-primary)]">
          Zuordnung unvollständig
        </p>
        <p class="mt-1 text-sm text-[var(--color-text-secondary)]">
          {{ message }}
        </p>
      </div>
    </div>
    <button
      type="button"
      class="btn-primary shrink-0"
      aria-label="In Geräte-Einstellungen setzen"
      @click="openSettings"
    >
      In Einstellungen setzen
    </button>
  </div>
</template>
