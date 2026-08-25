import { describe, expect, it } from 'vitest'
import {
  B2_CATALOG_WIDGET_TYPE_META,
  B2_CATALOG_WIDGET_TYPES,
  isB2CatalogWidgetType,
} from '@/composables/useDashboardWidgets'
import { ZONE_TILE_ALLOWED_WIDGET_TYPES } from '@/utils/zoneTileWidgets'

describe('B2 widget catalog (AUT-1528)', () => {
  it('should expose only B2 types for add-catalog', () => {
    expect([...B2_CATALOG_WIDGET_TYPES]).toEqual([
      'sensor-tile',
      'gauge',
      'historical',
      'multi-sensor',
      'statistics',
      'alarm-list',
      'fertigation-pair',
    ])
    expect(B2_CATALOG_WIDGET_TYPE_META.map((m) => m.type).sort()).toEqual(
      [...B2_CATALOG_WIDGET_TYPES].sort(),
    )
  })

  it('should reject B1 catalog types', () => {
    expect(isB2CatalogWidgetType('actuator-card')).toBe(false)
    expect(isB2CatalogWidgetType('actuator-runtime')).toBe(false)
    expect(isB2CatalogWidgetType('esp-health')).toBe(false)
    expect(isB2CatalogWidgetType('climate-rule-health')).toBe(false)
    expect(isB2CatalogWidgetType('claude-chat')).toBe(false)
    expect(isB2CatalogWidgetType('sensor-card')).toBe(false)
    expect(isB2CatalogWidgetType('line-chart')).toBe(false)
  })

  it('should list sensor-tile on the zone-tile whitelist and drop ghost types', () => {
    expect(ZONE_TILE_ALLOWED_WIDGET_TYPES.has('sensor-tile')).toBe(true)
    expect(ZONE_TILE_ALLOWED_WIDGET_TYPES.has('sensor-card')).toBe(false)
    expect(ZONE_TILE_ALLOWED_WIDGET_TYPES.has('line-chart')).toBe(false)
  })
})
