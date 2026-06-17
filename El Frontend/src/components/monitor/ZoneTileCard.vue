<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'
import { AlertTriangle, Zap, Pencil } from 'lucide-vue-next'
import type { ZoneKPI, ZoneHealthStatus } from '@/composables/useZoneKPIs'
import { HEALTH_STATUS_CONFIG as DEFAULT_HEALTH_CONFIG } from '@/composables/useZoneKPIs'
import type { LogicRule } from '@/types/logic'
import { formatNumber, zoneHealthToLevel } from '@/utils/formatters'
import StatusBadge from '@/components/base/StatusBadge.vue'
import { useAuthStore } from '@/shared/stores/auth.store'

interface Props {
  zone: ZoneKPI
  isStale?: boolean
  /** Number of sensors on mock/simulated ESPs in this zone */
  mockSensorCount?: number
  healthConfig?: Record<ZoneHealthStatus, { label: string; colorClass: string }>
  rules?: LogicRule[]
  totalRuleCount?: number
  isRuleActive?: (ruleId: string) => boolean
  /** Editor-Link für zone-tile-Layout (Monitor L1); Klick stoppt Tile-Navigation */
  zoneTileEditorTo?: RouteLocationRaw | null
  /** Number of devices flapping (PKG-20) */
  flappingCount?: number
}

const props = withDefaults(defineProps<Props>(), {
  isStale: false,
  mockSensorCount: 0,
  healthConfig: () => DEFAULT_HEALTH_CONFIG,
  rules: () => [],
  totalRuleCount: 0,
  zoneTileEditorTo: null,
  flappingCount: 0,
})

const realSensorCount = computed(() =>
  Math.max(0, props.zone.sensorCount - props.mockSensorCount)
)

const authStore = useAuthStore()

const MAX_DISPLAYED_RULES = 2

const displayedRules = computed(() => props.rules.slice(0, MAX_DISPLAYED_RULES))

const hasAnyActiveRule = computed(() => {
  if (!props.isRuleActive || !props.rules.length) return false
  return props.rules.some(r => props.isRuleActive!(r.id))
})

const hasAnyFailedRule = computed(() =>
  props.rules.some(r => r.last_execution_success === false || r.degraded_since != null)
)

const extraRuleCount = computed(() => {
  return Math.max(0, props.totalRuleCount - MAX_DISPLAYED_RULES)
})

const emit = defineEmits<{
  (e: 'click', zoneId: string): void
}>()

function handleClick(): void {
  emit('click', props.zone.zoneId)
}

function formatKpiNumber(st: ZoneKPI['aggregation']['sensorTypes'][number]): string {
  if (st.count === 0) return '—'
  return formatNumber(st.avg, st.decimals, '—')
}

/** KPI-Zeile = Zonenmittel (Ø); Zoneinsight darunter = VPD + 24h-Spanne (kein zweites Klima-Tacho als Standard). */
const ZONE_KPI_GROUP_TOOLTIP =
  'Zonenmittel (Ø): Mittelwert je Kategorie über die Zone; veraltete Werte werden ausgeschlossen. Zoneinsight nutzt dieselbe Ø-Quelle für VPD (T/RH) und eine 24h-Min–Max-Spanne für einen Leittemperatursensor.'

const ZONE_KPI_GROUP_ARIA =
  'Zonenmittel, Durchschnitt pro Kategorie. Zoneinsight: Vapor Pressure Deficit und Temperaturspanne 24 Stunden.'
</script>

