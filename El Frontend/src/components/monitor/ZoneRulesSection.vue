<script setup lang="ts">
/**
 * ZoneRulesSection — Regeln für diese Zone (Monitor L2) oder zonenübergreifend (L1 aggregateMode).
 *
 * Normal mode (zoneId): zeigt Regeln der Zone via logicStore.getRulesForZone(zoneId).
 * aggregateMode=true: zeigt Top-5 enabled Regeln aller Zonen (Fehler-first → Priorität → Name).
 *   Read-Only: kein Toggle, kein Delete. Jede Zeile = Deep-Link /logic/:ruleId.
 *   Text via getRuleReadableText (AUT-661 kanonischer Renderer).
 *
 * AUT-663: useZoneKPIs.filteredZoneKPIs enthält keine Rule-Daten (AUT-647 Blocker).
 *   aggregateMode nutzt daher logicStore.rules (kein neuer API-Call, bereits via fetchRules geladen).
 */
import { computed, onMounted, watch } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import { Zap, ExternalLink } from 'lucide-vue-next'
import { useLogicStore } from '@/shared/stores/logic.store'
import { useEspStore } from '@/stores/esp'
import RuleCardCompact from '@/components/logic/RuleCardCompact.vue'
import { getRuleReadableText } from '@/composables/useRuleReadableText'
import { extractEspIdsFromRule } from '@/types/logic'
import { formatRelativeTime } from '@/utils/formatters'
import type { LogicRule } from '@/types/logic'

const RULES_VISIBLE_THRESHOLD = 10
const MAX_DISPLAYED_WHEN_OVER = 5
const MAX_AGGREGATE_RULES = 5

interface Props {
  zoneId?: string | null
  /** L1 aggregateMode: zonenübergreifende Top-5 Liste (Fehler-first, Read-Only, Deep-Link). */
  aggregateMode?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  zoneId: null,
  aggregateMode: false,
})

const logicStore = useLogicStore()
const espStore = useEspStore()
const router = useRouter()

// ---------------------------------------------------------------------------
// Normal mode: rules for a single zone
// ---------------------------------------------------------------------------

const rulesForZone = computed<LogicRule[]>(() => {
  if (!props.zoneId) return []
  return logicStore.getRulesForZone(props.zoneId)
})

const displayedRules = computed<LogicRule[]>(() => {
  const rules = rulesForZone.value
  if (rules.length <= RULES_VISIBLE_THRESHOLD) return rules
  return rules.slice(0, MAX_DISPLAYED_WHEN_OVER)
})

const hasMoreRules = computed(() => rulesForZone.value.length > RULES_VISIBLE_THRESHOLD)

const hiddenRulesCount = computed(() =>
  hasMoreRules.value ? rulesForZone.value.length - MAX_DISPLAYED_WHEN_OVER : 0
)

// ---------------------------------------------------------------------------
// Aggregate mode: Top-5 enabled rules across all zones (AUT-663 Maßnahme 2)
// Data source: logicStore.rules — kein neuer API-Call.
// useZoneKPIs.filteredZoneKPIs hat keine Rule-Daten → AUT-647 Blocker dokumentiert.
// ---------------------------------------------------------------------------

function ruleHasError(r: LogicRule): boolean {
  return r.last_execution_success === false || r.degraded_since != null
}

// AUT-669: Regel referenziert ESPs aus ≥2 verschiedenen Zonen (read-only, espStore).
// Edge-Case: ESP ohne zone_id wird nicht gezählt.
function isCrossZoneRule(rule: LogicRule): boolean {
  const espIds = extractEspIdsFromRule(rule)
  const zoneIds = new Set<string>()
  for (const espId of espIds) {
    const device = espStore.devices.find(d => (d.device_id || d.esp_id) === espId)
    if (device?.zone_id) {
      zoneIds.add(device.zone_id)
    }
  }
  return zoneIds.size >= 2
}

const aggregatedRules = computed<LogicRule[]>(() => {
  if (!props.aggregateMode) return []
  const enabled = logicStore.rules.filter(r => r.enabled)
  return [...enabled]
    .sort((a, b) => {
      const aErr = ruleHasError(a) ? 0 : 1
      const bErr = ruleHasError(b) ? 0 : 1
      if (aErr !== bErr) return aErr - bErr
      if (b.priority !== a.priority) return b.priority - a.priority
      return a.name.localeCompare(b.name, 'de')
    })
    .slice(0, MAX_AGGREGATE_RULES)
})

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

