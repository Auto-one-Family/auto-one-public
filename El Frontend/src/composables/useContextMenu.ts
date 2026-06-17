/**
 * Context Menu Composable
 *
 * Thin wrapper around uiStore.openContextMenu.
 * Handles preventDefault and viewport boundary detection.
 */

import { useUiStore } from '@/shared/stores/ui.store'
import type { ContextMenuItem } from '@/shared/stores/ui.store'

export function useContextMenu() {
  const uiStore = useUiStore()

  /**
   * Open the context menu at the mouse position.
   * Call this from @contextmenu.prevent handlers.
   */
  function open(event: MouseEvent, items: ContextMenuItem[]): void {
    event.preventDefault()
    event.stopPropagation()
    uiStore.openContextMenu(event.clientX, event.clientY, items)
  }

  function close(): void {
    uiStore.closeContextMenu()
  }

  return { open, close }
}
