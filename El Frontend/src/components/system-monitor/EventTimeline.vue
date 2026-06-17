<script setup lang="ts">
/**
 * EventTimeline - Horizontale Timeline-Visualisierung korrelierter Events
 *
 * Zeigt den zeitlichen Verlauf korrelierter Events als horizontale Timeline
 * mit Latenz-Segmenten und farbcodierten Event-Nodes.
 *
 * Features:
 * - Horizontale Timeline (Desktop) / Vertikale Timeline (Mobile)
 * - Latenz-Farbcodierung: <100ms gruen, 100-500ms gelb, >500ms rot
 * - Event-Cards mit Kategorie-Farben
 * - "Aktuell" Badge fuer ausgewaehltes Event
 * - Klick auf Event wechselt Auswahl
 */

import { computed } from 'vue'
import {
  ArrowUp,
  ArrowDown,
  Circle,
} from 'lucide-vue-next'
import type { UnifiedEvent } from '@/types/websocket-events'
import { getEventIcon } from '@/utils/eventTypeIcons'
import { getEventCategory } from '@/utils/eventTransformer'

// ============================================================
// PROPS
// ============================================================
const props = defineProps<{
  /** Alle korrelierten Events (chronologisch sortiert) */
  events: UnifiedEvent[]
  /** ID des aktuell ausgewaehlten Events (wird hervorgehoben) */
  currentEventId: string
  /** Gesamte Latenz in Millisekunden */
  totalLatencyMs: number | null
}>()

// ============================================================
// EMITS
// ============================================================
const emit = defineEmits<{
  /** User klickt auf ein Event in der Timeline */
  'select-event': [event: UnifiedEvent]
}>()

// ============================================================
// COMPUTED
// ============================================================

/** Events chronologisch sortiert (aeltestes zuerst) */
const sortedEvents = computed(() => {
  return [...props.events].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  )
})

/** Latenz zwischen jedem Event-Paar */
const eventLatencies = computed(() => {
  const latencies: number[] = []
  for (let i = 1; i < sortedEvents.value.length; i++) {
    const prev = new Date(sortedEvents.value[i - 1].timestamp).getTime()
    const curr = new Date(sortedEvents.value[i].timestamp).getTime()
    latencies.push(curr - prev)
  }
  return latencies
})

/** Ist dies das erste Event (Ausloeser)? */
function isFirstEvent(event: UnifiedEvent): boolean {
  return sortedEvents.value[0]?.id === event.id
}

/** Ist dies das letzte Event (Abschluss)? */
function isLastEvent(event: UnifiedEvent): boolean {
  return sortedEvents.value[sortedEvents.value.length - 1]?.id === event.id
}

/** Ist dies das aktuell ausgewaehlte Event? */
function isCurrentEvent(event: UnifiedEvent): boolean {
  return event.id === props.currentEventId
}

/** CSS-Klasse fuer Latenz-Farbe */
function getLatencyColorClass(ms: number): string {
  if (ms < 100) return 'latency--fast'
  if (ms <= 500) return 'latency--medium'
  return 'latency--slow'
}

