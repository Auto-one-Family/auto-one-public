<script setup lang="ts">
/**
 * Editable Zone/Subzone × Domain track row (AUT-1234 T4 / AUT-1235 T5).
 * Resize edges, split/merge actions, click-empty to create — all via emits.
 */

import { computed, ref } from 'vue'
import { GitMerge, Scissors } from 'lucide-vue-next'
import type { PlanTrackRowModel, PlanTimelineWindow, PlanTrackBand } from '@/components/plan-timeline/planTimelineTracks'
import { nowMarkerPercent } from '@/components/plan-timeline/planTimelineTracks'
import { pointerToTimestamp } from '@/components/plan-timeline/planSegmentOps'

interface Props {
  track: PlanTrackRowModel
  window: PlanTimelineWindow
  /** Segment ids that have a merge candidate */
  mergeableIds?: Set<string>
  editable?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  mergeableIds: () => new Set(),
  editable: true,
})

const emit = defineEmits<{
  createAt: [payload: { track: PlanTrackRowModel; atMs: number }]
  edit: [band: PlanTrackBand]
  resize: [payload: { segmentId: string; edge: 'from' | 'to'; atMs: number }]
  split: [band: PlanTrackBand]
  merge: [segmentId: string]
}>()

const nowPct = computed(() => nowMarkerPercent(props.window))
const laneCount = computed(() => Math.max(1, props.track.laneCount || 1))
const barRef = ref<HTMLElement | null>(null)
const selectedId = ref<string | null>(null)

function bandStyle(band: PlanTrackBand): Record<string, string> {
  return {
    left: `${band.leftPct}%`,
    width: `${band.widthPct}%`,
    '--band-lane': String(band.laneIndex ?? 0),
  }
}

const selectedBand = computed(() =>
  props.track.bands.find((b) => b.segmentId === selectedId.value) ?? null,
)

function onBarClick(event: MouseEvent): void {
  if (!props.editable) return
  const target = event.target as HTMLElement
  if (target.closest('.plan-track__band') || target.closest('.plan-track__handle')) return
  if (!barRef.value) return
  const atMs = pointerToTimestamp(
    event.clientX,
    barRef.value.getBoundingClientRect(),
    props.window.startMs,
    props.window.endMs,
  )
  emit('createAt', { track: props.track, atMs })
}

function selectBand(band: PlanTrackBand, event: MouseEvent): void {
  event.stopPropagation()
  selectedId.value = band.segmentId
}

function onBandDblClick(band: PlanTrackBand, event: MouseEvent): void {
  if (!props.editable) return
  event.stopPropagation()
  emit('edit', band)
}

type DragState = {
  segmentId: string
  edge: 'from' | 'to'
}

let drag: DragState | null = null

function onHandleDown(band: PlanTrackBand, edge: 'from' | 'to', event: PointerEvent): void {
  if (!props.editable) return
  event.stopPropagation()
  event.preventDefault()
  drag = { segmentId: band.segmentId, edge }
  ;(event.target as HTMLElement).setPointerCapture?.(event.pointerId)
  window.addEventListener('pointermove', onHandleMove)
  window.addEventListener('pointerup', onHandleUp)
}

function onHandleMove(event: PointerEvent): void {
  // Visual feedback only during drag; persist on up
  void event
}

function onHandleUp(event: PointerEvent): void {
  window.removeEventListener('pointermove', onHandleMove)
  window.removeEventListener('pointerup', onHandleUp)
  if (!drag || !barRef.value) {
    drag = null
    return
  }
  const atMs = pointerToTimestamp(
    event.clientX,
    barRef.value.getBoundingClientRect(),
    props.window.startMs,
    props.window.endMs,
  )
  emit('resize', { segmentId: drag.segmentId, edge: drag.edge, atMs })
  drag = null
}
</script>

<template>
  <div class="plan-track" :aria-label="`${track.subzoneName} · ${track.domainLabel}`">
    <div class="plan-track__meta">
      <span class="plan-track__subzone">{{ track.subzoneName }}</span>
      <span class="plan-track__domain">{{ track.domainLabel }}</span>
      <div v-if="editable && selectedBand" class="plan-track__actions">
        <button
          type="button"
          class="plan-track__action"
          aria-label="Segment teilen"
          title="Teilen"
          @click="emit('split', selectedBand)"
        >
          <Scissors class="w-3.5 h-3.5" aria-hidden="true" />
        </button>
        <button
          type="button"
          class="plan-track__action"
          :disabled="!mergeableIds.has(selectedBand.segmentId)"
          aria-label="Mit Nachbar verschmelzen"
          title="Verschmelzen"
          @click="emit('merge', selectedBand.segmentId)"
        >
          <GitMerge class="w-3.5 h-3.5" aria-hidden="true" />
        </button>
      </div>
    </div>
    <div
      ref="barRef"
      class="plan-track__bar"
      :class="{ 'plan-track__bar--editable': editable }"
      :style="{ '--lane-count': String(laneCount) }"
      role="group"
      :aria-label="`${track.domainLabel} Zeitstrahl`"
      @click="onBarClick"
    >
      <div
        class="plan-track__now"
        :style="{ left: nowPct + '%' }"
        aria-hidden="true"
      />
      <div v-if="track.isEmpty" class="plan-track__empty">
        {{ editable ? 'klicken zum Anlegen' : 'kein Plan-Segment' }}
      </div>
      <div
        v-for="band in track.bands"
        :key="band.id"
        class="plan-track__band"
        :class="{
          'plan-track__band--selected': selectedId === band.segmentId,
          'plan-track__band--ghosted': band.visualState === 'ghosted',
          'plan-track__band--withdrawn': band.visualState === 'withdrawn',
        }"
        :data-measure="band.measure"
        :style="bandStyle(band)"
        :title="band.tooltip"
        @click="selectBand(band, $event)"
        @dblclick="onBandDblClick(band, $event)"
      >
        <button
          v-if="editable"
          type="button"
          class="plan-track__handle plan-track__handle--from"
          aria-label="Beginn verschieben"
          @pointerdown="onHandleDown(band, 'from', $event)"
        />
        <span class="plan-track__band-label">{{ band.label }}</span>
        <span
          v-if="band.pastDelta?.fromAppliedLog"
          class="plan-track__delta"
          :aria-label="`Ist ${band.pastDelta.istDisplay}, historischer Soll ${band.pastDelta.sollDisplay}, Delta ${band.pastDelta.deltaDisplay}`"
        >
          Δ {{ band.pastDelta.deltaDisplay }}
        </span>
        <button
          v-if="editable"
          type="button"
          class="plan-track__handle plan-track__handle--to"
          aria-label="Ende verschieben"
          @pointerdown="onHandleDown(band, 'to', $event)"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.plan-track {
  display: grid;
  grid-template-columns: minmax(120px, 180px) 1fr;
  gap: var(--space-3);
  align-items: center;
  min-height: 36px;
}

