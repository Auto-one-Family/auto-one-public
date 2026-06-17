<template>
  <div class="cleanup-preview">
    <!-- Header -->
    <div class="preview-header">
      <Eye class="w-5 h-5" />
      <h3>Vorschau</h3>
    </div>

    <!-- Summary -->
    <div class="preview-summary">
      <span class="event-count">
        {{ formatNumber(preview.deleted_count) }} Einträge würden gelöscht
      </span>

      <!-- Breakdown Badges -->
      <div v-if="hasSeverityBreakdown" class="severity-breakdown">
        <span
          v-for="(count, severity) in preview.deleted_by_severity"
          :key="String(severity)"
          :class="`severity-badge severity-${severity}`"
        >
          {{ severityLabel(String(severity)) }}: {{ formatNumber(count) }}
        </span>
      </div>
    </div>

    <!-- Event-Liste (Smart Display basierend auf Anzahl) -->
    <div class="preview-events">
      <!-- Case 1: Keine Events -->
      <div v-if="preview.deleted_count === 0" class="empty-preview">
        <CheckCircle class="w-8 h-8 text-green-400" />
        <p>Keine Ereignisse entsprechen den Filtern</p>
      </div>

      <!-- Case 2: 1-5 Events - Alle inline anzeigen -->
      <div
        v-else-if="preview.deleted_count <= 5 && hasPreviewEvents"
        class="inline-events"
      >
        <PreviewEventCard
          v-for="event in preview.preview_events"
          :key="event.id"
          :event="event"
        />
      </div>

      <!-- Case 3: 6-20 Events - Expandable mit "Mehr anzeigen" -->
      <div
        v-else-if="preview.deleted_count <= 20 && hasPreviewEvents"
        class="expandable-events"
      >
        <!-- Erste 5 Events -->
        <PreviewEventCard
          v-for="event in visibleEvents"
          :key="event.id"
          :event="event"
        />

        <!-- Expand-Button -->
        <button
          v-if="!showAll && hasMore"
          class="expand-btn"
          @click="showAll = true"
        >
          <ChevronDown class="w-4 h-4" />
          ... und {{ preview.deleted_count - 5 }} weitere anzeigen
        </button>
      </div>

      <!-- Case 4: 21+ Events - Statistics + Modal-Button -->
      <div v-else class="large-preview">
        <div class="large-stats">
          <AlertCircle class="w-6 h-6 text-yellow-400" />
          <div>
            <p class="font-semibold">{{ formatNumber(preview.deleted_count) }} Ereignisse betroffen</p>
            <p class="text-sm opacity-75">Zu viele für Inline-Anzeige</p>
          </div>
        </div>

        <!-- Zusatz-Info wenn verfügbar -->
        <div v-if="hasPreviewEvents" class="sample-info">
          <p class="text-sm opacity-75">
            <template v-if="allLoaded">
              Alle {{ formatNumber(preview.preview_events!.length) }} von {{ formatNumber(preview.deleted_count) }} Einträgen:
            </template>
            <template v-else>
              Beispiele (erste {{ preview.preview_events!.length }} von {{ formatNumber(preview.deleted_count) }}):
            </template>
          </p>
          <div class="sample-events" :class="{ 'sample-events--expanded': allLoaded }">
            <PreviewEventCard
              v-for="event in displayedSampleEvents"
              :key="event.id"
              :event="event"
              compact
            />
          </div>
        </div>

        <!-- Modal-Trigger (nur anzeigen wenn mehr Events existieren und nicht bereits alle geladen) -->
        <button
          v-if="preview.preview_limited && !allLoaded"
          class="show-all-modal-btn"
          @click="handleLoadAll"
        >
          <List class="w-4 h-4" />
          Alle {{ formatNumber(preview.deleted_count) }} Events anzeigen
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  Eye,
  CheckCircle,
  ChevronDown,
  AlertCircle,
  List
} from 'lucide-vue-next'

import PreviewEventCard from './PreviewEventCard.vue'
import type { CleanupResult } from '@/api/audit'

interface Props {
  preview: CleanupResult
}

const props = defineProps<Props>()

const emit = defineEmits<{
  openFullList: []
}>()

const showAll = ref(false)
const allLoaded = ref(false)

const hasPreviewEvents = computed(() => {
  return props.preview.preview_events && props.preview.preview_events.length > 0
})

