<script setup lang="ts">
defineOptions({ name: 'CustomDashboardView' })

/**
 * CustomDashboardView — Dashboard Builder with GridStack.js
 *
 * Route: /editor, /editor/:dashboardId
 *
 * Features:
 * - GridStack.js 12-column layout grid (immer Bearbeiten — kein separater Ansichtsmodus)
 * - Widget catalog sidebar (per +-Button ein-/ausblendbar)
 * - Widget configuration inline
 * - Layout save/load from localStorage
 * - Multiple named layouts
 */

import { ref, watch, onMounted, onUnmounted, onActivated, onDeactivated, nextTick, computed } from 'vue'
import { onClickOutside } from '@vueuse/core'
import { useRoute, onBeforeRouteLeave } from 'vue-router'
import { GridStack, type GridItemHTMLElement, type GridStackNode } from 'gridstack'
import 'gridstack/dist/gridstack.min.css'
import {
  LayoutGrid, Plus, Trash2, Download, Upload,
  ChevronDown, AlertTriangle, Crosshair,
} from 'lucide-vue-next'
import { useDashboardStore, type WidgetType } from '@/shared/stores/dashboard.store'
import { useUiStore } from '@/shared/stores'
import { useDragStateStore } from '@/shared/stores/dragState.store'
import { useToast } from '@/composables/useToast'
import { isB2CatalogWidgetType, useDashboardWidgets } from '@/composables/useDashboardWidgets'
import { useCrosshairSync } from '@/composables/useCrosshairSync'
import { useEspStore } from '@/stores/esp'
import { useZoneStore } from '@/shared/stores/zone.store'
import { getSensorDisplayName, formatSensorType } from '@/utils/sensorDefaults'
import { parseSensorId } from '@/composables/useSensorId'
import { findFirstFreePosition } from '@/utils/gridLayout'
import ViewTabBar from '@/components/common/ViewTabBar.vue'
import WidgetConfigPanel from '@/components/dashboard-widgets/WidgetConfigPanel.vue'
import InlineDashboardPanel from '@/components/dashboard/InlineDashboardPanel.vue'
import {
  ZONE_TILE_ALLOWED_WIDGET_TYPES,
  ZONE_TILE_MAX_WIDGETS,
} from '@/utils/zoneTileWidgets'

const route = useRoute()
const dashStore = useDashboardStore()
const uiStore = useUiStore()
const espStore = useEspStore()
const zoneStore = useZoneStore()
const dragStore = useDragStateStore()
const toast = useToast()

// Widget Config Panel state (declared early — referenced by composable callbacks)
const configPanelOpen = ref(false)
const configWidgetId = ref('')
const configWidgetType = ref('')

// Zone ID from current layout scope (PA-02c: zone-scoped sensor filtering)
const layoutZoneId = computed(() => dashStore.activeLayout?.zoneId)

// AUT-912: dashboard-level crosshair sync — group id = active layout id.
const { isActive: isCrosshairSyncActive, toggle: toggleCrosshairSyncGroup } = useCrosshairSync()
const crosshairSyncGroupId = computed(() => dashStore.activeLayoutId || undefined)
const isCrosshairSyncOn = computed(() => isCrosshairSyncActive(crosshairSyncGroupId.value))
function toggleCrosshairSync() {
  if (crosshairSyncGroupId.value) toggleCrosshairSyncGroup(crosshairSyncGroupId.value)
}

// Shared widget rendering via composable
const {
  WIDGET_TYPE_META: widgetTypes,
  WIDGET_DEFAULT_CONFIGS,
  createWidgetElement,
  mountWidgetToElement: mountWidgetComponent,
  unmountWidgetFromElement,
  cleanupAllWidgets,
} = useDashboardWidgets({
  showConfigButton: true,
  zoneId: layoutZoneId,
  syncGroupId: crosshairSyncGroupId,
  onConfigClick: (widgetId, widgetType) => {
    configWidgetId.value = widgetId
    configWidgetType.value = widgetType
    configPanelOpen.value = true
  },
  onRemoveClick: (widgetId) => {
    confirmRemoveWidget(widgetId)
  },
  onConfigUpdate: (widgetId, newConfig) => {
    const existing = widgetConfigs.value.get(widgetId) || {}
    const merged = { ...existing, ...newConfig }
    widgetConfigs.value.set(widgetId, merged)
    const widgetEl = document.querySelector(`[data-widget-id="${widgetId}"]`)
    const type = widgetEl?.getAttribute('data-type')
    if (type) updateWidgetTitleInDom(widgetId, type, merged)
    autoSave()
  },
})

/** Confirm and remove a widget from the grid via X-Button / Config-Panel */
async function confirmRemoveWidget(widgetId: string) {
  const confirmed = await uiStore.confirm({
    title: 'Widget entfernen',
    message: 'Dieses Widget wird aus dem Dashboard entfernt.',
    confirmText: 'Entfernen',
    variant: 'danger',
  })
  if (!confirmed) return
  const el = gridContainer.value?.querySelector(`[gs-id="${widgetId}"]`) as HTMLElement | null
  if (el && grid) {
    grid.removeWidget(el)
    // grid.on('removed') triggers autoSave automatically
  }
}

/** Sensor-Kachel: Entfernen aus dem Config-Panel (kein Delete-Icon auf der Kachel) */
async function handleConfigPanelRemove(): Promise<void> {
  const widgetId = configWidgetId.value
  if (!widgetId) return
  configPanelOpen.value = false
  await confirmRemoveWidget(widgetId)
}

// GridStack instance
let grid: GridStack | null = null
const gridContainer = ref<HTMLElement | null>(null)

// UI State
const showCatalog = ref(true)
const showLayoutDropdown = ref(false)
const newLayoutName = ref('')
const layoutSelectorRef = ref<HTMLElement | null>(null)
// Tracks completion of the async zone load for dropdown loading feedback
const zonesLoaded = ref(false)

// Guard: prevents autoSave during loadWidgetsToGrid (race condition with grid.on('removed'))
let isLoadingWidgets = false

