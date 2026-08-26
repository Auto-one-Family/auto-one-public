<script setup lang="ts">
/**
 * NotificationItem — Single notification row in the drawer
 *
 * Features:
 * - Severity dot (left)
 * - Title (bold when unread) + body (1 line truncated)
 * - Relative time (right)
 * - Expandable details (source, ESP, zone, deep-links)
 * - Zeile = Expand; Buttons = Bestätigen / Erledigen (kein Mute, kein Timeout)
 */

import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  Check, CheckCheck, ChevronDown, ChevronUp,
  Activity, Workflow, BarChart3, ShieldCheck, Mail, Info,
  AlertTriangle, AlertCircle,
} from 'lucide-vue-next'
import { formatRelativeTime } from '@/utils/formatters'
import {
  getEmailStatusLabel,
  getNotificationCategoryLabel,
  getNotificationSeverityLabel,
  getNotificationSourceLabel,
} from '@/utils/labels'
import { useEspStore } from '@/stores/esp'
import { buildEspContextRoute } from '@/utils/notificationNavigation'
import AlertAuditLines from '@/components/notifications/AlertAuditLines.vue'
import type { NotificationDTO } from '@/api/notifications'
import { GRAFANA_BASE_URL } from '@/composables/useGrafana'

interface Props {
  notification: NotificationDTO
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'mark-read': [id: string]
  'acknowledge': [id: string]
  'resolve': [id: string]
}>()

const router = useRouter()
const espStore = useEspStore()
const isExpanded = ref(false)


const metadata = computed(() => props.notification.metadata || {})
const hasEspId = computed(() => !!metadata.value.esp_id)
const hasRuleId = computed(() => !!metadata.value.rule_id)
const hasSensorType = computed(() => !!metadata.value.sensor_type)
const hasMeasurementAgeAtAlert = computed(() => {
  const age = metadata.value.measurement_age_seconds
  const mode = metadata.value.operating_mode
  return typeof age === 'number' && age >= 0 && mode !== 'continuous'
})

/**
 * AUT-131 B-CNFL2-04: Konflikt-Arbitration ist informational.
 * Erkennt Notifications die aus dem ConflictManager stammen
 * (metadata.event_type === "conflict.arbitration") oder
 * eine zukuenftige Kategorisierung "rule_arbitration" tragen.
 * Server stuetzt zusaetzlich metadata.ack_effect / resolve_effect = "informational".
 */
const isArbitrationInfo = computed<boolean>(() => {
  const eventType = metadata.value.event_type
  if (eventType === 'conflict.arbitration') return true
  // Forward-compatible fallback: category-Erweiterung "rule_arbitration"
  // (zur Zeit nicht in NotificationCategory-Union, daher String-Vergleich ueber unknown)
  const category = props.notification.category as unknown as string
  if (category === 'rule_arbitration') return true
  return false
})

/** Severity icon: AlertCircle for critical/alarm, AlertTriangle for warning, null for info */
const severityIcon = computed(() => {
  const s = props.notification.severity
  if (s === 'critical') return AlertCircle
  if (s === 'warning') return AlertTriangle
  return null
})

const severityIconClass = computed(() => {
  const s = props.notification.severity
  if (s === 'critical') return 'item__severity-icon--critical'
  if (s === 'warning') return 'item__severity-icon--warning'
  return ''
})

/** Operator-facing action hint derived from source + severity */
const actionHint = computed((): string | null => {
  const src = props.notification.source
  const severity = props.notification.severity
  if (src === 'sensor_threshold') return 'Sensor und Gerät prüfen'
  if (src === 'device_event') return 'Gerät prüfen und ggf. neu starten'
  if (src === 'freshness_reminder') return 'Sensor auf aktuelle Messwerte prüfen'
  if (src === 'calibration_reminder') return 'Kalibrierung durchführen'
  if (src === 'logic_engine') return 'Regelkonfiguration prüfen'
  if (severity === 'critical') return 'Sofortmaßnahme erforderlich — Anlage prüfen'
  if (severity === 'warning') return 'Prüfen und ggf. eingreifen'
  return null
})

