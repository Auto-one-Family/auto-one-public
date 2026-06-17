<script setup lang="ts">
/**
 * StatusBarChart Component
 *
 * Horizontal or vertical bar chart for status distribution visualization.
 * Ideal for showing device status counts (online/offline/warning).
 * Design-token-consistent dark theme.
 */

import { computed } from 'vue'
import { Bar } from 'vue-chartjs'
import { tokens } from '@/utils/cssTokens'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
} from 'chart.js'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip)

import type { StatusBarItem } from './types'
export type { StatusBarItem }

interface Props {
  /** Bar data items */
  data: StatusBarItem[]
  /** Bar orientation */
  horizontal?: boolean
  /** Container height */
  height?: string
  /** Show value labels on bars */
  showValues?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  horizontal: true,
  height: '120px',
  showValues: true,
})

const DEFAULT_COLORS = [tokens.statusGood, tokens.statusWarning, tokens.statusAlarm, tokens.accent, tokens.mock]

const chartData = computed(() => ({
  labels: props.data.map(d => d.label),
  datasets: [{
    data: props.data.map(d => d.value),
    backgroundColor: props.data.map((d, i) =>
      d.color ?? DEFAULT_COLORS[i % DEFAULT_COLORS.length]
    ),
    borderWidth: 0,
    borderRadius: 4,
    barPercentage: 0.7,
    categoryPercentage: 0.8,
  }],
}))

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  indexAxis: (props.horizontal ? 'y' : 'x') as 'x' | 'y',
  animation: { duration: 300 },
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: 'rgba(7, 7, 13, 0.9)',
      borderColor: 'rgba(133, 133, 160, 0.3)',
      borderWidth: 1,
      titleFont: { family: 'JetBrains Mono', size: 11 },
      bodyFont: { family: 'JetBrains Mono', size: 12 },
      titleColor: tokens.textSecondary,
      bodyColor: tokens.textPrimary,
      padding: 8,
    },
  },
  scales: {
    x: props.horizontal
      ? { display: false, grid: { display: false }, border: { display: false } }
      : {
          display: true,
          grid: { display: false },
          ticks: { color: tokens.textMuted, font: { family: 'JetBrains Mono', size: 10 } },
          border: { display: false },
        },
    y: props.horizontal
      ? {
          display: true,
          grid: { display: false },
          ticks: { color: tokens.textMuted, font: { family: 'JetBrains Mono', size: 10 } },
          border: { display: false },
        }
      : { display: false, grid: { display: false }, border: { display: false } },
  },
}))
</script>

<template>
  <div class="status-bar-chart" :style="{ height }">
    <Bar
      :data="chartData"
      :options="chartOptions"
    />
  </div>
</template>

<style scoped>
.status-bar-chart {
  position: relative;
  width: 100%;
}
</style>
