<script setup lang="ts">
/**
 * AccordionSection — Reusable expandable/collapsible section
 *
 * Features:
 * - Smooth animated expand/collapse (CSS grid-template-rows transition)
 * - localStorage persistence of open/closed state per storageKey
 * - Optional icon next to title
 * - Slot-based content
 * - External v-model control via modelValue
 * - Custom header via #header slot with {isOpen, toggle} scope
 *
 * Used by: SensorConfigPanel, ActuatorConfigPanel, ESPSettingsSheet, ZonePlate
 */

import { ref, computed, onMounted } from 'vue'
import type { Component } from 'vue'
import { ChevronRight } from 'lucide-vue-next'

interface Props {
  /** Section title text (optional when using #header slot) */
  title?: string
  /** Unique key for localStorage persistence (omit to disable persistence) */
  storageKey?: string
  /** Whether section is open by default */
  defaultOpen?: boolean
  /** Optional lucide icon component (Vue Component - object or functional) */
  icon?: Component
  /** External v-model control (overrides internal state when provided) */
  modelValue?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
  storageKey: undefined,
  defaultOpen: false,
  icon: undefined,
  modelValue: undefined,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()

const internalOpen = ref(props.defaultOpen)

onMounted(() => {
  if (props.modelValue === undefined && props.storageKey) {
    const stored = localStorage.getItem(`accordion:${props.storageKey}`)
    if (stored !== null) {
      internalOpen.value = stored === '1'
    }
  }
})

const isOpen = computed(() => {
  if (props.modelValue !== undefined) return props.modelValue
  return internalOpen.value
})

function toggle() {
  const newVal = !isOpen.value
  if (props.modelValue !== undefined) {
    emit('update:modelValue', newVal)
  } else {
    internalOpen.value = newVal
    if (props.storageKey) {
      localStorage.setItem(`accordion:${props.storageKey}`, newVal ? '1' : '0')
    }
  }
}

const chevronClass = computed(() =>
  isOpen.value ? 'accordion__chevron accordion__chevron--open' : 'accordion__chevron'
)
</script>

<template>
  <div class="accordion" :class="{ 'accordion--open': isOpen }">
    <slot name="header" :is-open="isOpen" :toggle="toggle">
      <button
        class="accordion__trigger"
        type="button"
        :aria-expanded="isOpen"
        @click="toggle"
      >
        <ChevronRight :class="chevronClass" />
        <component :is="icon" v-if="icon" class="accordion__icon" />
        <span class="accordion__title">{{ title }}</span>
      </button>
    </slot>

    <div class="accordion__panel" :class="{ 'accordion__panel--open': isOpen }">
      <div class="accordion__content">
        <slot />
      </div>
    </div>
  </div>
</template>

<style scoped>
.accordion {
  border-bottom: 1px solid var(--glass-border);
}

.accordion:last-child {
  border-bottom: none;
}

.accordion__trigger {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-3) 0;
  background: none;
  border: none;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: color var(--transition-fast);
  text-align: left;
}

.accordion__trigger:hover {
  color: var(--color-text-primary);
}

.accordion__chevron {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  transition: transform 200ms ease;
}

.accordion__chevron--open {
  transform: rotate(90deg);
}

.accordion__icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  opacity: 0.7;
}

.accordion__title {
  flex: 1;
}

.accordion__panel {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 200ms ease;
}

.accordion__panel--open {
  grid-template-rows: 1fr;
}

.accordion__content {
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  /* Padding only when open, via parent grid transition */
}

.accordion__panel--open .accordion__content {
  padding-bottom: var(--space-4);
}
</style>