.plan-track__meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.plan-track__subzone {
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.plan-track__domain {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.plan-track__actions {
  display: inline-flex;
  gap: 4px;
  margin-top: 2px;
}

.plan-track__action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.plan-track__action:hover:not(:disabled) {
  color: var(--color-accent);
  border-color: var(--color-accent);
}

.plan-track__action:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.plan-track__bar {
  --lane-h: 22px;
  --lane-pad: 3px;
  --lane-count: 1;
  position: relative;
  height: calc(var(--lane-pad) * 2 + var(--lane-count) * var(--lane-h));
  min-height: 28px;
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  overflow: hidden;
}

.plan-track__bar--editable {
  cursor: crosshair;
}

.plan-track__now {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  margin-left: -1px;
  background: var(--color-accent);
  opacity: 0.85;
  z-index: 2;
  pointer-events: none;
}

.plan-track__empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  opacity: 0.7;
  pointer-events: none;
}

.plan-track__band {
  --band-lane: 0;
  position: absolute;
  top: calc(var(--lane-pad) + var(--band-lane) * var(--lane-h));
  height: calc(var(--lane-h) - 2px);
  display: flex;
  align-items: center;
  padding: 0 var(--space-2);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--color-info) 28%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-info) 55%, transparent);
  overflow: hidden;
  z-index: 1;
  cursor: pointer;
}

/* Distinct tints per measure so stacked lanes stay scannable */
.plan-track__band[data-measure='target_ec'] {
  background: color-mix(in srgb, var(--color-info) 28%, transparent);
  border-color: color-mix(in srgb, var(--color-info) 55%, transparent);
}

.plan-track__band[data-measure='target_ph'] {
  background: color-mix(in srgb, var(--color-success) 26%, transparent);
  border-color: color-mix(in srgb, var(--color-success) 50%, transparent);
}

.plan-track__band[data-measure='target_temperature'] {
  background: color-mix(in srgb, var(--color-warning) 22%, transparent);
  border-color: color-mix(in srgb, var(--color-warning) 48%, transparent);
}

.plan-track__band[data-measure='target_humidity'] {
  background: color-mix(in srgb, var(--color-iridescent-2) 28%, transparent);
  border-color: color-mix(in srgb, var(--color-iridescent-2) 55%, transparent);
}

.plan-track__band[data-measure='target_co2'] {
  background: color-mix(in srgb, var(--color-iridescent-3) 26%, transparent);
  border-color: color-mix(in srgb, var(--color-iridescent-3) 50%, transparent);
}

.plan-track__band--selected {
  box-shadow: inset 0 0 0 1px var(--color-accent);
  border-color: var(--color-accent);
  z-index: 3;
}

/* AUT-1236: planned-but-not-occurred — visible, not removed (AUT-1207 rule). */
.plan-track__band--ghosted {
  opacity: 0.4;
  background: transparent;
  border-style: dashed;
  border-color: rgba(96, 165, 250, 0.45);
}

/* AUT-1236: withdrawn — strikethrough, never silently hidden. */
.plan-track__band--withdrawn {
  opacity: 0.55;
  border-color: var(--color-danger);
}

.plan-track__band--withdrawn .plan-track__band-label {
  text-decoration: line-through;
}

.plan-track__band-label {
  font-size: var(--text-xs);
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
  pointer-events: none;
}

.plan-track__delta {
  flex-shrink: 0;
  margin-left: var(--space-1);
  font-size: var(--text-xs);
  font-family: var(--font-mono, monospace);
  color: var(--color-text-secondary);
  pointer-events: none;
}

.plan-track__handle {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 8px;
  padding: 0;
  border: none;
  background: rgba(255, 255, 255, 0.2);
  cursor: ew-resize;
  z-index: 4;
}

.plan-track__handle--from {
  left: 0;
}

.plan-track__handle--to {
  right: 0;
}

.plan-track__handle:hover {
  background: var(--color-accent);
}
</style>
