<template>
  <div class="preview-event-card" :class="{ compact }">
    <!-- Severity-Indicator -->
    <div class="severity-dot" :class="`severity-${event.severity}`"></div>

    <!-- Event-Info -->
    <div class="event-info">
      <div class="event-primary">
        <span v-if="event.device_id" class="device-id">
          {{ event.device_id }}
        </span>
        <span class="event-type">{{ formatEventType(event.event_type) }}</span>
      </div>

      <div class="event-message">
        {{ truncateMessage(event.message, compact ? 50 : 100) }}
      </div>
    </div>

    <!-- Timestamp -->
    <div class="event-time">
      {{ formatRelativeTime(event.created_at) }}
    </div>
  </div>
</template>

<script setup lang="ts">
import type { CleanupPreviewEvent } from '@/api/audit'
import { formatRelativeTime } from '@/utils/formatters'

interface Props {
  event: CleanupPreviewEvent
  compact?: boolean
}

defineProps<Props>()

function formatEventType(type: string): string {
  const types: Record<string, string> = {
    'sensor_data': 'Sensor',
    'esp_heartbeat': 'Heartbeat',
    'esp_health': 'ESP-Status',
    'error_event': 'Fehler',
    'actuator_response': 'Aktor',
    'actuator_status': 'Aktor-Status',
    'actuator_alert': 'Aktor-Alarm',
    'config_response': 'Konfig',
    'device_discovered': 'Entdeckt',
    'device_approved': 'Genehmigt',
    'device_rejected': 'Abgelehnt',
    'zone_assignment': 'Zone',
    'logic_execution': 'Regel',
    'system_event': 'System',
    'notification': 'Info',
  }
  return types[type] || type
}

function truncateMessage(msg: string, maxLen: number): string {
  if (!msg) return ''
  if (msg.length <= maxLen) return msg
  return msg.substring(0, maxLen) + '...'
}

</script>

<style scoped>
.preview-event-card {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: var(--radius-md);
  transition: all 0.2s ease;
}

.preview-event-card.compact {
  padding: 0.5rem;
}

.preview-event-card:hover {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.15);
}

.severity-dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.severity-info { background: var(--color-accent); }
.severity-warning { background: var(--color-warning); }
.severity-error { background: var(--color-error); }
.severity-critical { background: var(--color-error); }

.event-info {
  flex: 1;
  min-width: 0;
}

.event-primary {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.25rem;
}

.device-id {
  font-size: 0.875rem;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.9);
  font-family: ui-monospace, monospace;
}

.event-type {
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.5);
}

.event-message {
  font-size: 0.875rem;
  color: rgba(255, 255, 255, 0.7);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.compact .event-message {
  font-size: 0.8125rem;
}

.event-time {
  flex-shrink: 0;
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.5);
  white-space: nowrap;
}
</style>
