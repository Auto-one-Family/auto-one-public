<script setup lang="ts">
/**
 * CommandPalette
 *
 * Centered glass-modal with search input and categorized results.
 * Opened via Ctrl+K, reads state from uiStore.
 * Supports keyboard navigation: ArrowUp/Down, Enter, Escape.
 */

import { nextTick, onUnmounted, ref, watch } from 'vue'
import { useScrollLock } from '@/composables/useScrollLock'
import { Search, CornerDownLeft } from 'lucide-vue-next'
import { useUiStore } from '@/shared/stores'
import { useCommandPalette } from '@/composables/useCommandPalette'

const uiStore = useUiStore()
const palette = useCommandPalette()
const inputRef = ref<HTMLInputElement | null>(null)
const listRef = ref<HTMLDivElement | null>(null)
const scrollLock = useScrollLock()

// Auto-focus input and reset query when palette opens
watch(() => uiStore.commandPaletteOpen, async (open) => {
  if (open) {
    scrollLock.lock()
    palette.resetQuery()
    await nextTick()
    inputRef.value?.focus()
  } else {
    scrollLock.unlock()
  }
})

onUnmounted(() => {
  scrollLock.unlock()
})

function handleKeydown(e: KeyboardEvent): void {
  switch (e.key) {
    case 'ArrowDown':
      e.preventDefault()
      palette.moveSelection(1)
      scrollToSelected()
      break
    case 'ArrowUp':
      e.preventDefault()
      palette.moveSelection(-1)
      scrollToSelected()
      break
    case 'Enter':
      e.preventDefault()
      handleSelect()
      break
    case 'Escape':
      e.preventDefault()
      uiStore.closeCommandPalette()
      break
  }
}

function handleSelect(): void {
  const executed = palette.executeSelected()
  if (executed) {
    uiStore.closeCommandPalette()
  }
}

function handleItemClick(index: number): void {
  palette.selectedIndex.value = index
  handleSelect()
}

function handleOverlayClick(): void {
  uiStore.closeCommandPalette()
}

function scrollToSelected(): void {
  const el = listRef.value?.querySelector('[data-selected="true"]')
  el?.scrollIntoView({ block: 'nearest' })
}

// Reset selection when query changes
watch(() => palette.query.value, () => {
  palette.selectedIndex.value = 0
})
</script>

<template>
  <Teleport to="body">
    <Transition name="palette">
      <div
        v-if="uiStore.commandPaletteOpen"
        class="palette-overlay"
        @click="handleOverlayClick"
      >
        <div
          class="palette"
          @click.stop
          @keydown="handleKeydown"
        >
          <!-- Search Input -->
          <div class="palette__search">
            <Search class="palette__search-icon" />
            <input
              ref="inputRef"
              v-model="palette.query.value"
              class="palette__input"
              placeholder="Suche nach Befehlen, Geräten, Views..."
              type="text"
              autocomplete="off"
              spellcheck="false"
            />
            <kbd class="palette__kbd">Esc</kbd>
          </div>

          <!-- Results -->
          <div ref="listRef" class="palette__results" role="listbox" aria-label="Suchergebnisse">
            <template v-if="palette.filteredCommands.value.length === 0">
              <div class="palette__empty">
                Keine Ergebnisse für "{{ palette.query.value }}"
              </div>
            </template>

            <template v-for="(items, category) in palette.groupedCommands.value" :key="category">
              <div class="palette__category">
                {{ palette.categoryLabels[category] || category }}
              </div>
              <button
                v-for="item in items"
                :key="item.id"
                :data-selected="palette.filteredCommands.value.indexOf(item) === palette.selectedIndex.value"
                :class="[
                  'palette__item',
                  { 'palette__item--selected': palette.filteredCommands.value.indexOf(item) === palette.selectedIndex.value }
                ]"
                role="option"
                :aria-selected="palette.filteredCommands.value.indexOf(item) === palette.selectedIndex.value"
                @click="handleItemClick(palette.filteredCommands.value.indexOf(item))"
                @mouseenter="palette.selectedIndex.value = palette.filteredCommands.value.indexOf(item)"
              >
                <component
                  :is="item.icon"
                  v-if="item.icon"
                  class="palette__item-icon"
                />
                <span class="palette__item-label">{{ item.label }}</span>
                <CornerDownLeft
                  v-if="palette.filteredCommands.value.indexOf(item) === palette.selectedIndex.value"
                  class="palette__item-enter"
                />
              </button>
            </template>
          </div>

          <!-- Footer -->
          <div class="palette__footer">
            <span class="palette__hint">
              <kbd>↑↓</kbd> Navigieren
            </span>
            <span class="palette__hint">
              <kbd>↵</kbd> Auswählen
            </span>
            <span class="palette__hint">
              <kbd>Esc</kbd> Schließen
            </span>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.palette-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-tooltip);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 20vh;
  background: var(--backdrop-color-light);
  -webkit-backdrop-filter: blur(var(--backdrop-blur-light));
  backdrop-filter: blur(var(--backdrop-blur-light));
}

