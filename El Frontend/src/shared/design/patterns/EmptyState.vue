<script setup lang="ts">
/**
 * EmptyState Component
 *
 * Displays an empty state placeholder with:
 * - Icon
 * - Title
 * - Description
 * - Optional action: either as router-link (ctaTo) or as emit action (actionText)
 *
 * Backward compatible:
 *   - actionText + @action → emit-based button (existing usage)
 *   - ctaText + ctaTo      → RouterLink primary CTA
 *   - Hint slot            → optional secondary text below CTA
 */

import type { Component } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import { Inbox } from 'lucide-vue-next'

interface Props {
  /** Icon component to display */
  icon?: Component
  /** Title text */
  title: string
  /** Description text */
  description?: string
  /** Action button text (emit variant) */
  actionText?: string
  /** Whether to show the emit-based action button */
  showAction?: boolean
  /** CTA button label (router variant) */
  ctaText?: string
  /** CTA target route — when set renders a RouterLink instead of a button */
  ctaTo?: RouteLocationRaw
}

const props = withDefaults(defineProps<Props>(), {
  icon: () => Inbox,
  showAction: true,
})

void props // Used in template
const emit = defineEmits<{
  action: []
}>()
</script>

<template>
  <div class="empty-state">
    <div class="empty-state__icon-wrapper">
      <component :is="icon" class="empty-state__icon" />
    </div>

    <h3 class="empty-state__title">{{ title }}</h3>

    <p v-if="description" class="empty-state__description">
      {{ description }}
    </p>

    <RouterLink
      v-if="ctaTo && ctaText"
      :to="ctaTo"
      class="btn-primary empty-state__cta"
    >
      {{ ctaText }}
    </RouterLink>

    <button
      v-else-if="showAction && actionText"
      class="btn-primary empty-state__cta"
      @click="emit('action')"
    >
      {{ actionText }}
    </button>

    <div v-if="$slots.hint" class="empty-state__hint">
      <slot name="hint" />
    </div>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1.5rem;
  text-align: center;
}

.empty-state__icon-wrapper {
  width: 4rem;
  height: 4rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background-color: var(--color-bg-tertiary);
  margin-bottom: 1rem;
}

.empty-state__icon {
  width: 2rem;
  height: 2rem;
  color: var(--color-text-muted);
}

.empty-state__title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 0.5rem;
}

.empty-state__description {
  font-size: 0.875rem;
  color: var(--color-text-muted);
  max-width: 24rem;
  margin-bottom: 1.5rem;
  line-height: 1.5;
}

.empty-state__cta {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  text-decoration: none;
}

.empty-state__hint {
  margin-top: 1rem;
  font-size: 0.8125rem;
  color: var(--color-text-muted);
  max-width: 24rem;
  line-height: 1.5;
}

.empty-state__hint :deep(a) {
  color: var(--color-iridescent-1);
  text-decoration: none;
}

.empty-state__hint :deep(a:hover) {
  text-decoration: underline;
}
</style>





















