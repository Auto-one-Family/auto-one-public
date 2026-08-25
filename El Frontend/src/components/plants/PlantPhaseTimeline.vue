<script setup lang="ts">
/**
 * PlantPhaseTimeline — Master axis + In-Phase layers (AUT-1228 / AUT-1240).
 *
 * Master segments come ONLY from Licht-/Wachstumsphase (phase_changed).
 * Nährstoff and Raumklima render as In-Phase chip layers inside the master
 * bar — never as equal-rank second/third timelines.
 *
 * Climate chips use plan_segments (domain=climate) for the plant's zone when
 * provided — no third phase column in the plant data model (AUT-1240 Verbots).
 */

import { computed } from 'vue'
import { getPlantPhaseLabel } from '@/components/plants/plantLabels'
import { formatDate } from '@/utils/formatters'
import { PLAN_MEASURE_LABELS } from '@/components/plan-timeline/planTimelineTracks'
import type { PlantLifecycleEvent } from '@/types'
import type { PlanSegment } from '@/types/planSegment'

interface Props {
  events: PlantLifecycleEvent[]
  /** Optional climate plan_segments (zone-scoped) for Raumklima In-Phase layer. */
  climateSegments?: PlanSegment[]
  /** Plant parent zone — filters climateSegments. */
  zoneId?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  climateSegments: () => [],
  zoneId: null,
})

interface MasterSegment {
  id: string
  label: string
  startMs: number
  endMs: number
  leftPct: number
  widthPct: number
  tooltip: string
  color: string
  borderColor: string
  nutrientChips: LayerChip[]
  climateChips: LayerChip[]
}

interface LayerChip {
  id: string
  label: string
  tooltip: string
  leftPct: number
  widthPct: number
}

const LIGHT_COLORS: [string, string] = [
  'rgba(96, 165, 250, 0.18)',
  'rgba(96, 165, 250, 0.35)',
]
const LIGHT_BORDERS: [string, string] = [
  'rgba(96, 165, 250, 0.55)',
  'rgba(96, 165, 250, 0.80)',
]

function buildMasterRaw(
  axisEvents: PlantLifecycleEvent[],
  nowMs: number,
): Omit<MasterSegment, 'leftPct' | 'widthPct' | 'nutrientChips' | 'climateChips'>[] {
  if (axisEvents.length === 0) return []
  const sorted = [...axisEvents].sort(
    (a, b) => Date.parse(a.event_timestamp) - Date.parse(b.event_timestamp),
  )
  return sorted.map((evt, i) => {
    const startMs = Date.parse(evt.event_timestamp)
    const endMs =
      i < sorted.length - 1 ? Date.parse(sorted[i + 1].event_timestamp) : nowMs
    const phaseValue = evt.new_phase ?? ''
    const label = phaseValue ? getPlantPhaseLabel(phaseValue) : '—'
    const startLabel = formatDate(evt.event_timestamp)
    const endLabel =
      i < sorted.length - 1
        ? formatDate(sorted[i + 1].event_timestamp)
        : 'heute'
    return {
      id: evt.event_id,
      label,
      startMs,
      endMs,
      color: LIGHT_COLORS[i % LIGHT_COLORS.length],
      borderColor: LIGHT_BORDERS[i % LIGHT_BORDERS.length],
      tooltip: `${label}\nVon: ${startLabel}\nBis: ${endLabel}`,
    }
  })
}

function nutrientIntervals(
  events: PlantLifecycleEvent[],
  nowMs: number,
): { id: string; label: string; startMs: number; endMs: number }[] {
  const sorted = [...events].sort(
    (a, b) => Date.parse(a.event_timestamp) - Date.parse(b.event_timestamp),
  )
  return sorted.map((evt, i) => {
    const startMs = Date.parse(evt.event_timestamp)
    const endMs =
      i < sorted.length - 1 ? Date.parse(sorted[i + 1].event_timestamp) : nowMs
    const phaseValue = evt.new_phase ?? ''
    return {
      id: evt.event_id,
      label: phaseValue ? getPlantPhaseLabel(phaseValue) : '—',
      startMs,
      endMs,
    }
  })
}

