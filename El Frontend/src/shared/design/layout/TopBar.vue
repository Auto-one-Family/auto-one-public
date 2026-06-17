<script setup lang="ts">
/**
 * TopBar — Unified Command Strip
 *
 * Consolidates the former TopBar + ActionBar + ZoomBreadcrumb into a single
 * 48px header. Dashboard-specific controls appear only when DashboardView
 * is active (via dashboard store).
 *
 * Layout (Hardware):
 * LEFT:   [Hamburger] [Breadcrumb: Dashboard > Zone > Device]
 * CENTER: [StatusPills] [TypeSegment]
 * RIGHT:  [+Mock] [Geräte (Pending Badge)] | [NOT-AUS] | [Dot] [User]
 *
 * Layout (Other pages):
 * LEFT:   [Hamburger] [PageTitle]
 * RIGHT:  [NOT-AUS] | [Dot] [User]
 */

import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/shared/stores/auth.store'
import { useWebSocket } from '@/composables/useWebSocket'
import { useDashboardStore } from '@/shared/stores/dashboard.store'
import { useAlertCenterStore } from '@/shared/stores/alert-center.store'
import { useEspStore } from '@/stores/esp'
import {
  LogOut, ChevronDown, Menu, Filter,
  Plus, AlertTriangle, Inbox,
} from 'lucide-vue-next'
import EmergencyStopButton from '@/components/safety/EmergencyStopButton.vue'
import AlertStatusBar from '@/components/notifications/AlertStatusBar.vue'
import StatusPill from '@/components/dashboard/StatusPill.vue'

const emit = defineEmits<{
  'toggle-sidebar': []
}>()

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const dashStore = useDashboardStore()
const alertCenterStore = useAlertCenterStore()
const espStore = useEspStore()
const showUserMenu = ref(false)
const showMobileFilters = ref(false)

// WebSocket Connection Status
const { connectionStatus } = useWebSocket({ autoConnect: true })

const connectionDotClass = computed(() => {
  switch (connectionStatus.value) {
    case 'connected': return 'header__dot--connected'
    case 'connecting': return 'header__dot--connecting'
    case 'error': return 'header__dot--error'
    default: return 'header__dot--disconnected'
  }
})

const connectionTooltip = computed(() => {
  if (espStore.hasFlappingDevices) {
    const n = espStore.flappingDeviceCount
    const serverPart = connectionStatus.value === 'connected'
      ? 'Server verbunden'
      : connectionStatus.value === 'connecting'
        ? 'Verbinde...'
        : 'Server getrennt'
    return `${serverPart} · ${n} Gerät${n > 1 ? 'e' : ''} instabil`
  }
  switch (connectionStatus.value) {
    case 'connected': return 'Server verbunden'
    case 'connecting': return 'Verbinde...'
    case 'error': return 'Verbindungsfehler'
    default: return 'Server getrennt'
  }
})

const pageTitle = computed(() =>
  (route.meta.title as string) || 'Dashboard'
)

const isDashboardFamily = computed(() =>
  ['/dashboards', '/monitor', '/editor'].some(
    p => route.path === p || route.path.startsWith(p + '/')
  )
)

const showAlertEntry = computed(
  () => alertCenterStore.alertStats !== null && espStore.devices.length > 0,
)

const breadcrumbSegments = computed(() => {
  if (!dashStore.showControls) return []

  const raw = [
    dashStore.breadcrumb.zoneName,
    dashStore.breadcrumb.deviceName || dashStore.breadcrumb.dashboardName || dashStore.breadcrumb.ruleName,
    dashStore.breadcrumb.sensorName,
  ]
  return raw.filter((segment): segment is string => typeof segment === 'string' && segment.trim().length > 0)
})

async function handleLogout() {
  showUserMenu.value = false
  await authStore.logout()
  router.push('/login')
}
</script>

