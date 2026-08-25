<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import BaseModal from '@/shared/design/primitives/BaseModal.vue'
import { BaseTabs, type TabItem } from '@/shared/design/primitives'
import SensorConfigPanel from '@/components/esp/SensorConfigPanel.vue'
import ActuatorConfigPanel from '@/components/esp/ActuatorConfigPanel.vue'
import DeviceStatusPanel from '@/components/devices/DeviceStatusPanel.vue'
import { useEspStore } from '@/stores/esp'
import { getSensorDisplayName } from '@/utils/sensorDefaults'
import { getActuatorLabel } from '@/utils/actuatorDefaults'
import type { MockSensor } from '@/types'

type WizardMode = 'sensor' | 'actuator'

const props = defineProps<{
  open: boolean
  espId: string
  gpio: number
  sensorType?: string
  unit?: string
  configId?: string
  actuatorType?: string
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'close'): void
  (e: 'deleted'): void
  (e: 'saved'): void
  (e: 'open-esp-settings', payload: { espId: string }): void
}>()

const mode = computed<WizardMode>(() => props.actuatorType ? 'actuator' : 'sensor')
/** AUT-1128 (S3): bumped on `saved` so DeviceStatusPanel re-pulls the persisted mirror. */
const statusRefreshToken = ref(0)

// AUT-911/912: Active sub-value for multi-value sensors (SHT31, BME280, ...).
// Seeded from props, then mutated locally when the operator switches sub-value
// inside SensorConfigPanel. Drives the modal title, the DeviceStatusPanel live
// preview and the :key that re-mounts the panel so each sub-value reloads its
// own config_id.
const activeSensorType = ref(props.sensorType)
const activeConfigId = ref(props.configId)
const activeUnit = ref(props.unit)

function seedActiveSubValue() {
  activeSensorType.value = props.sensorType
  activeConfigId.value = props.configId
  activeUnit.value = props.unit
  activeConfigTab.value = 'grundlagen'
}

watch(
  () => [props.sensorType, props.configId, props.unit],
  () => { if (props.open) seedActiveSubValue() },
)

function onSwitchSubValue(payload: { configId: string | undefined; sensorType: string; unit: string }) {
  activeSensorType.value = payload.sensorType
  activeConfigId.value = payload.configId
  activeUnit.value = payload.unit || activeUnit.value
  activeConfigTab.value = 'grundlagen'
}

// =============================================================================
// AUT-1130 (Verify P10): Tab-Leiste selbst lebt jetzt hier (volle Modal-Breite,
// vormals in der schmalen Config-Spalte gequetscht -> Zeilenumbruch/Truncation).
// SensorConfigPanel/ActuatorConfigPanel bleiben Eigner der Tab-LISTE (per
// defineExpose) — nur die Auswahl (`activeConfigTab`) und das Rendern der
// Buttons wandern hierher, damit die Leiste ueber cwm-config-col UND
// cwm-status-col spannen kann.
// =============================================================================
const activeConfigTab = ref('grundlagen')
const configPanelRef = ref<{
  tabs: TabItem[]
  handleSave: () => Promise<void>
  confirmAndDelete: () => Promise<void>
  saving: boolean
  deleting: boolean
  loading: boolean
} | null>(null)
const currentTabs = computed<TabItem[]>(() => configPanelRef.value?.tabs ?? [])

watch(currentTabs, (tabs) => {
  if (tabs.length && !tabs.some(t => t.key === activeConfigTab.value)) {
    activeConfigTab.value = tabs[0].key
  }
})

const espStore = useEspStore()

const titledSensor = computed<MockSensor | null>(() => {
  if (mode.value !== 'sensor') return null
  const device = espStore.devices.find(d => espStore.getDeviceId(d) === props.espId)
  const sensors = (device?.sensors as MockSensor[] | undefined) ?? []
  if (activeConfigId.value) {
    const hit = sensors.find(s => s.config_id === activeConfigId.value)
    if (hit) return hit
  }
  return sensors.find(s =>
    s.sensor_type === activeSensorType.value && s.gpio === props.gpio,
  ) ?? null
})

