<script setup lang="ts">
/**
 * HardwareView — ESP & Hardware Topology (Übersicht)
 *
 * Route: /hardware, /hardware/:zoneId (scroll-anchor), /hardware/:zoneId/:espId
 *
 * Two-level navigation:
 * Level 1: Zone Accordion — all zones as expandable sections with ESP cards
 * Level 2: ESP Detail — single ESP with sensors/actuators (Orbital Layout)
 *
 * Zones are default-expanded, showing DeviceMiniCards directly.
 * Click on ESP card navigates to Orbital Layout (Level 2).
 * /hardware/:zoneId auto-expands and scrolls to that zone.
 */

import { ref, onMounted, onUnmounted, computed, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useEspStore } from '@/stores/esp'
import { useLogicStore } from '@/shared/stores/logic.store'
import { useZoneStore } from '@/shared/stores/zone.store'
import { useUiStore, useDashboardStore } from '@/shared/stores'
import type { ESPDevice } from '@/api/esp'
import type { ZoneEntity } from '@/types'
import { useZoneDragDrop, ZONE_UNASSIGNED, useKeyboardShortcuts, useSwipeNavigation } from '@/composables'
import { useToast } from '@/composables/useToast'
import { zonesApi } from '@/api/zones'
import { Plus, Filter, GitBranch, MapPin, XCircle, ChevronDown } from 'lucide-vue-next'
import { getESPStatus } from '@/composables/useESPStatus'
import { createLogger } from '@/utils/logger'
import { shouldFallbackToHardwareOverview } from '@/utils/hardwareRouteGuard'

const logger = createLogger('HardwareView')

// Tab Bar + Config Modal
import SlideOver from '@/shared/design/primitives/SlideOver.vue'
import ESPConfigPanel from '@/components/esp/ESPConfigPanel.vue'
import ConfigWizardModal from '@/components/esp/ConfigWizardModal.vue'
import PendingConfigBanner from '@/components/esp/PendingConfigBanner.vue'
import { useActuatorStore } from '@/shared/stores/actuator.store'

// Components
import CreateMockEspModal from '@/components/modals/CreateMockEspModal.vue'
import ESPSettingsSheet from '@/components/esp/ESPSettingsSheet.vue'
import ZoneSettingsSheet from '@/components/zones/ZoneSettingsSheet.vue'
import SubzonePlantPanel from '@/components/zones/SubzonePlantPanel.vue'
import ComponentSidebar from '@/components/dashboard/ComponentSidebar.vue'
import LoadingState from '@/shared/design/primitives/BaseSkeleton.vue'
// EmptyState replaced by custom inline hardware-empty block

// Level components
import ZonePlate from '@/components/dashboard/ZonePlate.vue'
import DeviceMiniCard from '@/components/dashboard/DeviceMiniCard.vue'
import DeviceDetailView from '@/components/esp/DeviceDetailView.vue'
import AccordionSection from '@/shared/design/primitives/AccordionSection.vue'
import CameraCard from '@/components/camera/CameraCard.vue'
import InlineDashboardPanel from '@/components/dashboard/InlineDashboardPanel.vue'
import BaseSpinner from '@/shared/design/primitives/BaseSpinner.vue'
import { VueDraggable } from 'vue-draggable-plus'
import { useDragStateStore } from '@/shared/stores/dragState.store'
import { Inbox } from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const espStore = useEspStore()
const logicStore = useLogicStore()
const uiStore = useUiStore()
const dashStore = useDashboardStore()
const { groupDevicesByZone, handleDeviceDrop, handleRemoveFromZone, generateZoneId, getAvailableZones } = useZoneDragDrop()
const { register } = useKeyboardShortcuts()
const dragStore = useDragStateStore()
const zoneStore = useZoneStore()
const actuatorStore = useActuatorStore()
const { success: showSuccess, error: showError, info: showInfo } = useToast()

const detailEspId = computed(() => (route.params.espId as string) || null)
const detailPendingConfigOrders = computed(() => {
  const espId = detailEspId.value
  if (!espId) return []
  return actuatorStore.pendingConfigOrders.filter((intent) => {
    const sid = intent.subjectId
    return sid === espId || sid.startsWith(`rest:${espId}:`) || sid.includes(espId)
  })
})

// =============================================================================
// Navigation State (route-param based, 2 levels)
// =============================================================================
const currentLevel = computed<1 | 2>(() => {
  if (route.params.espId) return 2
  return 1
})

const selectedZoneId = computed(() => (route.params.zoneId as string) || null)
const selectedEspId = computed(() => (route.params.espId as string) || null)

// Swipe navigation for mobile zoom-back
const zoomContainerRef = ref<HTMLElement | null>(null)
useSwipeNavigation(zoomContainerRef, {
  onSwipeRight: () => {
    if (currentLevel.value > 1) zoomOut()
  },
})

const centeredEspId = ref<string | null>(null)
const centeredOriginRect = ref<DOMRect | null>(null)
const l2ContainerRef = ref<HTMLElement | null>(null)

// =============================================================================
// Accordion State — per-zone expand/collapse with localStorage persistence (D3)
// =============================================================================
const COLLAPSE_KEY_PREFIX = 'ao-zone-collapse-'

/** Load persisted collapse state from localStorage */
function loadCollapseState(zoneId: string): boolean | null {
  try {
    const stored = localStorage.getItem(`${COLLAPSE_KEY_PREFIX}${zoneId}`)
    if (stored === null) return null
    return stored === '1'
  } catch {
    return null
  }
}

/** Persist collapse state to localStorage */
function saveCollapseState(zoneId: string, expanded: boolean) {
  try {
    localStorage.setItem(`${COLLAPSE_KEY_PREFIX}${zoneId}`, expanded ? '1' : '0')
  } catch {
    // Ignore storage errors
  }
}

const expandedZones = ref<Set<string>>(new Set())
const allZonesInitialized = ref(false)

/** Initialize zones: restore from localStorage, fallback to smart defaults */
watch(
  () => espStore.devices.length,
  () => {
    if (!allZonesInitialized.value && espStore.devices.length > 0) {
      const allZoneIds = Array.from(new Set(
        espStore.devices
          .filter(d => d.zone_id)
          .map(d => d.zone_id!)
      ))

      const expanded = new Set<string>()
      let hasStoredState = false

      for (const zoneId of allZoneIds) {
        const stored = loadCollapseState(zoneId)
        if (stored !== null) {
          hasStoredState = true
          if (stored) expanded.add(zoneId)
        }
      }

      if (!hasStoredState) {
        // First visit: expand all if ≤4 zones, otherwise only the first
        if (allZoneIds.length <= 4) {
          allZoneIds.forEach(id => expanded.add(id))
        } else if (allZoneIds.length > 0) {
          expanded.add(allZoneIds[0])
        }
      }

      // D3: Zones with offline devices → always expanded
      for (const zoneId of allZoneIds) {
        const devicesInZone = espStore.devices.filter(d => d.zone_id === zoneId)
        const hasOffline = devicesInZone.some(d => {
          const s = getESPStatus(d)
          return s === 'offline' || s === 'error'
        })
        if (hasOffline) expanded.add(zoneId)
      }

      expandedZones.value = expanded
      allZonesInitialized.value = true
    }
  },
  { immediate: true }
)