/** Latenz formatieren */
function formatLatency(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60000).toFixed(1)}min`
}

/** Timestamp formatieren (mit Millisekunden) */
function formatTimestamp(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString('de-DE', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

/** Event-Typ lesbarer machen */
function formatEventType(eventType: string): string {
  return eventType.replace(/_/g, ' ').toUpperCase()
}

/** Event-Kategorie als CSS-Klasse */
function getEventCategoryClass(event: UnifiedEvent): string {
  return `timeline-node--${getEventCategory(event)}`
}
</script>

<template>
  <div class="event-timeline" :class="{ 'event-timeline--single': events.length <= 1 }">

    <!-- Nur 1 Event: Keine Timeline noetig -->
    <div v-if="events.length <= 1" class="timeline-single">
      <p class="timeline-single__text">
        Keine weiteren Events mit dieser Korrelations-ID
      </p>
    </div>

    <!-- 2+ Events: Timeline anzeigen -->
    <template v-else>

      <!-- Timeline-Linie mit Latenz-Segmenten (Desktop) -->
      <div class="timeline-track">
        <div class="timeline-track__line" />
        <div
          v-for="(latency, index) in eventLatencies"
          :key="`latency-${index}`"
          class="timeline-track__segment"
          :class="getLatencyColorClass(latency)"
          :style="{
            left: `${(index / (sortedEvents.length - 1)) * 100}%`,
            width: `${(1 / (sortedEvents.length - 1)) * 100}%`
          }"
        >
          <span class="timeline-track__latency">
            {{ formatLatency(latency) }}
          </span>
        </div>
      </div>

      <!-- Event-Nodes -->
      <div class="timeline-nodes">
        <button
          v-for="(event, index) in sortedEvents"
          :key="event.id"
          class="timeline-node"
          :class="[
            {
              'timeline-node--current': isCurrentEvent(event),
              'timeline-node--first': isFirstEvent(event),
              'timeline-node--last': isLastEvent(event),
            },
            getEventCategoryClass(event)
          ]"
          :style="sortedEvents.length > 1 ? { left: `${(index / (sortedEvents.length - 1)) * 100}%` } : undefined"
          @click="emit('select-event', event)"
          :title="`${formatEventType(event.event_type)} - ${formatTimestamp(event.timestamp)}`"
        >
          <!-- Node-Punkt -->
          <div class="timeline-node__dot">
            <component
              :is="isFirstEvent(event) ? ArrowUp : isLastEvent(event) ? ArrowDown : Circle"
              :size="14"
            />
          </div>

          <!-- Node-Card -->
          <div class="timeline-node__card">
            <div class="timeline-node__header">
              <component
                :is="getEventIcon(event.event_type)"
                :size="14"
                class="timeline-node__icon"
              />
              <span class="timeline-node__type">
                {{ formatEventType(event.event_type) }}
              </span>
            </div>
            <time class="timeline-node__time">
              {{ formatTimestamp(event.timestamp) }}
            </time>
            <p v-if="event.message" class="timeline-node__message">
              {{ event.message }}
            </p>
            <span v-if="isCurrentEvent(event)" class="timeline-node__badge">
              Aktuell
            </span>
          </div>
        </button>

        <!-- Mobile: Latenz-Labels zwischen Nodes -->
        <div
          v-for="(latency, index) in eventLatencies"
          :key="`mobile-latency-${index}`"
          class="timeline-mobile-latency"
          :class="getLatencyColorClass(latency)"
        >
          {{ formatLatency(latency) }}
        </div>
      </div>

    </template>

  </div>
</template>

<style scoped>
/* ============================================================
   EVENT TIMELINE - Horizontale Visualisierung
   ============================================================ */

.event-timeline {
  position: relative;
  padding: 1rem 0;
  min-height: 120px;
}

.event-timeline--single {
  min-height: auto;
  padding: 0.5rem 0;
}

/* Single Event State */
.timeline-single {
  text-align: center;
  padding: 1rem;
}

.timeline-single__text {
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

/* ============================================================
   TIMELINE TRACK - Die Verbindungslinie (Desktop)
   ============================================================ */

.timeline-track {
  position: relative;
  height: 2rem;
  margin: 0 4rem;
}

.timeline-track__line {
  position: absolute;
  top: 50%;
  left: 0;
  right: 0;
  height: 2px;
  background: rgba(255, 255, 255, 0.1);
  transform: translateY(-50%);
}

.timeline-track__segment {
  position: absolute;
  top: 50%;
  height: 3px;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
}

.timeline-track__latency {
  position: absolute;
  top: -1.25rem;
  font-size: 0.6875rem;
  font-weight: 600;
  font-family: monospace;
  padding: 0.125rem 0.375rem;
  border-radius: var(--radius-xs);
  white-space: nowrap;
}

/* Latenz-Farben */
.latency--fast {
  background: linear-gradient(90deg, rgba(52, 211, 153, 0.3), rgba(52, 211, 153, 0.3));
}
.latency--fast .timeline-track__latency,
.latency--fast.timeline-mobile-latency {
  background: rgba(52, 211, 153, 0.2);
  color: var(--color-success);
}

.latency--medium {
  background: linear-gradient(90deg, rgba(251, 191, 36, 0.3), rgba(251, 191, 36, 0.3));
}
.latency--medium .timeline-track__latency,
.latency--medium.timeline-mobile-latency {
  background: rgba(251, 191, 36, 0.2);
  color: var(--color-warning);
}

.latency--slow {
  background: linear-gradient(90deg, rgba(248, 113, 113, 0.3), rgba(248, 113, 113, 0.3));
}
.latency--slow .timeline-track__latency,
.latency--slow.timeline-mobile-latency {
  background: rgba(248, 113, 113, 0.2);
  color: var(--color-error);
}

/* ============================================================
   TIMELINE NODES - Die Event-Punkte
   ============================================================ */

.timeline-nodes {
  position: relative;
  display: flex;
  justify-content: space-between;
  margin: 0 4rem;
  padding-top: 0.5rem;
  min-height: 8rem;
}

.timeline-node {
  position: absolute;
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  transition: transform 0.15s ease;
}

.timeline-node:hover {
  transform: translateX(-50%) scale(1.02);
}

.timeline-node:focus {
  outline: none;
}

.timeline-node:focus .timeline-node__dot {
  box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.3);
}

/* Node-Punkt */
.timeline-node__dot {
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 15, 20, 0.95);
  border: 2px solid rgba(255, 255, 255, 0.2);
  color: var(--color-text-muted);
  transition: all 0.15s ease;
  z-index: var(--z-dropdown);
}

.timeline-node--current .timeline-node__dot {
  border-color: var(--color-info);
  background: rgba(96, 165, 250, 0.15);
  color: var(--color-info);
}

/* Kategorie-Farben fuer Dot */
.timeline-node--esp-status .timeline-node__dot { border-color: var(--color-accent); color: var(--color-accent); }
.timeline-node--sensors .timeline-node__dot { border-color: var(--color-category-sensors); color: var(--color-category-sensors); }
.timeline-node--actuators .timeline-node__dot { border-color: var(--color-category-actuators); color: var(--color-category-actuators); }
.timeline-node--system .timeline-node__dot { border-color: var(--color-category-system); color: var(--color-category-system); }

/* Node-Card */
.timeline-node__card {
  min-width: 130px;
  max-width: 170px;
  padding: 0.5rem 0.625rem;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: var(--radius-md);
  text-align: center;
  transition: all 0.15s ease;
}

.timeline-node:hover .timeline-node__card {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.1);
}

.timeline-node--current .timeline-node__card {
  background: rgba(96, 165, 250, 0.08);
  border-color: rgba(96, 165, 250, 0.2);
}

.timeline-node__header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.25rem;
  margin-bottom: 0.25rem;
}

.timeline-node__icon {
  flex-shrink: 0;
}

.timeline-node__type {
  font-size: 0.625rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.025em;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.timeline-node__time {
  display: block;
  font-size: 0.75rem;
  font-family: monospace;
  color: var(--color-text-muted);
  margin-bottom: 0.125rem;
}

.timeline-node__message {
  font-size: 0.625rem;
  color: var(--color-text-secondary);
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.timeline-node__badge {
  display: inline-block;
  margin-top: 0.25rem;
  padding: 0.0625rem 0.375rem;
  font-size: 0.5625rem;
  font-weight: 600;
  text-transform: uppercase;
  background: rgba(96, 165, 250, 0.15);
  color: var(--color-info);
  border-radius: var(--radius-full);
}

/* Mobile Latency Labels (hidden on desktop) */
.timeline-mobile-latency {
  display: none;
}

/* ============================================================
   RESPONSIVE - Vertikale Timeline auf Mobile
   ============================================================ */

@media (max-width: 640px) {
  .timeline-track {
    display: none;
  }

  .timeline-nodes {
    flex-direction: column;
    gap: 0;
    margin: 0;
    padding: 0;
    min-height: auto;
  }

  .timeline-node {
    position: relative;
    transform: none;
    flex-direction: row;
    width: 100%;
    left: 0 !important;
    padding-left: 2.5rem;
    padding-bottom: 0.75rem;
  }

  .timeline-node:hover {
    transform: none;
  }

  .timeline-node__dot {
    position: absolute;
    left: 0;
    top: 0;
    flex-shrink: 0;
  }

  .timeline-node__card {
    flex: 1;
    text-align: left;
    min-width: 0;
    max-width: none;
  }

  .timeline-node__header {
    justify-content: flex-start;
  }

  /* Vertikale Verbindungslinie */
  .timeline-node:not(:last-of-type)::after {
    content: '';
    position: absolute;
    left: calc(1rem - 1px);
    top: 2rem;
    bottom: -0.75rem;
    width: 2px;
    background: rgba(255, 255, 255, 0.1);
  }

  /* Mobile Latency Labels */
  .timeline-mobile-latency {
    display: flex;
    align-items: center;
    justify-content: center;
    margin-left: 2.5rem;
    margin-bottom: 0.75rem;
    padding: 0.125rem 0.5rem;
    border-radius: var(--radius-xs);
    font-size: 0.6875rem;
    font-weight: 600;
    font-family: monospace;
    width: fit-content;
  }
}
</style>
