<script setup lang="ts">
/**
 * RuleGroupCard
 *
 * One card per rule group (e.g. "Temperatur — 4 Regeln").
 * Shows an always-visible rule list: checkbox + name/summary + status.
 *
 * Visual language (transferred from retired RuleTemplateCard):
 * - BaseCard glass+hoverable
 * - Per-group Lucide icon + token color (no hardcoded hex)
 * - Colored left accent border
 * - Count chip; no duplicate category badge next to the title
 * - Multi-line rule text (line-clamp 2) to avoid harsh truncation
 *
 * @see AUT-1147 / AUT-1149
 */

import { ref, computed } from 'vue'
import type { Component } from 'vue'
import {
  ShieldAlert,
  Settings,
  CheckSquare,
  Square,
  ExternalLink,
  Thermometer,
  Droplets,
  FlaskConical,
  Wind,
  Gauge,
  Sun,
  Waves,
  Moon,
} from 'lucide-vue-next'
import BaseCard from '@/shared/design/primitives/BaseCard.vue'
import StatusBadge from '@/components/base/StatusBadge.vue'
import { getRuleReadableText } from '@/composables/useRuleReadableText'
import { useLogicStore } from '@/shared/stores/logic.store'
import type { LogicRule, RuleGroup } from '@/types/logic'
import type { StatusLevel } from '@/utils/formatters'

// ── Props ─────────────────────────────────────────────────────────────────────

interface Props {
  /** Group key — one of RULE_GROUP_CATALOG */
  groupName: RuleGroup
  /**
   * Rules already pre-filtered to this group.
   * Grouping logic is the CALLER'S responsibility.
   */
  rules: LogicRule[]
  /**
   * Optional map: ruleId → human-readable target label (zone / device name).
   */
  targetLabels?: Map<string, string>
}

const props = withDefaults(defineProps<Props>(), {
  targetLabels: () => new Map(),
})

// ── Emits ─────────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  'update:selectedIds': [ids: string[]]
  'edit-rule': [ruleId: string]
}>()

// ── Icon / color / label per group (template visual DNA → real groups) ───────

const GROUP_ICON: Record<RuleGroup, Component> = {
  ph:           FlaskConical,
  ec:           Droplets,
  bodenfeuchte: Droplets,
  luftfeuchte:  Droplets,
  temperatur:   Thermometer,
  co2:          Wind,
  luftdruck:    Gauge,
  licht:        Sun,
  durchfluss:   Waves,
  zeitplan:     Moon,
  sicherheit:   ShieldAlert,
  sonstiges:    Settings,
}

const GROUP_ICON_COLOR: Record<RuleGroup, string> = {
  ph:           'var(--color-accent)',
  ec:           'var(--color-info)',
  bodenfeuchte: 'var(--color-success)',
  luftfeuchte:  'var(--color-iridescent-2)',
  temperatur:   'var(--color-warning)',
  co2:          'var(--color-iridescent-1)',
  luftdruck:    'var(--color-info)',
  licht:        'var(--color-warning)',
  durchfluss:   'var(--color-info)',
  zeitplan:     'var(--color-iridescent-3)',
  sicherheit:   'var(--color-error)',
  sonstiges:    'var(--color-text-muted)',
}

const GROUP_LABEL: Record<RuleGroup, string> = {
  ph:           'pH',
  ec:           'EC',
  bodenfeuchte: 'Bodenfeuchte',
  luftfeuchte:  'Luftfeuchte',
  temperatur:   'Temperatur',
  co2:          'CO2',
  luftdruck:    'Luftdruck',
  licht:        'Licht',
  durchfluss:   'Durchfluss',
  zeitplan:     'Zeitplan',
  sicherheit:   'Sicherheit',
  sonstiges:    'Sonstiges',
}

const groupIcon = computed<Component>(() => GROUP_ICON[props.groupName] ?? Settings)
const groupIconColor = computed<string>(
  () => GROUP_ICON_COLOR[props.groupName] ?? 'var(--color-text-muted)',
)
const groupLabel = computed<string>(() => GROUP_LABEL[props.groupName] ?? props.groupName)

// ── Rule status ───────────────────────────────────────────────────────────────

const logicStore = useLogicStore()

function ruleStatusLevel(rule: LogicRule): StatusLevel {
  if (!rule.enabled) return 'offline'
  if (logicStore.isRuleTriggered(rule.id)) return 'warning'
  return 'ok'
}

// ── Multi-selection ───────────────────────────────────────────────────────────

const selectedIds = ref<Set<string>>(new Set())

