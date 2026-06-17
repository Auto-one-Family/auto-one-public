<script setup lang="ts">
/**
 * QuickWidgetPanel — Widget catalog sub-panel in the FAB.
 *
 * Shows all 9 widget types grouped by category (Sensoren, Aktoren, System).
 * Each item is draggable (HTML5 DnD) or activatable via keyboard (Space/Enter).
 * Drag closes the FAB menu so the user can see the GridStack editor.
 *
 * On non-editor routes: shows hint to navigate to the editor.
 * Monitor mode: click emits 'widget-selected' instead of drag (D3).
 */

import { computed, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft,
  LayoutGrid,
  GripVertical,
  BarChart3,
  Gauge,
  Activity,
  Zap,
  Bell,
  Cpu,
} from 'lucide-vue-next'
import { useQuickActionStore } from '@/shared/stores/quickAction.store'
import { useWidgetDragFromFab } from '@/composables/useWidgetDragFromFab'
import type { WidgetDragItem } from '@/composables/useWidgetDragFromFab'

interface Props {
  /** 'editor' = drag-to-grid (default), 'monitor' = click opens AddWidgetDialog */
  mode?: 'editor' | 'monitor'
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'editor',
})

const emit = defineEmits<{
  /** Emitted in monitor mode when a widget type is clicked */
  'widget-selected': [widgetType: string]
}>()

const ICON_MAP: Record<string, Component> = {
  BarChart3,
  Gauge,
  Activity,
  Zap,
  Bell,
  Cpu,
}

const route = useRoute()
const router = useRouter()
const quickActionStore = useQuickActionStore()
const {
  groupedWidgetItems,
  handleDragStart,
  handleDragEnd,
  announceWidget,
  announcedWidget,
} = useWidgetDragFromFab()

const isOnEditor = computed(() => route.path.startsWith('/editor'))
const isMonitorMode = computed(() => props.mode === 'monitor')

/** Show the catalog when on editor OR in monitor mode */
const showCatalog = computed(() => isOnEditor.value || isMonitorMode.value)

function handleBack(): void {
  quickActionStore.setActivePanel('menu')
}

function handleKeyAction(event: KeyboardEvent, item: WidgetDragItem): void {
  if (event.key === ' ' || event.key === 'Enter') {
    event.preventDefault()
    if (isMonitorMode.value) {
      handleMonitorSelect(item)
    } else {
      announceWidget(item)
    }
  }
}

/** In monitor mode: emit selected widget type and close FAB */
function handleMonitorSelect(item: WidgetDragItem): void {
  emit('widget-selected', item.type)
  quickActionStore.closeMenu()
}

function navigateToEditor(): void {
  void router.push('/editor')
  quickActionStore.closeMenu()
}
</script>

<template>
  <div class="qa-widget-panel" role="region" aria-label="Widget-Katalog">
    <!-- Header -->
    <div class="qa-widget-panel__header">
      <button
        class="qa-widget-panel__back"
        aria-label="Zurueck zum Menu"
        @click="handleBack"
      >
        <ArrowLeft class="qa-widget-panel__back-icon" />
      </button>
      <LayoutGrid class="qa-widget-panel__header-icon" />
      <span class="qa-widget-panel__title">Widgets</span>
    </div>

    <!-- Not-on-editor hint (only when not in monitor mode and not on editor) -->
    <div v-if="!showCatalog" class="qa-widget-panel__hint">
      <p class="qa-widget-panel__hint-text">
        Wechsle zum Dashboard Editor um Widgets per Drag &amp; Drop zu platzieren.
      </p>
      <button
        class="qa-widget-panel__hint-link"
        @click="navigateToEditor"
      >
        Zum Editor
      </button>
    </div>

    <!-- Widget Catalog (grouped by category) -->
    <div v-else class="qa-widget-panel__catalog">
      <div
        v-for="(items, category) in groupedWidgetItems"
        :key="category"
        class="qa-widget-panel__group"
      >
        <span class="qa-widget-panel__group-label">{{ category }}</span>
        <div class="qa-widget-panel__items">
          <div
            v-for="item in items"
            :key="item.type"
            class="qa-widget-panel__item"
            :class="{
              'qa-widget-panel__item--announced': announcedWidget?.type === item.type,
              'qa-widget-panel__item--clickable': isMonitorMode,
            }"
            :draggable="!isMonitorMode"
            role="button"
            :aria-label="isMonitorMode
              ? `${item.label} — ${item.description}. Klicken zum Hinzufuegen.`
              : `${item.label} — ${item.description}. Ziehen oder Enter zum Platzieren.`"
            tabindex="0"
            @dragstart="!isMonitorMode && handleDragStart($event, item)"
            @dragend="!isMonitorMode && handleDragEnd()"
            @click="isMonitorMode && handleMonitorSelect(item)"
            @keydown="handleKeyAction($event, item)"
          >
            <component
              :is="ICON_MAP[item.iconName] || BarChart3"
              class="qa-widget-panel__item-icon"
            />
            <div class="qa-widget-panel__item-text">
              <span class="qa-widget-panel__item-label">{{ item.label }}</span>
              <span class="qa-widget-panel__item-desc">{{ item.description }}</span>
            </div>
            <GripVertical v-if="!isMonitorMode" class="qa-widget-panel__grip" aria-hidden="true" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════════════════════════════
   QUICK WIDGET PANEL — Widget catalog sub-panel
   ═══════════════════════════════════════════════════════════════════════════ */