function isZoneExpanded(zoneId: string): boolean {
  return expandedZones.value.has(zoneId)
}

function setZoneExpanded(zoneId: string, expanded: boolean) {
  const next = new Set(expandedZones.value)
  if (expanded) {
    next.add(zoneId)
  } else {
    next.delete(zoneId)
  }
  expandedZones.value = next
  saveCollapseState(zoneId, expanded)
}

/**
 * When /hardware/:zoneId is navigated to (without espId),
 * auto-expand that zone and scroll to it.
 */
watch(
  () => [selectedZoneId.value, currentLevel.value] as const,
  async ([zoneId, level]) => {
    if (level === 1 && zoneId) {
      // Expand the targeted zone
      setZoneExpanded(zoneId, true)

      // Scroll to the zone element
      await nextTick()
      const el = document.getElementById(`zone-${zoneId}`)
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }

      // Replace route to clean /hardware/:zoneId → /hardware
      // (keeps the zone expanded, removes the intermediate route from history)
      router.replace({ name: 'hardware' })
    }
  },
  { immediate: true }
)

// Modal states
const settingsDevice = ref<ESPDevice | null>(null)
const isSettingsOpen = ref(false)
let settingsCloseTimer: ReturnType<typeof setTimeout> | null = null

// Handle ?openSettings=espId query param (legacy links + cross-component navigation)
watch(
  () => route.query.openSettings as string | undefined,
  (espId) => {
    if (!espId) return
    const device = espStore.devices.find(d => d.device_id === espId)
    if (device) {
      if (settingsCloseTimer) { clearTimeout(settingsCloseTimer); settingsCloseTimer = null }
      settingsDevice.value = device
      isSettingsOpen.value = true
    }
    // Clean the query param from URL
    router.replace({ path: route.path, query: { ...route.query, openSettings: undefined } })
  },
  { immediate: true }
)

// Config Wizard Modal state (unified sensor + actuator)
const isWizardOpen = ref(false)
const wizardPayload = ref<{
  espId: string
  gpio: number
  sensorType?: string
  unit?: string
  configId?: string
  actuatorType?: string
} | null>(null)
const showEspConfig = ref(false)
const configEspDevice = ref<ESPDevice | null>(null)

// =============================================================================
// Lifecycle
// =============================================================================
onMounted(() => {
  dashStore.activate()
  espStore.fetchAll()
  espStore.fetchPendingDevices()
  logicStore.fetchRules()
  logicStore.subscribeToWebSocket()
  zoneStore.fetchZoneEntities()
})

onUnmounted(() => {
  if (dragStore.isAnyDragActive) {
    dragStore.endDrag()
  }
  if (settingsCloseTimer) {
    clearTimeout(settingsCloseTimer)
    settingsCloseTimer = null
  }
  dashStore.deactivate()
  logicStore.unsubscribeFromWebSocket()
})

// Keyboard: Escape to zoom out
const unregisterEscape = register({
  key: 'Escape',
  handler: () => {
    if (currentLevel.value > 1) zoomOut()
  },
  description: 'Zurück zur Übersicht',
  scope: 'global',
})
onUnmounted(() => unregisterEscape())

// =============================================================================
// Filtered ESPs & Zone Grouping
// =============================================================================
const filteredEsps = computed(() => {
  let esps = espStore.devices

  if (dashStore.filterType === 'mock') {
    esps = esps.filter(e => espStore.isMock(espStore.getDeviceId(e)))
  } else if (dashStore.filterType === 'real') {
    esps = esps.filter(e => !espStore.isMock(espStore.getDeviceId(e)))
  }

  const filters = dashStore.activeStatusFilters
  if (filters.size > 0) {
    esps = esps.filter(device => {
      const status = getESPStatus(device)

      if (filters.has('online') && (status === 'online' || status === 'stale')) return true
      if (filters.has('offline') && (status === 'offline' || status === 'unknown')) return true
      if (filters.has('warning')) {
        if (status === 'error') return true
        const actuators = (device as any).actuators as Array<{ emergency_stopped?: boolean }> | undefined
        if (actuators?.some(a => a.emergency_stopped)) return true
      }
      if (filters.has('safemode') && status === 'safemode') return true
      return false
    })
  }

  return esps
})

const zoneGroups = computed(() => {
  const allGroups = groupDevicesByZone(filteredEsps.value)
  const zones = allGroups.filter(g => g.zoneId !== ZONE_UNASSIGNED)

  // D1: Sort zones — offline/warning first, then online, empty last, alpha within
  zones.sort((a, b) => {
    const aHasProblems = a.devices.some(d => {
      const s = getESPStatus(d)
      return s === 'offline' || s === 'error'
    })
    const bHasProblems = b.devices.some(d => {
      const s = getESPStatus(d)
      return s === 'offline' || s === 'error'
    })
    const aEmpty = a.devices.length === 0
    const bEmpty = b.devices.length === 0

    // Problems first
    if (aHasProblems && !bHasProblems) return -1
    if (!aHasProblems && bHasProblems) return 1
    // Empty last
    if (aEmpty && !bEmpty) return 1
    if (!aEmpty && bEmpty) return -1
    // Alpha within same category
    return (a.zoneName ?? '').localeCompare(b.zoneName ?? '')
  })

  return zones
})

// =============================================================================
// Zone Entity Integration (T13-R3 WP2)
// =============================================================================

/** Map zone_id → ZoneEntity for quick lookup */
const zoneEntityMap = computed(() => {
  const map = new Map<string, ZoneEntity>()
  for (const ze of zoneStore.zoneEntities) {
    map.set(ze.zone_id, ze)
  }
  return map
})

/** Active zone entities merged with device grouping data */
interface ZoneDisplayEntry {
  zoneId: string
  zoneName: string
  devices: ESPDevice[]
  zoneEntity?: ZoneEntity
  isArchived: boolean
}

