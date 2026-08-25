/**
 * useCrosshairSync — dashboard-level crosshair sync registry (AUT-912)
 *
 * Single source of truth for which dashboards have synchronized crosshair/tooltip
 * across their separate Multi-Sensor charts. Replaces the per-widget `syncTimeAxis`
 * toggle: a chart-spanning feature now has a chart-spanning (dashboard-level) control.
 *
 * Why a module-singleton ref instead of a per-widget prop:
 * dashboard widgets are mounted imperatively (`render(vnode, mountEl)`), not via
 * template. A shared reactive ref lets every mounted chart react to the toggle
 * WITHOUT a re-mount — the widget receives a stable `syncGroupId` once at mount and
 * derives its active state reactively from here.
 *
 * State is persisted in localStorage (a view preference, like the L2 accordion
 * state) — no server schema change.
 */
import { ref } from 'vue'

const STORAGE_KEY = 'automationone.crosshairSyncGroups'

function loadGroups(): Set<string> {
  if (typeof localStorage === 'undefined') return new Set()
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return new Set()
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed)
      ? new Set(parsed.filter((x): x is string => typeof x === 'string'))
      : new Set()
  } catch {
    return new Set()
  }
}

/** Module-singleton reactive state — shared across all imperative widget mounts. */
const activeGroups = ref<Set<string>>(loadGroups())

function persist(): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...activeGroups.value]))
  } catch {
    /* ignore quota / private-mode write errors — sync state is non-critical */
  }
}

export function useCrosshairSync() {
  /** True when crosshair sync is enabled for the given group (e.g. a dashboard/layout id). */
  function isActive(groupId?: string | null): boolean {
    return !!groupId && activeGroups.value.has(groupId)
  }

  function setActive(groupId: string, on: boolean): void {
    if (!groupId) return
    if (activeGroups.value.has(groupId) === on) return
    // Replace the Set so the ref triggers reactivity for all consumers.
    const next = new Set(activeGroups.value)
    if (on) next.add(groupId)
    else next.delete(groupId)
    activeGroups.value = next
    persist()
  }

  function toggle(groupId: string): void {
    setActive(groupId, !activeGroups.value.has(groupId))
  }

  return { activeGroups, isActive, setActive, toggle }
}
