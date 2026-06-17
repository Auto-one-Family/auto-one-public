<script setup lang="ts">
/**
 * PendingDevicesPanel — Device Management SlideOver
 *
 * Block 3: Converted from popover to SlideOver for consistent UX.
 * Provides device list (Variante A) with tabs for configured, pending, and info.
 * "Konfig." button emits to parent which opens ESPSettingsSheet (Variante B).
 *
 * Features:
 * - SlideOver from right (consistent with SensorConfigPanel/ActuatorConfigPanel)
 * - Tab navigation (Geräte / Wartend / Anleitung)
 * - Search field in Geräte tab
 * - Unassigned devices section
 * - Delete action with ConfirmDialog
 * - Toast feedback for approve/reject/delete actions
 */

import { ref, computed, watch } from 'vue'
import { Search, X, Check, Ban, Wifi, Clock, MapPin, Info, Loader2, Radio, Settings2, Trash2, Package, Usb, Zap, Key, Eye, EyeOff } from 'lucide-vue-next'
import { useEspStore } from '@/stores/esp'
import { useUiStore } from '@/shared/stores/ui.store'
import { useAuthStore } from '@/shared/stores/auth.store'
import { useFlashStore } from '@/stores/flash.store'
import { useZoneDragDrop, ZONE_UNASSIGNED } from '@/composables/useZoneDragDrop'
import { getESPStatus, getESPStatusDisplay } from '@/composables/useESPStatus'
import { getWifiStrength } from '@/utils/wifiStrength'
import { useToast } from '@/composables/useToast'
import SlideOver from '@/shared/design/primitives/SlideOver.vue'
import BaseButton from '@/shared/design/primitives/BaseButton.vue'
import BaseInput from '@/shared/design/primitives/BaseInput.vue'
import AccordionSection from '@/shared/design/primitives/AccordionSection.vue'
import EmptyState from '@/shared/design/patterns/EmptyState.vue'
import ErrorState from '@/shared/design/patterns/ErrorState.vue'
import RejectDeviceModal from '@/components/modals/RejectDeviceModal.vue'
import { flashApi, FlashPlatformUnavailableError, FlashExecuteError, type UsbDevice } from '@/api/flash'
import type { PendingESPDevice } from '@/types'
import type { ESPDevice } from '@/api/esp'

interface Props {
  isOpen: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:isOpen': [value: boolean]
  close: []
  'open-esp-config': [device: ESPDevice]
  'device-deleted': [deviceId: string]
}>()

const espStore = useEspStore()
const uiStore = useUiStore()
const authStore = useAuthStore()
const flashStore = useFlashStore()
const { groupDevicesByZone } = useZoneDragDrop()
const { success: showSuccess, error: showError } = useToast()

type TabType = 'devices' | 'pending' | 'info'
const activeTab = ref<TabType>('devices')
const searchQuery = ref('')
const pendingFetchError = ref<string | null>(null)

// Credentials panel state (AUT-767)
const credentialsOpen = ref(false)
const showWifiPw = ref(false)
const showMqttPw = ref(false)

watch(credentialsOpen, async (open) => {
  if (open) {
    // fetchEnv already called on panel open — just load secrets here
    flashStore.loadSecrets(flashStore.currentEnv)
  }
})

const buildStatusLabel = computed(() => {
  const labels: Record<string, string> = {
    saving: 'Wird gespeichert...',
    building: 'Binary wird gebaut...',
    ready: 'Binary bereit — Flash-Button aktiv',
    error: flashStore.buildError ?? 'Fehler beim Speichern',
  }
  return labels[flashStore.buildStatus] ?? ''
})

async function handleSaveCredentials() {
  await flashStore.saveAndBuild(flashStore.currentEnv)
}

watch(() => props.isOpen, async (open) => {
  if (open) {
    pendingFetchError.value = null
    searchQuery.value = ''
    // WP5a: always load env on panel open so currentEnv is correct before credentials accordion
    await flashStore.fetchEnv()
    try {
      await espStore.fetchPendingDevices()
    } catch (err) {
      pendingFetchError.value = err instanceof Error ? err.message : 'Laden fehlgeschlagen'
    }
  }
})

const zoneGroups = computed(() => {
  const devices = espStore.devices ?? []
  const groups = groupDevicesByZone(devices)
  return groups.filter(g => g.zoneId !== ZONE_UNASSIGNED)
})

const unassignedGroup = computed(() => espStore.unassignedDevices)

const filteredZoneGroups = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return zoneGroups.value
  return zoneGroups.value
    .map(group => ({ ...group, devices: group.devices.filter(d => matchesSearch(d, q)) }))
    .filter(group => group.devices.length > 0)
})

const filteredUnassigned = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return unassignedGroup.value
  return unassignedGroup.value.filter(d => matchesSearch(d, q))
})

function matchesSearch(device: ESPDevice, query: string): boolean {
  const id = (device.device_id || (device as any).esp_id || '').toLowerCase()
  const name = (device.name || '').toLowerCase()
  const zoneName = (device.zone_name || '').toLowerCase()
  return id.includes(query) || name.includes(query) || zoneName.includes(query)
}

const totalDeviceCount = computed(() => espStore.devices.length)
const pendingDevices = computed(() => espStore.pendingDevices)
const isLoading = computed(() => espStore.isPendingLoading)
const isEmpty = computed(() => pendingDevices.value.length === 0 && !isLoading.value && !pendingFetchError.value)

