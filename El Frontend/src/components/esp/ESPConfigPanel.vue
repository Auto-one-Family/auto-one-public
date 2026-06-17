<script setup lang="ts">
/**
 * ESPConfigPanel — ESP Device Configuration SlideOver
 *
 * Shows ESP device info and provides configuration options:
 * - Name, Zone, Subzone editing
 * - WiFi/MQTT status display
 * - Firmware version
 * - GPIO pin status table (simplified list)
 * - Emergency stop button
 */

import { ref, computed, onMounted } from 'vue'
import { Save, Wifi, Radio, Cpu, AlertOctagon } from 'lucide-vue-next'
import { useEspStore } from '@/stores/esp'
import { useToast } from '@/composables/useToast'
import { getWifiStrength } from '@/utils/wifiStrength'
import { formatLastSeen } from '@/utils/formatters'
import type { ESPDevice } from '@/api/esp'
import type { MockSensor, MockActuator } from '@/types'

interface Props {
  device: ESPDevice
}

const props = defineProps<Props>()

const espStore = useEspStore()
const toast = useToast()
const saving = ref(false)

// Editable fields
const deviceName = ref('')
const deviceZone = ref('')

onMounted(() => {
  deviceName.value = props.device.name || ''
  deviceZone.value = props.device.zone_id || ''
})

const deviceId = computed(() => espStore.getDeviceId(props.device))
const isMock = computed(() => espStore.isMock(deviceId.value))
const isOnline = computed(() => props.device.status === 'online' || props.device.connected === true)

const wifiInfo = computed(() => {
  const rssi = props.device.wifi_rssi ?? -100
  return getWifiStrength(rssi)
})

const lastSeen = computed(() => formatLastSeen(props.device.last_seen))

// GPIO usage from sensors/actuators
interface PinUsage {
  gpio: number
  owner: 'sensor' | 'actuator'
  name: string
  type: string
}

const pinUsage = computed<PinUsage[]>(() => {
  const pins: PinUsage[] = []
  const sensors = (props.device.sensors as MockSensor[]) || []
  const actuators = (props.device.actuators as MockActuator[]) || []

  for (const s of sensors) {
    pins.push({
      gpio: s.gpio,
      owner: 'sensor',
      name: s.name || s.sensor_type,
      type: s.sensor_type,
    })
  }

  for (const a of actuators) {
    pins.push({
      gpio: a.gpio,
      owner: 'actuator',
      name: a.name || a.actuator_type || 'Aktor',
      type: a.actuator_type || 'relay',
    })
  }

  return pins.sort((a, b) => a.gpio - b.gpio)
})

// Actions
async function handleSave() {
  saving.value = true
  try {
    await espStore.updateDevice(deviceId.value, {
      name: deviceName.value || undefined,
    })
    toast.success('ESP-Konfiguration gespeichert')
  } catch (err) {
    toast.error('Fehler beim Speichern')
  } finally {
    saving.value = false
  }
}

async function handleEmergencyStop() {
  try {
    if (isMock.value) {
      await espStore.emergencyStop(deviceId.value, 'Manual via ESP Config Panel')
    } else {
      await espStore.emergencyStopAll('Manual via ESP Config Panel')
    }
    toast.warning('Emergency-Stop ausgelöst')
  } catch {
    toast.error('Emergency-Stop fehlgeschlagen')
  }
}
</script>

