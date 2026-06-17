/**
 * useGrafana Composable
 *
 * Builds Grafana panel/dashboard embed URLs for iframe integration.
 * Requires Grafana environment:
 *   GF_SECURITY_ALLOW_EMBEDDING=true
 *   GF_AUTH_ANONYMOUS_ENABLED=true
 *   GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer
 *
 * @see docker-compose.yml grafana service
 */

import { computed, ref, type Ref } from 'vue'

/** Grafana base URL (same host, port 3000) */
export const GRAFANA_BASE_URL = `${window.location.protocol}//${window.location.hostname}:3000`

/** Known dashboard UIDs from provisioned dashboards */
export const GRAFANA_DASHBOARDS = {
  SYSTEM_HEALTH: 'automationone-system-health',
} as const

/** Known panel IDs from system-health dashboard */
export const GRAFANA_PANELS = {
  SERVER_STATUS: 1,
  MQTT_STATUS: 2,
  DATABASE_STATUS: 3,
  FRONTEND_ERRORS: 4,
  ESP_ONLINE: 5,
  ACTIVE_ALERTS: 6,
  CPU: 7,
  MEMORY: 8,
  UPTIME: 9,
} as const

export interface GrafanaPanelOptions {
  /** Dashboard UID */
  dashboardUid: string
  /** Panel ID within the dashboard */
  panelId: number
  /** Time range (Grafana syntax: now-1h, now-6h, now-24h, now-7d) */
  from?: string
  /** Time range end (default: now) */
  to?: string
  /** Refresh interval (e.g., '10s', '30s', '1m', '5m') */
  refresh?: string
  /** Theme override (dark matches AutomationOne design) */
  theme?: 'dark' | 'light'
  /** Template variables (key=value pairs) */
  vars?: Record<string, string>
}

export interface GrafanaDashboardOptions {
  /** Dashboard UID */
  dashboardUid: string
  /** Time range */
  from?: string
  to?: string
  /** Refresh interval */
  refresh?: string
  /** Theme */
  theme?: 'dark' | 'light'
  /** Template variables */
  vars?: Record<string, string>
  /** Kiosk mode (hides Grafana chrome) */
  kiosk?: boolean
}

/**
 * Build a Grafana solo panel embed URL (single panel, no chrome).
 */
function buildPanelUrl(options: GrafanaPanelOptions): string {
  const {
    dashboardUid,
    panelId,
    from = 'now-1h',
    to = 'now',
    refresh = '30s',
    theme = 'dark',
    vars = {},
  } = options

  const params = new URLSearchParams({
    orgId: '1',
    from,
    to,
    theme,
    panelId: String(panelId),
    refresh,
  })

  // Add template variables
  for (const [key, value] of Object.entries(vars)) {
    params.set(`var-${key}`, value)
  }

  return `${GRAFANA_BASE_URL}/d-solo/${dashboardUid}?${params.toString()}`
}

/**
 * Build a Grafana full dashboard embed URL.
 */
function buildDashboardUrl(options: GrafanaDashboardOptions): string {
  const {
    dashboardUid,
    from = 'now-1h',
    to = 'now',
    refresh = '30s',
    theme = 'dark',
    kiosk = true,
    vars = {},
  } = options

  const params = new URLSearchParams({
    orgId: '1',
    from,
    to,
    theme,
    refresh,
  })

  if (kiosk) {
    params.set('kiosk', '')
  }

  for (const [key, value] of Object.entries(vars)) {
    params.set(`var-${key}`, value)
  }

  return `${GRAFANA_BASE_URL}/d/${dashboardUid}?${params.toString()}`
}

/**
 * Composable for Grafana panel embedding.
 *
 * @example
 * const { panelUrl, isAvailable } = useGrafana({
 *   dashboardUid: GRAFANA_DASHBOARDS.SYSTEM_HEALTH,
 *   panelId: GRAFANA_PANELS.CPU,
 *   from: 'now-6h',
 * })
 */
export function useGrafana(options: Ref<GrafanaPanelOptions> | GrafanaPanelOptions) {
  const isAvailable = ref(true)

  const panelUrl = computed(() => {
    const opts = 'value' in options ? options.value : options
    return buildPanelUrl(opts)
  })

  return {
    panelUrl,
    isAvailable,
    GRAFANA_BASE_URL,
  }
}

export function useGrafanaDashboard(options: Ref<GrafanaDashboardOptions> | GrafanaDashboardOptions) {
  const isAvailable = ref(true)

  const dashboardUrl = computed(() => {
    const opts = 'value' in options ? options.value : options
    return buildDashboardUrl(opts)
  })

  return {
    dashboardUrl,
    isAvailable,
    GRAFANA_BASE_URL,
  }
}
