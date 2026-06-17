<script setup lang="ts">
/**
 * ActuatorSatellite Component
 *
 * Displays an actuator as a "satellite" card around the main ESP card.
 * Shows actuator status (ON/OFF/PWM value).
 *
 * Features:
 * - Status display (AN/AUS/PWM-Wert)
 * - Icon based on actuator type
 * - Click to show connection lines to linked sensors
 * - Draggable for future chart integration (Phase 4)
 */

import { computed, ref } from 'vue'
import { Power, ToggleRight, Waves, GitBranch, Fan, Flame, Lightbulb, Cog } from 'lucide-vue-next'
import { Badge } from '@/shared/design'
import { getActuatorTypeInfo } from '@/utils/labels'
import { formatRelativeTime } from '@/utils/formatters'
import { useDragStateStore } from '@/shared/stores/dragState.store'
import { useEspStore } from '@/stores/esp'

interface Props {
  /** ESP ID this actuator belongs to */
  espId: string
  /** GPIO pin number */
  gpio: number
  /** Actuator type (server-normalized, e.g. 'digital', 'pwm') */
  actuatorType: string
  /** Original ESP32 hardware type (relay, pump, valve, pwm) for icon lookup */
  hardwareType?: string | null
  /** Actuator name (optional) */
  name?: string | null
  /** Current state (ON/OFF) */
  state: boolean
  /** PWM value (0-255, if applicable) */
  pwmValue?: number
  /** Last acknowledged command timestamp */
  lastCommandAt?: string | null
  /** Last logic trigger timestamp */
  lastTriggeredAt?: string | null
  /** Raw trigger reason from rule execution */
  triggerReason?: string | null
  /** Rule name that triggered the last execution */
  triggerRuleName?: string | null
  /** Whether actuator is emergency stopped */
  emergencyStopped?: boolean
  /** Whether this actuator is selected/highlighted */
  selected?: boolean
  /** Whether to show connection lines on click */
  showConnections?: boolean
  /** Whether dragging is enabled */
  draggable?: boolean
  /** Device scope (T13-R3 WP4): zone_local, multi_zone, mobile */
  deviceScope?: 'zone_local' | 'multi_zone' | 'mobile' | null
  /** Assigned zones for multi_zone/mobile devices */
  assignedZones?: string[]
}

const props = withDefaults(defineProps<Props>(), {
  emergencyStopped: false,
  selected: false,
  showConnections: false,
  draggable: true,
  deviceScope: null,
  assignedZones: () => [],
})

const emit = defineEmits<{
  click: [gpio: number]
  showConnections: [gpio: number]
}>()

// Drag state store (global ESP-Card drag tracking)
const dragStore = useDragStateStore()
const espStore = useEspStore()

// Drag state
const isDragging = ref(false)

/**
 * Effective draggable state.
 * KRITISCH: Wenn ein ESP-Card-Drag (VueDraggable) aktiv ist,
 * muss das Actuator-eigene draggable deaktiviert werden,
 * da es sonst den VueDraggable-Drag stören würde.
 */
const effectiveDraggable = computed(() => {
  if (dragStore.isDraggingEspCard) {
    return false
  }
  return props.draggable
})

// Get actuator type info — hardware_type preferred for icon lookup (pump/valve/relay differentiation)
const actuatorInfo = computed(() => getActuatorTypeInfo(props.actuatorType, props.hardwareType))

// Get actuator icon component
const actuatorIcon = computed(() => {
  const iconName = actuatorInfo.value.icon.toLowerCase()
  if (iconName.includes('toggle')) return ToggleRight
  if (iconName.includes('waves') || iconName.includes('pump')) return Waves
  if (iconName.includes('branch') || iconName.includes('valve')) return GitBranch
  if (iconName.includes('fan')) return Fan
  if (iconName.includes('flame') || iconName.includes('heater')) return Flame
  if (iconName.includes('lightbulb') || iconName.includes('light')) return Lightbulb
  if (iconName.includes('cog') || iconName.includes('motor')) return Cog
  return Power
})

// Scope badge (T13-R3 WP4): only show for non-default scopes
const scopeBadge = computed(() => {
  const scope = props.deviceScope
  if (!scope || scope === 'zone_local') return null
  if (scope === 'multi_zone') return { text: 'MZ', cls: 'actuator-satellite__scope-badge--multi-zone' }
  if (scope === 'mobile') return { text: 'Mob', cls: 'actuator-satellite__scope-badge--mobile' }
  return null
})

