import type { DashboardWidget, WidgetType } from '@/shared/stores/dashboard.store'

export const ZONE_TILE_MAX_WIDGETS = 2

export const ZONE_TILE_ALLOWED_WIDGET_TYPES = new Set<WidgetType>([
  'gauge',
  'sensor-card',
  'multi-sensor',
  'line-chart',
  'historical',
  'statistics',
  'fertigation-pair',
])

export function isZoneTileAllowedWidgetType(type: string): type is WidgetType {
  return ZONE_TILE_ALLOWED_WIDGET_TYPES.has(type as WidgetType)
}

export function getZoneTileRenderableWidgets(
  widgets: DashboardWidget[],
  max = ZONE_TILE_MAX_WIDGETS,
): DashboardWidget[] {
  if (widgets.length === 0) return []
  return widgets.filter((widget) => isZoneTileAllowedWidgetType(widget.type)).slice(0, max)
}