.qa-widget-panel {
  position: absolute;
  bottom: calc(100% + var(--space-2));
  right: 0;
  width: 280px;
  max-height: 420px;
  display: flex;
  flex-direction: column;
  background: rgba(20, 20, 30, 0.92);
  -webkit-backdrop-filter: blur(16px);
  backdrop-filter: blur(16px);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--elevation-floating);
  overflow: hidden;
}

/* ── Header ── */

.qa-widget-panel__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.qa-widget-panel__back {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: var(--radius-sm);
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.qa-widget-panel__back:hover {
  background: rgba(255, 255, 255, 0.08);
  color: var(--color-text-primary);
}

.qa-widget-panel__back-icon {
  width: 14px;
  height: 14px;
}

.qa-widget-panel__header-icon {
  width: 16px;
  height: 16px;
  color: var(--color-accent);
}

.qa-widget-panel__title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  flex: 1;
}

/* ── Hint (non-editor) ── */

.qa-widget-panel__hint {
  padding: var(--space-4);
  text-align: center;
}

.qa-widget-panel__hint-text {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  line-height: 1.5;
  margin: 0 0 var(--space-3);
}

.qa-widget-panel__hint-link {
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-accent);
  background: rgba(96, 165, 250, 0.1);
  border: 1px solid rgba(96, 165, 250, 0.2);
  border-radius: var(--radius-sm);
  padding: var(--space-1) var(--space-3);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.qa-widget-panel__hint-link:hover {
  background: rgba(96, 165, 250, 0.2);
  border-color: rgba(96, 165, 250, 0.3);
}

/* ── Catalog ── */

.qa-widget-panel__catalog {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-1);
}

/* ── Group ── */

.qa-widget-panel__group {
  margin-bottom: var(--space-1);
}

.qa-widget-panel__group-label {
  display: block;
  font-size: var(--text-xxs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
  opacity: 0.6;
  padding: var(--space-2) var(--space-2) var(--space-1);
}

/* ── Widget Item ── */

.qa-widget-panel__item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2);
  border-radius: var(--radius-sm);
  cursor: grab;
  transition: background var(--transition-fast);
  user-select: none;
}

.qa-widget-panel__item:hover {
  background: rgba(255, 255, 255, 0.06);
}

.qa-widget-panel__item:active {
  cursor: grabbing;
}

.qa-widget-panel__item--clickable {
  cursor: pointer;
}

.qa-widget-panel__item--clickable:active {
  cursor: pointer;
}

.qa-widget-panel__item:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: -2px;
}

.qa-widget-panel__item--announced {
  background: rgba(96, 165, 250, 0.12);
  outline: 1px solid rgba(96, 165, 250, 0.3);
}

.qa-widget-panel__item-icon {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  color: var(--color-iridescent-2);
}

.qa-widget-panel__item-text {
  flex: 1;
  min-width: 0;
}

.qa-widget-panel__item-label {
  display: block;
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.qa-widget-panel__item-desc {
  display: block;
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.qa-widget-panel__grip {
  flex-shrink: 0;
  width: 14px;
  height: 14px;
  color: var(--color-text-muted);
  opacity: 0.3;
  transition: opacity var(--transition-fast);
}

.qa-widget-panel__item:hover .qa-widget-panel__grip {
  opacity: 0.6;
}

/* ═══ REDUCED MOTION ═══════════════════════════════════════════════════════ */

@media (prefers-reduced-motion: reduce) {
  .qa-widget-panel__item,
  .qa-widget-panel__back,
  .qa-widget-panel__hint-link {
    transition: none;
  }
}
</style>