<template>
  <header class="header">
    <!-- ═══ LEFT: Hamburger + Breadcrumb/Title ═══ -->
    <div class="header__left">
      <button class="header__hamburger" @click="emit('toggle-sidebar')">
        <Menu class="header__hamburger-icon" />
      </button>

      <span v-if="!isDashboardFamily" class="header__page-title">{{ pageTitle }}</span>
      <nav v-if="breadcrumbSegments.length > 0" class="header__breadcrumb" aria-label="Kontextpfad">
        <span
          v-for="(segment, idx) in breadcrumbSegments"
          :key="`${segment}-${idx}`"
          class="header__crumb--current"
        >
          <span v-if="idx > 0" class="header__crumb-sep">›</span>
          {{ segment }}
        </span>
      </nav>
    </div>

    <!-- ═══ CENTER: Dashboard Controls ═══ -->
    <div class="header__controls">
      <!-- Problem Alert (inline, dashboard only) -->
      <div v-if="dashStore.showControls && dashStore.hasProblems && dashStore.problemMessage" class="header__alert">
        <AlertTriangle class="header__alert-icon" />
        <span class="header__alert-text">{{ dashStore.problemMessage }}</span>
      </div>

      <!-- Error/SafeMode pills — desktop only, dashboard only -->
      <div v-if="dashStore.showControls && dashStore.deviceCounts.all > 0" class="header__filters-desktop">
        <StatusPill
          v-if="dashStore.statusCounts.warning > 0"
          type="warning"
          :count="dashStore.statusCounts.warning"
          label="Fehler"
          :active="dashStore.activeStatusFilters.has('warning')"
          @click="dashStore.toggleStatusFilter('warning')"
        />
        <StatusPill
          v-if="dashStore.statusCounts.safeMode > 0"
          type="safemode"
          :count="dashStore.statusCounts.safeMode"
          label="Safe Mode"
          :active="dashStore.activeStatusFilters.has('safemode')"
          @click="dashStore.toggleStatusFilter('safemode')"
        />
      </div>

      <!-- Mobile Filter Toggle (<1024px, dashboard only) -->
      <button
        v-if="dashStore.showControls && dashStore.deviceCounts.all > 0"
        class="header__filter-toggle"
        :class="{ 'header__filter-toggle--active': showMobileFilters }"
        @click="showMobileFilters = !showMobileFilters"
      >
        <Filter class="header__filter-toggle-icon" />
      </button>
    </div>

    <!-- ═══ RIGHT: Actions + System ═══ -->
    <div class="header__right">
      <!-- Hardware Actions (only on /hardware route) -->
      <template v-if="dashStore.showControls">
        <button
          class="header__action-btn header__action-btn--create"
          title="Test-ESP erstellen"
          @click="dashStore.showCreateMock = true"
        >
          <Plus class="header__action-btn-icon" />
          <span class="header__action-btn-label">Mock</span>
        </button>

        <button
          class="header__action-btn header__action-btn--pending"
          :class="{ 'header__action-btn--pending-active': espStore.pendingCount > 0 }"
          title="Ausstehende Geräte"
          @click="dashStore.showPendingPanel = true"
        >
          <Inbox class="header__action-btn-icon" />
          <span class="header__action-btn-label">Geräte</span>
          <span v-if="espStore.pendingCount > 0" class="header__action-btn-badge">
            {{ espStore.pendingCount }}
          </span>
        </button>
      </template>

      <!-- ================================================================
           TODO: ALERT PANEL — muss noch verschoben und verbessert werden
           bevor es ohne TopBar verwendbar ist.

           Aktueller Inhalt: AlertStatusBar (aktive Alert-Anzahl + Severity)
           Kandidaten für neuen Platz:
             - Sidebar-Footer (unter User-Info)
             - Als Trigger für NotificationDrawer in der Sidebar
             - Dedizierte Statuszeile am oberen Rand des shell__content
             - Teil des QuickActionBall-Panels

           Verbesserungs-Ideen:
             - Größeres Touch-Target
             - Severity-Farbe als Sidebar-Akzent
             - Flapping-Badge integrieren (aktuell in header__connection)
             - EmergencyStopButton ebenfalls mitmigrieren (aktuell darunter)
           ================================================================ -->
      <div v-if="showAlertEntry" class="header__alerts-group">
        <div class="header__divider" />
        <AlertStatusBar />
        <div class="header__divider" />
      </div>

      <!-- Emergency Stop -->
      <EmergencyStopButton />

      <!-- Connection Dot + Flapping Indicator + User -->
      <div class="header__connection" :title="connectionTooltip">
        <span
          v-if="espStore.hasFlappingDevices"
          class="header__flapping-badge"
          :title="`${espStore.flappingDeviceCount} Gerät${espStore.flappingDeviceCount > 1 ? 'e' : ''} mit instabiler Verbindung`"
        >
          <AlertTriangle class="header__flapping-icon" />
          <span class="header__flapping-count">{{ espStore.flappingDeviceCount }}</span>
        </span>
        <span class="header__dot" :class="connectionDotClass" />
      </div>

      <!-- User Menu -->
      <div class="header__user-wrapper">
        <button class="header__user-trigger" @click="showUserMenu = !showUserMenu">
          <div class="header__user-avatar">
            {{ authStore.user?.username?.charAt(0).toUpperCase() || '?' }}
          </div>
          <ChevronDown class="header__chevron" />
        </button>

        <Transition name="dropdown">
          <div v-if="showUserMenu" class="header__dropdown">
            <div class="header__dropdown-info">
              <p class="header__dropdown-name">{{ authStore.user?.username }}</p>
              <p class="header__dropdown-email">{{ authStore.user?.email || authStore.user?.role }}</p>
            </div>
            <div class="header__dropdown-actions">
              <button class="header__dropdown-item" @click="handleLogout">
                <LogOut class="header__dropdown-item-icon" />
                Abmelden
              </button>
            </div>
          </div>
        </Transition>
      </div>
    </div>
  </header>

  <!-- Mobile Filter Dropdown (slides below header, error/safemode pills only) -->
  <Transition name="filter-slide">
    <div v-if="dashStore.showControls && showMobileFilters && dashStore.deviceCounts.all > 0" class="header-mobile-filters">
      <div class="header-mobile-filters__pills">
        <StatusPill
          v-if="dashStore.statusCounts.warning > 0"
          type="warning"
          :count="dashStore.statusCounts.warning"
          label="Fehler"
          :active="dashStore.activeStatusFilters.has('warning')"
          @click="dashStore.toggleStatusFilter('warning')"
        />
        <StatusPill
          v-if="dashStore.statusCounts.safeMode > 0"
          type="safemode"
          :count="dashStore.statusCounts.safeMode"
          label="Safe Mode"
          :active="dashStore.activeStatusFilters.has('safemode')"
          @click="dashStore.toggleStatusFilter('safemode')"
        />
      </div>
    </div>
  </Transition>

  <!-- Click-away overlay -->
  <div
    v-if="showUserMenu"
    class="header__click-away"
    @click="showUserMenu = false"
  />