const approvingDevices = ref<Set<string>>(new Set())
const rejectingDevices = ref<Set<string>>(new Set())
const rejectModalOpen = ref(false)
const rejectTargetDevice = ref<PendingESPDevice | null>(null)

function getTimeAgo(isoDate: string): string {
  const now = new Date()
  const then = new Date(isoDate)
  const diffMs = now.getTime() - then.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return 'gerade eben'
  if (diffMin === 1) return 'vor 1 Min'
  if (diffMin < 60) return `vor ${diffMin} Min`
  const diffHours = Math.floor(diffMin / 60)
  if (diffHours === 1) return 'vor 1 Std'
  if (diffHours < 24) return `vor ${diffHours} Std`
  const diffDays = Math.floor(diffHours / 24)
  if (diffDays === 1) return 'vor 1 Tag'
  return `vor ${diffDays} Tagen`
}

function getSignalDisplay(rssi: number | null | undefined): { label: string; bars: number; colorClass: string } {
  const info = getWifiStrength(rssi)
  let colorClass = 'text-gray-400'
  if (info.quality === 'excellent' || info.quality === 'good') colorClass = 'text-emerald-400'
  else if (info.quality === 'fair') colorClass = 'text-yellow-400'
  else if (info.quality === 'poor' || info.quality === 'none') colorClass = 'text-orange-400'
  return { label: info.label, bars: info.bars, colorClass }
}

function getDeviceId(device: ESPDevice): string {
  return device.device_id || (device as any).esp_id || ''
}

function getSensorCount(device: ESPDevice): number {
  return (device.sensors as any[])?.length ?? device.sensor_count ?? 0
}

function handleClose() {
  emit('update:isOpen', false)
  emit('close')
}

function handleOpenConfig(device: ESPDevice) {
  emit('open-esp-config', device)
}

async function handleApprove(device: PendingESPDevice) {
  if (approvingDevices.value.has(device.device_id)) return
  approvingDevices.value.add(device.device_id)
  try {
    await espStore.approveDevice(device.device_id)
    showSuccess(`${device.device_id} genehmigt`)
  } catch (err) {
    showError(err instanceof Error ? err.message : 'Genehmigung fehlgeschlagen')
  } finally {
    approvingDevices.value.delete(device.device_id)
  }
}

function handleReject(device: PendingESPDevice) {
  if (rejectingDevices.value.has(device.device_id)) return
  rejectTargetDevice.value = device
  rejectModalOpen.value = true
}

async function confirmReject(reason: string) {
  const device = rejectTargetDevice.value
  if (!device) return
  rejectingDevices.value.add(device.device_id)
  try {
    await espStore.rejectDevice(device.device_id, reason)
    showSuccess(`${device.device_id} abgelehnt`)
  } catch (err) {
    showError(err instanceof Error ? err.message : 'Ablehnung fehlgeschlagen')
  } finally {
    rejectingDevices.value.delete(device.device_id)
    rejectTargetDevice.value = null
  }
}

function cancelReject() {
  rejectTargetDevice.value = null
}

async function handleDeleteDevice(device: ESPDevice) {
  const deviceId = getDeviceId(device)
  const displayName = device.name || deviceId
  const sensorCount = getSensorCount(device)
  const confirmed = await uiStore.confirm({
    title: 'Gerät löschen',
    message: sensorCount > 0
      ? `"${displayName}" und alle ${sensorCount} Sensoren werden gelöscht. Fortfahren?`
      : `"${displayName}" wird gelöscht. Fortfahren?`,
    variant: 'danger',
    confirmText: 'Löschen',
  })
  if (!confirmed) return
  try {
    await espStore.deleteDevice(deviceId)
    showSuccess(`${displayName} wurde gelöscht`)
    emit('device-deleted', deviceId)
  } catch (err) {
    showError(err instanceof Error ? err.message : 'Gerät konnte nicht gelöscht werden')
  }
}

function isProcessing(deviceId: string): boolean {
  return approvingDevices.value.has(deviceId) || rejectingDevices.value.has(deviceId)
}

async function handleRetryFetch() {
  pendingFetchError.value = null
  try {
    await espStore.fetchPendingDevices()
  } catch (err) {
    pendingFetchError.value = err instanceof Error ? err.message : 'Laden fehlgeschlagen'
  }
}

const isScanningUsb = ref(false)
const usbDevices = ref<UsbDevice[]>([])
const usbScanError = ref<string | null>(null)
const usbPlatformUnavailable = ref(false)
const usbPlatformMessage = ref('')
const usbScanned = ref(false)

async function handleScanUsb() {
  isScanningUsb.value = true
  usbDevices.value = []
  usbScanError.value = null
  usbPlatformUnavailable.value = false
  usbPlatformMessage.value = ''
  usbScanned.value = false
  isFlashing.value = {}
  flashResults.value = {}
  try {
    const result = await flashApi.listDevices()
    usbDevices.value = result.devices
    usbScanned.value = true
  } catch (err) {
    if (err instanceof FlashPlatformUnavailableError) {
      usbPlatformUnavailable.value = true
      usbPlatformMessage.value = err.message
    } else {
      usbScanError.value = err instanceof Error ? err.message : 'USB-Scan fehlgeschlagen'
    }
  } finally {
    isScanningUsb.value = false
  }
}

