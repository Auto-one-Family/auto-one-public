<script setup lang="ts">
/**
 * QuickActuatorPanel — Quick actuator toggle list shown as sub-panel in the FAB.
 *
 * Data source: useEspStore (devices flat-mapped to actuators).
 * Action: Toggle actuator state via espStore.sendActuatorCommand.
 * Search appears when more than MAX_ACTUATORS_NO_SEARCH actuators exist.
 *
 * AUT-253: One of three global FAB actions (Quick-Search, Aktor schalten, Schnell-Notiz).
 */

import { ref, computed } from 'vue'
import { ArrowLeft, Search, Loader2, Power, AlertTriangle } from 'lucide-vue-next'
import { useEspStore } from '@/stores/esp'
import { useActuatorStore } from '@/shared/stores/actuator.store'
import { useQuickActionStore } from '@/shared/stores/quickAction.store'
import { useToast } from '@/composables/useToast'
import { getActuatorTypeInfo } from '@/utils/labels'
import type { MockActuator } from '@/types'

interface FlatActuator extends MockActuator {
  esp_id: string
  device_name: string
  zone_name: string | null
  is_online: boolean
}

const MAX_ACTUATORS_NO_SEARCH = 8

const espStore = useEspStore()
const actuatorStore = useActuatorStore()
const quickActionStore = useQuickActionStore()
const { error: toastError } = useToast()

const searchQuery = ref('')
const togglingKey = ref<string | null>(null)

/** Flatten devices → actuators with esp_id, device name, online state */
const flatActuators = computed<FlatActuator[]>(() => {
  const result: FlatActuator[] = []
  for (const device of espStore.devices) {
    if (!Array.isArray(device.actuators)) continue
    const espId = device.device_id || device.esp_id
    if (!espId) continue
    const isOnline = device.status === 'online'
    for (const actuator of device.actuators) {
      result.push({
        ...actuator,
        esp_id: espId,
        device_name: device.name || espId,
        zone_name: device.zone_name ?? null,
        is_online: isOnline,
      })
    }
  }
  return result
})

const showSearch = computed(() => flatActuators.value.length > MAX_ACTUATORS_NO_SEARCH)

const filteredActuators = computed<FlatActuator[]>(() => {
  const query = searchQuery.value.trim().toLowerCase()
  if (!query) return flatActuators.value
  return flatActuators.value.filter((actuator) => {
    const name = (actuator.name ?? '').toLowerCase()
    const deviceName = actuator.device_name.toLowerCase()
    const zoneName = (actuator.zone_name ?? '').toLowerCase()
    const espId = actuator.esp_id.toLowerCase()
    return (
      name.includes(query) ||
      deviceName.includes(query) ||
      zoneName.includes(query) ||
      espId.includes(query)
    )
  })
})

const hasActuators = computed(() => flatActuators.value.length > 0)

function getActuatorKey(actuator: FlatActuator): string {
  return `${actuator.esp_id}:${actuator.gpio}`
}

function getDisplayName(actuator: FlatActuator): string {
  if (actuator.name && actuator.name.trim()) return actuator.name
  const typeLabel = getActuatorTypeInfo(actuator.actuator_type, actuator.hardware_type).label
  return `${typeLabel} (GPIO ${actuator.gpio})`
}

function isPending(actuator: FlatActuator): boolean {
  return actuatorStore.isActuatorCommandPending(actuator.esp_id, actuator.gpio)
}

function isInCooldown(actuator: FlatActuator): boolean {
  return actuatorStore.isActuatorCommandInCooldown(actuator.esp_id, actuator.gpio)
}

function isDisabled(actuator: FlatActuator): boolean {
  return (
    !actuator.is_online ||
    actuator.emergency_stopped === true ||
    isPending(actuator) ||
    isInCooldown(actuator) ||
    togglingKey.value === getActuatorKey(actuator)
  )
}

async function handleToggle(actuator: FlatActuator): Promise<void> {
  if (isDisabled(actuator)) return
  const key = getActuatorKey(actuator)
  togglingKey.value = key
  const command = actuator.state ? 'OFF' : 'ON'
  try {
    await espStore.sendActuatorCommand(actuator.esp_id, actuator.gpio, command)
  } catch (err) {
    // Toast is emitted by store; fallback in case of unexpected error
    if (!(err instanceof Error)) {
      toastError('Aktor-Befehl konnte nicht gesendet werden')
    }
  } finally {
    togglingKey.value = null
  }
}