<template>
  <div class="esp-config">
    <!-- Status Overview -->
    <section class="esp-config__section">
      <h3 class="esp-config__section-title">Status</h3>

      <div class="esp-config__status-grid">
        <div class="esp-config__status-item">
          <div class="esp-config__status-dot" :class="isOnline ? 'esp-config__status-dot--online' : 'esp-config__status-dot--offline'" />
          <span>{{ isOnline ? 'Online' : 'Offline' }}</span>
        </div>

        <div class="esp-config__status-item">
          <Wifi class="w-4 h-4" />
          <span>{{ wifiInfo.label }} ({{ device.wifi_rssi ?? '—' }} dBm)</span>
        </div>

        <div class="esp-config__status-item">
          <Radio class="w-4 h-4" />
          <span>MQTT: {{ isOnline ? 'Verbunden' : 'Getrennt' }}</span>
        </div>

        <div class="esp-config__status-item">
          <Cpu class="w-4 h-4" />
          <span>{{ isMock ? 'Simuliert' : 'Hardware' }}</span>
        </div>
      </div>
    </section>

    <!-- Device Info -->
    <section class="esp-config__section">
      <h3 class="esp-config__section-title">Geräte-Info</h3>

      <div class="esp-config__field">
        <label class="esp-config__label">Name</label>
        <input v-model="deviceName" type="text" class="esp-config__input" placeholder="Gerätename" />
      </div>

      <div class="esp-config__info-row">
        <span class="esp-config__info-label">ESP-ID:</span>
        <code class="esp-config__info-value">{{ deviceId }}</code>
      </div>

      <div class="esp-config__info-row">
        <span class="esp-config__info-label">IP-Adresse:</span>
        <code class="esp-config__info-value">{{ device.ip_address || '—' }}</code>
      </div>

      <div class="esp-config__info-row">
        <span class="esp-config__info-label">Firmware:</span>
        <code class="esp-config__info-value">{{ (device as any).firmware_version || '—' }}</code>
      </div>

      <div class="esp-config__info-row">
        <span class="esp-config__info-label">Letzter Heartbeat:</span>
        <span class="esp-config__info-value">{{ lastSeen }}</span>
      </div>

      <div class="esp-config__info-row">
        <span class="esp-config__info-label">Uptime:</span>
        <span class="esp-config__info-value">{{ device.uptime ? `${Math.floor(device.uptime / 3600)}h ${Math.floor((device.uptime % 3600) / 60)}m` : '—' }}</span>
      </div>

      <div class="esp-config__info-row">
        <span class="esp-config__info-label">Free Heap:</span>
        <code class="esp-config__info-value">{{ device.heap_free ? `${(device.heap_free / 1024).toFixed(0)} KB` : '—' }}</code>
      </div>
    </section>

    <!-- GPIO Belegung -->
    <section class="esp-config__section">
      <h3 class="esp-config__section-title">GPIO-Belegung ({{ pinUsage.length }} belegt)</h3>

      <div v-if="pinUsage.length === 0" class="esp-config__empty">Keine GPIOs belegt</div>

      <div v-else class="esp-config__pin-list">
        <div
          v-for="pin in pinUsage"
          :key="pin.gpio"
          :class="['esp-config__pin-item', `esp-config__pin-item--${pin.owner}`]"
        >
          <span class="esp-config__pin-gpio">GPIO {{ pin.gpio }}</span>
          <span class="esp-config__pin-name">{{ pin.name }}</span>
          <span class="esp-config__pin-type">{{ pin.type }}</span>
        </div>
      </div>
    </section>

    <!-- Actions -->
    <section class="esp-config__section">
      <button class="esp-config__save" :disabled="saving" @click="handleSave">
        <Save class="w-4 h-4" />
        {{ saving ? 'Speichert...' : 'Speichern' }}
      </button>

      <button class="esp-config__emergency" @click="handleEmergencyStop">
        <AlertOctagon class="w-5 h-5" />
        NOTFALL-STOPP — Alle Aktoren abschalten
      </button>
    </section>
  </div>
</template>

<style scoped>
.esp-config {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.esp-config__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding-bottom: var(--space-4);
  border-bottom: 1px solid var(--glass-border);
}

.esp-config__section:last-child { border-bottom: none; }

.esp-config__section-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  margin: 0;
}

/* Status Grid */
.esp-config__status-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-2);
}

.esp-config__status-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.esp-config__status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.esp-config__status-dot--online {
  background: var(--color-status-good);
  box-shadow: 0 0 6px rgba(34, 197, 94, 0.5);
}

.esp-config__status-dot--offline {
  background: var(--color-status-offline);
}

/* Fields */
.esp-config__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.esp-config__label {
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.esp-config__input {
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-base);
}

.esp-config__input:focus { outline: none; border-color: var(--color-accent); }

/* Info rows */
.esp-config__info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-1) 0;
}

.esp-config__info-label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.esp-config__info-value {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--color-text-primary);
}

/* Pin list */
.esp-config__empty {
  padding: var(--space-3);
  text-align: center;
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

.esp-config__pin-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.esp-config__pin-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
}

.esp-config__pin-item--sensor {
  background: rgba(96, 165, 250, 0.06);
  border-left: 2px solid var(--color-accent);
}

.esp-config__pin-item--actuator {
  background: rgba(34, 197, 94, 0.06);
  border-left: 2px solid var(--color-status-good);
}

.esp-config__pin-gpio {
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--color-text-primary);
  min-width: 60px;
}

.esp-config__pin-name {
  flex: 1;
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.esp-config__pin-type {
  font-family: var(--font-mono);
  color: var(--color-text-muted);
  font-size: var(--text-xxs);
}

/* Actions */
.esp-config__save {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-3) var(--space-4);
  background: var(--color-accent);
  border: none;
  border-radius: var(--radius-sm);
  color: white;
  font-size: var(--text-base);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.esp-config__save:hover:not(:disabled) { filter: brightness(1.1); }
.esp-config__save:disabled { opacity: 0.5; cursor: not-allowed; }

.esp-config__emergency {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-3) var(--space-4);
  background: rgba(239, 68, 68, 0.1);
  border: 2px solid var(--color-status-alarm);
  border-radius: var(--radius-md);
  color: var(--color-status-alarm);
  font-size: var(--text-sm);
  font-weight: 700;
  cursor: pointer;
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  transition: all var(--transition-fast);
}

.esp-config__emergency:hover {
  background: rgba(239, 68, 68, 0.2);
  box-shadow: 0 0 16px rgba(239, 68, 68, 0.3);
}
</style>