</template>

<style scoped>
/* ═══════════════════════════════════════════════════════════════════════════
   UNIFIED COMMAND STRIP — 48px consolidated header
   Merges TopBar + ActionBar + Breadcrumb into one strip.
   ═══════════════════════════════════════════════════════════════════════════ */

.header {
  height: var(--header-height);
  background-color: var(--color-bg-secondary);
  border-bottom: 1px solid var(--glass-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-4);
  flex-shrink: 0;
  position: relative;
  z-index: var(--z-dropdown);
  gap: var(--space-3);
  --header-control-size: 32px;
  --header-action-padding-y: 4px;
  --header-action-padding-x: var(--space-2);
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
}

/* ═══ LEFT SECTION ══════════════════════════════════════════════════════ */

.header__left {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
  flex-shrink: 1;
  max-width: 240px;
}

.header__hamburger {
  display: none;
  padding: var(--space-1);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  transition: all var(--transition-fast);
}

.header__hamburger:hover {
  color: var(--color-text-primary);
  background-color: var(--color-bg-tertiary);
}

.header__hamburger-icon {
  width: 18px;
  height: 18px;
}

@media (max-width: 767px) {
  .header__hamburger {
    display: flex;
    align-items: center;
    justify-content: center;
  }
}

/* ── Page Title (non-dashboard) ── */
.header__page-title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── Breadcrumb (dashboard) ── */
.header__breadcrumb {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  overflow: hidden;
}

.header__crumb,
.header__crumb--current {
  background: none;
  border: none;
  padding: 0;
  font: inherit;
  font-size: var(--text-sm);
  white-space: nowrap;
}

.header__crumb {
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
  border-radius: var(--radius-sm);
  padding: 2px 6px;
  margin: -2px -6px;
}