function handleBack(): void {
  quickActionStore.setActivePanel('menu')
}
</script>

<template>
  <div
    class="qa-actuator-panel"
    role="region"
    aria-label="Aktor schalten"
    data-testid="quick-actuator-panel"
  >
    <!-- Header -->
    <div class="qa-actuator-panel__header">
      <button
        class="qa-actuator-panel__back"
        aria-label="Zurück"
        data-testid="quick-actuator-back"
        @click="handleBack"
      >
        <ArrowLeft class="qa-actuator-panel__back-icon" />
      </button>
      <span class="qa-actuator-panel__title">Aktor schalten</span>
      <span v-if="hasActuators" class="qa-actuator-panel__count">
        {{ flatActuators.length }}
      </span>
    </div>

    <!-- Search (only when many actuators) -->
    <div v-if="showSearch" class="qa-actuator-panel__search">
      <Search class="qa-actuator-panel__search-icon" />
      <input
        v-model="searchQuery"
        type="text"
        class="qa-actuator-panel__search-input"
        placeholder="Suchen..."
        data-testid="quick-actuator-search"
      />
    </div>

    <!-- List -->
    <div v-if="hasActuators" class="qa-actuator-panel__list" data-testid="quick-actuator-list">
      <div
        v-for="actuator in filteredActuators"
        :key="getActuatorKey(actuator)"
        class="actuator-row"
        :class="{ 'actuator-row--disabled': isDisabled(actuator) }"
        :data-testid="`quick-actuator-row-${actuator.esp_id}-${actuator.gpio}`"
      >
        <div class="actuator-row__icon" :class="{ 'actuator-row__icon--on': actuator.state }">
          <Power class="actuator-row__icon-svg" />
        </div>
        <div class="actuator-row__info">
          <span class="actuator-row__name">{{ getDisplayName(actuator) }}</span>
          <span class="actuator-row__meta">
            <span class="actuator-row__device">{{ actuator.device_name }}</span>
            <span v-if="actuator.zone_name" class="actuator-row__zone">· {{ actuator.zone_name }}</span>
          </span>
          <span v-if="!actuator.is_online" class="actuator-row__status actuator-row__status--offline">
            ESP offline
          </span>
          <span v-else-if="actuator.emergency_stopped" class="actuator-row__status actuator-row__status--emergency">
            <AlertTriangle class="actuator-row__status-icon" />
            Notfall-Stopp
          </span>
        </div>
        <button
          class="actuator-row__toggle"
          :class="{
            'actuator-row__toggle--on': actuator.state,
            'actuator-row__toggle--off': !actuator.state,
          }"
          :disabled="isDisabled(actuator)"
          :data-testid="`quick-actuator-toggle-${actuator.esp_id}-${actuator.gpio}`"
          :aria-label="actuator.state ? 'Ausschalten' : 'Einschalten'"
          @click.stop="handleToggle(actuator)"
        >
          <Loader2 v-if="isPending(actuator) || togglingKey === getActuatorKey(actuator)" class="actuator-row__spinner" />
          <span v-else class="actuator-row__toggle-label">
            {{ actuator.state ? 'AUS' : 'EIN' }}
          </span>
        </button>
      </div>

      <!-- No matches when filter is active -->
      <div
        v-if="filteredActuators.length === 0"
        class="qa-actuator-panel__no-match"
        data-testid="quick-actuator-no-match"
      >
        Keine Aktoren gefunden
      </div>
    </div>

    <!-- Empty state -->
    <div v-else class="qa-actuator-panel__empty" data-testid="quick-actuator-empty">
      <Power class="qa-actuator-panel__empty-icon" />
      <span>Keine Aktoren konfiguriert</span>
    </div>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════════════════════════════
   QUICK ACTUATOR PANEL — Sub-panel inside the FAB
   ═══════════════════════════════════════════════════════════════════════════ */

.qa-actuator-panel {
  position: absolute;
  bottom: calc(100% + var(--space-2));
  right: 0;
  width: 320px;
  max-height: 420px;
  display: flex;
  flex-direction: column;
  border-radius: var(--radius-md);
  background: rgba(20, 20, 30, 0.9);
  -webkit-backdrop-filter: blur(16px);
  backdrop-filter: blur(16px);
  border: 1px solid var(--glass-border);
  box-shadow: var(--elevation-floating);
  transform-origin: bottom right;
  overflow: hidden;
}

