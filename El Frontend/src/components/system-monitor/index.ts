/**
 * System Monitor Components
 *
 * Components for the unified System Monitor view.
 *
 * Phase 2 Components (Extracted from SystemMonitorView.vue):
 * - MonitorTabs.vue - Consolidated tab bar with Live toggle, tabs, and action buttons
 * - MonitorFilterPanel.vue - Filter controls (ESP, level, time, event types)
 * - UnifiedEventList.vue - Event list with virtual scrolling
 * - EventDetailsPanel.vue - Event detail panel with error code translation
 *
 * Phase 3 Components (Tab Content):
 * - ServerLogsTab.vue - Server log viewer with polling
 * - DatabaseTab.vue - Database table explorer
 * - MqttTrafficTab.vue - MQTT message viewer
 *
 * DEPRECATED:
 * - MonitorHeader.vue - Functionality merged into MonitorTabs.vue (2026-01-26)
 */

// Phase 2 exports
/** @deprecated Use MonitorTabs instead - header functionality is now integrated there */
export { default as MonitorHeader } from './MonitorHeader.vue'
export { default as MonitorTabs } from './MonitorTabs.vue'
export { default as MonitorFilterPanel } from './MonitorFilterPanel.vue'
export { default as UnifiedEventList } from './UnifiedEventList.vue'
export { default as EventDetailsPanel } from './EventDetailsPanel.vue'

// Phase 3 exports - Tab Content
export { default as ServerLogsTab } from './ServerLogsTab.vue'
export { default as DatabaseTab } from './DatabaseTab.vue'
export { default as MqttTrafficTab } from './MqttTrafficTab.vue'

// Re-export types
export type { TabId } from './types'
