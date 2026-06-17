<script setup lang="ts">
/**
 * QuickActionItem — Single action entry in the Quick Action Menu.
 *
 * Renders an icon, label, optional badge, and optional shortcut hint.
 * Emits click event for the parent menu to handle.
 */

import type { Component } from 'vue'

interface Props {
  icon: Component
  label: string
  badge?: number
  badgeVariant?: 'critical' | 'warning' | 'info'
  shortcutHint?: string
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  badge: 0,
  badgeVariant: 'info',
  shortcutHint: undefined,
  disabled: false,
})

const emit = defineEmits<{
  click: []
}>()

function handleClick() {
  if (!props.disabled) {
    emit('click')
  }
}
</script>

<template>
  <button
    class="qa-item"
    :class="{ 'qa-item--disabled': disabled }"
    :disabled="disabled"
    @click="handleClick"
  >
    <span class="qa-item__icon-wrapper">
      <component :is="icon" class="qa-item__icon" />
      <span
        v-if="badge > 0"
        class="qa-item__badge"
        :class="`qa-item__badge--${badgeVariant}`"
      >
        {{ badge > 99 ? '99+' : badge }}
      </span>
    </span>
    <span class="qa-item__label">{{ label }}</span>
    <span v-if="shortcutHint" class="qa-item__shortcut">{{ shortcutHint }}</span>
  </button>
</template>

<style scoped>
.qa-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: all var(--transition-fast);
  text-align: left;
  white-space: nowrap;
  touch-action: manipulation;
}

.qa-item:hover:not(.qa-item--disabled) {
  color: var(--color-text-primary);
  background: rgba(255, 255, 255, 0.06);
}

.qa-item--disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.qa-item__icon-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 20px;
  height: 20px;
}

.qa-item__icon {
  width: 16px;
  height: 16px;
}

.qa-item__badge {
  position: absolute;
  top: -4px;
  right: -6px;
  min-width: 14px;
  height: 14px;
  padding: 0 3px;
  border-radius: var(--radius-full);
  font-size: var(--text-xxs);
  font-weight: 700;
  line-height: 14px;
  text-align: center;
  color: white;
  pointer-events: none;
}

.qa-item__badge--critical {
  background: var(--color-error);
  box-shadow: 0 0 6px rgba(248, 113, 113, 0.5);
}

.qa-item__badge--warning {
  background: var(--color-warning);
  box-shadow: 0 0 6px rgba(251, 191, 36, 0.4);
}

.qa-item__badge--info {
  background: var(--color-info);
}

.qa-item__label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}

.qa-item__shortcut {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  opacity: 0.6;
  padding: 1px 4px;
  border-radius: var(--radius-xs);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  font-family: var(--font-mono);
}
</style>
