<script setup lang="ts">
/**
 * DeviceDetailPanel — Slide-over detail view for a single device.
 *
 * Shows device info, schema-based metadata, zone context, linked rules,
 * and navigation links. Used inside the inventory view when a table row is clicked.
 *
 * Note: Full device editing (AlertConfig, RuntimeMaintenance, DeviceMetadata)
 * is done via SensorConfigPanel / ActuatorConfigPanel in the HardwareView (Übersicht, Route /hardware), not in the SensorsView (/sensors).
 */

import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  Activity, MapPin, ChevronRight, Save, Settings,
} from 'lucide-vue-next'
import { sensorsApi } from '@/api/sensors'
import { actuatorsApi } from '@/api/actuators'
import { getSensorLabel } from '@/utils/sensorDefaults'
import { ACTUATOR_TYPE_LABELS } from '@/utils/labels'
import { formatSensorValue, formatRelativeTime } from '@/utils/formatters'
import { useToast } from '@/composables/useToast'
import { AccordionSection } from '@/shared/design/primitives'
import LinkedRulesSection from '@/components/devices/LinkedRulesSection.vue'
import SchemaForm from '@/components/inventory/SchemaForm.vue'
import ZoneContextEditor from '@/components/inventory/ZoneContextEditor.vue'
import { getSchemaForDevice } from '@/config/device-schemas'
import type { ResolvedSchema } from '@/config/device-schemas'
import type { ComponentItem } from '@/shared/stores/inventory.store'

const props = defineProps<{
  item: ComponentItem
}>()

const router = useRouter()
const { success, error: showError } = useToast()

// Display helpers
const typeLabel = computed(() => {
  if (props.item.type === 'sensor') return getSensorLabel(props.item.deviceType)
  return ACTUATOR_TYPE_LABELS[props.item.deviceType] ?? props.item.deviceType
})

const currentValueFormatted = computed(() => {
  if (props.item.type === 'actuator') return props.item.currentValue
  if (props.item.currentValue === '—') return '—'
  const num = parseFloat(props.item.currentValue)
  if (isNaN(num)) return props.item.currentValue
  return formatSensorValue(num, props.item.deviceType)
})

// Cross-navigation
function goToMonitor() {
  if (props.item.zoneId) {
    router.push({ name: 'monitor-zone', params: { zoneId: props.item.zoneId } })
  }
}

function goToSensorDetail() {
  if (props.item.zoneId && props.item.type === 'sensor') {
    router.push({
      name: 'monitor-sensor',
      params: {
        zoneId: props.item.zoneId,
        sensorId: `${props.item.espId}-gpio${props.item.gpio}`,
      },
    })
  }
}

function goToConfigPanel() {
  router.push({
    path: '/hardware',
    query: { openSettings: props.item.espId },
  })
}

// ── Schema-based Metadata ──
const resolvedSchema = computed<ResolvedSchema | null>(() =>
  getSchemaForDevice(props.item.deviceType, props.item.type)
)

const schemaMetadata = ref<Record<string, unknown>>({})
const isSchemaDirty = ref(false)
const isSavingSchema = ref(false)

// Load schema metadata from current device metadata
watch(() => props.item.id, async () => {
  isSchemaDirty.value = false
  if (!resolvedSchema.value) return
  try {
    const raw = await fetchMetadata()
    schemaMetadata.value = (raw as unknown as Record<string, unknown>) ?? {}
  } catch {
    schemaMetadata.value = {}
  }
}, { immediate: true })

function onSchemaFieldChange(_key: string, _value: unknown) {
  isSchemaDirty.value = true
}

async function saveSchemaMetadata() {
  isSavingSchema.value = true
  try {
    await updateMetadata(schemaMetadata.value)
    isSchemaDirty.value = false
    success('Typspezifische Metadaten gespeichert')
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Fehler beim Speichern')
  } finally {
    isSavingSchema.value = false
  }
}

// Metadata API wrappers
function fetchMetadata() {
  if (props.item.type === 'sensor') {
    return sensorsApi.get(props.item.espId, props.item.gpio)
      .then(r => (r as unknown as Record<string, unknown>).sensor_metadata ?? {})
  }
  return actuatorsApi.get(props.item.espId, props.item.gpio)
    .then(r => (r as unknown as Record<string, unknown>).actuator_metadata ?? {})
}

function updateMetadata(data: Record<string, unknown>) {
  if (props.item.type === 'sensor') {
    return sensorsApi.createOrUpdate(props.item.espId, props.item.gpio, {
      sensor_metadata: data,
    } as never)
  }
  return actuatorsApi.createOrUpdate(props.item.espId, props.item.gpio, {
    actuator_metadata: data,
  } as never)
}
</script>

