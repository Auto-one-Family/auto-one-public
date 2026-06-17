<script setup lang="ts">
/**
 * QuickActionBall — Floating Action Button (FAB) for Quick Actions.
 *
 * Position: fixed, bottom-right, z-index: var(--z-fab)
 * Size: 44px (subtle, professional IoT dashboard)
 * Styling: Glassmorphism via design tokens
 *
 * Features:
 * - Context-dependent actions per view (via useQuickActions)
 * - Alert badge from notification-inbox.store
 * - Hover: scale(1.08) with overshoot easing
 * - Click: expand to QuickActionMenu
 * - Hidden on login page; in editor mode hidden on viewport < 768px
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useQuickActionStore } from '@/shared/stores/quickAction.store'
import { useQuickActions } from '@/composables/useQuickActions'
import { Zap, X } from 'lucide-vue-next'
import QuickActionMenu from './QuickActionMenu.vue'
import QuickAlertPanel from './QuickAlertPanel.vue'
import QuickNavPanel from './QuickNavPanel.vue'
import QuickWidgetPanel from './QuickWidgetPanel.vue'
import QuickDashboardPanel from './QuickDashboardPanel.vue'
import QuickActuatorPanel from './QuickActuatorPanel.vue'

interface Props {
  /** 'editor' = drag-to-grid (default), 'monitor' = click opens AddWidgetDialog */
  mode?: 'editor' | 'monitor'
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'editor',
})

const emit = defineEmits<{
  /** Forwarded from QuickWidgetPanel in monitor mode */
  'widget-selected': [widgetType: string]
}>()

const route = useRoute()
const store = useQuickActionStore()

// Initialize context-dependent actions (watches route changes)
useQuickActions()

// Sub-panel routing: which panel component to render
const activePanelComponent = computed(() => {
  switch (store.activePanel) {
    case 'alerts': return QuickAlertPanel
    case 'navigation': return QuickNavPanel
    case 'widgets': return QuickWidgetPanel
    case 'dashboards': return QuickDashboardPanel
    case 'actuator-toggle': return QuickActuatorPanel
    default: return QuickActionMenu
  }
})

// Click-away handling
const fabRef = ref<HTMLElement | null>(null)

function handleClickAway(e: MouseEvent) {
  if (store.isMenuOpen && fabRef.value && !fabRef.value.contains(e.target as Node)) {
    store.closeMenu()
  }
}

function handleEscape(e: KeyboardEvent) {
  if (e.key === 'Escape' && store.isMenuOpen) {
    store.closeMenu()
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickAway, true)
  document.addEventListener('keydown', handleEscape)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickAway, true)
  document.removeEventListener('keydown', handleEscape)
})
</script>

<template>
  <!-- FAB hidden on login/setup pages (route.meta.requiresAuth === false) -->
  <div
    v-if="route.meta.requiresAuth !== false"
    ref="fabRef"
    :class="['qa-fab', `qa-fab--${mode}`, { 'qa-fab--open': store.isMenuOpen }]"
  >
    <!-- Sub-Panel: Menu, Alerts, Navigation, or Widgets -->
    <Transition name="qa-menu-transition" mode="out-in">
      <component
        v-if="store.isMenuOpen"
        :is="activePanelComponent"
        :key="store.activePanel"
        v-bind="store.activePanel === 'widgets' ? { mode: props.mode } : {}"
        @widget-selected="(type: string) => emit('widget-selected', type)"
      />
    </Transition>

    <!-- FAB Button -->
    <button
      class="qa-fab__button"
      data-testid="quick-action-fab-toggle"
      :class="{
        'qa-fab__button--open': store.isMenuOpen,
        'qa-fab__button--critical': !store.isMenuOpen && store.isCritical,
        'qa-fab__button--warning': !store.isMenuOpen && store.isWarning && !store.isCritical,
      }"
      :aria-label="store.isMenuOpen ? 'Quick Actions schließen' : 'Quick Actions öffnen'"
      :aria-expanded="store.isMenuOpen"
      @click="store.toggleMenu()"
    >
      <!-- Icon: X when open, Zap when closed -->
      <Transition name="qa-icon-transition" mode="out-in">
        <X v-if="store.isMenuOpen" class="qa-fab__icon" />
        <Zap v-else class="qa-fab__icon" />
      </Transition>

      <!-- Alert Badge Dot (only when closed and alerts active) -->
      <span
        v-if="!store.isMenuOpen && store.hasActiveAlerts"
        class="qa-fab__alert-dot"
        :class="{
          'qa-fab__alert-dot--critical': store.isCritical,
          'qa-fab__alert-dot--warning': store.isWarning && !store.isCritical,
        }"
      />
    </button>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════════════════════════════
   QUICK ACTION BALL — Glassmorphism FAB
   ═══════════════════════════════════════════════════════════════════════════ */