const selectedCount = computed<number>(() => selectedIds.value.size)

const allSelected = computed<boolean>(
  () => props.rules.length > 0 && props.rules.every(r => selectedIds.value.has(r.id)),
)

function toggleSelectAll(): void {
  if (allSelected.value) {
    selectedIds.value = new Set()
  } else {
    selectedIds.value = new Set(props.rules.map(r => r.id))
  }
  emit('update:selectedIds', [...selectedIds.value].sort())
}

function toggleRule(ruleId: string): void {
  const next = new Set(selectedIds.value)
  if (next.has(ruleId)) {
    next.delete(ruleId)
  } else {
    next.add(ruleId)
  }
  selectedIds.value = next
  emit('update:selectedIds', [...selectedIds.value].sort())
}

function handleEditRule(ruleId: string): void {
  emit('edit-rule', ruleId)
}
</script>

<template>
  <BaseCard glass hoverable>
    <div
      class="rule-group-card"
      :style="{ '--rule-group-accent': groupIconColor }"
    >
      <!-- ── Card Header ──────────────────────────────────────────────────── -->
      <div class="rule-group-card__header">
        <div class="rule-group-card__header-main">
          <component
            :is="groupIcon"
            class="rule-group-card__icon"
            :style="{ color: groupIconColor }"
            aria-hidden="true"
          />
          <h4 class="rule-group-card__name">{{ groupLabel }}</h4>
        </div>

        <div class="rule-group-card__header-actions">
          <span class="rule-group-card__count-chip">
            {{ rules.length }}&thinsp;{{ rules.length === 1 ? 'Regel' : 'Regeln' }}
          </span>

          <button
            v-if="rules.length > 0"
            type="button"
            class="rule-group-card__select-all"
            :title="allSelected ? 'Alle abwählen' : 'Alle auswählen'"
            :aria-label="allSelected ? 'Alle Regeln dieser Gruppe abwählen' : 'Alle Regeln dieser Gruppe auswählen'"
            @click="toggleSelectAll"
          >
            <CheckSquare
              v-if="allSelected"
              class="rule-group-card__select-all-icon"
              aria-hidden="true"
            />
            <Square
              v-else
              class="rule-group-card__select-all-icon"
              aria-hidden="true"
            />
          </button>
        </div>
      </div>

      <!-- ── Rule List ────────────────────────────────────────────────────── -->
      <ul
        v-if="rules.length > 0"
        class="rule-group-card__rule-list"
        :aria-label="`Regeln in Gruppe ${groupLabel}`"
      >
        <li
          v-for="rule in rules"
          :key="rule.id"
          class="rule-group-card__rule-row"
          :class="{ 'rule-group-card__rule-row--selected': selectedIds.has(rule.id) }"
        >
          <label class="rule-group-card__rule-label">
            <input
              type="checkbox"
              class="rule-group-card__checkbox"
              :checked="selectedIds.has(rule.id)"
              :aria-label="`Regel auswählen: ${rule.name}`"
              @change="toggleRule(rule.id)"
            />
            <span class="rule-group-card__rule-body">
              <span class="rule-group-card__rule-name">{{ rule.name }}</span>
              <span
                class="rule-group-card__rule-text"
                :title="getRuleReadableText(rule)"
              >
                {{ getRuleReadableText(rule) }}
              </span>
            </span>
          </label>

          <div class="rule-group-card__rule-meta">
            <span
              v-if="targetLabels && targetLabels.get(rule.id)"
              class="rule-group-card__target-chip"
              :title="targetLabels.get(rule.id)"
            >
              {{ targetLabels.get(rule.id) }}
            </span>

            <StatusBadge
              :level="ruleStatusLevel(rule)"
              compact
            />

            <button
              type="button"
              class="rule-group-card__edit-btn"
              title="Regel vollständig bearbeiten"
              :aria-label="`Regel vollständig bearbeiten: ${rule.name}`"
              @click.stop="handleEditRule(rule.id)"
            >
              <ExternalLink class="rule-group-card__edit-icon" aria-hidden="true" />
            </button>
          </div>
        </li>
      </ul>

      <p v-else class="rule-group-card__empty">
        Keine Regeln in dieser Gruppe.
      </p>

      <div
        v-if="selectedCount > 0"
        class="rule-group-card__selection-hint"
        aria-live="polite"
      >
        {{ selectedCount }}&thinsp;{{ selectedCount === 1 ? 'Regel' : 'Regeln' }} ausgewählt
      </div>
      <p
        v-else-if="rules.length > 0"
        class="rule-group-card__selection-hint"
      >
        Regeln markieren, um sie gemeinsam zu bearbeiten
      </p>

      <div
        v-if="$slots['quick-field'] && selectedCount > 0"
        class="rule-group-card__quick-field"
      >
        <slot
          name="quick-field"
          :selected-ids="[...selectedIds].sort()"
        />
      </div>
    </div>
  </BaseCard>