const scopeTooltip = computed(() => {
  if (!scopeBadge.value) return ''
  if (props.deviceScope === 'multi_zone' && props.assignedZones?.length) {
    return `Multi-Zone: ${props.assignedZones.join(', ')}`
  }
  if (props.deviceScope === 'mobile') return 'Mobiles Gerät'
  return ''
})

function humanizeTriggerReason(reason: string | null | undefined): string | null {
  if (!reason) return null

  const normalized = reason.trim().toLowerCase()
  if (!normalized) return null

  if (normalized.includes('sensor') || normalized.includes('threshold')) {
    return 'Sensorbedingung erfuellt'
  }
  if (normalized.includes('hysteresis')) {
    return 'Hysterese-Bedingung erfuellt'
  }
  if (normalized.includes('time') || normalized.includes('schedule')) {
    return 'Zeitfenster aktiv'
  }
  if (normalized.includes('manual')) {
    return 'Manuell ausgeloest'
  }
  if (normalized.includes('startup') || normalized.includes('boot')) {
    return 'Systemstart'
  }

  const cleaned = reason.split('_').join(' ').trim()
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1)
}

const lastActionText = computed(() => {
  if (props.lastTriggeredAt) return formatRelativeTime(props.lastTriggeredAt)
  if (props.lastCommandAt) return formatRelativeTime(props.lastCommandAt)
  return null
})

const triggerReasonLabel = computed(() => humanizeTriggerReason(props.triggerReason))

const hasContextInfo = computed(() =>
  Boolean(lastActionText.value || triggerReasonLabel.value || props.triggerRuleName)
)

const cardTitle = computed(() => {
  const parts = [`${props.name || actuatorInfo.value.label} (GPIO ${props.gpio})`]
  if (lastActionText.value) parts.push(`Zuletzt: ${lastActionText.value}`)
  if (props.triggerRuleName) parts.push(`Regel: ${props.triggerRuleName}`)
  if (triggerReasonLabel.value) parts.push(`Grund: ${triggerReasonLabel.value}`)
  return parts.join('\n')
})

// Status display
const statusDisplay = computed(() => {
  if (props.emergencyStopped) {
    return { text: 'Not-Stopp', variant: 'danger' as const }
  }
  
  if (props.actuatorType === 'pwm' || props.actuatorType === 'fan') {
    const pwm = props.pwmValue || 0
    const percent = Math.round((pwm / 255) * 100)
    return {
      text: `${percent}%`,
      variant: pwm > 0 ? 'success' : 'gray'
    } as const
  }

  return {
    text: props.state ? 'AN' : 'AUS',
    variant: props.state ? 'success' : 'gray'
  } as const
})

// Toggle ON/OFF — stopPropagation prevents Config Wizard from opening
async function handleToggle(event: MouseEvent) {
  event.stopPropagation()
  if (props.emergencyStopped) return
  await espStore.sendActuatorCommand(props.espId, props.gpio, props.state ? 'OFF' : 'ON')
}

// Whether quick-toggle is available (digital/relay only, not PWM/fan)
const isToggleable = computed(() =>
  props.actuatorType !== 'pwm' && props.actuatorType !== 'fan'
)

// Handle click
function handleClick() {
  emit('click', props.gpio)
  if (props.showConnections) {
    emit('showConnections', props.gpio)
  }
}

// Drag handlers (Phase 4)
function handleDragStart(event: DragEvent) {
  if (!props.draggable || !event.dataTransfer) return

  // KRITISCH: Verhindere dass VueDraggable (Parent) das Event abfängt!
  // Ohne stopPropagation() würde VueDraggable denken, eine ESP-Card wird gedraggt.
  event.stopPropagation()

  isDragging.value = true

  // Set drag data with actuator info
  const dragData = {
    type: 'actuator' as const,
    espId: props.espId,
    gpio: props.gpio,
    actuatorType: props.actuatorType,
    name: props.name || actuatorInfo.value.label,
  }
  event.dataTransfer.setData('application/json', JSON.stringify(dragData))
  event.dataTransfer.effectAllowed = 'copy'
}

function handleDragEnd(event: DragEvent) {
  // KRITISCH: Auch hier stopPropagation für konsistentes Verhalten
  event.stopPropagation()
  isDragging.value = false
}
</script>

