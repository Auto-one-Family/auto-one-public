/**
 * Inventory Store — Component Inventory State Management
 *
 * Manages filter state, pagination, column visibility, and device selection
 * for the flat inventory table view. Data comes from espStore (no separate API).
 */

import { ref, computed, watchEffect } from 'vue'
import { defineStore } from 'pinia'
import { useEspStore } from '@/stores/esp'
import { useZoneGrouping } from '@/composables/useZoneGrouping'
import { getSensorUnit, getSensorLabel, getSensorDisplayName } from '@/utils/sensorDefaults'
import { getActuatorDisplayName } from '@/utils/actuatorDefaults'
import type { DeviceScope } from '@/types'
import { getESPStatus } from '@/composables/useESPStatus'
import { isMaintenanceOverdue, getNextMaintenanceDate, parseDeviceMetadata } from '@/types/device-metadata'
import type { DeviceMetadata } from '@/types/device-metadata'

// =============================================================================
// Types
// =============================================================================

export interface ComponentItem {
  id: string
  name: string
  type: 'sensor' | 'actuator'
  deviceType: string
  zone: string
  zoneId: string | null
  espId: string
  gpio: number
  currentValue: string
  unit: string
  quality: string
  status: 'online' | 'offline'
  lastSeen: string | null
  isMock: boolean
  metadata: DeviceMetadata | null
  maintenanceOverdue: boolean
  nextMaintenance: string | null
  scope: DeviceScope | null
  activeZone: string | null
}

export type SortKey = 'name' | 'type' | 'deviceType' | 'zone' | 'currentValue' | 'status' | 'lastSeen' | 'scope' | 'activeZone'
export type SortDirection = 'asc' | 'desc'
export type TypeFilter = 'all' | 'sensor' | 'actuator'
export type StatusFilter = 'all' | 'online' | 'offline' | 'maintenance_due'
export type ScopeFilter = 'all' | 'zone_local' | 'multi_zone' | 'mobile'

export interface ColumnDef {
  key: string
  label: string
  sortable: boolean
  defaultVisible: boolean
}

export const INVENTORY_COLUMNS: ColumnDef[] = [
  { key: 'status', label: 'Status', sortable: false, defaultVisible: true },
  { key: 'name', label: 'Name', sortable: true, defaultVisible: true },
  { key: 'type', label: 'Typ', sortable: true, defaultVisible: true },
  { key: 'deviceType', label: 'Gerätetyp', sortable: true, defaultVisible: true },
  { key: 'zone', label: 'Zone', sortable: true, defaultVisible: true },
  { key: 'currentValue', label: 'Aktueller Wert', sortable: true, defaultVisible: true },
  { key: 'espId', label: 'ESP ID', sortable: true, defaultVisible: false },
  { key: 'lastSeen', label: 'Zuletzt gesehen', sortable: true, defaultVisible: false },
  { key: 'nextMaintenance', label: 'Nächste Wartung', sortable: true, defaultVisible: false },
  { key: 'scope', label: 'Scope', sortable: true, defaultVisible: false },
  { key: 'activeZone', label: 'Aktive Zone', sortable: true, defaultVisible: false },
]

const DEFAULT_VISIBLE = INVENTORY_COLUMNS.filter(c => c.defaultVisible).map(c => c.key)

// =============================================================================
// Store
// =============================================================================