function goToLogicTab() {
  router.push({ name: 'logic' })
}

function isRuleActive(ruleId: string): boolean {
  return logicStore.isRuleActive(ruleId)
}

onMounted(() => {
  if (logicStore.rules.length === 0) {
    logicStore.fetchRules()
  }
})

watch(() => props.zoneId, (zoneId) => {
  if (zoneId && logicStore.rules.length === 0) {
    logicStore.fetchRules()
  }
})
</script>

<template>
  <section v-if="zoneId || aggregateMode" class="zone-rules-section monitor-section">

    <!-- ================================================================
         Aggregate Mode (L1): zonenübergreifende Top-5 Liste, Read-Only
         Text via getRuleReadableText (AUT-661), Deep-Link /logic/:ruleId
         ================================================================ -->
    <template v-if="aggregateMode">
      <div class="zone-rules-section__header">
        <h3 class="monitor-section__title">Aktive Regeln — Überblick ({{ aggregatedRules.length }})</h3>
        <span class="zone-rules-section__scope">Alle Zonen</span>
      </div>

      <div v-if="aggregatedRules.length === 0" class="zone-rules-section__empty">
        <Zap class="zone-rules-section__empty-icon" />
        <p class="zone-rules-section__empty-text">Keine aktiven Regeln</p>
        <button
          type="button"
          class="zone-rules-section__empty-link"
          aria-label="Zum Regeln-Tab navigieren"
          @click="goToLogicTab"
        >
          <ExternalLink class="zone-rules-section__empty-link-icon" />
          Regeln anlegen
        </button>
      </div>

      <ul v-else class="zone-rules-section__aggregate-list" role="list">
        <li
          v-for="rule in aggregatedRules"
          :key="rule.id"
          class="zone-rules-section__aggregate-item"
        >
          <RouterLink
            :to="`/logic/${rule.id}`"
            class="zone-rules-section__aggregate-row"
            :class="{
              'zone-rules-section__aggregate-row--error': ruleHasError(rule),
              'zone-rules-section__aggregate-row--active': isRuleActive(rule.id),
            }"
          >
            <div class="zone-rules-section__aggregate-top">
              <span class="zone-rules-section__aggregate-dot"></span>
              <span class="zone-rules-section__aggregate-name">{{ rule.name }}</span>
              <span v-if="isCrossZoneRule(rule)" class="zone-rules-section__cross-zone-badge">Zonenübergreifend</span>
              <span v-if="rule.last_triggered" class="zone-rules-section__aggregate-ts">{{ formatRelativeTime(rule.last_triggered) }}</span>
            </div>
            <span class="zone-rules-section__aggregate-text">{{ getRuleReadableText(rule) }}</span>
          </RouterLink>
        </li>
      </ul>
    </template>

    <!-- ================================================================
         Normal Mode (L2): Regeln einer Zone
         ================================================================ -->
    <template v-else>
      <div class="zone-rules-section__header">
        <h3 class="monitor-section__title">Zonenweite Regeln ({{ rulesForZone.length }})</h3>
        <span class="zone-rules-section__scope">Wirken auf ganze Zone</span>
      </div>

      <!-- Empty State -->
      <div
        v-if="rulesForZone.length === 0"
        class="zone-rules-section__empty"
      >
        <Zap class="zone-rules-section__empty-icon" />
        <p class="zone-rules-section__empty-text">Keine Automatisierungen für diese Zone</p>
        <p class="zone-rules-section__empty-hint">
          Regeln können im Regeln-Tab erstellt werden
        </p>
        <button
          type="button"
          class="zone-rules-section__empty-link"
          aria-label="Zum Regeln-Tab navigieren"
          @click="goToLogicTab"
        >
          <ExternalLink class="zone-rules-section__empty-link-icon" />
          Zum Regeln-Tab
        </button>
      </div>

      <!-- Rules Grid -->
      <div v-else class="zone-rules-section__content">
        <ul
          class="zone-rules-section__grid monitor-card-grid grid-auto-sm"
          role="list"
        >
          <li
            v-for="rule in displayedRules"
            :key="rule.id"
            class="zone-rules-section__grid-item"
          >
            <RuleCardCompact
              :rule="rule"
              :is-active="isRuleActive(rule.id)"
              :lifecycle="logicStore.getLifecycleEntry(rule.id)"
              :quick-actions="true"
            />
          </li>
        </ul>
        <div
          v-if="hasMoreRules"
          class="zone-rules-section__more"
        >
          <span class="zone-rules-section__more-text">
            Weitere {{ hiddenRulesCount }} Regeln
          </span>
          <button
            type="button"
            class="zone-rules-section__more-link"
            :aria-label="`Weitere ${hiddenRulesCount} Regeln im Regeln-Tab anzeigen`"
            @click="goToLogicTab"
          >
            <ExternalLink class="zone-rules-section__more-icon" />
            Im Regeln-Tab anzeigen
          </button>
        </div>
      </div>
    </template>

  </section>
