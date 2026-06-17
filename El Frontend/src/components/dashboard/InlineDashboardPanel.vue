<script setup lang="ts">
/**
 * InlineDashboardPanel — CSS-Grid-Only Dashboard Renderer
 *
 * Renders dashboard widgets in a 12-column CSS grid (NO GridStack).
 * Zero overhead: no drag/resize listeners, no external library.
 * Used for inline/side-panel dashboard embedding in Monitor/Hardware views.
 *
 * Mode system (D4):
 * - 'view': Read-only, no toolbar (guests, readonly previews, zone-tile mini widgets)
 * - 'manage': Read-only + hover toolbar for widget config/remove (authenticated users)
 * - 'side-panel': Side panel layout (single column stacking)
 *
 * Block 7c: El Frontend/src/components/dashboard/InlineDashboardPanel.vue
 */
import { onMounted, onUnmounted, onActivated, onDeactivated, computed, nextTick, watch, toRef, ref, getCurrentInstance } from 'vue'
import { RouterLink } from 'vue-router'
import { Pencil, Settings, Trash2 } from 'lucide-vue-next'
import { useDashboardStore, type DashboardWidget } from '@/shared/stores/dashboard.store'
import { useAuthStore } from '@/shared/stores/auth.store'
import { useUiStore } from '@/shared/stores/ui.store'
import { useDashboardWidgets } from '@/composables/useDashboardWidgets'
import WidgetConfigPanel from '@/components/dashboard-widgets/WidgetConfigPanel.vue'
import { createLogger } from '@/utils/logger'
import { getZoneTileRenderableWidgets } from '@/utils/zoneTileWidgets'

const logger = createLogger('InlineDashboardPanel')

interface Props {
  layoutId: string
  mode?: 'view' | 'manage' | 'side-panel'
  /** Zone ID for zone-scoped sensor filtering in widgets (PA-02c) */
  zoneId?: string
  /** Compact mode: hide header, reduced padding (L1 zone-tile; Editor-Stift in ZoneTileCard) */
  compact?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'view',
  compact: false,
})
const componentUid = getCurrentInstance()?.uid ?? Math.floor(Math.random() * 1_000_000)

const dashStore = useDashboardStore()
const authStore = useAuthStore()
const uiStore = useUiStore()

const zoneIdRef = toRef(props, 'zoneId')
const compactTileGaugeSemantics = toRef(props, 'compact')

const { createWidgetElement, mountWidgetToElement, cleanupAllWidgets, widgetComponentMap } = useDashboardWidgets({
  showConfigButton: false,
  showWidgetHeader: false,
  readOnly: true,
  zoneId: zoneIdRef as import('vue').Ref<string | undefined>,
  compactTileGaugeSemantics,
})

/** Row height in pixels — synchronized with CustomDashboardView/DashboardViewer cellHeight */
const ROW_HEIGHT_INLINE = 80
const ROW_HEIGHT_SIDE = 120

const isSidePanel = computed(() => props.mode === 'side-panel')
const isManageMode = computed(() => props.mode === 'manage' && authStore.isAuthenticated)
const ROW_HEIGHT_COMPACT = 70
const rowHeightPx = computed(() => {
  if (props.compact) return `${ROW_HEIGHT_COMPACT}px`
  if (isSidePanel.value) return `${ROW_HEIGHT_SIDE}px`
  return `${ROW_HEIGHT_INLINE}px`
})

const layout = computed(() =>
  dashStore.getLayoutById(props.layoutId)
)

const allWidgets = computed(() => layout.value?.widgets ?? [])

const widgets = computed(() => {
  if (!props.compact) return allWidgets.value
  return getZoneTileRenderableWidgets(allWidgets.value)
})

const editorRoute = computed(() => ({
  name: 'editor-dashboard' as const,
  params: { dashboardId: layout.value?.serverId || props.layoutId },
}))

// ── Manage Mode: Hover Toolbar & Config (D4) ──

const hoveredWidgetId = ref<string | null>(null)
const configWidget = ref<DashboardWidget | null>(null)

