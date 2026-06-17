<script setup lang="ts">
/**
 * StatCard Component
 * 
 * Displays a statistic with:
 * - Icon
 * - Main value
 * - Title/label
 * - Optional subtitle
 * - Optional trend indicator
 * - Loading skeleton state
 */

import { computed } from 'vue'
import type { Component } from 'vue'

interface Trend {
  direction: 'up' | 'down'
  value: number
}

interface Props {
  /** Card title */
  title: string
  /** Main value to display */
  value: number | string
  /** Optional subtitle text */
  subtitle?: string
  /** Lucide icon component */
  icon: Component
  /** Icon color class */
  iconColor?: string
  /** Icon background color class */
  iconBgColor?: string
  /** Optional trend indicator */
  trend?: Trend
  /** Whether the card is in loading state */
  loading?: boolean
  /** Whether to highlight this card (iridescent border) */
  highlighted?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  iconColor: 'text-iridescent-1',
  iconBgColor: 'bg-iridescent-1/10',
  loading: false,
  highlighted: false,
})

const cardClasses = computed(() => {
  const classes = ['stat-card']
  if (props.highlighted) {
    classes.push('stat-card--highlighted')
  }
  return classes
})

const trendClasses = computed(() => {
  if (!props.trend) return ''
  return props.trend.direction === 'up' 
    ? 'stat-card__trend--up' 
    : 'stat-card__trend--down'
})
</script>

<template>
  <div :class="cardClasses">
    <!-- Icon -->
    <div :class="['stat-card__icon', iconBgColor]">
      <component :is="icon" :class="['w-5 h-5', iconColor]" />
    </div>
    
    <!-- Content -->
    <div class="stat-card__content">
      <div class="stat-card__title">{{ title }}</div>
      
      <!-- Loading skeleton -->
      <div v-if="loading" class="stat-card__value">
        <div class="skeleton h-8 w-16"></div>
      </div>
      
      <!-- Actual value -->
      <div v-else class="stat-card__value">
        {{ value }}
      </div>
      
      <div v-if="subtitle" class="stat-card__subtitle">
        {{ subtitle }}
      </div>
    </div>
    
    <!-- Trend indicator -->
    <div v-if="trend && !loading" :class="['stat-card__trend', trendClasses]">
      <svg 
        v-if="trend.direction === 'up'" 
        class="w-4 h-4" 
        fill="none" 
        stroke="currentColor" 
        viewBox="0 0 24 24"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7" />
      </svg>
      <svg 
        v-else 
        class="w-4 h-4" 
        fill="none" 
        stroke="currentColor" 
        viewBox="0 0 24 24"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
      </svg>
      {{ trend.value }}%
    </div>
  </div>
</template>

<style scoped>
.stat-card {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  padding: 1.25rem;
  background-color: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  transition: all 0.3s ease;
}

.stat-card:hover {
  border-color: rgba(96, 165, 250, 0.2);
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
}

.stat-card--highlighted {
  position: relative;
  border: 1px solid transparent;
  background: 
    linear-gradient(var(--color-bg-secondary), var(--color-bg-secondary)) padding-box,
    linear-gradient(
      135deg, 
      var(--color-iridescent-1) 0%, 
      var(--color-iridescent-2) 25%,
      var(--color-iridescent-3) 50%,
      var(--color-iridescent-4) 75%,
      var(--color-iridescent-1) 100%
    ) border-box;
}

.stat-card__icon {
  padding: 0.75rem;
  border-radius: var(--radius-md);
  flex-shrink: 0;
}

.stat-card__content {
  flex: 1;
  min-width: 0;
}

.stat-card__title {
  font-size: 0.875rem;
  color: var(--color-text-secondary);
}

.stat-card__value {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--color-text-primary);
  line-height: 1.2;
}

.stat-card__subtitle {
  font-size: 0.75rem;
  color: var(--color-text-muted);
  margin-top: 0.25rem;
}

.stat-card__trend {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.75rem;
  font-weight: 500;
  flex-shrink: 0;
}

.stat-card__trend--up {
  color: var(--color-success);
}

.stat-card__trend--down {
  color: var(--color-error);
}
</style>





















