<script setup lang="ts">
/**
 * MonitorTabs - System Monitor Tab Bar (Consolidated Header + Tabs)
 *
 * Combines:
 * - Live toggle button (left)
 * - Tab navigation with badges (center)
 * - Action buttons: Export, Cleanup (right)
 *
 * Mobile-responsive with horizontal scroll on smaller screens.
 *
 * @emits update:activeTab - When a tab is selected
 * @emits toggle-pause - When live toggle is clicked
 * @emits export - When export button is clicked
 * @emits open-cleanup-panel - When cleanup button is clicked (admin only)
 */

import { Activity, FileText, Database, MessageSquare, HeartPulse, Stethoscope, ClipboardList, Play, Pause, Download, Network } from 'lucide-vue-next'

// ============================================================================
import type { TabId } from './types'
export type { TabId }

interface Tab {
  id: TabId
  label: string
  icon: typeof Activity
}

interface EventCounts {
  events: number
  logs: number
  mqtt: number
}

// ============================================================================
// Props & Emits
// ============================================================================

interface Props {
  activeTab: TabId
  eventCounts: EventCounts
  isPaused: boolean
  isAdmin?: boolean
}

withDefaults(defineProps<Props>(), {
  isAdmin: false
})

const emit = defineEmits<{
  'update:activeTab': [tab: TabId]
  'toggle-pause': []
  'export': []
  'open-cleanup-panel': []
}>()

// ============================================================================
// Constants
// ============================================================================

const tabs: Tab[] = [
  { id: 'events', label: 'Ereignisse (Stream)', icon: Activity },
  { id: 'logs', label: 'Server Logs', icon: FileText },
  { id: 'database', label: 'Datenbank', icon: Database },
  { id: 'mqtt', label: 'MQTT Traffic', icon: MessageSquare },
  { id: 'health', label: 'Health', icon: HeartPulse },
  { id: 'diagnostics', label: 'Diagnose', icon: Stethoscope },
  { id: 'reports', label: 'Reports', icon: ClipboardList },
  { id: 'hierarchy', label: 'Hierarchie', icon: Network },
]

// ============================================================================
// Methods
// ============================================================================

function handleTabClick(tabId: TabId) {
  emit('update:activeTab', tabId)
}
</script>

<template>
  <nav class="monitor-tab-bar">
    <!-- Live Toggle (links) -->
    <button
      class="live-toggle"
      :class="{ 'live-toggle--active': !isPaused }"
      @click="emit('toggle-pause')"
      :title="isPaused ? 'Live-Updates fortsetzen' : 'Live-Updates pausieren'"
    >
      <span class="live-dot" :class="{ 'live-dot--pulsing': !isPaused }" />
      <component :is="isPaused ? Play : Pause" class="live-icon" />
      <span class="live-label">{{ isPaused ? 'Pause' : 'Live' }}</span>
    </button>

    <!-- Trenner -->
    <div class="tab-divider" />

    <!-- Tabs (mitte) -->
    <div class="tabs-container">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        :data-tab="tab.id"
        class="monitor-tab"
        :class="{ 'monitor-tab--active': activeTab === tab.id }"
        @click="handleTabClick(tab.id)"
      >
        <component :is="tab.icon" class="tab-icon" />
        <span class="monitor-tab__label">{{ tab.label }}</span>
        <span
          v-if="tab.id === 'events' && eventCounts.events > 0"
          class="monitor-badge monitor-badge--error"
        >
          {{ eventCounts.events }}
        </span>
        <span
          v-else-if="tab.id === 'logs' && eventCounts.logs > 0"
          class="monitor-badge"
        >
          {{ eventCounts.logs }}
        </span>
        <span
          v-else-if="tab.id === 'mqtt' && eventCounts.mqtt > 0"
          class="monitor-badge"
        >
          {{ eventCounts.mqtt }}
        </span>
      </button>
    </div>

    <!-- Spacer -->
    <div class="tab-spacer" />

    <!-- Action-Buttons (rechts) -->
    <div class="tab-actions">
      <button
        class="action-btn"
        @click="emit('export')"
        title="Events exportieren (JSON)"
      >
        <Download class="action-icon" />
      </button>
      <button
        v-if="isAdmin"
        class="action-btn action-btn--iridescent"
        @click="emit('open-cleanup-panel')"
        title="Bereinigung & Aufbewahrung"
      >
        <Database class="action-icon" />
      </button>
    </div>
  </nav>
