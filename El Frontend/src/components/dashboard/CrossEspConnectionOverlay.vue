<script setup lang="ts">
/**
 * CrossEspConnectionOverlay Component
 *
 * Dashboard-level SVG overlay for visualizing Cross-ESP Logic Rule connections.
 * Draws lines between sensors and actuators on DIFFERENT ESPs.
 *
 * Uses data attributes to find satellite positions:
 * - data-esp-id: ESP device ID
 * - data-gpio: GPIO pin number
 * - data-satellite-type: 'sensor' | 'actuator'
 *
 * @see stores/logic.ts - crossEspConnections computed
 * @see types/logic.ts - LogicConnection interface
 */

import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useLogicStore } from '@/shared/stores/logic.store'
import type { LogicConnection } from '@/types/logic'

interface Props {
  /** Container element selector (default: parent element) */
  containerSelector?: string
  /** Whether to show the overlay */
  show?: boolean
  /** Whether to show rule names along lines */
  showLabels?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  containerSelector: '',
  show: true,
  showLabels: true,
})

const logicStore = useLogicStore()

// Refs
const overlayRef = ref<HTMLDivElement | null>(null)
const svgRef = ref<SVGSVGElement | null>(null)

// Position map: key = `${espId}_${gpio}`, value = { x, y }
const positions = ref<Record<string, { x: number; y: number }>>({})

// Hovered connection for tooltip
const hoveredConnection = ref<LogicConnection | null>(null)

// SVG dimensions
const svgWidth = ref(0)
const svgHeight = ref(0)

// Cross-ESP connections from store
const connections = computed(() => logicStore.crossEspConnections)

/**
 * Find all satellite elements and calculate their positions
 */
function updatePositions() {
  if (!overlayRef.value) return

  const container = props.containerSelector
    ? document.querySelector(props.containerSelector)
    : overlayRef.value.parentElement

  if (!container) return

  const overlayRect = overlayRef.value.getBoundingClientRect()

  // Update SVG dimensions
  svgWidth.value = overlayRect.width
  svgHeight.value = overlayRect.height

  // Find all satellites with data attributes
  const satellites = container.querySelectorAll('[data-esp-id][data-gpio][data-satellite-type]')

  const newPositions: Record<string, { x: number; y: number }> = {}

  satellites.forEach((el) => {
    const espId = el.getAttribute('data-esp-id')
    const gpio = el.getAttribute('data-gpio')

    if (!espId || !gpio) return

    const rect = el.getBoundingClientRect()

    // Calculate center position relative to overlay
    const x = rect.left - overlayRect.left + rect.width / 2
    const y = rect.top - overlayRect.top + rect.height / 2

    // Key format: `${espId}_${gpio}`
    newPositions[`${espId}_${gpio}`] = { x, y }
  })

  positions.value = newPositions
}

/**
 * Get SVG path for a connection (quadratic bezier curve)
 */
function getLinePath(conn: LogicConnection): string {
  const sourceKey = `${conn.sourceEspId}_${conn.sourceGpio}`
  const targetKey = `${conn.targetEspId}_${conn.targetGpio}`

  const source = positions.value[sourceKey]
  const target = positions.value[targetKey]

  if (!source || !target) return ''

  // Calculate control point for curved line
  const midX = (source.x + target.x) / 2
  const midY = (source.y + target.y) / 2

  // Offset control point perpendicular to the line for nice curve
  const dx = target.x - source.x
  const dy = target.y - source.y
  const distance = Math.sqrt(dx * dx + dy * dy)

  // Curve amount based on distance (more curve for longer lines)
  const curveOffset = Math.min(distance * 0.2, 50)

  // Perpendicular offset
  const perpX = -dy / distance * curveOffset
  const perpY = dx / distance * curveOffset

  const controlX = midX + perpX
  const controlY = midY + perpY

  return `M ${source.x} ${source.y} Q ${controlX} ${controlY} ${target.x} ${target.y}`
}

/**
 * Get line style based on connection state
 */
function getLineStyle(conn: LogicConnection) {
  return {
    stroke: conn.enabled ? 'var(--color-iridescent-1)' : 'var(--color-text-muted)',
    strokeWidth: conn.enabled ? 2.5 : 1.5,
    opacity: conn.enabled ? 0.8 : 0.4,
    strokeDasharray: conn.enabled ? 'none' : '6 4',
  }
}

/**
 * Check if connection has valid positions
 */
function hasValidPositions(conn: LogicConnection): boolean {
  const sourceKey = `${conn.sourceEspId}_${conn.sourceGpio}`
  const targetKey = `${conn.targetEspId}_${conn.targetGpio}`
  return !!positions.value[sourceKey] && !!positions.value[targetKey]
}

