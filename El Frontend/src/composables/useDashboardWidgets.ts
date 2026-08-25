/**
 * useDashboardWidgets — Shared Widget Mount/Unmount Composable
 *
 * Container-agnostic widget rendering for:
 * - CustomDashboardView (GridStack Editor)
 * - DashboardViewer (GridStack Static)
 * - InlineDashboardPanel (CSS-Grid)
 *
 * Extracts widgetComponentMap, widget type metadata, default configs,
 * and DOM creation/mount/cleanup logic from CustomDashboardView.
 */

import { getCurrentInstance, h, render, type Component, type Ref, unref } from 'vue'

// Widget components
import LineChartWidget from '@/components/dashboard-widgets/LineChartWidget.vue'
import GaugeWidget from '@/components/dashboard-widgets/GaugeWidget.vue'
import SensorCardWidget from '@/components/dashboard-widgets/SensorCardWidget.vue'
import SensorTile from '@/components/dashboard-widgets/SensorTile.vue'
import ActuatorCardWidget from '@/components/dashboard-widgets/ActuatorCardWidget.vue'
import HistoricalChartWidget from '@/components/dashboard-widgets/HistoricalChartWidget.vue'
import ESPHealthWidget from '@/components/dashboard-widgets/ESPHealthWidget.vue'
import AlarmListWidget from '@/components/dashboard-widgets/AlarmListWidget.vue'
import ActuatorRuntimeWidget from '@/components/dashboard-widgets/ActuatorRuntimeWidget.vue'
import MultiSensorWidget from '@/components/dashboard-widgets/MultiSensorWidget.vue'
import StatisticsWidget from '@/components/dashboard-widgets/StatisticsWidget.vue'
import FertigationPairWidget from '@/components/dashboard-widgets/FertigationPairWidget.vue'
import BoxplotWidget from '@/components/dashboard-widgets/BoxplotWidget.vue'
import CorrelationScatterWidget from '@/components/dashboard-widgets/CorrelationScatterWidget.vue'
import ClimateRuleHealthWidget from '@/components/dashboard-widgets/ClimateRuleHealthWidget.vue'
import ClaudeChatWidget from '@/components/monitor/widgets/ClaudeChatWidget.vue'

// Icons for widget catalog
import {
  BarChart3, Gauge, Activity, Zap, Bell, Cpu, Droplets,
  BoxSelect, GitCompareArrows, ThermometerSun, Sparkles,
} from 'lucide-vue-next'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface WidgetTypeMeta {
  type: string
  label: string
  description: string
  icon: Component
  /** Serializable icon name (lucide export name) — used by DnD/FAB catalog where Component objects cannot be transferred. Resolve via WIDGET_ICON_MAP. */
  iconName: string
  w: number
  h: number
  minW: number
  minH: number
  category: string
  /**
   * AUT-1107: Optional per-display-mode size overrides for widgets that expose a
   * mode picker in the config panel (currently only sensor-tile). Each key maps to
   * the SensorTileDisplayMode value. When a new widget is placed and its default
   * config has a displayMode, the matching entry is used instead of w/h/minW/minH.
   * Widgets without modeSizes fall back to the flat w/h/minW/minH fields.
   */
  modeSizes?: Partial<Record<string, { w: number; h: number; minW: number; minH: number }>>
}

export interface UseDashboardWidgetsOptions {
  /** Show gear (config) button on widget headers. Default: true */
  showConfigButton?: boolean
  /** Show outer widget header (title + type badge). Default: true.
   *  Set to false for inline/read-only panels where widgets provide their own headers. */
  showWidgetHeader?: boolean
  /** Called when gear button is clicked */
  onConfigClick?: (widgetId: string, widgetType: string) => void
  /** Called when remove (X) button is clicked */
  onRemoveClick?: (widgetId: string) => void
  /** Called when widget emits onUpdate:config */
  onConfigUpdate?: (widgetId: string, newConfig: Record<string, any>) => void
  /** Disable interactive controls (e.g. actuator toggle) in monitor context. Default: false */
  readOnly?: boolean
  /** Zone ID to propagate to widgets for zone-scoped sensor filtering (PA-02c) */
  zoneId?: Ref<string | undefined>
  /**
   * When true (Monitor L1 zone-tile `compact` panel), gauge widgets get spot-vs-zone KPI hints.
   * Ref so keep-alive / prop changes re-mount with correct semantics via existing watch on widgets.
   */
  compactTileGaugeSemantics?: Ref<boolean>
  /**
   * Dashboard-level crosshair-sync group id (AUT-912) propagated to Multi-Sensor charts.
   * Stable identity (e.g. the active layout id) injected once at mount; the on/off state is
   * read reactively from useCrosshairSync, so toggling never requires a re-mount.
   */
  syncGroupId?: Ref<string | undefined>
}

