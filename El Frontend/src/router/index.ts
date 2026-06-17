import { createRouter, createWebHistory } from 'vue-router'
import type { Component } from 'vue'
import { useAuthStore } from '@/shared/stores/auth.store'

/**
 * Wraps a dynamic import with retry logic.
 * Catches "Failed to fetch dynamically imported module" errors that occur
 * when Vite HMR invalidates a module or the browser cache is stale.
 * Without this wrapper, Vue Router logs an uncaught navigation error warning
 * before router.onError can handle it.
 */
const MAX_IMPORT_RETRIES = 2
const RETRY_DELAY_MS = 200
const LEGACY_REDIRECT_TELEMETRY_KEY = 'router.legacyRedirectTelemetry.v1'
const LEGACY_DECOMMISSION_PLAN = {
  measurement: 'active',
  warning: 'planned',
  softRemovalOrder: ['P3', 'P2', 'P1'],
  hardRemovalOrder: ['P2', 'P1'],
} as const
const LEGACY_REDIRECT_PATTERNS: RegExp[] = [
  /^\/custom-dashboard$/,
  /^\/dashboard-legacy$/,
  /^\/devices(?:\/.*)?$/,
  /^\/mock-esp(?:\/.*)?$/,
  /^\/database$/,
  /^\/logs$/,
  /^\/audit$/,
  /^\/mqtt-log$/,
  /^\/maintenance$/,
  /^\/actuators$/,
  /^\/sensor-history$/,
  /^\/monitor\/dashboard\/[^/]+$/,
]