</template>

<style scoped>
.rule-group-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  width: 100%;
  min-width: 0;
  padding: var(--space-2);
  border-left: 3px solid var(--rule-group-accent, var(--color-text-muted));
  border-radius: var(--radius-md);
  container-type: inline-size;
  container-name: rule-group;
}

.rule-group-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-3);
  min-width: 0;
}

.rule-group-card__header-main {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 8rem;
  flex: 1 1 auto;
}

.rule-group-card__header-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.rule-group-card__icon {
  width: 24px;
  height: 24px;
  flex-shrink: 0;
}

.rule-group-card__name {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
  min-width: 0;
  overflow-wrap: break-word;
}

.rule-group-card__count-chip {
  font-size: var(--text-xxs);
  color: var(--color-text-secondary);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  padding: 2px 6px;
  white-space: nowrap;
}

.rule-group-card__select-all {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 44px;
  min-height: 44px;
  padding: 0;
  border: none;
  background: transparent;
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: color var(--transition-fast), background var(--transition-fast);
}

.rule-group-card__select-all:hover {
  color: var(--color-text-secondary);
  background: var(--color-bg-tertiary);
}

.rule-group-card__select-all:focus-visible {
  outline: 2px solid var(--color-iridescent-2);
  outline-offset: 2px;
}

.rule-group-card__select-all-icon {
  width: 16px;
  height: 16px;
}

@media (hover: none) {
  .rule-group-card__select-all {
    color: var(--color-text-secondary);
  }
}

.rule-group-card__rule-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.rule-group-card__rule-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--space-2);
  padding: var(--space-2);
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  min-height: 44px;
  min-width: 0;
  transition: background var(--transition-fast), border-color var(--transition-fast);
}

.rule-group-card__rule-row:hover {
  background: var(--color-bg-tertiary);
  border-color: var(--glass-border);
}

.rule-group-card__rule-row--selected {
  background: color-mix(in srgb, var(--color-info) 8%, transparent);
  border-color: color-mix(in srgb, var(--color-info) 25%, transparent);
}

.rule-group-card__rule-label {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  flex: 1 1 12rem;
  min-width: 0;
  cursor: pointer;
}

.rule-group-card__checkbox {
  width: 16px;
  height: 16px;
  margin-top: 2px;
  flex-shrink: 0;
  cursor: pointer;
  accent-color: var(--color-info);
}

.rule-group-card__rule-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.rule-group-card__rule-name {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  line-height: 1.35;
  overflow-wrap: break-word;
}

.rule-group-card__rule-text {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.rule-group-card__rule-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex: 0 0 auto;
  margin-left: auto;
  padding-top: 2px;
}

.rule-group-card__target-chip {
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  padding: 2px 6px;
  max-width: 10rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rule-group-card__empty {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  margin: 0;
  padding: var(--space-2) 0;
}

.rule-group-card__selection-hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin: 0;
}

.rule-group-card__edit-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 44px;
  min-height: 44px;
  padding: 0;
  border: none;
  background: transparent;
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  cursor: pointer;
  flex-shrink: 0;
  transition: color var(--transition-fast), background var(--transition-fast);
}

.rule-group-card__edit-btn:hover {
  color: var(--color-text-secondary);
  background: var(--color-bg-tertiary);
}

.rule-group-card__edit-btn:focus-visible {
  outline: 2px solid var(--color-iridescent-2);
  outline-offset: 2px;
}

.rule-group-card__edit-icon {
  width: 14px;
  height: 14px;
}

.rule-group-card__quick-field {
  border-top: 1px dashed var(--glass-border);
  padding-top: var(--space-3);
  min-width: 0;
}

@container rule-group (max-width: 22rem) {
  .rule-group-card__rule-row {
    flex-direction: column;
    align-items: stretch;
  }

  .rule-group-card__rule-label {
    flex: 1 1 auto;
  }

  .rule-group-card__rule-meta {
    margin-left: 0;
    padding-left: calc(16px + var(--space-2));
    padding-top: 0;
  }

  .rule-group-card__target-chip {
    max-width: none;
    flex: 1 1 auto;
  }
}
</style>
