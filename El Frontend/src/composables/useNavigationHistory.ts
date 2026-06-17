/**
 * useNavigationHistory — Route-Tracking via router.afterEach()
 *
 * Tracks visited routes in localStorage for MRU (Most Recently Used) display
 * in the QuickNavPanel. Supports favorites that persist across sessions.
 *
 * Storage keys:
 *   ao_nav_history   — Last 20 visited routes (deduplicated by path)
 *   ao_nav_favorites — User-pinned routes
 */

import { ref, computed, onUnmounted } from 'vue'
import { useRouter, type RouteLocationNormalized } from 'vue-router'
import type { Component } from 'vue'
import { markRaw } from 'vue'
import {
  LayoutDashboard,
  Cpu,
  Activity,
  Workflow,
  Settings,
  MonitorDot,
  PenTool,
  Gauge,
  Users,
  Wrench,
  Zap,
  FileText,
} from 'lucide-vue-next'

// ── Types ────────────────────────────────────────────────────────────────

export interface NavHistoryItem {
  path: string
  label: string
  icon: Component
  timestamp: number
}

interface StoredNavItem {
  path: string
  label: string
  iconName: string
  timestamp: number
}

// ── Constants ────────────────────────────────────────────────────────────

const STORAGE_KEY_HISTORY = 'ao_nav_history'
const STORAGE_KEY_FAVORITES = 'ao_nav_favorites'
const MAX_HISTORY = 20
const MAX_RECENT = 5

/** Map route paths to human-readable labels + icons */
const ROUTE_META: Record<string, { label: string; iconName: string }> = {
  '/': { label: 'Dashboard', iconName: 'LayoutDashboard' },
  '/hardware': { label: 'Hardware', iconName: 'Cpu' },
  '/monitor': { label: 'Monitor', iconName: 'Activity' },
  '/logic': { label: 'Automatisierung', iconName: 'Workflow' },
  '/settings': { label: 'Einstellungen', iconName: 'Settings' },
  '/system-monitor': { label: 'System Monitor', iconName: 'MonitorDot' },
  '/editor': { label: 'Dashboard Editor', iconName: 'PenTool' },
  '/sensors': { label: 'Sensoren & Aktoren', iconName: 'Gauge' },
  '/users': { label: 'Benutzerverwaltung', iconName: 'Users' },
  '/maintenance': { label: 'Wartung', iconName: 'Wrench' },
  '/load-test': { label: 'Lasttest', iconName: 'Zap' },
  '/system-config': { label: 'Systemkonfiguration', iconName: 'Settings' },
  '/access-denied': { label: 'Zugriff verweigert', iconName: 'FileText' },
}

const ICON_MAP: Record<string, Component> = {
  LayoutDashboard: markRaw(LayoutDashboard),
  Cpu: markRaw(Cpu),
  Activity: markRaw(Activity),
  Workflow: markRaw(Workflow),
  Settings: markRaw(Settings),
  MonitorDot: markRaw(MonitorDot),
  PenTool: markRaw(PenTool),
  Gauge: markRaw(Gauge),
  Users: markRaw(Users),
  Wrench: markRaw(Wrench),
  Zap: markRaw(Zap),
  FileText: markRaw(FileText),
}

// ── Helpers ──────────────────────────────────────────────────────────────

function resolveIcon(iconName: string): Component {
  return ICON_MAP[iconName] ?? ICON_MAP['FileText']
}

function resolveRouteLabel(route: RouteLocationNormalized): string {
  const basePath = '/' + (route.path.split('/')[1] ?? '')
  const meta = ROUTE_META[basePath]
  if (!meta) return route.path

  // Append sub-context if available (e.g., zone name, dashboard name)
  if (route.params.zoneId) return `${meta.label} — Zone`
  if (route.params.dashboardId) return `${meta.label} — Dashboard`
  if (route.params.ruleId) return `${meta.label} — Regel`
  return meta.label
}

