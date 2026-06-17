<script setup lang="ts">
/**
 * ClimateRuleHealthWidget — Climate cockpit tile for a single critical rule.
 *
 * Displays the latest `rule.health` snapshot from the server:
 *  - Header: rule name, critical badge, time-window indicator
 *  - KPI row: setpoint, current value, deviation, target ESP status
 *  - Footer: last dispatch / offline duration
 *  - Border highlight when the rule is in the `degraded` state
 *
 * Data is read reactively from `useRuleHealthStore`. The widget itself
 * performs no HTTP calls — the store owns the WebSocket subscription.
 *
 * AUT-115
 */

import { computed } from 'vue'
import { AlertTriangle, Clock, Wifi, WifiOff, ThermometerSun } from 'lucide-vue-next'
import { useRuleHealthStore, type RuleHealthPayload } from '@/shared/stores/ruleHealth.store'
import { formatRelativeTime } from '@/utils/formatters'

// =============================================================================
// Props
// =============================================================================

interface Props {
  ruleId: number
  title?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: undefined,
})

// =============================================================================
// Constants
// =============================================================================

/** Deviation thresholds for color-coding the |deviation| value. */
const DEVIATION_OK_THRESHOLD = 1
const DEVIATION_WARN_THRESHOLD = 2

// =============================================================================
// Store
// =============================================================================

const ruleHealthStore = useRuleHealthStore()

const ruleHealth = computed<RuleHealthPayload | undefined>(() =>
  ruleHealthStore.getRuleHealth(props.ruleId),
)

// =============================================================================
// Computed
// =============================================================================

const isLoading = computed<boolean>(() => ruleHealth.value == null)

const displayTitle = computed<string>(() => {
  if (props.title) return props.title
  return ruleHealth.value?.rule_name ?? 'Klima-Regel'
})

const isCritical = computed<boolean>(() => ruleHealth.value?.is_critical === true)

const isDegraded = computed<boolean>(() => ruleHealth.value?.degraded_since != null)

const timeWindowActive = computed<string | null>(
  () => ruleHealth.value?.time_window_active ?? null,
)

/** 'ok' | 'warn' | 'alarm' | 'unknown' — drives deviation color. */
const deviationStatus = computed<'ok' | 'warn' | 'alarm' | 'unknown'>(() => {
  const dev = ruleHealth.value?.deviation
  if (dev == null) return 'unknown'
  const abs = Math.abs(dev)
  if (abs < DEVIATION_OK_THRESHOLD) return 'ok'
  if (abs < DEVIATION_WARN_THRESHOLD) return 'warn'
  return 'alarm'
})

const espOnline = computed<boolean>(() => ruleHealth.value?.target_esp_online === true)

const espHasTarget = computed<boolean>(() => ruleHealth.value?.target_esp_id != null)

const espOfflineSince = computed<string | null>(
  () => ruleHealth.value?.target_esp_offline_since ?? null,
)

const lastDispatch = computed(() => ruleHealth.value?.last_dispatch ?? null)
const lastSkip = computed(() => ruleHealth.value?.last_skip ?? null)
const degradedSince = computed<string | null>(
  () => ruleHealth.value?.degraded_since ?? null,
)

// =============================================================================
// Formatters
// =============================================================================

function formatNumber(value: number | null | undefined, decimals = 1): string {
  if (value == null || Number.isNaN(value)) return '–'
  return value.toFixed(decimals)
}