.header__crumb:hover {
  color: var(--color-accent-bright);
  background: rgba(96, 165, 250, 0.08);
}

.header__crumb--current {
  color: var(--color-text-primary);
  font-weight: 600;
  cursor: default;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
}

.header__crumb-sep {
  color: var(--color-text-muted);
  opacity: 0.4;
  font-size: var(--text-xs);
  user-select: none;
  flex-shrink: 0;
}

/* Cross-tab link (Monitor ↔ Hardware) */
.header__cross-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  margin-left: var(--space-1);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  text-decoration: none;
  transition: color var(--transition-fast), background var(--transition-fast);
  flex-shrink: 0;
}

.header__cross-link:hover {
  color: var(--color-accent-bright);
  background: rgba(96, 165, 250, 0.08);
}

.header__cross-link-icon {
  width: 13px;
  height: 13px;
}

/* ═══ CENTER SECTION: Dashboard Controls ════════════════════════════════ */

.header__controls {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex: 1 1 0;
  justify-content: center;
  min-width: 0;
  overflow: hidden;
}

/* ── Compact Status Chip (Online/Total) ── */
.header__status-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: 2px var(--space-2);
  border-radius: var(--radius-full);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-secondary);
  white-space: nowrap;
  flex-shrink: 0;
  cursor: default;
}

/* ── Problem Alert (inline) ── */
.header__alert {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: 2px var(--space-2);
  border-radius: var(--radius-full);
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.2);
  font-size: var(--text-xs);
  color: var(--color-warning);
  white-space: nowrap;
  flex-shrink: 0;
}

.header__alert-icon {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
}

.header__alert-text {
  font-weight: 500;
}

/* ── Desktop Filter Row (≥1024px) ── */
.header__filters-desktop {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

/* ── Mobile Filter Toggle (visible <1024px) ── */
.header__filter-toggle {
  display: none;
  align-items: center;
  justify-content: center;
  padding: var(--space-1);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  transition: all var(--transition-fast);
}

.header__filter-toggle:hover {
  color: var(--color-text-primary);
  background: var(--color-bg-tertiary);
}

.header__filter-toggle--active {
  color: var(--color-accent-bright);
  background: rgba(96, 165, 250, 0.08);
}

.header__filter-toggle-icon {
  width: 16px;
  height: 16px;
}

@media (max-width: 1399px) {
  .header__crumb--current {
    max-width: 140px;
  }
}

@media (max-width: 1023px) {
  .header__filters-desktop {
    display: none;
  }

  .header__filter-toggle {
    display: flex;
  }

  .header__alert {
    display: none;
  }

  .header__crumb--current {
    max-width: 100px;
  }

  .header__divider {
    height: 16px;
  }

  .header__right {
    gap: var(--space-1);
  }
}

@media (max-width: 767px) {
  .header {
    padding: 0 var(--space-2);
    gap: var(--space-2);
  }

  .header__left {
    max-width: 42%;
  }

  .header__controls {
    justify-content: flex-start;
  }

  .header__right {
    gap: var(--space-1);
  }

  .header__connection {
    display: none;
  }

  .header__flapping-badge {
    display: none;
  }
}

/* Medium widths: keep single-row and reduce low-priority noise */
@media (max-width: 900px) {
  .header {
    flex-wrap: nowrap;
    align-items: center;
    padding: 0 var(--space-2);
  }

  .header__left {
    flex: 1;
    min-width: 0;
  }

  .header__controls {
    flex: 0 0 auto;
    justify-content: flex-end;
    gap: var(--space-1);
  }

  .header__breadcrumb {
    gap: var(--space-1);
    min-width: 0;
    overflow: hidden;
    white-space: nowrap;
  }

  .header__crumb,
  .header__crumb--current {
    max-width: clamp(72px, 18vw, 132px);
    overflow: hidden;
    text-overflow: ellipsis;
    display: inline-block;
    vertical-align: bottom;
  }

  .header__action-btn--create {
    display: none;
  }

  .header__right {
    gap: var(--space-1);
  }
}

/* Compact displays: reduce visual blur and increase edge contrast */
@media (max-width: 1366px), (max-height: 820px) {
  .header {
    border-bottom-color: var(--glass-border-hover);
  }

  .header__status-chip {
    background: var(--color-bg-tertiary);
    border-color: var(--glass-border-hover);
    box-shadow: none;
  }

  .header__dot--connected,
  .header__dot--connecting {
    animation: none;
    box-shadow: none;
  }

  .header__flapping-badge {
    animation: none;
  }
}

/* ═══ RIGHT SECTION ═════════════════════════════════════════════════════ */

.header__right {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
  min-width: 0;
}

.header__alerts-group {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}

/* ── Action Buttons (Dashboard) ── */
.header__action-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--header-action-padding-y) var(--header-action-padding-x);
  min-height: var(--header-control-size);
  font-size: var(--text-xs);
  font-weight: 500;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.header__action-btn-icon {
  width: 15px;
  height: 15px;
  flex-shrink: 0;
}

