<script setup lang="ts">
/**
 * ESPCardBase — Unified base component for all ESP device card variants.
 *
 * Provides consistent: status dot, device name, mock/real badge, border styling.
 * Variant-specific content via named slots.
 *
 * Variants:
 * - mini:    Compact card for zone overview (ZonePlate)
 * - summary: Medium card for zone detail
 * - detail:  Full card for device detail (ESP orbital layout)
 * - widget:  Dashboard widget (health overview)
 */

import { computed, toRef } from 'vue'
import { useESPStatus } from '@/composables/useESPStatus'
import type { ESPDevice } from '@/api/esp'

export interface ESPCardBaseProps {
  esp: ESPDevice
  variant?: 'mini' | 'summary' | 'detail' | 'widget'
  showActions?: boolean
  interactive?: boolean
}

const props = withDefaults(defineProps<ESPCardBaseProps>(), {
  variant: 'summary',
  showActions: undefined,
  interactive: true,
})

const espRef = toRef(() => props.esp)
const {
  status,
  statusColor,
  statusDetailLabel,
  statusTooltip,
  statusPulse,
  isOnline,
  isMock,
  borderColor,
  displayName,
  deviceId,
  lastSeenText,
} = useESPStatus(espRef)

/** Whether to show action buttons (defaults based on variant) */
const actionsVisible = computed(() =>
  props.showActions ?? props.variant !== 'mini'
)

/** Badge text and class */
const badgeText = computed(() => isMock.value ? 'MOCK' : 'REAL')
const badgeClass = computed(() => isMock.value ? 'esp-card-base__badge--mock' : 'esp-card-base__badge--real')

/** Size class for the card based on variant */
const sizeClass = computed(() => `esp-card-base--${props.variant}`)
</script>

<template>
  <div
    class="esp-card-base"
    :class="[sizeClass, { 'esp-card-base--interactive': interactive }]"
    :style="{ borderLeftColor: borderColor }"
    :role="interactive ? 'button' : undefined"
    :tabindex="interactive ? 0 : undefined"
    :aria-label="`${displayName}, Status: ${statusDetailLabel}`"
  >
    <!-- Header: Status dot + Name + Badge + Actions slot -->
    <div class="esp-card-base__header esp-drag-handle">
      <span
        class="esp-card-base__status-dot"
        :class="{ 'esp-card-base__status-dot--pulse': statusPulse }"
        :style="{ backgroundColor: statusColor }"
        :title="statusTooltip"
        :aria-label="statusDetailLabel"
      />
      <span class="esp-card-base__name">
        <slot name="name" :display-name="displayName" :device-id="deviceId">
          {{ displayName }}
        </slot>
      </span>
      <span class="esp-card-base__badge" :class="badgeClass">{{ badgeText }}</span>
      <div v-if="actionsVisible" class="esp-card-base__actions">
        <slot name="actions" :device-id="deviceId" :is-online="isOnline" :is-mock="isMock" />
      </div>
    </div>

    <!-- Status text (last seen) — hidden on mini variant -->
    <div v-if="variant !== 'mini'" class="esp-card-base__status-line">
      <span class="esp-card-base__status-text" :style="{ color: statusColor }">{{ statusDetailLabel }}</span>
      <span class="esp-card-base__last-seen">{{ lastSeenText }}</span>
    </div>

    <!-- Variant-specific content via default slot -->
    <div v-if="$slots.default" class="esp-card-base__content">
      <slot
        :status="status"
        :is-online="isOnline"
        :is-mock="isMock"
        :device-id="deviceId"
        :display-name="displayName"
        :last-seen-text="lastSeenText"
      />
    </div>

    <!-- Metrics slot (for mini cards: spark bars, for widget: uptime/rssi) -->
    <div v-if="$slots.metrics" class="esp-card-base__metrics">
      <slot name="metrics" :status="status" :is-online="isOnline" />
    </div>

    <!-- Footer slot (for summary: counts, for detail: sensor/actuator lists) -->
    <div v-if="$slots.footer" class="esp-card-base__footer">
      <slot name="footer" />
    </div>
  </div>
</template>

<style scoped>
.esp-card-base {
  display: flex;
  flex-direction: column;
  background-color: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-left: 3px solid var(--color-text-muted);
  border-radius: var(--radius-md);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.esp-card-base--interactive {
  cursor: pointer;
}

.esp-card-base--interactive:hover {
  border-color: var(--glass-border-hover);
  box-shadow: var(--elevation-raised);
}

.esp-card-base--interactive:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}

/* --- Size variants --- */

.esp-card-base--mini {
  padding: 0.375rem 0.5rem;
  gap: 2px;
}

.esp-card-base--summary {
  padding: 0.5rem 0.75rem;
  gap: 0.375rem;
}

.esp-card-base--detail {
  padding: 0.75rem;
  gap: 0.5rem;
}

.esp-card-base--widget {
  padding: 0.5rem 0.75rem;
  gap: 0.375rem;
}

/* --- Header --- */

.esp-card-base__header {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  min-width: 0;
}

.esp-card-base__status-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
}

.esp-card-base__status-dot--pulse {
  animation: esp-status-pulse 2s infinite;
}

@keyframes esp-status-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.esp-card-base__name {
  flex: 1;
  min-width: 0;
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.esp-card-base--mini .esp-card-base__name {
  font-size: var(--text-sm);
}

.esp-card-base__badge {
  flex-shrink: 0;
  padding: 1px 0.375rem;
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: var(--tracking-wide);
}

.esp-card-base__badge--mock {
  background-color: rgba(167, 139, 250, 0.12);
  color: var(--color-mock);
  border: 1px solid rgba(167, 139, 250, 0.25);
}

.esp-card-base__badge--real {
  background-color: rgba(34, 211, 238, 0.12);
  color: var(--color-real);
  border: 1px solid rgba(34, 211, 238, 0.25);
}

.esp-card-base__actions {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  flex-shrink: 0;
}

/* --- Status line --- */

.esp-card-base__status-line {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: var(--text-xs);
}

.esp-card-base__status-text {
  font-weight: 500;
}

.esp-card-base__last-seen {
  color: var(--color-text-muted);
}

/* --- Content areas --- */

.esp-card-base__content {
  min-width: 0;
}

.esp-card-base__metrics {
  min-width: 0;
}

.esp-card-base__footer {
  border-top: 1px solid var(--glass-border);
  padding-top: 0.375rem;
  margin-top: 0.25rem;
}

.esp-card-base--mini .esp-card-base__footer {
  border-top: none;
  padding-top: 0;
  margin-top: 0;
}
</style>
