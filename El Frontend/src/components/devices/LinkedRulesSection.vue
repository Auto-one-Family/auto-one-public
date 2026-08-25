<script setup lang="ts">
/**
 * LinkedRulesSection — Display of Logic Rules linked to a sensor/actuator
 *
 * Berechtigte Ausnahme von RuleCardCompact — Chip/Listen-Ansicht im Geräte-Kontext (AUT-648 D3).
 * Zeigt verknüpfte Regeln als kompakte Chips/Einträge; keine vollständige Rule-Card.
 *
 * Sensor mode (deviceType='sensor'): Uses logicStore.connections (one entry per
 * sensor->actuator pair). Compact list with cross-ESP indicator.
 *
 * Actuator mode (deviceType='actuator'): AUT-256 — Rule-level rich rendering
 * via logicStore.getRulesForActuator(). Shows for each rule:
 *  - Name, enabled/disabled StatusBadge
 *  - Priority (lower = higher precedence in conflict manager)
 *  - Cooldown
 *  - Active time-window if present (e.g. "22:00-06:00")
 *  - Compact condition summary
 *  - Sorted by priority (ascending = highest first)
 * Footer warning pill when 2+ enabled rules target the actuator.
 */
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Link2, ArrowRight, ExternalLink, AlertTriangle, Clock, Gauge } from 'lucide-vue-next'
import { useLogicStore } from '@/shared/stores/logic.store'
import { getRuleReadableText } from '@/composables/useRuleReadableText'
import type { LogicRule, TimeCondition } from '@/types/logic'
import StatusBadge from '@/components/base/StatusBadge.vue'

interface Props {
  espId: string
  gpio: number
  deviceType: 'sensor' | 'actuator'
}

const props = defineProps<Props>()
const router = useRouter()
const logicStore = useLogicStore()

// =============================================================================
// Sensor mode (legacy: connections-based)
// =============================================================================
const linkedConnections = computed(() => {
  return logicStore.connections.filter((c) => {
    if (props.deviceType === 'sensor') {
      return c.sourceEspId === props.espId && c.sourceGpio === props.gpio
    }
    return c.targetEspId === props.espId && c.targetGpio === props.gpio
  })
})

// =============================================================================
// Actuator mode (AUT-256: rule-level rendering)
// =============================================================================
const actuatorRules = computed<LogicRule[]>(() =>
  props.deviceType === 'actuator'
    ? logicStore.getRulesForActuator(props.espId, props.gpio)
    : []
)

const activeActuatorRuleCount = computed(() =>
  actuatorRules.value.filter((r) => r.enabled).length
)

/** Find first time_window/time condition in a rule's flat condition list. */
function findTimeWindow(rule: LogicRule): TimeCondition | null {
  for (const cond of rule.conditions ?? []) {
    if (cond.type === 'time_window' || cond.type === 'time') {
      return cond as TimeCondition
    }
  }
  return null
}

function formatTimeWindow(tc: TimeCondition): string {
  const sh = String(tc.start_hour).padStart(2, '0')
  const sm = String(tc.start_minute ?? 0).padStart(2, '0')
  const eh = String(tc.end_hour).padStart(2, '0')
  const em = String(tc.end_minute ?? 0).padStart(2, '0')
  return `${sh}:${sm}-${eh}:${em}`
}

function formatCooldown(seconds: number | undefined): string | null {
  if (seconds == null || seconds <= 0) return null
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  return `${Math.round(seconds / 3600)}h`
}

function navigateToRuleId(ruleId: string) {
  router.push({ name: 'logic-rule', params: { ruleId } })
}

onMounted(() => {
  if (logicStore.rules.length === 0) {
    logicStore.fetchRules()
  }
})
</script>