const isFlashing = ref<Record<string, boolean>>({})
const flashResults = ref<Record<string, { success: boolean; message: string }>>({})

function flashErrorMessage(err: unknown): string {
  if (err instanceof FlashExecuteError) {
    const messages: Record<number, string> = {
      3101: 'USB-Scanning nicht verfügbar auf dieser Plattform',
      3102: 'NVS-Binary nicht gefunden — bitte zuerst Credentials konfigurieren (AUT-767)',
      3103: 'NVS-Binary-Build fehlgeschlagen',
      3104: 'Ungültige Flash-Umgebung',
      3105: `Flash fehlgeschlagen: ${err.message}`,
      3106: 'Firmware-Artefakte fehlen — bitte zuerst auf dev-local bauen und in firmware_builds/ ablegen',
      3107: 'Port-Freigabe fehlgeschlagen — bitte Serial Monitor manuell schließen',
      3109: 'Erase-Bestätigung fehlt — bitte „Löschen bestätigen" aktivieren',
    }
    return messages[err.error_code] ?? err.message
  }
  return err instanceof Error ? err.message : 'Flash fehlgeschlagen'
}

// WP5b: Build guard + WP5c: erase confirm via uiStore.confirm()
async function requestFlash(port: string) {
  if (flashStore.buildStatus !== 'ready') {
    showError('Bitte zuerst Credentials speichern und Binary bauen (Credentials-Bereich öffnen).')
    return
  }
  if (flashStore.flashType === 'full') {
    const confirmed = await uiStore.confirm({
      title: 'Komplett-Flash bestätigen',
      message:
        'Achtung: Der gesamte Flash wird gelöscht (bootloader, firmware, NVS). ' +
        'Alle gespeicherten Daten auf dem ESP werden unwiderruflich entfernt. ' +
        'Danach wird die aktuelle Firmware mit den Credentials geflasht. ' +
        'Fortfahren?',
      variant: 'danger',
      confirmText: 'Löschen und flashen',
    })
    if (!confirmed) return
    void executeFlashForPort(port, true)
    return
  }
  void executeFlashForPort(port)
}

async function executeFlashForPort(port: string, eraseConfirm = false) {
  if (isFlashing.value[port]) return
  isFlashing.value = { ...isFlashing.value, [port]: true }
  flashResults.value = { ...flashResults.value, [port]: undefined as any }
  try {
    await flashApi.executeFlash(port, flashStore.currentEnv, flashStore.flashType, eraseConfirm)
    flashResults.value = { ...flashResults.value, [port]: { success: true, message: 'Flash abgeschlossen' } }
  } catch (err) {
    flashResults.value = { ...flashResults.value, [port]: { success: false, message: flashErrorMessage(err) } }
  } finally {
    isFlashing.value = { ...isFlashing.value, [port]: false }
  }
}

</script>

