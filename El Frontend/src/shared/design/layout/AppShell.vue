<script setup lang="ts">
/**
 * AppShell — Mission Control Layout Container
 *
 * Full viewport shell with full-width header, fixed sidebar below header,
 * and scrollable content area. All dimensions driven by design tokens.
 */

import { ref, onMounted, onUnmounted } from 'vue'
import { RouterView, useRouter } from 'vue-router'
import { Menu } from 'lucide-vue-next'
import AppSidebar from './Sidebar.vue'
import QuickActionBall from '@/components/quick-action/QuickActionBall.vue'
import PendingDevicesPanel from '@/components/esp/PendingDevicesPanel.vue'
import { useUiStore } from '@/shared/stores'
import { useDashboardStore } from '@/shared/stores/dashboard.store'
import { useKeyboardShortcuts } from '@/composables'
import { useEdgeSwipe } from '@/composables/useSwipeNavigation'
import type { ESPDevice } from '@/api/esp'

const uiStore = useUiStore()
const dashStore = useDashboardStore()
const router = useRouter()

function handlePendingPanelOpenEspConfig(device: ESPDevice): void {
  dashStore.showPendingPanel = false
  void router.push({ name: 'hardware', query: { openSettings: device.device_id } })
}
const { register } = useKeyboardShortcuts()

// Mobile sidebar state — opened via hamburger button or left-edge swipe
const sidebarOpen = ref(false)

function openSidebar() {
  sidebarOpen.value = true
}

function closeSidebar() {
  sidebarOpen.value = false
}

// Swipe right from left screen edge → open sidebar (mobile/tablet)
useEdgeSwipe(openSidebar)

// ── Global Keyboard Shortcuts ──
const unregisterFns: Array<() => void> = []

onMounted(() => {
  // Ctrl+K → Command Palette toggle
  unregisterFns.push(register({
    key: 'k',
    ctrl: true,
    handler: (e) => {
      e.preventDefault()
      uiStore.toggleCommandPalette()
    },
    description: 'Command Palette öffnen',
    scope: 'global',
  }))

  // Escape → Close topmost overlay
  unregisterFns.push(register({
    key: 'Escape',
    handler: (e) => {
      const closed = uiStore.closeTopModal()
      if (closed) {
        e.preventDefault()
        e.stopPropagation()
      }
    },
    description: 'Overlay schließen',
    scope: 'global',
  }))
})

onUnmounted(() => {
  unregisterFns.forEach(fn => fn())
})
</script>

<template>
  <div class="shell">
    <!-- Mobile top bar — hamburger only, pushes content down (hidden on md+) -->
    <div class="shell__mobile-bar">
      <button
        class="shell__menu-toggle"
        aria-label="Navigation öffnen"
        @click="openSidebar"
      >
        <Menu class="shell__menu-icon" />
      </button>
    </div>

    <!-- Mobile Overlay (behind sidebar, above content) -->
    <Transition name="overlay">
      <div
        v-if="sidebarOpen"
        class="shell__overlay"
        @click="closeSidebar"
      />
    </Transition>

    <!-- Body: sidebar (fixed) + scrollable content -->
    <div class="shell__body">
      <AppSidebar
        :is-open="sidebarOpen"
        @close="closeSidebar"
      />

      <!-- Page Content — scrollable -->
      <main class="shell__content">
        <RouterView v-slot="{ Component }">
          <keep-alive :include="['MonitorView', 'LogicView', 'CustomDashboardView']" :max="5">
            <component :is="Component" />
          </keep-alive>
        </RouterView>
      </main>
    </div>

    <!-- Quick Action Ball (FAB) — global, bottom-right -->
    <QuickActionBall />

    <!-- Geraete / Wartend — global, funktioniert auf allen Routen -->
    <PendingDevicesPanel
      v-model:is-open="dashStore.showPendingPanel"
      @close="dashStore.showPendingPanel = false"
      @open-esp-config="handlePendingPanelOpenEspConfig"
    />
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════════════════════════════
   APP SHELL — Full viewport layout: header full-width, sidebar + content below
   ═══════════════════════════════════════════════════════════════════════════ */

.shell {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: var(--color-bg-primary);
  overflow: hidden;
}

/* Mobile top bar — flex row, visible only below md */
.shell__mobile-bar {
  flex-shrink: 0;
  height: 48px;
  display: flex;
  align-items: center;
  padding: 0 var(--space-3);
  background: var(--color-bg-secondary);
  border-bottom: 1px solid var(--glass-border);
}

@media (min-width: 768px) {
  .shell__mobile-bar {
    display: none;
  }
}

/* Hamburger button inside mobile bar */
.shell__menu-toggle {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 1px solid var(--glass-border);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.shell__menu-toggle:hover {
  color: var(--color-text-primary);
  border-color: var(--glass-border-hover);
  background: rgba(255, 255, 255, 0.04);
}

.shell__menu-icon {
  width: 18px;
  height: 18px;
  pointer-events: none;
}

/* Mobile overlay with blur */
.shell__overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(7, 7, 13, 0.6);
  -webkit-backdrop-filter: blur(4px);
  backdrop-filter: blur(4px);
  z-index: var(--z-fixed);
}

@media (min-width: 768px) {
  .shell__overlay {
    display: none;
  }
}

/* Body — sidebar + content side by side, fills remaining height */
.shell__body {
  flex: 1;
  min-height: 0;
  position: relative;
  overflow: hidden;
}

/* Scrollable page content */
.shell__content {
  height: 100%;
  padding: var(--space-4) var(--space-4);
  overflow-y: auto;
  min-height: 0;
}

@media (min-width: 768px) {
  .shell__content {
    margin-left: var(--sidebar-width);
    padding: var(--space-6);
  }
}

/* ── Overlay Transition ── */
.overlay-enter-active,
.overlay-leave-active {
  transition: opacity 0.3s var(--ease-out);
}

.overlay-enter-from,
.overlay-leave-to {
  opacity: 0;
}
</style>