// Email delivery status from metadata (Phase C V1.1)
const emailStatus = computed(() => metadata.value.email_status as string | undefined)
const emailProvider = computed(() => metadata.value.email_provider as string | undefined)
const hasEmailInfo = computed(() => !!emailStatus.value)

const canAcknowledge = computed(() => props.notification.status === 'active')
const canResolve = computed(() =>
  props.notification.status === 'active' || props.notification.status === 'acknowledged'
)
const isResolved = computed(() => props.notification.status === 'resolved')
const isAutoResolved = computed(() =>
  isResolved.value && metadata.value.grafana_status === 'resolved'
)

const statusLabel = computed(() => {
  switch (props.notification.status) {
    case 'active': return 'Aktiv'
    case 'acknowledged': return 'Bestätigt'
    case 'resolved': return 'Erledigt'
    default: return ''
  }
})

const statusClass = computed(() => {
  switch (props.notification.status) {
    case 'active': return 'item__status--active'
    case 'acknowledged': return 'item__status--acknowledged'
    case 'resolved': return 'item__status--resolved'
    default: return ''
  }
})

/** Source label for badge (Sensor, Infrastruktur, Aktor, Regel, System) */
const sourceLabel = computed(() => getNotificationSourceLabel(props.notification.source))

/**
 * AUT-246: Source line — formatted "{Source-Type}: {Specific-Name}" for clarity.
 * Helps the operator immediately see WHO triggered the alert without expanding.
 *
 * Mapping (per AUT-246):
 *   sensor_threshold → "Sensor-Schwelle: {Sensor-Name}" (clickable → Sensor-Settings)
 *   logic_engine     → "Regel: {Rule-Name}" (clickable → Rule-Editor)
 *   device_event     → "Gerät: {ESP-Name} ({Reason})"
 *   system           → "System: {reason}"
 *   freshness_reminder/calibration_reminder → "Sensor-Hinweis: {Sensor-Name}"
 *   grafana          → "Infrastruktur: {Title or 'Grafana'}"
 *   mqtt_handler     → "Aktor: {ESP-Name}"
 */
interface SourceLine {
  prefix: string
  name: string
  clickable: boolean
  navigate: (() => void) | null
}

const sourceLine = computed<SourceLine | null>(() => {
  const src = props.notification.source
  if (!src) return null
  const meta = metadata.value
  switch (src) {
    case 'sensor_threshold': {
      const sensorName =
        (meta.sensor_name as string)
        || (meta.sensor_type as string)
        || 'Unbekannter Sensor'
      return {
        prefix: 'Sensor-Schwelle',
        name: sensorName,
        clickable: !!meta.esp_id,
        navigate: meta.esp_id ? navigateToSensor : null,
      }
    }
    case 'logic_engine': {
      const ruleName = (meta.rule_name as string) || (meta.rule_id as string) || 'Regel'
      return {
        prefix: 'Regel',
        name: ruleName,
        clickable: !!meta.rule_id,
        navigate: meta.rule_id ? navigateToRule : null,
      }
    }
    case 'device_event': {
      const espName = (meta.esp_id as string) || 'Gerät'
      const reason = (meta.event_type as string) || (meta.reason as string) || ''
      return {
        prefix: 'Gerät',
        name: reason ? `${espName} (${reason})` : espName,
        clickable: !!meta.esp_id,
        navigate: meta.esp_id ? navigateToSensor : null,
      }
    }
    case 'manual':
    case 'system':
    case 'autoops': {
      const reason = (meta.reason as string) || (meta.event_type as string) || 'Systemereignis'
      return {
        prefix: 'System',
        name: reason,
        clickable: false,
        navigate: null,
      }
    }
    case 'freshness_reminder':
    case 'calibration_reminder': {
      const sensorName =
        (meta.sensor_name as string)
        || (meta.sensor_type as string)
        || 'Unbekannter Sensor'
      return {
        prefix: 'Sensor-Hinweis',
        name: sensorName,
        clickable: !!meta.esp_id,
        navigate: meta.esp_id ? navigateToSensor : null,
      }
    }
    case 'grafana': {
      const title = (meta.alert_name as string) || 'Grafana-Alert'
      return {
        prefix: 'Infrastruktur',
        name: title,
        clickable: false,
        navigate: null,
      }
    }
    case 'mqtt_handler': {
      const espName = (meta.esp_id as string) || 'Aktor'
      return {
        prefix: 'Aktor',
        name: espName,
        clickable: !!meta.esp_id,
        navigate: meta.esp_id ? navigateToSensor : null,
      }
    }
    case 'ai_anomaly_service': {
      const sensorName = (meta.sensor_name as string) || (meta.sensor_type as string) || 'KI-Erkennung'
      return {
        prefix: 'KI-Anomalie',
        name: sensorName,
        clickable: !!meta.esp_id,
        navigate: meta.esp_id ? navigateToSensor : null,
      }
    }
    default: {
      // Unknown source — fall back to the human-readable source label.
      const fallback = getNotificationSourceLabel(src)
      return fallback
        ? {
            prefix: fallback,
            name: '',
            clickable: false,
            navigate: null,
          }
        : null
    }
  }
})

