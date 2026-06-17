<script setup lang="ts">
/**
 * ActuatorCardWidget — Actuator toggle card for dashboard
 *
 * Fix: Uses local actuatorId ref to survive render() one-shot props.
 * Fix-U: Offline/stale detection via espStore (no props-drilling).
 */
import { ref, computed, watch, onUnmounted } from 'vue'
import { useEspStore } from '@/stores/esp'
import { useActuatorStore } from '@/shared/stores/actuator.store'
import { useToast } from '@/composables/useToast'
import { Zap, Power, WifiOff, Loader2 } from 'lucide-vue-next'
import type { MockActuator } from '@/types'

const ACTUATOR_COMMAND_TIMEOUT_MS = 15_000

const ZONE_STALE_THRESHOLD_MS = 60_000

interface Props {
  actuatorId?: string // "espId:gpio"
  readOnly?: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:config': [config: { actuatorId: string }]
}>()

const espStore = useEspStore()
const actuatorStore = useActuatorStore()
const { warning: toastWarning } = useToast()

// Local actuatorId state — survives render() one-shot props (Bug 1b fix)
const localActuatorId = ref(props.actuatorId || '')

// Sync from props when they change (e.g. page reload with saved config)
watch(() => props.actuatorId, (v) => { if (v) localActuatorId.value = v })

const availableActuators = computed(() => {
  const items: { id: string; label: string }[] = []
  for (const device of espStore.devices) {
    const deviceId = espStore.getDeviceId(device)
    for (const a of (device.actuators as MockActuator[]) || []) {
      items.push({
        id: `${deviceId}:${a.gpio}`,
        label: `${a.name || a.actuator_type} (${deviceId})`,
      })
    }
  }
  return items
})

// Current actuator data — uses localActuatorId instead of props.actuatorId
const currentActuator = computed(() => {
  if (!localActuatorId.value) return null
  const [eId, gpioStr] = localActuatorId.value.split(':')
  const gpioNum = parseInt(gpioStr)
  const device = espStore.devices.find(d => espStore.getDeviceId(d) === eId)
  if (!device) return null
  return ((device.actuators as MockActuator[]) || []).find(a => a.gpio === gpioNum) || null
})

const espId = computed(() => localActuatorId.value?.split(':')[0] || '')
const gpio = computed(() => parseInt(localActuatorId.value?.split(':')[1] || '0'))

// Fix-U: Store-based offline/stale detection
const espDevice = computed(() =>
  espStore.devices.find(d => espStore.getDeviceId(d) === espId.value)
)
const isEspOffline = computed(() => espDevice.value?.status === 'offline')
const isStale = computed(() => {
  const lastSeen = (espDevice.value as any)?.last_seen
  if (!lastSeen) return true
  const age = Date.now() - new Date(lastSeen).getTime()
  return age > ZONE_STALE_THRESHOLD_MS
})

const commandIsPending = computed(() =>
  espId.value ? actuatorStore.isActuatorCommandPending(espId.value, gpio.value) : false
)

const commandInCooldown = computed(() =>
  espId.value ? actuatorStore.isActuatorCommandInCooldown(espId.value, gpio.value) : false
)

const commandToggleBlocked = computed(() => commandIsPending.value || commandInCooldown.value)

const showWarnBadge = ref(false)
let pendingTimeoutHandle: ReturnType<typeof setTimeout> | null = null

watch(commandIsPending, (pending) => {
  if (pending) {
    pendingTimeoutHandle = setTimeout(() => {
      if (commandIsPending.value) {
        showWarnBadge.value = true
        toastWarning('Keine Bestätigung erhalten — Aktor-Befehl möglicherweise nicht ausgeführt.')
      }
    }, ACTUATOR_COMMAND_TIMEOUT_MS)
  } else {
    if (pendingTimeoutHandle !== null) {
      clearTimeout(pendingTimeoutHandle)
      pendingTimeoutHandle = null
    }
    showWarnBadge.value = false
  }
})

onUnmounted(() => {
  if (pendingTimeoutHandle !== null) clearTimeout(pendingTimeoutHandle)
})

async function toggle() {
  if (!currentActuator.value || isEspOffline.value || isStale.value || commandToggleBlocked.value) return
  const command = currentActuator.value.state ? 'OFF' : 'ON'
  await espStore.sendActuatorCommand(espId.value, gpio.value, command)
}

function selectActuator(id: string) {
  localActuatorId.value = id  // Immediate local update (Bug 1b fix)
  emit('update:config', { actuatorId: id })
}
</script>