function openConfig(w: DashboardWidget): void {
  configWidget.value = w
}

function closeConfig(): void {
  configWidget.value = null
}

type WidgetDataDensity = 'none' | 'low' | 'medium' | 'high'

function splitConfigIds(value: unknown): string[] {
  if (typeof value !== 'string') return []
  return value.split(',').map(part => part.trim()).filter(Boolean)
}

/**
 * Compact mode row-span should reflect how much content a widget can actually render.
 * This avoids oversized empty cards while still giving dense charts enough space.
 */
function getWidgetDataDensity(w: DashboardWidget): WidgetDataDensity {
  const cfg = (w.config ?? {}) as Record<string, unknown>

  if (w.type === 'line-chart' || w.type === 'historical' || w.type === 'statistics') {
    return typeof cfg['sensorId'] === 'string' && cfg['sensorId'].trim() !== '' ? 'medium' : 'none'
  }

  if (w.type === 'fertigation-pair') {
    const hasInflow = typeof cfg['inflowSensorId'] === 'string' && cfg['inflowSensorId'].trim() !== ''
    const hasRunoff = typeof cfg['runoffSensorId'] === 'string' && cfg['runoffSensorId'].trim() !== ''
    if (!hasInflow && !hasRunoff) return 'none'
    return hasInflow && hasRunoff ? 'high' : 'low'
  }

  if (w.type === 'multi-sensor') {
    const sensors = splitConfigIds(cfg['dataSources'])
    const actuators = splitConfigIds(cfg['actuatorIds'])
    const signalCount = sensors.length + actuators.length
    if (signalCount === 0) return 'none'
    if (signalCount <= 2) return 'low'
    if (signalCount <= 4) return 'medium'
    return 'high'
  }

  return 'low'
}

function handleConfigUpdate(newConfig: Record<string, any>): void {
  if (!configWidget.value) return
  dashStore.updateWidgetConfig(props.layoutId, configWidget.value.id, newConfig)
}

async function confirmRemove(w: DashboardWidget): Promise<void> {
  const confirmed = await uiStore.confirm({
    title: 'Widget entfernen',
    message: 'Dieses Widget wird aus dem Dashboard entfernt.',
    confirmText: 'Entfernen',
    variant: 'danger',
  })
  if (confirmed) {
    dashStore.removeWidget(props.layoutId, w.id)
  }
}

// ── Widget Style & Mounting ──

/**
 * Calculate grid cell style from widget position.
 * Side-panel mode: single column, widgets stacked vertically (ignore x/w).
 * View / manage mode: full 12-column grid with original positions.
 */
function compactRowSpan(w: DashboardWidget): number {
  if (w.type === 'gauge' || w.type === 'sensor-card') return 1
  if (w.type === 'actuator-card') return 1

  if (
    w.type === 'line-chart' ||
    w.type === 'historical' ||
    w.type === 'statistics' ||
    w.type === 'fertigation-pair' ||
    w.type === 'multi-sensor'
  ) {
    const density = getWidgetDataDensity(w)
    if (density === 'none') return 1

    const isSingleWidgetPanel = widgets.value.length === 1
    const baseSpan = (() => {
      if (density === 'low') return 2
      if (density === 'high') return 3
      return 2
    })()

    return isSingleWidgetPanel ? Math.min(baseSpan + 1, 4) : baseSpan
  }
  return 1
}

function widgetStyle(w: DashboardWidget): Record<string, string> {
  if (props.compact) {
    return {
      'grid-column': '1 / -1',
      'grid-row': `span ${compactRowSpan(w)}`,
    }
  }

  if (isSidePanel.value) {
    // Stack vertically — each widget spans full width, height from original h
    const minH = Math.max(w.h, 2)
    return {
      'grid-column': '1 / -1',
      'grid-row': `span ${minH}`,
    }
  }
  return {
    'grid-column': `${w.x + 1} / span ${w.w}`,
    'grid-row': `${w.y + 1} / span ${w.h}`,
  }
}