function handleSourceLineClick(event: MouseEvent): void {
  if (!sourceLine.value?.clickable || !sourceLine.value.navigate) return
  event.stopPropagation()
  sourceLine.value.navigate()
}

/** CSS class for source badge color (optional differentiation) */
const sourceBadgeClass = computed(() => {
  const s = props.notification.source
  if (!s) return 'item__source-badge--default'
  switch (s) {
    case 'sensor_threshold': return 'item__source-badge--sensor'
    case 'grafana': return 'item__source-badge--infra'
    case 'mqtt_handler': return 'item__source-badge--actuator'
    case 'logic_engine': return 'item__source-badge--rule'
    case 'ai_anomaly_service': return 'item__source-badge--rule'
    case 'freshness_reminder':
    case 'calibration_reminder':
      return 'item__source-badge--sensor'
    default: return 'item__source-badge--default'
  }
})

function formatMeasurementAgeAtAlert(secondsRaw: unknown): string {
  if (typeof secondsRaw !== 'number' || Number.isNaN(secondsRaw) || secondsRaw < 0) {
    return 'Unbekannt'
  }
  const totalSeconds = Math.floor(secondsRaw)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)

  if (hours > 0) return `${hours}h ${minutes}m`
  if (minutes > 0) return `${minutes}m`
  return `${totalSeconds}s`
}

function handleMarkRead(): void {
  if (!props.notification.is_read) {
    emit('mark-read', props.notification.id)
  }
}

function handleAcknowledge(): void {
  emit('acknowledge', props.notification.id)
}

function handleResolve(): void {
  emit('resolve', props.notification.id)
}

function navigateToSensor(): void {
  const target = buildEspContextRoute(props.notification, espStore.devices)
  if (!target) return
  router.push(target)
}

function navigateToRule(): void {
  const ruleId = metadata.value.rule_id as string
  if (ruleId) {
    router.push(`/logic/${ruleId}`)
  }
}

function navigateToCorrelation(): void {
  if (!props.notification.correlation_id) return
  router.push({
    path: '/system-monitor',
    query: {
      tab: 'events',
      correlation: props.notification.correlation_id,
    },
  })
}
</script>