<template>
  <SlideOver :open="isOpen" title="Geräteverwaltung" width="md" @close="handleClose">
    <div class="pdp-tabs">
      <button :class="['pdp-tab', { 'pdp-tab--active': activeTab === 'devices' }]" @click="activeTab = 'devices'">
        <Settings2 class="pdp-tab__icon w-4 h-4" />
        <span>Geräte</span>
        <span v-if="totalDeviceCount > 0" class="pdp-tab-count">{{ totalDeviceCount }}</span>
      </button>
      <button :class="['pdp-tab', { 'pdp-tab--active': activeTab === 'pending' }]" @click="activeTab = 'pending'">
        <Radio class="pdp-tab__icon w-4 h-4" />
        <span>Wartend</span>
        <span v-if="pendingDevices.length > 0" class="pdp-tab-badge">{{ pendingDevices.length }}</span>
      </button>
      <button :class="['pdp-tab', { 'pdp-tab--active': activeTab === 'info' }]" @click="activeTab = 'info'">
        <Info class="pdp-tab__icon w-4 h-4" />
        <span>Anleitung</span>
      </button>
    </div>

    <!-- Tab: Geräte -->
    <div v-if="activeTab === 'devices'" class="pdp-content">
      <div class="pdp-search">
        <Search class="pdp-search-icon" />
        <input v-model="searchQuery" type="text" class="pdp-search-input" placeholder="Gerät suchen..." />
        <button v-if="searchQuery" class="pdp-search-clear" @click="searchQuery = ''">
          <X class="w-3.5 h-3.5" />
        </button>
      </div>

      <div v-if="filteredZoneGroups.length > 0 || filteredUnassigned.length > 0" class="pdp-list">
        <div v-for="group in filteredZoneGroups" :key="group.zoneId" class="pdp-zone-group">
          <div class="pdp-zone-title">{{ group.zoneName }}</div>
          <div v-for="device in group.devices" :key="getDeviceId(device)" class="pdp-device">
            <div class="pdp-device-info">
              <div class="pdp-device-name">{{ device.name || getDeviceId(device) }}</div>
              <div class="pdp-device-meta">
                <span class="pdp-status-dot" :style="{ backgroundColor: getESPStatusDisplay(getESPStatus(device)).color }" />
                <span class="pdp-device-status" :style="{ color: getESPStatusDisplay(getESPStatus(device)).color }">
                  {{ getESPStatusDisplay(getESPStatus(device)).text }}
                </span>
                <span class="pdp-device-sep">·</span>
                <span>{{ getSensorCount(device) }} Sensoren</span>
              </div>
            </div>
            <div class="pdp-device-actions">
              <BaseButton variant="ghost" size="sm" title="Konfigurieren" @click="handleOpenConfig(device)">
                <Settings2 class="w-4 h-4" />
              </BaseButton>
              <BaseButton variant="danger" size="sm" title="Löschen" @click="handleDeleteDevice(device)">
                <Trash2 class="w-4 h-4" />
              </BaseButton>
            </div>
          </div>
        </div>

        <div v-if="filteredUnassigned.length > 0" class="pdp-zone-group pdp-zone-group--unassigned">
          <div class="pdp-zone-title pdp-zone-title--unassigned">
            <Package class="w-3 h-3" />
            Nicht zugewiesen
          </div>
          <div v-for="device in filteredUnassigned" :key="getDeviceId(device)" class="pdp-device">
            <div class="pdp-device-info">
              <div class="pdp-device-name">{{ device.name || getDeviceId(device) }}</div>
              <div class="pdp-device-meta">
                <span class="pdp-status-dot" :style="{ backgroundColor: getESPStatusDisplay(getESPStatus(device)).color }" />
                <span class="pdp-device-status" :style="{ color: getESPStatusDisplay(getESPStatus(device)).color }">
                  {{ getESPStatusDisplay(getESPStatus(device)).text }}
                </span>
                <span class="pdp-device-sep">·</span>
                <span>{{ getSensorCount(device) }} Sensoren</span>
              </div>
            </div>
            <div class="pdp-device-actions">
              <BaseButton variant="ghost" size="sm" title="Konfigurieren" @click="handleOpenConfig(device)">
                <Settings2 class="w-4 h-4" />
              </BaseButton>
              <BaseButton variant="danger" size="sm" title="Löschen" @click="handleDeleteDevice(device)">
                <Trash2 class="w-4 h-4" />
              </BaseButton>
            </div>
          </div>
        </div>
      </div>

      <div v-else-if="totalDeviceCount === 0" class="pdp-empty">
        <Settings2 class="pdp-empty-icon" />
        <p class="pdp-empty-text">Keine Geräte vorhanden.</p>
        <p class="pdp-empty-hint">Erstelle ein Mock-ESP oder verbinde ein echtes Gerät.</p>
      </div>

      <div v-else class="pdp-empty">
        <Search class="pdp-empty-icon" />
        <p class="pdp-empty-text">Keine Treffer für "{{ searchQuery }}"</p>
        <button class="pdp-clear-search" @click="searchQuery = ''">Suche zurücksetzen</button>
      </div>

      <div class="pdp-footer">Wartend: {{ pendingDevices.length }} Gerät(e) zur Genehmigung</div>
    </div>

    <!-- Tab: Wartend -->
    <div v-if="activeTab === 'pending'" class="pdp-content">
      <div class="pdp-pending-section">
        <div v-if="isLoading" class="pdp-loading">
          <Loader2 class="pdp-loading-icon" />
          <span>Suche nach Geräten...</span>
        </div>

        <ErrorState v-else-if="pendingFetchError" :message="pendingFetchError" :show-retry="true" @retry="handleRetryFetch" />

        <EmptyState
          v-else-if="isEmpty"
          :icon="Radio"
          title="Keine neuen Geräte"
          description="ESP32 verbinden sich automatisch."
          action-text="Wie verbinde ich ein ESP32?"
          @action="activeTab = 'info'"
        />

        <div v-else class="pdp-list">
          <div
            v-for="(device, index) in pendingDevices"
            :key="device.device_id"
            class="pdp-pending-device"
            :class="{
              'pdp-pending-device--processing': isProcessing(device.device_id),
              'pdp-pending-device--fresh': getTimeAgo(device.last_seen || device.discovered_at) === 'gerade eben',
            }"
            :style="{ '--stagger-index': index }"
          >
            <div class="pdp-device-info">
              <div class="pdp-device-name pdp-device-name--mono">{{ device.device_id }}</div>
              <div class="pdp-device-meta">
                <span v-if="device.ip_address" class="pdp-meta-item">
                  <MapPin class="w-3 h-3" />{{ device.ip_address }}
                </span>
                <span v-if="device.wifi_rssi" class="pdp-meta-item" :class="getSignalDisplay(device.wifi_rssi).colorClass">
                  <Wifi class="w-3 h-3" />{{ getSignalDisplay(device.wifi_rssi).label }}
                </span>
                <span class="pdp-meta-item">
                  <Clock class="w-3 h-3" />{{ getTimeAgo(device.last_seen || device.discovered_at) }}
                </span>
              </div>
            </div>
            <div class="pdp-pending-actions">
              <BaseButton variant="primary" :loading="approvingDevices.has(device.device_id)" :disabled="isProcessing(device.device_id)" title="Gerät genehmigen" @click="handleApprove(device)">
                <Check v-if="!approvingDevices.has(device.device_id)" class="w-4 h-4" />
                <span>Genehmigen</span>
              </BaseButton>
              <BaseButton variant="danger" :loading="rejectingDevices.has(device.device_id)" :disabled="isProcessing(device.device_id)" title="Gerät ablehnen" @click="handleReject(device)">
                <Ban v-if="!rejectingDevices.has(device.device_id)" class="w-4 h-4" />
                <span>Ablehnen</span>
              </BaseButton>
            </div>
          </div>
        </div>
      </div>
      <!-- AUT-767: Credentials-Panel -->
      <div v-if="authStore.isOperator" class="pdp-pending-section pdp-credentials-section">
        <AccordionSection
          title="Credentials konfigurieren"
          storage-key="pdp-credentials"
          :icon="Key"
          v-model="credentialsOpen"
        >
          <div v-if="flashStore.isLoading" class="pdp-creds-loading">
            <Loader2 class="w-4 h-4 animate-spin" />
            <span>Lade Credentials...</span>
          </div>

          <ErrorState
            v-else-if="flashStore.loadError"
            :message="flashStore.loadError"
            :show-retry="true"
            @retry="flashStore.loadSecrets(flashStore.currentEnv)"
          />

          <form v-else class="pdp-creds-form" @submit.prevent="handleSaveCredentials">
            <div class="pdp-creds-fields">
              <BaseInput
                label="WLAN-Name (SSID)"
                placeholder="Mein-WLAN"
                v-model="flashStore.ssid"
              />

              <div class="pdp-creds-pw-group">
                <label class="pdp-creds-label">WLAN-Passwort</label>
                <div class="pdp-creds-pw-wrap">
                  <input
                    :type="showWifiPw ? 'text' : 'password'"
                    class="pdp-creds-input"
                    placeholder="••••••••"
                    :value="flashStore.wifiPassword"
                    @input="flashStore.wifiPassword = ($event.target as HTMLInputElement).value"
                  />
                  <button type="button" class="pdp-creds-eye" @click="showWifiPw = !showWifiPw">
                    <Eye v-if="!showWifiPw" class="w-4 h-4" />
                    <EyeOff v-else class="w-4 h-4" />
                  </button>
                </div>
              </div>

              <BaseInput
                label="MQTT Broker (Host/IP)"
                placeholder="192.168.x.x"
                v-model="flashStore.serverAddress"
              />

              <BaseInput
                label="MQTT Port"
                type="number"
                placeholder="1883"
                :min="1"
                :max="65535"
                v-model="flashStore.mqttPort"
              />

              <BaseInput
                label="MQTT Benutzername"
                placeholder="esp_user"
                v-model="flashStore.mqttUsername"
              />

              <div class="pdp-creds-pw-group">
                <label class="pdp-creds-label">MQTT Passwort</label>
                <div class="pdp-creds-pw-wrap">
                  <input
                    :type="showMqttPw ? 'text' : 'password'"
                    class="pdp-creds-input"
                    placeholder="••••••••"
                    :value="flashStore.mqttPassword"
                    @input="flashStore.mqttPassword = ($event.target as HTMLInputElement).value"
                  />
                  <button type="button" class="pdp-creds-eye" @click="showMqttPw = !showMqttPw">
                    <Eye v-if="!showMqttPw" class="w-4 h-4" />
                    <EyeOff v-else class="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>

            <div
              v-if="flashStore.buildStatus !== 'idle'"
              class="pdp-creds-build-status"
              :class="`pdp-creds-build-status--${flashStore.buildStatus}`"
            >
              <Loader2
                v-if="flashStore.buildStatus === 'saving' || flashStore.buildStatus === 'building'"
                class="w-4 h-4 animate-spin"
              />
              {{ buildStatusLabel }}
            </div>

            <BaseButton
              type="submit"
              variant="primary"
              size="sm"
              :loading="flashStore.buildStatus === 'saving' || flashStore.buildStatus === 'building'"
              :disabled="flashStore.buildStatus === 'saving' || flashStore.buildStatus === 'building'"
            >
              <Key
                v-if="flashStore.buildStatus !== 'saving' && flashStore.buildStatus !== 'building'"
                class="w-4 h-4"
              />
              <span>Speichern & Bauen</span>
            </BaseButton>
          </form>
        </AccordionSection>
      </div>

      <!-- AUT-826: USB-Flash-Sektion -->
      <div class="pdp-pending-section pdp-usb-section">
        <div class="pdp-usb-title">
          <Usb class="w-3.5 h-3.5" />
          USB-Geräte (direkt angeschlossen)
        </div>

        <BaseButton variant="secondary" size="sm" :loading="isScanningUsb" @click="handleScanUsb">
          <Usb v-if="!isScanningUsb" class="w-4 h-4" />
          <span>Scan USB Geräte</span>
        </BaseButton>

        <!-- Platform not available: persistent InfoBlock (D4 — always active button, never pre-disabled) -->
        <ErrorState
          v-if="usbPlatformUnavailable"
          :message="usbPlatformMessage"
          :show-retry="false"
        />

        <!-- Generic scan error (retryable) -->
        <ErrorState
          v-else-if="usbScanError"
          :message="usbScanError"
          :show-retry="true"
          @retry="handleScanUsb"
        />

        <!-- Empty after successful scan -->
        <div v-else-if="usbScanned && usbDevices.length === 0 && !isScanningUsb" class="pdp-empty pdp-usb-empty">
          <Usb class="pdp-empty-icon" />
          <p class="pdp-empty-text">Keine ESP-Geräte gefunden</p>
          <p class="pdp-empty-hint">ESP32 via USB anschließen und erneut scannen.</p>
        </div>

        <!-- Device list -->
        <div v-else-if="usbDevices.length > 0" class="pdp-list">
          <!-- WP5c: Flash-Modus-Auswahl -->
          <div class="pdp-flash-mode">
            <span class="pdp-flash-mode__label">Flash-Modus:</span>
            <div class="pdp-flash-mode__options">
              <button
                :class="['pdp-flash-mode__btn', { 'pdp-flash-mode__btn--active': flashStore.flashType === 'nvs' }]"
                @click="flashStore.flashType = 'nvs'"
              >Nur Credentials</button>
              <button
                :class="['pdp-flash-mode__btn', { 'pdp-flash-mode__btn--active': flashStore.flashType === 'firmware' }]"
                @click="flashStore.flashType = 'firmware'"
              >Firmware + Credentials</button>
              <button
                :class="['pdp-flash-mode__btn pdp-flash-mode__btn--danger', { 'pdp-flash-mode__btn--active': flashStore.flashType === 'full' }]"
                @click="flashStore.flashType = 'full'"
              >Komplett (Erase)</button>
            </div>
            <p v-if="flashStore.flashType === 'full'" class="pdp-flash-mode__warning">
              Löscht den gesamten Flash. Bestätigung beim Flash-Button erforderlich.
            </p>
          </div>

          <div v-for="device in usbDevices" :key="device.port" class="pdp-device pdp-device--column">
            <div class="pdp-device-row">
              <div class="pdp-device-info">
                <div class="pdp-device-name">{{ device.chip_family }} · {{ device.board_type }}</div>
                <div class="pdp-device-meta">
                  <span class="pdp-meta-item">
                    <Usb class="w-3 h-3" />
                    <span class="pdp-device-name--mono">{{ device.port }}</span>
                  </span>
                </div>
              </div>
              <div class="pdp-device-actions">
                <!-- WP5b: disabled when binary not ready -->
                <BaseButton
                  variant="primary"
                  size="sm"
                  :loading="isFlashing[device.port]"
                  :disabled="isFlashing[device.port] || flashStore.buildStatus !== 'ready'"
                  :title="flashStore.buildStatus !== 'ready' ? 'Bitte zuerst Credentials speichern und Binary bauen' : undefined"
                  @click="requestFlash(device.port)"
                >
                  <Zap v-if="!isFlashing[device.port]" class="w-4 h-4" />
                  <span>Flash</span>
                </BaseButton>
              </div>
            </div>
            <div v-if="flashResults[device.port]" :class="['pdp-flash-result', flashResults[device.port]?.success ? 'pdp-flash-result--success' : 'pdp-flash-result--error']">
              {{ flashResults[device.port]?.message }}
            </div>
          </div>
        </div>
      </div>
    </div>


    <!-- Tab: Anleitung -->
    <div v-if="activeTab === 'info'" class="pdp-content">
      <div class="pdp-info">
        <h4 class="pdp-info-title">
          <Wifi class="pdp-info-title-icon" />
          ESP32 verbinden
        </h4>
        <p class="pdp-info-text">Echte ESP32-Geräte verbinden sich automatisch und erscheinen im "Wartend"-Tab zur Genehmigung.</p>
        <div class="pdp-steps">
          <div class="pdp-step">
            <span class="pdp-step-number">1</span>
            <div class="pdp-step-content"><strong>Firmware flashen</strong><span>AutomationOne Firmware auf ESP32 installieren</span></div>
          </div>
          <div class="pdp-step">
            <span class="pdp-step-number">2</span>
            <div class="pdp-step-content"><strong>Provisioning</strong><span>ESP startet im AP-Modus für WiFi-Konfiguration</span></div>
          </div>
          <div class="pdp-step">
            <span class="pdp-step-number">3</span>
            <div class="pdp-step-content"><strong>Auto-Discovery</strong><span>ESP sendet Heartbeat und erscheint als "Wartend"</span></div>
          </div>
          <div class="pdp-step">
            <span class="pdp-step-number">4</span>
            <div class="pdp-step-content"><strong>Freigabe</strong><span>Klicke "Genehmigen" und der ESP wechselt zu vollem Betrieb</span></div>
          </div>
        </div>
        <div class="pdp-info-note">
          <Info class="w-4 h-4" />
          <span>Firmware: <code>El Trabajante/</code> · Docs: <code>CLAUDE.md</code></span>
        </div>
      </div>
    </div>
  </SlideOver>

  <RejectDeviceModal
    v-model:open="rejectModalOpen"
    :device-id="rejectTargetDevice?.device_id ?? ''"
    @confirm="confirmReject"
    @cancel="cancelReject"
  />
