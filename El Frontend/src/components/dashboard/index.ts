/**
 * Dashboard Components
 *
 * Components for the two-level dashboard:
 * - Level 1: Zone overview with ESP cards (ActionBar, ZoneGroups, CrossEspConnections)
 * - Level 2: ESP-Orbital detail view
 */

// Level 1: Zone Overview
export { default as ActionBar } from './ActionBar.vue'
export { default as StatCard } from './StatCard.vue'
export { default as StatusPill } from './StatusPill.vue'
export { default as ComponentSidebar } from './ComponentSidebar.vue'
export { default as UnassignedDropBar } from './UnassignedDropBar.vue'
export { default as CrossEspConnectionOverlay } from './CrossEspConnectionOverlay.vue'

// Komponentenübersicht
export { default as ComponentCard } from './ComponentCard.vue'
export type { ComponentCardItem } from './types'

// Zonen
export { default as ZonePlate } from './ZonePlate.vue'
