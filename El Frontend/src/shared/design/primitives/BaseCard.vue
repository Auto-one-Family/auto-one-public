<script setup lang="ts">
/**
 * Card Component
 * 
 * A versatile card component with support for:
 * - Different border color variants
 * - Glass morphism effect
 * - Water reflection shimmer
 * - Hoverable state
 * - Header, body, footer slots
 */

interface Props {
  /** Whether to add hover effect */
  hoverable?: boolean
  /** Whether to add padding to the card body */
  noPadding?: boolean
  /** Border color variant */
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'mock' | 'real'
  /** Enable glass morphism effect */
  glass?: boolean
  /** Enable water reflection shimmer */
  shimmer?: boolean
  /** Iridescent border effect */
  iridescent?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  hoverable: false,
  noPadding: false,
  variant: 'default',
  glass: false,
  shimmer: false,
  iridescent: false,
})

// Compute card classes
const cardClasses = computed(() => {
  const classes: string[] = ['card']
  
  // Variant border colors
  const variantClasses: Record<string, string> = {
    'default': '',
    'success': 'border-success/30',
    'warning': 'border-warning/30',
    'danger': 'border-danger/30',
    'info': 'border-info/30',
    'mock': 'border-mock/30',
    'real': 'border-real/30',
  }
  
  if (variantClasses[props.variant]) {
    classes.push(variantClasses[props.variant])
  }
  
  if (props.hoverable) {
    classes.push('cursor-pointer', 'hover:shadow-card-hover', 'hover:-translate-y-0.5')
  }
  
  if (props.glass) {
    classes.push('card-glass')
  }
  
  if (props.shimmer) {
    classes.push('water-reflection')
  }
  
  if (props.iridescent) {
    classes.push('iridescent-border')
  }
  
  return classes
})

import { computed } from 'vue'
</script>

<template>
  <div :class="cardClasses">
    <!-- Header slot -->
    <div
      v-if="$slots.header"
      class="card-header"
    >
      <slot name="header" />
    </div>

    <!-- Default slot (body) -->
    <div :class="noPadding ? '' : 'card-body'">
      <slot />
    </div>

    <!-- Footer slot -->
    <div
      v-if="$slots.footer"
      class="card-footer"
    >
      <slot name="footer" />
    </div>
  </div>
</template>