function toUserFriendlyZoneName(zoneId: string, ...candidates: Array<string | null | undefined>): string {
  for (const candidate of candidates) {
    const normalized = candidate?.trim()
    if (normalized && normalized !== zoneId) {
      return normalized
    }
  }

  const fallback = candidates.find(value => value && value.trim())?.trim()
  if (fallback) {
    return fallback
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ')
  }

  return zoneId
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

const activeZoneEntries = computed((): ZoneDisplayEntry[] => {
  const deviceGroupMap = new Map<string, { zoneName: string; devices: ESPDevice[] }>()
  for (const g of zoneGroups.value) {
    deviceGroupMap.set(g.zoneId, { zoneName: g.zoneName, devices: g.devices })
  }

  // Start from active zone entities (DB-backed)
  const entries: ZoneDisplayEntry[] = []
  const seenZoneIds = new Set<string>()

  for (const ze of zoneStore.activeZones) {
    const group = deviceGroupMap.get(ze.zone_id)
    entries.push({
      zoneId: ze.zone_id,
      zoneName: toUserFriendlyZoneName(ze.zone_id, ze.name, group?.zoneName),
      devices: group?.devices ?? [],
      zoneEntity: ze,
      isArchived: false,
    })
    seenZoneIds.add(ze.zone_id)
  }

  // Add device-only zones (devices assigned to zones not yet in DB)
  for (const g of zoneGroups.value) {
    if (!seenZoneIds.has(g.zoneId)) {
      entries.push({
        zoneId: g.zoneId,
        zoneName: g.zoneName ?? g.zoneId,
        devices: g.devices,
        zoneEntity: undefined,
        isArchived: false,
      })
    }
  }

  // Sort: problems first, empty last, alpha within
  entries.sort((a, b) => {
    const aHasProblems = a.devices.some(d => {
      const s = getESPStatus(d)
      return s === 'offline' || s === 'error'
    })
    const bHasProblems = b.devices.some(d => {
      const s = getESPStatus(d)
      return s === 'offline' || s === 'error'
    })
    const aEmpty = a.devices.length === 0
    const bEmpty = b.devices.length === 0
    if (aHasProblems && !bHasProblems) return -1
    if (!aHasProblems && bHasProblems) return 1
    if (aEmpty && !bEmpty) return 1
    if (!aEmpty && bEmpty) return -1
    return (a.zoneName ?? '').localeCompare(b.zoneName ?? '')
  })

  return entries
})

/** Archived zone entities with their devices */
const archivedZoneEntries = computed((): ZoneDisplayEntry[] => {
  return zoneStore.archivedZones.map(ze => {
    const devices = filteredEsps.value.filter(d => d.zone_id === ze.zone_id)
    const deviceZoneName = devices.find(d => d.zone_name)?.zone_name
    return {
      zoneId: ze.zone_id,
      zoneName: toUserFriendlyZoneName(ze.zone_id, ze.name, deviceZoneName),
      devices,
      zoneEntity: ze,
      isArchived: true,
    }
  })
})

// ZoneSettingsSheet state
const zoneSettingsEntity = ref<ZoneEntity | null>(null)
const isZoneSettingsOpen = ref(false)

function openZoneSettings(zoneId: string) {
  const entity = zoneEntityMap.value.get(zoneId)
  if (!entity) return
  zoneSettingsEntity.value = entity
  isZoneSettingsOpen.value = true
}

function handleZoneSettingsClose() {
  isZoneSettingsOpen.value = false
  setTimeout(() => { if (!isZoneSettingsOpen.value) zoneSettingsEntity.value = null }, 200)
}

// SubzonePlantPanel state (AUT-252 Section C)
const subzonePlantData = ref<{ subzoneId: string; subzoneName: string } | null>(null)
const isSubzonePlantOpen = ref(false)

function openSubzonePlant(payload: { subzoneId: string; subzoneName: string; zoneId: string }) {
  subzonePlantData.value = { subzoneId: payload.subzoneId, subzoneName: payload.subzoneName }
  isSubzonePlantOpen.value = true
}

function closeSubzonePlant() {
  isSubzonePlantOpen.value = false
  setTimeout(() => {
    if (!isSubzonePlantOpen.value) subzonePlantData.value = null
  }, 200)
}

function handleZoneEntityUpdated() {
  zoneStore.fetchZoneEntities()
  espStore.fetchAll()
}

function handleZoneEntityArchived() {
  zoneStore.fetchZoneEntities()
  handleZoneSettingsClose()
}

/** Unassigned devices — filtered to match active status/type filters */
const unassignedDevices = computed(() => {
  const filters = dashStore.activeStatusFilters
  const filterType = dashStore.filterType
  // If no filters active, fall back to store source of truth
  if (filters.size === 0 && filterType === 'all') return espStore.unassignedDevices
  // Otherwise derive from filteredEsps to stay consistent with zone groups
  return filteredEsps.value.filter(d => !d.zone_id)
})

/** Local copy for VueDraggable v-model (unassigned section) */
const localUnassignedDevices = ref<ESPDevice[]>([])
watch(unassignedDevices, (newDevices) => {
  localUnassignedDevices.value = [...newDevices]
}, { immediate: true, deep: true })

/** Unassigned section default open when devices exist */
const unassignedSectionOpen = ref(unassignedDevices.value.length > 0)
watch(() => unassignedDevices.value.length, (len) => {
  if (len > 0) unassignedSectionOpen.value = true
})

function isMockDevice(device: ESPDevice): boolean {
  return espStore.isMock(espStore.getDeviceId(device))
}

function endAnyDragIfActive(): void {
  if (dragStore.isAnyDragActive) {
    dragStore.endDrag()
  }
}

async function handleUnassignedDragAdd(event: any) {
  const deviceId = event?.item?.dataset?.deviceId
  if (!deviceId) {
    return
  }

  const device = espStore.devices.find(d =>
    espStore.getDeviceId(d) === deviceId
  )
  if (!device) {
    return
  }

  // Device was dropped into unassigned — remove from zone
  if (device.zone_id) {
    await handleRemoveFromZone(device)
    return
  }
  return
}

function handleUnassignedDragStart() {
  dragStore.startEspCardDrag()
}

function handleUnassignedDragEnd() {
  dragStore.endEspCardDrag()
}

// =============================================================================
// Zone Create (inline form)
// =============================================================================
const showCreateZoneForm = ref(false)
const newZoneName = ref('')
const selectedEspForNewZone = ref('')

async function handleZoneCreate() {
  const name = newZoneName.value.trim()
  if (!name) return

  const zoneId = generateZoneId(name)
  try {
    // Create DB-backed zone entity
    await zoneStore.createZone({ zone_id: zoneId, name })

    // If an ESP was selected, assign it to the new zone
    if (selectedEspForNewZone.value) {
      await zonesApi.assignZone(selectedEspForNewZone.value, {
        zone_id: zoneId,
        zone_name: name,
      })
      await espStore.fetchAll()
    }

    showSuccess(`Zone "${name}" erstellt`)
    showCreateZoneForm.value = false
    newZoneName.value = ''
    selectedEspForNewZone.value = ''
    // Auto-expand the new zone
    setZoneExpanded(zoneId, true)
  } catch (err) {
    showError(err instanceof Error ? err.message : 'Zone konnte nicht erstellt werden')
    logger.error('Failed to create zone', err)
  }
}

function cancelZoneCreate() {
  endAnyDragIfActive()
  showCreateZoneForm.value = false
  newZoneName.value = ''
  selectedEspForNewZone.value = ''
}

// =============================================================================
// Level 2 (Orbital) computed
// =============================================================================

const selectedDevice = computed(() => {
  if (!selectedEspId.value) return null
  return espStore.devices.find(d => espStore.getDeviceId(d) === selectedEspId.value) ?? null
})

watch(
  selectedDevice,
  (nextDevice, previousDevice) => {
    const shouldFallback = shouldFallbackToHardwareOverview({
      currentLevel: currentLevel.value,
      selectedEspId: selectedEspId.value,
      nextDeviceExists: nextDevice !== null,
      previousDeviceExists: previousDevice !== null,
    })
    if (!shouldFallback) return
    if (!previousDevice) return

    logger.info('L2 fallback to L1: selected device missing', {
      selectedEspId: selectedEspId.value,
      previousDeviceId: espStore.getDeviceId(previousDevice),
    })
    router.replace({ name: 'hardware' })
  },
)

const selectedZoneName = computed(() => {
  if (!selectedZoneId.value) return ''
  const zoneDevices = espStore.devices.filter(d => d.zone_id === selectedZoneId.value)
  const zoneName = zoneDevices[0]?.zone_name || selectedZoneId.value
  const total = zoneDevices.length
  const online = zoneDevices.filter(d => {
    const s = getESPStatus(d)
    return s === 'online' || s === 'stale'
  }).length
  return `Zone: ${zoneName} (${online}/${total} Online)`
})

const selectedDeviceName = computed(() => {
  if (!selectedDevice.value) return ''
  return selectedDevice.value.name || espStore.getDeviceId(selectedDevice.value)
})

// =============================================================================
// Breadcrumb → Dashboard Store
// =============================================================================
watch(
  [currentLevel, selectedZoneName, selectedDeviceName],
  ([level, zone, device]) => {
    // Map new 2-level to dashStore's 3-level breadcrumb format
    // Level 2 (Orbital) maps to old Level 3 for TopBar
    const breadcrumbLevel = level === 2 ? 3 : 1
    dashStore.breadcrumb = {
      level: breadcrumbLevel as 1 | 2 | 3,
      zoneName: zone,
      deviceName: device,
      sensorName: '',
      ruleName: '',
      dashboardName: '',
    }
  },
  { immediate: true }
)

// =============================================================================
// Navigation helpers
// =============================================================================
function zoomToDevice(deviceId: string) {
  const device = espStore.devices.find(d => espStore.getDeviceId(d) === deviceId)
  const zoneId = device?.zone_id || 'unknown'
  router.push({ name: 'hardware-esp', params: { zoneId, espId: deviceId } })
}

function zoomOut() {
  if (currentLevel.value === 2) {
    router.push({ name: 'hardware' })
  }
}

// =============================================================================
// Event Handlers
// =============================================================================

function onDeviceCardClick(payload: { deviceId: string; originRect: DOMRect }) {
  centeredEspId.value = payload.deviceId
  centeredOriginRect.value = payload.originRect
  zoomToDevice(payload.deviceId)
}

watch(currentLevel, async (level) => {
  if (level === 2 && centeredOriginRect.value && l2ContainerRef.value) {
    await nextTick()
    const last = l2ContainerRef.value.getBoundingClientRect()
    const orig = centeredOriginRect.value
    const dx = orig.left + orig.width / 2 - (last.left + last.width / 2)
    const dy = orig.top + orig.height / 2 - (last.top + last.height / 2)
    const scale = Math.min(orig.width / last.width, 0.15)
    l2ContainerRef.value.style.setProperty('--flip-start-x', `${dx}px`)
    l2ContainerRef.value.style.setProperty('--flip-start-y', `${dy}px`)
    l2ContainerRef.value.style.setProperty('--flip-start-scale', `${scale}`)
  }
  if (level === 1) {
    centeredEspId.value = null
    centeredOriginRect.value = null
  }
})

function onDeviceMonitorNav(device: ESPDevice) {
  const zoneId = device.zone_id
  if (zoneId) {
    router.push({ name: 'monitor-zone', params: { zoneId } })
  }
}

async function onDeviceDropped(payload: { device: any; fromZoneId: string | null; toZoneId: string }) {
  await handleDeviceDrop(payload)
}

function resetFilters() {
  dashStore.resetFilters()
}

function onMockEspCreated(espId: string) {
  espStore.fetchAll()
  logger.info(`Mock ESP erstellt: ${espId}`)
}

async function handleHeartbeat(espId: string) {
  if (!espStore.isMock(espId)) return
  try {
    await espStore.triggerHeartbeat(espId)
  } catch (err) {
    logger.error(`Failed to trigger heartbeat for ${espId}`, err)
  }
}

async function handleDelete(espId: string) {
  const device = espStore.devices.find(d => espStore.getDeviceId(d) === espId)
  const displayName = device?.name || espId
  const confirmed = await uiStore.confirm({
    title: 'Gerät löschen',
    message: `Möchtest du "${displayName}" wirklich löschen?`,
    variant: 'danger',
    confirmText: 'Löschen',
  })
  if (!confirmed) return
  try {
    await espStore.deleteDevice(espId)
  } catch (err) {
    logger.error(`Failed to delete device ${espId}`, err)
  }
}

function handleSettings(device: ESPDevice) {
  if (settingsCloseTimer) { clearTimeout(settingsCloseTimer); settingsCloseTimer = null }
  settingsDevice.value = device
  isSettingsOpen.value = true
}

/** Click-to-Place: Show zone picker via context menu */
function handleChangeZone(device: ESPDevice) {
  const currentZoneId = device.zone_id || null

  // Build zone menu items from available zones
  const availableZones = getAvailableZones(espStore.devices)
  const menuItems: Array<{ id: string; label: string; icon: any; action: () => void; variant?: 'default' | 'danger' }> = []

  for (const zone of availableZones) {
    if (zone.zoneId === currentZoneId) continue // Skip current zone
    menuItems.push({
      id: `zone-${zone.zoneId}`,
      label: zone.zoneName,
      icon: MapPin,
      action: async () => {
        await handleDeviceDrop({
          device,
          fromZoneId: currentZoneId,
          toZoneId: zone.zoneId,
        })
      },
    })
  }

  // Add "Remove from zone" option if device has a zone
  if (currentZoneId) {
    menuItems.push({
      id: 'remove-zone',
      label: 'Aus Zone entfernen',
      icon: XCircle,
      variant: 'danger',
      action: async () => {
        await handleRemoveFromZone(device)
      },
    })
  }

  if (menuItems.length === 0) {
    showError('Keine anderen Zonen vorhanden')
    return
  }

  // Position context menu near the device card (not screen center)
  const deviceId = espStore.getDeviceId(device)
  const cardEl = document.querySelector(`[data-device-id="${deviceId}"]`)
  let x = window.innerWidth / 2
  let y = window.innerHeight / 2
  if (cardEl) {
    const rect = cardEl.getBoundingClientRect()
    x = rect.right
    y = rect.top
  }
  uiStore.openContextMenu(x, y, menuItems)
}

function handleSettingsClose() {
  endAnyDragIfActive()
  isSettingsOpen.value = false
  if (settingsCloseTimer) clearTimeout(settingsCloseTimer)
  settingsCloseTimer = setTimeout(() => {
    settingsDevice.value = null
    settingsCloseTimer = null
  }, 200)
}

function closeWizard() {
  endAnyDragIfActive()
  isWizardOpen.value = false
}

/**
 * AUT-251: User clicked "im Geraet aendern" inside ConfigWizardModal.
 * Closes the wizard and opens the ESP-Settings-Sheet for the device.
 */
function handleOpenEspSettingsFromConfig(payload: { espId: string }) {
  const device = espStore.devices.find(d => espStore.getDeviceId(d) === payload.espId)
  if (!device) return
  isWizardOpen.value = false
  if (settingsCloseTimer) { clearTimeout(settingsCloseTimer); settingsCloseTimer = null }
  settingsDevice.value = device
  isSettingsOpen.value = true
}

function handleDeviceDeleted(_payload: { deviceId: string }) {
  handleSettingsClose()
}

function handleNameUpdated(payload: { deviceId: string; name: string | null }) {
  logger.info(`Device name updated: ${payload.deviceId} → "${payload.name || 'Unbenannt'}"`)
}

function handleZoneUpdated(payload: { deviceId: string; zoneId: string; zoneName: string }) {
  logger.info(`Zone updated: ${payload.deviceId} → "${payload.zoneName}"`)
}

// =============================================================================
// Zone Management (Rename) — zones are string fields, not DB entities
// =============================================================================

/** Rename zone: reassign all ESPs in the zone with the new zone_name */
async function handleZoneRename(payload: { zoneId: string; newName: string }) {
  const newName = payload.newName.trim()
  if (!newName) return

  const zoneEntity = zoneEntityMap.value.get(payload.zoneId)
  const devicesInZone = espStore.devices.filter(d => d.zone_id === payload.zoneId)
  if (!zoneEntity && devicesInZone.length === 0) return

  try {
    // Keep DB entity display name in sync with what users entered.
    if (zoneEntity && zoneEntity.name !== newName) {
      await zoneStore.updateZone(payload.zoneId, { name: newName })
    }

    for (const device of devicesInZone) {
      const devId = espStore.getDeviceId(device)
      if (device.zone_name === newName) continue
      await zonesApi.assignZone(devId, {
        zone_id: payload.zoneId,
        zone_name: newName,
      })
    }

    if (devicesInZone.length > 0) {
      await espStore.fetchAll()
    }

    showSuccess(`Zone umbenannt zu "${newName}"`)
  } catch (err) {
    showError(err instanceof Error ? err.message : 'Zone konnte nicht umbenannt werden')
    logger.error(`Failed to rename zone ${payload.zoneId}`, err)
  }
}

// =============================================================================
// SlideOver handlers: open config panels from ESP detail view
// =============================================================================

function handleSensorClickFromDetail(payload: { espId: string; gpio: number; sensorType: string; configId?: string }) {
  const device = espStore.devices.find(d => espStore.getDeviceId(d) === payload.espId)
  const sensors = (device?.sensors as any[]) || []

  // Primary: gpio + sensorType (unique for multi-value sensors like SHT31)
  let sensor = sensors.find((s: any) => s.gpio === payload.gpio && s.sensor_type === payload.sensorType)
  // Fallback: GPIO only (backward compat for single-value sensors)
  if (!sensor) sensor = sensors.find((s: any) => s.gpio === payload.gpio)
  if (!sensor) return

  wizardPayload.value = {
    espId: payload.espId,
    gpio: payload.gpio,
    sensorType: sensor.sensor_type || 'unknown',
    unit: sensor.unit || '',
    configId: payload.configId || sensor.config_id,
  }
  isWizardOpen.value = true
}

function handleActuatorClickFromDetail(payload: { espId: string; gpio: number }) {
  const device = espStore.devices.find(d => espStore.getDeviceId(d) === payload.espId)
  const actuators = (device?.actuators as any[]) || []
  const actuator = actuators.find((a: any) => a.gpio === payload.gpio)
  if (!actuator) return

  wizardPayload.value = {
    espId: payload.espId,
    gpio: payload.gpio,
    actuatorType: actuator.actuator_type || 'relay',
  }
  isWizardOpen.value = true
}

</script>

<template>
  <div class="hardware-view">
    <!-- View Tab Bar (Übersicht / Monitor / Editor) -->

    <!-- Loading / Empty State (grouped to prevent white flash on device deletion) -->
    <LoadingState v-if="espStore.isLoading && espStore.devices.length === 0" text="Lade ESP-Geräte..." />
    <div v-else-if="espStore.devices.length === 0" class="hardware-empty">
      <div class="hardware-empty__icon-wrapper">
        <Plus class="hardware-empty__icon" />
      </div>
      <h3 class="hardware-empty__title">Keine Geräte konfiguriert</h3>
      <p class="hardware-empty__desc">Erstelle dein erstes Mock-ESP, um das System zu testen.</p>
      <button class="hardware-empty__btn" @click="dashStore.showCreateMock = true">
        <Plus class="hardware-empty__btn-icon" />
        Gerät erstellen
      </button>
      <button
        class="hardware-empty__link"
        @click="dashStore.showPendingPanel = true"
      >
        Oder verbinde ein echtes ESP32
      </button>
    </div>

    <!-- No Results (filters) -->
    <div v-else-if="filteredEsps.length === 0" class="card p-8 text-center">
      <Filter class="w-12 h-12 mx-auto mb-4" style="color: var(--color-text-muted)" />
      <h3 class="font-semibold mb-2" style="color: var(--color-text-secondary)">Keine Ergebnisse</h3>
      <p style="color: var(--color-text-muted)" class="mb-4">Keine Geräte entsprechen den aktuellen Filtern.</p>
      <button class="btn-secondary" @click="resetFilters">Filter zurücksetzen</button>
    </div>

    <!-- Two-Level Hardware View -->
    <div v-else class="hardware-content" :class="{ 'hardware-content--has-side': dashStore.hardwarePanels.length > 0 }">
      <div class="hardware-main-layout">
        <div ref="zoomContainerRef" class="zoom-container">

          <!-- LEVEL 1: Zone Accordion Overview (always visible, dimmed when overlay is open) -->
          <div class="zoom-level--l1" :class="{ 'zoom-level--l1--dimmed': currentLevel === 2 }">
            <!-- Camera Snapshot Panel (AUT-572 Welle 1) — conditionally rendered via server capability -->
            <CameraCard class="hardware-camera-panel" />
            <div class="zone-accordion-list">
              <div v-if="zoneGroups.length === 0" class="no-zones-hint">
                <p>Alle Geräte sind noch keiner Zone zugewiesen.</p>
                <p class="text-sm">Ziehe Geräte aus der unteren Leiste in eine Zone.</p>
              </div>
              <!-- B1.1: Warnbanner "Nicht zugewiesen" ueber Zone-Liste (prominent oben mit Bezug auf folgende Zonen). -->
              <div
                v-if="unassignedDevices.length > 0"
                class="unassigned-banner"
                role="status"
                aria-live="polite"
              >
                <Inbox class="unassigned-banner__icon" aria-hidden="true" />
                <div class="unassigned-banner__body">
                  <strong class="unassigned-banner__count">
                    {{ unassignedDevices.length }} Gerät{{ unassignedDevices.length === 1 ? '' : 'e' }}
                  </strong>
                  ohne Zone — per Drag-and-drop unten in eine Zone ziehen.
                </div>
              </div>

              <ZonePlate
                v-for="entry in activeZoneEntries"
                :id="`zone-${entry.zoneId}`"
                :key="entry.zoneId"
                :zone-id="entry.zoneId"
                :zone-name="entry.zoneName"
                :devices="entry.devices"
                :zone-entity="entry.zoneEntity"
                :is-expanded="isZoneExpanded(entry.zoneId)"
                @update:is-expanded="setZoneExpanded(entry.zoneId, $event)"
                @device-click="onDeviceCardClick"
                @device-dropped="onDeviceDropped"
                @change-zone="handleChangeZone"
                @rename="handleZoneRename"
                @device-delete="handleDelete"
                @settings="handleSettings"
                @monitor-nav="onDeviceMonitorNav"
                @zone-settings="openZoneSettings"
                @subzone-plant="openSubzonePlant"
              />

              <!-- Unassigned Devices Section (hidden when empty) -->
              <section
                v-if="unassignedDevices.length > 0 || dragStore.isDraggingEspCard"
                class="unassigned-section"
                :class="{ 'unassigned-section--drop-target': dragStore.isDraggingEspCard }"
              >
                <AccordionSection
                  v-model="unassignedSectionOpen"
                  storage-key="ao-unassigned-section"
                  class="unassigned-section__accordion"
                >
                  <template #header="{ isOpen, toggle }">
                    <div class="unassigned-section__header" @click="toggle">
                      <ChevronDown
                        class="unassigned-section__chevron"
                        :class="{ 'unassigned-section__chevron--collapsed': !isOpen }"
                      />
                      <Inbox class="unassigned-section__icon" />
                      <h3 class="unassigned-section__title">Nicht zugewiesen</h3>
                      <span v-if="unassignedDevices.length > 0" class="unassigned-section__count">
                        {{ unassignedDevices.length }}
                      </span>
                      <span v-if="unassignedDevices.length > 0" class="unassigned-section__context">Per Drag-and-drop einer Zone zuweisen</span>
                      <span v-else class="unassigned-section__empty-hint">
                        Alle Geräte zugewiesen
                      </span>
                    </div>
                  </template>

                  <VueDraggable
                    v-model="localUnassignedDevices"
                    class="unassigned-section__devices grid-auto-md"
                    group="esp-devices"
                    :animation="150"
                    handle=".esp-drag-handle"
                    :force-fallback="true"
                    :fallback-on-body="true"
                    ghost-class="zone-item--ghost"
                    chosen-class="zone-item--chosen"
                    drag-class="zone-item--drag"
                    :swap-threshold="0.65"
                    :delay-on-touch-only="true"
                    :delay="300"
                    :fallback-tolerance="5"
                    :touch-start-threshold="3"
                    @add="handleUnassignedDragAdd"
                    @start="handleUnassignedDragStart"
                    @end="handleUnassignedDragEnd"
                  >
                    <div
                      v-for="device in localUnassignedDevices"
                      :key="espStore.getDeviceId(device)"
                      :data-device-id="espStore.getDeviceId(device)"
                      class="unassigned-section__device-wrapper"
                    >
                      <DeviceMiniCard
                        :device="device"
                        :is-mock="isMockDevice(device)"
                        @click="onDeviceCardClick"
                        @change-zone="handleChangeZone"
                        @settings="handleSettings"
                        @device-delete="handleDelete"
                      />
                    </div>
                  </VueDraggable>

                  <div v-if="unassignedDevices.length === 0" class="unassigned-section__all-assigned">
                    <Inbox class="unassigned-section__all-assigned-icon" />
                    <span>Alle Geräte sind Zonen zugewiesen</span>
                  </div>
                </AccordionSection>
              </section>

              <!-- Zone Create: inline form -->
              <div v-if="showCreateZoneForm" class="zone-create-form">
                <input
                  v-model="newZoneName"
                  class="zone-create-form__input"
                  placeholder="Zone-Name"
                  maxlength="60"
                  @keydown.enter.prevent="handleZoneCreate"
                  @keydown.escape.prevent="cancelZoneCreate"
                />
                <select
                  v-if="unassignedDevices.length > 0"
                  v-model="selectedEspForNewZone"
                  class="zone-create-form__select"
                >
                  <option value="">Kein ESP zuweisen</option>
                  <option
                    v-for="dev in unassignedDevices"
                    :key="espStore.getDeviceId(dev)"
                    :value="espStore.getDeviceId(dev)"
                  >
                    {{ dev.name || espStore.getDeviceId(dev) }}
                  </option>
                </select>
                <button
                  class="zone-create-form__btn zone-create-form__btn--primary"
                  :disabled="!newZoneName.trim()"
                  @click="handleZoneCreate"
                >
                  Erstellen
                </button>
                <button
                  class="zone-create-form__btn"
                  @click="cancelZoneCreate"
                >
                  Abbrechen
                </button>
              </div>

              <!-- + Zone erstellen button (FL-01: zones are standalone entities, no ESP required) -->
              <button
                v-if="!showCreateZoneForm"
                class="zone-create-btn"
                title="Neue Zone erstellen"
                @click="showCreateZoneForm = true"
              >
                <Plus class="zone-create-btn__icon" />
                Zone erstellen
              </button>
              <!-- Archived Zones (collapsible) -->
              <AccordionSection
                v-if="archivedZoneEntries.length > 0"
                :title="`Archivierte Zonen (${archivedZoneEntries.length})`"
                storage-key="ao-archived-zones"
                :default-open="false"
                class="archived-zones-section"
              >
                <ZonePlate
                  v-for="entry in archivedZoneEntries"
                  :key="entry.zoneId"
                  :zone-id="entry.zoneId"
                  :zone-name="entry.zoneName"
                  :devices="entry.devices"
                  :zone-entity="entry.zoneEntity"
                  :is-archived="true"
                  :is-expanded="isZoneExpanded(entry.zoneId)"
                  @update:is-expanded="setZoneExpanded(entry.zoneId, $event)"
                  @device-click="onDeviceCardClick"
                  @settings="handleSettings"
                  @monitor-nav="onDeviceMonitorNav"
                  @zone-settings="openZoneSettings"
                  @subzone-plant="openSubzonePlant"
                />
              </AccordionSection>
            </div>

            <button
              v-if="logicStore.crossEspConnections.length > 0"
              class="cross-esp-toggle"
              :title="'Cross-ESP Visualisierung (demnächst verfügbar)'"
              @click="showInfo('Cross-ESP Visualisierung wird noch entwickelt')"
            >
              <GitBranch class="w-4 h-4" />
              <span>{{ logicStore.crossEspConnections.length }} Cross-ESP</span>
            </button>
          </div>

        </div>

      </div>

      <!-- Hardware Side-Panel (target.view='hardware', placement='side-panel') -->
      <aside v-if="dashStore.hardwarePanels.length > 0" class="hardware-side-panel">
        <InlineDashboardPanel
          v-for="panel in dashStore.hardwarePanels"
          :key="panel.id"
          :layoutId="panel.id"
          mode="side-panel"
        />
      </aside>
    </div>

    <!-- LEVEL 2: Orbital Overlay — opens above L1 (Teleport to body, S4/S5) -->
    <Teleport to="body">
      <Transition name="orbital-overlay">
        <div
          v-if="currentLevel === 2"
          class="orbital-overlay"
          role="dialog"
          aria-modal="true"
          @click.self="zoomOut"
        >
          <div ref="l2ContainerRef" class="orbital-overlay__panel zoom-level--l2">
            <div
              v-if="detailPendingConfigOrders.length > 0"
              class="hardware-pending-config-stack"
              role="status"
              aria-live="polite"
            >
              <PendingConfigBanner
                v-for="order in detailPendingConfigOrders"
                :key="order.intentId"
                :subject-id="order.subjectId"
                :correlation-id="order.correlationId"
              />
            </div>
            <DeviceDetailView
              v-if="selectedDevice"
              :device="selectedDevice"
              :zone-id="selectedZoneId || ''"
              :zone-name="selectedZoneName"
              @back="zoomOut()"
              @settings="handleSettings"
              @delete="handleDelete"
              @heartbeat="handleHeartbeat"
              @name-updated="handleNameUpdated"
              @sensor-click="handleSensorClickFromDetail"
              @actuator-click="handleActuatorClickFromDetail"
            />
            <div v-else class="orbital-device-not-found">
              <BaseSpinner size="lg" />
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Component Palette: Top-Drawer in Orbital Mode (S7, above overlay) -->
    <Teleport to="body">
      <Transition name="palette-slide">
        <ComponentSidebar
          v-show="currentLevel === 2"
          :orbital-mode="true"
        />
      </Transition>
    </Teleport>

    <!-- Create Mock ESP Modal -->
    <CreateMockEspModal v-model="dashStore.showCreateMock" @created="onMockEspCreated" />

    <!-- ESP Settings Sheet -->
    <ESPSettingsSheet
      v-if="settingsDevice"
      :device="settingsDevice"
      :is-open="isSettingsOpen"
      @update:is-open="isSettingsOpen = $event"
      @close="handleSettingsClose"
      @deleted="handleDeviceDeleted"
      @heartbeat-triggered="(p: any) => handleHeartbeat(p.deviceId)"
      @name-updated="handleNameUpdated"
      @zone-updated="handleZoneUpdated"
    />

    <!-- Zone Settings Sheet -->
    <ZoneSettingsSheet
      v-if="zoneSettingsEntity"
      :zone="zoneSettingsEntity"
      :is-open="isZoneSettingsOpen"
      :device-count="filteredEsps.filter(d => d.zone_id === zoneSettingsEntity?.zone_id).length"
      @close="handleZoneSettingsClose"
      @zone-updated="handleZoneEntityUpdated"
      @zone-archived="handleZoneEntityArchived"
      @zone-reactivated="handleZoneEntityUpdated"
    />

    <!-- Subzone Plant Panel (AUT-252 Section C) -->
    <SlideOver
      :open="isSubzonePlantOpen"
      :title="subzonePlantData?.subzoneName || 'Pflanzenkontext'"
      width="lg"
      @close="closeSubzonePlant"
    >
      <SubzonePlantPanel
        v-if="subzonePlantData"
        :subzone-id="subzonePlantData.subzoneId"
        :subzone-name="subzonePlantData.subzoneName"
      />
    </SlideOver>

    <!-- Config Wizard Modal (Sensor + Actuator unified, S8) -->
    <ConfigWizardModal
      v-if="wizardPayload"
      :open="isWizardOpen"
      :esp-id="wizardPayload.espId"
      :gpio="wizardPayload.gpio"
      :sensor-type="wizardPayload.sensorType"
      :unit="wizardPayload.unit"
      :config-id="wizardPayload.configId"
      :actuator-type="wizardPayload.actuatorType"
      @update:open="isWizardOpen = $event"
      @close="closeWizard"
      @deleted="closeWizard(); espStore.fetchDevice(wizardPayload!.espId)"
      @saved="espStore.fetchDevice(wizardPayload!.espId)"
      @open-esp-settings="handleOpenEspSettingsFromConfig"
    />

    <!-- ESP Config SlideOver -->
    <SlideOver
      :open="showEspConfig"
      :title="configEspDevice?.name || 'ESP'"
      width="lg"
      @close="showEspConfig = false"
    >
      <ESPConfigPanel
        v-if="configEspDevice"
        :device="configEspDevice"
      />
    </SlideOver>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════════════════════════════
   HARDWARE VIEW — Two-level zone accordion + orbital detail
   ═══════════════════════════════════════════════════════════════════════════ */

.hardware-view {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding-bottom: 120px;
  position: relative;
  background-color: var(--color-bg-level-1);
}

/* ═══ Hardware Content with optional Side-Panel (Block 7d) ═══ */

.hardware-content {
  display: flex;
  flex-direction: column;
  flex: 1;
}

.hardware-content--has-side {
  display: grid;
  grid-template-columns: 1fr 300px;
  gap: var(--space-4);
}

.hardware-side-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  overflow-y: auto;
  max-height: calc(100vh - 120px);
  position: sticky;
  top: 0;
}

