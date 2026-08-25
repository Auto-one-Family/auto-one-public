/**
 * useWidgetDragFromFab — Bridges FAB widget catalog to HTML5 drag + GridStack drop.
 *
 * Responsibilities:
 * 1. Provides serializable WidgetDragItem[] from WIDGET_TYPE_META
 * 2. Groups items by category (Sensoren/Aktoren/System)
 * 3. handleDragStart: sets dataTransfer + data-gs-* attributes, updates dragState store, closes FAB
 * 4. handleDragEnd: cleans up dragState
 * 5. Keyboard alternative: announceWidget → CustomEvent → CustomDashboardView.addWidget()
 */

import { ref, computed } from 'vue'
import { useDragStateStore } from '@/shared/stores/dragState.store'
import type { DashboardWidgetDragPayload } from '@/shared/stores/dragState.store'
import { useQuickActionStore } from '@/shared/stores/quickAction.store'
import { B2_CATALOG_WIDGET_TYPE_META } from '@/composables/useDashboardWidgets'
// ── Types ──────────────────────────────────────────────────────────────────────

export interface WidgetDragItem {
  type: string
  label: string
  description: string
  iconName: string
  category: string
  w: number
  h: number
  minW: number
  minH: number
}

/**
 * Serializable widget items derived from the single source WIDGET_TYPE_META
 * (AUT-901). No hand-maintained copy: adding/removing a type in WIDGET_TYPE_META
 * keeps the FAB catalog in sync by construction (the former WIDGET_DRAG_ITEMS
 * hand-copy drifted — it still listed line-chart/sensor-card after AUT-900 and
 * lacked the 5 newer types). Only the serializable string `iconName` is carried
 * here; the Component lookup happens at render time via WIDGET_ICON_MAP.
 */
const WIDGET_DRAG_ITEMS: WidgetDragItem[] = B2_CATALOG_WIDGET_TYPE_META.map((meta) => ({
  type: meta.type,
  label: meta.label,
  description: meta.description,
  iconName: meta.iconName,
  category: meta.category,
  w: meta.w,
  h: meta.h,
  minW: meta.minW,
  minH: meta.minH,
}))

// ── Composable ─────────────────────────────────────────────────────────────────

export function useWidgetDragFromFab() {
  const dragStore = useDragStateStore()
  const quickActionStore = useQuickActionStore()

  /** Currently announced widget for keyboard placement */
  const announcedWidget = ref<WidgetDragItem | null>(null)

  /** All widget items */
  const widgetItems = WIDGET_DRAG_ITEMS

  /** Grouped by category */
  const groupedWidgetItems = computed(() => {
    const groups: Record<string, WidgetDragItem[]> = {}
    for (const item of widgetItems) {
      if (!groups[item.category]) groups[item.category] = []
      groups[item.category].push(item)
    }
    return groups
  })

  /**
   * Start HTML5 drag from a widget catalog item.
   * Sets dataTransfer payload, data-gs-* attributes for GridStack,
   * updates dragState store, and closes the FAB menu.
   */
  function handleDragStart(event: DragEvent, item: WidgetDragItem): void {
    if (!event.dataTransfer) return

    const payload: DashboardWidgetDragPayload = {
      action: 'add-dashboard-widget',
      widgetType: item.type,
      label: item.label,
      defaultW: item.w,
      defaultH: item.h,
      minW: item.minW,
      minH: item.minH,
    }

    // HTML5 dataTransfer
    event.dataTransfer.effectAllowed = 'copy'
    event.dataTransfer.setData('application/json', JSON.stringify(payload))
    event.dataTransfer.setData('text/plain', item.type)

    // Set data-gs-* attributes on the source element for GridStack recognition
    const el = event.target as HTMLElement
    el.setAttribute('data-gs-w', String(item.w))
    el.setAttribute('data-gs-h', String(item.h))
    el.setAttribute('data-gs-min-w', String(item.minW))
    el.setAttribute('data-gs-min-h', String(item.minH))

    // Update global drag state
    dragStore.startDashboardWidgetDrag(payload)

    // Close the FAB menu so user can see the grid
    quickActionStore.closeMenu()
  }

  /** End drag — cleanup via dragState store */
  function handleDragEnd(): void {
    dragStore.endDrag()
  }

  /**
   * Keyboard alternative: announce a widget for placement.
   * Dispatches CustomEvent that CustomDashboardView listens for.
   */
  function announceWidget(item: WidgetDragItem): void {
    announcedWidget.value = item
    window.dispatchEvent(new CustomEvent('widget-place-announced', {
      detail: { type: item.type },
    }))
    quickActionStore.closeMenu()
  }

  /** Cancel keyboard announcement */
  function cancelAnnouncement(): void {
    announcedWidget.value = null
  }

  return {
    widgetItems,
    groupedWidgetItems,
    announcedWidget,
    handleDragStart,
    handleDragEnd,
    announceWidget,
    cancelAnnouncement,
  }
}