export interface UseDashboardWidgetsReturn {
  widgetComponentMap: Record<string, Component>
  WIDGET_TYPE_META: WidgetTypeMeta[]
  WIDGET_DEFAULT_CONFIGS: Record<string, Record<string, unknown>>
  createWidgetElement: (type: string, title: string, widgetId: string, mountId: string) => HTMLElement
  mountWidgetToElement: (widgetId: string, mountId: string, type: string, config: Record<string, any>) => void
  unmountWidgetFromElement: (widgetId: string) => void
  cleanupAllWidgets: () => void
  mountedWidgets: Map<string, HTMLElement>
}

// ─── Static Data (shared across all instances) ──────────────────────────────

/** Widget component registry — all 16 types */
const widgetComponentMap: Record<string, Component> = {
  'sensor-tile': SensorTile,
  'line-chart': LineChartWidget,
  'gauge': GaugeWidget,
  'sensor-card': SensorCardWidget,
  'actuator-card': ActuatorCardWidget,
  'historical': HistoricalChartWidget,
  'esp-health': ESPHealthWidget,
  'alarm-list': AlarmListWidget,
  'actuator-runtime': ActuatorRuntimeWidget,
  'multi-sensor': MultiSensorWidget,
  'statistics': StatisticsWidget,
  'fertigation-pair': FertigationPairWidget,
  'comparison-boxplot': BoxplotWidget,
  'correlation-scatter': CorrelationScatterWidget,
  'climate-rule-health': ClimateRuleHealthWidget,
  'claude-chat': ClaudeChatWidget,
}

/**
 * Widget type metadata for catalog and auto-generation.
 *
 * Single source of truth for the widget catalog (AUT-901). Each entry carries
 * both `icon` (Component, for in-setup render like the editor sidebar) and
 * `iconName` (serializable string, resolved via WIDGET_ICON_MAP for the
 * AddWidgetDialog and the FAB QuickWidgetPanel). Exported so the FAB drag path
 * (useWidgetDragFromFab) can derive its items instead of hand-copying them.
 */
/** AUT-1528: B2 add-catalog only. Render map stays complete for placed B1 cards. */
export const B2_CATALOG_WIDGET_TYPES = [
  'sensor-tile',
  'gauge',
  'historical',
  'multi-sensor',
  'statistics',
  'alarm-list',
  'fertigation-pair',
] as const

export type B2CatalogWidgetType = typeof B2_CATALOG_WIDGET_TYPES[number]

export function isB2CatalogWidgetType(type: string): type is B2CatalogWidgetType {
  return (B2_CATALOG_WIDGET_TYPES as readonly string[]).includes(type)
}