<template>
  <button
    :class="['monitor-zone-tile', `monitor-zone-tile--${zone.healthStatus}`]"
    @click="handleClick"
  >
    <!-- Header: Zone Name + Editor (zone-tile) + Status Ampel -->
    <div class="monitor-zone-tile__header">
      <h3 class="monitor-zone-tile__name">{{ zone.zoneName }}</h3>
      <div class="monitor-zone-tile__header-actions">
        <RouterLink
          v-if="zoneTileEditorTo && authStore.isAuthenticated"
          :to="zoneTileEditorTo"
          class="monitor-zone-tile__editor"
          title="Zone-Kachel-Dashboard im Editor anpassen"
          aria-label="Zone-Kachel-Dashboard im Editor anpassen"
          @click.stop
        >
          <Pencil class="monitor-zone-tile__editor-icon" />
        </RouterLink>
        <StatusBadge
          :level="zoneHealthToLevel(zone.healthStatus)"
          :label-override="healthConfig[zone.healthStatus].label"
        />
      </div>
    </div>
    <!-- Health Reason (only for warning/alarm) -->
    <div v-if="zone.healthReason" class="monitor-zone-tile__reason">
      {{ zone.healthReason }}
    </div>

    <!-- Flapping Badge (PKG-20) -->
    <div v-if="flappingCount > 0" class="monitor-zone-tile__flapping">
      <AlertTriangle class="w-3 h-3" />
      <span>{{ flappingCount }} {{ flappingCount === 1 ? 'Gerät' : 'Geräte' }} instabil</span>
    </div>

    <!-- KPIs from aggregateZoneSensors -->
    <slot name="kpis">
      <div
        v-if="zone.aggregation.sensorTypes.length > 0"
        class="monitor-zone-tile__kpis"
        role="group"
        :title="ZONE_KPI_GROUP_TOOLTIP"
        :aria-label="ZONE_KPI_GROUP_ARIA"
      >
        <div
          v-for="st in zone.aggregation.sensorTypes"
          :key="st.type"
          class="monitor-zone-tile__kpi"
        >
          <span class="monitor-zone-tile__kpi-label">{{ st.label }}</span>
          <span class="monitor-zone-tile__kpi-value">
            <span class="monitor-zone-tile__kpi-avg">Ø</span>
            <span class="monitor-zone-tile__kpi-number">{{ formatKpiNumber(st) }}</span>
            <span class="monitor-zone-tile__kpi-unit">{{ st.unit }}</span>
          </span>
        </div>
      </div>
      <div v-else class="monitor-zone-tile__kpis-empty">
        Keine Sensordaten
      </div>
    </slot>

    <!-- Extra slot (for Phase 3 mini-widgets) -->
    <slot name="extra" />

    <!-- Rules Summary (L1 compact, max 2 rules) -->
    <div v-if="totalRuleCount > 0" class="monitor-zone-tile__rules-summary">
      <div class="monitor-zone-tile__rules-header">
        <div class="monitor-zone-tile__rules-title">
          <Zap class="w-3 h-3" />
          <span :class="{ 'monitor-zone-tile__rules-label--active': hasAnyActiveRule }">Regeln</span>
        </div>
        <div class="monitor-zone-tile__rules-badges">
          <span v-if="hasAnyFailedRule" class="monitor-zone-tile__rules-error-dot" aria-label="Mindestens eine Regel hat einen Fehler" title="Mindestens eine Regel hat einen Fehler" />
          <span class="monitor-zone-tile__rules-count">
            {{ totalRuleCount }}
          </span>
        </div>
      </div>
      <span class="monitor-zone-tile__rules-hint">Automationen in dieser Zone</span>
      <div v-for="rule in displayedRules" :key="rule.id" :class="['monitor-zone-tile__rule', { 'monitor-zone-tile__rule--active': isRuleActive?.(rule.id) }]">
        <span class="monitor-zone-tile__rule-name" :title="rule.name">{{ rule.name }}</span>
      </div>
      <span v-if="extraRuleCount > 0" class="monitor-zone-tile__rules-extra">
        + {{ extraRuleCount }} weitere {{ extraRuleCount === 1 ? 'Regel' : 'Regeln' }}
      </span>
    </div>

    <!-- Footer: ESP-Count + Sensor/Actuator Counts + Last Activity -->
    <slot name="footer">
      <div class="monitor-zone-tile__footer">
        <div class="monitor-zone-tile__counts">
          <span class="monitor-zone-tile__count">
            Geraete: {{ zone.totalDevices > 0 ? `${zone.onlineDevices}/${zone.totalDevices} online` : '—' }}
          </span>
          <span :class="['monitor-zone-tile__count', {
            'monitor-zone-tile__count--ok': zone.activeSensors === zone.sensorCount && zone.sensorCount > 0,
            'monitor-zone-tile__count--warn': zone.activeSensors < zone.sensorCount && zone.activeSensors > 0,
            'monitor-zone-tile__count--alarm': zone.sensorCount > 0 && zone.activeSensors === 0,
          }]">
            Sensoren: {{ zone.activeSensors }}/{{ zone.sensorCount }} aktiv
          </span>
          <span v-if="mockSensorCount > 0" class="monitor-zone-tile__count monitor-zone-tile__count--mock-split">
            {{ realSensorCount }} Real · {{ mockSensorCount }} Sim
          </span>
          <span :class="['monitor-zone-tile__count', {
            'monitor-zone-tile__count--ok': zone.activeActuators > 0,
          }]">
            Aktoren: {{ zone.activeActuators }}/{{ zone.actuatorCount }} aktiv
          </span>
          <span v-if="zone.mobileGuestCount > 0" class="monitor-zone-tile__count monitor-zone-tile__count--mobile">
            Mobil: + {{ zone.mobileGuestCount }}
          </span>
        </div>
      </div>
    </slot>
  </button>