</template>

<style scoped>
/* ============================================================================
   Tab Bar Container - Consolidated Header (Optimized Spacing)
   ============================================================================ */
.monitor-tab-bar {
  display: flex;
  align-items: center;
  gap: var(--space-md);                    /* Increased from sm for better visual separation */
  padding: 0.75rem var(--space-lg);        /* Increased vertical padding for breathing room */
  border-bottom: 1px solid var(--glass-border);
  background: var(--glass-bg);
  backdrop-filter: blur(12px);
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
}

/* ============================================================================
   Live Toggle Button - Iridescent
   ============================================================================ */
.live-toggle {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: 0.5rem 0.875rem;              /* Increased padding for better touch target (min 36px height) */
  border-radius: var(--radius-lg);        /* Slightly less round for modern look */
  font-size: 0.8125rem;                   /* Slightly larger for readability */
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-base);
  position: relative;
  overflow: hidden;
  background: linear-gradient(135deg,
    rgba(251, 191, 36, 0.2) 0%,
    rgba(251, 191, 36, 0.1) 100%
  );
  border: 1px solid rgba(251, 191, 36, 0.3);
  box-shadow: 0 0 12px rgba(251, 191, 36, 0.15);
  color: var(--color-warning);
  flex-shrink: 0;
}

.live-toggle:hover {
  background: linear-gradient(135deg,
    rgba(251, 191, 36, 0.3) 0%,
    rgba(251, 191, 36, 0.15) 100%
  );
  border-color: rgba(251, 191, 36, 0.5);
  box-shadow: 0 0 18px rgba(251, 191, 36, 0.25);
  transform: translateY(-1px);
}

.live-toggle:active {
  transform: translateY(0);
}

/* Live state - Green */
.live-toggle--active {
  color: var(--color-success);
  background: linear-gradient(135deg,
    rgba(52, 211, 153, 0.2) 0%,
    rgba(52, 211, 153, 0.1) 100%
  );
  border: 1px solid rgba(52, 211, 153, 0.3);
  box-shadow: 0 0 15px rgba(52, 211, 153, 0.2);
}

.live-toggle--active:hover {
  background: linear-gradient(135deg,
    rgba(52, 211, 153, 0.3) 0%,
    rgba(52, 211, 153, 0.15) 100%
  );
  border-color: rgba(52, 211, 153, 0.5);
  box-shadow: 0 0 20px rgba(52, 211, 153, 0.3);
}

.live-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: currentColor;
  flex-shrink: 0;
  box-shadow: 0 0 6px currentColor;
}

.live-dot--pulsing {
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.live-icon {
  width: 0.875rem;
  height: 0.875rem;
}

.live-label {
  font-weight: 600;
}

/* ============================================================================
   Divider
   ============================================================================ */
.tab-divider {
  width: 1px;
  height: 1.75rem;                        /* Slightly taller for visual weight */
  background: linear-gradient(
    to bottom,
    transparent,
    var(--glass-border) 20%,
    var(--glass-border) 80%,
    transparent
  );                                       /* Subtle fade effect */
  margin: 0 var(--space-sm);              /* More horizontal spacing */
  flex-shrink: 0;
}

/* ============================================================================
   Tabs Container
   ============================================================================ */
.tabs-container {
  /* B6.1: Scrollbare Tab-Bar mit Fade-Hinweis an den Raendern, falls Tabs ueberlaufen. */
  display: flex;
  align-items: center;
  gap: 0.375rem;                          /* Slightly more gap between tabs */
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
  -ms-overflow-style: none;
  mask-image: linear-gradient(
    to right,
    transparent 0,
    var(--color-text-inverse) 16px,
    var(--color-text-inverse) calc(100% - 16px),
    transparent 100%
  );
  -webkit-mask-image: linear-gradient(
    to right,
    transparent 0,
    var(--color-text-inverse) 16px,
    var(--color-text-inverse) calc(100% - 16px),
    transparent 100%
  );
}

.tabs-container::-webkit-scrollbar {
  display: none;
}

.monitor-tab {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.875rem;               /* Consistent padding with live toggle */
  border-radius: var(--radius-lg);
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--color-text-secondary);
  background: transparent;
  border: 1px solid transparent;           /* Reserve space for border on active */
  cursor: pointer;
  transition: all var(--transition-base);
  white-space: nowrap;
  flex-shrink: 0;
}