export const useInventoryStore = defineStore('inventory', () => {
  const espStore = useEspStore()
  const { allSensors, allActuators } = useZoneGrouping()

  // ── Filter State ──
  const searchQuery = ref('')
  const zoneFilter = ref<string[]>([])
  const typeFilter = ref<TypeFilter>('all')
  const statusFilter = ref<StatusFilter>('all')
  const scopeFilter = ref<ScopeFilter>('all')

  // ── Sort State ──
  const sortKey = ref<SortKey>('name')
  const sortDirection = ref<SortDirection>('asc')

  // ── Pagination ──
  const pageSize = ref(
    parseInt(localStorage.getItem('ao-inventory-pagesize') || '25', 10)
  )
  const currentPage = ref(1)

  // ── Column Visibility ──
  const visibleColumns = ref<string[]>(
    JSON.parse(localStorage.getItem('ao-inventory-columns') || 'null') ?? DEFAULT_VISIBLE
  )

  // ── Detail Panel ──
  const selectedDeviceId = ref<string | null>(null)
  const isDetailOpen = ref(false)

  // ── Persist preferences ──
  watchEffect(() => {
    localStorage.setItem('ao-inventory-columns', JSON.stringify(visibleColumns.value))
    localStorage.setItem('ao-inventory-pagesize', String(pageSize.value))
  })

  // ── All Components (unified sensors + actuators) ──
  const allComponents = computed<ComponentItem[]>(() => {
    // Pre-compute duplicate detection for same sensor_type on same GPIO per ESP
    const sensorCounts = new Map<string, number>()
    const sensorIndices = new Map<string, number>()
    for (const s of allSensors.value) {
      const groupKey = `${s.esp_id}_${s.gpio}_${s.sensor_type}`
      sensorCounts.set(groupKey, (sensorCounts.get(groupKey) || 0) + 1)
    }

    const sensors: ComponentItem[] = allSensors.value.map(s => {
      const device = espStore.devices.find(d => espStore.getDeviceId(d) === s.esp_id)
      const espStatus = device ? getESPStatus(device) : null
      const rawMeta = device?.sensors
        ? (device.sensors as Record<string, unknown>[]).find(
            (sen: Record<string, unknown>) => sen.gpio === s.gpio && (sen as Record<string, unknown>).sensor_type === s.sensor_type
          )
        : null
      const metadata = rawMeta && (rawMeta as Record<string, unknown>).sensor_metadata
        ? parseDeviceMetadata((rawMeta as Record<string, unknown>).sensor_metadata as Record<string, unknown>)
        : null

      // Disambiguate sensors with same type on same GPIO (e.g., 2x DS18B20 on OneWire bus)
      const groupKey = `${s.esp_id}_${s.gpio}_${s.sensor_type}`
      const isDuplicate = (sensorCounts.get(groupKey) || 0) > 1
      let displayName = getSensorDisplayName({ sensor_type: s.sensor_type, name: s.name }) || `${getSensorLabel(s.sensor_type)} (GPIO ${s.gpio})`
      if (isDuplicate && !s.name) {
        const idx = (sensorIndices.get(groupKey) || 0) + 1
        sensorIndices.set(groupKey, idx)
        displayName = `${getSensorLabel(s.sensor_type)} #${idx}`
      }

      return {
        id: s.config_id || `${s.esp_id}_gpio${s.gpio}_${s.sensor_type}`,
        name: displayName,
        type: 'sensor' as const,
        deviceType: s.sensor_type,
        zone: s.zone_name || 'Nicht zugewiesen',
        zoneId: s.zone_id,
        espId: s.esp_id,
        gpio: s.gpio,
        currentValue: s.raw_value != null ? String(s.raw_value) : '—',
        unit: (s.unit && s.unit !== 'raw') ? s.unit : (getSensorUnit(s.sensor_type) !== 'raw' ? getSensorUnit(s.sensor_type) : ''),
        quality: s.quality || 'unknown',
        status: (espStatus === 'online' || espStatus === 'stale') ? 'online' : 'offline',
        lastSeen: s.last_read ?? null,
        isMock: s.esp_id?.startsWith('ESP_MOCK_') || s.esp_id?.startsWith('MOCK_') || false,
        metadata,
        maintenanceOverdue: metadata ? isMaintenanceOverdue(metadata) : false,
        nextMaintenance: metadata ? (getNextMaintenanceDate(metadata)?.toISOString().slice(0, 10) ?? null) : null,
        scope: (s as unknown as Record<string, unknown>).device_scope as DeviceScope | null ?? null,
        activeZone: null,
      }
    })

    const actuators: ComponentItem[] = allActuators.value.map(a => {
      const device = espStore.devices.find(d => espStore.getDeviceId(d) === a.esp_id)
      const espStatus = device ? getESPStatus(device) : null
      const rawMeta = device?.actuators
        ? (device.actuators as Record<string, unknown>[]).find(
            (act: Record<string, unknown>) => act.gpio === a.gpio
          )
        : null
      const metadata = rawMeta && (rawMeta as Record<string, unknown>).actuator_metadata
        ? parseDeviceMetadata((rawMeta as Record<string, unknown>).actuator_metadata as Record<string, unknown>)
        : null

      const stateLabel = a.emergency_stopped ? 'NOT-STOPP' : a.state ? 'AN' : 'AUS'

      return {
        id: `${a.esp_id}_gpio${a.gpio}`,
        name: getActuatorDisplayName({ actuator_type: a.actuator_type, name: a.name }),
        type: 'actuator' as const,
        deviceType: a.actuator_type,
        zone: a.zone_name || 'Nicht zugewiesen',
        zoneId: a.zone_id,
        espId: a.esp_id,
        gpio: a.gpio,
        currentValue: stateLabel,
        unit: '',
        quality: a.emergency_stopped ? 'error' : 'good',
        status: (espStatus === 'online' || espStatus === 'stale') ? 'online' : 'offline',
        lastSeen: null,
        isMock: a.esp_id?.startsWith('ESP_MOCK_') || a.esp_id?.startsWith('MOCK_') || false,
        metadata,
        maintenanceOverdue: metadata ? isMaintenanceOverdue(metadata) : false,
        nextMaintenance: metadata ? (getNextMaintenanceDate(metadata)?.toISOString().slice(0, 10) ?? null) : null,
        scope: (a as unknown as Record<string, unknown>).device_scope as DeviceScope | null ?? null,
        activeZone: null,
      }
    })

    return [...sensors, ...actuators]
  })

  // ── Has non-local scope (show scope filter only when relevant) ──
  const hasNonLocalScope = computed(() =>
    allComponents.value.some(c => c.scope && c.scope !== 'zone_local'),
  )

  // ── Available Zones (for filter dropdown) ──
  const availableZones = computed(() => {
    const zones = new Set<string>()
    allComponents.value.forEach(c => {
      if (c.zoneId) zones.add(c.zone)
    })
    return Array.from(zones).sort()
  })

  // ── Filtered Components ──
  const filteredComponents = computed(() => {
    return allComponents.value.filter(c => {
      // Type filter
      if (typeFilter.value !== 'all' && c.type !== typeFilter.value) return false

      // Zone filter
      if (zoneFilter.value.length > 0 && !zoneFilter.value.includes(c.zone)) return false

      // Status filter
      if (statusFilter.value === 'online' && c.status !== 'online') return false
      if (statusFilter.value === 'offline' && c.status !== 'offline') return false
      if (statusFilter.value === 'maintenance_due' && !c.maintenanceOverdue) return false

      // Scope filter
      if (scopeFilter.value !== 'all' && c.scope !== scopeFilter.value) return false

      // Search query (debounced externally)
      if (searchQuery.value) {
        const q = searchQuery.value.toLowerCase()
        const searchFields = [c.name, c.deviceType, c.zone, c.espId, c.metadata?.manufacturer, c.metadata?.model].filter(Boolean)
        if (!searchFields.some(f => f!.toLowerCase().includes(q))) return false
      }

      return true
    })
  })

  // ── Sorted Components ──
  const sortedComponents = computed(() => {
    const items = [...filteredComponents.value]
    items.sort((a, b) => {
      let valA: string | number = ''
      let valB: string | number = ''

      switch (sortKey.value) {
        case 'name': valA = a.name.toLowerCase(); valB = b.name.toLowerCase(); break
        case 'type': valA = a.type; valB = b.type; break
        case 'deviceType': valA = a.deviceType; valB = b.deviceType; break
        case 'zone': valA = a.zone; valB = b.zone; break
        case 'status': valA = a.status; valB = b.status; break
        case 'currentValue': valA = a.currentValue; valB = b.currentValue; break
        case 'lastSeen': valA = a.lastSeen ?? ''; valB = b.lastSeen ?? ''; break
        case 'scope': valA = a.scope ?? ''; valB = b.scope ?? ''; break
        case 'activeZone': valA = a.activeZone ?? ''; valB = b.activeZone ?? ''; break
      }

      if (valA < valB) return sortDirection.value === 'asc' ? -1 : 1
      if (valA > valB) return sortDirection.value === 'asc' ? 1 : -1
      return 0
    })
    return items
  })

  // ── Paginated Components ──
  const paginatedComponents = computed(() => {
    const start = (currentPage.value - 1) * pageSize.value
    return sortedComponents.value.slice(start, start + pageSize.value)
  })

  const totalPages = computed(() => {
    return Math.max(1, Math.ceil(sortedComponents.value.length / pageSize.value))
  })

  const totalCount = computed(() => sortedComponents.value.length)

  // ── Actions ──

  function toggleSort(key: SortKey) {
    if (sortKey.value === key) {
      sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
    } else {
      sortKey.value = key
      sortDirection.value = 'asc'
    }
    currentPage.value = 1
  }

  function setPage(page: number) {
    currentPage.value = Math.max(1, Math.min(page, totalPages.value))
  }

  function toggleColumn(key: string) {
    const idx = visibleColumns.value.indexOf(key)
    if (idx === -1) {
      visibleColumns.value = [...visibleColumns.value, key]
    } else {
      visibleColumns.value = visibleColumns.value.filter(c => c !== key)
    }
  }

  function openDetail(deviceId: string) {
    selectedDeviceId.value = deviceId
    isDetailOpen.value = true
  }

  function closeDetail() {
    isDetailOpen.value = false
    setTimeout(() => { selectedDeviceId.value = null }, 300)
  }

  function resetFilters() {
    searchQuery.value = ''
    zoneFilter.value = []
    typeFilter.value = 'all'
    statusFilter.value = 'all'
    scopeFilter.value = 'all'
    currentPage.value = 1
  }

  return {
    // Filter State
    searchQuery,
    zoneFilter,
    typeFilter,
    statusFilter,
    scopeFilter,

    // Sort State
    sortKey,
    sortDirection,

    // Pagination
    pageSize,
    currentPage,
    totalPages,
    totalCount,

    // Column Visibility
    visibleColumns,

    // Detail Panel
    selectedDeviceId,
    isDetailOpen,

    // Computed Data
    allComponents,
    availableZones,
    hasNonLocalScope,
    filteredComponents,
    sortedComponents,
    paginatedComponents,

    // Actions
    toggleSort,
    setPage,
    toggleColumn,
    openDetail,
    closeDetail,
    resetFilters,
  }
})