.header__action-btn-label {
  display: none;
}

@media (min-width: 1280px) {
  .header__action-btn-label {
    display: inline;
  }
}

/* Create Mock */
.header__action-btn--create {
  color: var(--color-success);
  background: rgba(52, 211, 153, 0.06);
  border-color: rgba(52, 211, 153, 0.15);
}

.header__action-btn--create:hover {
  background: rgba(52, 211, 153, 0.12);
  border-color: rgba(52, 211, 153, 0.3);
}

/* Pending Devices */
.header__action-btn--pending {
  color: var(--color-iridescent-1);
  background: rgba(96, 165, 250, 0.06);
  border-color: rgba(96, 165, 250, 0.15);
  position: relative;
}

.header__action-btn--pending:hover {
  background: rgba(96, 165, 250, 0.12);
  border-color: rgba(96, 165, 250, 0.3);
}

.header__action-btn--pending-active {
  background: rgba(96, 165, 250, 0.1);
  border-color: rgba(96, 165, 250, 0.28);
  box-shadow: 0 0 8px rgba(96, 165, 250, 0.15);
}

.header__action-btn--pending-active:hover {
  background: rgba(96, 165, 250, 0.16);
  border-color: rgba(96, 165, 250, 0.45);
  box-shadow: 0 0 14px rgba(96, 165, 250, 0.28);
}

/* Pending count badge */
.header__action-btn-badge {
  position: absolute;
  top: -5px;
  right: -5px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: var(--radius-full);
  background: linear-gradient(135deg, var(--color-iridescent-1), var(--color-iridescent-2));
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 0 8px rgba(96, 165, 250, 0.5);
  animation: badge-pulse 2s ease-in-out infinite;
  font-variant-numeric: tabular-nums;
  pointer-events: none;
}

/* ── Divider ── */
.header__divider {
  width: 1px;
  height: 20px;
  background-color: var(--glass-border);
  flex-shrink: 0;
}

/* ── Connection Dot ── */
.header__connection {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: 0 6px;
  min-height: var(--header-control-size);
  cursor: default;
}

.header__dot {
  width: 7px;
  height: 7px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
  transition: background-color var(--transition-base), box-shadow var(--transition-base);
}

.header__dot--connected {
  background-color: var(--color-success);
  box-shadow: 0 0 6px rgba(52, 211, 153, 0.5);
  animation: pulse-dot 3s ease-in-out infinite;
}

.header__dot--connecting {
  background-color: var(--color-warning);
  box-shadow: 0 0 6px rgba(251, 191, 36, 0.4);
  animation: pulse-dot 1.2s ease-in-out infinite;
}

.header__dot--error {
  background-color: var(--color-error);
  box-shadow: 0 0 6px rgba(248, 113, 113, 0.4);
}

.header__dot--disconnected {
  background-color: var(--color-text-muted);
}

/* ── Flapping Indicator (PKG-20) ── */
.header__flapping-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 6px;
  border-radius: var(--radius-full);
  background: rgba(251, 191, 36, 0.12);
  border: 1px solid rgba(251, 191, 36, 0.3);
  color: var(--color-warning);
  font-size: var(--text-xs);
  font-weight: 600;
  white-space: nowrap;
  animation: flapping-pulse 2s ease-in-out infinite;
  cursor: default;
}

.header__flapping-icon {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
}

.header__flapping-count {
  font-variant-numeric: tabular-nums;
}

@keyframes flapping-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