</template>

<style scoped>
.monitor-zone-tile {
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  cursor: pointer;
  transition: all var(--transition-base);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  border-left: 3px solid var(--glass-border);
  /* Reset button defaults */
  font: inherit;
  color: inherit;
  text-align: left;
  width: 100%;
}

.monitor-zone-tile:focus-visible {
  outline: 2px solid var(--color-iridescent-2);
  outline-offset: 2px;
}

.monitor-zone-tile--ok {
  border-left-color: var(--color-success);
}

.monitor-zone-tile--warning {
  border-left-color: var(--color-warning);
}

.monitor-zone-tile--alarm {
  border-left-color: var(--color-error);
}

.monitor-zone-tile:hover {
  border-color: var(--color-accent);
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
}

.monitor-zone-tile__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-2);
}

.monitor-zone-tile__header-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.monitor-zone-tile__editor {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 44px;
  min-height: 44px;
  margin: calc(-1 * var(--space-2));
  color: var(--color-text-muted);
  border-radius: var(--radius-sm);
  text-decoration: none;
}

.monitor-zone-tile__editor:hover,
.monitor-zone-tile__editor:focus-visible {
  color: var(--color-iridescent-2);
  outline: none;
  box-shadow: 0 0 0 2px var(--color-iridescent-2);
}

.monitor-zone-tile__editor-icon {
  width: 18px;
  height: 18px;
}

@media (hover: none) {
  .monitor-zone-tile__editor {
    color: var(--color-text-secondary);
  }
}

.monitor-zone-tile__name {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
  white-space: normal;
  line-height: 1.25;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  flex: 1;
}

/* Status Ampel: Farbe + Text + Icon (doppelte Kodierung) */
.monitor-zone-tile__status {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
  align-self: flex-start;
}

.zone-status--ok {
  color: var(--color-success);
}

.zone-status--warning {
  color: var(--color-warning);
}

.zone-status--alarm {
  color: var(--color-error);
}

.zone-status--empty {
  color: var(--color-text-muted);
}

.monitor-zone-tile--empty {
  opacity: 0.7;
  border-style: dashed;
}

.monitor-zone-tile__reason {
  font-size: var(--text-xs, 11px);
  color: var(--color-text-muted);
  margin-top: calc(-1 * var(--space-2));
  padding: 0 var(--space-1);
}

.monitor-zone-tile--warning .monitor-zone-tile__reason {
  color: var(--color-warning);
  opacity: 0.85;
}

.monitor-zone-tile--alarm .monitor-zone-tile__reason {
  color: var(--color-error);
  opacity: 0.85;
}

/* Flapping Badge (PKG-20) */
.monitor-zone-tile__flapping {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: 2px var(--space-2);
  border-radius: var(--radius-sm);
  background: rgba(251, 191, 36, 0.1);
  border: 1px solid rgba(251, 191, 36, 0.25);
  color: var(--color-warning);
  font-size: var(--text-xs, 11px);
  font-weight: 500;
  animation: flapping-zone-pulse 2.5s ease-in-out infinite;
}

