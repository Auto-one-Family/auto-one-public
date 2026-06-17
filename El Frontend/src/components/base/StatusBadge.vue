<script setup lang="ts">
import { computed } from 'vue'
import { CheckCircle2, AlertTriangle, XCircle, WifiOff } from 'lucide-vue-next'
import type { Component } from 'vue'
import type { StatusLevel } from '@/utils/formatters'

interface Props {
  level: StatusLevel
  /** Only show the colored dot, no text */
  compact?: boolean
  /** Show Lucide icon in non-compact mode */
  showIcon?: boolean
  /** Override the default level label */
  labelOverride?: string
}

const props = withDefaults(defineProps<Props>(), {
  compact: false,
  showIcon: true,
})

const DEFAULT_LABELS: Record<StatusLevel, string> = {
  ok: 'OK',
  warning: 'Warnung',
  alarm: 'Alarm',
  offline: 'Offline',
}

const LEVEL_ICONS: Record<StatusLevel, Component> = {
  ok: CheckCircle2,
  warning: AlertTriangle,
  alarm: XCircle,
  offline: WifiOff,
}

const label = computed(() => props.labelOverride ?? DEFAULT_LABELS[props.level])
const icon = computed(() => LEVEL_ICONS[props.level])
</script>

<template>
  <span
    :class="['status-badge', `status-badge--${level}`, { 'status-badge--compact': compact }]"
    :title="compact ? label : undefined"
    :aria-label="compact ? label : undefined"
  >
    <template v-if="compact">
      <span class="status-badge__dot" />
    </template>
    <template v-else>
      <component :is="icon" v-if="showIcon" class="status-badge__icon" aria-hidden="true" />
      <span class="status-badge__label">{{ label }}</span>
    </template>
  </span>
</template>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: 2px var(--space-2);
  border-radius: var(--radius-full);
  font-size: var(--text-xs, 11px);
  font-weight: 500;
  white-space: nowrap;
  line-height: 1.4;
}

/* ── Level colors ───────────────────────────────────────────── */
.status-badge--ok {
  color: var(--color-status-ok);
  background: color-mix(in srgb, var(--color-status-ok) 12%, transparent);
}

.status-badge--warning {
  color: var(--color-status-warn);
  background: color-mix(in srgb, var(--color-status-warn) 12%, transparent);
}

.status-badge--alarm {
  color: var(--color-status-alarm);
  background: color-mix(in srgb, var(--color-status-alarm) 12%, transparent);
  animation: alarm-pulse 1.5s ease-in-out infinite;
}

.status-badge--offline {
  color: var(--color-status-offl);
  background: color-mix(in srgb, var(--color-status-offl) 10%, transparent);
}

/* ── Icon ──────────────────────────────────────────────────── */
.status-badge__icon {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
}

/* ── Compact dot ───────────────────────────────────────────── */
.status-badge--compact {
  padding: 0;
  background: transparent;
  animation: none;
}

.status-badge__dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-badge--ok .status-badge__dot         { background: var(--color-status-ok); }
.status-badge--warning .status-badge__dot    { background: var(--color-status-warn); }
.status-badge--alarm .status-badge__dot      {
  background: var(--color-status-alarm);
  animation: alarm-pulse 1.5s ease-in-out infinite;
}
.status-badge--offline .status-badge__dot    { background: var(--color-status-offl); }

@keyframes alarm-pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.4; }
}
</style>