function climateIntervals(
  segments: PlanSegment[],
  zoneId: string | null | undefined,
  nowMs: number,
): { id: string; label: string; startMs: number; endMs: number }[] {
  if (!zoneId) return []
  const relevant = segments.filter(
    (s) =>
      s.zone_id === zoneId &&
      s.domain === 'climate' &&
      (s.measure === 'target_temperature' || s.measure === 'target_humidity') &&
      s.value != null,
  )
  return relevant
    .map((s) => {
      const startMs = Date.parse(s.from_ts)
      const endMs = s.to_ts ? Date.parse(s.to_ts) : nowMs
      const mLabel = PLAN_MEASURE_LABELS[s.measure] ?? s.measure
      return {
        id: s.id,
        label: `${mLabel} ${s.value}`,
        startMs,
        endMs,
      }
    })
    .filter((x) => !Number.isNaN(x.startMs) && !Number.isNaN(x.endMs) && x.endMs > x.startMs)
    .sort((a, b) => a.startMs - b.startMs)
}

function chipsInsideMaster(
  intervals: { id: string; label: string; startMs: number; endMs: number }[],
  masterStart: number,
  masterEnd: number,
): LayerChip[] {
  const span = Math.max(masterEnd - masterStart, 1)
  const chips: LayerChip[] = []
  for (const iv of intervals) {
    const from = Math.max(iv.startMs, masterStart)
    const to = Math.min(iv.endMs, masterEnd)
    if (to <= from) continue
    chips.push({
      id: `${iv.id}@${masterStart}`,
      label: iv.label,
      tooltip: iv.label,
      leftPct: ((from - masterStart) / span) * 100,
      widthPct: ((to - from) / span) * 100,
    })
  }
  return chips
}

const model = computed(() => {
  const nowMs = Date.now()
  const occurred = props.events.filter((e) => e.event_status === 'occurred')
  const lightEvents = occurred.filter((e) => e.event_type === 'phase_changed')
  const nutrientEvents = occurred.filter(
    (e) => e.event_type === 'nutrient_phase_changed',
  )

  const masterRaw = buildMasterRaw(lightEvents, nowMs)
  const nutrientIv = nutrientIntervals(nutrientEvents, nowMs)
  const climateIv = climateIntervals(
    props.climateSegments,
    props.zoneId,
    nowMs,
  )

  const nutrientEmpty = nutrientIv.length === 0
  const climateEmpty = climateIv.length === 0

  if (masterRaw.length === 0) {
    return {
      masters: [] as MasterSegment[],
      hasMaster: false,
      nutrientEmpty,
      climateEmpty,
      axisStartLabel: '',
    }
  }

  const minMs = Math.min(...masterRaw.map((s) => s.startMs))
  const totalSpan = Math.max(nowMs - minMs, 1)

  const masters: MasterSegment[] = masterRaw.map((raw) => {
    const leftPct = ((raw.startMs - minMs) / totalSpan) * 100
    const widthPct = ((raw.endMs - raw.startMs) / totalSpan) * 100
    return {
      ...raw,
      leftPct,
      widthPct,
      nutrientChips: chipsInsideMaster(nutrientIv, raw.startMs, raw.endMs),
      climateChips: chipsInsideMaster(climateIv, raw.startMs, raw.endMs),
    }
  })

  return {
    masters,
    hasMaster: true,
    nutrientEmpty,
    climateEmpty,
    axisStartLabel: formatDate(new Date(minMs).toISOString()),
  }
})
</script>