@media (max-width: 768px) {
  .hardware-content--has-side {
    grid-template-columns: 1fr;
  }
  .hardware-side-panel {
    position: static;
    max-height: none;
  }
}

.hardware-main-layout {
  display: flex;
  gap: var(--space-3);
  min-height: 400px;
}

.zoom-container {
  position: relative;
  flex: 1;
  min-width: 0;
}

.zoom-level--active {
  display: block;
  animation: fade-in 0.25s var(--ease-out) both;
}

@keyframes fade-in {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Zone Accordion List — vertical stack */
.hardware-camera-panel {
  margin-bottom: var(--space-4);
  max-width: 400px;
}

.zone-accordion-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.no-zones-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-8);
  text-align: center;
  color: var(--color-text-muted);
  background: var(--glass-bg);
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-md);
}

/* Cross-ESP Toggle */
.cross-esp-toggle {
  position: fixed;
  bottom: var(--space-6);
  right: var(--space-6);
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  background-color: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-full);
  color: var(--color-text-muted);
  font-size: var(--text-xs);
  font-weight: 500;
  cursor: pointer;
  z-index: var(--z-fixed);
  box-shadow: var(--elevation-raised);
  transition: all var(--transition-base);
}

.cross-esp-toggle:hover {
  border-color: var(--color-accent-bright);
  color: var(--color-text-primary);
}