</template>

<style scoped>
.pdp-tabs {
  display: flex;
  gap: 0;
  padding: 0 var(--space-2);
  margin-bottom: var(--space-3);
  background: var(--glass-bg-l1);
  border-bottom: 1px solid var(--glass-border);
}

.pdp-tab {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  flex: 1;
  justify-content: center;
  padding: var(--space-2) var(--space-2);
  font-size: var(--text-sm);
  font-weight: 500;
  font-family: var(--font-body);
  color: var(--color-text-muted);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: color var(--transition-fast), background var(--transition-fast), border-color var(--transition-fast);
  min-height: 44px;
  white-space: nowrap;
}

.pdp-tab:hover {
  color: var(--color-text-secondary);
  background: rgba(255, 255, 255, 0.03);
}

.pdp-tab--active {
  color: var(--color-iridescent-1);
  border-bottom-color: var(--color-iridescent-1);
  background: rgba(96, 165, 250, 0.04);
}

.pdp-tab__icon { flex-shrink: 0; opacity: 0.7; }
.pdp-tab--active .pdp-tab__icon { opacity: 1; }

.pdp-tab-count {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-weight: 400;
}

.pdp-tab-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 1.125rem;
  height: 1.125rem;
  padding: 0 0.3rem;
  font-size: 0.6875rem;
  font-weight: 600;
  color: white;
  background: linear-gradient(135deg, var(--color-iridescent-1), var(--color-iridescent-3));
  border-radius: var(--radius-full);
}

