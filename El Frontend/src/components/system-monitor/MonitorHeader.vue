<script setup lang="ts">
/**
 * @deprecated This component has been replaced by MonitorTabs.vue (2026-01-26)
 *
 * MonitorHeader - System Monitor Header Component (DEPRECATED)
 *
 * The header functionality has been consolidated into MonitorTabs.vue to:
 * - Save ~50px vertical space
 * - Provide a cleaner, more unified UI
 * - Combine Live toggle, tabs, and actions in one bar
 *
 * This file is kept for reference but should not be used in new code.
 *
 * @see MonitorTabs.vue for the replacement component
 */

import { ref, computed } from 'vue'
import {
  Play,
  Pause,
  Download,
  RefreshCw,
  BarChart3,
  Database,
  Activity,
  Cpu,
  Info,
} from 'lucide-vue-next'

// ============================================================================
// Props & Emits
// ============================================================================

interface Props {
  isPaused: boolean
  isLoading: boolean
  isConnected: boolean
  connectionStatus: 'connected' | 'connecting' | 'disconnected' | 'error'
  eventCount: number
  totalEspCount: number          // Total registered ESPs from ESP Store
  totalDbEvents: number | null   // Total events in database (from statistics)
  onlineEspCount: number         // ESPs currently online from ESP Store
  // Admin Features
  isAdmin?: boolean
  showStats?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isAdmin: false,
  showStats: false,
  totalDbEvents: null,
  totalEspCount: 0,
  onlineEspCount: 0,
})

// Tooltip state
const showEventsTooltip = ref(false)
const showEspTooltip = ref(false)

const emit = defineEmits<{
  'toggle-pause': []
  'toggle-stats': []
  'open-cleanup-panel': []
  'refresh': []
  'export': []
}>()

// ============================================================================
// Computed
// ============================================================================

// Computed tooltips
const eventsTooltip = computed(() => {
  const loaded = props.eventCount
  const total = props.totalDbEvents
  if (total !== null) {
    return `${loaded} Events aktuell geladen.\nGesamt in DB: ${total}.\nFilter: Letzte 6h + Live-Stream`
  }
  return `${loaded} Events im View geladen.\nÄltere Events via Statistiken einsehbar.`
})

const espTooltip = computed(() => {
  const online = props.onlineEspCount
  const total = props.totalEspCount
  if (total === 0) return 'Keine ESPs registriert'
  return `${online} von ${total} ESPs online`
})
</script>

