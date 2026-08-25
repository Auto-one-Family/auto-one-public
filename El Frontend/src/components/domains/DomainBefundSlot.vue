<script setup lang="ts">
/**
 * DomainBefundSlot — v1 empty anchor for future findings (AUT-1321).
 *
 * Context key = Domäne × Zone/Subzone × Messgröße.
 * Delivers the PLACE for a finding, never an invented finding.
 */

interface Props {
  domainLabel: string
  placeLabel: string
  measureLabel: string
}

defineProps<Props>()
</script>

<template>
  <div
    class="rounded-md border border-dashed border-dark-600 bg-dark-900/40 px-3 py-2"
    role="status"
    :aria-label="`Befund-Slot ${domainLabel} · ${placeLabel} · ${measureLabel}`"
  >
    <p class="text-xs text-dark-300">
      {{ domainLabel }} · {{ placeLabel }} · {{ measureLabel }}
    </p>
    <p class="mt-1 text-sm text-dark-200">
      Noch keine Befunde · Auswertung folgt
    </p>
  </div>
</template>
