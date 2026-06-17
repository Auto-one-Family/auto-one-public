<script setup lang="ts">
/**
 * RssiIndicator - WiFi Signal Strength Visualization
 *
 * Displays RSSI (Received Signal Strength Indicator) as visual bars
 * with color coding for signal quality.
 *
 * Signal Quality Levels:
 * - Excellent (4 bars): > -50 dBm
 * - Good (3 bars): -50 to -60 dBm
 * - Fair (2 bars): -60 to -70 dBm
 * - Weak (1 bar): -70 to -80 dBm
 * - Critical (0 bars): < -80 dBm
 */

import { computed } from 'vue'

interface Props {
  rssi: number
  showValue?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showValue: true,
})

/**
 * Get signal quality level (0-4) from RSSI
 */
const rssiLevel = computed(() => {
  if (props.rssi > -50) return 4
  if (props.rssi > -60) return 3
  if (props.rssi > -70) return 2
  if (props.rssi > -80) return 1
  return 0
})

/**
 * Get quality class for styling
 */
const qualityClass = computed(() => {
  if (rssiLevel.value >= 3) return 'good'
  if (rssiLevel.value >= 2) return 'fair'
  if (rssiLevel.value >= 1) return 'weak'
  return 'critical'
})

/**
 * Get quality label (German)
 */
const qualityLabel = computed(() => {
  if (rssiLevel.value >= 4) return 'Ausgezeichnet'
  if (rssiLevel.value >= 3) return 'Gut'
  if (rssiLevel.value >= 2) return 'Mittel'
  if (rssiLevel.value >= 1) return 'Schwach'
  return 'Kritisch'
})
</script>

<template>
  <div
    class="rssi-indicator"
    :class="`rssi-indicator--${qualityClass}`"
    :title="`${rssi} dBm - ${qualityLabel}`"
  >
    <span v-if="showValue" class="rssi-value">{{ rssi }} dBm</span>
    <div class="rssi-bars">
      <span class="rssi-bar" :class="{ active: rssiLevel >= 1 }" />
      <span class="rssi-bar" :class="{ active: rssiLevel >= 2 }" />
      <span class="rssi-bar" :class="{ active: rssiLevel >= 3 }" />
      <span class="rssi-bar" :class="{ active: rssiLevel >= 4 }" />
    </div>
  </div>
</template>

<style scoped>
.rssi-indicator {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
}

.rssi-value {
  font-size: 0.75rem;
  font-family: var(--font-mono, monospace);
  color: var(--color-text-muted);
}

.rssi-bars {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  height: 0.875rem;
}

.rssi-bar {
  width: 3px;
  border-radius: 1px;
  background-color: var(--color-bg-quaternary);
  transition: all 0.2s ease;
}

.rssi-bar:nth-child(1) { height: 25%; }
.rssi-bar:nth-child(2) { height: 50%; }
.rssi-bar:nth-child(3) { height: 75%; }
.rssi-bar:nth-child(4) { height: 100%; }

.rssi-bar.active {
  background-color: var(--color-success);
}

/* Fair signal - Amber */
.rssi-indicator--fair .rssi-bar.active {
  background-color: var(--color-warning);
}

/* Weak signal - Orange */
.rssi-indicator--weak .rssi-bar.active {
  background-color: var(--color-warning);
}

/* Critical signal - Red */
.rssi-indicator--critical .rssi-bar.active {
  background-color: var(--color-error);
}
</style>