<template>
  <div class="detail-panel">
    <!-- Header Info -->
    <div class="detail-panel__header">
      <div class="detail-panel__title-row">
        <h3 class="detail-panel__title">{{ item.name }}</h3>
        <span v-if="item.isMock" class="detail-panel__mock-badge">MOCK</span>
      </div>
      <div class="detail-panel__subtitle">
        {{ typeLabel }} · {{ item.type === 'sensor' ? 'Sensor' : 'Aktor' }}
      </div>
    </div>

    <!-- Status & Value -->
    <div class="detail-panel__info-grid">
      <div class="detail-panel__info-item">
        <span class="detail-panel__info-label">Status</span>
        <span class="detail-panel__info-value">
          <span
            class="detail-panel__status-dot"
            :style="{ background: item.status === 'online' ? 'var(--color-success)' : 'var(--color-error)' }"
          />
          {{ item.status === 'online' ? 'Online' : 'Offline' }}
        </span>
      </div>
      <div class="detail-panel__info-item">
        <span class="detail-panel__info-label">Aktueller Wert</span>
        <span class="detail-panel__info-value detail-panel__info-value--primary">
          {{ currentValueFormatted }}
        </span>
      </div>
      <div class="detail-panel__info-item">
        <span class="detail-panel__info-label">Zone</span>
        <span class="detail-panel__info-value">{{ item.zone }}</span>
      </div>
      <div class="detail-panel__info-item">
        <span class="detail-panel__info-label">ESP ID</span>
        <span class="detail-panel__info-value detail-panel__info-value--mono">{{ item.espId }}</span>
      </div>
      <div class="detail-panel__info-item">
        <span class="detail-panel__info-label">GPIO</span>
        <span class="detail-panel__info-value">{{ item.gpio }}</span>
      </div>
      <div v-if="item.lastSeen" class="detail-panel__info-item">
        <span class="detail-panel__info-label">Zuletzt gesehen</span>
        <span class="detail-panel__info-value">{{ formatRelativeTime(item.lastSeen) }}</span>
      </div>
    </div>

    <!-- Type-Specific Schema Fields -->
    <AccordionSection
      v-if="resolvedSchema"
      :title="`${typeLabel} — Typspezifisch`"
      storage-key="ao-detail-schema"
    >
      <SchemaForm
        v-model="schemaMetadata"
        :properties="resolvedSchema.deviceProperties"
        @field-change="onSchemaFieldChange"
      />
      <div v-if="isSchemaDirty" class="detail-panel__save-row">
        <button
          class="detail-panel__save-btn"
          :disabled="isSavingSchema"
          @click="saveSchemaMetadata"
        >
          <Save class="w-4 h-4" />
          {{ isSavingSchema ? 'Speichern...' : 'Speichern' }}
        </button>
      </div>
    </AccordionSection>

    <!-- Linked Rules -->
    <AccordionSection title="Verknüpfte Regeln" storage-key="ao-detail-rules">
      <LinkedRulesSection
        :esp-id="item.espId"
        :gpio="item.gpio"
        :device-type="item.type"
      />
    </AccordionSection>

    <!-- Zone Context -->
    <AccordionSection
      v-if="item.zoneId"
      title="Zone-Kontext"
      storage-key="ao-detail-zone-context"
    >
      <ZoneContextEditor
        :zone-id="item.zoneId"
        :zone-name="item.zone"
      />
    </AccordionSection>

    <!-- Navigation Links -->
    <div class="detail-panel__links">
      <button
        class="detail-panel__link"
        @click="goToConfigPanel"
      >
        <Settings class="w-4 h-4" />
        <span>Vollständige Konfiguration</span>
        <ChevronRight class="w-4 h-4 ml-auto" />
      </button>
      <button
        v-if="item.zoneId && item.type === 'sensor'"
        class="detail-panel__link"
        @click="goToSensorDetail"
      >
        <Activity class="w-4 h-4" />
        <span>Live-Daten im Monitor</span>
        <ChevronRight class="w-4 h-4 ml-auto" />
      </button>
      <button
        v-if="item.zoneId"
        class="detail-panel__link"
        @click="goToMonitor"
      >
        <MapPin class="w-4 h-4" />
        <span>Zone im Monitor</span>
        <ChevronRight class="w-4 h-4 ml-auto" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.detail-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.detail-panel__header {
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--glass-border);
}

.detail-panel__title-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.detail-panel__title {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--color-text-primary);
}

.detail-panel__mock-badge {
  padding: 1px 8px;
  font-size: var(--text-xxs);
  font-weight: 600;
  border-radius: var(--radius-full);
  background: rgba(167, 139, 250, 0.15);
  color: var(--color-mock);
}

.detail-panel__subtitle {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  margin-top: var(--space-1);
}

/* Info Grid */
.detail-panel__info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
}

.detail-panel__info-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.detail-panel__info-label {
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.detail-panel__info-value {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.detail-panel__info-value--primary {
  color: var(--color-text-primary);
  font-weight: 600;
  font-size: var(--text-base);
}

.detail-panel__info-value--mono {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.detail-panel__status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

/* Links */
.detail-panel__links {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-top: var(--space-2);
}

.detail-panel__link {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-accent-bright);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  text-align: left;
  width: 100%;
}

.detail-panel__link:hover {
  border-color: var(--color-accent);
  background: rgba(59, 130, 246, 0.06);
}

/* Save Row */
.detail-panel__save-row {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--space-3);
  padding-top: var(--space-2);
  border-top: 1px solid var(--glass-border);
}

.detail-panel__save-btn {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-3);
  background: var(--color-accent);
  border: none;
  border-radius: var(--radius-sm);
  color: white;
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: opacity var(--transition-fast);
}

.detail-panel__save-btn:hover {
  opacity: 0.9;
}

.detail-panel__save-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