.pdp-content {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.pdp-search {
  position: relative;
  display: flex;
  align-items: center;
}

.pdp-search-icon {
  position: absolute;
  left: var(--space-3);
  width: 1rem;
  height: 1rem;
  color: var(--color-text-muted);
  pointer-events: none;
}

.pdp-search-input {
  width: 100%;
  padding: var(--space-2) var(--space-3) var(--space-2) var(--space-8);
  font-size: var(--text-sm);
  font-family: var(--font-body);
  color: var(--color-text-primary);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  outline: none;
  transition: border-color var(--transition-fast);
}

.pdp-search-input::placeholder { color: var(--color-text-muted); }
.pdp-search-input:focus { border-color: var(--color-accent); }

.pdp-search-clear {
  position: absolute;
  right: var(--space-2);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  color: var(--color-text-muted);
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: color var(--transition-fast);
}

.pdp-search-clear:hover { color: var(--color-text-primary); }

.pdp-list { display: flex; flex-direction: column; gap: var(--space-3); }

.pdp-zone-group { display: flex; flex-direction: column; gap: var(--space-1); }

.pdp-zone-title {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  padding: 0 var(--space-2);
}

.pdp-zone-title--unassigned { color: var(--color-warning); }

.pdp-zone-group--unassigned {
  padding-top: var(--space-2);
  border-top: 1px solid var(--glass-border);
}

.pdp-device {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  transition: border-color var(--transition-fast);
}

.pdp-device:hover { border-color: var(--glass-border-hover); }

.pdp-device-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.pdp-device-name {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pdp-device-name--mono { font-family: var(--font-mono); }

.pdp-device-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  font-family: var(--font-body);
  color: var(--color-text-muted);
}

.pdp-status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.pdp-device-status { font-weight: 500; }
.pdp-device-sep { color: var(--glass-border); }
.pdp-meta-item { display: flex; align-items: center; gap: 0.25rem; }

.pdp-device-actions { display: flex; gap: var(--space-1); flex-shrink: 0; }

.pdp-pending-section { display: flex; flex-direction: column; gap: var(--space-3); }

.pdp-pending-device {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  border-left-width: 3px;
  border-left-color: transparent;
  transition: border-color var(--transition-base);
  animation: device-enter 0.35s var(--ease-out) calc(var(--stagger-index, 0) * 0.04s) both;
}

.pdp-pending-device:hover {
  border-color: var(--glass-border-hover);
  border-left-color: rgba(96, 165, 250, 0.4);
}

.pdp-pending-device--fresh {
  border-left-color: var(--color-iridescent-2);
  box-shadow: inset 0 0 12px rgba(96, 165, 250, 0.04);
}

.pdp-pending-device--processing { opacity: 0.7; pointer-events: none; }

@keyframes device-enter {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

.pdp-pending-actions { display: flex; gap: 0.375rem; }
.pdp-pending-actions :deep(button) { flex: 1; }

.pdp-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-8) var(--space-4);
  text-align: center;
}