function lazyView(factory: () => Promise<{ default: Component }>): () => Promise<{ default: Component }> {
  return async () => {
    for (let attempt = 0; attempt <= MAX_IMPORT_RETRIES; attempt++) {
      try {
        return await factory()
      } catch (error) {
        const isImportError =
          error instanceof TypeError &&
          error.message?.includes('Failed to fetch dynamically imported module')
        if (!isImportError || attempt === MAX_IMPORT_RETRIES) {
          throw error
        }
        await new Promise((r) => setTimeout(r, RETRY_DELAY_MS * (attempt + 1)))
      }
    }
    // Unreachable — either returns or throws above
    return await factory()
  }
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    // Auth routes (public)
    {
      path: '/login',
      name: 'login',
      component: lazyView(() => import('@/views/LoginView.vue')),
      meta: { requiresAuth: false },
    },
    {
      path: '/setup',
      name: 'setup',
      component: lazyView(() => import('@/views/SetupView.vue')),
      meta: { requiresAuth: false },
    },

    // Protected routes (require auth)
    {
      path: '/',
      component: lazyView(() => import('@/shared/design/layout/AppShell.vue')),
      meta: { requiresAuth: true },
      children: [
        // Default redirect to /dashboards (or /monitor for viewer role)
        {
          path: '',
          // TODO replace isViewer with capability check
          redirect: () => {
            const authStore = useAuthStore()
            return authStore.isViewer ? '/monitor' : '/dashboards'
          },
        },

        // ═══════════════════════════════════════════════════════════════════
        // HARDWARE VIEW — Übersicht: Zone Accordion + ESP Orbital (/hardware)
        // ═══════════════════════════════════════════════════════════════════
        {
          path: 'hardware',
          name: 'hardware',
          component: lazyView(() => import('@/views/HardwareView.vue')),
          meta: { title: 'Übersicht' },
        },
        {
          path: 'hardware/:zoneId',
          name: 'hardware-zone',
          component: lazyView(() => import('@/views/HardwareView.vue')),
          meta: { title: 'Übersicht' },
        },
        {
          path: 'hardware/:zoneId/:espId',
          name: 'hardware-esp',
          component: lazyView(() => import('@/views/HardwareView.vue')),
          meta: { title: 'Übersicht' },
        },

        // ═══════════════════════════════════════════════════════════════════
        // MONITOR VIEW — Sensor & Actuator Data (/monitor)
        // ═══════════════════════════════════════════════════════════════════
        {
          path: 'monitor',
          name: 'monitor',
          component: lazyView(() => import('@/views/MonitorView.vue')),
          meta: { title: 'Monitor', viewerAllowed: true },
        },
        // DEPRECATED 2026-03-26: monitor-dashboard removed (D2 cleanup), redirect to editor
        {
          path: 'monitor/dashboard/:dashboardId',
          redirect: (to) => ({
            path: `/editor/${to.params.dashboardId}`,
          }),
        },
        {
          path: 'monitor/:zoneId',
          name: 'monitor-zone',
          component: lazyView(() => import('@/views/MonitorView.vue')),
          meta: { title: 'Monitor', viewerAllowed: true },
        },
        {
          path: 'monitor/:zoneId/sensor/:sensorId',
          name: 'monitor-sensor',
          component: lazyView(() => import('@/views/MonitorView.vue')),
          meta: { title: 'Monitor', viewerAllowed: true },
        },
        {
          path: 'monitor/:zoneId/dashboard/:dashboardId',
          name: 'monitor-zone-dashboard',
          component: lazyView(() => import('@/views/MonitorView.vue')),
          meta: { title: 'Monitor', viewerAllowed: true },
        },

        // ═══════════════════════════════════════════════════════════════════
        // EDITOR — Dashboard Widget Builder (/editor)
        // ═══════════════════════════════════════════════════════════════════
        {
          path: 'editor',
          name: 'editor',
          component: lazyView(() => import('@/views/CustomDashboardView.vue')),
          meta: { title: 'Dashboards', viewerAllowed: true },
        },
        {
          path: 'editor/:dashboardId',
          name: 'editor-dashboard',
          component: lazyView(() => import('@/views/CustomDashboardView.vue')),
          meta: { title: 'Editor' },
        },

        // ═══════════════════════════════════════════════════════════════════
        // DASHBOARDS — Standalone Dashboard List Tab (/dashboards)
        // ═══════════════════════════════════════════════════════════════════
        {
          path: 'dashboards',
          name: 'dashboards',
          component: lazyView(() => import('@/views/DashboardsView.vue')),
          meta: { title: 'Dashboards', viewerAllowed: true },
        },

        // DEPRECATED 2026-03-01: /custom-dashboard → /editor
        {
          path: 'custom-dashboard',
          redirect: '/editor',
        },

        // DEPRECATED 2026-02-23: DashboardView-Legacy → Hardware
        {
          path: 'dashboard-legacy',
          redirect: '/hardware',
        },

        // DEPRECATED redirects (backward compatibility)
        {
          path: 'devices',
          name: 'devices',
          redirect: '/hardware',
        },
        {
          path: 'devices/:espId',
          name: 'device-detail',
          redirect: (to) => ({
            path: '/hardware',
            query: { openSettings: to.params.espId as string },
          }),
        },
        {
          path: 'mock-esp',
          redirect: '/hardware',
        },
        {
          path: 'mock-esp/:espId',
          redirect: (to) => ({
            path: '/hardware',
            query: { openSettings: to.params.espId as string },
          }),
        },
        // DEPRECATED 2026-01-23: DatabaseExplorerView → System Monitor
        {
          path: 'database',
          name: 'database',
          redirect: '/system-monitor?tab=database',
        },
        // DEPRECATED 2026-01-23: LogViewerView → System Monitor
        {
          path: 'logs',
          name: 'logs',
          redirect: '/system-monitor?tab=logs',
        },
        {
          path: 'system-monitor',
          name: 'system-monitor',
          component: lazyView(() => import('@/views/SystemMonitorView.vue')),
          meta: { requiresAdmin: true, title: 'System Monitor' },
        },
        // DEPRECATED 2026-01-24: AuditLogView → System Monitor (Phase 1 Konsolidierung)
        // Alle Funktionen sind in SystemMonitorView Tab "Ereignisse" verfügbar
        {
          path: 'audit',
          name: 'audit',
          redirect: '/system-monitor?tab=events',
        },
        {
          path: 'users',
          name: 'users',
          component: lazyView(() => import('@/views/UserManagementView.vue')),
          meta: { requiresAdmin: true, title: 'Benutzerverwaltung' },
        },
        {
          path: 'system-config',
          name: 'system-config',
          component: lazyView(() => import('@/views/SystemConfigView.vue')),
          meta: { requiresAdmin: true, title: 'Systemkonfiguration' },
        },
        {
          path: 'load-test',
          name: 'load-test',
          component: lazyView(() => import('@/views/LoadTestView.vue')),
          meta: { requiresAdmin: true, title: 'Last-Tests' },
        },
        // DEPRECATED 2026-01-23: MqttLogView → System Monitor
        {
          path: 'mqtt-log',
          name: 'mqtt-log',
          redirect: '/system-monitor?tab=mqtt',
        },
        // Phase 4D: Wartung in Health-Tab integriert (Auftrag Step 8)
        {
          path: 'maintenance',
          name: 'maintenance',
          redirect: '/system-monitor?tab=health',
        },
        {
          path: 'access-denied',
          name: 'access-denied',
          component: lazyView(() => import('@/views/AccessDeniedView.vue')),
          meta: { title: 'Zugriff verweigert', viewerAllowed: true },
        },
        {
          path: 'plugins',
          name: 'plugins',
          component: lazyView(() => import('@/views/PluginsView.vue')),
          meta: { requiresAdmin: true, title: 'AutoOps Plugins' },
        },
        {
          path: 'email',
          name: 'email-postfach',
          component: lazyView(() => import('@/views/EmailPostfachView.vue')),
          meta: { requiresAdmin: true, title: 'E-Mail-Postfach' },
        },
        {
          path: 'sensors',
          name: 'sensors',
          component: lazyView(() => import('@/views/SensorsView.vue')),
          meta: { title: 'Komponenten' },
        },
        // DEPRECATED 2025-01-04: ActuatorsView → SensorsView with tab query
        {
          path: 'actuators',
          name: 'actuators',
          redirect: '/sensors?tab=actuators',
        },
        {
          path: 'logic',
          name: 'logic',
          component: lazyView(() => import('@/views/LogicView.vue')),
          meta: { title: 'Automatisierung' },
        },
        {
          path: 'logic/:ruleId',
          name: 'logic-rule',
          component: lazyView(() => import('@/views/LogicView.vue')),
          meta: { title: 'Automatisierung' },
        },
        {
          path: 'settings',
          name: 'settings',
          component: lazyView(() => import('@/views/SettingsView.vue')),
          meta: { title: 'Einstellungen' },
        },
        {
          path: 'calibration',
          name: 'calibration',
          component: lazyView(() => import('@/views/CalibrationView.vue')),
          meta: { requiresAdmin: true, title: 'Kalibrierung' },
        },
        // DEPRECATED 2026-03-01: SensorHistoryView → Monitor (integriert in Monitor L3 SlideOver)
        {
          path: 'sensor-history',
          name: 'sensor-history',
          redirect: '/monitor',
        },
      ],
    },

    // Catch-all redirect
    {
      path: '/not-found',
      name: 'not-found',
      component: lazyView(() => import('@/views/NotFoundView.vue')),
      meta: { requiresAuth: false },
    },

    {
      path: '/:pathMatch(.*)*',
      redirect: (to) => ({
        name: 'not-found',
        query: { from: to.fullPath },
      }),
    },
  ],
})

