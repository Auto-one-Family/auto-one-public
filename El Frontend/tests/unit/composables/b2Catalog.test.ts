import { beforeEach, describe, expect, it } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import {
  B2_CATALOG_WIDGET_TYPE_META,
  B2_CATALOG_WIDGET_TYPES,
  isB2CatalogWidgetType,
  useDashboardWidgets,
  WIDGET_TYPE_META,
} from '@/composables/useDashboardWidgets'
import { useWidgetDragFromFab } from '@/composables/useWidgetDragFromFab'
import { ZONE_TILE_ALLOWED_WIDGET_TYPES } from '@/utils/zoneTileWidgets'
import AddWidgetDialog from '@/components/monitor/AddWidgetDialog.vue'

const KEEP_CATALOG_TYPES = [
  'sensor-tile',
  'gauge',
  'historical',
  'multi-sensor',
  'statistics',
  'alarm-list',
  'fertigation-pair',
] as const

const CUT_CATALOG_TYPES = ['sensor-card', 'line-chart'] as const

describe('B2 widget catalog (AUT-1528)', () => {
  it('should expose only B2 types for add-catalog', () => {
    expect([...B2_CATALOG_WIDGET_TYPES]).toEqual([...KEEP_CATALOG_TYPES])
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

describe('AUT-1526 dead catalog / FAB cuts', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should keep wired widgets in live catalog and render map', () => {
    const catalogTypes = WIDGET_TYPE_META.map((m) => m.type)
    const Host = defineComponent({
      setup() {
        const { widgetComponentMap } = useDashboardWidgets({ showConfigButton: false })
        return { widgetComponentMap }
      },
      template: '<div />',
    })
    const wrapper = mount(Host)

    for (const type of KEEP_CATALOG_TYPES) {
      expect(catalogTypes).toContain(type)
      expect(isB2CatalogWidgetType(type)).toBe(true)
      expect(wrapper.vm.widgetComponentMap[type]).toBeTruthy()
    }
  })

  it('should omit cut types from live catalog and FAB', () => {
    const catalogTypes = WIDGET_TYPE_META.map((m) => m.type)
    const { widgetItems } = useWidgetDragFromFab()
    const fabTypes = widgetItems.map((item) => item.type)

    for (const type of CUT_CATALOG_TYPES) {
      expect(catalogTypes).not.toContain(type)
      expect(fabTypes).not.toContain(type)
      expect(isB2CatalogWidgetType(type)).toBe(false)
    }
    expect(fabTypes.sort()).toEqual([...KEEP_CATALOG_TYPES].sort())
  })

  it('should not expose tileContext on AddWidgetDialog', () => {
    const props = AddWidgetDialog.props as Record<string, unknown> | undefined
    expect(props?.tileContext).toBeUndefined()
  })
})
