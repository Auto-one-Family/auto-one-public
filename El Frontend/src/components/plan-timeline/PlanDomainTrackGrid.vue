<script setup lang="ts">
/**
 * Operator domain rows (Luft / Wasser / Boden / Licht / Pflanze)
 * for the consolidated zone timeline.
 */

import { computed } from 'vue'
import type {
  PlanDomainRowModel,
  PlanTimelineWindow,
  PlanTrackBand,
} from '@/components/plan-timeline/planTimelineTracks'
import { nowMarkerPercent } from '@/components/plan-timeline/planTimelineTracks'
import type { PlanMeasureMarker } from '@/components/plan-timeline/planMeasureMarkers'
import type { PlanVpdOverlayBand } from '@/components/plan-timeline/planVpdOverlay'

interface Props {
  rows: PlanDomainRowModel[]
  window: PlanTimelineWindow
  markers: PlanMeasureMarker[]
  /** VPD bands render inside the Luft track (not a separate row). */
  vpdBands?: PlanVpdOverlayBand[]
}

const props = withDefaults(defineProps<Props>(), {
  vpdBands: () => [],
})

const emit = defineEmits<{
  selectMeasure: [marker: PlanMeasureMarker]
}>()

const nowPct = computed(() => nowMarkerPercent(props.window))

function bandStyle(band: PlanTrackBand): Record<string, string> {
  return {
    left: `${band.leftPct}%`,
    width: `${band.widthPct}%`,
    '--band-lane': String(band.laneIndex ?? 0),
  }
}

function vpdStyle(band: PlanVpdOverlayBand, laneIndex: number): Record<string, string> {
  return {
    left: `${band.leftPct}%`,
    width: `${band.widthPct}%`,
    '--band-lane': String(laneIndex),
  }
}

/** Climate lanes + optional VPD lane for Luft. */
function laneCount(row: PlanDomainRowModel): number {
  const base = Math.max(1, row.track?.laneCount ?? 1)
  if (row.key === 'luft' && props.vpdBands.length > 0) {
    const climateEmpty = !row.track || row.track.isEmpty
    // VPD alone still needs one lane; with climate it sits on the next lane.
    return climateEmpty ? 1 : base + 1
  }
  return base
}

function vpdLaneIndex(row: PlanDomainRowModel): number {
  if (!row.track || row.track.isEmpty) return 0
  return Math.max(1, row.track.laneCount)
}

function isLuftBarEmpty(row: PlanDomainRowModel): boolean {
  const noClimate = !row.track || row.track.isEmpty
  const noVpd = row.key !== 'luft' || props.vpdBands.length === 0
  return noClimate && noVpd
}

function onMarkerClick(marker: PlanMeasureMarker): void {
  if (marker.eventStatus === 'reverted') return
  emit('selectMeasure', marker)
}

function markerTitle(m: PlanMeasureMarker): string {
  const note = m.notes ? ` — ${m.notes}` : ''
  if (m.visualState === 'withdrawn') return `${m.label}${note}\nZurückgenommen`
  if (m.visualState === 'ghosted') {
    return `${m.label}${note}\nGeplant, bisher nicht eingetreten`
  }
  return `${m.label}${note}`
}
</script>