.cross-esp-toggle--active {
  background: var(--gradient-iridescent);
  border-color: transparent;
  color: white;
}

/* B1.3: Zone Create Button — primary/accent statt grau, damit klar sichtbar. */
.zone-create-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  width: 100%;
  min-height: 48px;
  padding: var(--space-3);
  background: var(--gradient-iridescent);
  border: 1px solid color-mix(in srgb, var(--color-accent) 60%, transparent);
  border-radius: var(--radius-lg);
  color: var(--color-text-inverse);
  font-size: var(--text-base);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  box-shadow: 0 2px 12px color-mix(in srgb, var(--color-accent) 25%, transparent);
}

.zone-create-btn:hover:not(:disabled) {
  filter: brightness(1.1);
  box-shadow: 0 4px 18px color-mix(in srgb, var(--color-accent) 40%, transparent);
  transform: translateY(-1px);
}

.zone-create-btn:focus-visible {
  outline: 2px solid var(--color-accent-bright, var(--color-iridescent-2));
  outline-offset: 2px;
}

.zone-create-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.zone-create-btn__icon {
  width: 16px;
  height: 16px;
}

/* Zone Create Form */
.zone-create-form {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
}

.zone-create-form__input {
  flex: 1;
  min-width: 120px;
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  outline: none;
  transition: border-color var(--transition-fast);
}