export const WIDGET_TYPE_META: WidgetTypeMeta[] = [
  // AUT-247: SensorTile is the unified sensor widget — listed first as preferred
  // AUT-1107: modeSizes provide content-driven initial placement dimensions per displayMode.
  // Rationale: numeric = compact number display (small footprint), gauge = semicircle needs
  // equal aspect ratio (mirrors GaugeWidget entry), sparkline = line chart needs width,
  // historic = time-series chart needs substantial space (mirrors historical entry but with
  // relaxed minW since SensorTile has no inline time-range chips).
  // The base w/h/minW/minH remain as fallback for FAB-drag-in and any unknown modes.
  {
    type: 'sensor-tile',
    label: 'Sensor-Kachel',
    description: 'Wert, Kurve oder Kreisanzeige — umschaltbar',
    icon: Activity,
    iconName: 'Activity',
    w: 4, h: 3, minW: 3, minH: 4,
    category: 'Sensoren',
    modeSizes: {
      numeric:   { w: 3, h: 2, minW: 2, minH: 2 },
      gauge:     { w: 3, h: 3, minW: 2, minH: 3 },
      sparkline: { w: 4, h: 3, minW: 3, minH: 3 },
      historic:  { w: 6, h: 4, minW: 4, minH: 4 },
    },
  },
  { type: 'gauge', label: 'Gauge-Chart', description: 'Kreisanzeige für aktuelle Messwerte', icon: Gauge, iconName: 'Gauge', w: 3, h: 3, minW: 2, minH: 3, category: 'Sensoren' },
  { type: 'historical', label: 'Historische Zeitreihe', description: 'Historischer Verlauf aus der Datenbank', icon: BarChart3, iconName: 'BarChart3', w: 6, h: 4, minW: 6, minH: 4, category: 'Sensoren' },
  { type: 'multi-sensor', label: 'Multi-Sensor-Chart', description: 'Mehrere Sensoren in einem Chart vergleichen', icon: BarChart3, iconName: 'BarChart3', w: 8, h: 5, minW: 6, minH: 4, category: 'Sensoren' },
  { type: 'actuator-card', label: 'Aktor-Status', description: 'Aktor-Status und Steuerung', icon: Zap, iconName: 'Zap', w: 3, h: 2, minW: 2, minH: 2, category: 'Aktoren' },
  { type: 'actuator-runtime', label: 'Aktor-Laufzeit', description: 'Laufzeitstatistik eines Aktors', icon: BarChart3, iconName: 'BarChart3', w: 4, h: 3, minW: 3, minH: 3, category: 'Aktoren' },
  { type: 'esp-health', label: 'ESP-Health', description: 'Health-Metriken eines ESP32', icon: Cpu, iconName: 'Cpu', w: 6, h: 3, minW: 4, minH: 3, category: 'System' },
  { type: 'alarm-list', label: 'Alarm-Liste', description: 'Liste aktiver und vergangener Alarme', icon: Bell, iconName: 'Bell', w: 4, h: 4, minW: 4, minH: 4, category: 'System' },
  { type: 'statistics', label: 'Statistik', description: 'Statistik eines Sensors über einen Zeitraum', icon: BarChart3, iconName: 'BarChart3', w: 4, h: 3, minW: 3, minH: 2, category: 'Sensoren' },
  { type: 'fertigation-pair', label: 'Fertigation-Paar', description: 'EC/pH Eingang und Ausgang im Vergleich', icon: Droplets, iconName: 'Droplets', w: 6, h: 4, minW: 4, minH: 3, category: 'Sensoren' },
  { type: 'comparison-boxplot', label: 'MultispeQ Boxplot', description: 'Vergleich von MultispeQ-Aggregaten (Min/Q1/Median/Q3/Max) pro Gruppe', icon: BoxSelect, iconName: 'BoxSelect', w: 6, h: 4, minW: 4, minH: 3, category: 'MultispeQ' },
  { type: 'correlation-scatter', label: 'MultispeQ Korrelation', description: 'Scatter-Plot Sensorwert vs. Metadaten (z. B. PPFD vs. Yield)', icon: GitCompareArrows, iconName: 'GitCompareArrows', w: 6, h: 4, minW: 4, minH: 3, category: 'MultispeQ' },
  { type: 'climate-rule-health', label: 'Klima-Regel Cockpit', description: 'Soll/IST/ESP-Status/Dispatch für eine kritische Klimaregel', icon: ThermometerSun, iconName: 'ThermometerSun', w: 4, h: 3, minW: 3, minH: 2, category: 'Regeln' },
  { type: 'claude-chat', label: 'Claude Assistant', description: 'KI-gestütztes Debugging und Stack-Analyse', icon: Sparkles, iconName: 'Sparkles', w: 4, h: 6, minW: 3, minH: 4, category: 'System' },
]

export const B2_CATALOG_WIDGET_TYPE_META: WidgetTypeMeta[] = WIDGET_TYPE_META.filter(
  (meta) => isB2CatalogWidgetType(meta.type),
)

/**
 * Shared widget icon map (AUT-901) — serializable `iconName` -> Lucide Component.
 *
 * Single icon lookup for the AddWidgetDialog and the FAB QuickWidgetPanel,
 * replacing two drifting local ICON_MAPs that only covered 6 icons (the 5
 * newer types fell back to BarChart3). Keep in sync with the `iconName` values
 * in WIDGET_TYPE_META above.
 */
