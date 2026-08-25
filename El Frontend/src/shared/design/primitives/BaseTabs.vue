<script setup lang="ts">
/**
 * BaseTabs — Generic horizontal tab bar
 *
 * Extracted from the inline tab-bar code that used to live in
 * ConfigWizardModal.vue (AUT-1127 S2). Used independently by both
 * ActuatorConfigPanel and SensorConfigPanel to render their own
 * type-specific tab set — there is no shared parent tab state between them.
 */
import type { Component } from 'vue'

export interface TabItem {
  key: string
  label: string
  icon?: Component
  badge?: number
}

interface Props {
  tabs: TabItem[]
  modelValue: string
}

defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()
</script>

<template>
  <div class="base-tabs" role="tablist">
    <button
      v-for="tab in tabs"
      :key="tab.key"
      class="base-tabs__tab"
      role="tab"
      type="button"
      :aria-selected="modelValue === tab.key"
      :class="{ 'base-tabs__tab--active': modelValue === tab.key }"
      @click="emit('update:modelValue', tab.key)"
    >
      <component :is="tab.icon" v-if="tab.icon" class="base-tabs__icon" :size="14" />
      {{ tab.label }}
      <span v-if="tab.badge" class="base-tabs__badge">{{ tab.badge }}</span>
    </button>
  </div>
</template>

<style scoped>
.base-tabs {
  display: flex;
  gap: 0;
  flex-wrap: wrap;
  border-bottom: 1px solid var(--glass-border);
  background: var(--glass-bg-l1);
  flex-shrink: 0;
}

.base-tabs__tab {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.625rem 1rem;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-muted);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: color var(--transition-fast), border-color var(--transition-fast), background var(--transition-fast);
  white-space: nowrap;
  position: relative;
  min-height: 44px;
}

.base-tabs__tab:hover {
  color: var(--color-text-secondary);
  background: rgba(255, 255, 255, 0.03);
}

.base-tabs__tab--active {
  color: var(--color-iridescent-1);
  border-bottom-color: var(--color-iridescent-1);
  background: rgba(96, 165, 250, 0.04);
}

.base-tabs__icon {
  flex-shrink: 0;
  opacity: 0.7;
}

.base-tabs__tab--active .base-tabs__icon {
  opacity: 1;
}

.base-tabs__badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 0.3rem;
  font-size: 0.65rem;
  font-weight: 700;
  color: var(--color-bg-primary);
  background: var(--color-iridescent-1);
  border-radius: var(--radius-full);
}
</style>
