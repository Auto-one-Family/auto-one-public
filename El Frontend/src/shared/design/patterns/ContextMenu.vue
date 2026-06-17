<script setup lang="ts">
/**
 * ContextMenu
 *
 * Floating context menu rendered at mouse position.
 * Globally mounted in App.vue, reads state from uiStore.
 * Supports keyboard navigation, viewport boundary detection, and glass-morphism.
 */

import { computed, nextTick, ref, watch } from 'vue'
import { useUiStore } from '@/shared/stores/ui.store'

const uiStore = useUiStore()
const menuRef = ref<HTMLDivElement | null>(null)
const highlightedIndex = ref(-1)

const state = computed(() => uiStore.contextMenuState)
const isOpen = computed(() => state.value.isOpen)

// Filter out separators for keyboard navigation
const actionableItems = computed(() =>
  state.value.items.filter(item => !item.separator && !item.disabled)
)

// Viewport-clamped position
const adjustedPosition = computed(() => {
  const menuWidth = 200 // Estimated menu width
  const menuHeight = state.value.items.length * 36 + 16 // Estimated height
  const padding = 8

  let x = state.value.x
  let y = state.value.y

  // Clamp to viewport
  if (x + menuWidth + padding > window.innerWidth) {
    x = window.innerWidth - menuWidth - padding
  }
  if (y + menuHeight + padding > window.innerHeight) {
    y = window.innerHeight - menuHeight - padding
  }
  if (x < padding) x = padding
  if (y < padding) y = padding

  return { x, y }
})

function handleItemClick(item: typeof state.value.items[0]): void {
  if (item.disabled || item.separator) return
  uiStore.closeContextMenu()
  if (item.action) {
    item.action()
  }
}

function handleOverlayClick(): void {
  uiStore.closeContextMenu()
}

function handleKeydown(e: KeyboardEvent): void {
  if (!isOpen.value) return

  switch (e.key) {
    case 'ArrowDown': {
      e.preventDefault()
      const max = actionableItems.value.length - 1
      highlightedIndex.value = Math.min(highlightedIndex.value + 1, max)
      break
    }
    case 'ArrowUp': {
      e.preventDefault()
      highlightedIndex.value = Math.max(highlightedIndex.value - 1, 0)
      break
    }
    case 'Enter': {
      e.preventDefault()
      const item = actionableItems.value[highlightedIndex.value]
      if (item) handleItemClick(item)
      break
    }
    case 'Escape':
      e.preventDefault()
      e.stopPropagation()
      uiStore.closeContextMenu()
      break
  }
}

// Reset highlight and focus when menu opens
watch(isOpen, async (open) => {
  if (open) {
    highlightedIndex.value = 0
    await nextTick()
    menuRef.value?.focus()
  }
})

function isHighlighted(item: typeof state.value.items[0]): boolean {
  const actionIdx = actionableItems.value.indexOf(item)
  return actionIdx === highlightedIndex.value
}
</script>

<template>
  <Teleport to="body">
    <Transition name="context-menu">
      <div
        v-if="isOpen"
        class="context-menu-overlay"
        @click="handleOverlayClick"
        @contextmenu.prevent="handleOverlayClick"
      >
        <div
          ref="menuRef"
          class="context-menu"
          :style="{
            left: adjustedPosition.x + 'px',
            top: adjustedPosition.y + 'px',
          }"
          role="menu"
          tabindex="-1"
          @click.stop
          @keydown="handleKeydown"
        >
          <template v-for="item in state.items" :key="item.id">
            <!-- Separator -->
            <div v-if="item.separator" class="context-menu__separator" />

            <!-- Menu Item -->
            <button
              v-else
              :class="[
                'context-menu__item',
                {
                  'context-menu__item--danger': item.variant === 'danger',
                  'context-menu__item--disabled': item.disabled,
                  'context-menu__item--highlighted': isHighlighted(item),
                },
              ]"
              role="menuitem"
              :disabled="item.disabled"
              @click="handleItemClick(item)"
              @mouseenter="highlightedIndex = actionableItems.indexOf(item)"
            >
              <component
                :is="item.icon"
                v-if="item.icon"
                class="context-menu__icon"
              />
              <span class="context-menu__label">{{ item.label }}</span>
              <span
                v-if="item.shortcutHint"
                class="context-menu__shortcut"
              >
                {{ item.shortcutHint }}
              </span>
            </button>
          </template>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.context-menu-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-popover);
}

.context-menu {
  position: fixed;
  min-width: 180px;
  max-width: 260px;
  padding: var(--space-1, 4px);
  background-color: var(--color-bg-secondary);
  border: 1px solid var(--glass-border, rgba(255, 255, 255, 0.06));
  border-radius: var(--radius-md, 10px);
  box-shadow: var(--glass-shadow, 0 8px 32px rgba(0, 0, 0, 0.4));
  backdrop-filter: blur(12px);
  outline: none;
}

.context-menu__separator {
  height: 1px;
  margin: var(--space-1, 4px) var(--space-2, 8px);
  background-color: var(--glass-border, rgba(255, 255, 255, 0.06));
}

.context-menu__item {
  display: flex;
  align-items: center;
  gap: var(--space-2, 8px);
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
  white-space: nowrap;
}

.context-menu__item:hover,
.context-menu__item--highlighted {
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.context-menu__item--danger {
  color: var(--color-error);
}

.context-menu__item--danger:hover,
.context-menu__item--danger.context-menu__item--highlighted {
  background-color: rgba(248, 113, 113, 0.1);
  color: var(--color-error);
}

.context-menu__item--disabled {
  color: var(--color-text-muted);
  cursor: not-allowed;
  pointer-events: none;
}

.context-menu__icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.context-menu__label {
  flex: 1;
}

.context-menu__shortcut {
  font-size: var(--text-xs, 11px);
  color: var(--color-text-muted);
  margin-left: auto;
  padding-left: var(--space-4, 16px);
}

/* Transitions */
.context-menu-enter-active,
.context-menu-leave-active {
  transition: opacity var(--transition-fast, 120ms) ease;
}

.context-menu-enter-active .context-menu,
.context-menu-leave-active .context-menu {
  transition: transform var(--transition-fast, 120ms) ease,
              opacity var(--transition-fast, 120ms) ease;
}

.context-menu-enter-from,
.context-menu-leave-to {
  opacity: 0;
}

.context-menu-enter-from .context-menu,
.context-menu-leave-to .context-menu {
  transform: scale(0.95);
  opacity: 0;
}
</style>