export const WIDGET_ICON_MAP: Record<string, Component> = {
  BarChart3,
  Gauge,
  Activity,
  Zap,
  Bell,
  Cpu,
  Droplets,
  BoxSelect,
  GitCompareArrows,
  ThermometerSun,
  Sparkles,
}

/** Default config per widget type */
const WIDGET_DEFAULT_CONFIGS: Record<string, Record<string, unknown>> = {
  // AUT-1107: Mode-Leiste + Qualitäts-Punkt aus der Kachel — Konfiguration nur im Panel.
  'sensor-tile': {
    displayMode: 'numeric',
    timeRange: '1h',
    showThresholds: false,
    hideModeToggle: true,
    showQualityDot: false,
  },
  'line-chart': { timeRange: '1h', showThresholds: false },
  'gauge': {},
  'sensor-card': {},
  'historical': { timeRange: '24h' },
  'multi-sensor': { dataSources: '' },
  'actuator-card': {},
  'actuator-runtime': {},
  'esp-health': {},
  'alarm-list': {},
  'statistics': { timeRange: '7d', showStdDev: true, showQuality: false },
  'fertigation-pair': { sensorType: 'ec', timeRange: '24h', diffWarningThreshold: 0.5, diffCriticalThreshold: 0.8 },
  'comparison-boxplot': {
    config: {
      sensor_type: 'phi2',
      group_by: 'zone_id',
      date_range: '30d',
      anonymize_labels: true,
    },
  },
  'correlation-scatter': {
    config: {
      x_sensor_type: 'ppfd',
      y_metadata_key: 'yield_g',
      date_range: '30d',
      show_regression_line: false,
    },
  },
  'climate-rule-health': { ruleId: 0 },
  'claude-chat': {},
}

/** Gear icon SVG (inline, no external dependency) */
const GEAR_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>'

/** X (close/remove) icon SVG (inline, Lucide X) */
const REMOVE_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>'

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * Shared widget rendering composable.
 *
 * MUST be called in setup() context (captures getCurrentInstance for appContext).
 */
