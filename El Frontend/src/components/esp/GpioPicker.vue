<script setup lang="ts">
/**
 * GPIO Pin Picker Component
 *
 * Provides a user-friendly interface for selecting GPIO pins on ESP32 devices.
 * Supports both dropdown (compact) and grid (visual) display variants.
 *
 * Features:
 * - Real-time GPIO availability from useGpioStatus composable
 * - Sensor/Actuator type-based recommendations
 * - Mock-ESP fallback to static GPIO list
 * - Validation with detailed error messages
 *
 * @example
 * <GpioPicker
 *   v-model="selectedGpio"
 *   :esp-id="espId"
 *   :sensor-type="sensorType"
 *   variant="dropdown"
 *   @validation-change="onValidationChange"
 * />
 *
 * @author KI-Agent (Claude)
 * @since Phase 5 (GPIO-Picker & Add-Sensor/Actuator-Flow)
 */

import { computed, watch } from 'vue'
import { useGpioStatus } from '@/composables/useGpioStatus'
import { useBoardLayout } from '@/composables/useBoardLayout'
import { useEspStore } from '@/stores/esp'
import { getRecommendedGpios, getGpioConfig, type HardwareType } from '@/utils/gpioConfig'
import type { GpioPinStatus } from '@/types/gpio'

// Icons from lucide-vue-next
import { Check, Lock, Activity, Zap, Cpu } from 'lucide-vue-next'

// ════════════════════════════════════════════════════════════════
// PROPS & EMITS
// ════════════════════════════════════════════════════════════════

interface Props {
  /** Selected GPIO pin (v-model) */
  modelValue: number | null
  /** ESP device ID */
  espId: string
  /** Sensor type for recommendations (optional) */
  sensorType?: string
  /** Actuator type for recommendations (optional) */
  actuatorType?: string
  /** Disable all interaction */
  disabled?: boolean
  /** Display variant */
  variant?: 'dropdown' | 'grid'
  /** Placeholder text for dropdown */
  placeholder?: string
  /** Show only available pins in dropdown (hide reserved) */
  showOnlyAvailable?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  sensorType: undefined,
  actuatorType: undefined,
  disabled: false,
  variant: 'dropdown',
  placeholder: 'GPIO auswählen...',
  showOnlyAvailable: true,
})

const emit = defineEmits<{
  'update:modelValue': [value: number | null]
  'validation-change': [valid: boolean, message: string | null]
}>()

// ════════════════════════════════════════════════════════════════
// GPIO STATUS (Phase 3 Composable)
// ════════════════════════════════════════════════════════════════

const {
  gpioStatus,
  allPinStatuses,
  isLoading,
  validateGpio,
  validateGpioForSensor,
  isOneWireBus,
  refresh,
} = useGpioStatus(computed(() => props.espId))

// ════════════════════════════════════════════════════════════════
// BOARD-AWARE FALLBACK
// ════════════════════════════════════════════════════════════════

const espStore = useEspStore()
const deviceHardwareType = computed(() => {
  const device = espStore.devices.find(d => espStore.getDeviceId(d) === props.espId)
  return (device as any)?.hardware_type ?? null
})
const { layout: boardLayout } = useBoardLayout(deviceHardwareType)

/**
 * Check if we have dynamic GPIO status from the server.
 * If not, we'll use static GPIO config as fallback.
 */
const hasDynamicStatus = computed(() => gpioStatus.value !== null)

/**
 * Static GPIO list for fallback when server GPIO status is not available.
 * Board-aware via useBoardLayout; falls back to WROOM config for unknown boards.
 */
const staticFallbackPins = computed<GpioPinStatus[]>(() => {
  const gpios: number[] = boardLayout.value
    ? [...boardLayout.value.safeGpios]
    : getGpioConfig('ESP32_WROOM')
        .filter(pin => pin.category !== 'avoid')
        .map(pin => pin.gpio)
  return gpios
    .sort((a, b) => a - b)
    .map(gpio => ({
      gpio,
      available: true,
      owner: null,
      component: null,
      name: `GPIO ${gpio}`,
      statusClass: 'available' as const,
      tooltip: `GPIO ${gpio}`,
    }))
})

/**
 * Effective pin list: Use dynamic status if available, otherwise static fallback.
 */
const effectivePinStatuses = computed<GpioPinStatus[]>(() => {
  if (hasDynamicStatus.value && allPinStatuses.value.length > 0) {
    return allPinStatuses.value
  }
  return staticFallbackPins.value
})

// ════════════════════════════════════════════════════════════════
// COMPUTED
// ════════════════════════════════════════════════════════════════

/**
 * Recommended GPIOs for the selected sensor/actuator type.
 */