/* ── Header ── */

.qa-actuator-panel__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--glass-border);
}

.qa-actuator-panel__back {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: var(--radius-sm);
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.qa-actuator-panel__back:hover {
  color: var(--color-text-primary);
  background: rgba(255, 255, 255, 0.06);
}

.qa-actuator-panel__back-icon {
  width: 14px;
  height: 14px;
}

.qa-actuator-panel__title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  flex: 1;
}

.qa-actuator-panel__count {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-full);
  min-width: 18px;
  height: 18px;
  padding: 0 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

/* ── Search ── */

.qa-actuator-panel__search {
  position: relative;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--glass-border);
}

.qa-actuator-panel__search-icon {
  position: absolute;
  top: 50%;
  left: calc(var(--space-3) + var(--space-2));
  transform: translateY(-50%);
  width: 13px;
  height: 13px;
  color: var(--color-text-muted);
  pointer-events: none;
}

.qa-actuator-panel__search-input {
  width: 100%;
  padding: var(--space-1) var(--space-2) var(--space-1) calc(var(--space-2) + 13px + var(--space-1));
  font-size: var(--text-xs);
  color: var(--color-text-primary);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  outline: none;
  transition: border-color var(--transition-fast);
}

.qa-actuator-panel__search-input:focus {
  border-color: var(--color-iridescent-1);
}

.qa-actuator-panel__search-input::placeholder {
  color: var(--color-text-muted);
}

/* ── List ── */

.qa-actuator-panel__list {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-1);
}

/* ── Actuator Row ── */

.actuator-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2);
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast);
}

.actuator-row:hover:not(.actuator-row--disabled) {
  background: rgba(255, 255, 255, 0.03);
}

.actuator-row--disabled {
  opacity: 0.6;
}

.actuator-row__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
  color: var(--color-text-muted);
  transition: all var(--transition-fast);
}

.actuator-row__icon--on {
  background: rgba(52, 211, 153, 0.12);
  color: var(--color-success);
}

.actuator-row__icon-svg {
  width: 14px;
  height: 14px;
}

.actuator-row__info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.actuator-row__name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.actuator-row__meta {
  display: flex;
  gap: var(--space-1);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.actuator-row__device {
  overflow: hidden;
  text-overflow: ellipsis;
}

.actuator-row__zone {
  overflow: hidden;
  text-overflow: ellipsis;
}

.actuator-row__status {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: var(--text-xxs);
  font-weight: 500;
  margin-top: 1px;
}

.actuator-row__status--offline {
  color: var(--color-text-muted);
}

.actuator-row__status--emergency {
  color: var(--color-error);
}

.actuator-row__status-icon {
  width: 10px;
  height: 10px;
}

.actuator-row__toggle {
  flex-shrink: 0;
  min-width: 56px;
  height: 28px;
  padding: 0 var(--space-2);
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  display: flex;
  align-items: center;
  justify-content: center;
}

.actuator-row__toggle:hover:not(:disabled) {
  border-color: var(--color-iridescent-1);
  color: var(--color-text-primary);
}

.actuator-row__toggle:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.actuator-row__toggle--on {
  border-color: rgba(52, 211, 153, 0.3);
  color: var(--color-success);
  background: rgba(52, 211, 153, 0.08);
}

.actuator-row__toggle--on:hover:not(:disabled) {
  background: rgba(52, 211, 153, 0.15);
  border-color: var(--color-success);
}

.actuator-row__toggle--off {
  border-color: var(--glass-border);
  color: var(--color-text-secondary);
}

.actuator-row__toggle-label {
  letter-spacing: 0.5px;
}

.actuator-row__spinner {
  width: 14px;
  height: 14px;
  animation: qa-actuator-spin 1s linear infinite;
}

@keyframes qa-actuator-spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* ── Empty / No Match ── */

.qa-actuator-panel__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-6) var(--space-4);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

.qa-actuator-panel__empty-icon {
  width: 24px;
  height: 24px;
  opacity: 0.4;
}

.qa-actuator-panel__no-match {
  padding: var(--space-4) var(--space-3);
  text-align: center;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

/* ── Reduced motion ── */

@media (prefers-reduced-motion: reduce) {
  .actuator-row__spinner {
    animation: none;
  }
}
</style>