function formatDeviation(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '–'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}`
}
</script>

<template>
  <div
    class="climate-rule-health-widget"
    :class="{ 'climate-rule-health-widget--degraded': isDegraded }"
  >
    <!-- Loading / no data yet -->
    <div v-if="isLoading" class="climate-rule-health-widget__loading">
      <ThermometerSun class="climate-rule-health-widget__loading-icon" />
      <span>Warte auf Regelstatus…</span>
    </div>

    <template v-else>
      <!-- Header -->
      <header class="climate-rule-health-widget__header">
        <div class="climate-rule-health-widget__title-group">
          <ThermometerSun class="climate-rule-health-widget__title-icon" />
          <h3 class="climate-rule-health-widget__title" :title="displayTitle">
            {{ displayTitle }}
          </h3>
        </div>
        <div class="climate-rule-health-widget__badges">
          <span
            v-if="isCritical"
            class="climate-rule-health-widget__badge climate-rule-health-widget__badge--critical"
          >
            <AlertTriangle class="climate-rule-health-widget__badge-icon" />
            Kritisch
          </span>
          <span
            v-if="timeWindowActive"
            class="climate-rule-health-widget__badge climate-rule-health-widget__badge--info"
            :title="`Aktives Zeitfenster: ${timeWindowActive}`"
          >
            <Clock class="climate-rule-health-widget__badge-icon" />
            {{ timeWindowActive }}
          </span>
        </div>
      </header>

      <!-- KPI Row -->
      <div class="climate-rule-health-widget__kpis">
        <!-- Setpoint -->
        <div class="climate-rule-health-widget__kpi">
          <span class="climate-rule-health-widget__kpi-label">Soll</span>
          <span class="climate-rule-health-widget__kpi-value">
            {{ formatNumber(ruleHealth?.setpoint ?? null) }}
          </span>
        </div>

        <!-- Current value -->
        <div class="climate-rule-health-widget__kpi">
          <span class="climate-rule-health-widget__kpi-label">IST</span>
          <span class="climate-rule-health-widget__kpi-value">
            {{ formatNumber(ruleHealth?.current_value ?? null) }}
          </span>
        </div>

        <!-- Deviation -->
        <div class="climate-rule-health-widget__kpi">
          <span class="climate-rule-health-widget__kpi-label">Δ</span>
          <span
            class="climate-rule-health-widget__kpi-value"
            :class="[
              `climate-rule-health-widget__kpi-value--${deviationStatus}`,
            ]"
          >
            {{ formatDeviation(ruleHealth?.deviation ?? null) }}
          </span>
        </div>

        <!-- ESP status -->
        <div class="climate-rule-health-widget__kpi">
          <span class="climate-rule-health-widget__kpi-label">ESP</span>
          <span
            v-if="!espHasTarget"
            class="climate-rule-health-widget__esp climate-rule-health-widget__esp--unknown"
          >
            <span class="climate-rule-health-widget__esp-dot" />
            <span class="climate-rule-health-widget__esp-text">–</span>
          </span>
          <span
            v-else-if="espOnline"
            class="climate-rule-health-widget__esp climate-rule-health-widget__esp--online"
          >
            <Wifi class="climate-rule-health-widget__esp-icon" />
            <span class="climate-rule-health-widget__esp-text">Online</span>
          </span>
          <span
            v-else
            class="climate-rule-health-widget__esp climate-rule-health-widget__esp--offline"
            :title="espOfflineSince ? `Offline seit ${espOfflineSince}` : 'Offline'"
          >
            <WifiOff class="climate-rule-health-widget__esp-icon" />
            <span class="climate-rule-health-widget__esp-text">
              {{ espOfflineSince ? formatRelativeTime(espOfflineSince) : 'Offline' }}
            </span>
          </span>
        </div>
      </div>

      <!-- Footer: last dispatch / skip / degraded -->
      <footer class="climate-rule-health-widget__footer">
        <div
          v-if="isDegraded && degradedSince"
          class="climate-rule-health-widget__footer-line climate-rule-health-widget__footer-line--error"
        >
          <AlertTriangle class="climate-rule-health-widget__footer-icon" />
          <span>Degraded seit {{ formatRelativeTime(degradedSince) }}</span>
        </div>
        <div
          v-else-if="lastDispatch"
          class="climate-rule-health-widget__footer-line"
        >
          <Clock class="climate-rule-health-widget__footer-icon" />
          <span>
            {{ lastDispatch.command }} ({{ lastDispatch.state }}) ·
            {{ formatRelativeTime(lastDispatch.ts) }}
          </span>
        </div>
        <div
          v-else-if="lastSkip"
          class="climate-rule-health-widget__footer-line climate-rule-health-widget__footer-line--muted"
        >
          <span>
            Übersprungen ({{ lastSkip.consecutive_count }}×): {{ lastSkip.reason }}
          </span>
        </div>
        <div
          v-else
          class="climate-rule-health-widget__footer-line climate-rule-health-widget__footer-line--muted"
        >
          <span>Noch keine Aktivität</span>
        </div>
      </footer>
    </template>
  </div>
</template>

<style scoped>
.climate-rule-health-widget {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  height: 100%;
  padding: var(--space-3);
  background: var(--color-bg-card, var(--color-bg-secondary));
  border: 1px solid var(--color-border, var(--glass-border));
  border-radius: var(--radius-md);
  box-sizing: border-box;
  overflow: hidden;
}

.climate-rule-health-widget--degraded {
  border: 2px solid var(--color-error);
}

/* ---------- Loading ---------- */

.climate-rule-health-widget__loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  height: 100%;
  color: var(--color-text-secondary, var(--color-text-muted));
  font-size: var(--text-sm);
}

.climate-rule-health-widget__loading-icon {
  width: 24px;
  height: 24px;
  opacity: 0.4;
}

/* ---------- Header ---------- */

.climate-rule-health-widget__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.climate-rule-health-widget__title-group {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}

.climate-rule-health-widget__title-icon {
  width: 18px;
  height: 18px;
  color: var(--color-info);
  flex-shrink: 0;
}

.climate-rule-health-widget__title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.climate-rule-health-widget__badges {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  flex-shrink: 0;
}

.climate-rule-health-widget__badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px var(--space-2);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: 600;
  white-space: nowrap;
}

.climate-rule-health-widget__badge-icon {
  width: 12px;
  height: 12px;
}

.climate-rule-health-widget__badge--critical {
  background: color-mix(in srgb, var(--color-error) 18%, transparent);
  color: var(--color-error);
  border: 1px solid color-mix(in srgb, var(--color-error) 35%, transparent);
}

.climate-rule-health-widget__badge--info {
  background: color-mix(in srgb, var(--color-info) 18%, transparent);
  color: var(--color-info);
  border: 1px solid color-mix(in srgb, var(--color-info) 35%, transparent);
}

/* ---------- KPI Row ---------- */

.climate-rule-health-widget__kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-2);
  flex: 1;
  min-height: 0;
}

.climate-rule-health-widget__kpi {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-1);
  padding: var(--space-2);
  background: var(--color-bg-tertiary, transparent);
  border-radius: var(--radius-sm);
  min-width: 0;
}

.climate-rule-health-widget__kpi-label {
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  color: var(--color-text-secondary, var(--color-text-muted));
  letter-spacing: 0.04em;
}

.climate-rule-health-widget__kpi-value {
  font-size: var(--text-lg);
  font-weight: 700;
  font-family: var(--font-mono);
  color: var(--color-text-primary);
  line-height: 1;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.climate-rule-health-widget__kpi-value--ok {
  color: var(--color-success);
}

.climate-rule-health-widget__kpi-value--warn {
  color: var(--color-warning);
}

.climate-rule-health-widget__kpi-value--alarm {
  color: var(--color-error);
}

.climate-rule-health-widget__kpi-value--unknown {
  color: var(--color-text-secondary, var(--color-text-muted));
}

/* ---------- ESP indicator ---------- */

.climate-rule-health-widget__esp {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--text-xs);
  font-weight: 600;
  max-width: 100%;
  overflow: hidden;
}

.climate-rule-health-widget__esp-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.climate-rule-health-widget__esp-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-text-secondary, var(--color-text-muted));
  flex-shrink: 0;
}

.climate-rule-health-widget__esp-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.climate-rule-health-widget__esp--online {
  color: var(--color-success);
}

.climate-rule-health-widget__esp--offline {
  color: var(--color-error);
}

.climate-rule-health-widget__esp--unknown {
  color: var(--color-text-secondary, var(--color-text-muted));
}

/* ---------- Footer ---------- */

.climate-rule-health-widget__footer {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: var(--text-xs);
  color: var(--color-text-secondary, var(--color-text-muted));
  border-top: 1px solid var(--color-border, var(--glass-border));
  padding-top: var(--space-2);
  flex-shrink: 0;
}

.climate-rule-health-widget__footer-line {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.climate-rule-health-widget__footer-line--error {
  color: var(--color-error);
  font-weight: 600;
}

.climate-rule-health-widget__footer-line--muted {
  opacity: 0.7;
}

.climate-rule-health-widget__footer-icon {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
}
</style>