/** True when the stored title is the widget meta label or unset — eligible for auto-enrichment. */
function isGenericWidgetTitle(title: string | undefined, defaultLabel: string): boolean {
  if (!title) return true
  return title === defaultLabel
}

/** Resolve ESP display name + human sensor label from a sensorId string. */
function resolveSensorMeta(sensorId: string): { espName: string; sensorLabel: string } | null {
  const { espId, gpio, sensorType } = parseSensorId(sensorId)
  if (!espId || gpio == null) return null
  const device = espStore.devices.find(d => espStore.getDeviceId(d) === espId)
  const espName = device?.name?.trim() || espId
  const sensor = device
    ? ((device.sensors as { gpio: number; sensor_type?: string; name?: string | null }[]) || []).find(
        s => s.gpio === gpio && (!sensorType || s.sensor_type === sensorType)
      )
    : null
  const sensorLabel = sensor
    ? getSensorDisplayName({ sensor_type: sensor.sensor_type || sensorType || '', name: sensor.name })
    : (sensorType ? formatSensorType(sensorType) : '')
  if (!sensorLabel) return { espName, sensorLabel: espName }
  return { espName, sensorLabel }
}

/** Compute display title for widget header. For line-chart with sensorId, appends sensor name when title is default. */
function getWidgetDisplayTitle(type: string, config: Record<string, any> | undefined): string {
  const widgetDef = widgetTypes.find(t => t.type === type)
  const defaultLabel = widgetDef?.label || type
  const base = config?.title || defaultLabel

  if (type === 'sensor-tile' && config?.sensorId && isGenericWidgetTitle(config?.title, defaultLabel)) {
    const meta = resolveSensorMeta(config.sensorId)
    if (meta) return `${meta.espName} · ${meta.sensorLabel}`
  }

  if (type === 'multi-sensor' && isGenericWidgetTitle(config?.title, defaultLabel)) {
    const sources = typeof config?.dataSources === 'string'
      ? config.dataSources.split(',').map((s: string) => s.trim()).filter(Boolean)
      : []
    if (sources.length >= 2) {
      const labels = sources
        .slice(0, 2)
        .map((id: string) => resolveSensorMeta(id)?.sensorLabel)
        .filter((label): label is string => Boolean(label))
      if (labels.length >= 2) return `${labels[0]} vs. ${labels[1]}`
      if (labels.length === 1) return labels[0]
      return `${sources.length} Sensoren vergleichen`
    }
  }

  if (type === 'line-chart' && config?.sensorId) {
    const { espId, gpio, sensorType } = parseSensorId(config.sensorId)
    const device = espId ? espStore.devices.find(d => espStore.getDeviceId(d) === espId) : null
    const sensor = device && gpio !== null
      ? ((device.sensors as { gpio: number; sensor_type?: string; name?: string | null }[]) || []).find(
          s => s.gpio === gpio && (!sensorType || s.sensor_type === sensorType)
        )
      : null
    const sensorLabel = sensor
      ? getSensorDisplayName({ sensor_type: sensor.sensor_type || sensorType || '', name: sensor.name })
      : (sensorType ? formatSensorType(sensorType) : '')
    if (sensorLabel && base === defaultLabel) {
      return `${base} — ${sensorLabel}`
    }
  }
  return base
}

/** Update widget header title in DOM (for config updates from widget or panel) */
function updateWidgetTitleInDom(widgetId: string, type: string, config: Record<string, any>) {
  const widgetEl = document.querySelector(`[data-widget-id="${widgetId}"]`)
  if (!widgetEl) return
  const titleEl = widgetEl.querySelector('.dashboard-widget__title')
  if (titleEl) titleEl.textContent = getWidgetDisplayTitle(type, config)
}

// Close layout dropdown on outside click
onClickOutside(layoutSelectorRef, () => {
  showLayoutDropdown.value = false
})

const activeLayout = computed(() => dashStore.activeLayout)
const isZoneTileLayout = computed(() => activeLayout.value?.scope === 'zone-tile')

const zoneTileCompatibleWidgetsCount = computed(() =>
  activeLayout.value?.widgets.filter((w) => ZONE_TILE_ALLOWED_WIDGET_TYPES.has(w.type)).length ?? 0,
)

const zoneTileIncompatibleWidgetsCount = computed(() =>
  Math.max(0, (activeLayout.value?.widgets.length ?? 0) - zoneTileCompatibleWidgetsCount.value),
)

const zoneTileOverflowWidgetsCount = computed(() =>
  Math.max(0, zoneTileCompatibleWidgetsCount.value - ZONE_TILE_MAX_WIDGETS),
)

const zoneTilePreviewState = computed<'ready' | 'empty' | 'incompatible'>(() => {
  if (Math.min(zoneTileCompatibleWidgetsCount.value, ZONE_TILE_MAX_WIDGETS) > 0) return 'ready'
  if ((activeLayout.value?.widgets.length ?? 0) === 0) return 'empty'
  return 'incompatible'
})


const groupedWidgets = computed(() => {
  const groups: Record<string, typeof widgetTypes> = {}
  for (const w of widgetTypes) {
    if (!isB2CatalogWidgetType(w.type)) continue
    if (!groups[w.category]) groups[w.category] = []
    groups[w.category].push(w)
  }
  return groups
})


// =============================================================================
// GridStack Initialization
// =============================================================================

/**
 * Initialize GridStack on the container element.
 * Extracted into a separate function so it can be called both from onMounted
 * and from the watch on activeLayoutId (GridStack re-init after layout creation).
 */
