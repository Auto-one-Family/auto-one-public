<script setup lang="ts">
/**
 * ConnectionLines Component
 * 
 * SVG-based connection lines between ESP cards and satellite components.
 * Shows logical connections from Logic Rules.
 * 
 * Line Types:
 * - Green solid lines = Active logic connections (from Logic Rules)
 * - Dashed lines = Internal ESP connections (sensor → actuator on same ESP)
 * - Solid lines = Cross-ESP connections (sensor on ESP1 → actuator on ESP2)
 */

import { ref, onMounted, onUnmounted } from 'vue'

interface Connection {
  /** Source ESP ID */
  sourceEspId: string
  /** Source GPIO */
  sourceGpio: number
  /** Source type: 'sensor' | 'actuator' */
  sourceType: 'sensor' | 'actuator'
  /** Target ESP ID */
  targetEspId: string
  /** Target GPIO */
  targetGpio: number
  /** Target type: 'sensor' | 'actuator' */
  targetType: 'sensor' | 'actuator'
  /** Connection type: 'logic' | 'internal' | 'cross-esp' */
  connectionType: 'logic' | 'internal' | 'cross-esp'
  /** Rule ID (if logic connection) */
  ruleId?: string
  /** Rule name (if logic connection) */
  ruleName?: string
  /** Human-readable rule description (e.g., "Temp > 25°C → Lüfter AN") */
  ruleDescription?: string
  /** Whether connection is active */
  active?: boolean
}

interface Position {
  x: number
  y: number
}

interface Props {
  /** Connections to draw */
  connections: Connection[]
  /** Component positions: { espId: { x, y }, gpio: { x, y } } */
  positions: Record<string, Position>
  /** Whether to show tooltips */
  showTooltips?: boolean
  /** Currently hovered connection */
  hoveredConnection?: Connection | null
}

const props = withDefaults(defineProps<Props>(), {
  showTooltips: true,
  hoveredConnection: null,
})

const emit = defineEmits<{
  connectionHover: [connection: Connection | null]
  connectionClick: [connection: Connection]
}>()

// SVG element ref
const svgRef = ref<SVGSVGElement | null>(null)
const containerRef = ref<HTMLDivElement | null>(null)

// ViewBox dimensions (will be updated based on container size)
const viewBox = ref('0 0 1000 1000')

// Update viewBox when container size changes
function updateViewBox() {
  if (containerRef.value && svgRef.value) {
    const rect = containerRef.value.getBoundingClientRect()
    viewBox.value = `0 0 ${rect.width} ${rect.height}`
  }
}

// Get line path for a connection
function getLinePath(connection: Connection): string {
  const sourcePos = props.positions[`${connection.sourceEspId}_${connection.sourceGpio}`] || 
                     props.positions[connection.sourceEspId]
  const targetPos = props.positions[`${connection.targetEspId}_${connection.targetGpio}`] || 
                    props.positions[connection.targetEspId]
  
  if (!sourcePos || !targetPos) return ''
  
  // Use quadratic curve for smoother lines
  const midX = (sourcePos.x + targetPos.x) / 2
  const midY = (sourcePos.y + targetPos.y) / 2
  
  return `M ${sourcePos.x} ${sourcePos.y} Q ${midX} ${midY} ${targetPos.x} ${targetPos.y}`
}

// Get line style based on connection type
function getLineStyle(connection: Connection): {
  stroke: string
  strokeWidth: number
  strokeDasharray?: string
  opacity: number
} {
  const baseStyle = {
    strokeWidth: 2,
    opacity: connection.active !== false ? 1 : 0.5,
  }
  
  switch (connection.connectionType) {
    case 'logic':
      return {
        ...baseStyle,
        stroke: 'var(--color-success)',
        strokeWidth: 3,
      }
    case 'cross-esp':
      return {
        ...baseStyle,
        stroke: 'var(--color-iridescent-1)',
        strokeWidth: 2,
      }
    case 'internal':
      return {
        ...baseStyle,
        stroke: 'var(--color-text-muted)',
        strokeWidth: 1.5,
        strokeDasharray: '4 4',
      }
    default:
      return {
        ...baseStyle,
        stroke: 'var(--color-text-muted)',
      }
  }
}

// Handle connection hover
function handleConnectionHover(connection: Connection | null) {
  emit('connectionHover', connection)
}

// Handle connection click
function handleConnectionClick(connection: Connection) {
  emit('connectionClick', connection)
}

/**
 * Truncate text for display along line
 */
function truncateText(text: string | undefined, maxLength: number): string {
  if (!text) return ''
  if (text.length <= maxLength) return text
  return text.substring(0, maxLength - 3) + '...'
}

/**
 * Get display text for connection (name or description)
 */
function getConnectionText(connection: Connection): string {
  if (connection.ruleDescription) {
    return truncateText(connection.ruleDescription, 25)
  }
  if (connection.ruleName) {
    return truncateText(connection.ruleName, 20)
  }
  return ''
}

// Lifecycle
onMounted(() => {
  updateViewBox()
  window.addEventListener('resize', updateViewBox)
})

onUnmounted(() => {
  window.removeEventListener('resize', updateViewBox)
})
</script>