const recommendedGpios = computed<number[]>(() => {
  const hwType = deviceHardwareType.value as HardwareType | null
  if (props.sensorType) {
    return getRecommendedGpios(props.sensorType, 'sensor', hwType)
  }
  if (props.actuatorType) {
    return getRecommendedGpios(props.actuatorType, 'actuator', hwType)
  }
  return []
})

/**
 * Check if current sensor type is a OneWire sensor (DS18B20).
 */
const isCurrentSensorOneWire = computed(() => {
  return props.sensorType?.toLowerCase().includes('ds18b20') ?? false
})

/**
 * Enriched pin list with recommended and selected flags.
 * 
 * OneWire Multi-Device Support: Marks OneWire bus pins as available
 * for DS18B20 sensors even if they're technically "reserved".
 */
const enrichedPins = computed(() => {
  return effectivePinStatuses.value.map(pin => {
    // OneWire Special Case: If this is a DS18B20 sensor and the pin is a OneWire bus,
    // mark it as available even though it's "reserved"
    let isAvailableForSensor = pin.available
    if (isCurrentSensorOneWire.value && isOneWireBus(pin.gpio)) {
      isAvailableForSensor = true
    }

    return {
      ...pin,
      available: isAvailableForSensor,
      recommended: recommendedGpios.value.includes(pin.gpio),
      selected: pin.gpio === props.modelValue,
    }
  })
})

/**
 * Available pins only (for dropdown).
 */
const availablePins = computed(() => {
  return enrichedPins.value.filter(pin => pin.available)
})

/**
 * Recommended pins that are available.
 */
const recommendedAvailablePins = computed(() => {
  return availablePins.value.filter(pin => pin.recommended)
})

/**
 * Non-recommended available pins.
 */
const otherAvailablePins = computed(() => {
  return availablePins.value.filter(pin => !pin.recommended)
})

/**
 * Validation state.
 * 
 * OneWire Multi-Device Support: Uses validateGpioForSensor when a sensor type
 * is provided, which allows DS18B20 sensors to share GPIOs with other DS18B20s.
 */
const validation = computed(() => {
  if (props.modelValue === null) {
    return { valid: false, message: 'Bitte GPIO auswählen' }
  }

  // If using static fallback, always valid (no server-side validation)
  if (!hasDynamicStatus.value) {
    return { valid: true, message: null }
  }

  // Use sensor-type-aware validation if sensor type is provided
  if (props.sensorType) {
    return validateGpioForSensor(props.modelValue, props.sensorType)
  }

  return validateGpio(props.modelValue)
})

/**
 * Show static fallback hint.
 */
const showFallbackHint = computed(() => {
  return !hasDynamicStatus.value && !isLoading.value
})

// ════════════════════════════════════════════════════════════════
// METHODS
// ════════════════════════════════════════════════════════════════

/**
 * Select a GPIO pin.
 */
function selectGpio(gpio: number | string): void {
  if (props.disabled) return

  const gpioNum = typeof gpio === 'string' ? parseInt(gpio, 10) : gpio
  if (isNaN(gpioNum)) return

  // Check if pin is available
  const pin = enrichedPins.value.find(p => p.gpio === gpioNum)
  if (pin && !pin.available && hasDynamicStatus.value) {
    // Pin not available (only enforce when we have dynamic status)
    return
  }

  emit('update:modelValue', gpioNum)
}

/**
 * Handle dropdown change event.
 */
function onDropdownChange(event: Event): void {
  const target = event.target as HTMLSelectElement
  const value = target.value

  if (value === '' || value === 'null') {
    emit('update:modelValue', null)
    return
  }

  selectGpio(parseInt(value, 10))
}

/**
 * Get status icon component for a pin.
 */
function getStatusIcon(pin: GpioPinStatus) {
  if (pin.owner === 'system') return Lock
  if (pin.owner === 'sensor') return Activity
  if (pin.owner === 'actuator') return Zap
  return null
}

/**
 * Get CSS classes for a pin in grid mode.
 */
function getPinClasses(pin: GpioPinStatus & { selected: boolean; recommended: boolean }): string {
  const classes = ['gpio-pin']

  if (pin.selected) {
    classes.push('gpio-pin--selected')
  } else if (!pin.available) {
    classes.push('gpio-pin--disabled')
  } else if (pin.recommended) {
    classes.push('gpio-pin--recommended')
  } else {
    classes.push('gpio-pin--available')
  }

  // Add owner-based class
  if (pin.owner) {
    classes.push(`gpio-pin--${pin.owner}`)
  }

  return classes.join(' ')
}