<template>
  <header class="monitor-header">
    <div class="monitor-header__left">
      <!-- Live Status with Play/Pause Button -->
      <button
        class="monitor-header__live-status"
        :class="{ 'live-status--paused': isPaused }"
        @click="emit('toggle-pause')"
        :title="isPaused ? 'Fortsetzen' : 'Pausieren'"
      >
        <span class="status-dot" :class="{ 'animate-pulse': !isPaused }"></span>
        <component :is="isPaused ? Play : Pause" class="w-4 h-4" />
        <span>{{ isPaused ? 'Pausiert' : 'Live' }}</span>
      </button>
    </div>
    <div class="monitor-header__stats">
      <!-- Events Count with Tooltip -->
      <div
        class="stat stat--with-tooltip"
        @mouseenter="showEventsTooltip = true"
        @mouseleave="showEventsTooltip = false"
      >
        <Activity class="stat-icon" />
        <span class="stat-value">{{ eventCount }}</span>
        <span class="stat-label">geladen</span>
        <Info class="stat-info-icon" />

        <!-- Tooltip -->
        <Transition name="tooltip-fade">
          <div v-if="showEventsTooltip" class="stat-tooltip">
            {{ eventsTooltip }}
          </div>
        </Transition>
      </div>

      <!-- ESP Count with Tooltip - Compact "X/Y online" Format -->
      <div
        v-if="totalEspCount > 0"
        class="stat stat--with-tooltip stat--esp"
        @mouseenter="showEspTooltip = true"
        @mouseleave="showEspTooltip = false"
      >
        <Cpu class="stat-icon" />
        <span class="stat-value">
          <span class="esp-online">{{ onlineEspCount }}</span><span class="esp-separator">/</span><span class="esp-total">{{ totalEspCount }}</span>
        </span>
        <span class="stat-label">online</span>
        <Info class="stat-info-icon" />

        <!-- Tooltip -->
        <Transition name="tooltip-fade">
          <div v-if="showEspTooltip" class="stat-tooltip">
            {{ espTooltip }}
          </div>
        </Transition>
      </div>
    </div>
    <div class="monitor-header__actions">
      <!-- Stats Toggle -->
      <button
        class="monitor-btn"
        :class="{ 'monitor-btn--active': showStats }"
        @click="emit('toggle-stats')"
        title="Statistiken anzeigen"
      >
        <BarChart3 class="w-4 h-4" />
      </button>
      <button
        class="monitor-btn"
        @click="emit('refresh')"
        :disabled="isLoading"
        title="Aktualisieren"
      >
        <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': isLoading }" />
      </button>
      <button class="monitor-btn" @click="emit('export')" title="Exportieren">
        <Download class="w-4 h-4" />
      </button>
      <!-- Admin Actions: Consolidated Cleanup Panel Button -->
      <button
        v-if="isAdmin"
        class="monitor-btn monitor-btn--iridescent"
        @click="emit('open-cleanup-panel')"
        title="Bereinigung & Aufbewahrung"
      >
        <Database class="w-4 h-4" />
      </button>
    </div>
  </header>
</template>

<style scoped>
/* === HEADER CONTAINER === */
.monitor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-md) var(--space-lg);
  border-bottom: 1px solid var(--glass-border);
  background: var(--glass-bg);
  backdrop-filter: blur(12px);
  gap: var(--space-lg);
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
}

.monitor-header__left {
  display: flex;
  align-items: center;
  gap: var(--space-lg);
}

/* === LIVE STATUS BUTTON - IRIDESCENT === */
.monitor-header__live-status {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-xs) var(--space-md);
  border-radius: var(--radius-full);
  font-size: 0.75rem;
  font-weight: 600;
  transition: all var(--transition-base);
  position: relative;
  overflow: hidden;
  cursor: pointer;
  background: linear-gradient(135deg,
    rgba(52, 211, 153, 0.2) 0%,
    rgba(52, 211, 153, 0.1) 100%
  );
  border: 1px solid rgba(52, 211, 153, 0.3);
  box-shadow: 0 0 15px rgba(52, 211, 153, 0.2);
  color: var(--color-success);
}

.monitor-header__live-status:hover {
  background: linear-gradient(135deg,
    rgba(52, 211, 153, 0.3) 0%,
    rgba(52, 211, 153, 0.15) 100%
  );
  border-color: rgba(52, 211, 153, 0.5);
  box-shadow: 0 0 20px rgba(52, 211, 153, 0.3);
  transform: translateY(-1px);
}

.monitor-header__live-status:active {
  transform: translateY(0);
}

.live-status--paused {
  color: var(--color-warning);
  background: linear-gradient(135deg,
    rgba(251, 191, 36, 0.2) 0%,
    rgba(251, 191, 36, 0.1) 100%
  );
  border: 1px solid rgba(251, 191, 36, 0.3);
  box-shadow: 0 0 15px rgba(251, 191, 36, 0.2);
}

.live-status--paused:hover {
  background: linear-gradient(135deg,
    rgba(251, 191, 36, 0.3) 0%,
    rgba(251, 191, 36, 0.15) 100%
  );
  border-color: rgba(251, 191, 36, 0.5);
  box-shadow: 0 0 20px rgba(251, 191, 36, 0.3);
}

.live-status--paused .status-dot {
  animation: none !important;
}

