import { defineStore } from 'pinia'
import { ref, computed, markRaw } from 'vue'
import type { Component } from 'vue'

// ── Types ───────────────────────────────────────────────────────────────

export type ConfirmVariant = 'info' | 'warning' | 'danger'

export interface ConfirmOptions {
  title: string
  message: string
  variant: ConfirmVariant
  /** Override default confirm button text (default: variant-based) */
  confirmText?: string
  /** Override default cancel button text (default: 'Abbrechen') */
  cancelText?: string
  /** Override auto-selected icon */
  icon?: Component
}

interface ConfirmState extends ConfirmOptions {
  isOpen: boolean
  resolve: ((confirmed: boolean) => void) | null
}

export interface ContextMenuItem {
  id: string
  label: string
  icon?: Component
  shortcutHint?: string
  variant?: 'default' | 'danger'
  disabled?: boolean
  separator?: boolean
  action?: () => void | Promise<void>
}

interface ContextMenuState {
  isOpen: boolean
  x: number
  y: number
  items: ContextMenuItem[]
}

// ── Store ───────────────────────────────────────────────────────────────

export const useUiStore = defineStore('ui', () => {
  // ── Sidebar State ──
  const sidebarCollapsed = ref(false)

  // ── Command Palette State ──
  const commandPaletteOpen = ref(false)

  // ── Confirm Dialog State ──
  const confirmState = ref<ConfirmState>({
    isOpen: false,
    title: '',
    message: '',
    variant: 'info',
    resolve: null,
  })

  // ── Context Menu State ──
  const contextMenuState = ref<ContextMenuState>({
    isOpen: false,
    x: 0,
    y: 0,
    items: [],
  })

  // ── Modal Stack (Escape key priority: last in = first closed) ──
  const modalStack = ref<string[]>([])

  // ── Getters ──
  const hasOpenModal = computed(() => modalStack.value.length > 0)
  const topModal = computed(() =>
    modalStack.value.length > 0
      ? modalStack.value[modalStack.value.length - 1]
      : null
  )

  // ── Modal Stack Management ──

  function pushModal(id: string): void {
    if (!modalStack.value.includes(id)) {
      modalStack.value.push(id)
    }
  }

  function popModal(id: string): void {
    const index = modalStack.value.indexOf(id)
    if (index !== -1) {
      modalStack.value.splice(index, 1)
    }
  }

  /**
   * Close the topmost modal/overlay. Returns true if something was closed.
   * Used by global Escape handler.
   */
  function closeTopModal(): boolean {
    if (modalStack.value.length === 0) return false
    const topId = modalStack.value[modalStack.value.length - 1]

    switch (topId) {
      case 'context-menu':
        closeContextMenu()
        return true
      case 'confirm-dialog':
        resolveConfirm(false)
        return true
      case 'command-palette':
        closeCommandPalette()
        return true
      default:
        // Unknown modal - just pop it
        modalStack.value.pop()
        return true
    }
  }

  // ── Confirm Dialog Actions ──

  /**
   * Show a confirm dialog and return a Promise that resolves to true/false.
   * Usage: const confirmed = await uiStore.confirm({ title, message, variant })
   */
  function confirm(options: ConfirmOptions): Promise<boolean> {
    return new Promise<boolean>((resolve) => {
      confirmState.value = {
        ...options,
        icon: options.icon ? markRaw(options.icon) : undefined,
        isOpen: true,
        resolve,
      }
      pushModal('confirm-dialog')
    })
  }

  function resolveConfirm(confirmed: boolean): void {
    const resolveFn = confirmState.value.resolve
    confirmState.value = {
      isOpen: false,
      title: '',
      message: '',
      variant: 'info',
      resolve: null,
    }
    popModal('confirm-dialog')
    if (resolveFn) resolveFn(confirmed)
  }

  // ── Context Menu Actions ──

  function openContextMenu(x: number, y: number, items: ContextMenuItem[]): void {
    // Close any existing context menu first
    if (contextMenuState.value.isOpen) {
      closeContextMenu()
    }
    contextMenuState.value = {
      isOpen: true,
      x,
      y,
      items: items.map(item => ({
        ...item,
        icon: item.icon ? markRaw(item.icon) : undefined,
      })),
    }
    pushModal('context-menu')
  }

  function closeContextMenu(): void {
    contextMenuState.value = { isOpen: false, x: 0, y: 0, items: [] }
    popModal('context-menu')
  }

  // ── Command Palette Actions ──

  function openCommandPalette(): void {
    commandPaletteOpen.value = true
    pushModal('command-palette')
  }

  function closeCommandPalette(): void {
    commandPaletteOpen.value = false
    popModal('command-palette')
  }

  function toggleCommandPalette(): void {
    if (commandPaletteOpen.value) {
      closeCommandPalette()
    } else {
      openCommandPalette()
    }
  }

  // ── Sidebar ──

  function toggleSidebar(): void {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  return {
    // State
    sidebarCollapsed,
    commandPaletteOpen,
    confirmState,
    contextMenuState,
    modalStack,

    // Getters
    hasOpenModal,
    topModal,

    // Actions - Confirm
    confirm,
    resolveConfirm,

    // Actions - Context Menu
    openContextMenu,
    closeContextMenu,

    // Actions - Command Palette
    openCommandPalette,
    closeCommandPalette,
    toggleCommandPalette,

    // Actions - Modal Stack
    pushModal,
    popModal,
    closeTopModal,

    // Actions - Sidebar
    toggleSidebar,
  }
})
