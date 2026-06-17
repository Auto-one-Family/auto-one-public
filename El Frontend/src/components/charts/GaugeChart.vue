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
  /** Color thresholds for gauge segments */
  thresholds?: GaugeThreshold[]
  /** Gauge size */
  size?: 'sm' | 'md' | 'lg'
}

const props = withDefaults(defineProps<Props>(), {
  min: 0,
  max: 100,
  unit: '',
  thresholds: () => [
    { value: 0, color: tokens.statusGood },
    { value: 60, color: tokens.statusWarning },
    { value: 80, color: tokens.statusAlarm },
  ],
  size: 'md',
})

const SIZES: Record<string, number> = {
  sm: 80,
  md: 120,
  lg: 160,
}

const sizePixels = computed(() => SIZES[props.size] ?? SIZES.md)

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
 * Build gauge segments based on thresholds.
 * The filled portion uses threshold colors, the remaining is transparent.
 */
const chartData = computed(() => {
  const sorted = [...props.thresholds].sort((a, b) => a.value - b.value)
  const segments: number[] = []
  const colors: string[] = []

  // Calculate filled segments based on value position in threshold ranges
  for (let i = 0; i < sorted.length; i++) {
    const thresholdStart = (sorted[i].value - props.min) / range.value
    const thresholdEnd = i < sorted.length - 1
      ? (sorted[i + 1].value - props.min) / range.value
      : 1

    if (normalizedValue.value <= thresholdStart) {
      // Value hasn't reached this threshold
      break
    }

    const segmentEnd = Math.min(normalizedValue.value, thresholdEnd)
    const segmentSize = segmentEnd - thresholdStart

    if (segmentSize > 0) {
      segments.push(segmentSize * 100)
      colors.push(sorted[i].color)
    }
  }

  // Remaining unfilled portion
  const filledTotal = segments.reduce((sum, s) => sum + s, 0)
  const remaining = 100 - filledTotal

  if (remaining > 0) {
    segments.push(remaining)
    colors.push('rgba(29, 29, 42, 0.5)')
  }

  // Bottom half (hidden) - same size as top to create 180° gauge
  segments.push(100)
  colors.push('transparent')

  return {
    datasets: [{
      data: segments,
      backgroundColor: colors,
      borderWidth: 0,
      circumference: 180,
      rotation: 270,
    }],
  }
})

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
  const decimals = props.value % 1 !== 0 ? 1 : 0
  return props.value.toFixed(decimals)
})
</script>

<template>
  <div
    class="gauge-chart"
    :class="{ 'gauge-chart--sm': size === 'sm' }"
    :style="{
      width: `${sizePixels}px`,
      height: `${sizePixels * 0.6}px`,
    }"
  >
    <div class="gauge-chart__canvas">
      <Doughnut
        :data="chartData"
        :options="chartOptions"
      />
    </div>
    <div class="gauge-chart__value" :style="{ color: valueColor }">
      <span class="gauge-chart__number">{{ displayValue }}</span>
      <span v-if="unit" class="gauge-chart__unit">{{ unit }}</span>
    </div>
    <div class="gauge-chart__range">
      <span class="gauge-chart__min">{{ min }}</span>
      <span class="gauge-chart__max">{{ max }}</span>
    </div>
  </div>
</template>

<style scoped>
.gauge-chart {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.gauge-chart__canvas {
  position: relative;
  width: 100%;
  height: 100%;
}

.gauge-chart__value {
  position: absolute;
  bottom: 4px;
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
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
}

/* Compact size: hide range labels, shrink value text to fit 70px containers */
.gauge-chart--sm .gauge-chart__range {
  display: none;
}

.gauge-chart--sm .gauge-chart__value {
  bottom: 2px;
}

.gauge-chart--sm .gauge-chart__number {
  font-size: 1em;
}

.gauge-chart--sm .gauge-chart__unit {
  font-size: 0.55em;
}
</style>