@keyframes badge-pulse {
  0%, 100% { box-shadow: 0 0 6px rgba(96, 165, 250, 0.5); }
  50%       { box-shadow: 0 0 14px rgba(129, 140, 248, 0.75); }
}

/* Connection label removed — tooltip-only via :title attribute */

/* ── User Menu ── */
.header__user-wrapper {
  position: relative;
}

.header__user-trigger {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: 3px;
  min-height: var(--header-control-size);
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
}

.header__user-trigger:hover {
  background-color: var(--color-bg-tertiary);
}

.header__user-avatar {
  width: 24px;
  height: 24px;
  border-radius: var(--radius-full);
  background: linear-gradient(135deg, var(--color-bg-tertiary), var(--color-bg-quaternary));
  border: 1px solid var(--glass-border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
}

.header__chevron {
  width: 12px;
  height: 12px;
  color: var(--color-text-muted);
  transition: transform var(--transition-fast);
}

.header__user-trigger:hover .header__chevron {
  color: var(--color-text-secondary);
}

/* ── Dropdown ── */
.header__dropdown {
  position: absolute;
  right: 0;
  top: calc(100% + var(--space-2));
  width: 200px;
  background-color: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  box-shadow: var(--elevation-floating);
  z-index: var(--z-dropdown);
  overflow: hidden;
}

.header__dropdown-info {
  padding: var(--space-3);
  border-bottom: 1px solid var(--glass-border);
}

.header__dropdown-name {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
}

.header__dropdown-email {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin-top: 2px;
  text-transform: capitalize;
}

.header__dropdown-actions {
  padding: var(--space-1);
}

.header__dropdown-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
  color: var(--color-error);
  border-radius: var(--radius-sm);
  transition: background-color var(--transition-fast);
}

.header__dropdown-item:hover {
  background-color: var(--color-bg-quaternary);
}

.header__dropdown-item-icon {
  width: 14px;
  height: 14px;
}

/* ═══ MOBILE FILTER DROPDOWN ════════════════════════════════════════════ */

.header-mobile-filters {
  display: none;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  background: var(--color-bg-secondary);
  border-bottom: 1px solid var(--glass-border);
  z-index: var(--z-dropdown);
}

@media (max-width: 1023px) {
  .header-mobile-filters {
    display: flex;
  }
}

.header-mobile-filters__pills {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  flex-wrap: wrap;
}

@media (min-width: 1536px) {
  .header {
    --header-control-size: 40px;
    --header-action-padding-y: 8px;
    --header-action-padding-x: var(--space-3);
  }

  .header__right {
    gap: var(--space-3);
  }

  .header__action-btn {
    font-size: var(--text-sm);
  }

  .header__action-btn-icon {
    width: 16px;
    height: 16px;
  }

  .header__divider {
    height: 24px;
  }

  .header__dot {
    width: 8px;
    height: 8px;
  }

  .header__user-avatar {
    width: 30px;
    height: 30px;
    font-size: var(--text-sm);
  }

  .header__chevron {
    width: 14px;
    height: 14px;
  }
}

/* ═══ TRANSITIONS ═══════════════════════════════════════════════════════ */

.dropdown-enter-active {
  transition: all var(--duration-fast) var(--ease-out);
}

.dropdown-leave-active {
  transition: all var(--duration-fast) var(--ease-in-out);
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.97);
}

.filter-slide-enter-active {
  transition: all var(--duration-base) var(--ease-out);
}

.filter-slide-leave-active {
  transition: all var(--duration-fast) var(--ease-in-out);
}

.filter-slide-enter-from,
.filter-slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

/* ── Click-away overlay ── */
.header__click-away {
  position: fixed;
  inset: 0;
  z-index: calc(var(--z-dropdown) - 1);
}

/* ── SVG pointer-events fix: prevent SVG icons from intercepting clicks on parent buttons ── */
.header__type-btn svg,
.header__action-btn svg {
  pointer-events: none;
}

/* ═══ REDUCED MOTION ════════════════════════════════════════════════════ */

@media (prefers-reduced-motion: reduce) {
  .header__dot--connected,
  .header__dot--connecting,
  .header__flapping-badge,
  .header__action-btn-badge {
    animation: none;
  }
}
</style>