// ════════════════════════════════════════════════════════════════
// WATCHERS
// ════════════════════════════════════════════════════════════════

// Emit validation changes
watch(
  validation,
  newVal => {
    emit('validation-change', newVal.valid, newVal.message)
  },
  { immediate: true }
)

// Re-validate when espId changes
watch(
  () => props.espId,
  () => {
    refresh()
  }
)

// Re-emit validation when sensor/actuator type changes (recommendations change)
watch(
  [() => props.sensorType, () => props.actuatorType],
  () => {
    // Trigger validation re-emit
    emit('validation-change', validation.value.valid, validation.value.message)
  }
)
</script>

<template>
  <div class="gpio-picker" :class="{ 'gpio-picker--disabled': disabled }">
    <!-- Loading State -->
    <div v-if="isLoading" class="gpio-picker__loading">
      <span class="gpio-picker__spinner" />
      <span>GPIO-Status wird geladen...</span>
    </div>

    <!-- Dropdown Variant -->
    <template v-else-if="variant === 'dropdown'">
      <div class="gpio-picker__dropdown">
        <select
          :value="modelValue ?? ''"
          :disabled="disabled"
          class="gpio-picker__select"
          @change="onDropdownChange"
        >
          <option value="" disabled>{{ placeholder }}</option>

          <!-- Recommended pins (if any available) -->
          <optgroup v-if="recommendedAvailablePins.length > 0" label="Empfohlen">
            <option v-for="pin in recommendedAvailablePins" :key="pin.gpio" :value="pin.gpio">
              GPIO {{ pin.gpio }} ★
            </option>
          </optgroup>

          <!-- Other available pins -->
          <optgroup v-if="otherAvailablePins.length > 0" label="Verfügbar">
            <option v-for="pin in otherAvailablePins" :key="pin.gpio" :value="pin.gpio">
              GPIO {{ pin.gpio }}
            </option>
          </optgroup>

          <!-- Fallback: All available if no grouping needed -->
          <template v-if="recommendedAvailablePins.length === 0 && otherAvailablePins.length === 0">
            <option v-for="pin in availablePins" :key="pin.gpio" :value="pin.gpio">
              GPIO {{ pin.gpio }}
            </option>
          </template>
        </select>

        <!-- Fallback Hint -->
        <p v-if="showFallbackHint" class="gpio-picker__hint">
          <Cpu class="gpio-picker__hint-icon" />
          Statische GPIO-Liste (kein Live-Status)
        </p>

        <!-- Validation Error -->
        <p v-if="!validation.valid && modelValue !== null" class="gpio-picker__error">
          {{ validation.message }}
        </p>
      </div>
    </template>

    <!-- Grid Variant -->
    <template v-else-if="variant === 'grid'">
      <div class="gpio-picker__grid">
        <button
          v-for="pin in enrichedPins"
          :key="pin.gpio"
          type="button"
          :class="getPinClasses(pin)"
          :disabled="(!pin.available && hasDynamicStatus) || disabled"
          :title="pin.tooltip"
          @click="selectGpio(pin.gpio)"
        >
          <span class="gpio-pin__number">{{ pin.gpio }}</span>

          <!-- Status Icon -->
          <component
            v-if="pin.selected"
            :is="Check"
            class="gpio-pin__icon gpio-pin__icon--check"
          />
          <component
            v-else-if="getStatusIcon(pin)"
            :is="getStatusIcon(pin)"
            class="gpio-pin__icon"
          />

          <!-- Recommended Indicator -->
          <span v-if="pin.recommended && pin.available" class="gpio-pin__recommended" />
        </button>
      </div>

      <!-- Legend -->
      <div class="gpio-picker__legend">
        <span class="legend-item legend-item--available">
          <span class="legend-dot" /> Verfügbar
        </span>
        <span v-if="recommendedGpios.length > 0" class="legend-item legend-item--recommended">
          <span class="legend-dot" /> Empfohlen
        </span>
        <span class="legend-item legend-item--sensor">
          <span class="legend-dot" /> Sensor
        </span>
        <span class="legend-item legend-item--actuator">
          <span class="legend-dot" /> Aktor
        </span>
        <span class="legend-item legend-item--system">
          <span class="legend-dot" /> System
        </span>
      </div>

      <!-- Fallback Hint -->
      <p v-if="showFallbackHint" class="gpio-picker__hint gpio-picker__hint--grid">
        <Cpu class="gpio-picker__hint-icon" />
        Statische GPIO-Liste (kein Live-Status vom ESP)
      </p>
    </template>
  </div>
</template>

<style scoped>
.gpio-picker {
  width: 100%;
}

.gpio-picker--disabled {
  opacity: 0.5;
  pointer-events: none;
}

