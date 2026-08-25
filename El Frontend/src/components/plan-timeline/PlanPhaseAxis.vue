<script setup lang="ts">
/**
 * Upper plant-phase axis for the consolidated Planungs-Zeitstrahl.
 * One row per cohort; shared time scale with domain tracks below.
 */

import type { PlanCohortPhaseTrack } from '@/components/plan-timeline/planCohorts'
import type { PlanTimelineWindow } from '@/components/plan-timeline/planTimelineTracks'
import { nowMarkerPercent } from '@/components/plan-timeline/planTimelineTracks'
import { computed } from 'vue'

interface Props {
  tracks: PlanCohortPhaseTrack[]
  window: PlanTimelineWindow
  /** Shown when the zone has no plants / no cohorts. */
  emptyHint?: string
}

const props = withDefaults(defineProps<Props>(), {
  emptyHint: 'Keine Pflanzen in dieser Zone',
})

const nowPct = computed(() => nowMarkerPercent(props.window))
const showCohortLabels = computed(() => props.tracks.length > 1)
</script>

<template>
  <div class="phase-axis" aria-label="Pflanzenphasen">
    <div v-if="tracks.length === 0" class="phase-axis__empty">
      {{ emptyHint }}
    </div>
    <div
      v-for="track in tracks"
      :key="track.id"
      class="phase-axis__row"
    >
      <div class="phase-axis__meta">
        <span class="phase-axis__meta-title">Phasen</span>
        <span
          v-if="showCohortLabels"
          class="phase-axis__meta-sub"
          :title="track.label"
        >
          {{ track.label }}
        </span>
      </div>
      <div class="phase-axis__bar" :aria-label="`Phasen · ${track.label}`">
        <div
          class="phase-axis__now"
          :style="{ left: nowPct + '%' }"
          aria-hidden="true"
        />
        <div v-if="track.isEmpty" class="phase-axis__bar-empty">
          keine Licht-/Wachstumsphasen
        </div>
        <div
          v-for="band in track.bands"
          :key="band.id"
          class="phase-axis__band"
          :style="{ left: band.leftPct + '%', width: band.widthPct + '%' }"
          :title="band.tooltip"
        >
          <span class="phase-axis__band-label">{{ band.label }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.phase-axis {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.phase-axis__empty {
  padding: var(--space-3);
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  text-align: center;
}

.phase-axis__row {
  display: grid;
  grid-template-columns: minmax(88px, 120px) 1fr;
  gap: var(--space-3);
  align-items: stretch;
  min-height: 36px;
}

.phase-axis__meta {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  min-width: 0;
}

.phase-axis__meta-title {
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-text-muted);
}

.phase-axis__meta-sub {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.phase-axis__bar {
  position: relative;
  min-height: 36px;
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  background: var(--color-bg-tertiary);
  overflow: hidden;
}

.phase-axis__now {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  margin-left: -1px;
  background: var(--color-accent);
  opacity: 0.7;
  z-index: 2;
  pointer-events: none;
}

.phase-axis__bar-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 36px;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.phase-axis__band {
  position: absolute;
  top: 4px;
  bottom: 4px;
  display: flex;
  align-items: center;
  padding: 0 var(--space-2);
  border-radius: var(--radius-sm);
  background: rgba(96, 165, 250, 0.22);
  border: 1px solid rgba(96, 165, 250, 0.55);
  overflow: hidden;
  z-index: 1;
}

.phase-axis__band-label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