/**
 * Get arrow marker position (at target end)
 */
function getArrowPosition(conn: LogicConnection) {
  const targetKey = `${conn.targetEspId}_${conn.targetGpio}`
  return positions.value[targetKey] || { x: 0, y: 0 }
}

/**
 * Truncate text for display
 */
function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return text.substring(0, maxLength - 3) + '...'
}

// Observers for position tracking
let resizeObserver: ResizeObserver | null = null
let mutationObserver: MutationObserver | null = null

/**
 * Setup observers for position tracking
 */
function setupObservers() {
  if (!overlayRef.value) return

  const container = props.containerSelector
    ? document.querySelector(props.containerSelector)
    : overlayRef.value.parentElement

  if (!container) return

  // ResizeObserver for container size changes
  resizeObserver = new ResizeObserver(() => {
    updatePositions()
  })
  resizeObserver.observe(container)

  // MutationObserver for DOM changes (new satellites added/removed)
  mutationObserver = new MutationObserver(() => {
    nextTick(() => updatePositions())
  })
  mutationObserver.observe(container, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['data-esp-id', 'data-gpio', 'style', 'class'],
  })
}

/**
 * Cleanup observers
 */
function cleanupObservers() {
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  if (mutationObserver) {
    mutationObserver.disconnect()
    mutationObserver = null
  }
}

// Lifecycle
onMounted(async () => {
  // Fetch rules if not loaded
  if (logicStore.ruleCount === 0 && !logicStore.isLoading) {
    await logicStore.fetchRules()
  }

  // Wait for DOM to be ready
  await nextTick()

  // Initial position calculation
  updatePositions()

  // Setup observers
  setupObservers()

  // Also listen to window resize
  window.addEventListener('resize', updatePositions)
  window.addEventListener('scroll', updatePositions, true)
})

onUnmounted(() => {
  cleanupObservers()
  window.removeEventListener('resize', updatePositions)
  window.removeEventListener('scroll', updatePositions, true)
})

// Watch for connection changes
watch(
  () => logicStore.crossEspConnections,
  () => {
    nextTick(() => updatePositions())
  },
  { deep: true }
)
</script>

<template>
  <div
    v-if="show && connections.length > 0"
    ref="overlayRef"
    class="cross-esp-overlay"
  >
    <svg
      ref="svgRef"
      :viewBox="`0 0 ${svgWidth} ${svgHeight}`"
      class="cross-esp-overlay__svg"
      xmlns="http://www.w3.org/2000/svg"
    >
      <!-- Gradient definition for lines -->
      <defs>
        <linearGradient id="cross-esp-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="var(--color-iridescent-1)" />
          <stop offset="100%" stop-color="var(--color-iridescent-2)" />
        </linearGradient>

        <!-- Arrow marker -->
        <marker
          id="arrow-marker"
          viewBox="0 0 10 10"
          refX="5"
          refY="5"
          markerWidth="4"
          markerHeight="4"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--color-iridescent-1)" />
        </marker>
      </defs>

      <!-- Connection lines -->
      <g v-for="(conn, index) in connections" :key="conn.ruleId + '_' + index">
        <template v-if="hasValidPositions(conn)">
          <!-- Path definition for text -->
          <defs>
            <path
              :id="`cross-path-${index}`"
              :d="getLinePath(conn)"
              fill="none"
            />
          </defs>

          <!-- Connection line -->
          <path
            :d="getLinePath(conn)"
            :style="getLineStyle(conn)"
            fill="none"
            marker-end="url(#arrow-marker)"
            :class="[
              'cross-esp-overlay__line',
              { 'cross-esp-overlay__line--hovered': hoveredConnection?.ruleId === conn.ruleId },
              { 'cross-esp-overlay__line--active': logicStore.isConnectionActive(conn) }
            ]"
            @mouseenter="hoveredConnection = conn"
            @mouseleave="hoveredConnection = null"
          />

          <!-- Rule name along line -->
          <text
            v-if="showLabels && conn.ruleName"
            :class="[
              'cross-esp-overlay__label',
              { 'cross-esp-overlay__label--active': logicStore.isConnectionActive(conn) }
            ]"
            dy="-8"
          >
            <textPath
              :href="`#cross-path-${index}`"
              startOffset="50%"
              text-anchor="middle"
            >
              {{ truncateText(conn.ruleName, 20) }}
            </textPath>
          </text>

          <!-- Target indicator dot -->
          <circle
            :cx="getArrowPosition(conn).x"
            :cy="getArrowPosition(conn).y"
            r="6"
            :fill="conn.enabled ? 'var(--color-iridescent-1)' : 'var(--color-text-muted)'"
            :opacity="conn.enabled ? 0.6 : 0.3"
            class="cross-esp-overlay__target-dot"
          />
        </template>
      </g>

      <!-- Tooltip for hovered connection -->
      <g v-if="hoveredConnection && hasValidPositions(hoveredConnection)">
        <rect
          :x="getArrowPosition(hoveredConnection).x + 15"
          :y="getArrowPosition(hoveredConnection).y - 50"
          width="200"
          height="70"
          rx="6"
          fill="var(--color-bg-secondary)"
          stroke="var(--color-iridescent-1)"
          stroke-width="1"
          class="cross-esp-overlay__tooltip-bg"
        />
        <text
          :x="getArrowPosition(hoveredConnection).x + 25"
          :y="getArrowPosition(hoveredConnection).y - 30"
          fill="var(--color-text-primary)"
          font-size="12"
          font-weight="600"
        >
          {{ hoveredConnection.ruleName }}
        </text>
        <text
          :x="getArrowPosition(hoveredConnection).x + 25"
          :y="getArrowPosition(hoveredConnection).y - 12"
          fill="var(--color-text-secondary)"
          font-size="10"
        >
          {{ hoveredConnection.ruleDescription }}
        </text>
        <text
          :x="getArrowPosition(hoveredConnection).x + 25"
          :y="getArrowPosition(hoveredConnection).y + 6"
          fill="var(--color-text-muted)"
          font-size="9"
          font-family="'JetBrains Mono', monospace"
        >
          {{ hoveredConnection.sourceEspId }}:{{ hoveredConnection.sourceGpio }}
          → {{ hoveredConnection.targetEspId }}:{{ hoveredConnection.targetGpio }}
        </text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.cross-esp-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: var(--z-modal);
  overflow: visible;
}

