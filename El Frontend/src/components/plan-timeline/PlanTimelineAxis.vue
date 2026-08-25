<script setup lang="ts">
/**
 * PlanTimelineAxis — Date tick rail with "heute" seam for Planungs-Zeitstrahl.
 */

import { computed } from 'vue'
import type { PlanTimelineWindow } from '@/components/plan-timeline/planTimelineTracks'
import {
  buildPlanDateTicks,
  nowMarkerPercent,
} from '@/components/plan-timeline/planTimelineTracks'

interface Props {
  window: PlanTimelineWindow
}

const props = defineProps<Props>()

const nowPct = computed(() => nowMarkerPercent(props.window))
const ticks = computed(() => buildPlanDateTicks(props.window))
</script>

<template>
  <div class="plan-axis" role="img" aria-label="Zeitachse mit Datumseinteilung">
    <div class="plan-axis__rail">
      <div class="plan-axis__past" :style="{ width: nowPct + '%' }" />
      <div class="plan-axis__future" :style="{ width: 100 - nowPct + '%' }" />
      <div
        class="plan-axis__now"
        :style="{ left: nowPct + '%' }"
        title="heute"
        aria-hidden="true"
      />
      <div
        v-for="(tick, idx) in ticks"
        :key="`${tick.ms}-${idx}`"
        class="plan-axis__tick"
        :class="{ 'plan-axis__tick--today': tick.isToday }"
        :style="{ left: tick.leftPct + '%' }"
        aria-hidden="true"
      />
    </div>
    <div class="plan-axis__labels">
      <span
        v-for="(tick, idx) in ticks"
        :key="`label-${tick.ms}-${idx}`"
        class="plan-axis__label"
        :class="{ 'plan-axis__label--today': tick.isToday }"
        :style="{ left: tick.leftPct + '%' }"
      >
        {{ tick.label }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.plan-axis {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  width: 100%;
  min-width: 0;
}

.plan-axis__rail {
  position: relative;
  display: flex;
  height: 6px;
  border-radius: var(--radius-full);
  overflow: visible;
  background: var(--color-bg-tertiary);
}

.plan-axis__past {
  height: 100%;
  border-radius: var(--radius-full) 0 0 var(--radius-full);
  background: rgba(96, 165, 250, 0.25);
}

.plan-axis__future {
  height: 100%;
  border-radius: 0 var(--radius-full) var(--radius-full) 0;
  background: rgba(167, 139, 250, 0.18);
}

.plan-axis__now {
  position: absolute;
  top: -3px;
  bottom: -3px;
  width: 2px;
  margin-left: -1px;
  background: var(--color-accent);
  box-shadow: 0 0 6px var(--color-accent);
  z-index: 2;
}

.plan-axis__tick {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  margin-left: -0.5px;
  background: var(--color-text-muted);
  opacity: 0.35;
  z-index: 1;
}

.plan-axis__tick--today {
  opacity: 0;
}

.plan-axis__labels {
  position: relative;
  height: 1.25rem;
}

.plan-axis__label {
  position: absolute;
  transform: translateX(-50%);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.plan-axis__label--today {
  color: var(--color-accent);
  font-weight: 600;
}
</style>
