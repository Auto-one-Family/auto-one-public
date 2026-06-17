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

/** Static widget items derived from WIDGET_TYPE_META (duplicated to avoid setup-context dependency) */
const WIDGET_DRAG_ITEMS: WidgetDragItem[] = [
  { type: 'line-chart', label: 'Linien-Chart', description: 'Live-Verlauf eines Sensors', iconName: 'BarChart3', category: 'Sensoren', w: 6, h: 4, minW: 4, minH: 3 },
  { type: 'gauge', label: 'Gauge-Chart', description: 'Kreisanzeige fuer Messwerte', iconName: 'Gauge', category: 'Sensoren', w: 3, h: 3, minW: 2, minH: 3 },
  { type: 'sensor-card', label: 'Sensor-Karte', description: 'Kompakte Karte mit Wert', iconName: 'Activity', category: 'Sensoren', w: 3, h: 2, minW: 2, minH: 2 },
  { type: 'historical', label: 'Historische Zeitreihe', description: 'Zeitreihe mit API-Daten', iconName: 'BarChart3', category: 'Sensoren', w: 6, h: 4, minW: 6, minH: 4 },
  { type: 'multi-sensor', label: 'Multi-Sensor-Chart', description: 'Mehrere Sensoren vergleichen', iconName: 'BarChart3', category: 'Sensoren', w: 8, h: 5, minW: 6, minH: 4 },
  { type: 'actuator-card', label: 'Aktor-Status', description: 'Aktor-Status und Steuerung', iconName: 'Zap', category: 'Aktoren', w: 3, h: 2, minW: 2, minH: 2 },
  { type: 'actuator-runtime', label: 'Aktor-Laufzeit', description: 'Laufzeitstatistik', iconName: 'BarChart3', category: 'Aktoren', w: 4, h: 3, minW: 3, minH: 3 },
  { type: 'esp-health', label: 'ESP-Health', description: 'Health-Metriken eines ESP32', iconName: 'Cpu', category: 'System', w: 6, h: 3, minW: 4, minH: 3 },
  { type: 'alarm-list', label: 'Alarm-Liste', description: 'Aktive und vergangene Alarme', iconName: 'Bell', category: 'System', w: 4, h: 4, minW: 4, minH: 4 },
]

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
