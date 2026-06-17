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
import { Plus, Inbox } from 'lucide-vue-next'
import { useDashboardStore } from '@/shared/stores/dashboard.store'

/** Determine ViewContext from route path */
function resolveViewContext(path: string): ViewContext {
  if (path.startsWith('/hardware')) return 'hardware'
  if (path.startsWith('/monitor')) return 'monitor'
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
): QuickAction[] {
  if (view !== 'hardware') return []
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
      quickActionStore.setContextActions(buildContextActions(view, dashStore))
      quickActionStore.setGlobalActions([])
    },
    { immediate: true },
  )

  onUnmounted(() => {
    stopWatch()
  })
}