const modalTitle = computed(() => {
  if (mode.value === 'sensor') {
    return getSensorDisplayName({
      sensor_type: activeSensorType.value ?? titledSensor.value?.sensor_type ?? '',
      name: titledSensor.value?.name,
    }) || 'Sensor'
  }
  // AUT-1523: Name einmal = Input im Panel. Titel = Typ-Label, kein GPIO-Fallback.
  return getActuatorLabel(props.actuatorType ?? 'relay')
})

watch(() => props.open, (open) => {
  if (open) seedActiveSubValue()
})

function handleClose() {
  emit('update:open', false)
  emit('close')
}

function handleDeleted() {
  emit('deleted')
  handleClose()
}

function handleSaved() {
  statusRefreshToken.value++
  emit('saved')
  handleClose()
}
</script>

<template>
  <BaseModal
    :open="open"
    :title="modalTitle"
    max-width="cwm-modal-max"
    show-close
    :close-on-overlay="false"
    close-on-escape
    allow-background-interaction
    @update:open="emit('update:open', $event)"
    @close="handleClose"
  >
    <!-- AUT-1523: Aktor-Titel = Typ-Label (Pumpe/…), Name nur noch im Panel-Input.
         AUT-1130: ESP/GPIO-Subtitle bleibt entfernt. -->

    <!-- AUT-1127 (S2): Regeln-Tab entfernt (war reiner Platzhalter-Text ohne Link, ohne
         Funktionsverlust). AUT-1128 (S3): Sensor-Messwert-Verlauf-Tab entfernt — Zielort
         ist eine offene TM/Robin-Entscheidung (siehe AUT-1125 Luecken), bewusst NICHT
         stillschweigend geloescht/umgezogen, bis die Entscheidung vorliegt. -->

    <!-- AUT-1130 (Verify P10): Tab-Leiste in voller Modal-Breite — genau die Flaeche,
         in der zuvor der doppelte ESP-ID-Subtitle stand. Tab-LISTE kommt weiterhin
         vom jeweils aktiven Config-Panel (defineExpose), nur Auswahl+Rendering
         sitzen hier, damit sie nicht in der schmalen Config-Spalte umbrechen. -->
    <BaseTabs
      v-if="currentTabs.length"
      v-model="activeConfigTab"
      :tabs="currentTabs"
      class="cwm-tabs-row"
    />

    <!-- AUT-1128 (S3): Zwei-Panel-Layout — Config-Felder links, read-only
         Status-Panel rechts angedockt. Kein gemeinsamer Wrapper zwischen Sensor- und
         Aktor-Panel; beide binden DeviceStatusPanel eigenstaendig ein. -->
    <div class="cwm-layout">
      <div class="cwm-config-col">
        <SensorConfigPanel
          v-if="mode === 'sensor' && espId && gpio !== undefined"
          ref="configPanelRef"
          :key="activeConfigId ?? activeSensorType ?? ''"
          :esp-id="espId"
          :gpio="gpio"
          :sensor-type="activeSensorType ?? ''"
          :unit="activeUnit"
          :config-id="activeConfigId"
          :show-metadata="false"
          :hide-actions="true"
          :active-tab="activeConfigTab"
          @deleted="handleDeleted"
          @saved="handleSaved"
          @switch-sub-value="onSwitchSubValue"
          @open-esp-settings="emit('open-esp-settings', $event)"
        />
        <ActuatorConfigPanel
          v-else-if="mode === 'actuator' && espId && gpio !== undefined"
          ref="configPanelRef"
          :esp-id="espId"
          :gpio="gpio"
          :actuator-type="actuatorType ?? 'relay'"
          :show-metadata="false"
          :active-tab="activeConfigTab"
          @deleted="handleDeleted"
          @saved="handleSaved"
          @open-esp-settings="emit('open-esp-settings', $event)"
        />
      </div>
      <div class="cwm-status-col">
        <DeviceStatusPanel
          v-if="espId && gpio !== undefined"
          :esp-id="espId"
          :gpio="gpio"
          :mode="mode"
          :actuator-type="actuatorType"
          :sensor-type="activeSensorType"
          :unit="activeUnit"
          :refresh-token="statusRefreshToken"
        />
      </div>
    </div>
    <template v-if="mode === 'sensor'" #footer>
      <div class="cwm-footer-actions">
        <button
          type="button"
          class="cwm-footer-save"
          :disabled="configPanelRef?.saving || configPanelRef?.loading"
          aria-label="Sensor-Konfiguration speichern"
          @click="configPanelRef?.handleSave()"
        >
          {{ configPanelRef?.saving ? 'Speichert...' : 'Speichern' }}
        </button>
        <button
          type="button"
          class="cwm-footer-delete"
          :disabled="configPanelRef?.deleting || configPanelRef?.loading"
          aria-label="Sensor entfernen"
          @click="configPanelRef?.confirmAndDelete()"
        >
          Sensor entfernen
        </button>
      </div>
    </template>
  </BaseModal>
