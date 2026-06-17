/**
 * Command Palette Composable
 *
 * Singleton registry for command palette items with fuzzy search.
 * Commands are registered with categories and searched via query.
 * Max 10 results shown, keyboard navigation via ArrowUp/Down/Enter.
 */

import { ref, computed } from 'vue'
import type { Component } from 'vue'

// ── Types ──────────────────────────────────────────────────────────────

export interface CommandItem {
  id: string
  label: string
  category: 'navigation' | 'devices' | 'actions' | 'rules' | 'sensors'
  /** Lucide icon component (wrap with markRaw) */
  icon?: Component
  /** Additional search terms beyond label */
  searchTerms?: string[]
  /** Action executed when command is selected */
  action: () => void | Promise<void>
}

// ── Constants ──────────────────────────────────────────────────────────

const MAX_RESULTS = 10

// ── Singleton State ────────────────────────────────────────────────────

const commands = ref<CommandItem[]>([])
const query = ref('')
const selectedIndex = ref(0)

// ── Fuzzy Search ───────────────────────────────────────────────────────

/**
 * Simple fuzzy match: all query characters must appear in target in order.
 * Returns true if the query characters are found sequentially in the target.
 */
function fuzzyMatch(target: string, search: string): boolean {
  const lower = target.toLowerCase()
  const q = search.toLowerCase()
  let j = 0
  for (let i = 0; i < lower.length && j < q.length; i++) {
    if (lower[i] === q[j]) j++
  }
  return j === q.length
}

function matchesQuery(item: CommandItem, q: string): boolean {
  if (fuzzyMatch(item.label, q)) return true
  if (item.searchTerms?.some(term => fuzzyMatch(term, q))) return true
  return false
}

// ── Computed ───────────────────────────────────────────────────────────

const filteredCommands = computed(() => {
  const q = query.value.trim()
  if (!q) return commands.value.slice(0, MAX_RESULTS)
  return commands.value
    .filter(item => matchesQuery(item, q))
    .slice(0, MAX_RESULTS)
})

/** Group filtered commands by category for display */
const groupedCommands = computed(() => {
  const groups: Record<string, CommandItem[]> = {}
  for (const cmd of filteredCommands.value) {
    if (!groups[cmd.category]) {
      groups[cmd.category] = []
    }
    groups[cmd.category].push(cmd)
  }
  return groups
})

const categoryLabels: Record<string, string> = {
  navigation: 'Navigation',
  devices: 'Geräte',
  actions: 'Aktionen',
  rules: 'Regeln',
  sensors: 'Sensoren',
}

// ── Public API ─────────────────────────────────────────────────────────

export function useCommandPalette() {
  /** Register commands (replaces existing with same IDs) */
  function registerCommands(items: CommandItem[]): void {
    const newIds = new Set(items.map(i => i.id))
    // Remove existing commands with same IDs, then add new ones
    commands.value = [
      ...commands.value.filter(c => !newIds.has(c.id)),
      ...items,
    ]
  }

  /** Unregister commands by ID prefix (e.g. 'device:' to remove all device commands) */
  function unregisterByPrefix(prefix: string): void {
    commands.value = commands.value.filter(c => !c.id.startsWith(prefix))
  }

  /** Reset search query */
  function resetQuery(): void {
    query.value = ''
    selectedIndex.value = 0
  }

  /** Move selection up or down */
  function moveSelection(direction: 1 | -1): void {
    const max = filteredCommands.value.length - 1
    if (max < 0) return
    selectedIndex.value = Math.max(0, Math.min(max, selectedIndex.value + direction))
  }

  /** Execute the currently selected command */
  function executeSelected(): CommandItem | null {
    const item = filteredCommands.value[selectedIndex.value]
    if (item) {
      item.action()
      return item
    }
    return null
  }

  return {
    // State
    query,
    selectedIndex,

    // Computed
    filteredCommands,
    groupedCommands,
    categoryLabels,

    // Actions
    registerCommands,
    unregisterByPrefix,
    resetQuery,
    moveSelection,
    executeSelected,
  }
}