</template>

<style scoped>
.zone-rules-section.monitor-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-bottom: 0;
  padding: var(--space-3);
  border: 1px solid var(--glass-border);
  border-left: 3px solid var(--color-info);
  border-radius: var(--radius-md);
  background: var(--glass-bg);
}

.zone-rules-section__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.monitor-section__title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  margin: 0;
}

.zone-rules-section__scope {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  padding: 2px 8px;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  background: var(--color-bg-secondary);
}

.zone-rules-section__content {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.zone-rules-section__grid {
  list-style: none;
  margin: 0;
  padding: 0;
}

.zone-rules-section__grid.monitor-card-grid {
  gap: var(--space-3);
}

.zone-rules-section__grid-item {
  min-width: 0;
}

.zone-rules-section__more {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-md);
}

.zone-rules-section__more-text {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.zone-rules-section__more-link {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-iridescent-2);
  background: none;
  border: none;
  cursor: pointer;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  transition: color var(--transition-fast);
}

.zone-rules-section__more-link:hover {
  color: var(--color-iridescent-1);
}

.zone-rules-section__more-link:focus-visible {
  outline: 2px solid var(--color-iridescent-2);
  outline-offset: 2px;
}

.zone-rules-section__more-icon {
  width: 14px;
  height: 14px;
}

.zone-rules-section__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-6) var(--space-4);
  background: var(--color-bg-secondary);
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
}

.zone-rules-section__empty-icon {
  width: 32px;
  height: 32px;
}

.zone-rules-section__empty-text {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-secondary);
  margin: 0;
}

.zone-rules-section__empty-hint {
  font-size: var(--text-xs);
  margin: 0;
}

.zone-rules-section__empty-link {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-iridescent-2);
  background: none;
  border: none;
  cursor: pointer;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  margin-top: var(--space-2);
  transition: color var(--transition-fast);
}

.zone-rules-section__empty-link:hover {
  color: var(--color-iridescent-1);
}

.zone-rules-section__empty-link:focus-visible {
  outline: 2px solid var(--color-iridescent-2);
  outline-offset: 2px;
}

.zone-rules-section__empty-link-icon {
  width: 14px;
  height: 14px;
}

/* ============================================================
   Aggregate Mode styles (L1 cross-zone overview, AUT-663)
   ============================================================ */

.zone-rules-section__aggregate-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.zone-rules-section__aggregate-item {
  min-width: 0;
}

.zone-rules-section__aggregate-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: var(--glass-bg);
  text-decoration: none;
  transition: border-color var(--transition-fast), background var(--transition-fast);
}

.zone-rules-section__aggregate-row:hover {
  border-color: var(--color-iridescent-2);
  background: var(--color-bg-secondary);
}

.zone-rules-section__aggregate-row:focus-visible {
  outline: 2px solid var(--color-iridescent-2);
  outline-offset: 2px;
}

.zone-rules-section__aggregate-row--error {
  border-left: 3px solid var(--color-error);
}

.zone-rules-section__aggregate-row--active {
  border-left: 3px solid var(--color-info);
}

.zone-rules-section__aggregate-top {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  min-width: 0;
}

.zone-rules-section__aggregate-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-text-muted);
  flex-shrink: 0;
}

.zone-rules-section__aggregate-row--error .zone-rules-section__aggregate-dot { background: var(--color-error); }
.zone-rules-section__aggregate-row--active .zone-rules-section__aggregate-dot { background: var(--color-info); }

.zone-rules-section__aggregate-ts {
  font-size: 10px;
  color: var(--color-text-muted);
  white-space: nowrap;
  margin-left: auto;
  flex-shrink: 0;
}

.zone-rules-section__aggregate-name {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}

.zone-rules-section__aggregate-text {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.zone-rules-section__cross-zone-badge {
  display: inline-flex;
  align-self: flex-start;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-info);
  font-size: 10px;
  font-weight: 500;
  color: var(--color-info);
  background: transparent;
  flex-shrink: 0;
}
</style>