<template>
  <div
    :class="[
      'actuator-card-widget',
      {
        'actuator-card-widget--offline': isEspOffline && localActuatorId,
        'actuator-card-widget--stale': isStale && !isEspOffline && localActuatorId,
      },
    ]"
  >
    <template v-if="localActuatorId && currentActuator">
      <div class="actuator-card-widget__header">
        <span class="actuator-card-widget__name">{{ currentActuator.name || currentActuator.actuator_type }}</span>
        <Zap class="w-4 h-4" :style="{ color: currentActuator.state ? 'var(--color-success)' : 'var(--color-text-muted)' }" />
      </div>
      <div class="actuator-card-widget__controls">
        <span :class="['actuator-card-widget__state-badge', currentActuator.state ? 'actuator-card-widget__state-badge--on' : '']">
          {{ commandIsPending ? '...' : (currentActuator.state ? 'EIN' : 'AUS') }}
        </span>
        <button
          v-if="!readOnly"
          class="actuator-card-widget__toggle"
          :class="{ 'actuator-card-widget__toggle--on': currentActuator.state, 'actuator-card-widget__toggle--pending': commandToggleBlocked }"
          :disabled="isEspOffline || isStale || commandToggleBlocked"
          :title="commandIsPending ? 'Befehl wird ausgeführt...' : commandInCooldown ? 'Bitte kurz warten (min. 2s zwischen Befehlen)' : isEspOffline ? 'ESP ist offline' : isStale ? 'Status veraltet' : ''"
          @click.stop="toggle"
        >
          <Loader2 v-if="commandIsPending" class="w-4 h-4 actuator-card-widget__spinner" />
          <Power v-else class="w-4 h-4" />
        </button>
      </div>
      <span v-if="commandIsPending" class="actuator-card-widget__status-badge actuator-card-widget__status-badge--pending">
        Wird ausgeführt...
      </span>
      <span v-else-if="showWarnBadge" class="actuator-card-widget__status-badge actuator-card-widget__status-badge--warn">
        Keine Bestätigung
      </span>
      <span v-else-if="isEspOffline" class="actuator-card-widget__status-badge">
        <WifiOff :size="10" /> ESP offline
      </span>
      <span v-else-if="isStale" class="actuator-card-widget__status-badge actuator-card-widget__status-badge--stale">
        Veraltet
      </span>
    </template>
    <div v-else-if="!readOnly" class="actuator-card-widget__empty">
      <Zap class="w-6 h-6" style="opacity: 0.3" />
      <select
        class="actuator-card-widget__select"
        @change="selectActuator(($event.target as HTMLSelectElement).value)"
      >
        <option value="" disabled selected>Aktor wählen</option>
        <option v-for="a in availableActuators" :key="a.id" :value="a.id">{{ a.label }}</option>
      </select>
    </div>
    <div v-else class="actuator-card-widget__empty">
      <Zap class="w-6 h-6" style="opacity: 0.3" />
      <span class="actuator-card-widget__empty-label">Kein Aktor konfiguriert</span>
    </div>
  </div>
</template>

<style scoped>
.actuator-card-widget {
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: var(--space-2);
}

.actuator-card-widget--offline {
  opacity: 0.5;
}

.actuator-card-widget--stale {
  opacity: 0.7;
  border-left: 2px solid var(--color-warning);
}

.actuator-card-widget__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-2);
}

.actuator-card-widget__name {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.actuator-card-widget__controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.actuator-card-widget__state-badge {
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: 600;
  background: var(--color-bg-quaternary);
  color: var(--color-text-muted);
}

.actuator-card-widget__state-badge--on {
  background: var(--color-zone-normal, rgba(34, 197, 94, 0.15));
  color: var(--color-success);
}

.actuator-card-widget__toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-quaternary);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.actuator-card-widget__toggle:hover:not(:disabled) {
  border-color: var(--color-accent);
}

.actuator-card-widget__toggle:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.actuator-card-widget__toggle--on {
  background: rgba(239, 68, 68, 0.1);
  border-color: var(--color-error);
  color: var(--color-error);
}

.actuator-card-widget__status-badge {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
  margin-top: var(--space-1);
}

.actuator-card-widget__status-badge--stale {
  color: var(--color-warning);
}

.actuator-card-widget__status-badge--pending {
  color: var(--color-accent);
}

.actuator-card-widget__status-badge--warn {
  color: var(--color-warning);
}

.actuator-card-widget__toggle--pending {
  border-color: var(--color-accent);
  opacity: 0.7;
}

.actuator-card-widget__spinner {
  color: var(--color-accent);
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.actuator-card-widget__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  height: 100%;
  color: var(--color-text-muted);
}

.actuator-card-widget__select {
  padding: var(--space-1) var(--space-2);
  background: var(--color-bg-quaternary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-xs);
  max-width: 160px;
}

.actuator-card-widget__empty-label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}
</style>
