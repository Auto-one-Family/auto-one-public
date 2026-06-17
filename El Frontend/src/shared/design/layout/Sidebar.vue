<script setup lang="ts">
/**
 * AppSidebar — Mission Control Navigation
 *
 * Design: Glow-line active indicator, section dividers,
 * brand logo element, hover states that feel alive.
 */

import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/shared/stores/auth.store'
import { useDashboardStore } from '@/shared/stores/dashboard.store'
import { useEspStore } from '@/stores/esp'
import { useSidebarSwipe } from '@/composables/useSwipeNavigation'
import {
  X,
  LayoutDashboard,
  Cpu,
  Workflow,
  Monitor,
  Users,
  UserCog,
  Activity,
  SlidersHorizontal,
  Puzzle,
  Mail,
  Inbox,
} from 'lucide-vue-next'

defineProps<{
  isOpen: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

const route = useRoute()
const authStore = useAuthStore()
const dashStore = useDashboardStore()
const espStore = useEspStore()
const pendingCount = computed(() => espStore.pendingCount ?? 0)

// Swipe left on open sidebar → close (mobile/tablet)
const sidebarRef = ref<HTMLElement | null>(null)
useSidebarSwipe(sidebarRef, () => emit('close'))

function matchesRoutePrefix(prefix: string): boolean {
  if (prefix === '/') return route.path === '/'
  return route.path === prefix || route.path.startsWith(`${prefix}/`)
}

function isDashboardRoute(): boolean {
  return ['/dashboards', '/monitor', '/editor'].some(matchesRoutePrefix)
}

function isHardwareRoute(): boolean {
  return matchesRoutePrefix('/hardware')
}

function handleNavClick() {
  emit('close')
}

function handlePendingClick() {
  dashStore.showPendingPanel = true
  emit('close')
}
</script>

<template>
  <aside
    ref="sidebarRef"
    :class="[
      'sidebar',
      isOpen ? 'sidebar--open' : 'sidebar--closed',
    ]"
  >
    <!-- Brand Header -->
    <div class="sidebar__header">
      <div class="sidebar__brand">
        <div class="sidebar__brand-mark">
          <div class="sidebar__brand-dot" />
        </div>
        <h1 class="sidebar__logo">
          <span class="sidebar__logo-text">Automation</span><span class="sidebar__logo-accent">One</span>
        </h1>
      </div>
      <button
        class="sidebar__close-btn md:hidden"
        @click="emit('close')"
      >
        <X class="w-5 h-5" />
      </button>
    </div>

    <!-- Navigation -->
    <nav class="sidebar__nav">
      <!-- Main Section Label -->
      <div class="sidebar__section-label">Navigation</div>

      <RouterLink
        v-if="!authStore.isViewer"
        to="/dashboards"
        :class="['sidebar__link', isDashboardRoute() && 'sidebar__link--active']"
        @click="handleNavClick"
      >
        <div class="sidebar__link-indicator" />
        <LayoutDashboard class="sidebar__link-icon" />
        <span>Dashboards</span>
      </RouterLink>

      <RouterLink
        v-if="!authStore.isViewer"
        to="/hardware"
        :class="['sidebar__link', isHardwareRoute() && 'sidebar__link--active']"
        @click="handleNavClick"
      >
        <div class="sidebar__link-indicator" />
        <Cpu class="sidebar__link-icon" />
        <span>Geräte</span>
      </RouterLink>

      <RouterLink
        v-if="!authStore.isViewer"
        to="/logic"
        :class="['sidebar__link', matchesRoutePrefix('/logic') && 'sidebar__link--active']"
        @click="handleNavClick"
      >
        <div class="sidebar__link-indicator" />
        <Workflow class="sidebar__link-icon" />
        <span>Regeln</span>
      </RouterLink>

      <RouterLink
        v-if="!authStore.isViewer"
        to="/sensors"
        :class="['sidebar__link', matchesRoutePrefix('/sensors') && 'sidebar__link--active']"
        @click="handleNavClick"
      >
        <div class="sidebar__link-indicator" />
        <Activity class="sidebar__link-icon" />
        <span>Komponenten</span>
      </RouterLink>

      <!-- TODO replace isViewer with capability check -->
      <RouterLink
        v-if="authStore.isViewer"
        to="/monitor"
        :class="['sidebar__link', matchesRoutePrefix('/monitor') && 'sidebar__link--active']"
        @click="handleNavClick"
      >
        <div class="sidebar__link-indicator" />
        <Monitor class="sidebar__link-icon" />
        <span>Monitor</span>
      </RouterLink>


      <!-- Admin Section -->
      <template v-if="authStore.isAdmin">
        <div class="sidebar__divider" />
        <div class="sidebar__section-label">Administration</div>

        <RouterLink
          to="/system-monitor"
          :class="['sidebar__link', matchesRoutePrefix('/system-monitor') && 'sidebar__link--active']"
          @click="handleNavClick"
        >
          <div class="sidebar__link-indicator" />
          <Monitor class="sidebar__link-icon" />
          <span>System</span>
        </RouterLink>

        <RouterLink
          to="/users"
          :class="['sidebar__link', matchesRoutePrefix('/users') && 'sidebar__link--active']"
          @click="handleNavClick"
        >
          <div class="sidebar__link-indicator" />
          <Users class="sidebar__link-icon" />
          <span>Benutzer</span>
        </RouterLink>

        <RouterLink
          to="/calibration"
          :class="['sidebar__link', matchesRoutePrefix('/calibration') && 'sidebar__link--active']"
          @click="handleNavClick"
        >
          <div class="sidebar__link-indicator" />
          <SlidersHorizontal class="sidebar__link-icon" />
          <span>Kalibrierung</span>
        </RouterLink>

        <RouterLink
          to="/plugins"
          :class="['sidebar__link', matchesRoutePrefix('/plugins') && 'sidebar__link--active']"
          @click="handleNavClick"
        >
          <div class="sidebar__link-indicator" />
          <Puzzle class="sidebar__link-icon" />
          <span>Plugins</span>
        </RouterLink>

        <RouterLink
          to="/email"
          :class="['sidebar__link', matchesRoutePrefix('/email') && 'sidebar__link--active']"
          @click="handleNavClick"
        >
          <div class="sidebar__link-indicator" />
          <Mail class="sidebar__link-icon" />
          <span>Postfach</span>
        </RouterLink>
      </template>
    </nav>

    <!-- Footer -->
    <div class="sidebar__footer">
      <button
        class="sidebar__link sidebar__link--pending"
        :class="{ 'sidebar__link--pending-active': pendingCount > 0 }"
        title="Ausstehende Geräte"
        @click="handlePendingClick"
      >
        <div class="sidebar__link-indicator" />
        <Inbox class="sidebar__link-icon" />
        <span>Geräte</span>
        <span v-if="pendingCount > 0" class="sidebar__pending-badge">{{ pendingCount }}</span>
      </button>

      <RouterLink
        to="/settings"
        :class="['sidebar__link', matchesRoutePrefix('/settings') && 'sidebar__link--active']"
        @click="handleNavClick"
      >
        <div class="sidebar__link-indicator" />
        <UserCog class="sidebar__link-icon" />
        <span>Einstellungen</span>
      </RouterLink>

      <!-- User Info -->
      <div class="sidebar__user">
        <div class="sidebar__user-avatar">
          {{ authStore.user?.username?.charAt(0).toUpperCase() || '?' }}
        </div>
        <div class="sidebar__user-info">
          <p class="sidebar__user-name">
            {{ authStore.user?.username || 'Unbekannt' }}
          </p>
          <p class="sidebar__user-role">
            {{ authStore.user?.role || 'user' }}
          </p>
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════════════════════════════
   SIDEBAR — Mission Control Navigation
   ═══════════════════════════════════════════════════════════════════════════ */

