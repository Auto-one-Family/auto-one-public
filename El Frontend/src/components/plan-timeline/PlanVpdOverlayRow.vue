<script setup lang="ts">
/**
 * Read-only VPD-Zielband overlay under a Raumklima track (AUT-1240).
 * Physically separate from Ist-Telemetrie / past-overlay (UX-6).
 * Never emits edit/resize/split.
 */

import { computed } from 'vue'
import type { PlanTimelineWindow } from '@/components/plan-timeline/planTimelineTracks'
import { nowMarkerPercent } from '@/components/plan-timeline/planTimelineTracks'
import type { PlanVpdOverlayBand } from '@/components/plan-timeline/planVpdOverlay'

interface Props {
  bands: PlanVpdOverlayBand[]
  window: PlanTimelineWindow
}

const props = defineProps<Props>()

const nowPct = computed(() => nowMarkerPercent(props.window))
</script>

<template>
  <div
    class="vpd-overlay"
    aria-label="VPD-Zielband abgeleitet — nur Anzeige"
  >
    <div class="vpd-overlay__meta">
      <span class="vpd-overlay__title">VPD-Zielband</span>
      <span class="vpd-overlay__sub">abgeleitet · nur Anzeige</span>
    </div>
    <div class="vpd-overlay__bar" role="img" aria-label="VPD-Zielband Overlay">
      <div
        class="vpd-overlay__now"
        :style="{ left: nowPct + '%' }"
        aria-hidden="true"
      />
      <div v-if="bands.length === 0" class="vpd-overlay__empty">
        kein VPD-Band (Temperatur- und Feuchte-Ziel im Fenster nötig)
      </div>
      <div
        v-for="band in bands"
        :key="band.id"
        class="vpd-overlay__band"
        :class="{
          'vpd-overlay__band--ok': band.computable,
          'vpd-overlay__band--gap': !band.computable,
        }"
        :style="{ left: band.leftPct + '%', width: band.widthPct + '%' }"
        :title="band.tooltip"
      >
        <span class="vpd-overlay__band-label">{{ band.label }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.vpd-overlay {
  display: grid;
  /* Align meta/bar with PlanTimelineTrackRow + PlanMeasureMarkerRow */
  grid-template-columns: minmax(88px, 120px) 1fr;
  gap: var(--space-3);
  align-items: stretch;
  /* Distinct from editable tracks + past-overlay telemetry */
  opacity: 0.95;
}

.vpd-overlay__meta {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  padding-left: var(--space-1);
}

.vpd-overlay__title {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
}

.vpd-overlay__sub {
  font-size: 10px;
  color: var(--color-text-muted);
}

.vpd-overlay__bar {
  position: relative;
  min-height: 28px;
  border-radius: var(--radius-sm);
  border: 1px dashed var(--glass-border);
  background: color-mix(in srgb, var(--color-bg-tertiary) 80%, transparent);
  overflow: hidden;
}

.vpd-overlay__now {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: var(--color-info);
  z-index: 2;
  pointer-events: none;
}

.vpd-overlay__empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-style: italic;
  pointer-events: none;
}

.vpd-overlay__band {
  position: absolute;
  top: 3px;
  bottom: 3px;
  display: flex;
  align-items: center;
  overflow: hidden;
  border-radius: var(--radius-sm);
  pointer-events: none;
  cursor: default;
}

.vpd-overlay__band--ok {
  background: color-mix(in srgb, var(--color-info) 22%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-info) 45%, transparent);
}

.vpd-overlay__band--gap {
  background: color-mix(in srgb, var(--color-warning) 14%, transparent);
  border: 1px dashed color-mix(in srgb, var(--color-warning) 40%, transparent);
}

.vpd-overlay__band-label {
  padding: 0 var(--space-2);
  font-size: 10px;
  font-weight: 500;
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