<template>
  <div
    :class="[
      'actuator-satellite',
      {
        'actuator-satellite--selected': selected,
        'actuator-satellite--active': state && !emergencyStopped,
        'actuator-satellite--emergency': emergencyStopped,
        'actuator-satellite--dragging': isDragging,
        'actuator-satellite--draggable': effectiveDraggable,
        'actuator-satellite--with-context': hasContextInfo,
      }
    ]"
    :data-esp-id="espId"
    :data-gpio="gpio"
    data-satellite-type="actuator"
    :draggable="effectiveDraggable"
    :title="cardTitle"
    @click="handleClick"
    @dragstart="handleDragStart"
    @dragend="handleDragEnd"
  >
    <div class="actuator-satellite__top">
      <div
        class="actuator-satellite__icon"
        :class="[
          `actuator-satellite__icon--${statusDisplay.variant}`,
          { 'actuator-satellite__icon--active': state && !emergencyStopped }
        ]"
      >
        <component :is="actuatorIcon" class="w-4 h-4" />
      </div>

      <div class="actuator-satellite__main">
        <div class="actuator-satellite__title-row">
          <span class="actuator-satellite__label" :title="name || actuatorInfo.label">
            {{ name || actuatorInfo.label }}
          </span>
          <span class="actuator-satellite__gpio-badge">GPIO {{ gpio }}</span>
        </div>

        <div class="actuator-satellite__meta-row">
          <Badge
            :variant="statusDisplay.variant"
            size="xs"
            :pulse="state && !emergencyStopped"
            class="actuator-satellite__badge"
          >
            {{ statusDisplay.text }}
          </Badge>

          <button
            v-if="isToggleable"
            class="actuator-satellite__toggle"
            :class="{
              'actuator-satellite__toggle--on': state && !emergencyStopped,
              'actuator-satellite__toggle--disabled': emergencyStopped,
            }"
            :disabled="emergencyStopped"
            @click.stop="handleToggle"
            :title="state ? 'Ausschalten' : 'Einschalten'"
          >
            <span class="actuator-satellite__toggle-thumb" />
          </button>

          <span
            v-if="scopeBadge"
            :class="['actuator-satellite__scope-badge', scopeBadge.cls]"
            :title="scopeTooltip"
          >
            {{ scopeBadge.text }}
          </span>
        </div>
      </div>
    </div>

    <div v-if="hasContextInfo" class="actuator-satellite__context">
      <span v-if="lastActionText" class="actuator-satellite__context-line">
        Zuletzt: {{ lastActionText }}
      </span>
      <span v-if="triggerRuleName" class="actuator-satellite__context-line actuator-satellite__context-line--rule">
        {{ triggerRuleName }}
      </span>
      <span v-if="triggerReasonLabel" class="actuator-satellite__context-line">
        {{ triggerReasonLabel }}
      </span>
    </div>

    <!-- Connection indicator (if has connections) -->
    <div v-if="showConnections" class="actuator-satellite__connection-indicator" />
  </div>
</template>

<style scoped>
/* =============================================================================
   ActuatorSatellite - Compact Vertical Design for Side-by-Side Layout
   Optimized for narrow columns in horizontal ESP layout
   ============================================================================= */

.actuator-satellite {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0.3125rem;
  padding: 0.5625rem;
  background: rgba(30, 32, 40, 0.9);
  border: 1px solid var(--glass-border);
  border-top: 2px solid var(--color-iridescent-2);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  width: 150px;
  max-width: 150px;
  min-width: 0;
  min-height: 88px;
  backdrop-filter: blur(10px);
  box-shadow:
    0 2px 8px rgba(0, 0, 0, 0.2),
    0 4px 16px rgba(0, 0, 0, 0.1);
}

.actuator-satellite--with-context {
  min-height: 112px;
  padding: 0.625rem;
}

.actuator-satellite:hover {
  border-color: var(--color-iridescent-1);
  transform: translateY(-2px);
  background: rgba(40, 42, 54, 0.95);
  /* Enhanced hover shadow */
  box-shadow:
    0 4px 12px rgba(0, 0, 0, 0.25),
    0 8px 24px rgba(0, 0, 0, 0.15),
    0 0 16px rgba(167, 139, 250, 0.15);
}

.actuator-satellite--selected {
  border-color: var(--color-iridescent-1);
  box-shadow: 0 0 0 2px rgba(167, 139, 250, 0.2);
}

.actuator-satellite--draggable {
  cursor: grab;
}

.actuator-satellite--draggable:active {
  cursor: grabbing;
}

.actuator-satellite--dragging {
  opacity: 0.7;
  transform: scale(0.95);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.4);
}