function initGrid() {
  if (!gridContainer.value || grid) return

  grid = GridStack.init({
    column: 12,
    cellHeight: 80,
    margin: 8,
    float: true,
    animate: true,
    removable: true,
    acceptWidgets: true,
    handle: '.dashboard-widget__header',
  }, gridContainer.value)

  // Load active layout
  if (dashStore.activeLayout) {
    loadWidgetsToGrid(dashStore.activeLayout.widgets)
  }

  // Auto-save on change
  grid.on('change', () => {
    autoSave()
  })

  grid.on('removed', (_event: Event, items: GridStackNode[]) => {
    // Unmount Vue components of removed widgets to prevent memory leaks
    for (const item of items) {
      if (item.id) {
        unmountWidgetFromElement(item.id)
      }
    }
    autoSave()
  })

  // Handle external widget drops from FAB QuickWidgetPanel (HTML5 DnD)
  grid.on('dropped', (_event: Event, _previousNode: GridStackNode, newNode: GridStackNode) => {
    if (!newNode.el) return

    const payload = dragStore.dashboardWidgetPayload
    if (!payload) return

    // Remove GridStack's auto-created placeholder — reuse addWidget() for robust mounting
    grid!.removeWidget(newNode.el, true, false)
    addWidget(payload.widgetType)

    dragStore.endDrag()
  })

  grid.enableMove(true)
  grid.enableResize(true)
  grid.opts.removable = true
}

// Re-initialize GridStack when a layout is created or switched.
// When no layout exists at mount time, the grid div is hidden (v-if).
// After creating a layout, the div appears but GridStack was never initialized.
watch(() => dashStore.activeLayoutId, (newId) => {
  if (newId && !grid) {
    nextTick(() => {
      initGrid()
    })
  }
})

// Retry sync for current layout
function retrySyncCurrentLayout() {
  if (dashStore.activeLayoutId) {
    dashStore.retrySync(dashStore.activeLayoutId)
  }
}

/** Handle keyboard widget placement from FAB (Space/Enter on widget chip) */
function handleWidgetPlaceAnnounced(e: Event): void {
  const detail = (e as CustomEvent).detail
  if (detail?.type) {
    addWidget(detail.type)
  }
}

onMounted(() => {
  // Ensure ESP data is loaded for widgets
  if (espStore.devices.length === 0) {
    espStore.fetchAll()
  }

  // Ensure zone list is loaded for dropdown Zone-Tiles / Zone-Dashboards
  if (zoneStore.zoneEntities.length === 0) {
    zoneStore.fetchZoneEntities('active').finally(() => { zonesLoaded.value = true })
  } else {
    zonesLoaded.value = true
  }

  // Deep-link target from URL
  const dashboardIdFromUrl = route.params.dashboardId as string | undefined
  const layoutFromQuery = route.query.layout as string | undefined
  const deepLinkId = dashboardIdFromUrl || layoutFromQuery

  /** Try to activate a dashboard by local ID or serverId */
  function activateDeepLink(id: string): boolean {
    const layout = dashStore.getLayoutById(id)
    if (layout) {
      dashStore.activeLayoutId = layout.id
      dashStore.breadcrumb.dashboardName = layout.name
      return true
    }
    return false
  }

  // Try immediate activation from localStorage cache
  if (deepLinkId) {
    activateDeepLink(deepLinkId)
  }

  // Fetch dashboards from server (merges with localStorage cache)
  // After fetch, retry deep-link activation (server-only dashboards may not be in localStorage yet)
  dashStore.fetchLayouts().then(() => {
    if (deepLinkId) {
      const current = dashStore.activeLayout
      // Only retry if the deep-link layout is not yet active
      if (!current || (current.id !== deepLinkId && current.serverId !== deepLinkId)) {
        if (!activateDeepLink(deepLinkId)) {
          // Invalid deep-link ID: show toast and fallback to first dashboard
          toast.warning(`Dashboard "${deepLinkId}" nicht gefunden`)
          if (dashStore.layouts.length > 0) {
            dashStore.activeLayoutId = dashStore.layouts[0].id
          }
        }
        // Reload grid with newly activated layout
        nextTick(() => {
          if (grid && dashStore.activeLayout) {
            loadWidgetsToGrid(dashStore.activeLayout.widgets)
          }
        })
      }
    }
  })

  // Listen for keyboard-placed widgets from FAB
  window.addEventListener('widget-place-announced', handleWidgetPlaceAnnounced)

  nextTick(() => {
    initGrid()
  })
})

onUnmounted(() => {
  window.removeEventListener('widget-place-announced', handleWidgetPlaceAnnounced)

  // Cleanup all mounted Vue vnodes
  cleanupAllWidgets()

  if (grid) {
    grid.destroy(false)
    grid = null
  }

  // Clear breadcrumb
  dashStore.breadcrumb.dashboardName = ''

  // Best-effort flush for pending debounced syncs
  void dashStore.flushPendingSyncs('flush')
})

onBeforeRouteLeave(async () => {
  await dashStore.flushPendingSyncs('flush')
})

// keep-alive lifecycle: Preserve GridStack state across tab switches
onActivated(() => {
  // Clear stale sync errors from previous navigation
  dashStore.lastSyncError = null

  // Re-init grid if it was destroyed during deactivation
  if (!grid) {
    nextTick(() => initGrid())
  }
  // keep-alive return path: rebuild GridStack widget mounts in edit mode
  else if (dashStore.activeLayout) {
    nextTick(() => loadWidgetsToGrid(dashStore.activeLayout!.widgets))
  }
  // Restore breadcrumb
  const layout = dashStore.activeLayout
  if (layout) {
    dashStore.breadcrumb.dashboardName = layout.name
  }
})

onDeactivated(() => {
  // Clear breadcrumb while hidden (other views may set their own)
  dashStore.breadcrumb.dashboardName = ''
})

// Widget config cache (stored per widget ID)
const widgetConfigs = ref<Map<string, Record<string, any>>>(new Map())