.sidebar {
  position: fixed;
  left: 0;
  top: 0;
  height: 100vh;
  width: var(--sidebar-width);
  background-color: var(--color-bg-secondary);
  border-right: 1px solid var(--glass-border);
  display: flex;
  flex-direction: column;
  z-index: var(--z-fixed);
  transition: transform 0.3s var(--ease-out);
}

.sidebar--closed {
  transform: translateX(-100%);
}

.sidebar--open {
  transform: translateX(0);
}

@media (min-width: 768px) {
  .sidebar {
    transform: translateX(0);
  }
}

/* ── Brand Header ── */
.sidebar__header {
  height: var(--header-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
}

.sidebar__brand {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.sidebar__brand-mark {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  background: linear-gradient(135deg, var(--color-iridescent-1), var(--color-iridescent-3));
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 0 12px rgba(96, 165, 250, 0.3);
}

.sidebar__brand-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: white;
  opacity: 0.9;
}

.sidebar__logo {
  font-size: var(--text-lg);
  font-weight: 700;
  letter-spacing: var(--tracking-tight);
  line-height: 1;
}

.sidebar__logo-text {
  color: var(--color-text-primary);
}

.sidebar__logo-accent {
  background: var(--gradient-iridescent);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.sidebar__close-btn {
  padding: var(--space-2);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  transition: all var(--transition-fast);
}

.sidebar__close-btn:hover {
  color: var(--color-text-primary);
  background-color: var(--color-bg-tertiary);
}

/* ── Navigation ── */
.sidebar__nav {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-3) var(--space-2);
}

/* Section Labels */
.sidebar__section-label {
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
}

/* Divider */
.sidebar__divider {
  height: 1px;
  background-color: var(--glass-border);
  margin: var(--space-2) var(--space-3);
}

/* ── Navigation Links ── */
.sidebar__link {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  margin-bottom: 2px;
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  font-size: var(--text-base);
  font-weight: 500;
  transition: all var(--transition-fast);
  text-decoration: none;
  min-height: 40px;
}

.sidebar__link:hover {
  color: var(--color-text-primary);
  background-color: rgba(255, 255, 255, 0.03);
}

.sidebar__link:active {
  background-color: rgba(255, 255, 255, 0.05);
}

/* Glow Indicator — left edge bar */
.sidebar__link-indicator {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 0;
  border-radius: 0 var(--radius-xs) var(--radius-xs) 0;
  background: var(--color-accent);
  transition: height var(--transition-base), box-shadow var(--transition-base);
}

/* Active state — glow line visible */
.sidebar__link--active {
  color: var(--color-text-primary);
  background-color: rgba(59, 130, 246, 0.06);
}

.sidebar__link--active .sidebar__link-indicator {
  height: 20px;
  background: var(--color-accent-bright);
  box-shadow: 0 0 8px rgba(96, 165, 250, 0.4);
  animation: glow-line 2s ease-in-out infinite;
}

.sidebar__link--active .sidebar__link-icon {
  color: var(--color-accent-bright);
}

.sidebar__link--active:hover {
  background-color: rgba(59, 130, 246, 0.08);
}

.sidebar__link-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  transition: color var(--transition-fast);
}

/* Pending Devices Button (button element needs explicit width + cursor) */
.sidebar__link--pending {
  width: 100%;
  background: none;
  border: none;
  cursor: pointer;
  text-align: left;
  touch-action: manipulation;
}

.sidebar__link--pending-active .sidebar__link-icon {
  color: var(--color-accent-bright);
}

.sidebar__pending-badge {
  margin-left: auto;
  min-width: 18px;
  height: 18px;
  padding: 0 var(--space-1);
  border-radius: var(--radius-full);
  background: var(--color-accent);
  color: #fff;
  font-size: var(--text-xs);
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* ── Footer ── */
.sidebar__footer {
  padding: var(--space-3) var(--space-2);
  border-top: 1px solid var(--glass-border);
  flex-shrink: 0;
}

.sidebar__user {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-top: var(--space-3);
  padding: var(--space-2) var(--space-3);
}

.sidebar__user-avatar {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-full);
  background: linear-gradient(135deg, var(--color-bg-tertiary), var(--color-bg-quaternary));
  border: 1px solid var(--glass-border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
}

.sidebar__user-info {
  flex: 1;
  min-width: 0;
}

.sidebar__user-name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar__user-role {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  text-transform: capitalize;
}
</style>