.monitor-tab:hover {
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-primary);
  border-color: var(--glass-border);
}

.monitor-tab--active {
  background: linear-gradient(135deg,
    rgba(96, 165, 250, 0.1) 0%,
    rgba(129, 140, 248, 0.08) 100%
  );                                       /* Subtle iridescent background */
  color: var(--color-text-primary);
  border-color: rgba(96, 165, 250, 0.25);
  box-shadow: 0 0 10px rgba(96, 165, 250, 0.1);
}

.tab-icon {
  width: 1rem;
  height: 1rem;
}

.monitor-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.25rem;
  height: 1.25rem;
  padding: 0 0.375rem;
  border-radius: var(--radius-full);
  font-size: 0.625rem;
  font-weight: 600;
  background-color: var(--color-bg-quaternary);
  color: var(--color-text-secondary);
}

.monitor-badge--error {
  background-color: var(--color-error);
  color: white;
}

/* ============================================================================
   Spacer (flex-grow)
   ============================================================================ */
.tab-spacer {
  flex: 1;
  min-width: var(--space-md);
}

/* ============================================================================
   Action Buttons
   ============================================================================ */
.tab-actions {
  display: flex;
  align-items: center;
  gap: var(--space-sm);                   /* More spacing between action buttons */
  flex-shrink: 0;
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;                         /* Slightly larger (36px) */
  height: 2.25rem;
  border-radius: var(--radius-lg);
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  border: 1px solid var(--glass-border);
  cursor: pointer;
  transition: all var(--transition-base);
  position: relative;
  overflow: hidden;
}

.action-btn::before {
  content: '';
  position: absolute;
  inset: 0;
  background: var(--gradient-iridescent);
  opacity: 0;
  transition: opacity var(--transition-base);
}

.action-btn:hover::before {
  opacity: 0.15;
}

.action-btn:hover {
  background: var(--color-bg-quaternary);
  color: var(--color-text-primary);
  border-color: var(--glass-border-hover);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}

.action-btn:active {
  transform: translateY(0);
}

/* Iridescent Button (Admin) */
.action-btn--iridescent {
  background: var(--gradient-iridescent);
  color: white;
  border-color: var(--color-iridescent-1);
  box-shadow: 0 0 10px rgba(96, 165, 250, 0.2);
}

.action-btn--iridescent::before {
  display: none;
}

.action-btn--iridescent:hover {
  transform: translateY(-2px);
  box-shadow: 0 0 20px rgba(96, 165, 250, 0.4);
}

.action-icon {
  width: 1rem;
  height: 1rem;
  position: relative;
  z-index: var(--z-dropdown);
}

/* ============================================================================
   Mobile Responsive
   ============================================================================ */
@media (max-width: 768px) {
  .monitor-tab-bar {
    padding: 0.625rem var(--space-md);    /* Slightly reduce but keep comfortable */
    gap: var(--space-sm);
  }

  .live-toggle {
    padding: 0.5rem 0.75rem;
  }

  .live-label {
    display: none;
  }

  .monitor-tab {
    min-height: 40px;                      /* 40px touch target */
    padding: 0.5rem 0.75rem;
    font-size: 0.8125rem;
  }

  .action-btn {
    width: 40px;                           /* 40px touch target on mobile */
    height: 40px;
  }
}

@media (max-width: 480px) {
  .monitor-tab__label {
    display: none;
  }

  .monitor-tab {
    padding: 0.5rem;
    min-width: 40px;
  }

  .tab-divider {
    display: none;
  }

  .tab-actions {
    gap: var(--space-xs);                  /* Tighter on very small screens */
  }
}

/* Allow labels on larger phones in landscape */
@media (min-width: 480px) and (max-width: 768px) {
  .monitor-tab__label {
    display: inline;
  }
}
</style>