function loadWidgetsToGrid(widgets: any[]) {
  if (!grid) return

  // Guard: prevent autoSave from firing during removeAll/addWidget cycle
  isLoadingWidgets = true

  // Cleanup existing mounted widgets
  cleanupAllWidgets()

  grid.removeAll(true)

  const mountOps: Array<() => void> = []

  for (const w of widgets) {
    const mountId = `widget-mount-${w.id}`
    if (w.config) {
      widgetConfigs.value.set(w.id, w.config)
    }
    const widgetDef = widgetTypes.find(t => t.type === w.type)
    const itemEl = grid.addWidget({
      x: w.x,
      y: w.y,
      w: w.w,
      h: w.h,
      minW: widgetDef?.minW,
      minH: widgetDef?.minH,
      id: w.id,
    })

    // Collect mount operations to run in a single nextTick
    mountOps.push(() => {
      const contentDiv = itemEl.querySelector('.grid-stack-item-content')
      contentDiv?.appendChild(createWidgetElement(w.type, getWidgetDisplayTitle(w.type, w.config), w.id, mountId))
      mountWidgetComponent(w.id, mountId, w.type, w.config || {})
    })
  }

  // Release guard AFTER all Vue mount operations complete
  nextTick(() => {
    for (const op of mountOps) op()
    isLoadingWidgets = false
  })
}

// =============================================================================
// Widget Actions
// =============================================================================

