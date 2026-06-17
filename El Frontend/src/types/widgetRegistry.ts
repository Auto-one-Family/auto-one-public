/**
 * Widget Registry — Capability Map (AUT-247)
 *
 * Replaces the `computed(() => [...].includes(widgetType))` explosion in
 * WidgetConfigPanel.vue with a single declarative registry.
 *
 * Each widget type declares which configuration fields are relevant.
 * WidgetConfigPanel reads `WIDGET_REGISTRY[widgetType]` to decide which
 * UI sections to render.
 *
 * The registry is the single source of truth for widget capabilities; new
 * widget types should add an entry here rather than extending per-field
 * computeds.
 */

/**
 * Capability flags for a single widget type.
 *
 * All fields are optional and default to `false` when omitted (handled by
 * `getWidgetCapabilities()`).
 */
export interface WidgetCapabilities {
  /** Sensor picker (single sensor, grouped by Zone -> Subzone) */
  hasSensorPicker?: boolean
  /** Actuator picker */
  hasActuatorPicker?: boolean
  /** Multi-sensor list (1-6 sensors, MultiSensorWidget) */
  hasMultiSensorList?: boolean
  /** Short time range chips (1h / 6h / 24h / 7d / 30d) */
  hasShortTimeRange?: boolean
  /** Long time range chips (7d / 30d / 90d / season) */
  hasLongTimeRange?: boolean
  /** Y-axis min / max range */
  hasYRange?: boolean
  /** Threshold display + warn/alarm low/high inputs */
  hasThresholds?: boolean
  /** Color picker */
  hasColor?: boolean
  /** Sensor type select (Boxplot, Correlation-Scatter) */
  hasSensorType?: boolean
  /** Group-by select (Boxplot) */
  hasGroupBy?: boolean
  /** Anonymize-labels checkbox (Boxplot) */
  hasAnonymize?: boolean
  /** Correlation-scatter X-sensor / Y-metadata configuration */
  hasCorrelationConfig?: boolean
  /** Zone-filter for list widgets (alarm-list, esp-health, actuator-runtime) */
  hasZoneFilter?: boolean
  /** Statistics options (showStdDev, showQuality) */
  hasStatisticsOptions?: boolean
  /** Fertigation-pair config (inflow/runoff/sensorType/diff thresholds) */
  isFertigationPair?: boolean
}

/**
 * Resolved capabilities — every field defined as boolean.
 *
 * Returned by `getWidgetCapabilities()` so consumers don't need null-checks.
 */
export type ResolvedWidgetCapabilities = {
  [K in keyof WidgetCapabilities]-?: boolean
}

/**
 * Default (all-false) capabilities.
 */
const DEFAULT_CAPABILITIES: ResolvedWidgetCapabilities = {
  hasSensorPicker: false,
  hasActuatorPicker: false,
  hasMultiSensorList: false,
  hasShortTimeRange: false,
  hasLongTimeRange: false,
  hasYRange: false,
  hasThresholds: false,
  hasColor: false,
  hasSensorType: false,
  hasGroupBy: false,
  hasAnonymize: false,
  hasCorrelationConfig: false,
  hasZoneFilter: false,
  hasStatisticsOptions: false,
  isFertigationPair: false,
}

/**
 * Widget capability registry.
 *
 * Keep this in sync with:
 * - WidgetType union in `src/shared/stores/dashboard.store.ts`
 * - widgetComponentMap / WIDGET_TYPE_META in `src/composables/useDashboardWidgets.ts`
 *
 * AUT-247: `sensor-tile` is the canonical unified widget. The legacy types
 * (`sensor-card`, `gauge`, `line-chart`, `historical`) remain registered so
 * existing dashboard JSONs keep loading; their wrappers render `SensorTile`
 * with a fixed `displayMode`.
 */
export const WIDGET_REGISTRY: Record<string, WidgetCapabilities> = {
  // ── Sensor widgets (AUT-247: all back the SensorTile, kept for JSON compat) ──
  'sensor-tile': {
    hasSensorPicker: true,
    hasShortTimeRange: true,
    hasYRange: true,
    hasThresholds: true,
    hasColor: true,
  },
  'sensor-card': {
    hasSensorPicker: true,
    hasYRange: true,
    hasThresholds: true,
    hasColor: true,
  },
  'gauge': {
    hasSensorPicker: true,
    hasYRange: true,
    hasThresholds: true,
    hasColor: true,
  },
  'line-chart': {
    hasSensorPicker: true,
    hasYRange: true,
    hasThresholds: true,
    hasColor: true,
  },
  'historical': {
    hasSensorPicker: true,
    hasShortTimeRange: true,
    hasYRange: true,
    hasThresholds: true,
    hasColor: true,
  },

  // ── Statistics ──
  'statistics': {
    hasSensorPicker: true,
    hasShortTimeRange: true,
    hasStatisticsOptions: true,
  },

  // ── Multi-Sensor ──
  'multi-sensor': {
    hasMultiSensorList: true,
    hasYRange: true,
    hasColor: false, // F2b: per-Serie-Farbe via dataSources — Folge-Issue
  },

  // ── Fertigation Pair ──
  'fertigation-pair': {
    isFertigationPair: true,
    hasShortTimeRange: true,
  },

  // ── MultispeQ Boxplot / Correlation ──
  'comparison-boxplot': {
    hasSensorType: true,
    hasGroupBy: true,
    hasAnonymize: true,
    hasLongTimeRange: true,
  },
  'correlation-scatter': {
    hasSensorType: true,
    hasCorrelationConfig: true,
    hasLongTimeRange: true,
  },

  // ── Actuator ──
  'actuator-card': {
    hasActuatorPicker: true,
  },
  'actuator-runtime': {
    hasZoneFilter: true,
  },

  // ── System / Lists ──
  'esp-health': {
    hasZoneFilter: true,
  },
  'alarm-list': {
    hasZoneFilter: true,
  },

  // ── Cockpits ──
  'climate-rule-health': {
    // No standard fields — rule selector handled inside the widget itself.
  },
}

/**
 * Resolve capabilities for a widget type.
 *
 * Always returns a fully populated object — unknown widget types resolve to
 * all-false (safe default; the panel will simply show the title input).
 */
export function getWidgetCapabilities(widgetType: string | undefined | null): ResolvedWidgetCapabilities {
  if (!widgetType) return { ...DEFAULT_CAPABILITIES }
  const declared = WIDGET_REGISTRY[widgetType]
  if (!declared) return { ...DEFAULT_CAPABILITIES }
  return { ...DEFAULT_CAPABILITIES, ...declared }
}