/* === STATUS BADGE - IRIDESCENT (Deprecated, kept for compatibility) === */
.monitor-header__status {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-xs) var(--space-md);
  border-radius: var(--radius-full);
  font-size: 0.75rem;
  font-weight: 600;
  transition: all var(--transition-base);
  position: relative;
  overflow: hidden;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: currentColor;
  flex-shrink: 0;
}

.monitor-header__live-status .status-dot {
  box-shadow: 0 0 8px currentColor;
}

.status--connected {
  color: var(--color-success);
  background: linear-gradient(135deg,
    rgba(52, 211, 153, 0.2) 0%,
    rgba(52, 211, 153, 0.1) 100%
  );
  border: 1px solid rgba(52, 211, 153, 0.3);
  box-shadow: 0 0 15px rgba(52, 211, 153, 0.2);
}

.status--connected .status-dot {
  box-shadow: 0 0 8px currentColor;
}

.status--connecting {
  color: var(--color-warning);
  background: linear-gradient(135deg,
    rgba(251, 191, 36, 0.2) 0%,
    rgba(251, 191, 36, 0.1) 100%
  );
  border: 1px solid rgba(251, 191, 36, 0.3);
}

.status--disconnected {
  color: var(--color-error);
  background: linear-gradient(135deg,
    rgba(248, 113, 113, 0.2) 0%,
    rgba(248, 113, 113, 0.1) 100%
  );
  border: 1px solid rgba(248, 113, 113, 0.3);
}

.status--paused {
  color: var(--color-text-muted);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
}

/* === STATS === */
.monitor-header__stats {
  display: flex;
  gap: var(--space-lg);
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.stat {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  font-variant-numeric: tabular-nums;
}

.stat--with-tooltip {
  position: relative;
  cursor: help;
  padding: var(--space-xs) var(--space-sm);
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid transparent;
  transition: all var(--transition-base);
}

.stat--with-tooltip:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: var(--glass-border);
}

.stat-icon {
  width: 0.875rem;
  height: 0.875rem;
  color: var(--color-iridescent-1);
  flex-shrink: 0;
}

.stat-value {
  font-weight: 700;
  color: var(--color-text-primary);
}

.stat-label {
  font-weight: 500;
  color: var(--color-text-muted);
}

/* ESP Count - Compact Format "X/Y online" */
.stat--esp .stat-value {
  display: flex;
  align-items: baseline;
  gap: 0;
}

.esp-online {
  color: var(--color-success);
  font-weight: 700;
}

.esp-separator {
  color: var(--color-text-muted);
  font-weight: 400;
  margin: 0 1px;
}

.esp-total {
  color: var(--color-text-secondary);
  font-weight: 600;
}

.stat-info-icon {
  width: 0.75rem;
  height: 0.75rem;
  opacity: 0.4;
  transition: opacity var(--transition-base);
  margin-left: var(--space-xs);
}

.stat--with-tooltip:hover .stat-info-icon {
  opacity: 0.8;
}

/* Tooltip */
.stat-tooltip {
  position: absolute;
  top: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  z-index: var(--z-sticky);
  padding: var(--space-sm) var(--space-md);
  background: rgba(0, 0, 0, 0.95);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  font-size: 0.75rem;
  line-height: 1.5;
  white-space: pre-line;
  min-width: 200px;
  max-width: 280px;
  text-align: center;
  box-shadow:
    0 4px 16px rgba(0, 0, 0, 0.4),
    0 0 1px rgba(255, 255, 255, 0.1);
  pointer-events: none;
}

.stat-tooltip::before {
  content: '';
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 6px solid transparent;
  border-bottom-color: rgba(0, 0, 0, 0.95);
}

/* Tooltip Transition */
.tooltip-fade-enter-active,
.tooltip-fade-leave-active {
  transition: opacity 0.15s, transform 0.15s;
}

.tooltip-fade-enter-from,
.tooltip-fade-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(-4px);
}

/* === ACTIONS === */
.monitor-header__actions {
  display: flex;
  gap: var(--space-sm);
}

.monitor-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: var(--radius-md);
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  border: 1px solid var(--glass-border);
  cursor: pointer;
  transition: all var(--transition-base);
  position: relative;
  overflow: hidden;
}