</template>

<style scoped>
/* Layout bug fix: `:deep()` cannot reach this class. BaseModal teleports its
   content to <body>, and Vue's scoped-CSS parent->child root inheritance does
   not cross a <Teleport> boundary, so `:deep(.cwm-modal-max)` never matched —
   the modal silently fell back to the unrelated global `.modal-content {
   max-width: 28rem }` in styles/forms.css (a legacy rule for non-BaseModal
   dialogs that happens to share the class name). Result: modal stuck at
   448px, `.cwm-layout`'s `minmax(0, 1fr)` config column collapsed toward 0 to
   satisfy the status column's 300px floor.
   Fix: `:global()` emits plain unscoped CSS (bypasses the Teleport issue
   entirely), and the compound selector's specificity (0,2,0) reliably beats
   forms.css's `.modal-content` (0,1,0) regardless of stylesheet import
   order. */
:global(.modal-content.cwm-modal-max) {
  max-width: min(94vw, 1520px);
}

/* ── AUT-1130 (Verify P10): volle-Breite Tab-Leiste ueber beiden Spalten (statt
   in der schmalen cwm-config-col gequetscht) — sitzt als Geschwister VOR
   .cwm-layout und erbt dadurch die volle modal-body-Breite. ────────────────── */
.cwm-tabs-row {
  margin-bottom: var(--space-3);
}

/* ── AUT-1128 (S3) / AUT-1130: Zwei-Panel-Layout als Grid statt Flex-Prozente —
   `minmax(0, 1fr)` gibt der Config-Spalte immer den verbleibenden Platz. Die
   Status-Spalte bleibt bewusst kompakt (kurze Label:Wert-Paare + Buttons
   brauchen keine Breite proportional zum jetzt viel breiteren Modal) statt
   linear mitzuwachsen. ────────────────────────────────────────────────────── */
.cwm-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(300px, 380px);
  gap: 1.25rem;
  align-items: start;
}

.cwm-config-col {
  min-width: 0;
  overflow-y: auto;
  max-height: calc(90vh - 190px);
  padding: 1rem 1rem 1rem 0;
}

.cwm-status-col {
  overflow-y: auto;
  max-height: calc(90vh - 190px);
  padding: 1rem;
  background: var(--glass-bg-l1);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  position: sticky;
  top: 0;
}

@media (max-width: 900px) {
  .cwm-layout {
    grid-template-columns: 1fr;
  }

  .cwm-config-col,
  .cwm-status-col {
    max-height: none;
    position: static;
  }
}

.cwm-footer-actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.cwm-footer-save,
.cwm-footer-delete {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-sm);
  font-size: var(--text-base);
  font-weight: 600;
  cursor: pointer;
}

.cwm-footer-save {
  background: var(--color-accent);
  border: none;
  color: white;
}

.cwm-footer-save:disabled,
.cwm-footer-delete:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.cwm-footer-delete {
  background: transparent;
  border: 1px solid var(--color-danger);
  color: var(--color-danger);
}
</style>