// Dynamic import failure recovery — when browser runs out of resources
// (ERR_INSUFFICIENT_RESOURCES) or chunks fail to load, reload the page once.
const RELOAD_COOLDOWN_MS = 10_000
let scheduledReloadTimer: number | null = null
router.onError((error, to) => {
  if (
    error.message?.includes('Failed to fetch dynamically imported module') ||
    error.message?.includes('Loading chunk') ||
    error.message?.includes('ERR_INSUFFICIENT_RESOURCES')
  ) {
    const lastReload = sessionStorage.getItem('__route_reload_ts')
    const now = Date.now()
    const elapsedSinceReload = lastReload ? now - Number(lastReload) : RELOAD_COOLDOWN_MS
    if (elapsedSinceReload < RELOAD_COOLDOWN_MS) {
      const retryInMs = RELOAD_COOLDOWN_MS - elapsedSinceReload
      if (scheduledReloadTimer !== null) {
        window.clearTimeout(scheduledReloadTimer)
      }
      scheduledReloadTimer = window.setTimeout(() => {
        sessionStorage.setItem('__route_reload_ts', String(Date.now()))
        window.location.assign(to.fullPath)
      }, retryInMs)
      console.warn('[Router] Dynamic import failed repeatedly, scheduled reload retry', {
        path: to.fullPath,
        retry_in_ms: retryInMs,
      })
      return
    }
    if (scheduledReloadTimer !== null) {
      window.clearTimeout(scheduledReloadTimer)
      scheduledReloadTimer = null
    }
    sessionStorage.setItem('__route_reload_ts', String(now))
    window.location.assign(to.fullPath)
  }
})