.zone-create-form__input:focus {
  border-color: var(--color-iridescent-1);
}

.zone-create-form__select {
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  outline: none;
  min-width: 150px;
  cursor: pointer;
}

.zone-create-form__select:focus {
  border-color: var(--color-iridescent-1);
}

.zone-create-form__btn {
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: all var(--transition-fast);
}

.zone-create-form__btn:hover {
  color: var(--color-text-primary);
  border-color: var(--glass-border-hover);
}

.zone-create-form__btn--primary {
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  border-color: color-mix(in srgb, var(--color-accent) 30%, transparent);
  color: var(--color-accent-bright);
}

.zone-create-form__btn--primary:hover:not(:disabled) {
  background: color-mix(in srgb, var(--color-accent) 25%, transparent);
}

.zone-create-form__btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* B1.1: Unassigned Banner (prominent oben, mit visuellem Bezug zur folgenden Zonen-Liste). */
.unassigned-banner {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: color-mix(in srgb, var(--color-warning) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-warning) 35%, transparent);
  border-left: 4px solid var(--color-warning);
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: 1.4;
  position: relative;
}

/* Pfeil-/Pointer-Andeutung nach unten als visuelle Verbindung zu Zone-Liste. */
.unassigned-banner::after {
  content: '';
  position: absolute;
  bottom: -7px;
  left: var(--space-6);
  width: 12px;
  height: 12px;
  background: color-mix(in srgb, var(--color-warning) 10%, transparent);
  border-right: 1px solid color-mix(in srgb, var(--color-warning) 35%, transparent);
  border-bottom: 1px solid color-mix(in srgb, var(--color-warning) 35%, transparent);
  transform: rotate(45deg);
}