export function useDashboardWidgets(options: UseDashboardWidgetsOptions = {}): UseDashboardWidgetsReturn {
  const {
    showConfigButton = true,
    showWidgetHeader = true,
    onConfigClick,
    onRemoveClick,
    onConfigUpdate,
    readOnly = false,
    zoneId,
    compactTileGaugeSemantics,
    syncGroupId,
  } = options

  // Capture appContext in setup() context — CRITICAL: do not move into callbacks
  const instance = getCurrentInstance()
  const appContext = instance?.appContext ?? null

  // Per-instance map of mounted widget elements
  const mountedWidgets = new Map<string, HTMLElement>()

  /**
   * Build widget DOM element using the DOM API (no innerHTML for user strings).
   * GridStack cells or CSS-Grid cells can use this to inject widget content.
   */
  function createWidgetElement(type: string, title: string, widgetId: string, mountId: string): HTMLElement {
    const widgetDef = WIDGET_TYPE_META.find(w => w.type === type)
    const label = widgetDef?.label || type
    const hasVueComponent = type in widgetComponentMap

    const container = document.createElement('div')
    container.className = 'dashboard-widget'
    container.dataset.type = type
    container.dataset.widgetId = widgetId

    // Outer header: skip for inline/read-only panels (widgets provide their own headers)
    if (showWidgetHeader) {
      const header = document.createElement('div')
      header.className = 'dashboard-widget__header'

      const titleEl = document.createElement('span')
      titleEl.className = 'dashboard-widget__title'
      titleEl.textContent = title || label

      header.append(titleEl)

      // Actions in eigener Flex-Gruppe — Settings/Remove bleiben im Header und
      // überdecken nicht Mode-Leiste oder Chart-Controls der Sensor-Kachel.
      const actions = document.createElement('div')
      actions.className = 'dashboard-widget__actions'

      if (showConfigButton && onConfigClick) {
        const gearBtn = document.createElement('button')
        gearBtn.className = 'dashboard-widget__gear-btn'
        gearBtn.type = 'button'
        gearBtn.title = 'Konfigurieren'
        gearBtn.setAttribute('aria-label', 'Widget konfigurieren')
        gearBtn.innerHTML = GEAR_SVG
        gearBtn.addEventListener('click', (e) => {
          e.stopPropagation()
          onConfigClick(widgetId, type)
        })
        actions.appendChild(gearBtn)
      }

      // Sensor-Kachel: kein Delete im Kachel-Header (Overlap). Entfernen über Config-Panel.
      if (onRemoveClick && type !== 'sensor-tile') {
        const removeBtn = document.createElement('button')
        removeBtn.className = 'dashboard-widget__remove-btn'
        removeBtn.type = 'button'
        removeBtn.title = 'Widget entfernen'
        removeBtn.setAttribute('aria-label', 'Widget entfernen')
        removeBtn.innerHTML = REMOVE_SVG
        removeBtn.addEventListener('click', (e) => {
          e.stopPropagation()
          onRemoveClick(widgetId)
        })
        actions.appendChild(removeBtn)
      }

      if (actions.childElementCount > 0) {
        header.appendChild(actions)
      }

      container.appendChild(header)
    }

    if (hasVueComponent) {
      const mountDiv = document.createElement('div')
      mountDiv.id = mountId
      mountDiv.className = 'dashboard-widget__vue-mount'
      container.appendChild(mountDiv)
    } else {
      const body = document.createElement('div')
      body.className = 'dashboard-widget__body'
      const placeholder = document.createElement('div')
      placeholder.className = 'dashboard-widget__placeholder'
      placeholder.textContent = label
      body.appendChild(placeholder)
      container.appendChild(body)
    }

    return container
  }

  /**
   * Mount a Vue widget component into an element.
   * Container-agnostic: works for GridStack cells AND CSS-Grid cells.
   */
  function mountWidgetToElement(widgetId: string, mountId: string, type: string, config: Record<string, any>): void {
    const WidgetComponent = widgetComponentMap[type]
    if (!WidgetComponent) return

    const mountEl = document.getElementById(mountId)
    if (!mountEl) return

    // Build props from config
    const props: Record<string, any> = {}
    if (config.sensorId) props.sensorId = config.sensorId
    if (config.valueSource === 'zone_avg' || config.valueSource === 'sensor') {
      props.valueSource = config.valueSource
    }
    if (config.aggCategory) props.aggCategory = config.aggCategory
    if (config.actuatorId) props.actuatorId = config.actuatorId
    if (config.timeRange) props.timeRange = config.timeRange
    if (config.showThresholds != null) props.showThresholds = config.showThresholds
    if (config.zoneFilter) props.zoneFilter = config.zoneFilter
    if (config.showOfflineOnly != null) props.showOfflineOnly = config.showOfflineOnly
    if (config.maxItems) props.maxItems = config.maxItems
    if (config.showResolved != null) props.showResolved = config.showResolved
    if (config.actuatorFilter) props.actuatorFilter = config.actuatorFilter
    if (config.dataSources != null) props.dataSources = config.dataSources
    if (config.actuatorIds != null) props.actuatorIds = config.actuatorIds
    if (config.comparisonMode != null) props.comparisonMode = config.comparisonMode
    if (config.yMin != null) props.yMin = config.yMin
    if (config.yMax != null) props.yMax = config.yMax
    if (config.color) props.color = config.color
    if (config.warnLow != null) props.warnLow = config.warnLow
    if (config.warnHigh != null) props.warnHigh = config.warnHigh
    if (config.alarmLow != null) props.alarmLow = config.alarmLow
    if (config.alarmHigh != null) props.alarmHigh = config.alarmHigh
    if (config.showStdDev != null) props.showStdDev = config.showStdDev
    if (config.showQuality != null) props.showQuality = config.showQuality

    // AUT-247: SensorTile-specific props
    if (config.displayMode) props.displayMode = config.displayMode
    if (config.liveBufferSize != null) props.liveBufferSize = config.liveBufferSize
    if (config.unit) props.unit = config.unit
    if (config.showTrendIcon != null) props.showTrendIcon = config.showTrendIcon
    // Force-hide for sensor-tile: alte Layout-JSONs ohne Flags sollen die Mode-Leiste /
    // den Qualitäts-Punkt nicht wieder einblenden (Editor + Inline-Monitor).
    if (type === 'sensor-tile') {
      props.hideModeToggle = true
      props.showQualityDot = false
    } else {
      if (config.showQualityDot != null) props.showQualityDot = config.showQualityDot
      if (config.hideModeToggle != null) props.hideModeToggle = config.hideModeToggle
    }

    // FertigationPairWidget props
    if (config.inflowSensorId) props.inflowSensorId = config.inflowSensorId
    if (config.runoffSensorId) props.runoffSensorId = config.runoffSensorId
    if (config.sensorType) props.sensorType = config.sensorType
    if (config.diffWarningThreshold != null) props.diffWarningThreshold = config.diffWarningThreshold
    if (config.diffCriticalThreshold != null) props.diffCriticalThreshold = config.diffCriticalThreshold
    if (config.referenceBands) props.referenceBands = config.referenceBands
    if (config.title) props.title = config.title

    // ClimateRuleHealthWidget props (AUT-115)
    if (config.ruleId != null) props.ruleId = config.ruleId

    // BoxplotWidget + CorrelationScatterWidget: nested config object (AUT-220)
    if (type === 'comparison-boxplot' || type === 'correlation-scatter') {
      // Pass widget-specific config as a nested object (the widgets expect `config` prop)
      // Falls back to flat config keys to remain compatible with legacy widget configs.
      props.config = (config.config && typeof config.config === 'object')
        ? config.config
        : {
            sensor_type: config.sensor_type,
            group_by: config.group_by,
            date_range: config.date_range,
            anonymize_labels: config.anonymize_labels,
            x_sensor_type: config.x_sensor_type,
            y_metadata_key: config.y_metadata_key,
            show_regression_line: config.show_regression_line,
          }
    }

    // espId prop for widgets that support device-scoped context (e.g. ClaudeChatWidget)
    if (config.espId) props.espId = config.espId

    // readOnly prop for actuator widgets (monitor context = no toggle)
    if (readOnly && type === 'actuator-card') {
      props.readOnly = true
    }

    // Zone ID for zone-scoped sensor filtering (PA-02c)
    if (zoneId?.value) {
      props.zoneId = zoneId.value
    }

    // Dashboard-level crosshair-sync group (AUT-912) — only the multi-sensor chart consumes it.
    // Stable identity injected at mount; useCrosshairSync drives the reactive on/off.
    if (type === 'multi-sensor' && unref(syncGroupId)) {
      props.syncGroupId = unref(syncGroupId)
    }

    // L1 zone-tile: Spot-Gauge vs Zonenmittel (gleiche Aggregation wie ZoneTileCard-Ø)
    if (type === 'gauge' && unref(compactTileGaugeSemantics)) {
      if (config.valueSource === 'zone_avg') {
        props.tileZoneAvgSemantics = true
      } else {
        props.tileSpotSemantics = true
      }
    }

    // onUpdate:config handler
    if (onConfigUpdate) {
      props['onUpdate:config'] = (newConfig: Record<string, any>) => {
        onConfigUpdate(widgetId, newConfig)
      }
    }

    // Create vnode and attach appContext for Pinia/router access
    const vnode = h(WidgetComponent, props)
    if (appContext) {
      vnode.appContext = appContext
    }

    render(vnode, mountEl)
    mountedWidgets.set(widgetId, mountEl)
  }

  /** Unmount a single widget from its element */
  function unmountWidgetFromElement(widgetId: string): void {
    const mountEl = mountedWidgets.get(widgetId)
    if (mountEl) {
      render(null, mountEl)
      mountedWidgets.delete(widgetId)
    }
  }

  /** Cleanup all mounted widgets — call in onUnmounted() */
  function cleanupAllWidgets(): void {
    for (const [, el] of mountedWidgets) {
      render(null, el)
    }
    mountedWidgets.clear()
  }

  return {
    widgetComponentMap,
    WIDGET_TYPE_META,
    WIDGET_DEFAULT_CONFIGS,
    createWidgetElement,
    mountWidgetToElement,
    unmountWidgetFromElement,
    cleanupAllWidgets,
    mountedWidgets,
  }
}