.pdp-empty-icon { width: 2rem; height: 2rem; margin-bottom: var(--space-2); color: var(--color-text-muted); opacity: 0.7; }
.pdp-empty-text { font-size: var(--text-sm); font-family: var(--font-body); color: var(--color-text-secondary); line-height: var(--leading-loose); margin: 0; }
.pdp-empty-hint { color: var(--color-text-muted); font-size: var(--text-xs); }

.pdp-clear-search {
  margin-top: var(--space-2);
  padding: var(--space-1) var(--space-3);
  font-size: var(--text-sm);
  font-family: var(--font-body);
  color: var(--color-accent-bright);
  background: transparent;
  border: 1px solid rgba(96, 165, 250, 0.25);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.pdp-clear-search:hover { background: rgba(96, 165, 250, 0.1); }

.pdp-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: var(--space-8);
  color: var(--color-text-muted);
}

.pdp-loading-icon { width: 1.5rem; height: 1.5rem; color: var(--color-iridescent-2); animation: spin 0.8s linear infinite; }

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.pdp-footer {
  margin-top: auto;
  padding-top: var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  border-top: 1px solid var(--glass-border);
}

.pdp-info { padding: var(--space-1) 0; }

.pdp-info-title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
  font-size: var(--text-lg);
  font-weight: 600;
  font-family: var(--font-body);
  color: var(--color-text-primary);
}

.pdp-info-title-icon { width: 1.25rem; height: 1.25rem; color: var(--color-success); }

.pdp-info-text {
  margin-bottom: var(--space-3);
  font-size: var(--text-base);
  font-family: var(--font-body);
  color: var(--color-text-secondary);
  line-height: var(--leading-loose);
}

