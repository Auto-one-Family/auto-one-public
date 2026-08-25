<script setup lang="ts">
/**
 * ZoneTankEcPhBar — compact per-tank EC/pH strip for Monitor L2 (AUT-1324).
 *
 * V1: Ist + Mini-Verlauf only (no Soll/Delta). Values come from already-loaded
 * monitor zone sensors + device.tank_id; sparklines from parent cache.
 * Layout: SensorCard cell pattern (label → large value+unit → sparkline).
 */

import { computed } from 'vue'
import { Droplets } from 'lucide-vue-next'
import LiveLineChart, { type ThresholdConfig } from '@/components/charts/LiveLineChart.vue'
import type { ChartDataPoint } from '@/components/charts/types'
import { formatIstSollValue } from '@/components/plants/tankIstSollFormat'
import { getSensorUnit } from '@/utils/sensorDefaults'
import {
  buildTankEcPhRows,
  type TankEcPhSensorRef,
  type ZoneTankDeviceLike,
  type ZoneTankLike,
  type ZoneTankSensorLike,
} from '@/utils/zoneTankEcPh'

interface Props {
  tanks: ZoneTankLike[]
  devices: ZoneTankDeviceLike[]
  zoneSensors: ZoneTankSensorLike[]
  /** Show tank name when true (multi-tank) or always when >1 tank. */
  showTankLabels?: boolean
  getSparkline: (sensor: TankEcPhSensorRef) => ChartDataPoint[] | undefined
  getThresholds: (sensorType: string) => ThresholdConfig | undefined
}

const props = withDefaults(defineProps<Props>(), {
  showTankLabels: undefined,
})

const rows = computed(() =>
  buildTankEcPhRows(props.tanks, props.devices, props.zoneSensors),
)

const shouldShowTankLabel = computed(() => {
  if (props.showTankLabels !== undefined) return props.showTankLabels
  return rows.value.length > 1
})

function displayValue(sensor: TankEcPhSensorRef | null, decimals: number): string {
  return formatIstSollValue(sensor?.value, decimals)
}

function unitFor(sensor: TankEcPhSensorRef | null, fallback: string): string {
  if (!sensor) return fallback
  return getSensorUnit(sensor.sensor_type) || fallback
}
</script>

<template>
  <section
    v-if="rows.length > 0"
    class="zone-tank-ecph-bar"
    aria-label="Tank EC und pH"
  >
    <div
      v-for="row in rows"
      :key="row.tankId"
      class="zone-tank-ecph-bar__tank"
    >
      <header
        v-if="shouldShowTankLabel"
        class="zone-tank-ecph-bar__tank-label"
      >
        <Droplets class="zone-tank-ecph-bar__icon" aria-hidden="true" />
        <span>{{ row.tankName }}</span>
      </header>

      <div class="zone-tank-ecph-bar__metrics" role="group" :aria-label="`EC und pH für ${row.tankName}`">
        <!-- EC — SensorCard cell: label → value+unit → sparkline -->
        <div class="zone-tank-ecph-bar__metric">
          <span class="zone-tank-ecph-bar__metric-label">EC</span>
          <div class="zone-tank-ecph-bar__metric-value">
            <span class="zone-tank-ecph-bar__metric-number">{{ displayValue(row.ec, 0) }}</span>
            <span
              v-if="row.ec?.value != null"
              class="zone-tank-ecph-bar__metric-unit"
            >{{ unitFor(row.ec, 'µS/cm') }}</span>
          </div>
          <div class="zone-tank-ecph-bar__sparkline">
            <LiveLineChart
              v-if="row.ec && getSparkline(row.ec)?.length"
              :data="getSparkline(row.ec)!"
              compact
              height="28px"
              :max-data-points="30"
              :sensor-type="row.ec.sensor_type"
              :thresholds="getThresholds(row.ec.sensor_type)"
              :show-thresholds="!!getThresholds(row.ec.sensor_type)"
            />
            <span v-else class="zone-tank-ecph-bar__sparkline-empty">Keine Daten</span>
          </div>
        </div>

        <!-- PH — SensorCard cell: label → value+unit → sparkline -->
        <div class="zone-tank-ecph-bar__metric">
          <span class="zone-tank-ecph-bar__metric-label">PH</span>
          <div class="zone-tank-ecph-bar__metric-value">
            <span class="zone-tank-ecph-bar__metric-number">{{ displayValue(row.ph, 2) }}</span>
            <span
              v-if="row.ph?.value != null && unitFor(row.ph, '')"
              class="zone-tank-ecph-bar__metric-unit"
            >{{ unitFor(row.ph, '') }}</span>
          </div>
          <div class="zone-tank-ecph-bar__sparkline">
            <LiveLineChart
              v-if="row.ph && getSparkline(row.ph)?.length"
              :data="getSparkline(row.ph)!"
              compact
              height="28px"
              :max-data-points="30"
              :sensor-type="row.ph.sensor_type"
              :thresholds="getThresholds(row.ph.sensor_type)"
              :show-thresholds="!!getThresholds(row.ph.sensor_type)"
            />
            <span v-else class="zone-tank-ecph-bar__sparkline-empty">Keine Daten</span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.zone-tank-ecph-bar {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

.zone-tank-ecph-bar__tank {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  background: var(--color-bg-card, var(--color-bg-secondary));
}

.zone-tank-ecph-bar__tank-label {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--color-text-secondary);
}

.zone-tank-ecph-bar__icon {
  width: 0.875rem;
  height: 0.875rem;
  color: var(--color-iridescent-1);
}

.zone-tank-ecph-bar__metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0;
  align-items: stretch;
}

.zone-tank-ecph-bar__metric {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
  padding: 0 var(--space-3);
}

.zone-tank-ecph-bar__metric:first-child {
  padding-left: 0;
  border-right: 1px solid var(--glass-border);
}

.zone-tank-ecph-bar__metric:last-child {
  padding-right: 0;
}

.zone-tank-ecph-bar__metric-label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

/* Mirrors SensorCard value row (label → number + unit) */
.zone-tank-ecph-bar__metric-value {
  display: flex;
  align-items: baseline;
  gap: var(--space-1);
  min-width: 0;
  white-space: nowrap;
}

.zone-tank-ecph-bar__metric-number {
  font-size: clamp(1.125rem, 3vw, 1.5rem);
  font-weight: 700;
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  font-variant-numeric: tabular-nums;
  color: var(--color-text-primary);
}

.zone-tank-ecph-bar__metric-unit {
  font-size: var(--text-base);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.zone-tank-ecph-bar__sparkline {
  height: 28px;
  min-height: 28px;
}

.zone-tank-ecph-bar__sparkline-empty {
  display: flex;
  align-items: center;
  height: 100%;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

@media (max-width: 480px) {
  .zone-tank-ecph-bar__metrics {
    grid-template-columns: 1fr;
  }

  .zone-tank-ecph-bar__metric:first-child {
    padding-right: 0;
    padding-bottom: var(--space-2);
    border-right: none;
    border-bottom: 1px solid var(--glass-border);
  }

  .zone-tank-ecph-bar__metric:last-child {
    padding-left: 0;
    padding-top: var(--space-2);
  }
}
</style>