<template>
  <div
    :class="['item', { 'item--unread': !notification.is_read, 'item--resolved': isResolved }]"
    :data-testid="`notification-item-${notification.id}`"
    @click="isExpanded = !isExpanded"
  >
    <!-- Top Row -->
    <div class="item__row">
      <!-- Severity icon: AlertCircle (critical), AlertTriangle (warning), dot fallback -->
      <component
        :is="severityIcon"
        v-if="severityIcon"
        :class="['item__severity-icon', severityIconClass]"
        aria-hidden="true"
      />
      <span v-else class="item__severity-dot" :title="notification.severity ?? ''" />

      <div class="item__content">
        <div class="item__title-row">
          <span :class="['item__title', { 'item__title--unread': !notification.is_read }]">
            {{ notification.title }}
          </span>
          <span v-if="sourceLabel" :class="['item__source-badge', sourceBadgeClass]">
            {{ sourceLabel }}
          </span>
          <span v-if="statusLabel" :class="['item__status', statusClass]">
            {{ statusLabel }}
          </span>
          <span v-if="isAutoResolved" class="item__auto-badge">Auto</span>
        </div>
        <span v-if="notification.body" class="item__body">
          {{ notification.body }}
        </span>
        <!-- AUT-610: Action hint derived from source + severity -->
        <span v-if="actionHint" class="item__action-hint">{{ actionHint }}</span>
        <!-- AUT-246: Source line — "{Source-Type}: {Specific-Name}" with optional navigation -->
        <component
          :is="sourceLine?.clickable ? 'button' : 'span'"
          v-if="sourceLine"
          :class="[
            'item__source-line',
            { 'item__source-line--clickable': sourceLine.clickable },
          ]"
          :type="sourceLine.clickable ? 'button' : undefined"
          :data-testid="`notification-source-line-${notification.id}`"
          @click="handleSourceLineClick"
        >
          <span class="item__source-line-prefix">{{ sourceLine.prefix }}:</span>
          <span class="item__source-line-name">{{ sourceLine.name || '—' }}</span>
        </component>
        <div
          v-if="isArbitrationInfo"
          class="item__arbitration-hint"
          :data-testid="`notification-arbitration-hint-${notification.id}`"
        >
          <Info class="item__arbitration-icon" />
          <span>Dieser Alert ist informativ. Die Regel wurde bereits arbitriert.</span>
        </div>
      </div>

      <div class="item__meta">
        <span class="item__time">{{ formatRelativeTime(notification.created_at) }}</span>
        <component
          :is="isExpanded ? ChevronUp : ChevronDown"
          class="item__chevron"
        />
      </div>
    </div>

    <!-- Expanded Details -->
    <Transition name="expand">
      <div v-if="isExpanded" class="item__details">
        <div class="item__detail-grid">
          <AlertAuditLines
            :acknowledged-at="notification.acknowledged_at"
            :acknowledged-by="notification.acknowledged_by"
            :resolved-at="notification.resolved_at"
          />
          <div v-if="notification.source" class="item__detail">
            <span class="item__detail-label">Quelle</span>
            <span class="item__detail-value">{{ sourceLabel || notification.source }}</span>
          </div>
          <div v-if="notification.category" class="item__detail">
            <span class="item__detail-label">Kategorie</span>
            <span class="item__detail-value">{{ getNotificationCategoryLabel(notification.category) }}</span>
          </div>
          <div v-if="notification.severity" class="item__detail">
            <span class="item__detail-label">Schweregrad</span>
            <span class="item__detail-value">{{ getNotificationSeverityLabel(notification.severity) }}</span>
          </div>
          <div v-if="hasEspId" class="item__detail">
            <span class="item__detail-label">ESP</span>
            <span class="item__detail-value">{{ metadata.esp_id }}</span>
          </div>
          <div v-if="notification.correlation_id" class="item__detail">
            <span class="item__detail-label">Korrelation</span>
            <span class="item__detail-value">{{ notification.correlation_id }}</span>
          </div>
          <div v-if="hasSensorType" class="item__detail">
            <span class="item__detail-label">Sensor</span>
            <span class="item__detail-value">{{ metadata.sensor_type }}</span>
          </div>
          <div v-if="hasMeasurementAgeAtAlert" class="item__detail">
            <span class="item__detail-label">Messwertalter beim Alert</span>
            <span class="item__detail-value">
              {{ formatMeasurementAgeAtAlert(metadata.measurement_age_seconds) }}
            </span>
          </div>
          <div v-if="hasEmailInfo" class="item__detail">
            <span class="item__detail-label">Email</span>
            <span :class="['item__email-status', `item__email-status--${emailStatus}`]">
              <Mail class="item__email-icon" />
              {{ getEmailStatusLabel(emailStatus ?? '') }}
              <span v-if="emailProvider" class="item__email-provider">via {{ emailProvider }}</span>
            </span>
          </div>
          <div v-if="notification.correlation_id" class="item__detail">
            <span class="item__detail-label">Korrelation (MQTT/Log)</span>
            <span class="item__detail-value item__correlation-id">{{ notification.correlation_id }}</span>
          </div>
        </div>

        <div class="item__actions">
          <button
            v-if="canAcknowledge"
            type="button"
            class="item__action item__action--ack"
            title="Alert bestätigen (Acknowledge)"
            :data-testid="`notification-alert-ack-${notification.id}`"
            @click.stop="handleAcknowledge"
          >
            <ShieldCheck class="item__action-icon" />
            Bestätigen
          </button>
          <button
            v-if="canResolve"
            type="button"
            class="item__action item__action--resolve"
            title="Alert erledigen (Resolve)"
            :data-testid="`notification-alert-resolve-${notification.id}`"
            @click.stop="handleResolve"
          >
            <CheckCheck class="item__action-icon" />
            Erledigen
          </button>
          <button
            v-if="!notification.is_read"
            class="item__action"
            title="Als gelesen markieren"
            @click.stop="handleMarkRead"
          >
            <Check class="item__action-icon" />
            Als gelesen
          </button>
          <button
            v-if="hasEspId"
            class="item__action"
            title="Zum Gerät"
            @click.stop="navigateToSensor"
          >
            <Activity class="item__action-icon" />
            Zum Gerät
          </button>
          <button
            v-if="notification.correlation_id"
            class="item__action"
            title="Im Ereignis-Monitor anzeigen"
            @click.stop="navigateToCorrelation"
          >
            <Activity class="item__action-icon" />
            Ereignis-Details
          </button>
          <button
            v-if="hasRuleId"
            class="item__action"
            title="Zur Regel"
            @click.stop="navigateToRule"
          >
            <Workflow class="item__action-icon" />
            Zur Regel
          </button>
          <a
            v-if="notification.source === 'grafana'"
            class="item__action"
            :href="`${GRAFANA_BASE_URL}/alerting/list`"
            target="_blank"
            title="In Grafana öffnen"
            @click.stop
          >
            <BarChart3 class="item__action-icon" />
            In Grafana
          </a>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.item {
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--glass-border);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.item:hover {
  background: rgba(255, 255, 255, 0.02);
}