.unassigned-banner__icon {
  width: 18px;
  height: 18px;
  color: var(--color-warning);
  flex-shrink: 0;
}

.unassigned-banner__body {
  flex: 1;
  min-width: 0;
}

.unassigned-banner__count {
  color: var(--color-warning);
  font-weight: 700;
}

/* ── Unassigned Section ─────────────────────────────────────────────────── */
.unassigned-section {
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning-border);
  border-left: 4px solid var(--color-warning);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.unassigned-section--drop-target {
  border-color: var(--color-warning);
  box-shadow: 0 0 0 1px var(--color-warning), inset 0 0 12px var(--color-warning-glow);
}

.unassigned-section__accordion {
  border-bottom: none;
}

.unassigned-section__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-3) var(--space-3);
  cursor: pointer;
  transition: background-color var(--transition-fast);
}

.unassigned-section__header:hover {
  background: var(--color-warning-bg-hover);
}

.unassigned-section__icon {
  width: 16px;
  height: 16px;
  color: var(--color-warning);
  flex-shrink: 0;
}

.unassigned-section__title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-warning);
  margin: 0;
}

.unassigned-section__context {
  margin-left: auto;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.unassigned-section__count {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 var(--space-1);
  font-size: var(--text-xs);
  font-weight: 700;
  color: var(--color-bg-primary);
  background: var(--color-warning);
  border-radius: var(--radius-full);
}

.unassigned-section__empty-hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-style: italic;
}

