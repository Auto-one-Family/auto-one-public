<script setup lang="ts">
/**
 * GaugeChart Component
 *
 * Semi-circular gauge visualization using Doughnut chart with 180° rotation.
 * Shows a single value against min/max range with configurable thresholds.
 * Design-token-consistent dark theme.
 */

import { computed } from 'vue'
import { Doughnut } from 'vue-chartjs'
import { tokens } from '@/utils/cssTokens'
import { formatNumber } from '@/utils/formatters'
import {
  Chart as ChartJS,
  ArcElement,
  Tooltip,
} from 'chart.js'

ChartJS.register(ArcElement, Tooltip)

import type { GaugeThreshold } from './types'
export type { GaugeThreshold }

interface Props {
  /** Current gauge value */
  value: number
  /** Minimum range value */
  min?: number
  /** Maximum range value */
  max?: number
  /** Unit suffix displayed with value */
  unit?: string
  /** Explicit decimals (de-DE). Default: 1 if fractional, else 0 */
  decimals?: number
  /** Color thresholds for gauge segments */
  thresholds?: GaugeThreshold[]
  /** Gauge size */
  size?: 'sm' | 'md' | 'lg'
}

const props = withDefaults(defineProps<Props>(), {
  min: 0,
  max: 100,
  unit: '',
  decimals: undefined,
  thresholds: () => [
    { value: 0, color: tokens.statusGood },
    { value: 60, color: tokens.statusWarning },
    { value: 80, color: tokens.statusAlarm },
  ],
  size: 'md',
})

const range = computed(() => props.max - props.min)

/** Clamp value within min/max range */
const clampedValue = computed(() =>
  Math.min(Math.max(props.value, props.min), props.max)
)

/** Normalized value as fraction of range (0-1) */
const normalizedValue = computed(() =>
  range.value > 0 ? (clampedValue.value - props.min) / range.value : 0
)

/**
 * Fixed top-semicircle geometry (AUT-1099): rotation 270° (9 o'clock start)
 * + circumference 180° (sweeping through 12 o'clock to 3 o'clock). The arc
 * segments (chartData) AND the needle marker (markerDeg + CSS pivot/length
 * below) all derive from these two constants so they cannot drift apart
 * again the way they did across the AUT-1099 Teil b/c regressions.
 *
 * Chart.js internally computes the canvas start angle as `(rotation - 90)`deg,
 * measured clockwise from the 3-o'clock axis (see DoughnutController
 * _getRotation() in chart.js). rotation:270 therefore starts at 9 o'clock,
 * not rotation:180 (which starts at 6 o'clock and draws the left half
 * instead of the top half) — confirmed against the installed chart.js source
 * after a rotation:180 regression produced a visibly skewed ring.
 */
const ARC_ROTATION_DEG = 270
const ARC_CIRCUMFERENCE_DEG = 180

/**
 * Zone-Ring: all threshold segments are always fully visible regardless of
 * the current value (AUT-1099 E1). The current value is shown via the
 * `.gauge-chart__marker` needle element below. This replaces the previous
 * Fill-Bogen approach where segments were only painted up to `normalizedValue`.
 *
 * Why no hidden bottom segment:
 *   The visible segments sum to 100 (full range = 0..1 mapped to 0..100).
 *   With circumference:180 and no extra data, Chart.js maps all 100 units to
 *   the full 180°, giving the correct semicircle. Adding a transparent "100"
 *   segment would dilute the arc to only 90° (a quarter-circle) — the bug
 *   present in Part (a).
 */
const chartData = computed(() => {
  const sorted = [...props.thresholds].sort((a, b) => a.value - b.value)
  const segments: number[] = []
  const colors: string[] = []

  for (let i = 0; i < sorted.length; i++) {
    const start = (sorted[i].value - props.min) / range.value
    const end = i < sorted.length - 1
      ? (sorted[i + 1].value - props.min) / range.value
      : 1
    const s = Math.min(1, Math.max(0, start))
    const e = Math.min(1, Math.max(0, end))
    const size = Math.max(0, e - s) * 100
    if (size > 0) {
      segments.push(size)
      colors.push(sorted[i].color)
    }
  }

  return {
    datasets: [{
      data: segments,
      backgroundColor: colors,
      borderWidth: 0,
      // rotation:270 = start at 9 o'clock (west); circumference:180 sweeps
      // clockwise to 3 o'clock (east) through 12 o'clock (north).
      circumference: ARC_CIRCUMFERENCE_DEG,
      rotation: ARC_ROTATION_DEG,
    }],
  }
})

/**
 * Rotation angle (deg) for the needle marker.
 * Maps normalizedValue 0→1 to CSS rotation -90°→+90° so that:
 *   min (0) → 9 o'clock (−90°), mid (0.5) → 12 o'clock (0°), max (1) → 3 o'clock (+90°)
 * Derived from the same ARC_CIRCUMFERENCE_DEG as the arc segments above.
 */
const markerDeg = computed(
  () => normalizedValue.value * ARC_CIRCUMFERENCE_DEG - ARC_CIRCUMFERENCE_DEG / 2
)

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  cutout: '75%',
  animation: { duration: 400 },
  plugins: {
    legend: { display: false },
    tooltip: { enabled: false },
  },
}))