function addWidget(type: string) {
  if (!grid) {
    toast.warning('Erstelle zuerst ein Dashboard')
    return
  }

  if (
    isZoneTileLayout.value &&
    ZONE_TILE_ALLOWED_WIDGET_TYPES.has(type as WidgetType) &&
    zoneTileCompatibleWidgetsCount.value >= ZONE_TILE_MAX_WIDGETS
  ) {
    toast.info(`Zone-Tile unterstützt maximal ${ZONE_TILE_MAX_WIDGETS} Widgets.`)
    return
  }

  const widgetDef = widgetTypes.find(w => w.type === type)
  if (!widgetDef) return

  const id = `widget-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
  const mountId = `widget-mount-${id}`
  const config = { title: widgetDef.label, ...WIDGET_DEFAULT_CONFIGS[type] }
  widgetConfigs.value.set(id, config)

  // AUT-1107: When the widget has mode-specific sizes (currently sensor-tile only),
  // use the dimensions for the initial displayMode so the cell fits the content.
  // Falls back to the flat w/h/minW/minH when no matching entry exists.
  const modeKey = (config as Record<string, unknown>).displayMode as string | undefined
  const modeSize = widgetDef.modeSizes?.[modeKey ?? '']
  const effectiveW = modeSize?.w ?? widgetDef.w
  const effectiveH = modeSize?.h ?? widgetDef.h
  const effectiveMinW = modeSize?.minW ?? widgetDef.minW
  const effectiveMinH = modeSize?.minH ?? widgetDef.minH

  const currentWidgets = (dashStore.activeLayout?.widgets ?? []).map(w => ({
    x: w.x ?? 0,
    y: w.y ?? 0,
    w: w.w ?? 1,
    h: w.h ?? 1,
  }))
  const pos = findFirstFreePosition(currentWidgets, effectiveW, effectiveH)

  const itemEl = grid.addWidget({
    x: pos.x,
    y: pos.y,
    w: effectiveW,
    h: effectiveH,
    minW: effectiveMinW,
    minH: effectiveMinH,
    id,
  })

  // Inject widget DOM and mount Vue component after GridStack has created the cell
  nextTick(() => {
    const contentDiv = itemEl.querySelector('.grid-stack-item-content')
    contentDiv?.appendChild(createWidgetElement(type, getWidgetDisplayTitle(type, config), id, mountId))
    mountWidgetComponent(id, mountId, type, config)
  })

  autoSave()
}

/** Handle config update from config panel — re-mounts the Vue component with new props */
function handleConfigUpdate(newConfig: Record<string, any>) {
  const widgetId = configWidgetId.value
  if (!widgetId) return

  widgetConfigs.value.set(widgetId, newConfig)

  // Re-mount the widget component with updated config
  const mountId = `widget-mount-${widgetId}`
  unmountWidgetFromElement(widgetId)
  mountWidgetComponent(widgetId, mountId, configWidgetType.value, newConfig)

  // Update the header title (uses getWidgetDisplayTitle for line-chart + sensorId)
  updateWidgetTitleInDom(widgetId, configWidgetType.value, newConfig)

  autoSave()
}

function autoSave() {
  if (!grid || !dashStore.activeLayoutId || isLoadingWidgets) return

  const items = grid.getGridItems()
  const widgets = items.map((el: GridItemHTMLElement) => {
    const node = el.gridstackNode
    const widgetEl = el.querySelector('.dashboard-widget')
    const widgetId = widgetEl?.getAttribute('data-widget-id') || node?.id || ''
    return {
      id: widgetId,
      type: (widgetEl?.getAttribute('data-type') || 'line-chart') as WidgetType,
      x: node?.x || 0,
      y: node?.y || 0,
      w: node?.w || 3,
      h: node?.h || 2,
      config: widgetConfigs.value.get(widgetId) || {},
    }
  })

  dashStore.saveLayout(dashStore.activeLayoutId, widgets)
}

// =============================================================================
// Layout Management
// =============================================================================

function handleCreateLayout(forcedName?: string) {
  const name = (forcedName ?? newLayoutName.value).trim()
  if (!name) return

  dashStore.createLayout(name, undefined, { view: 'dashboards', placement: 'standalone' })
  newLayoutName.value = ''
  showLayoutDropdown.value = false

  // Clear grid (guard against autoSave race)
  if (grid) {
    isLoadingWidgets = true
    grid.removeAll(true)
    isLoadingWidgets = false
  }

  showCatalog.value = true
  if (grid) {
    grid.enableMove(true)
    grid.enableResize(true)
    grid.opts.removable = true
  }

  toast.success(`Dashboard "${name}" erstellt`)
}

function switchLayout(layoutId: string) {
  dashStore.activeLayoutId = layoutId
  const layout = dashStore.layouts.find(l => l.id === layoutId)
  if (layout) {
    dashStore.breadcrumb.dashboardName = layout.name
    if (grid) {
      loadWidgetsToGrid(layout.widgets)
    }
  }
  showLayoutDropdown.value = false
}

async function handleDeleteLayout() {
  if (!dashStore.activeLayoutId) return
  const name = dashStore.activeLayout?.name
  const confirmed = await uiStore.confirm({
    title: 'Dashboard löschen',
    message: `Dashboard "${name}" wirklich löschen?`,
    variant: 'danger',
    confirmText: 'Löschen',
  })
  if (!confirmed) return
  dashStore.deleteLayout(dashStore.activeLayoutId)
  if (grid) {
    isLoadingWidgets = true
    grid.removeAll(true)
    isLoadingWidgets = false
  }
  toast.info(`Dashboard "${name}" gelöscht`)
}

function handleExport() {
  if (!dashStore.activeLayoutId) return
  const json = dashStore.exportLayout(dashStore.activeLayoutId)
  if (!json) return

  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `dashboard-${dashStore.activeLayout?.name || 'export'}.json`
  a.click()
  URL.revokeObjectURL(url)
  toast.success('Dashboard exportiert')
}

function handleImport() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.json'
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    const json = await file.text()
    const layout = dashStore.importLayout(json)
    if (layout) {
      toast.success(`Dashboard "${layout.name}" importiert`)
      switchLayout(layout.id)
    } else {
      toast.error('Import fehlgeschlagen')
    }
  }
  input.click()
}

// =============================================================================
// Single Dashboard Delete (from dropdown list)
// =============================================================================

async function handleDeleteSingleLayout(layoutId: string, layoutName: string) {
  const confirmed = await uiStore.confirm({
    title: 'Dashboard löschen',
    message: `Dashboard "${layoutName}" löschen? Diese Aktion kann nicht rückgängig gemacht werden.`,
    variant: 'danger',
    confirmText: 'Löschen',
  })
  if (!confirmed) return

  const wasActive = dashStore.activeLayoutId === layoutId
  dashStore.deleteLayout(layoutId)

  if (wasActive && grid) {
    isLoadingWidgets = true
    grid.removeAll(true)
    isLoadingWidgets = false
    if (dashStore.activeLayout) {
      loadWidgetsToGrid(dashStore.activeLayout.widgets)
    }
  }

  toast.info(`Dashboard "${layoutName}" gelöscht`)
}

function handleSelectZoneTileCategory(zoneId: string) {
  const existing = dashStore.getCanonicalZoneTileLayout(zoneId)
  if (existing) {
    switchLayout(existing.id)
    return
  }
  const zone = zoneStore.activeZones.find(z => z.zone_id === zoneId)
  const layout = dashStore.createLayout(`${zone?.name ?? zoneId} — Tile`)
  dashStore.setLayoutMetadata(layout.id, { scope: 'zone-tile', zoneId })
  // Clear grid (guard against autoSave race)
  if (grid) {
    isLoadingWidgets = true
    grid.removeAll(true)
    isLoadingWidgets = false
  }
  showLayoutDropdown.value = false
  showCatalog.value = true
  toast.success(`Zone-Tile für ${zone?.name ?? zoneId} erstellt`)
}

function handleSelectZoneDashboard(zoneId: string) {
  const existing = dashStore.layouts.find(l => l.scope === 'zone' && l.zoneId === zoneId)
  if (existing) {
    switchLayout(existing.id)
    return
  }
  const zone = zoneStore.activeZones.find(z => z.zone_id === zoneId)
  const layout = dashStore.createLayout(`${zone?.name ?? zoneId} — Dashboard`)
  dashStore.setLayoutMetadata(layout.id, {
    scope: 'zone',
    zoneId,
    target: { view: 'monitor', placement: 'bottom-panel' },
  })
  // Clear grid (guard against autoSave race)
  if (grid) {
    isLoadingWidgets = true
    grid.removeAll(true)
    isLoadingWidgets = false
  }
  showLayoutDropdown.value = false
  showCatalog.value = true
  toast.success(`Zone-Dashboard für ${zone?.name ?? zoneId} erstellt`)
}


</script>

<template>
  <div class="dashboard-builder">
    <!-- View Tab Bar (Hardware / Monitor / Dashboard) -->
    <ViewTabBar />

    <!-- Toolbar -->
    <div class="dashboard-builder__toolbar">
      <div class="dashboard-builder__toolbar-left">
        <LayoutGrid class="w-5 h-5" style="color: var(--color-accent-bright)" />
        <h2 class="dashboard-builder__title">Dashboard Builder</h2>

        <!-- Layout Selector -->
        <div ref="layoutSelectorRef" class="dashboard-builder__layout-selector">
          <button class="dashboard-builder__layout-btn" @click="showLayoutDropdown = !showLayoutDropdown">
            <span>{{ dashStore.activeLayout?.name || 'Kein Dashboard' }}</span>
            <ChevronDown class="w-3 h-3" />
          </button>

          <div v-if="showLayoutDropdown" class="dashboard-builder__layout-dropdown">
            <!-- Section A: Dashboards (standalone) -->
            <div v-if="dashStore.dashboardsTabLayouts.length > 0" class="dashboard-builder__layout-group">
              <div class="dashboard-builder__layout-group-title">Dashboards</div>
              <div
                v-for="layout in dashStore.dashboardsTabLayouts"
                :key="layout.id"
                :class="['dashboard-builder__layout-item', { 'dashboard-builder__layout-item--active': layout.id === dashStore.activeLayoutId }]"
                @click="switchLayout(layout.id)"
              >
                <span class="dashboard-builder__layout-item-name">{{ layout.name }}</span>
                <button
                  class="dashboard-builder__layout-item-delete"
                  title="Dashboard löschen"
                  @click.stop="handleDeleteSingleLayout(layout.id, layout.name)"
                >
                  <Trash2 class="w-3 h-3" />
                </button>
              </div>
            </div>

            <!-- Zones loading feedback (while activeZones still empty) -->
            <div v-if="zoneStore.activeZones.length === 0 && !zonesLoaded" class="dashboard-builder__layout-group">
              <div class="dashboard-builder__layout-group-title">Zonen werden geladen...</div>
            </div>

            <!-- Section B: Zone-Tiles (all active zones, lazy-create on first select) -->
            <div v-if="zoneStore.activeZones.length > 0" class="dashboard-builder__layout-group">
              <div class="dashboard-builder__layout-group-title">Zone-Tiles</div>
              <div
                v-for="zone in zoneStore.activeZones"
                :key="zone.zone_id"
                :class="['dashboard-builder__layout-item', {
                  'dashboard-builder__layout-item--active': dashStore.getCanonicalZoneTileLayout(zone.zone_id)?.id === dashStore.activeLayoutId
                }]"
                @click="handleSelectZoneTileCategory(zone.zone_id)"
              >
                <span class="dashboard-builder__layout-item-name">{{ zone.name }}</span>
              </div>
            </div>

            <!-- Section C: Zone-Dashboards (all active zones, lazy-create on first select) -->
            <div v-if="zoneStore.activeZones.length > 0" class="dashboard-builder__layout-group">
              <div class="dashboard-builder__layout-group-title">Zone-Dashboards</div>
              <div
                v-for="zone in zoneStore.activeZones"
                :key="`zd-${zone.zone_id}`"
                :class="['dashboard-builder__layout-item', {
                  'dashboard-builder__layout-item--active': dashStore.layouts.find(l => l.scope === 'zone' && l.zoneId === zone.zone_id)?.id === dashStore.activeLayoutId
                }]"
                @click="handleSelectZoneDashboard(zone.zone_id)"
              >
                <span class="dashboard-builder__layout-item-name">{{ zone.name }}</span>
              </div>
            </div>

            <div class="dashboard-builder__layout-divider" />
            <!-- Create Input — only under Dashboards -->
            <div class="dashboard-builder__layout-create">
              <input
                v-model="newLayoutName"
                type="text"
                placeholder="Neues Dashboard..."
                class="dashboard-builder__layout-input"
                @keydown.enter="() => handleCreateLayout()"
              />
              <button class="dashboard-builder__layout-create-btn" @click="() => handleCreateLayout()">
                <Plus class="w-3 h-3" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="dashboard-builder__toolbar-right">
        <button
          v-if="dashStore.activeLayoutId"
          :class="['dashboard-builder__tool-btn', { 'dashboard-builder__tool-btn--active': isCrosshairSyncOn }]"
          :title="isCrosshairSyncOn
            ? 'Crosshair-Sync aus — Fadenkreuz nicht mehr über Charts synchronisieren'
            : 'Crosshair-Sync ein — Fadenkreuz/Tooltip über alle Multi-Sensor-Charts dieses Dashboards synchronisieren (gleiche Zeitspanne)'"
          aria-label="Crosshair-Sync umschalten"
          :aria-pressed="isCrosshairSyncOn"
          @click="toggleCrosshairSync"
        >
          <Crosshair class="w-4 h-4" />
        </button>
        <button
          v-if="dashStore.activeLayoutId"
          :class="['dashboard-builder__tool-btn', { 'dashboard-builder__tool-btn--active': showCatalog }]"
          title="Widget-Katalog ein- oder ausblenden"
          aria-label="Widget-Katalog ein- oder ausblenden"
          @click="showCatalog = !showCatalog"
        >
          <Plus class="w-4 h-4" />
        </button>
        <button class="dashboard-builder__tool-btn" title="Exportieren" @click="handleExport">
          <Download class="w-4 h-4" />
        </button>
        <button class="dashboard-builder__tool-btn" title="Importieren" @click="handleImport">
          <Upload class="w-4 h-4" />
        </button>
        <button
          v-if="dashStore.activeLayoutId"
          class="dashboard-builder__tool-btn dashboard-builder__tool-btn--danger"
          title="Dashboard löschen"
          @click="handleDeleteLayout"
        >
          <Trash2 class="w-4 h-4" />
        </button>
      </div>
    </div>

    <!-- Sync-Error-Banner -->
    <div
      v-if="dashStore.lastSyncError"
      class="dashboard-builder__sync-error"
    >
      <AlertTriangle class="w-4 h-4 flex-shrink-0" />
      <span>{{ dashStore.lastSyncError }}</span>
      <button
        @click="retrySyncCurrentLayout"
        class="dashboard-builder__sync-retry"
      >
        Erneut versuchen
      </button>
    </div>

    <div class="dashboard-builder__content">
      <!-- Widget Catalog Sidebar (only in edit mode) -->
      <aside v-if="showCatalog" class="dashboard-builder__catalog">
        <h3 class="dashboard-builder__catalog-title">Widget-Katalog</h3>
        <p v-if="!dashStore.activeLayoutId" class="dashboard-builder__catalog-hint">
          Erstelle zuerst ein Dashboard
        </p>
        <div v-for="(widgets, category) in groupedWidgets" :key="category" class="dashboard-builder__catalog-group">
          <div class="dashboard-builder__catalog-group-title">{{ category }}</div>
          <button
            v-for="widget in widgets"
            :key="widget.type"
            class="dashboard-builder__catalog-item"
            :disabled="!dashStore.activeLayoutId"
            @click="addWidget(widget.type)"
          >
            <component :is="widget.icon" class="w-4 h-4 flex-shrink-0" />
            <div class="dashboard-builder__catalog-item-text">
              <span>{{ widget.label }}</span>
              <span class="dashboard-builder__catalog-item-desc">{{ widget.description }}</span>
            </div>
          </button>
        </div>
      </aside>

      <!-- Grid Area -->
      <div class="dashboard-builder__grid-area">
        <div v-if="!dashStore.activeLayoutId" class="dashboard-builder__no-layout">
          <LayoutGrid class="w-12 h-12" style="color: var(--color-text-muted); opacity: 0.3" />
          <template v-if="dashStore.layouts.length === 0">
            <p class="dashboard-builder__empty-title">Kein Dashboard vorhanden</p>
            <p class="dashboard-builder__empty-hint">
              Erstelle ein neues Dashboard für deine Zonen.
            </p>
            <button class="dashboard-builder__empty-cta" @click="handleCreateLayout('Neues Dashboard')">
              <Plus class="w-4 h-4" />
              Neues Dashboard
            </button>
          </template>
          <p v-else>Erstelle ein neues Dashboard oder wähle ein bestehendes aus.</p>
        </div>

        <div v-else>
          <section v-if="isZoneTileLayout" class="dashboard-builder__tile-preview">
            <div class="dashboard-builder__tile-preview-header">
              <span>Zone-Tile Vorschau</span>
              <span v-if="zoneTileIncompatibleWidgetsCount > 0" class="dashboard-builder__tile-preview-badge">
                {{ zoneTileIncompatibleWidgetsCount }} nur im Editor sichtbar
              </span>
              <span v-if="zoneTileOverflowWidgetsCount > 0" class="dashboard-builder__tile-preview-badge">
                {{ zoneTileOverflowWidgetsCount }} über Limit (max. {{ ZONE_TILE_MAX_WIDGETS }})
              </span>
            </div>
            <div class="dashboard-builder__tile-preview-body">
              <p v-if="zoneTilePreviewState === 'empty'" class="dashboard-builder__tile-preview-state">
                Noch keine Widgets. Füge im Katalog ein Widget hinzu.
              </p>
              <p v-else-if="zoneTilePreviewState === 'incompatible'" class="dashboard-builder__tile-preview-state">
                Auf der Zone-Kachel sind nur `Gauge`, `Sensor-Karte`, `Multi-Sensor-Chart`, `Linien-Chart`, `Historische Zeitreihe`, `Statistik` und `Fertigation-Paar` sichtbar.
              </p>
              <InlineDashboardPanel
                v-else-if="dashStore.activeLayoutId"
                :layout-id="dashStore.activeLayoutId"
                :zone-id="layoutZoneId"
                :compact="true"
                mode="view"
                class="dashboard-builder__tile-preview-panel"
              />
            </div>
          </section>
          <div
            ref="gridContainer"
            :class="[
              'grid-stack',
              'grid-stack--editing',
              { 'grid-stack--drop-target': dragStore.isDraggingDashboardWidget },
            ]"
          />
        </div>
      </div>
    </div>
    <!-- Widget Config Panel (SlideOver) -->
    <WidgetConfigPanel
      :open="configPanelOpen"
      :widget-id="configWidgetId"
      :widget-type="configWidgetType"
      :config="widgetConfigs.get(configWidgetId) || {}"
      :zone-id="layoutZoneId"
      @close="configPanelOpen = false"
      @update:config="handleConfigUpdate"
      @remove="handleConfigPanelRemove"
    />

  </div>
</template>

<style scoped>
.dashboard-builder {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: calc(100vh - var(--header-height) - 2rem);
}

/* Toolbar */
.dashboard-builder__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-4);
  background: var(--color-bg-secondary);
  border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
}

.dashboard-builder__toolbar-left {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.dashboard-builder__toolbar-right {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.dashboard-builder__title {
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0;
}

/* Layout Selector */
.dashboard-builder__layout-selector {
  position: relative;
}

.dashboard-builder__layout-btn {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  cursor: pointer;
}

.dashboard-builder__layout-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  margin-top: var(--space-1);
  min-width: 200px;
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  box-shadow: var(--elevation-floating);
  z-index: var(--z-dropdown);
  padding: var(--space-1);
}

.dashboard-builder__layout-item {
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.dashboard-builder__layout-group {
  padding: var(--space-1) 0;
}

.dashboard-builder__layout-group-title {
  font-size: var(--text-xxs);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  color: var(--color-text-muted);
  padding: 0 var(--space-3) var(--space-1);
}

.dashboard-builder__layout-item { display: flex; align-items: center; gap: var(--space-2); }
.dashboard-builder__layout-item:hover { background: var(--glass-bg-light); color: var(--color-text-primary); }
.dashboard-builder__layout-item--active { color: var(--color-iridescent-1); background: var(--color-accent-bg); }

.dashboard-builder__layout-divider {
  height: 1px;
  background: var(--glass-border);
  margin: var(--space-1) 0;
}


.dashboard-builder__layout-create {
  display: flex;
  gap: var(--space-1);
  padding: var(--space-1);
}

.dashboard-builder__layout-input {
  flex: 1;
  padding: var(--space-1) var(--space-2);
  background: var(--color-bg-quaternary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
}

.dashboard-builder__layout-create-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: var(--color-accent);
  border: none;
  border-radius: var(--radius-sm);
  color: white;
  cursor: pointer;
}

/* Tool Buttons */
.dashboard-builder__tool-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.dashboard-builder__tool-btn:hover { background: var(--glass-bg-light); color: var(--color-text-primary); }
.dashboard-builder__tool-btn--active { color: var(--color-iridescent-2); background: var(--color-accent-bg); }
.dashboard-builder__tool-btn--danger:hover { color: var(--color-status-alarm); }

.dashboard-builder__sync-error {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid var(--color-status-alarm);
  border-radius: var(--radius-md, 6px);
  color: var(--color-status-alarm);
  font-size: var(--text-sm);
  margin-bottom: var(--space-2);
}

.dashboard-builder__sync-retry {
  margin-left: auto;
  padding: var(--space-1) var(--space-2);
  background: transparent;
  border: 1px solid var(--color-status-alarm);
  border-radius: var(--radius-sm, 4px);
  color: var(--color-status-alarm);
  font-size: var(--text-xs);
  cursor: pointer;
  white-space: nowrap;
}

.dashboard-builder__sync-retry:hover {
  background: rgba(239, 68, 68, 0.12);
}

/* Content Area */
.dashboard-builder__content {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* Widget Catalog */
.dashboard-builder__catalog {
  width: 220px;
  background: var(--color-bg-secondary);
  border-right: 1px solid var(--glass-border);
  overflow-y: auto;
  padding: var(--space-3);
  flex-shrink: 0;
}

.dashboard-builder__catalog-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  margin: 0 0 var(--space-3) 0;
}

.dashboard-builder__catalog-group {
  margin-bottom: var(--space-3);
}

.dashboard-builder__catalog-group-title {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  margin-bottom: var(--space-1);
  text-transform: uppercase;
}

.dashboard-builder__catalog-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  margin-bottom: 2px;
}

.dashboard-builder__catalog-item-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.dashboard-builder__catalog-item-desc {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  line-height: 1.3;
}

.dashboard-builder__catalog-item:hover:not(:disabled) {
  border-color: var(--color-accent);
  color: var(--color-text-primary);
  background: rgba(59, 130, 246, 0.04);
}

.dashboard-builder__catalog-item:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.dashboard-builder__catalog-hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  padding: var(--space-2) var(--space-1);
  margin-bottom: var(--space-2);
}

/* Grid Area */
.dashboard-builder__grid-area {
  flex: 1;
  overflow: auto;
  padding: var(--space-4);
  background: var(--color-bg-primary);
}

.dashboard-builder__tile-preview {
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
  margin-bottom: var(--space-3);
  overflow: hidden;
}

.dashboard-builder__tile-preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--glass-border);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: 600;
}

.dashboard-builder__tile-preview-badge {
  font-size: var(--text-xs);
  color: var(--color-warning);
  font-weight: 500;
}

.dashboard-builder__tile-preview-body {
  padding: var(--space-3);
  min-height: 88px;
}

.dashboard-builder__tile-preview-state {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.dashboard-builder__tile-preview-panel {
  border-radius: var(--radius-sm);
  border: 1px dashed var(--glass-border);
}

.dashboard-builder__no-layout {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: var(--space-3);
  color: var(--color-text-muted);
  text-align: center;
}

.dashboard-builder__empty-title {
  font-size: var(--text-lg);
  font-weight: 600;
  margin: 0;
}

.dashboard-builder__empty-hint {
  font-size: var(--text-sm);
  max-width: 300px;
  color: var(--color-text-muted);
  margin: 0;
}

.dashboard-builder__empty-cta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  background: var(--color-accent);
  border: none;
  border-radius: var(--radius-sm);
  color: white;
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.dashboard-builder__empty-cta:hover {
  opacity: 0.9;
}

/* GridStack widget styling */
:deep(.grid-stack) {
  min-height: 400px;
}

:deep(.grid-stack-item-content) {
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}

:deep(.grid-stack-item-content:hover) {
  border-color: var(--glass-border-hover);
  box-shadow: var(--glass-shadow-l2), 0 0 12px var(--color-iridescent-glow);
}

:deep(.dashboard-widget) {
  display: flex;
  flex-direction: column;
  height: 100%;
}

:deep(.dashboard-widget__header) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--glass-border);
  cursor: default;
  flex-shrink: 0;
  gap: var(--space-2);
  min-height: 32px;
}

.grid-stack--editing :deep(.dashboard-widget__header) {
  cursor: move;
}

:deep(.dashboard-widget__title) {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

:deep(.dashboard-widget__type) {
  font-family: var(--font-mono);
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
  background: var(--color-bg-quaternary);
  padding: 1px 4px;
  border-radius: var(--radius-xs);
}

:deep(.dashboard-widget__actions) {
  display: none;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
  margin-left: auto;
}

.grid-stack--editing :deep(.dashboard-widget__actions) {
  display: inline-flex;
}

:deep(.dashboard-widget__gear-btn),
:deep(.dashboard-widget__remove-btn) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  opacity: 0.55;
}

.grid-stack--editing :deep(.dashboard-widget__header:hover .dashboard-widget__gear-btn),
.grid-stack--editing :deep(.dashboard-widget__header:hover .dashboard-widget__remove-btn),
.grid-stack--editing :deep(.dashboard-widget__header:focus-within .dashboard-widget__gear-btn),
.grid-stack--editing :deep(.dashboard-widget__header:focus-within .dashboard-widget__remove-btn) {
  opacity: 1;
}

/* Edit mode: dashed outline around widgets */
.grid-stack--editing :deep(.grid-stack-item-content) {
  outline: 1px dashed var(--color-iridescent-glow);
  outline-offset: -1px;
}

:deep(.dashboard-widget__gear-btn:hover) {
  background: var(--glass-bg-light);
  color: var(--color-text-primary);
}

:deep(.dashboard-widget__remove-btn:hover) {
  background: var(--glass-bg-light);
  color: var(--color-status-alarm);
}

/* Touch devices: enlarge targets to 44px (WCAG) and always visible */
@media (pointer: coarse), (hover: none) {
  .grid-stack--editing :deep(.dashboard-widget__gear-btn),
  .grid-stack--editing :deep(.dashboard-widget__remove-btn) {
    min-width: 44px;
    min-height: 44px;
    opacity: 1;
  }
}

:deep(.dashboard-widget__vue-mount) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

:deep(.dashboard-widget__body) {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

:deep(.dashboard-widget__placeholder) {
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  opacity: 0.5;
}

/* GridStack resizing handles */
:deep(.grid-stack-item > .ui-resizable-se) {
  width: 16px;
  height: 16px;
  right: 4px;
  bottom: 4px;
}

/* Drop-zone feedback when dragging widget from FAB */
.grid-stack--drop-target {
  outline: 2px dashed var(--color-accent);
  outline-offset: 4px;
  animation: drop-zone-pulse 1.5s ease-in-out infinite;
}

@keyframes drop-zone-pulse {
  0%, 100% { outline-color: rgba(96, 165, 250, 0.4); }
  50% { outline-color: rgba(96, 165, 250, 0.8); }
}

@media (prefers-reduced-motion: reduce) {
  .grid-stack--drop-target {
    animation: none;
    outline-color: var(--color-accent);
  }
}

/* ── Per-item delete button in dropdown ── */
.dashboard-builder__layout-item-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dashboard-builder__layout-item-delete {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  min-width: 24px;
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  border-radius: var(--radius-sm);
  cursor: pointer;
  opacity: 0.4;
  transition: all var(--transition-fast);
  margin-left: auto;
  flex-shrink: 0;
}

.dashboard-builder__layout-item:hover .dashboard-builder__layout-item-delete {
  opacity: 1;
}

.dashboard-builder__layout-item-delete:hover {
  color: var(--color-error);
  background: rgba(248, 113, 113, 0.1);
}

@media (hover: none) {
  .dashboard-builder__layout-item-delete {
    opacity: 1;
  }
}

</style>
