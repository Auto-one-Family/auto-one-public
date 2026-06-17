<script setup lang="ts">
/**
 * FormGroup Component
 *
 * Collapsible group of form fields with title and description.
 */

import { ref } from 'vue'
import { ChevronDown } from 'lucide-vue-next'
import type { FormGroupSchema } from '@/types/form-schema'

interface Props {
  /** Group schema */
  schema: FormGroupSchema
}

const props = defineProps<Props>()

const isCollapsed = ref(props.schema.collapsed ?? false)

function toggle(): void {
  isCollapsed.value = !isCollapsed.value
}
</script>

<template>
  <div class="form-group">
    <button
      class="form-group__header"
      type="button"
      :aria-expanded="!isCollapsed"
      @click="toggle"
    >
      <div class="form-group__title-row">
        <h4 class="form-group__title">{{ schema.title }}</h4>
        <ChevronDown
          class="form-group__chevron"
          :class="{ 'form-group__chevron--collapsed': isCollapsed }"
        />
      </div>
      <p v-if="schema.description" class="form-group__description">
        {{ schema.description }}
      </p>
    </button>

    <div
      class="form-group__body"
      :class="{ 'form-group__body--collapsed': isCollapsed }"
    >
      <div class="form-group__body-inner">
        <slot />
      </div>
    </div>
  </div>
</template>

<style scoped>
.form-group {
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.form-group__header {
  display: flex;
  flex-direction: column;
  width: 100%;
  padding: var(--space-3);
  border: none;
  background: var(--color-bg-tertiary);
  cursor: pointer;
  text-align: left;
  transition: background var(--transition-fast);
}

.form-group__header:hover {
  background: var(--color-bg-quaternary);
}

.form-group__title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.form-group__title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin: 0;
}

.form-group__chevron {
  width: 14px;
  height: 14px;
  color: var(--color-text-muted);
  transition: transform var(--transition-base);
}

.form-group__chevron--collapsed {
  transform: rotate(-90deg);
}

.form-group__description {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin: var(--space-1) 0 0;
}

.form-group__body {
  display: grid;
  grid-template-rows: 1fr;
  transition: grid-template-rows var(--transition-base);
}

.form-group__body--collapsed {
  grid-template-rows: 0fr;
}

.form-group__body-inner {
  overflow: hidden;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-3);
}

.form-group__body--collapsed .form-group__body-inner {
  padding-top: 0;
  padding-bottom: 0;
}
</style>
