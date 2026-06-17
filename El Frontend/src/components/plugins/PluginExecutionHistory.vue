<script setup lang="ts">
/**
 * PluginExecutionHistory
 *
 * Displays execution history for a plugin with status, duration, and trigger info.
 */

import { computed } from 'vue'
import { CheckCircle, XCircle, Clock, Loader2, User, Cpu, Workflow } from 'lucide-vue-next'
import type { PluginExecutionDTO } from '@/api/plugins'
import { formatRelativeTime } from '@/utils/formatters'

interface Props {
  executions: PluginExecutionDTO[]
  isLoading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isLoading: false,
})

const STATUS_CONFIG: Record<string, { icon: typeof CheckCircle; label: string; class: string }> = {
  success: { icon: CheckCircle, label: 'Erfolgreich', class: 'exec--success' },
  error: { icon: XCircle, label: 'Fehlgeschlagen', class: 'exec--failure' },
  failure: { icon: XCircle, label: 'Fehlgeschlagen', class: 'exec--failure' },
  running: { icon: Loader2, label: 'Läuft...', class: 'exec--running' },
  timeout: { icon: Clock, label: 'Timeout', class: 'exec--timeout' },
}

const TRIGGER_ICONS: Record<string, typeof User> = {
  manual: User,
  logic_rule: Workflow,
  schedule: Clock,
  system: Cpu,
}

function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '—'
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`
  return `${seconds.toFixed(1)}s`
}

const sortedExecutions = computed(() =>
  [...props.executions].sort((a, b) => {
    const dateA = a.started_at ? new Date(a.started_at).getTime() : 0
    const dateB = b.started_at ? new Date(b.started_at).getTime() : 0
    return dateB - dateA
  }),
)
</script>

<template>
  <div class="exec-history">
    <!-- Loading -->
    <div v-if="isLoading" class="exec-history__loading">
      <Loader2 class="w-5 h-5 animate-spin" />
      <span>Lade Historie...</span>
    </div>

    <!-- Empty -->
    <div v-else-if="sortedExecutions.length === 0" class="exec-history__empty">
      Keine Ausführungen vorhanden
    </div>

    <!-- List -->
    <div v-else class="exec-history__list">
      <div
        v-for="exec in sortedExecutions"
        :key="exec.id"
        class="exec-history__item"
        :class="STATUS_CONFIG[exec.status]?.class || ''"
      >
        <div class="exec-history__status">
          <component
            :is="STATUS_CONFIG[exec.status]?.icon || Clock"
            class="exec-history__status-icon"
          />
        </div>

        <div class="exec-history__details">
          <div class="exec-history__top-row">
            <span class="exec-history__status-label">
              {{ STATUS_CONFIG[exec.status]?.label || exec.status }}
            </span>
            <span class="exec-history__duration">
              {{ formatDuration(exec.duration_seconds) }}
            </span>
          </div>

          <div class="exec-history__bottom-row">
            <div class="exec-history__trigger">
              <component
                :is="TRIGGER_ICONS[exec.triggered_by] || Cpu"
                class="exec-history__trigger-icon"
              />
              <span>{{ exec.triggered_by }}</span>
            </div>
            <span v-if="exec.started_at" class="exec-history__time">
              {{ formatRelativeTime(new Date(exec.started_at)) }}
            </span>
          </div>

          <!-- Error message -->
          <div v-if="exec.error_message" class="exec-history__error">
            {{ exec.error_message }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.exec-history {
  display: flex;
  flex-direction: column;
}

.exec-history__loading,
.exec-history__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 2rem;
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

.exec-history__list {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.exec-history__item {
  display: flex;
  gap: 0.75rem;
  padding: 0.625rem 0.75rem;
  background: var(--color-bg-secondary);
  border-left: 3px solid transparent;
  transition: background var(--transition-fast);
}

.exec-history__item:hover {
  background: var(--color-bg-tertiary);
}

.exec-history__item.exec--success {
  border-left-color: var(--color-success);
}

.exec-history__item.exec--failure {
  border-left-color: var(--color-error);
}

.exec-history__item.exec--running {
  border-left-color: var(--color-warning);
}

.exec-history__item.exec--timeout {
  border-left-color: var(--color-text-muted);
}

.exec-history__status {
  padding-top: 0.125rem;
  flex-shrink: 0;
}

.exec-history__status-icon {
  width: 16px;
  height: 16px;
}

.exec--success .exec-history__status-icon {
  color: var(--color-success);
}

.exec--failure .exec-history__status-icon {
  color: var(--color-error);
}

.exec--running .exec-history__status-icon {
  color: var(--color-warning);
  animation: spin 1s linear infinite;
}

.exec--timeout .exec-history__status-icon {
  color: var(--color-text-muted);
}

.exec-history__details {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.exec-history__top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.exec-history__status-label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-primary);
}

.exec-history__duration {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.exec-history__bottom-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.exec-history__trigger {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.exec-history__trigger-icon {
  width: 12px;
  height: 12px;
}

.exec-history__time {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.exec-history__error {
  margin-top: 0.25rem;
  padding: 0.375rem 0.5rem;
  font-size: var(--text-xs);
  color: var(--color-error);
  background: rgba(248, 113, 113, 0.06);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(248, 113, 113, 0.12);
  line-height: 1.4;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
