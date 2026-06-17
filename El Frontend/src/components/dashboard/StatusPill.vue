<script setup lang="ts">
/**
 * StatusPill Component
 *
 * Compact status indicator pill for the ActionBar.
 * Shows a colored dot + count + optional label.
 * BEM CSS with CSS custom properties for consistent theming.
 */

type StatusType = 'online' | 'offline' | 'warning' | 'safemode'

interface Props {
  type: StatusType
  count: number
  label: string
  active?: boolean
}

withDefaults(defineProps<Props>(), {
  active: false
})

const emit = defineEmits<{
  click: []
}>()
</script>

<template>
  <button
    :class="[
      'status-pill',
      `status-pill--${type}`,
      { 'status-pill--active': active }
    ]"
    type="button"
    @click="emit('click')"
  >
    <span class="status-pill__dot" />
    <span class="status-pill__count">{{ count }}</span>
    <span class="status-pill__label">{{ label }}</span>
  </button>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════════════════════════════
   STATUS PILL — Industrial Toggle
   Token-aligned, compact, clear status communication
   ═══════════════════════════════════════════════════════════════════════════ */

.status-pill {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: 5px var(--space-2);
  border-radius: var(--radius-full);
  border: 1px solid var(--glass-border);
  background: transparent;
  cursor: pointer;
  user-select: none;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.status-pill:hover {
  background: rgba(255, 255, 255, 0.03);
  border-color: var(--glass-border-hover);
}

/* ── Dot ── */
.status-pill__dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
  transition: box-shadow var(--transition-fast);
}

/* ── Count ── */
.status-pill__count {
  font-size: var(--text-sm);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--color-text-secondary);
  transition: color var(--transition-fast);
}

/* ── Label ── */
.status-pill__label {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  transition: color var(--transition-fast);
}

@media (max-width: 640px) {
  .status-pill__label {
    display: none;
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   COLOR VARIANTS
   ═══════════════════════════════════════════════════════════════════════════ */

/* ── Online ── */
.status-pill--online .status-pill__dot {
  background: var(--color-success);
}

.status-pill--online:hover {
  background: rgba(52, 211, 153, 0.06);
}

.status-pill--online.status-pill--active {
  background: rgba(52, 211, 153, 0.1);
  border-color: rgba(52, 211, 153, 0.3);
}

.status-pill--online.status-pill--active .status-pill__dot {
  box-shadow: 0 0 6px var(--color-success);
}

.status-pill--online.status-pill--active .status-pill__count {
  color: var(--color-success);
}

/* ── Offline ── */
.status-pill--offline .status-pill__dot {
  background: var(--color-error);
}

.status-pill--offline:hover {
  background: rgba(248, 113, 113, 0.06);
}

.status-pill--offline.status-pill--active {
  background: rgba(248, 113, 113, 0.1);
  border-color: rgba(248, 113, 113, 0.3);
}

.status-pill--offline.status-pill--active .status-pill__dot {
  box-shadow: 0 0 6px var(--color-error);
}

.status-pill--offline.status-pill--active .status-pill__count {
  color: var(--color-error);
}

/* ── Warning ── */
.status-pill--warning .status-pill__dot {
  background: var(--color-warning);
}

.status-pill--warning:hover {
  background: rgba(251, 191, 36, 0.06);
}

.status-pill--warning.status-pill--active {
  background: rgba(251, 191, 36, 0.1);
  border-color: rgba(251, 191, 36, 0.3);
}

.status-pill--warning.status-pill--active .status-pill__dot {
  box-shadow: 0 0 6px var(--color-warning);
  animation: pulse-dot 1.5s ease-in-out infinite;
}

.status-pill--warning.status-pill--active .status-pill__count {
  color: var(--color-warning);
}

/* ── SafeMode ── */
.status-pill--safemode .status-pill__dot {
  background: var(--color-warning);
}

.status-pill--safemode:hover {
  background: rgba(249, 115, 22, 0.06);
}

.status-pill--safemode.status-pill--active {
  background: rgba(249, 115, 22, 0.1);
  border-color: rgba(249, 115, 22, 0.3);
}

.status-pill--safemode.status-pill--active .status-pill__dot {
  box-shadow: 0 0 6px var(--color-warning);
}

.status-pill--safemode.status-pill--active .status-pill__count {
  color: var(--color-warning);
}
</style>