@keyframes flapping-zone-pulse {
  0%, 100% { opacity: 1; border-color: rgba(251, 191, 36, 0.25); }
  50% { opacity: 0.7; border-color: rgba(251, 191, 36, 0.5); }
}

@media (prefers-reduced-motion: reduce) {
  .monitor-zone-tile__flapping {
    animation: none;
  }
}

/* KPIs */
.monitor-zone-tile__kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(110px, 100%), 1fr));
  gap: var(--space-2);
}

.monitor-zone-tile__kpi {
  display: flex;
  flex-direction: column;
  gap: 1px; /* no token for 1px — smallest is --space-1 (4px) */
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: var(--glass-bg);
  padding: var(--space-3);
  min-height: 64px;
  justify-content: center;
  min-width: 0;
}

.monitor-zone-tile__kpi-label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.monitor-zone-tile__kpi-value {
  display: inline-flex;
  align-items: baseline;
  gap: var(--space-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: var(--font-mono);
  color: var(--color-text-primary);
  line-height: 1.2;
  min-width: 0;
}

.monitor-zone-tile__kpi-number {
  font-size: var(--text-xl);
  font-weight: 700;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.monitor-zone-tile__kpi-avg {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  font-weight: 600;
}

.monitor-zone-tile__kpi-unit {
  font-size: var(--text-base);
  color: var(--color-text-secondary);
  flex: 0 0 auto;
}

.monitor-zone-tile__kpis-empty {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-style: italic;
}

/* Footer: counts + activity — margin-top: auto pushes footer to bottom in equal-height tiles */
.monitor-zone-tile__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding-top: var(--space-2);
  border-top: 1px solid var(--glass-border-hover);
  margin-top: auto;
}

.monitor-zone-tile__counts {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-1) var(--space-2);
  font-size: var(--text-xs);
  min-width: 0;
}

.monitor-zone-tile__count {
  color: var(--color-text-muted);
  white-space: nowrap;
  flex: 0 0 auto;
}

.monitor-zone-tile__count--ok {
  color: var(--color-success);
}

.monitor-zone-tile__count--warn {
  color: var(--color-warning);
}

.monitor-zone-tile__count--alarm {
  color: var(--color-error);
}

.monitor-zone-tile__count--mobile {
  color: var(--color-text-secondary);
  font-style: italic;
}

.monitor-zone-tile__count--mock-split {
  color: var(--color-mock);
  font-size: var(--text-xxs);
}

/* Rules Summary */
.monitor-zone-tile__rules-summary {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--text-xs);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: var(--glass-bg);
  padding: var(--space-2) var(--space-3);
}

.monitor-zone-tile__rules-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.monitor-zone-tile__rules-title {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  color: var(--color-text-muted);
}

.monitor-zone-tile__rules-label--active {
  color: var(--color-info);
}

.monitor-zone-tile__rules-badges {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
}

.monitor-zone-tile__rules-error-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-error);
  flex-shrink: 0;
}

.monitor-zone-tile__rules-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 18px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  font-size: var(--text-xs);
  font-weight: 700;
  color: var(--color-text-secondary);
}

.monitor-zone-tile__rules-hint {
  color: var(--color-text-muted);
}

.monitor-zone-tile__rule {
  position: relative;
  padding-left: calc(12px + var(--space-2));
  color: var(--color-text-muted);
  transition: all var(--transition-fast);
}

.monitor-zone-tile__rule::before {
  content: '•';
  position: absolute;
  left: var(--space-1);
  color: var(--color-text-muted);
}

.monitor-zone-tile__rule--active {
  color: var(--color-text-secondary);
  text-shadow: 0 0 8px rgba(96, 165, 250, 0.4);
}

.monitor-zone-tile__rule--active::before {
  color: var(--color-info);
}

.monitor-zone-tile__rule-name {
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.monitor-zone-tile__rules-extra {
  padding-left: calc(12px + var(--space-2));
  color: var(--color-text-muted);
  font-style: italic;
}

@media (max-width: 900px) {
  .monitor-zone-tile__kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .monitor-zone-tile__kpis {
    grid-template-columns: 1fr;
  }
}

</style>