router.afterEach((to) => {
  const redirectedFromPath = to.redirectedFrom?.path
  if (!redirectedFromPath) {
    return
  }
  const isLegacyRedirect = LEGACY_REDIRECT_PATTERNS.some((pattern) => pattern.test(redirectedFromPath))
  if (isLegacyRedirect) {
    const raw = localStorage.getItem(LEGACY_REDIRECT_TELEMETRY_KEY)
    const telemetry = raw ? JSON.parse(raw) as Record<string, { count: number; last_to: string; last_at: string }> : {}
    const current = telemetry[redirectedFromPath] ?? { count: 0, last_to: '', last_at: '' }
    telemetry[redirectedFromPath] = {
      count: current.count + 1,
      last_to: to.fullPath,
      last_at: new Date().toISOString(),
    }
    localStorage.setItem(LEGACY_REDIRECT_TELEMETRY_KEY, JSON.stringify(telemetry))
    console.info('[Router] Legacy redirect used', {
      from: redirectedFromPath,
      to: to.fullPath,
      rollout_plan: LEGACY_DECOMMISSION_PLAN,
      redirect_count: telemetry[redirectedFromPath].count,
    })
  }
})

// Navigation guards
router.beforeEach(async (to, _from, next) => {
  const authStore = useAuthStore()

  // Wait for auth status check if not done yet
  if (authStore.setupRequired === null) {
    try {
      await authStore.checkAuthStatus()
    } catch {
      if (to.meta.requiresAuth) {
        return next({ name: 'login', query: { redirect: to.fullPath } })
      }
      return next()
    }
  }

  // Redirect to setup if required
  if (authStore.setupRequired && to.name !== 'setup') {
    return next({ name: 'setup' })
  }

  // Check if route requires auth
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return next({ name: 'login', query: { redirect: to.fullPath } })
  }

  // Check if route requires admin
  if (to.meta.requiresAdmin && !authStore.isAdmin) {
    return next({
      name: 'access-denied',
      query: { from: to.fullPath },
    })
  }

  // Viewer guard: viewers may only access viewerAllowed routes
  // TODO replace isViewer with capability check
  if (authStore.isViewer && to.meta.requiresAuth && !to.meta.viewerAllowed) {
    return next({ name: 'monitor' })
  }

  // Redirect authenticated users away from login/setup
  if (authStore.isAuthenticated && (to.name === 'login' || to.name === 'setup')) {
    // TODO replace isViewer with capability check
    return next({ name: authStore.isViewer ? 'monitor' : 'dashboards' })
  }

  next()
})

export default router
