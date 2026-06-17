<script setup lang="ts">
/**
 * ComponentCard — Level 2 Sensor/Actuator Card
 *
 * Compact card showing a single sensor or actuator with:
 * - Type icon, name, current value, unit
 * - Quality badge (sensors) or state badge (actuators)
 * - Owning ESP name (small, secondary)
 * - Zone name (small, secondary)
 *
 * Used in the Komponentenübersicht (Level 2) where ESPs are NOT shown.
 */

import { computed } from 'vue'
import {
  Thermometer,
  Droplets,
  Gauge,
  Sun,
  Wind,
  Leaf,
  Waves,
  Zap,
  Power,
  Fan,
  Lamp,
  Heater,
} from 'lucide-vue-next'
import type { Component } from 'vue'

import type { ComponentCardItem } from './types'
export type { ComponentCardItem }

interface Props {
  item: ComponentCardItem
}

const props = defineProps<Props>()

const emit = defineEmits<{
  click: [item: ComponentCardItem]
}>()

// ── Icon mapping ─────────────────────────────────────────────────────

const sensorIcons: Record<string, Component> = {
  temperature: Thermometer,
  humidity: Droplets,
  pressure: Gauge,
  light: Sun,
  wind: Wind,
  co2: Leaf,
  ph: Waves,
  soil_moisture: Droplets,
}

const actuatorIcons: Record<string, Component> = {
  relay: Zap,
  pump: Power,
  fan: Fan,
  lamp: Lamp,
  heater: Heater,
  valve: Power,
}

const icon = computed<Component>(() => {
  if (props.item.type === 'sensor') {
    const baseType = props.item.sensorType?.toLowerCase().replace(/[_-]/g, '') || ''
    for (const [key, comp] of Object.entries(sensorIcons)) {
      if (baseType.includes(key)) return comp
    }
    return Thermometer
  } else {
    const baseType = props.item.actuatorType?.toLowerCase().replace(/[_-]/g, '') || ''
    for (const [key, comp] of Object.entries(actuatorIcons)) {
      if (baseType.includes(key)) return comp
    }
    return Zap
  }
})

// ── Display values ───────────────────────────────────────────────────

const displayValue = computed(() => {
  if (props.item.type === 'sensor') {
    if (props.item.value === null || props.item.value === undefined) return '—'
    return `${props.item.value}${props.item.unit ? ' ' + props.item.unit : ''}`
  }
  // Actuator
  if (props.item.emergencyStopped) return 'Not-Stopp'
  return props.item.state ? 'Ein' : 'Aus'
})

const qualityClass = computed(() => {
  if (props.item.type !== 'sensor') return ''
  const q = props.item.quality || 'good'
  if (q === 'excellent' || q === 'good') return 'component-card__quality--good'
  if (q === 'fair') return 'component-card__quality--fair'
  return 'component-card__quality--poor'
})

const stateClass = computed(() => {
  if (props.item.type !== 'actuator') return ''
  if (props.item.emergencyStopped) return 'component-card__state--emergency'
  return props.item.state ? 'component-card__state--on' : 'component-card__state--off'
})

const displayName = computed(() =>
  props.item.name || props.item.sensorType || props.item.actuatorType || `GPIO ${props.item.gpio}`
)
</script>

<template>
  <div
    :class="[
      'component-card',
      item.type === 'actuator' ? 'component-card--actuator' : 'component-card--sensor',
      { 'component-card--stale': item.isStale }
    ]"
    role="button"
    tabindex="0"
    @click="emit('click', item)"
    @keydown.enter="emit('click', item)"
  >
    <!-- Icon + Name -->
    <div class="component-card__header">
      <component :is="icon" class="component-card__icon" />
      <span class="component-card__name">{{ displayName }}</span>
    </div>

    <!-- Value -->
    <div class="component-card__value" :class="[qualityClass, stateClass]">
      {{ displayValue }}
    </div>

    <!-- Meta: ESP + Zone -->
    <div class="component-card__meta">
      <span class="component-card__esp" :title="item.espId">
        {{ item.espName || item.espId }}
      </span>
      <span v-if="item.zoneName" class="component-card__zone">
        {{ item.zoneName }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.component-card {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  padding: 0.625rem 0.75rem;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  min-width: 140px;
  max-width: 220px;
  transition: all 0.15s ease;
  cursor: pointer;
}

.component-card:hover {
  border-color: var(--glass-border-hover, rgba(255, 255, 255, 0.12));
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.component-card--sensor {
  border-left: 3px solid var(--color-iridescent-2);
}

.component-card--actuator {
  border-left: 3px solid var(--color-iridescent-3);
}

.component-card--stale {
  opacity: 0.6;
  border-left-color: var(--color-text-muted);
}

/* Header */
.component-card__header {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.component-card__icon {
  width: 0.875rem;
  height: 0.875rem;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.component-card__name {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Value */
.component-card__value {
  font-size: 1rem;
  font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
  color: var(--color-text-primary);
  line-height: 1.2;
}

.component-card__quality--good {
  color: var(--color-success);
}

.component-card__quality--fair {
  color: var(--color-warning);
}

.component-card__quality--poor {
  color: var(--color-error);
}

.component-card__state--on {
  color: var(--color-success);
}

.component-card__state--off {
  color: var(--color-text-muted);
}

.component-card__state--emergency {
  color: var(--color-error);
  animation: pulse-error 1.5s ease-in-out infinite;
}

@keyframes pulse-error {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

/* Meta */
.component-card__meta {
  display: flex;
  justify-content: space-between;
  gap: 0.25rem;
  font-size: 0.625rem;
  color: var(--color-text-muted);
}

.component-card__esp,
.component-card__zone {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 50%;
}
</style>
