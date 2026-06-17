<script setup lang="ts">
/**
 * NotificationBadge — Bell icon with unread counter
 *
 * Placed in TopBar between EmergencyStopButton and ConnectionDot.
 * - Shows unread count (max "99+")
 * - Color reflects highest severity (critical=error, warning=warning)
 * - CSS pulse animation on new critical notification
 * - Click toggles notification drawer
 */

import { computed } from 'vue'
import { Bell } from 'lucide-vue-next'
import { useNotificationInboxStore } from '@/shared/stores/notification-inbox.store'
import { useAlertCenterStore } from '@/shared/stores'
import { useEspStore } from '@/stores/esp'

const inboxStore = useNotificationInboxStore()
const alertStore = useAlertCenterStore()
const espStore = useEspStore()

/**
 * Phase 4B: Badge shows unresolved alert count when alerts are active,
 * falls back to unread notification count otherwise.
 */
const badgeCount = computed(() => {
  const unresolvedAlerts = alertStore.unresolvedCount
  return unresolvedAlerts > 0 ? unresolvedAlerts : inboxStore.unreadCount
})

/** Hide badge when no devices exist (stale notifications from previous sessions) */
const hasBadge = computed(() => badgeCount.value > 0 && espStore.devices.length > 0)

const badgeText = computed(() => {
  if (badgeCount.value > 99) return '99+'
  return String(badgeCount.value)
})

const severityClass = computed(() => {
  if (!hasBadge.value) return ''
  // Active alerts take priority for severity coloring
  if (alertStore.unresolvedCount > 0) {
    return alertStore.hasCritical
      ? 'notification-badge--critical'
      : 'notification-badge--warning'
  }
  switch (inboxStore.highestSeverity) {
    case 'critical':
      return 'notification-badge--critical'
    case 'warning':
      return 'notification-badge--warning'
    default:
      return 'notification-badge--default'
  }
})
</script>

<template>
  <button
    type="button"
    :class="['notification-badge', severityClass]"
    data-testid="notification-drawer-trigger"
    aria-label="Server-Inbox öffnen (Meldungen und Alerts, nicht Echtzeit-Fehlerstrom)"
    :title="alertStore.unresolvedCount > 0
      ? `Server-Inbox: ${alertStore.unresolvedCount} aktive Alerts (Echtzeit-Fehler nur als Toast)`
      : `Server-Inbox: ${inboxStore.unreadCount} ungelesen (Echtzeit-Fehler nur als Toast)`"
    @click="inboxStore.toggleDrawer()"
  >
    <Bell class="notification-badge__icon" />
    <span v-if="hasBadge" class="notification-badge__count">
      {{ badgeText }}
    </span>
  </button>
</template>

<style scoped>
.notification-badge {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.notification-badge:hover {
  color: var(--color-text-primary);
  background: var(--color-bg-tertiary);
}

.notification-badge__icon {
  width: 16px;
  height: 16px;
  pointer-events: none;
}

.notification-badge__count {
  position: absolute;
  top: -4px;
  right: -6px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: var(--radius-full);
  font-size: var(--text-xxs);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 16px;
  text-align: center;
  color: var(--color-text-inverse);
  pointer-events: none;
}

/* Severity-based badge colors */
.notification-badge--default .notification-badge__count {
  background: var(--color-text-muted);
}

.notification-badge--warning .notification-badge__count {
  background: var(--color-warning);
}

.notification-badge--critical .notification-badge__count {
  background: var(--color-error);
  animation: badge-pulse 2s ease-in-out infinite;
}

.notification-badge--critical .notification-badge__icon {
  color: var(--color-error);
}

.notification-badge--warning .notification-badge__icon {
  color: var(--color-warning);
}

@keyframes badge-pulse {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(248, 113, 113, 0.4);
  }
  50% {
    box-shadow: 0 0 0 4px rgba(248, 113, 113, 0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .notification-badge--critical .notification-badge__count {
    animation: none;
  }
}
</style>