/** Determine current value color based on thresholds */
const valueColor = computed(() => {
  const sorted = [...props.thresholds].sort((a, b) => a.value - b.value)
  let color = sorted[0]?.color ?? tokens.accent
  for (const t of sorted) {
    if (clampedValue.value >= t.value) {
      color = t.color
    }
  }
  return color
})

const displayValue = computed(() => {
  const decimals = props.decimals ?? (props.value % 1 !== 0 ? 1 : 0)
  return formatNumber(props.value, decimals)
})
</script>

<template>
  <div
    class="gauge-chart"
    :class="{ 'gauge-chart--sm': size === 'sm' }"
  >
    <div class="gauge-chart__stage">
      <div class="gauge-chart__canvas">
        <Doughnut
          :data="chartData"
          :options="chartOptions"
        />
      </div>
      <!-- Needle marker — pivots at doughnut center (bottom of element) -->
      <div
        class="gauge-chart__marker"
        aria-hidden="true"
        :style="{ transform: `rotate(${markerDeg}deg)` }"
      />
      <div class="gauge-chart__value" :style="{ color: valueColor }">
        <span class="gauge-chart__number">{{ displayValue }}</span>
        <span v-if="unit" class="gauge-chart__unit">{{ unit }}</span>
      </div>
      <div class="gauge-chart__range">
        <span class="gauge-chart__min">{{ min }}</span>
        <span class="gauge-chart__max">{{ max }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
/*
 * AUT-902: container-relative gauge (no fixed SIZES px).
 * The root fills the widget cell; the stage keeps the gauge's 5:3 shape and is
 * "contained" to the largest box that fits BOTH cell width and height. chart.js
 * (responsive + maintainAspectRatio:false) resizes the canvas to the stage on
 * cell resize via its own ResizeObserver — including 0-height→visible mounts
 * (zone-tile preview, tabs). Text scales with the cell via container queries.
 */
.gauge-chart {
  position: relative;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  container-type: size;
}

.gauge-chart__stage {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  aspect-ratio: 5 / 3;
  width: min(100%, calc(100cqh * 5 / 3));
  max-width: 100%;
  max-height: 100%;
  font-size: clamp(0.5rem, 14cqmin, 1.25rem);
}

.gauge-chart__canvas {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 0;
}

.gauge-chart__value {
  position: absolute;
  bottom: 0.25em;
  left: 50%;
  transform: translateX(-50%);
  text-align: center;
  line-height: 1;
}

.gauge-chart__number {
  font-family: var(--font-mono);
  font-size: 1.25em;
  font-weight: 600;
}

.gauge-chart__unit {
  font-family: var(--font-mono);
  font-size: 0.65em;
  color: var(--color-text-muted);
  margin-left: 2px;
}

.gauge-chart__range {
  display: flex;
  justify-content: space-between;
  width: 100%;
  padding: 0 4px;
  margin-top: -2px;
}

.gauge-chart__min,
.gauge-chart__max {
  font-family: var(--font-mono);
  font-size: 0.6em;
  color: var(--color-text-muted);
}

/*
 * Hide range labels when the cell is too short to read them (small live tiles,
 * compact zone-tile preview). Container query replaces the old fixed `--sm` px
 * breakpoint so it reacts to the actual cell, not just the size prop.
 */
@container (max-height: 96px) {
  .gauge-chart__range {
    display: none;
  }
}

/* Legacy `size="sm"` callers keep range hidden + value tucked a touch lower. */
.gauge-chart--sm .gauge-chart__range {
  display: none;
}

.gauge-chart--sm .gauge-chart__value {
  bottom: 0.15em;
}

/*
 * AUT-1099 (needle-anchor fix) — Zone-Ring needle marker.
 * Centered horizontally at 50%, but the pivot is NOT at 50% of the stage
 * height. For a circumference:180/rotation:270 doughnut (top semicircle,
 * 9→12→3 o'clock), Chart.js's DoughnutController.getRatioAndOffset() (see
 * installed chart.js source, dist/chart.js) shifts the drawn circle's
 * center DOWN from the canvas midpoint by 0.5 * outerRadius, so the
 * semicircle fills the full available canvas height instead of just the
 * top half. With the stage's fixed 5:3 aspect ratio (AUT-902) this
 * resolves to an exact 1/12 (~8.33%) pivot offset from the bottom edge —
 * the old 50% pivot was the actual cause of the ~15-20° needle/arc
 * mismatch (not the rotation constant, which already matched the arc).
 * Needle length reaches exactly to the arc's outer radius: 5/6 (~83.33%)
 * of the stage height from this pivot — independent of `cutout` for this
 * specific rotation/circumference span. Both fractions are tied to
 * ARC_ROTATION_DEG/ARC_CIRCUMFERENCE_DEG above: if those ever change,
 * recompute via getRatioAndOffset before touching these values.
 *
 * The marker element points straight up by default; the JS `markerDeg`
 * rotation maps min→-90° (9 o'clock), mid→0° (12 o'clock), max→+90°
 * (3 o'clock) — consistent with the 180° semicircle arc geometry.
 *
 * Contrast: white (--color-text-primary) stands apart from all zone segment
 * colors (green/yellow/red family), satisfying the Design-Spec contrast rule.
 */
.gauge-chart__marker {
  position: absolute;
  left: calc(50% - 1px);
  bottom: calc(100% / 12);
  width: 2px;
  height: calc(100% * 5 / 6);
  background: var(--color-text-primary);
  transform-origin: bottom center;
  border-radius: 1px 1px 0 0;
  pointer-events: none;
}
</style>