.qa-fab {
  position: fixed;
  bottom: 20px;
  right: 20px;
  z-index: var(--z-fab);
}

/* In editor mode: hidden on mobile < 768px (drag workflow not suited for touch) */
@media (max-width: 767px) {
  .qa-fab--editor {
    display: none;
  }
}

/* ── FAB Button ── */

.qa-fab__button {
  position: relative;
  width: 44px;
  height: 44px;
  border-radius: var(--radius-full);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border: 1px solid var(--glass-border);
  background: rgba(20, 20, 30, 0.7);
  -webkit-backdrop-filter: blur(12px);
  backdrop-filter: blur(12px);
  box-shadow: var(--elevation-floating);
  color: var(--color-text-secondary);
  transition:
    transform var(--duration-base) var(--ease-spring),
    background var(--duration-base) var(--ease-out),
    border-color var(--duration-base) var(--ease-out),
    box-shadow var(--duration-base) var(--ease-out),
    color var(--duration-fast) var(--ease-out),
    -webkit-backdrop-filter var(--duration-base) var(--ease-out),
    backdrop-filter var(--duration-base) var(--ease-out);
}

.qa-fab__button:hover {
  transform: scale(1.08);
  -webkit-backdrop-filter: blur(16px);
  backdrop-filter: blur(16px);
  border-color: var(--glass-border-hover);
  color: var(--color-text-primary);
  box-shadow:
    var(--elevation-floating),
    0 0 20px rgba(96, 165, 250, 0.15);
}

.qa-fab__button:active {
  transform: scale(0.96);
}

/* Open state */
.qa-fab__button--open {
  background: rgba(20, 20, 30, 0.9);
  border-color: var(--glass-border-hover);
  color: var(--color-text-primary);
}

/* Critical alert state — subtle red glow */
.qa-fab__button--critical {
  border-color: rgba(248, 113, 113, 0.3);
  box-shadow:
    var(--elevation-floating),
    0 0 12px rgba(248, 113, 113, 0.2);
  animation: qa-pulse-critical 2.5s ease-in-out infinite;
}

/* Warning alert state — subtle amber glow */
.qa-fab__button--warning {
  border-color: rgba(251, 191, 36, 0.25);
  box-shadow:
    var(--elevation-floating),
    0 0 10px rgba(251, 191, 36, 0.15);
}

/* ── Icon ── */

.qa-fab__icon {
  width: 18px;
  height: 18px;
  pointer-events: none;
}

/* ── Alert Badge Dot ── */

.qa-fab__alert-dot {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  pointer-events: none;
}

.qa-fab__alert-dot--critical {
  background: var(--color-error);
  box-shadow: 0 0 6px rgba(248, 113, 113, 0.6);
  animation: qa-dot-pulse 1.5s ease-in-out infinite;
}

.qa-fab__alert-dot--warning {
  background: var(--color-warning);
  box-shadow: 0 0 4px rgba(251, 191, 36, 0.4);
  animation: qa-dot-pulse 2s ease-in-out infinite;
}

/* ═══ ANIMATIONS ═══════════════════════════════════════════════════════════ */

@keyframes qa-pulse-critical {
  0%, 100% {
    box-shadow:
      var(--elevation-floating),
      0 0 12px rgba(248, 113, 113, 0.2);
  }
  50% {
    box-shadow:
      var(--elevation-floating),
      0 0 20px rgba(248, 113, 113, 0.35);
  }
}

@keyframes qa-dot-pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.7;
    transform: scale(1.3);
  }
}

/* ═══ TRANSITIONS ═══════════════════════════════════════════════════════════ */

/* Menu expand/collapse */
.qa-menu-transition-enter-active {
  transition: all var(--duration-base) var(--ease-out);
}

.qa-menu-transition-leave-active {
  transition: all var(--duration-fast) var(--ease-in-out);
}

.qa-menu-transition-enter-from {
  opacity: 0;
  transform: scale(0.9) translateY(8px);
}

.qa-menu-transition-leave-to {
  opacity: 0;
  transform: scale(0.95) translateY(4px);
}

/* Icon swap */
.qa-icon-transition-enter-active,
.qa-icon-transition-leave-active {
  transition: all var(--duration-fast) var(--ease-out);
}

.qa-icon-transition-enter-from {
  opacity: 0;
  transform: rotate(-90deg) scale(0.6);
}

.qa-icon-transition-leave-to {
  opacity: 0;
  transform: rotate(90deg) scale(0.6);
}

/* ═══ REDUCED MOTION ═══════════════════════════════════════════════════════ */

@media (prefers-reduced-motion: reduce) {
  .qa-fab__button {
    transition: none;
  }

  .qa-fab__button--critical,
  .qa-fab__alert-dot--critical,
  .qa-fab__alert-dot--warning {
    animation: none;
  }
}
</style>