<template>
  <div class="domain-grid" aria-label="Planungs-Tracks">
    <template v-for="row in rows" :key="row.key">
      <div class="domain-grid__row" :aria-label="row.label">
        <div class="domain-grid__meta">
          <span class="domain-grid__label">{{ row.label }}</span>
        </div>

        <!-- Segment tracks: Luft / Wasser (VPD inside Luft) -->
        <div
          v-if="row.kind === 'segments' && row.track"
          class="domain-grid__bar"
          :style="{ '--lane-count': String(laneCount(row)) }"
        >
          <div
            class="domain-grid__now"
            :style="{ left: nowPct + '%' }"
            aria-hidden="true"
          />
          <div v-if="isLuftBarEmpty(row)" class="domain-grid__empty">
            kein Plan-Segment
          </div>
          <div
            v-for="band in row.track.bands"
            :key="band.id"
            class="domain-grid__band"
            :class="{
              'domain-grid__band--ghosted': band.visualState === 'ghosted',
              'domain-grid__band--withdrawn': band.visualState === 'withdrawn',
            }"
            :data-measure="band.measure"
            :style="bandStyle(band)"
            :title="band.tooltip"
          >
            <span class="domain-grid__band-label">{{ band.label }}</span>
            <span
              v-if="band.pastDelta?.fromAppliedLog"
              class="domain-grid__delta"
            >
              Δ {{ band.pastDelta.deltaDisplay }}
            </span>
          </div>
          <div
            v-for="band in row.key === 'luft' ? vpdBands : []"
            :key="band.id"
            class="domain-grid__band domain-grid__band--vpd"
            :class="{
              'domain-grid__band--vpd-ok': band.computable,
              'domain-grid__band--vpd-gap': !band.computable,
            }"
            :style="vpdStyle(band, vpdLaneIndex(row))"
            :title="band.tooltip"
          >
            <span class="domain-grid__band-label">{{ band.label }}</span>
          </div>
        </div>

        <!-- Empty placeholders: Boden / Licht -->
        <div v-else-if="row.kind === 'empty'" class="domain-grid__bar domain-grid__bar--empty">
          <div
            class="domain-grid__now"
            :style="{ left: nowPct + '%' }"
            aria-hidden="true"
          />
          <span class="domain-grid__empty">{{ row.emptyHint }}</span>
        </div>

        <!-- Plant measures -->
        <div v-else class="domain-grid__bar domain-grid__bar--measures">
          <div
            class="domain-grid__now"
            :style="{ left: nowPct + '%' }"
            aria-hidden="true"
          />
          <div v-if="markers.length === 0" class="domain-grid__empty">
            keine Maßnahmen
          </div>
          <button
            v-for="m in markers"
            :key="m.eventId"
            type="button"
            class="domain-grid__measure"
            :class="{
              'domain-grid__measure--range': m.widthPct > 0,
              'domain-grid__measure--ghosted': m.visualState === 'ghosted',
              'domain-grid__measure--withdrawn': m.visualState === 'withdrawn',
            }"
            :style="m.widthPct > 0
              ? { left: m.leftPct + '%', width: Math.max(m.widthPct, 2) + '%', transform: 'translateY(-50%)' }
              : { left: m.leftPct + '%' }"
            :title="markerTitle(m)"
            :aria-label="`Maßnahme ${m.label}`"
            :disabled="m.eventStatus === 'reverted'"
            @click="onMarkerClick(m)"
          >
            {{ m.label }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.domain-grid {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.domain-grid__row {
  display: grid;
  grid-template-columns: minmax(88px, 120px) 1fr;
  gap: var(--space-3);
  align-items: stretch;
  min-height: 36px;
}

.domain-grid__meta {
  display: flex;
  align-items: center;
  min-width: 0;
}

.domain-grid__label {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
}

.domain-grid__bar {
  --lane-h: 22px;
  --lane-pad: 3px;
  --lane-count: 1;
  position: relative;
  min-height: calc(
    var(--lane-count) * var(--lane-h) + 2 * var(--lane-pad)
  );
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  background: var(--color-bg-tertiary);
  overflow: hidden;
}

.domain-grid__bar--empty,
.domain-grid__bar--measures {
  min-height: 36px;
}

.domain-grid__now {
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

.domain-grid__empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.domain-grid__band {
  position: absolute;
  top: calc(
    var(--lane-pad) + (var(--band-lane, 0) * var(--lane-h))
  );
  height: calc(var(--lane-h) - 4px);
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: 0 var(--space-2);
  border-radius: var(--radius-sm);
  background: rgba(129, 140, 248, 0.22);
  border: 1px solid rgba(129, 140, 248, 0.5);
  overflow: hidden;
  z-index: 1;
}

.domain-grid__band[data-measure='target_temperature'],
.domain-grid__band[data-measure='target_humidity'],
.domain-grid__band[data-measure='target_co2'] {
  background: rgba(96, 165, 250, 0.2);
  border-color: rgba(96, 165, 250, 0.55);
}

.domain-grid__band[data-measure='target_ec'],
.domain-grid__band[data-measure='target_ph'],
.domain-grid__band[data-measure='recipe_ref'] {
  background: rgba(167, 139, 250, 0.22);
  border-color: rgba(167, 139, 250, 0.55);
}

.domain-grid__band--ghosted {
  opacity: 0.4;
}

.domain-grid__band--withdrawn {
  opacity: 0.5;
  background: rgba(248, 113, 113, 0.15);
  border-color: rgba(248, 113, 113, 0.45);
}

.domain-grid__band--vpd {
  background: rgba(96, 165, 250, 0.12);
  border: 1px solid rgba(96, 165, 250, 0.4);
}

.domain-grid__band--vpd-ok {
  background: rgba(96, 165, 250, 0.18);
  border-color: rgba(96, 165, 250, 0.5);
}

.domain-grid__band--vpd-gap {
  background: rgba(251, 191, 36, 0.1);
  border: 1px dashed rgba(251, 191, 36, 0.45);
}

.domain-grid__band-label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.domain-grid__delta {
  font-size: var(--text-xs);
  color: var(--color-warning);
  white-space: nowrap;
}

.domain-grid__measure {
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  z-index: 3;
  max-width: 120px;
  padding: 2px 8px;
  min-height: 28px;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-primary);
  background: rgba(251, 191, 36, 0.18);
  border: 1px solid rgba(251, 191, 36, 0.55);
  border-radius: var(--radius-sm);
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.domain-grid__measure:hover:not(:disabled) {
  background: rgba(251, 191, 36, 0.3);
}

.domain-grid__measure--range {
  transform: translateY(-50%);
  background: color-mix(in srgb, var(--color-success) 22%, transparent);
  border-color: color-mix(in srgb, var(--color-success) 55%, transparent);
}

.domain-grid__measure--ghosted {
  opacity: 0.45;
  border-style: dashed;
}

.domain-grid__measure--withdrawn {
  opacity: 0.55;
  background: rgba(248, 113, 113, 0.15);
  border-color: rgba(248, 113, 113, 0.45);
  cursor: default;
}

.domain-grid__measure:disabled {
  cursor: default;
}
</style>