<template>
  <div class="linked-rules">
    <!-- ─────────────────────────────────────────────────────────────────
         ACTUATOR MODE (AUT-256): Rule-level rich list + conflict warning
         ───────────────────────────────────────────────────────────────── -->
    <template v-if="deviceType === 'actuator'">
      <!-- Empty State -->
      <div v-if="actuatorRules.length === 0" class="linked-rules__empty">
        <Link2 class="w-5 h-5" style="color: var(--color-text-muted)" />
        <p class="linked-rules__empty-text">Keine verknüpften Regeln</p>
        <p class="linked-rules__empty-hint">
          Regeln können im Regeln-Tab erstellt werden
        </p>
      </div>

      <!-- Rule list -->
      <div v-else class="linked-rules__list">
        <button
          v-for="(rule, idx) in actuatorRules"
          :key="rule.id"
          class="linked-rules__rule"
          :class="{ 'linked-rules__rule--disabled': !rule.enabled, 'linked-rules__rule--active': rule.enabled }"
          @click="navigateToRuleId(rule.id)"
        >
          <div class="linked-rules__rule-header">
            <span class="linked-rules__rule-index">{{ idx + 1 }}.</span>
            <span class="linked-rules__rule-name">{{ rule.name }}</span>
            <StatusBadge
              :level="rule.enabled ? 'ok' : 'offline'"
              compact
            />
          </div>

          <div class="linked-rules__rule-meta">
            <span class="linked-rules__chip" :title="`Priority ${rule.priority} (kleinere Zahl = höhere Priorität)`">
              <Gauge class="w-3 h-3" />
              Priority: {{ rule.priority }}
            </span>
            <span
              v-if="formatCooldown(rule.cooldown_seconds)"
              class="linked-rules__chip"
              title="Regel-Cooldown: Mindestabstand zwischen zwei Auslösungen DIESER Regel (Ebene: Logic-Engine, gilt nur für diese Regel). Der Aktor-Cooldown (Geräte-Ebene) ist separat konfiguriert."
            >
              <Clock class="w-3 h-3" />
              Regel-Pause: {{ formatCooldown(rule.cooldown_seconds) }}
            </span>
            <span
              v-if="findTimeWindow(rule)"
              class="linked-rules__chip"
              title="Aktives Zeitfenster"
            >
              <Clock class="w-3 h-3" />
              Zeit: {{ formatTimeWindow(findTimeWindow(rule)!) }}
            </span>
          </div>

          <p class="linked-rules__rule-condition">
            {{ getRuleReadableText(rule) }}
          </p>
        </button>
      </div>

      <!-- Conflict warning pill (>= 2 active rules target this actuator) -->
      <div
        v-if="activeActuatorRuleCount >= 2"
        class="linked-rules__warning"
        role="status"
      >
        <AlertTriangle class="w-3.5 h-3.5" />
        <span>{{ activeActuatorRuleCount }} aktive Regeln steuern diesen Aktor.</span>
      </div>
    </template>

    <!-- ─────────────────────────────────────────────────────────────────
         SENSOR MODE (legacy: connection-based list)
         ───────────────────────────────────────────────────────────────── -->
    <template v-else>
      <div v-if="linkedConnections.length === 0" class="linked-rules__empty">
        <Link2 class="w-5 h-5" style="color: var(--color-text-muted)" />
        <p class="linked-rules__empty-text">Keine verknüpften Regeln</p>
        <p class="linked-rules__empty-hint">
          Regeln können im Regeln-Tab erstellt werden
        </p>
      </div>

      <div v-else class="linked-rules__list">
        <button
          v-for="rule in linkedConnections"
          :key="rule.ruleId"
          class="linked-rules__item"
          @click="navigateToRuleId(rule.ruleId)"
        >
          <div class="linked-rules__item-header">
            <span class="linked-rules__item-name">{{ rule.ruleName }}</span>
            <span
              :class="['badge', rule.enabled ? 'badge-success' : 'badge-gray']"
            >
              {{ rule.enabled ? 'Aktiv' : 'Inaktiv' }}
            </span>
          </div>
          <p class="linked-rules__item-desc">{{ rule.ruleDescription }}</p>
          <div class="linked-rules__item-meta">
            <span>{{ rule.sourceEspId }}:{{ rule.sourceGpio }}</span>
            <ArrowRight class="w-3 h-3" />
            <span>{{ rule.targetEspId }}:{{ rule.targetGpio }}</span>
            <span v-if="rule.isCrossEsp" class="badge badge-info linked-rules__cross-badge">
              Cross-ESP
            </span>
            <ExternalLink class="linked-rules__nav-icon" />
          </div>
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.linked-rules {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.linked-rules__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-4);
  text-align: center;
}

.linked-rules__empty-text {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  font-weight: 500;
  margin: 0;
}

.linked-rules__empty-hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin: 0;
}

.linked-rules__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

/* ============================================================================
   ACTUATOR MODE: Rule cards (AUT-256)
   ============================================================================ */

.linked-rules__rule {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3);
  background: var(--color-bg-quaternary, rgba(255, 255, 255, 0.04));
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  cursor: pointer;
  transition: all var(--transition-fast);
  text-align: left;
  width: 100%;
  color: inherit;
  font: inherit;
}

.linked-rules__rule:hover {
  border-color: var(--color-accent);
  background: rgba(59, 130, 246, 0.04);
}

.linked-rules__rule--active {
  border-left: 3px solid var(--color-success);
}

.linked-rules__rule--disabled {
  opacity: 0.55;
}

.linked-rules__rule-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.linked-rules__rule-index {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.linked-rules__rule-name {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.linked-rules__rule-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.linked-rules__chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--text-xxs);
  color: var(--color-text-secondary);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-xs);
  padding: 1px 6px;
  white-space: nowrap;
}

.linked-rules__rule-condition {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  line-height: var(--leading-normal);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.linked-rules__warning {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  border: 1px solid color-mix(in srgb, var(--color-warning) 30%, transparent);
  background: color-mix(in srgb, var(--color-warning) 8%, transparent);
  color: var(--color-warning);
  font-size: var(--text-xs);
  font-weight: 500;
}

/* ============================================================================
   SENSOR MODE (legacy)
   ============================================================================ */

.linked-rules__item {
  padding: var(--space-3);
  background: var(--color-bg-quaternary, rgba(255, 255, 255, 0.04));
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  cursor: pointer;
  transition: all var(--transition-fast);
  text-align: left;
  width: 100%;
  color: inherit;
  font: inherit;
}

.linked-rules__item:hover {
  border-color: var(--color-accent);
  background: rgba(59, 130, 246, 0.04);
}

.linked-rules__item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  margin-bottom: var(--space-1);
}

.linked-rules__item-name {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.linked-rules__item-desc {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  margin: 0 0 var(--space-2);
  line-height: 1.4;
}

.linked-rules__item-meta {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  color: var(--color-text-muted);
}

.linked-rules__cross-badge {
  font-family: var(--font-body);
  margin-left: var(--space-1);
}

.linked-rules__nav-icon {
  width: 12px;
  height: 12px;
  margin-left: auto;
  color: var(--color-text-muted);
  opacity: 0;
  transition: opacity var(--transition-fast);
}

.linked-rules__item:hover .linked-rules__nav-icon {
  opacity: 1;
  color: var(--color-accent-bright);
}
</style>
