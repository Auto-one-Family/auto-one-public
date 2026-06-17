<script setup lang="ts">
/**
 * SharedSensorRefCard — Compact read-only reference card for multi_zone sensors (6.7)
 *
 * Shown in Monitor L2 "Shared Sensors" section for sensors that physically live
 * in another zone but logically serve the current zone via assigned_zones.
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Share2, ArrowRight } from 'lucide-vue-next'
import { getSensorLabel, getSensorUnit, getSensorConfig } from '@/utils/sensorDefaults'

interface SharedSensor {
  sensor_type: string
  name?: string | null
  raw_value?: number | null
  unit?: string
  quality?: string
  gpio?: number
  config_id?: string
  _homeZoneName?: string
}

interface Props {
  sensor: SharedSensor
  homeZoneId: string
}

const props = defineProps<Props>()
const router = useRouter()

const displayName = computed(() =>
  props.sensor.name || getSensorLabel(props.sensor.sensor_type) || props.sensor.sensor_type
)

const resolvedUnit = computed(() => {
  const raw = props.sensor.unit
  if (raw && raw !== 'raw') return raw
  const configUnit = getSensorUnit(props.sensor.sensor_type)
  return configUnit !== 'raw' ? configUnit : ''
})

function formatValue(value: number | null | undefined): string {
  if (value === null || value === undefined) return '--'
  const dec = getSensorConfig(props.sensor.sensor_type)?.decimals ?? 2
  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  }).format(Number(value))
}

function goToHomeZone(): void {
  router.push({ name: 'monitor-zone', params: { zoneId: props.homeZoneId } })
}
</script>

<template>
  <div class="shared-ref-card">
    <div class="shared-ref-card__header">
      <Share2 class="shared-ref-card__icon" />
      <span class="shared-ref-card__name" :title="displayName">{{ displayName }}</span>
      <span class="shared-ref-card__badge">Shared</span>
    </div>
    <div class="shared-ref-card__value">
      <span class="shared-ref-card__number">{{ formatValue(sensor.raw_value) }}</span>
      <span class="shared-ref-card__unit">{{ resolvedUnit }}</span>
    </div>
    <div class="shared-ref-card__footer">
      <span class="shared-ref-card__home">via {{ sensor._homeZoneName || homeZoneId }}</span>
      <button
        class="shared-ref-card__link"
        @click.stop="goToHomeZone"
        title="Zur Heimzone navigieren"
      >
        <ArrowRight class="w-3 h-3" />
        Heimzone
      </button>
    </div>
  </div>
</template>

<style scoped>
.shared-ref-card {
  padding: var(--space-3);
  border-radius: var(--radius-md);
  border: 1px dashed rgba(96, 165, 250, 0.25);
  background: var(--color-bg-tertiary);
  transition: border-color var(--transition-fast);
}

.shared-ref-card:hover {
  border-color: rgba(96, 165, 250, 0.4);
}

.shared-ref-card__header {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  margin-bottom: var(--space-1);
}

.shared-ref-card__icon {
  width: 14px;
  height: 14px;
  color: var(--color-iridescent-1);
  flex-shrink: 0;
}

.shared-ref-card__name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-primary);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.shared-ref-card__badge {
  display: inline-flex;
  align-items: center;
  font-size: var(--text-xxs);
  font-weight: 500;
  padding: 1px 6px;
  border-radius: var(--radius-xs);
  background: var(--color-info-bg);
  color: var(--color-info);
  white-space: nowrap;
  flex-shrink: 0;
}

.shared-ref-card__value {
  display: flex;
  align-items: baseline;
  gap: var(--space-1);
  margin-bottom: var(--space-1);
}

.shared-ref-card__number {
  font-size: 1.25rem;
  font-weight: 700;
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  color: var(--color-text-primary);
}

.shared-ref-card__unit {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.shared-ref-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.shared-ref-card__home {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.shared-ref-card__link {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: var(--text-xs);
  color: var(--color-iridescent-1);
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: var(--radius-sm);
  white-space: nowrap;
  min-height: 44px;
  min-width: 44px;
  justify-content: center;
  transition: background var(--transition-fast);
}

.shared-ref-card__link:hover {
  background: rgba(96, 165, 250, 0.1);
}
</style>