function resolveRouteIconName(path: string): string {
  const basePath = '/' + (path.split('/')[1] ?? '')
  return ROUTE_META[basePath]?.iconName ?? 'FileText'
}

function loadFromStorage(key: string): StoredNavItem[] {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return []
    return JSON.parse(raw) as StoredNavItem[]
  } catch {
    return []
  }
}

function saveToStorage(key: string, items: StoredNavItem[]): void {
  try {
    localStorage.setItem(key, JSON.stringify(items))
  } catch {
    // localStorage full or blocked — silently ignore
  }
}

function storedToNav(item: StoredNavItem): NavHistoryItem {
  return {
    path: item.path,
    label: item.label,
    icon: resolveIcon(item.iconName),
    timestamp: item.timestamp,
  }
}

function navToStored(item: NavHistoryItem, iconName: string): StoredNavItem {
  return {
    path: item.path,
    label: item.label,
    iconName,
    timestamp: item.timestamp,
  }
}

// ── Composable ───────────────────────────────────────────────────────────

export function useNavigationHistory() {
  const router = useRouter()

  // Reactive state
  const history = ref<NavHistoryItem[]>(
    loadFromStorage(STORAGE_KEY_HISTORY).map(storedToNav),
  )
  const favorites = ref<NavHistoryItem[]>(
    loadFromStorage(STORAGE_KEY_FAVORITES).map(storedToNav),
  )

  /** Last 5 visited routes (MRU) */
  const recentNavItems = computed<NavHistoryItem[]>(() =>
    history.value.slice(0, MAX_RECENT),
  )

  /** Check if a path is in favorites */
  function isFavorite(path: string): boolean {
    return favorites.value.some((f) => f.path === path)
  }

  /** Add a route to favorites */
  function addFavorite(path: string): void {
    if (isFavorite(path)) return

    const iconName = resolveRouteIconName(path)
    const basePath = '/' + (path.split('/')[1] ?? '')
    const label = ROUTE_META[basePath]?.label ?? path

    const item: NavHistoryItem = {
      path,
      label,
      icon: resolveIcon(iconName),
      timestamp: Date.now(),
    }

    favorites.value = [item, ...favorites.value]
    saveToStorage(
      STORAGE_KEY_FAVORITES,
      favorites.value.map((f) =>
        navToStored(f, resolveRouteIconName(f.path)),
      ),
    )
  }

  /** Remove a route from favorites */
  function removeFavorite(path: string): void {
    favorites.value = favorites.value.filter((f) => f.path !== path)
    saveToStorage(
      STORAGE_KEY_FAVORITES,
      favorites.value.map((f) =>
        navToStored(f, resolveRouteIconName(f.path)),
      ),
    )
  }

  /** Toggle favorite status for a path */
  function toggleFavorite(path: string): void {
    if (isFavorite(path)) {
      removeFavorite(path)
    } else {
      addFavorite(path)
    }
  }

  // Track route changes
  const removeAfterEach = router.afterEach((to) => {
    // Skip non-auth routes (login, setup)
    if (to.meta.requiresAuth === false) return

    const iconName = resolveRouteIconName(to.path)
    const label = resolveRouteLabel(to)

    const newItem: NavHistoryItem = {
      path: to.path,
      label,
      icon: resolveIcon(iconName),
      timestamp: Date.now(),
    }

    // Deduplicate: remove existing entry with same path, prepend new
    const filtered = history.value.filter((h) => h.path !== to.path)
    history.value = [newItem, ...filtered].slice(0, MAX_HISTORY)

    saveToStorage(
      STORAGE_KEY_HISTORY,
      history.value.map((h) =>
        navToStored(h, resolveRouteIconName(h.path)),
      ),
    )
  })

  onUnmounted(() => {
    removeAfterEach()
  })

  return {
    recentNavItems,
    favorites,
    isFavorite,
    addFavorite,
    removeFavorite,
    toggleFavorite,
  }
}
