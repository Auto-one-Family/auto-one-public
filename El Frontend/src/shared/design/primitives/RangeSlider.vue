<script setup lang="ts">
/**
 * RangeSlider — Four-Point Threshold Slider
 *
 * Displays four draggable points on a horizontal track:
 * alarmLow → warnLow → warnHigh → alarmHigh
 *
 * Color zones between points:
 * [Red] alarmLow — [Yellow] warnLow — [Green] warnHigh — [Yellow] alarmHigh [Red]
 *
 * Used in SensorConfigPanel for threshold configuration.
 */

import { computed } from 'vue'

interface Props {
  /** Absolute minimum of the scale */
  min: number
  /** Absolute maximum of the scale */
  max: number
  /** Alarm low threshold */
  alarmLow: number
  /** Warning low threshold */
  warnLow: number
  /** Warning high threshold */
  warnHigh: number
  /** Alarm high threshold */
  alarmHigh: number
  /** Unit label (e.g., "°C", "pH") */
  unit?: string
  /** Step size for inputs */
  step?: number
  /** Disabled state */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  unit: '',
  step: 0.1,
  disabled: false,
})

const emit = defineEmits<{
  'update:alarmLow': [value: number]
  'update:warnLow': [value: number]
  'update:warnHigh': [value: number]
  'update:alarmHigh': [value: number]
}>()

const range = computed(() => props.max - props.min)

/** Convert value to percentage position on track */
function toPercent(value: number): number {
  if (range.value === 0) return 0
  return ((value - props.min) / range.value) * 100
}

/** Zone positions as percentages */
const zones = computed(() => ({
  alarmLowPct: toPercent(props.alarmLow),
  warnLowPct: toPercent(props.warnLow),
  warnHighPct: toPercent(props.warnHigh),
  alarmHighPct: toPercent(props.alarmHigh),
}))

/** Background gradient for the track */
const trackGradient = computed(() => {
  const { alarmLowPct, warnLowPct, warnHighPct, alarmHighPct } = zones.value
  return `linear-gradient(to right,
    var(--color-zone-alarm) 0%,
    var(--color-zone-alarm) ${alarmLowPct}%,
    var(--color-zone-warning) ${alarmLowPct}%,
    var(--color-zone-warning) ${warnLowPct}%,
    var(--color-zone-normal) ${warnLowPct}%,
    var(--color-zone-normal) ${warnHighPct}%,
    var(--color-zone-warning) ${warnHighPct}%,
    var(--color-zone-warning) ${alarmHighPct}%,
    var(--color-zone-alarm) ${alarmHighPct}%,
    var(--color-zone-alarm) 100%
  )`
})

function handleAlarmLow(e: Event) {
  const val = parseFloat((e.target as HTMLInputElement).value)
  if (val <= props.warnLow) {
    emit('update:alarmLow', val)
  }
}

function handleWarnLow(e: Event) {
  const val = parseFloat((e.target as HTMLInputElement).value)
  if (val >= props.alarmLow && val <= props.warnHigh) {
    emit('update:warnLow', val)
  }
}

function handleWarnHigh(e: Event) {
  const val = parseFloat((e.target as HTMLInputElement).value)
  if (val >= props.warnLow && val <= props.alarmHigh) {
    emit('update:warnHigh', val)
  }
}

function handleAlarmHigh(e: Event) {
  const val = parseFloat((e.target as HTMLInputElement).value)
  if (val >= props.warnHigh) {
    emit('update:alarmHigh', val)
  }
}
</script>

