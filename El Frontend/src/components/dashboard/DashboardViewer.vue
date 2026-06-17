<script setup lang="ts">
/**
 * DashboardViewer — View-Only Dashboard Rendering
 *
 * Renders a dashboard layout in STATIC mode (no drag, no resize, no config).
 * Used inside MonitorView for L3 dashboard display.
 *
 * Uses GridStack with staticGrid: true (no event listener overhead).
 * Widget rendering via useDashboardWidgets composable (container-agnostic).
 */

import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { GridStack } from 'gridstack'
import 'gridstack/dist/gridstack.min.css'
import { Pencil, ArrowLeft } from 'lucide-vue-next'
import { useDashboardStore } from '@/shared/stores/dashboard.store'
import { useDashboardWidgets } from '@/composables/useDashboardWidgets'

// Props
interface Props {
  layoutId: string
  showHeader?: boolean
}
const props = withDefaults(defineProps<Props>(), {
  showHeader: true,
})

const router = useRouter()
const dashStore = useDashboardStore()

// Widget rendering via shared composable (no config button in viewer)
const {
  createWidgetElement,
  mountWidgetToElement,
  cleanupAllWidgets,
} = useDashboardWidgets({
  showConfigButton: false,
})

// GridStack instance
let grid: GridStack | null = null
const gridContainer = ref<HTMLElement | null>(null)

// Resolved layout (match by local ID or server UUID for deep-link robustness)
const layout = computed(() =>
  dashStore.getLayoutById(props.layoutId) ?? null
)

// ─── GridStack Init ─────────────────────────────────────────────────────────

function initGrid() {
  if (!gridContainer.value || grid) return

  grid = GridStack.init({
    column: 12,
    cellHeight: 80,
    margin: 8,
    float: true,
    animate: true,
    staticGrid: true,
    disableDrag: true,
    disableResize: true,
    removable: false,
  }, gridContainer.value)
}

function loadWidgets() {
  if (!grid || !layout.value) return

  // Clean previous widgets
  cleanupAllWidgets()
  grid.removeAll(false)

  for (const widget of layout.value.widgets) {
    const mountId = `viewer-mount-${widget.id}`

    const itemEl = grid.addWidget({
      x: widget.x,
      y: widget.y,
      w: widget.w,
      h: widget.h,
      noMove: true,
      noResize: true,
      id: widget.id,
    })

    // Inject widget DOM and mount Vue component after GridStack has created the cell
    nextTick(() => {
      const contentDiv = itemEl.querySelector('.grid-stack-item-content')
      contentDiv?.appendChild(createWidgetElement(widget.type, widget.config?.title || '', widget.id, mountId))
      mountWidgetToElement(widget.id, mountId, widget.type, widget.config || {})
    })
  }
}

// ─── Lifecycle ──────────────────────────────────────────────────────────────

onMounted(async () => {
  await nextTick()
  initGrid()
  loadWidgets()
})

onUnmounted(() => {
  // 1. Unmount all widget Vue components
  cleanupAllWidgets()
  // 2. Destroy GridStack (false = don't remove DOM elements, Vue handles cleanup)
  if (grid) {
    grid.destroy(false)
    grid = null
  }
})

// Watch for layout changes (e.g. reactive updates from store)
watch(() => layout.value?.updatedAt, () => {
  if (grid && layout.value) {
    loadWidgets()
  }
})

// ─── Actions ────────────────────────────────────────────────────────────────

function goBack() {
  router.back()
}


</script>

<template>
  <div class="dashboard-viewer">
    <!-- Header -->
    <div v-if="showHeader" class="dashboard-viewer__header">
      <button class="dashboard-viewer__back" @click="goBack">
        <ArrowLeft class="w-4 h-4" />
        <span>Zurück</span>
      </button>

      <div class="dashboard-viewer__title-wrap">
        <h2 class="dashboard-viewer__title">{{ layout?.name || 'Dashboard' }}</h2>
        <span class="dashboard-viewer__widget-count">
          {{ layout?.widgets.length || 0 }} Widgets
        </span>
      </div>

      <router-link
        v-if="layout"
        :to="{ name: 'editor-dashboard', params: { dashboardId: layout.id } }"
        class="dashboard-viewer__edit-btn"
      >
        <Pencil class="w-4 h-4" />
        <span>Im Editor bearbeiten</span>
      </router-link>
    </div>

    <!-- Empty State -->
    <div v-if="!layout" class="dashboard-viewer__empty">
      <p>Dashboard „{{ layoutId }}" nicht gefunden.</p>
      <router-link :to="{ name: 'monitor' }" class="dashboard-viewer__back-btn">
        Zurück zum Monitor
      </router-link>
    </div>

    <!-- GridStack Container (static mode) -->
    <div v-else ref="gridContainer" class="grid-stack dashboard-viewer__grid" />
  </div>
</template>

<style scoped>
.dashboard-viewer {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.dashboard-viewer__header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.dashboard-viewer__back {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.dashboard-viewer__back:hover {
  color: var(--color-text-primary);
  border-color: var(--glass-border-hover);
}

.dashboard-viewer__title-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.dashboard-viewer__title {
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0;
}

.dashboard-viewer__widget-count {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.dashboard-viewer__edit-btn {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-iridescent-2);
  font-size: var(--text-sm);
  font-weight: 500;
  text-decoration: none;
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.dashboard-viewer__edit-btn:hover {
  border-color: var(--color-iridescent-2);
  background: rgba(129, 140, 248, 0.06);
}

/* Empty State */
.dashboard-viewer__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-12);
  text-align: center;
  color: var(--color-text-muted);
}

.dashboard-viewer__back-btn {
  padding: var(--space-2) var(--space-4);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.dashboard-viewer__back-btn:hover {
  border-color: var(--glass-border-hover);
  color: var(--color-text-primary);
}

/* GridStack overrides for viewer (static mode) */
.dashboard-viewer__grid {
  min-height: 200px;
}

.dashboard-viewer__grid :deep(.grid-stack-item) {
  cursor: default;
}

.dashboard-viewer__grid :deep(.grid-stack-item-content) {
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}

/* Hide gear button (should not be rendered, but safety net) */
.dashboard-viewer__grid :deep(.dashboard-widget__gear-btn) {
  display: none;
}

/* Widget type badge hidden in viewer mode */
.dashboard-viewer__grid :deep(.dashboard-widget__type) {
  display: none;
}
</style>