const displayedSampleEvents = computed(() => {
  if (!props.preview.preview_events) return []
  if (allLoaded.value) return props.preview.preview_events
  return props.preview.preview_events.slice(0, 10)
})

function handleLoadAll() {
  allLoaded.value = true
  emit('openFullList')
}

const hasSeverityBreakdown = computed(() => {
  return Object.keys(props.preview.deleted_by_severity).length > 0
})

const visibleEvents = computed(() => {
  if (!props.preview.preview_events) return []

  if (showAll.value) {
    return props.preview.preview_events
  }

  return props.preview.preview_events.slice(0, 5)
})

const hasMore = computed(() => {
  return (props.preview.preview_events?.length ?? 0) > 5
})

function formatNumber(num: number): string {
  return new Intl.NumberFormat('de-DE').format(num)
}

function severityLabel(severity: string): string {
  const labels: Record<string, string> = {
    info: 'Info',
    warning: 'Warnung',
    error: 'Fehler',
    critical: 'Kritisch',
  }
  return labels[severity] || severity
}
</script>

<style scoped>
.cleanup-preview {
  padding: 1.25rem;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: var(--radius-md);
  margin-top: 1rem;
}

.preview-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
  color: white;
}

.preview-header h3 {
  font-size: 1rem;
  font-weight: 600;
  margin: 0;
}

.preview-summary {
  margin-bottom: 1rem;
}

.event-count {
  display: block;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--color-warning);
  margin-bottom: 0.5rem;
}

.severity-breakdown {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.severity-badge {
  padding: 0.25rem 0.75rem;
  border-radius: var(--radius-md);
  font-size: 0.75rem;
  font-weight: 500;
}

.severity-info {
  background: rgba(59, 130, 246, 0.2);
  color: var(--color-accent);
}

.severity-warning {
  background: rgba(251, 191, 36, 0.2);
  color: var(--color-warning);
}

.severity-error {
  background: rgba(239, 68, 68, 0.2);
  color: var(--color-error);
}

.severity-critical {
  background: rgba(220, 38, 38, 0.2);
  color: var(--color-error);
}

.preview-events {
  margin-top: 1rem;
}

.empty-preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  padding: 2rem;
  color: rgba(255, 255, 255, 0.6);
  text-align: center;
}

.empty-preview p {
  margin: 0;
}

.text-green-400 {
  color: var(--color-success);
}

.inline-events,
.expandable-events {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.expand-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.75rem;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: var(--radius-md);
  color: rgba(255, 255, 255, 0.7);
  cursor: pointer;
  transition: all 0.3s ease;
}

.expand-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: white;
}

.large-preview {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.large-stats {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: rgba(251, 191, 36, 0.1);
  border: 1px solid rgba(251, 191, 36, 0.3);
  border-radius: var(--radius-md);
}

.large-stats p {
  margin: 0;
}

.font-semibold {
  font-weight: 600;
}

.text-sm {
  font-size: 0.875rem;
}

.opacity-75 {
  opacity: 0.75;
}

.text-yellow-400 {
  color: var(--color-warning);
}

.sample-info {
  padding: 1rem;
  background: rgba(255, 255, 255, 0.02);
  border-radius: var(--radius-md);
}

.sample-info > p {
  margin: 0 0 0.75rem;
}

.sample-events {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-height: 300px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.2) transparent;
}

.sample-events--expanded {
  max-height: 400px;
}

.sample-events::-webkit-scrollbar {
  width: 6px;
}

.sample-events::-webkit-scrollbar-track {
  background: transparent;
}

.sample-events::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
  border-radius: var(--radius-xs);
}

.sample-events::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.3);
}

.show-all-modal-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.75rem;
  background: linear-gradient(135deg, var(--color-iridescent-2) 0%, var(--color-iridescent-3) 100%);
  border: none;
  border-radius: var(--radius-md);
  color: white;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
}

.show-all-modal-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(102, 126, 234, 0.4);
}

/* Icon sizing */
.w-4 { width: 1rem; }
.h-4 { height: 1rem; }
.w-5 { width: 1.25rem; }
.h-5 { height: 1.25rem; }
.w-6 { width: 1.5rem; }
.h-6 { height: 1.5rem; }
.w-8 { width: 2rem; }
.h-8 { height: 2rem; }
</style>