/* Iridescent Hover Shine */
.monitor-btn::before {
  content: '';
  position: absolute;
  inset: 0;
  background: var(--gradient-iridescent);
  opacity: 0;
  transition: opacity var(--transition-base);
}

.monitor-btn:hover::before {
  opacity: 0.15;
}

.monitor-btn:hover {
  background: var(--color-bg-quaternary);
  color: var(--color-text-primary);
  border-color: var(--glass-border-hover);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}

.monitor-btn:active {
  transform: translateY(0);
}

/* Active State - Iridescent Gradient */
.monitor-btn--active {
  background: var(--gradient-iridescent);
  color: white;
  border-color: var(--color-iridescent-1);
  box-shadow: var(--glass-shadow-glow);
}

.monitor-btn--active::before {
  display: none;
}

/* Danger Button */
.monitor-btn--danger {
  border-color: rgba(248, 113, 113, 0.3);
}

.monitor-btn--danger:hover {
  background: linear-gradient(135deg,
    rgba(248, 113, 113, 0.3) 0%,
    rgba(248, 113, 113, 0.2) 100%
  );
  color: var(--color-error);
  border-color: var(--color-error);
  box-shadow: 0 0 15px rgba(248, 113, 113, 0.3);
}

.monitor-btn--danger:hover::before {
  display: none;
}

/* Warning Button */
.monitor-btn--warning {
  border-color: rgba(251, 191, 36, 0.3);
}

.monitor-btn--warning:hover {
  background: linear-gradient(135deg,
    rgba(251, 191, 36, 0.3) 0%,
    rgba(251, 191, 36, 0.2) 100%
  );
  color: var(--color-warning);
  border-color: var(--color-warning);
  box-shadow: 0 0 15px rgba(251, 191, 36, 0.3);
}

.monitor-btn--warning:hover::before {
  display: none;
}

/* Iridescent Button - Consolidated Cleanup/Settings */
.monitor-btn--iridescent {
  background: var(--gradient-iridescent);
  color: white;
  border-color: var(--color-iridescent-1);
  box-shadow: 0 0 10px rgba(96, 165, 250, 0.2);
}

.monitor-btn--iridescent::before {
  display: none;
}

.monitor-btn--iridescent:hover {
  transform: translateY(-2px);
  box-shadow: 0 0 20px rgba(96, 165, 250, 0.4);
}

.monitor-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

.monitor-btn:disabled::before {
  display: none;
}

/* === MOBILE RESPONSIVE === */
@media (max-width: 768px) {
  .monitor-header {
    flex-wrap: wrap;
    padding: var(--space-sm) var(--space-md);
  }

  .monitor-header__left {
    flex: 1 1 100%;
    justify-content: space-between;
  }

  .monitor-header__stats {
    flex: 1;
    justify-content: flex-start;
    font-size: 0.75rem;
    gap: var(--space-sm);
  }

  .stat--with-tooltip {
    padding: var(--space-xs);
  }

  .stat-info-icon {
    display: none;
  }

  .stat-tooltip {
    min-width: 180px;
    max-width: 240px;
    font-size: 0.6875rem;
  }

  .monitor-header__actions {
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: var(--space-xs);
  }

  /* Touch-friendly buttons (44x44px minimum) */
  .monitor-btn {
    width: 44px;
    height: 44px;
    border-radius: var(--radius-lg);
  }
}

@media (max-width: 480px) {
  .monitor-header {
    padding: var(--space-sm);
  }

  .monitor-header__status {
    padding: var(--space-xs) var(--space-sm);
    font-size: 0.6875rem;
  }

  /* Slightly smaller on very small screens but still touch-friendly */
  .monitor-btn {
    width: 40px;
    height: 40px;
  }
}

/* === ANIMATIONS === */
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.animate-pulse {
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

/* Icon sizes */
.w-4 { width: 1rem; }
.h-4 { height: 1rem; }
</style>
