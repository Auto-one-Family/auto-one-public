/**
 * Keyboard Shortcuts Composable
 *
 * Singleton registry for keyboard shortcuts with scope awareness.
 * Shortcuts are registered with a scope ('global' or view-specific like 'dashboard').
 * Single-key shortcuts are suppressed when an input element is focused.
 * Ctrl/Meta combos fire regardless of focus.
 */

export interface KeyboardShortcut {
  /** Key name (e.g. 'k', 'Escape', 'Delete', '?') */
  key: string
  ctrl?: boolean
  shift?: boolean
  alt?: boolean
  /** Handler receives the original KeyboardEvent */
  handler: (e: KeyboardEvent) => void
  /** Human-readable description for shortcuts help */
  description: string
  /** Scope: 'global' always active, others must be activated */
  scope: 'global' | string
}

// ── Singleton State ─────────────────────────────────────────────────────

const shortcuts = new Map<string, KeyboardShortcut>()
const activeScopes = new Set<string>(['global'])
let listenerAttached = false

// ── Helpers ─────────────────────────────────────────────────────────────

function generateId(shortcut: KeyboardShortcut): string {
  const parts: string[] = []
  if (shortcut.ctrl) parts.push('ctrl')
  if (shortcut.shift) parts.push('shift')
  if (shortcut.alt) parts.push('alt')
  parts.push(shortcut.key.toLowerCase())
  parts.push(shortcut.scope)
  return parts.join('+')
}

function isInputFocused(): boolean {
  const el = document.activeElement
  if (!el) return false
  const tag = el.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
  if ((el as HTMLElement).isContentEditable) return true
  return false
}

function hasModifier(shortcut: KeyboardShortcut): boolean {
  return !!(shortcut.ctrl || shortcut.alt)
}

function matchesEvent(shortcut: KeyboardShortcut, e: KeyboardEvent): boolean {
  // Key comparison (case-insensitive for letter keys)
  if (e.key.toLowerCase() !== shortcut.key.toLowerCase()) return false

  // Modifier checks (Ctrl or Meta for macOS)
  const ctrlOrMeta = e.ctrlKey || e.metaKey
  if (!!shortcut.ctrl !== ctrlOrMeta) return false
  if (!!shortcut.shift !== e.shiftKey) return false
  if (!!shortcut.alt !== e.altKey) return false

  return true
}

function handleKeydown(e: KeyboardEvent): void {
  for (const shortcut of shortcuts.values()) {
    // Skip if scope not active
    if (!activeScopes.has(shortcut.scope)) continue

    // Skip single-key shortcuts when input is focused
    if (isInputFocused() && !hasModifier(shortcut)) continue

    if (matchesEvent(shortcut, e)) {
      shortcut.handler(e)
      return // First match wins
    }
  }
}

function ensureListener(): void {
  if (listenerAttached) return
  document.addEventListener('keydown', handleKeydown, { capture: true })
  listenerAttached = true
}

// ── Public API ──────────────────────────────────────────────────────────

export function useKeyboardShortcuts() {
  /**
   * Register a keyboard shortcut. Returns an unregister function.
   * Call the unregister function in onUnmounted.
   */
  function register(shortcut: KeyboardShortcut): () => void {
    const id = generateId(shortcut)
    shortcuts.set(id, shortcut)
    ensureListener()
    return () => {
      shortcuts.delete(id)
    }
  }

  /** Activate a scope (e.g. when entering a view) */
  function activateScope(scope: string): void {
    activeScopes.add(scope)
  }

  /** Deactivate a scope (e.g. when leaving a view) */
  function deactivateScope(scope: string): void {
    activeScopes.delete(scope)
  }

  /** Get all registered shortcuts (for help dialog) */
  function getAll(): KeyboardShortcut[] {
    return Array.from(shortcuts.values())
  }

  /** Get shortcuts for a specific scope */
  function getByScope(scope: string): KeyboardShortcut[] {
    return Array.from(shortcuts.values()).filter(s => s.scope === scope)
  }

  return { register, activateScope, deactivateScope, getAll, getByScope }
}