.palette {
  width: 100%;
  max-width: 560px;
  background-color: var(--color-bg-secondary);
  border: 1px solid var(--glass-border, rgba(255, 255, 255, 0.06));
  border-radius: var(--radius-lg, 14px);
  box-shadow: var(--glass-shadow, 0 8px 32px rgba(0, 0, 0, 0.4));
  overflow: hidden;
}

/* Search */
.palette__search {
  display: flex;
  align-items: center;
  gap: var(--space-3, 12px);
  padding: var(--space-3, 12px) var(--space-4, 16px);
  border-bottom: 1px solid var(--glass-border, rgba(255, 255, 255, 0.06));
}

.palette__search-icon {
  width: 20px;
  height: 20px;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.palette__input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--color-text-primary);
  font-size: var(--text-base, 16px);
  font-family: inherit;
}

.palette__input::placeholder {
  color: var(--color-text-muted);
}

.palette__kbd {
  padding: 2px 6px;
  font-size: var(--text-xs, 11px);
  color: var(--color-text-muted);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border, rgba(255, 255, 255, 0.06));
  border-radius: var(--radius-sm, 6px);
  font-family: inherit;
}

/* Results */
.palette__results {
  max-height: 320px;
  overflow-y: auto;
  padding: var(--space-1, 4px);
}

.palette__empty {
  padding: var(--space-6, 24px) var(--space-4, 16px);
  text-align: center;
  color: var(--color-text-muted);
  font-size: var(--text-sm, 14px);
}

.palette__category {
  padding: var(--space-2, 8px) var(--space-3, 12px) var(--space-1, 4px);
  font-size: var(--text-xs, 11px);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.palette__item {
  display: flex;
  align-items: center;
  gap: var(--space-3, 12px);
  width: 100%;
  padding: var(--space-2, 8px) var(--space-3, 12px);
  border: none;
  border-radius: var(--radius-sm, 6px);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: var(--text-sm, 14px);
  cursor: pointer;
  transition: all var(--transition-fast, 120ms) ease;
  text-align: left;
}

.palette__item:hover,
.palette__item--selected {
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.palette__item-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  opacity: 0.6;
}

.palette__item--selected .palette__item-icon {
  opacity: 1;
}

.palette__item-label {
  flex: 1;
}

.palette__item-enter {
  width: 14px;
  height: 14px;
  color: var(--color-text-muted);
}

/* Footer */
.palette__footer {
  display: flex;
  gap: var(--space-4, 16px);
  padding: var(--space-2, 8px) var(--space-4, 16px);
  border-top: 1px solid var(--glass-border, rgba(255, 255, 255, 0.06));
}

.palette__hint {
  font-size: var(--text-xs, 11px);
  color: var(--color-text-muted);
  display: flex;
  align-items: center;
  gap: var(--space-1, 4px);
}

.palette__hint kbd {
  padding: 1px 4px;
  font-size: var(--text-xxs);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border, rgba(255, 255, 255, 0.06));
  border-radius: var(--radius-xs);
  font-family: inherit;
}

/* Transitions */
.palette-enter-active,
.palette-leave-active {
  transition: opacity var(--transition-fast, 120ms) ease;
}

.palette-enter-active .palette,
.palette-leave-active .palette {
  transition: transform var(--transition-fast, 120ms) ease,
              opacity var(--transition-fast, 120ms) ease;
}

.palette-enter-from,
.palette-leave-to {
  opacity: 0;
}

.palette-enter-from .palette,
.palette-leave-to .palette {
  transform: scale(0.95) translateY(-10px);
  opacity: 0;
}
</style>