/** Check if a widget type has a registered Vue component */
function isKnownWidgetType(type: string): boolean {
  return type in widgetComponentMap
}

/** Mount all widgets into their DOM containers */
function mountWidgets() {
  cleanupAllWidgets()

  nextTick(() => {
    if (!isMounted) return
    for (const w of widgets.value) {
      if (!isKnownWidgetType(w.type)) {
        logger.warn(`Unknown widget type "${w.type}" — skipping render`)
        continue
      }

      const containerId = getContainerId(w.id)
      const container = document.getElementById(containerId)
      if (!container) continue

      // Clear previous DOM to prevent element accumulation on re-mount
      container.innerHTML = ''

      // Use distinct mount ID to avoid duplicate IDs (container already has containerId)
      const vmMountId = `vm-${containerId}`
      const el = createWidgetElement(w.type, w.config?.title || '', w.id, vmMountId)
      container.appendChild(el)
      mountWidgetToElement(w.id, vmMountId, w.type, w.config || {})
    }
  })
}

/** Instance-scoped mount container ID (prevents duplicate IDs across kept-alive views) */
function getContainerId(widgetId: string): string {
  return `inline-${componentUid}-${props.layoutId}-${widgetId}`
}

watch(
  () => `${widgets.value.map(w => w.id).join(',')}|${props.compact ? '1' : '0'}`,
  () => mountWidgets(),
)

onMounted(() => {
  if (widgets.value.length > 0) mountWidgets()
})

// Keep-alive re-entry: force remount to restore manual Vue mounts after tab switches.
onActivated(() => {
  if (widgets.value.length > 0) mountWidgets()
})

// Keep-alive leave: unmount all widget roots to avoid stale mounts.
onDeactivated(() => {
  cleanupAllWidgets()
})

let isMounted = true
onUnmounted(() => {
  isMounted = false
  cleanupAllWidgets()
})
</script>

<template>
  <div
    v-if="layout && widgets.length > 0"
    :class="['inline-dashboard', `inline-dashboard--${mode}`, { 'inline-dashboard--compact': compact }]"
  >
    <!-- Header (hidden in compact mode to avoid nested interactive elements) -->
    <div v-if="!compact" class="inline-dashboard__header">
      <span class="inline-dashboard__name">{{ layout.name }}</span>
      <RouterLink :to="editorRoute" class="inline-dashboard__edit-link" title="Im Editor bearbeiten">
        <Pencil :size="14" />
      </RouterLink>
    </div>

    <!-- CSS Grid -->
    <div class="inline-dashboard__grid">
      <div
        v-for="w in widgets"
        :key="w.id"
        class="inline-dashboard__cell"
        :style="widgetStyle(w)"
        @mouseenter="hoveredWidgetId = w.id"
        @mouseleave="hoveredWidgetId = null"
      >
        <!-- Manage toolbar: hover on desktop, always visible on touch (D4) -->
        <div
          v-if="isManageMode"
          :class="['widget-toolbar', { 'widget-toolbar--visible': hoveredWidgetId === w.id }]"
        >
          <button
            class="widget-toolbar__btn"
            title="Konfigurieren"
            @click.stop="openConfig(w)"
          >
            <Settings :size="14" />
          </button>
          <button
            class="widget-toolbar__btn widget-toolbar__btn--danger"
            title="Entfernen"
            @click.stop="confirmRemove(w)"
          >
            <Trash2 :size="14" />
          </button>
        </div>

        <div v-if="isKnownWidgetType(w.type)" :id="getContainerId(w.id)" class="inline-dashboard__mount" />
        <div v-else class="inline-dashboard__unknown">
          <span>{{ w.type }}</span>
        </div>
      </div>
    </div>

    <!-- Widget Config Panel (SlideOver, reused 1:1 from editor — D4) -->
    <WidgetConfigPanel
      v-if="configWidget"
      :open="!!configWidget"
      :widget-id="configWidget.id"
      :widget-type="configWidget.type"
      :config="configWidget.config || {}"
      :zone-id="zoneId"
      @close="closeConfig"
      @update:config="handleConfigUpdate"
    />
  </div>