.pdp-steps { display: flex; flex-direction: column; gap: var(--space-2); }

.pdp-step {
  display: flex;
  gap: var(--space-2);
  padding: var(--space-2);
  background: var(--glass-bg-l1);
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--color-iridescent-2);
}

.pdp-step-number {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  height: 1.25rem;
  font-size: 0.6875rem;
  font-weight: 700;
  color: white;
  background: linear-gradient(135deg, var(--color-iridescent-1), var(--color-iridescent-3));
  border-radius: 50%;
  flex-shrink: 0;
}

.pdp-step-content { display: flex; flex-direction: column; gap: 0.125rem; }
.pdp-step-content strong { font-size: var(--text-sm); font-weight: 600; font-family: var(--font-body); color: var(--color-text-primary); }
.pdp-step-content span { font-size: var(--text-xs); font-family: var(--font-body); color: var(--color-text-secondary); }

.pdp-info-note {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-3);
  padding: var(--space-2);
  font-size: var(--text-xs);
  font-family: var(--font-body);
  color: var(--color-text-muted);
  background: var(--color-accent-bg);
  border-radius: var(--radius-sm);
}

.pdp-info-note code { color: var(--color-iridescent-2); font-family: var(--font-mono); font-size: 0.65rem; }

.pdp-usb-section {
  padding-top: var(--space-3);
  border-top: 1px solid var(--glass-border);
}

.pdp-usb-title {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  font-weight: 600;
  font-family: var(--font-body);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  padding: 0 var(--space-2);
  margin-bottom: var(--space-1);
}

.pdp-usb-empty { padding: var(--space-4); }

.pdp-device--column {
  flex-direction: column;
  align-items: stretch;
  gap: var(--space-1);
}

.pdp-device-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.pdp-flash-result {
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-xs);
  font-family: var(--font-body);
  border-radius: var(--radius-sm);
}

.pdp-flash-result--success {
  color: var(--color-success);
  background: rgba(52, 211, 153, 0.08);
}

.pdp-flash-result--error {
  color: var(--color-danger);
  background: rgba(248, 113, 113, 0.08);
}

/* AUT-767: Credentials Panel */
.pdp-credentials-section {
  padding: 0 var(--space-3);
  border-bottom: 1px solid var(--glass-border);
}

.pdp-creds-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.pdp-creds-fields {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.pdp-creds-loading {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

.pdp-creds-label {
  display: block;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: 500;
  margin-bottom: var(--space-1);
}

.pdp-creds-pw-group {
  width: 100%;
}

.pdp-creds-pw-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.pdp-creds-input {
  width: 100%;
  padding: var(--space-2) var(--space-4);
  padding-right: var(--space-8);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border-l2);
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.pdp-creds-input::placeholder {
  color: var(--color-text-muted);
}

.pdp-creds-input:focus {
  outline: none;
  border-color: transparent;
  box-shadow: 0 0 0 2px var(--color-accent);
}

.pdp-creds-eye {
  position: absolute;
  right: var(--space-2);
  background: none;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  padding: var(--space-1);
  transition: color var(--transition-fast);
  display: flex;
  align-items: center;
}

.pdp-creds-eye:hover {
  color: var(--color-text-primary);
}

.pdp-creds-build-status {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
}

.pdp-creds-build-status--saving,
.pdp-creds-build-status--building {
  background: rgba(96, 165, 250, 0.08);
  color: var(--color-text-secondary);
}

.pdp-creds-build-status--ready {
  background: rgba(34, 197, 94, 0.08);
  color: var(--color-success);
}

.pdp-creds-build-status--error {
  background: rgba(239, 68, 68, 0.08);
  color: var(--color-danger);
}

/* AUT-854: Flash mode selector */
.pdp-flash-mode {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-2) 0;
}

.pdp-flash-mode__label {
  font-size: var(--text-xs);
  font-weight: 600;
  font-family: var(--font-body);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
}

.pdp-flash-mode__options {
  display: flex;
  gap: var(--space-1);
  flex-wrap: wrap;
}

.pdp-flash-mode__btn {
  flex: 1;
  min-width: calc(33% - var(--space-1));
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-xs);
  font-weight: 500;
  font-family: var(--font-body);
  color: var(--color-text-secondary);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  min-height: 32px;
  text-align: center;
  white-space: nowrap;
}

.pdp-flash-mode__btn:hover {
  border-color: var(--glass-border-hover);
  color: var(--color-text-primary);
  background: rgba(255, 255, 255, 0.04);
}

.pdp-flash-mode__btn--active {
  background: rgba(96, 165, 250, 0.12);
  border-color: var(--color-iridescent-1);
  color: var(--color-iridescent-1);
  font-weight: 600;
}

.pdp-flash-mode__btn--danger.pdp-flash-mode__btn--active {
  background: rgba(248, 113, 113, 0.12);
  border-color: var(--color-danger);
  color: var(--color-danger);
}

.pdp-flash-mode__warning {
  font-size: var(--text-xs);
  font-family: var(--font-body);
  color: var(--color-warning);
  padding: var(--space-1) var(--space-2);
  background: rgba(251, 191, 36, 0.08);
  border-left: 2px solid var(--color-warning);
  border-radius: var(--radius-sm);
  line-height: var(--leading-loose);
}
</style>