<template>
  <div class="range-slider" :class="{ 'range-slider--disabled': disabled }">
    <!-- Track with color zones -->
    <div class="range-slider__track" :style="{ background: trackGradient }">
      <!-- Range inputs overlaid on track -->
      <input
        type="range"
        class="range-slider__input range-slider__input--alarm-low"
        :min="min"
        :max="max"
        :step="step"
        :value="alarmLow"
        :disabled="disabled"
        title="Alarm unten"
        @input="handleAlarmLow"
      />
      <input
        type="range"
        class="range-slider__input range-slider__input--warn-low"
        :min="min"
        :max="max"
        :step="step"
        :value="warnLow"
        :disabled="disabled"
        title="Warnung unten"
        @input="handleWarnLow"
      />
      <input
        type="range"
        class="range-slider__input range-slider__input--warn-high"
        :min="min"
        :max="max"
        :step="step"
        :value="warnHigh"
        :disabled="disabled"
        title="Warnung oben"
        @input="handleWarnHigh"
      />
      <input
        type="range"
        class="range-slider__input range-slider__input--alarm-high"
        :min="min"
        :max="max"
        :step="step"
        :value="alarmHigh"
        :disabled="disabled"
        title="Alarm oben"
        @input="handleAlarmHigh"
      />
    </div>

    <!-- Labels beneath the track -->
    <div class="range-slider__labels">
      <div class="range-slider__label range-slider__label--alarm" :style="{ left: `${zones.alarmLowPct}%` }">
        <span class="range-slider__label-value">{{ alarmLow }}</span>
        <span class="range-slider__label-text">Alarm ↓</span>
      </div>
      <div class="range-slider__label range-slider__label--warn" :style="{ left: `${zones.warnLowPct}%` }">
        <span class="range-slider__label-value">{{ warnLow }}</span>
        <span class="range-slider__label-text">Warn ↓</span>
      </div>
      <div class="range-slider__label range-slider__label--warn" :style="{ left: `${zones.warnHighPct}%` }">
        <span class="range-slider__label-value">{{ warnHigh }}</span>
        <span class="range-slider__label-text">Warn ↑</span>
      </div>
      <div class="range-slider__label range-slider__label--alarm" :style="{ left: `${zones.alarmHighPct}%` }">
        <span class="range-slider__label-value">{{ alarmHigh }}</span>
        <span class="range-slider__label-text">Alarm ↑</span>
      </div>
    </div>

    <!-- Scale min/max -->
    <div class="range-slider__scale">
      <span>{{ min }}{{ unit ? ` ${unit}` : '' }}</span>
      <span>{{ max }}{{ unit ? ` ${unit}` : '' }}</span>
    </div>
  </div>
</template>

<style scoped>
.range-slider {
  position: relative;
  width: 100%;
  padding: var(--space-2) 0 var(--space-8) 0;
  user-select: none;
}

.range-slider--disabled {
  opacity: 0.5;
  pointer-events: none;
}

/* ═══════════════════════════════════════════════════════════════════════════
   TRACK
   ═══════════════════════════════════════════════════════════════════════════ */

.range-slider__track {
  position: relative;
  height: 8px;
  border-radius: var(--radius-xs);
  border: 1px solid var(--glass-border);
}

/* ═══════════════════════════════════════════════════════════════════════════
   RANGE INPUTS — Overlaid on top of each other
   ═══════════════════════════════════════════════════════════════════════════ */

.range-slider__input {
  position: absolute;
  top: -6px;
  left: 0;
  width: 100%;
  height: 20px;
  margin: 0;
  padding: 0;
  background: transparent;
  -webkit-appearance: none;
  appearance: none;
  pointer-events: none;
  z-index: var(--z-dropdown);
}

.range-slider__input::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  cursor: pointer;
  pointer-events: all;
  border: 2px solid;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
  transition: transform 0.15s ease;
}

.range-slider__input::-webkit-slider-thumb:hover {
  transform: scale(1.2);
}

.range-slider__input::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  cursor: pointer;
  pointer-events: all;
  border: 2px solid;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
  transition: transform 0.15s ease;
}

/* Alarm thumbs — red */
.range-slider__input--alarm-low::-webkit-slider-thumb,
.range-slider__input--alarm-high::-webkit-slider-thumb {
  background: var(--color-status-alarm);
  border-color: var(--color-error);
}

.range-slider__input--alarm-low::-moz-range-thumb,
.range-slider__input--alarm-high::-moz-range-thumb {
  background: var(--color-status-alarm);
  border-color: var(--color-error);
}

/* Warning thumbs — yellow */
.range-slider__input--warn-low::-webkit-slider-thumb,
.range-slider__input--warn-high::-webkit-slider-thumb {
  background: var(--color-status-warning);
  border-color: var(--color-warning);
}

.range-slider__input--warn-low::-moz-range-thumb,
.range-slider__input--warn-high::-moz-range-thumb {
  background: var(--color-status-warning);
  border-color: var(--color-warning);
}

/* ═══════════════════════════════════════════════════════════════════════════
   LABELS
   ═══════════════════════════════════════════════════════════════════════════ */

.range-slider__labels {
  position: relative;
  height: 36px;
  margin-top: var(--space-2);
}

.range-slider__label {
  position: absolute;
  transform: translateX(-50%);
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
}

.range-slider__label-value {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-primary);
}

.range-slider__label-text {
  font-size: var(--text-xxs);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.range-slider__label--alarm .range-slider__label-text {
  color: var(--color-status-alarm);
}

.range-slider__label--warn .range-slider__label-text {
  color: var(--color-status-warning);
}

/* ═══════════════════════════════════════════════════════════════════════════
   SCALE
   ═══════════════════════════════════════════════════════════════════════════ */

.range-slider__scale {
  display: flex;
  justify-content: space-between;
  margin-top: var(--space-1);
  font-family: var(--font-mono);
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
}
</style>