.item--unread {
  background: rgba(96, 165, 250, 0.03);
}

.item__row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
}

/* Severity Dot */
.item__dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
  margin-top: 5px;
}

.item__dot--critical {
  background: var(--color-error);
  box-shadow: 0 0 6px rgba(248, 113, 113, 0.4);
}

.item__dot--warning {
  background: var(--color-warning);
}

.item__dot--info {
  background: var(--color-info);
}

/* Resolved item */
.item--resolved {
  opacity: 0.6;
}

/* Content */
.item__content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.item__title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}

/* Source Badge (Alert-Basis 3) */
.item__source-badge {
  flex-shrink: 0;
  padding: 1px var(--space-1);
  font-size: var(--text-xxs);
  font-weight: 600;
  border-radius: var(--radius-xs);
  text-transform: uppercase;
  letter-spacing: 0.03em;
  line-height: 1.4;
}

.item__source-badge--sensor {
  color: var(--color-info);
  background: rgba(96, 165, 250, 0.12);
}

.item__source-badge--infra {
  color: var(--color-warning);
  background: rgba(251, 191, 36, 0.12);
}

.item__source-badge--actuator {
  color: var(--color-iridescent-3);
  background: rgba(167, 139, 250, 0.12);
}

.item__source-badge--rule {
  color: var(--color-iridescent-2);
  background: rgba(129, 140, 248, 0.12);
}

.item__source-badge--default {
  color: var(--color-text-muted);
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--glass-border);
}

/* Status Badge */
.item__status {
  flex-shrink: 0;
  padding: 1px var(--space-1);
  font-size: var(--text-xxs);
  font-weight: 600;
  border-radius: var(--radius-xs);
  text-transform: uppercase;
  letter-spacing: 0.03em;
  line-height: 1.4;
}

.item__status--active {
  color: var(--color-error);
  background: rgba(248, 113, 113, 0.12);
}

.item__status--acknowledged {
  color: var(--color-warning);
  background: rgba(251, 191, 36, 0.12);
}

.item__status--resolved {
  color: var(--color-success);
  background: rgba(52, 211, 153, 0.12);
}

