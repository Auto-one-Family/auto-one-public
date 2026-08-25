/**
 * useQuickActions — Context-dependent Quick Action definitions
 *
 * Watches the current route and provides view-specific actions
 * to the QuickActionBall. Only hardware view actions are shown.
 */

import { watch, onUnmounted, markRaw } from 'vue'
import { useRoute } from 'vue-router'
import { useQuickActionStore } from '@/shared/stores/quickAction.store'
import type { QuickAction, ViewContext } from '@/shared/stores/quickAction.store'
import { Plus, Inbox, LayoutGrid } from 'lucide-vue-next'
import { useDashboardStore } from '@/shared/stores/dashboard.store'

/** Determine ViewContext from route path */
function resolveViewContext(path: string): ViewContext {
  if (path.startsWith('/hardware')) return 'hardware'
  if (path.startsWith('/monitor')) return 'monitor'
  if (path.startsWith('/dashboards')) return 'dashboards'
  if (path.startsWith('/logic')) return 'logic'
  if (path.startsWith('/system-monitor')) return 'system-monitor'
  if (path.startsWith('/editor')) return 'editor'
  if (path.startsWith('/settings')) return 'settings'
  if (path.startsWith('/sensors')) return 'sensors'
  if (path.startsWith('/plugins')) return 'plugins'
  return 'other'
}

function buildContextActions(
  view: ViewContext,
  dashStore: ReturnType<typeof useDashboardStore>,
  quickActionStore: ReturnType<typeof useQuickActionStore>,
): QuickAction[] {
  if (view === 'hardware') {
    return [
      {
        id: 'hw-create-mock',
        label: 'Mock hinzufügen',
        icon: markRaw(Plus),
        category: 'context',
        handler: () => { dashStore.showCreateMock = true },
      },
      {
        id: 'hw-pending-devices',
        label: 'Ausstehende Geräte',
        icon: markRaw(Inbox),
        category: 'context',
        handler: () => { dashStore.showPendingPanel = true },
      },
    ]
  }

  // AUT-901: FAB widget catalog is reachable only in Monitor + Dashboards.
  // The Editor keeps its own in-view catalog; other views have no widget
  // placement. The handler opens the dormant 'widgets' sub-panel
  // (QuickWidgetPanel). AUT-730 will later move this route->action mapping into
  // a quick-action-config.ts; for now this minimal inline computed lives in the
  // existing useQuickActions file and stays conflict-free (AUT-730 integrates
  // this 'add-widget' action rather than duplicating it).
  if (view === 'monitor' || view === 'dashboards') {
    return [
      {
        id: 'add-widget',
        label: 'Widget hinzufügen',
        icon: markRaw(LayoutGrid),
        category: 'context',
        handler: () => { quickActionStore.setActivePanel('widgets') },
      },
    ]
  }

  return []
}

/**
 * Composable: watches route changes and updates the quick action store
 * with context-appropriate actions.
 *
 * Must be called inside a component setup function.
 */
export function useQuickActions(): void {
  const route = useRoute()
  const quickActionStore = useQuickActionStore()
  const dashStore = useDashboardStore()

  const stopWatch = watch(
    () => route.path,
    (path) => {
      const view = resolveViewContext(path)
      quickActionStore.setViewContext(view)
      quickActionStore.setContextActions(buildContextActions(view, dashStore, quickActionStore))
      quickActionStore.setGlobalActions([])
    },
    { immediate: true },
  )

  onUnmounted(() => {
    stopWatch()
  })
}