.cross-esp-overlay__svg {
  width: 100%;
  height: 100%;
  overflow: visible;
}

.cross-esp-overlay__line {
  pointer-events: stroke;
  cursor: pointer;
  transition: all 0.2s ease;
}

.cross-esp-overlay__line:hover {
  stroke-width: 4 !important;
  opacity: 1 !important;
  filter: drop-shadow(0 0 8px var(--color-iridescent-1));
}

.cross-esp-overlay__line--hovered {
  stroke-width: 4 !important;
  opacity: 1 !important;
  filter: drop-shadow(0 0 8px var(--color-iridescent-1));
}

.cross-esp-overlay__label {
  font-size: var(--text-xxs);
  fill: var(--color-text-secondary);
  pointer-events: none;
  font-weight: 500;
  text-shadow:
    0 0 4px var(--color-bg-primary),
    0 0 4px var(--color-bg-primary),
    0 0 4px var(--color-bg-primary);
}

.cross-esp-overlay__target-dot {
  pointer-events: none;
  transition: all 0.2s ease;
}

.cross-esp-overlay__tooltip-bg {
  pointer-events: none;
  filter: drop-shadow(0 4px 12px rgba(0, 0, 0, 0.3));
}

/* Animation for active connections */
@keyframes pulse-line {
  0%, 100% {
    opacity: 0.8;
  }
  50% {
    opacity: 1;
  }
}

.cross-esp-overlay__line[style*="stroke: var(--color-iridescent-1)"] {
  animation: pulse-line 3s ease-in-out infinite;
}

/* Live execution feedback styles */
.cross-esp-overlay__line--active {
  stroke-width: 5 !important;
  opacity: 1 !important;
  filter: drop-shadow(0 0 12px var(--color-success));
  animation: pulse-active-cross 0.6s ease-out;
}

@keyframes pulse-active-cross {
  0% {
    stroke-width: 2;
    filter: drop-shadow(0 0 0 var(--color-success));
  }
  50% {
    stroke-width: 8;
    filter: drop-shadow(0 0 20px var(--color-success));
  }
  100% {
    stroke-width: 5;
    filter: drop-shadow(0 0 12px var(--color-success));
  }
}

.cross-esp-overlay__label--active {
  fill: var(--color-success) !important;
  font-weight: 700 !important;
  animation: glow-text 0.6s ease-out;
}

@keyframes glow-text {
  0%, 100% {
    filter: drop-shadow(0 0 0 var(--color-success));
  }
  50% {
    filter: drop-shadow(0 0 10px var(--color-success));
  }
}
</style>