</template>

<style scoped>
.inline-dashboard {
  border: 1px solid var(--color-border, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-md, 10px);
  background: var(--color-bg-secondary);
  overflow: hidden;
}

.inline-dashboard--side-panel {
  border-radius: 0;
  border-left: 1px solid var(--color-border, rgba(255, 255, 255, 0.08));
  border-right: none;
  border-top: none;
  border-bottom: none;
  height: 100%;
}

.inline-dashboard__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border, rgba(255, 255, 255, 0.08));
  background: var(--color-bg-tertiary);
}

.inline-dashboard__name {
  font-size: var(--text-sm, 13px);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.inline-dashboard__edit-link {
  color: var(--color-text-muted);
  transition: color var(--transition-fast, 150ms);
}

.inline-dashboard__edit-link:hover {
  color: var(--color-iridescent-1);
}

.inline-dashboard__grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  grid-auto-rows: v-bind(rowHeightPx);
  gap: var(--space-1);
  padding: var(--space-2);
}

.inline-dashboard--side-panel .inline-dashboard__grid {
  grid-template-columns: 1fr;
  grid-auto-rows: v-bind(rowHeightPx);
  gap: var(--space-2);
}

.inline-dashboard__cell {
  position: relative;
  min-width: 0;
  overflow: hidden;
  border-radius: var(--radius-sm, 6px);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-border, rgba(255, 255, 255, 0.06));
}

.inline-dashboard__mount {
  width: 100%;
  height: 100%;
  overflow: hidden;
}

/* Widget shell fills mount container — no outer header, direct widget content */
.inline-dashboard__mount :deep(.dashboard-widget) {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.inline-dashboard__mount :deep(.dashboard-widget__vue-mount) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.inline-dashboard__unknown {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: var(--color-text-muted);
  font-size: var(--text-xs, 11px);
  font-style: italic;
  opacity: 0.6;
}

/* Compact mode: reduced padding, no border, constrained height (Phase 3 mini-widgets) */
.inline-dashboard--compact {
  border: none;
  background: transparent;
}

.inline-dashboard--compact .inline-dashboard__grid {
  grid-template-columns: 1fr;
  padding: 0;
  gap: var(--space-2);
}

.inline-dashboard--compact .inline-dashboard__cell {
  overflow: hidden;
}

/* ── Manage Mode: Widget Hover Toolbar (D4) ── */

.widget-toolbar {
  position: absolute;
  top: var(--space-1, 4px);
  right: var(--space-1, 4px);
  z-index: var(--z-dropdown);
  display: flex;
  gap: 8px;
  padding: 2px;
  background: rgba(30, 30, 45, 0.75);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  border-radius: var(--radius-sm, 6px);
  border: 1px solid var(--glass-border, rgba(255, 255, 255, 0.06));
  opacity: 0;
  transition: opacity var(--transition-fast, 150ms);
  pointer-events: none;
}

.widget-toolbar--visible {
  opacity: 1;
  pointer-events: auto;
}

/* Touch devices: always show toolbar */
@media (hover: none) {
  .widget-toolbar {
    opacity: 1;
    pointer-events: auto;
  }
}

.widget-toolbar__btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  border-radius: var(--radius-sm, 6px);
  transition: all var(--transition-fast, 150ms);
  padding: 0;
}

.widget-toolbar__btn:hover {
  background: var(--glass-bg-light, rgba(255, 255, 255, 0.04));
  color: var(--color-text-primary);
}

.widget-toolbar__btn--danger:hover {
  color: var(--color-error);
}

.widget-toolbar__btn:focus-visible {
  outline: 2px solid var(--color-iridescent-2);
  outline-offset: 1px;
}

/* Touch: enlarge touch targets to 44px (WCAG) */
@media (hover: none) {
  .widget-toolbar__btn {
    min-width: 44px;
    min-height: 44px;
  }
}
</style>