.unassigned-section__chevron {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  color: var(--color-text-muted);
  transition: transform var(--transition-fast);
}

.unassigned-section__chevron--collapsed {
  transform: rotate(-90deg);
}

.unassigned-section__devices {
  gap: 8px;
  min-height: 32px;
  padding-top: var(--space-1);
}

.unassigned-section__device-wrapper {
  /* Must be a real box element — display: contents breaks SortableJS drag visuals */
}

.unassigned-section__all-assigned {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-4);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

.unassigned-section__all-assigned-icon {
  width: 16px;
  height: 16px;
  opacity: 0.5;
}

/* ── Empty State (Iridescent CTA) ─────────────────────────────────────── */
.hardware-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-12) var(--space-6);
  text-align: center;
}

.hardware-empty__icon-wrapper {
  width: 4rem;
  height: 4rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-full);
  background-color: var(--color-bg-tertiary);
  margin-bottom: var(--space-4);
  color: var(--color-iridescent-3);
  animation: pulse-glow 3s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

.hardware-empty__icon {
  width: 2rem;
  height: 2rem;
}

.hardware-empty__title {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: var(--space-2);
}

.hardware-empty__desc {
  font-size: var(--text-base);
  color: var(--color-text-muted);
  max-width: 20rem;
  margin-bottom: var(--space-6);
}

.hardware-empty__btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-6);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text-inverse);
  background: var(--gradient-iridescent);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  box-shadow: 0 0 20px var(--color-iridescent-glow);
  transition: filter var(--transition-fast), box-shadow var(--transition-fast);
}

.hardware-empty__btn:hover {
  filter: brightness(1.15);
  box-shadow: 0 0 28px var(--color-iridescent-glow-hover);
}

.hardware-empty__btn-icon {
  width: 16px;
  height: 16px;
}

.hardware-empty__link {
  margin-top: var(--space-3);
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  background: none;
  border: none;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
  transition: color var(--transition-fast);
}

.hardware-empty__link:hover {
  color: var(--color-accent-bright);
}

/* ═══ Archived zones section ═══ */
.archived-zones-section {
  margin-top: var(--space-4);
  opacity: 0.7;
}

.archived-zones-section :deep(.accordion__panel) {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

@media (max-width: 640px) {
  .hardware-view { padding-bottom: 80px; }
  .zone-accordion-list { gap: var(--space-3); }
  .hardware-main-layout { flex-direction: column; }
  .zone-create-form { flex-wrap: wrap; }
}

/* ─── Level 1: always visible, dims behind overlay ─── */
.zoom-level--l1 {
  display: block;
  transition: opacity 0.3s ease, filter 0.3s ease;
}

.zoom-level--l1--dimmed {
  opacity: 0.25;
  filter: blur(3px);
  pointer-events: none;
  user-select: none;
}

/* ─── Orbital Overlay (L2) — fixed over L1 ─── */
.orbital-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal-backdrop);
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
  overflow-y: auto;
}

.orbital-overlay__panel {
  position: relative;
  width: 100%;
  max-width: min(960px, 100%);
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border-l2);
  border-radius: var(--radius-lg);
  box-shadow: var(--elevation-floating), 0 0 80px rgba(96, 165, 250, 0.08);
  overflow-y: auto;
  max-height: 92vh;
}

/* FLIP Fly-in animation on the panel */
.zoom-level--l2 {
  animation: orbital-fly-in 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
}

@keyframes orbital-fly-in {
  from {
    opacity: 0;
    transform: translate(var(--flip-start-x, 0px), var(--flip-start-y, 0px)) scale(var(--flip-start-scale, 0.85));
  }
  to {
    opacity: 1;
    transform: translate(0, 0) scale(1);
  }
}

/* Backdrop fade transition */
.orbital-overlay-enter-active {
  transition: opacity 0.25s ease;
}
.orbital-overlay-leave-active {
  transition: opacity 0.2s ease;
}
.orbital-overlay-enter-from,
.orbital-overlay-leave-to {
  opacity: 0;
}

</style>

<style>
/* palette-slide: Component Palette top-drawer enter/leave animation (S7) */
.palette-slide-enter-active {
  animation: palette-slide-down 0.4s cubic-bezier(0.22, 1, 0.36, 1) both;
}
.palette-slide-leave-active {
  animation: palette-slide-up 0.3s ease-in both;
}
@keyframes palette-slide-down {
  from { opacity: 0; transform: translateX(-50%) translateY(-120%); }
  to   { opacity: 1; transform: translateX(-50%) translateY(0); }
}
@keyframes palette-slide-up {
  from { opacity: 1; transform: translateX(-50%) translateY(0); }
  to   { opacity: 0; transform: translateX(-50%) translateY(-120%); }
}

.orbital-device-not-found {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 400px;
}

.hardware-pending-config-stack {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
  max-width: min(100%, 720px);
  margin-inline: auto;
}
</style>