<template>
  <div ref="containerRef" class="connection-lines-container">
    <svg
      ref="svgRef"
      :viewBox="viewBox"
      class="connection-lines"
      xmlns="http://www.w3.org/2000/svg"
    >
      <!-- Connection lines with text -->
      <g v-for="(connection, index) in connections" :key="index">
        <!-- Define path for text to follow -->
        <defs>
          <path
            :id="`connection-path-${index}`"
            :d="getLinePath(connection)"
            fill="none"
          />
        </defs>

        <!-- Visible line -->
        <path
          :d="getLinePath(connection)"
          :style="getLineStyle(connection)"
          fill="none"
          :class="[
            'connection-line',
            { 'connection-line--hovered': hoveredConnection === connection },
            { 'connection-line--active': connection.active }
          ]"
          @mouseenter="handleConnectionHover(connection)"
          @mouseleave="handleConnectionHover(null)"
          @click="handleConnectionClick(connection)"
        />

        <!-- Text along the line (only for logic/cross-esp connections with text) -->
        <text
          v-if="connection.connectionType !== 'internal' && getConnectionText(connection)"
          :class="[
            'connection-text',
            { 'connection-text--hovered': hoveredConnection === connection },
            { 'connection-text--active': connection.active }
          ]"
          dy="-5"
        >
          <textPath
            :href="`#connection-path-${index}`"
            startOffset="50%"
            text-anchor="middle"
          >
            {{ getConnectionText(connection) }}
          </textPath>
        </text>

        <!-- Arrow marker (for logic connections) -->
        <circle
          v-if="connection.connectionType === 'logic' || connection.connectionType === 'cross-esp'"
          :cx="positions[`${connection.targetEspId}_${connection.targetGpio}`]?.x || positions[connection.targetEspId]?.x"
          :cy="positions[`${connection.targetEspId}_${connection.targetGpio}`]?.y || positions[connection.targetEspId]?.y"
          r="4"
          :fill="getLineStyle(connection).stroke"
          class="connection-arrow"
        />
      </g>
      
      <!-- Tooltip (if hovered) -->
      <g v-if="showTooltips && hoveredConnection">
        <rect
          :x="(positions[`${hoveredConnection.targetEspId}_${hoveredConnection.targetGpio}`]?.x || positions[hoveredConnection.targetEspId]?.x) + 10"
          :y="(positions[`${hoveredConnection.targetEspId}_${hoveredConnection.targetGpio}`]?.y || positions[hoveredConnection.targetEspId]?.y) - 30"
          width="200"
          height="60"
          rx="4"
          fill="var(--color-bg-secondary)"
          stroke="var(--glass-border)"
          class="connection-tooltip-bg"
        />
        <text
          :x="(positions[`${hoveredConnection.targetEspId}_${hoveredConnection.targetGpio}`]?.x || positions[hoveredConnection.targetEspId]?.x) + 15"
          :y="(positions[`${hoveredConnection.targetEspId}_${hoveredConnection.targetGpio}`]?.y || positions[hoveredConnection.targetEspId]?.y) - 15"
          fill="var(--color-text-primary)"
          font-size="12"
          font-weight="600"
        >
          {{ hoveredConnection.ruleName || 'Logic Rule' }}
        </text>
        <text
          :x="(positions[`${hoveredConnection.targetEspId}_${hoveredConnection.targetGpio}`]?.x || positions[hoveredConnection.targetEspId]?.x) + 15"
          :y="(positions[`${hoveredConnection.targetEspId}_${hoveredConnection.targetGpio}`]?.y || positions[hoveredConnection.targetEspId]?.y)"
          fill="var(--color-text-muted)"
          font-size="10"
        >
          {{ hoveredConnection.sourceEspId }}:GPIO{{ hoveredConnection.sourceGpio }} → 
          {{ hoveredConnection.targetEspId }}:GPIO{{ hoveredConnection.targetGpio }}
        </text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.connection-lines-container {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: var(--z-dropdown);
}

.connection-lines {
  width: 100%;
  height: 100%;
  pointer-events: stroke;
}

.connection-line {
  cursor: pointer;
  transition: all 0.2s;
}

.connection-line:hover {
  stroke-width: 4 !important;
  opacity: 1 !important;
}

.connection-line--hovered {
  stroke-width: 4 !important;
  opacity: 1 !important;
  filter: drop-shadow(0 0 4px currentColor);
}

.connection-arrow {
  pointer-events: none;
}

.connection-text {
  font-size: var(--text-xxs);
  fill: var(--color-text-secondary);
  pointer-events: none;
  opacity: 0.7;
  font-weight: 500;
  text-shadow: 0 0 3px var(--color-bg-primary), 0 0 3px var(--color-bg-primary);
}

.connection-text--hovered {
  opacity: 1;
  font-weight: 600;
  fill: var(--color-text-primary);
}

/* Dimmen anderer Linien bei Hover */
.connection-lines:has(.connection-line:hover) .connection-line:not(:hover) {
  opacity: 0.3;
}

.connection-lines:has(.connection-line:hover) .connection-text:not(.connection-text--hovered) {
  opacity: 0.3;
}

.connection-tooltip-bg {
  pointer-events: none;
  filter: drop-shadow(0 2px 8px rgba(0, 0, 0, 0.2));
}

/* Active connection styles (when rule is executing) */
.connection-line--active {
  stroke-width: 4 !important;
  opacity: 1 !important;
  filter: drop-shadow(0 0 8px currentColor);
  animation: pulse-active 0.5s ease-out;
}

@keyframes pulse-active {
  0% {
    stroke-width: 2;
    filter: drop-shadow(0 0 0 currentColor);
  }
  50% {
    stroke-width: 6;
    filter: drop-shadow(0 0 16px currentColor);
  }
  100% {
    stroke-width: 4;
    filter: drop-shadow(0 0 8px currentColor);
  }
}

.connection-text--active {
  opacity: 1;
  font-weight: 600;
  fill: var(--color-success);
  animation: text-glow 0.5s ease-out;
}

@keyframes text-glow {
  0%, 100% {
    filter: drop-shadow(0 0 0 var(--color-success));
  }
  50% {
    filter: drop-shadow(0 0 8px var(--color-success));
  }
}
</style>

