.actuator-satellite--active {
  border-color: var(--color-success);
  border-left: 3px solid var(--color-success);
  background: color-mix(in srgb, var(--color-success) 10%, rgba(30, 32, 40, 0.9));
  box-shadow:
    0 2px 8px rgba(0, 0, 0, 0.2),
    0 4px 16px rgba(0, 0, 0, 0.1),
    0 0 14px color-mix(in srgb, var(--color-success) 20%, transparent);
}

.actuator-satellite--emergency {
  border-color: var(--color-error);
  border-left: 3px solid var(--color-error);
  background: color-mix(in srgb, var(--color-error) 15%, rgba(30, 32, 40, 0.9));
  animation: pulse-emergency 1s infinite;
}

@keyframes pulse-emergency {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

/* Top section with icon + content */
.actuator-satellite__top {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  width: 100%;
}

/* Icon - compact circle */
.actuator-satellite__icon {
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  flex-shrink: 0;
  transition: all 0.2s;
}

.actuator-satellite__main {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 0;
  width: 100%;
}

.actuator-satellite__title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.375rem;
  min-width: 0;
}

.actuator-satellite__meta-row {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 0.375rem;
  min-width: 0;
}

.actuator-satellite__icon--success {
  background-color: rgba(52, 211, 153, 0.15);
  color: var(--color-success);
}

.actuator-satellite__icon--gray {
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-muted);
}

.actuator-satellite__icon--danger {
  background-color: rgba(248, 113, 113, 0.15);
  color: var(--color-error);
}

.actuator-satellite__icon--active {
  animation: pulse-icon 2s infinite;
}

@keyframes pulse-icon {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

/* Badge - centered */
.actuator-satellite__badge {
  align-self: flex-start;
}

/* Label - compact, up to 2 lines */
.actuator-satellite__label {
  font-size: 0.6875rem;
  font-weight: 500;
  color: var(--color-text-secondary);
  text-align: left;
  max-width: 100%;
  line-height: 1.2;
  /* Allow up to 2 lines for longer names */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
  max-height: 2.4em;
}

.actuator-satellite__gpio-badge {
  font-family: var(--font-mono);
  font-size: var(--text-xxs);
  font-weight: 500;
  color: rgba(255, 255, 255, 0.45);
  background: rgba(255, 255, 255, 0.04);
  padding: 0.0625rem 0.25rem;
  border-radius: var(--radius-xs);
  flex-shrink: 0;
  white-space: nowrap;
  overflow: visible;
}

.actuator-satellite__context {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.125rem;
  width: 100%;
  margin-top: 0.125rem;
  padding-top: 0.25rem;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.actuator-satellite__context-line {
  width: 100%;
  text-align: left;
  color: var(--color-text-muted);
  font-size: 0.5625rem;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.actuator-satellite__context-line--rule {
  color: var(--color-text-secondary);
  font-weight: 500;
}

/* Scope badges (T13-R3 WP4) */
.actuator-satellite__scope-badge {
  font-size: 7px;
  font-weight: 600;
  padding: 0.0625rem 0.25rem;
  border-radius: var(--radius-xs);
  white-space: nowrap;
  cursor: default;
}

.actuator-satellite__scope-badge--multi-zone {
  background: rgba(96, 165, 250, 0.2);
  color: rgb(96, 165, 250);
}

.actuator-satellite__scope-badge--mobile {
  background: rgba(251, 146, 60, 0.2);
  color: rgb(251, 146, 60);
}

/* Toggle slider — 28×16px quick on/off for digital actuators */
.actuator-satellite__toggle {
  width: 28px;
  height: 16px;
  flex-shrink: 0;
  position: relative;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  background: var(--color-bg-tertiary, rgba(255, 255, 255, 0.06));
  cursor: pointer;
  padding: 0;
  transition: background 0.2s, border-color 0.2s;
}

.actuator-satellite__toggle--on {
  background: var(--color-real);
  border-color: var(--color-real);
}

.actuator-satellite__toggle--disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.actuator-satellite__toggle-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 10px;
  height: 10px;
  background: rgba(255, 255, 255, 0.85);
  border-radius: 50%;
  transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.actuator-satellite__toggle--on .actuator-satellite__toggle-thumb {
  transform: translateX(12px);
}

/* Connection indicator */
.actuator-satellite__connection-indicator {
  position: absolute;
  top: 0.25rem;
  right: 0.25rem;
  width: 0.375rem;
  height: 0.375rem;
  border-radius: 50%;
  background-color: var(--color-success);
  animation: pulse-dot 2s infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>