/* Auto-resolve badge */
.item__auto-badge {
  flex-shrink: 0;
  padding: 1px var(--space-1);
  font-size: var(--text-xxs);
  font-weight: 600;
  color: var(--color-text-muted);
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-xs);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.item__title {
  flex: 1 1 8rem;
  min-width: 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.item__title--unread {
  color: var(--color-text-primary);
  font-weight: 600;
}

.item__body {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* AUT-246: Source line ("Sensor-Schwelle: …", "Regel: …", "Gerät: …", "System: …") */
.item__source-line {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  margin-top: 2px;
  padding: 1px var(--space-1);
  font-size: var(--text-xxs);
  color: var(--color-text-secondary);
  background: transparent;
  border: none;
  border-radius: var(--radius-xs);
  align-self: flex-start;
  text-align: left;
  font-family: inherit;
}

.item__source-line--clickable {
  color: var(--color-info);
  cursor: pointer;
  transition: color var(--transition-fast), background var(--transition-fast);
}

.item__source-line--clickable:hover {
  color: var(--color-text-primary);
  background: rgba(96, 165, 250, 0.08);
}

.item__source-line-prefix {
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.item__source-line-name {
  font-weight: 500;
}

/* Meta (time + chevron) */
.item__meta {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  flex-shrink: 0;
}

.item__time {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.item__chevron {
  width: 14px;
  height: 14px;
  color: var(--color-text-muted);
  pointer-events: none;
}

/* Expanded Details */
.item__details {
  margin-top: var(--space-3);
  padding-top: var(--space-3);
  border-top: 1px solid var(--glass-border);
}

.item__detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

.item__detail--full-width {
  grid-column: 1 / -1;
}

.item__detail {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.item__detail-label {
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.item__detail-value {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  font-family: var(--font-mono);
}

.item__correlation-id {
  overflow-wrap: anywhere;
  word-break: break-all;
}

/* Email Status (Phase C V1.1) */
.item__email-status {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: var(--text-xs);
  font-family: var(--font-mono);
}

.item__email-status--sent {
  color: var(--color-success);
}

.item__email-status--failed {
  color: var(--color-error);
}

.item__email-status--pending {
  color: var(--color-text-muted);
}

.item__email-status--permanently_failed {
  color: var(--color-error);
}

.item__email-icon {
  width: 11px;
  height: 11px;
}

.item__email-provider {
  color: var(--color-text-muted);
  font-size: var(--text-xxs);
}

/* AUT-610: Severity icon (replaces compact StatusBadge dot) */
.item__severity-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  margin-top: 2px;
}

.item__severity-icon--critical {
  color: var(--color-error);
}

.item__severity-icon--warning {
  color: var(--color-warning);
}

/* Info/fallback dot when no specific icon */
.item__severity-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
  margin-top: 5px;
  background: var(--color-info);
}

/* AUT-610: Operator action hint */
.item__action-hint {
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
  font-style: italic;
  margin-top: 1px;
}

/* Arbitration Info Hint (AUT-131 B-CNFL2-04) */
.item__arbitration-hint {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  margin-top: var(--space-1);
  padding: 3px var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-info);
  background: var(--color-info-bg);
  border: 1px solid var(--color-info-border);
  border-radius: var(--radius-sm);
  align-self: flex-start;
}

.item__arbitration-icon {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
}

/* Action Buttons */
.item__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.item__action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-1);
  min-height: 44px;
  min-width: 44px;
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-secondary);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  text-decoration: none;
}

.item__action:hover {
  color: var(--color-text-primary);
  background: rgba(255, 255, 255, 0.06);
  border-color: var(--glass-border-hover);
}

.item__action--ack {
  color: var(--color-warning);
  border-color: rgba(251, 191, 36, 0.2);
}

.item__action--ack:hover {
  color: var(--color-warning);
  background: rgba(251, 191, 36, 0.08);
  border-color: rgba(251, 191, 36, 0.3);
}

.item__action--resolve {
  color: var(--color-success);
  border-color: rgba(52, 211, 153, 0.2);
}

.item__action--resolve:hover {
  color: var(--color-success);
  background: rgba(52, 211, 153, 0.08);
  border-color: rgba(52, 211, 153, 0.3);
}

.item__action-icon {
  width: 12px;
  height: 12px;
  pointer-events: none;
}

/* Expand Transition */
.expand-enter-active,
.expand-leave-active {
  transition: all var(--transition-fast);
  overflow: hidden;
}

.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  max-height: 0;
}

.expand-enter-to,
.expand-leave-from {
  opacity: 1;
  max-height: 80rem;
}
</style>