/* ════════════════════════════════════════════════════════════════
   LOADING STATE
   ════════════════════════════════════════════════════════════════ */

.gpio-picker__loading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 0.75rem;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.gpio-picker__spinner {
  width: 1rem;
  height: 1rem;
  border: 2px solid var(--glass-border);
  border-top-color: var(--color-iridescent-1);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

/* ════════════════════════════════════════════════════════════════
   DROPDOWN VARIANT
   ════════════════════════════════════════════════════════════════ */

.gpio-picker__dropdown {
  width: 100%;
}

.gpio-picker__select {
  width: 100%;
  padding: 0.625rem 0.75rem;
  font-size: 0.875rem;
  background-color: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  cursor: pointer;
  transition:
    border-color 0.2s,
    box-shadow 0.2s;
  appearance: none;
  background-image: url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%23707080' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e");
  background-position: right 0.5rem center;
  background-repeat: no-repeat;
  background-size: 1.5em 1.5em;
  padding-right: 2.5rem;
}

.gpio-picker__select:hover:not(:disabled) {
  border-color: var(--color-iridescent-1);
}

.gpio-picker__select:focus {
  outline: none;
  border-color: var(--color-iridescent-1);
  box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.15);
}

.gpio-picker__select:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.gpio-picker__select option {
  background-color: var(--color-bg-secondary);
  color: var(--color-text-primary);
}

.gpio-picker__select optgroup {
  font-weight: 600;
  color: var(--color-text-secondary);
}

.gpio-picker__hint {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  margin-top: 0.375rem;
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.gpio-picker__hint-icon {
  width: 0.875rem;
  height: 0.875rem;
  opacity: 0.7;
}

.gpio-picker__hint--grid {
  margin-top: 0.5rem;
  padding-top: 0.5rem;
  border-top: 1px solid var(--glass-border);
}

.gpio-picker__error {
  margin-top: 0.375rem;
  font-size: 0.75rem;
  color: var(--color-error);
}

/* ════════════════════════════════════════════════════════════════
   GRID VARIANT
   ════════════════════════════════════════════════════════════════ */

.gpio-picker__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(3.5rem, 1fr));
  gap: 0.5rem;
}

.gpio-pin {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 0.5rem;
  min-height: 3.5rem;
  background-color: var(--color-bg-secondary);
  border: 2px solid var(--glass-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.2s ease;
}

.gpio-pin:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}

.gpio-pin:focus {
  outline: none;
  box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.2);
}

/* Available state */
.gpio-pin--available {
  border-color: var(--color-success);
}

.gpio-pin--available:hover:not(:disabled) {
  background-color: rgba(52, 211, 153, 0.1);
  border-color: var(--color-success);
}

/* Recommended state */
.gpio-pin--recommended {
  border-color: var(--color-iridescent-2);
  background-color: rgba(129, 140, 248, 0.05);
}

.gpio-pin--recommended:hover:not(:disabled) {
  background-color: rgba(129, 140, 248, 0.15);
}

/* Selected state */
.gpio-pin--selected {
  border-color: var(--color-iridescent-1);
  background-color: rgba(96, 165, 250, 0.15);
  box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.2);
}

/* Disabled/Reserved state */
.gpio-pin--disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background-color: var(--color-bg-tertiary);
}

/* Owner-based colors */
.gpio-pin--sensor {
  border-color: var(--color-info);
}

.gpio-pin--actuator {
  border-color: var(--color-warning);
}

.gpio-pin--system {
  border-color: var(--color-text-muted);
}

.gpio-pin__number {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.gpio-pin__icon {
  width: 0.875rem;
  height: 0.875rem;
  margin-top: 0.25rem;
  opacity: 0.7;
}

.gpio-pin__icon--check {
  color: var(--color-success);
  opacity: 1;
}

.gpio-pin__recommended {
  position: absolute;
  top: -3px;
  right: -3px;
  width: 8px;
  height: 8px;
  background-color: var(--color-iridescent-2);
  border-radius: 50%;
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%,
  100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.3);
    opacity: 0.7;
  }
}

/* ════════════════════════════════════════════════════════════════
   LEGEND
   ════════════════════════════════════════════════════════════════ */

.gpio-picker__legend {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--glass-border);
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.legend-item--available .legend-dot {
  background-color: var(--color-success);
}

.legend-item--recommended .legend-dot {
  background-color: var(--color-iridescent-2);
}

.legend-item--sensor .legend-dot {
  background-color: var(--color-info);
}

.legend-item--actuator .legend-dot {
  background-color: var(--color-warning);
}

.legend-item--system .legend-dot {
  background-color: var(--color-text-muted);
}
</style>