<template>
  <div class="phase-timeline">
    <div class="phase-timeline__legend">
      <span class="phase-timeline__legend-item phase-timeline__legend-item--master">
        Master · Licht / Wachstum
      </span>
      <span class="phase-timeline__legend-item phase-timeline__legend-item--nutrient">
        Layer · Nährstoff
      </span>
      <span class="phase-timeline__legend-item phase-timeline__legend-item--climate">
        Layer · Raumklima
      </span>
    </div>

    <div v-if="!model.hasMaster" class="phase-timeline__empty-master">
      <p class="phase-timeline__empty-title">keine Licht-/Wachstumsphasen erfasst</p>
      <p class="phase-timeline__layer-empty" :class="{ 'phase-timeline__layer-empty--warn': model.nutrientEmpty }">
        {{
          model.nutrientEmpty
            ? 'kein Nährstoff-Regime erfasst'
            : 'Nährstoff-Regime vorhanden — wartet auf Master-Achse'
        }}
      </p>
      <p class="phase-timeline__layer-empty" :class="{ 'phase-timeline__layer-empty--warn': model.climateEmpty }">
        {{
          model.climateEmpty
            ? 'kein Klima-Regime erfasst'
            : 'Raumklima-Segmente vorhanden — wartet auf Master-Achse'
        }}
      </p>
    </div>

    <div v-else class="phase-timeline__master-wrap">
      <div class="phase-timeline__track-header">
        <span class="phase-timeline__track-dot" aria-hidden="true" />
        <span class="phase-timeline__track-label">Licht / Wachstum (Master)</span>
      </div>

      <div class="phase-timeline__bar" aria-label="Master-Zeitstrahl Licht/Wachstum">
        <div
          v-for="seg in model.masters"
          :key="seg.id"
          class="phase-timeline__segment"
          :style="{
            left: seg.leftPct + '%',
            width: seg.widthPct + '%',
            backgroundColor: seg.color,
            borderColor: seg.borderColor,
          }"
          :title="seg.tooltip"
        >
          <span class="phase-timeline__seg-label">{{ seg.label }}</span>

          <div class="phase-timeline__layers" aria-label="In-Phase-Layer">
            <div class="phase-timeline__layer phase-timeline__layer--nutrient">
              <template v-if="model.nutrientEmpty">
                <span class="phase-timeline__chip phase-timeline__chip--empty">
                  kein Nährstoff-Regime erfasst
                </span>
              </template>
              <template v-else-if="seg.nutrientChips.length === 0">
                <span class="phase-timeline__chip phase-timeline__chip--empty">
                  kein Nährstoff-Regime in dieser Phase
                </span>
              </template>
              <span
                v-for="chip in seg.nutrientChips"
                :key="chip.id"
                class="phase-timeline__chip phase-timeline__chip--nutrient"
                :style="{ left: chip.leftPct + '%', width: chip.widthPct + '%' }"
                :title="chip.tooltip"
              >
                {{ chip.label }}
              </span>
            </div>

            <div class="phase-timeline__layer phase-timeline__layer--climate">
              <template v-if="model.climateEmpty">
                <span class="phase-timeline__chip phase-timeline__chip--empty">
                  kein Klima-Regime erfasst
                </span>
              </template>
              <template v-else-if="seg.climateChips.length === 0">
                <span class="phase-timeline__chip phase-timeline__chip--empty">
                  kein Raumklima-Soll in dieser Phase
                </span>
              </template>
              <span
                v-for="chip in seg.climateChips"
                :key="chip.id"
                class="phase-timeline__chip phase-timeline__chip--climate"
                :style="{ left: chip.leftPct + '%', width: chip.widthPct + '%' }"
                :title="chip.tooltip"
              >
                {{ chip.label }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div class="phase-timeline__axis">
        <span class="phase-timeline__axis-start">{{ model.axisStartLabel }}</span>
        <span class="phase-timeline__axis-today">heute</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.phase-timeline {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.phase-timeline__legend {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.phase-timeline__legend-item::before {
  content: '';
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: var(--space-1);
}

.phase-timeline__legend-item--master::before {
  background: var(--color-iridescent-1);
}

.phase-timeline__legend-item--nutrient::before {
  background: var(--color-iridescent-3);
}

.phase-timeline__legend-item--climate::before {
  background: var(--color-info);
}

.phase-timeline__track-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-1);
}

.phase-timeline__track-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-iridescent-1);
}

.phase-timeline__track-label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.phase-timeline__bar {
  position: relative;
  min-height: 72px;
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.phase-timeline__segment {
  position: absolute;
  top: 0;
  bottom: 0;
  min-width: 2px;
  border-right: 1px solid;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.phase-timeline__seg-label {
  padding: var(--space-1) var(--space-2) 0;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.phase-timeline__layers {
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 2px var(--space-1) var(--space-1);
  min-height: 40px;
}

.phase-timeline__layer {
  position: relative;
  flex: 1;
  min-height: 16px;
}

.phase-timeline__chip {
  position: absolute;
  top: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  padding: 0 4px;
  font-size: 10px;
  font-weight: 500;
  border-radius: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.phase-timeline__chip--nutrient {
  background: color-mix(in srgb, var(--color-iridescent-3) 35%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-iridescent-3) 55%, transparent);
  color: var(--color-text-primary);
}

.phase-timeline__chip--climate {
  background: color-mix(in srgb, var(--color-info) 28%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-info) 50%, transparent);
  color: var(--color-text-primary);
}

.phase-timeline__chip--empty {
  position: relative;
  left: 0;
  width: auto;
  max-width: 100%;
  font-style: italic;
  color: var(--color-text-muted);
  border: 1px dashed var(--glass-border);
  background: transparent;
}

.phase-timeline__axis {
  display: flex;
  justify-content: space-between;
  padding: 0 2px;
  margin-top: var(--space-1);
}

.phase-timeline__axis-start,
.phase-timeline__axis-today {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.phase-timeline__empty-master {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
}

.phase-timeline__empty-title {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  font-style: italic;
  text-align: center;
}

.phase-timeline__layer-empty {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  text-align: center;
}

.phase-timeline__layer-empty--warn {
  color: var(--color-warning);
}
</style>
