<script setup lang="ts">
/**
 * PluginCard
 *
 * Displays a single AutoOps plugin with status, category, last execution,
 * and quick actions (execute, enable/disable).
 */

import { computed } from 'vue'
import { Play, Power, PowerOff, Clock, CheckCircle, XCircle, Loader2 } from 'lucide-vue-next'
import type { PluginDTO } from '@/api/plugins'
import { formatRelativeTime } from '@/utils/formatters'

interface Props {
  plugin: PluginDTO
  isExecuting?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isExecuting: false,
})

const emit = defineEmits<{
  (e: 'select', pluginId: string): void
  (e: 'execute', pluginId: string): void
  (e: 'toggle', pluginId: string, enabled: boolean): void
}>()

const CATEGORY_LABELS: Record<string, string> = {
  monitoring: 'Monitoring',
  automation: 'Automatisierung',
  diagnostics: 'Diagnose',
  maintenance: 'Wartung',
}

const STATUS_ICONS: Record<string, typeof CheckCircle> = {
  success: CheckCircle,
  error: XCircle,
  failure: XCircle,
  running: Loader2,
  timeout: Clock,
}

const categoryLabel = computed(() =>
  CATEGORY_LABELS[props.plugin.category] || props.plugin.category,
)

const lastExecStatus = computed(() =>
  props.plugin.last_execution?.status || null,
)

const lastExecTime = computed(() => {
  const exec = props.plugin.last_execution
  const ts = exec?.finished_at ?? exec?.started_at
  if (!ts) return null
  return formatRelativeTime(new Date(ts))
})
</script>

<template>
  <div
    class="plugin-card"
    :class="{
      'plugin-card--disabled': !plugin.is_enabled,
      'plugin-card--executing': isExecuting,
    }"
    @click="emit('select', plugin.plugin_id)"
  >
    <!-- Header -->
    <div class="plugin-card__header">
      <div class="plugin-card__title-row">
        <span class="plugin-card__name">{{ plugin.display_name }}</span>
        <span class="plugin-card__status" :class="plugin.is_enabled ? 'plugin-card__status--active' : 'plugin-card__status--disabled'">
          <span
            class="plugin-card__status-dot"
            :class="plugin.is_enabled ? 'plugin-card__status-dot--active' : 'plugin-card__status-dot--disabled'"
          />
          {{ plugin.is_enabled ? 'Aktiv' : 'Inaktiv' }}
        </span>
      </div>
      <span class="plugin-card__category">{{ categoryLabel }}</span>
    </div>

    <!-- Description -->
    <p class="plugin-card__description">{{ plugin.description }}</p>

    <!-- Capabilities -->
    <div v-if="plugin.capabilities.length > 0" class="plugin-card__capabilities">
      <span
        v-for="cap in plugin.capabilities"
        :key="cap"
        class="plugin-card__capability-chip"
      >
        {{ cap }}
      </span>
    </div>

    <!-- Last Execution -->
    <div v-if="lastExecStatus" class="plugin-card__last-exec">
      <component
        :is="STATUS_ICONS[lastExecStatus] || Clock"
        class="plugin-card__exec-icon"
        :class="`plugin-card__exec-icon--${lastExecStatus}`"
      />
      <span class="plugin-card__exec-text">
        {{ lastExecTime }}
      </span>
    </div>

    <!-- Actions -->
    <div class="plugin-card__actions" @click.stop>
      <button
        class="plugin-card__action-btn plugin-card__action-btn--execute"
        :disabled="!plugin.is_enabled || isExecuting"
        title="Plugin ausführen"
        aria-label="Plugin ausführen"
        @click="emit('execute', plugin.plugin_id)"
      >
        <Loader2 v-if="isExecuting" class="w-3.5 h-3.5 animate-spin" />
        <Play v-else class="w-3.5 h-3.5" />
        <span>Ausführen</span>
      </button>
      <button
        class="plugin-card__action-btn"
        :class="plugin.is_enabled
          ? 'plugin-card__action-btn--disable'
          : 'plugin-card__action-btn--enable'"
        :title="plugin.is_enabled ? 'Deaktivieren' : 'Aktivieren'"
        :aria-label="plugin.is_enabled ? 'Plugin deaktivieren' : 'Plugin aktivieren'"
        @click="emit('toggle', plugin.plugin_id, !plugin.is_enabled)"
      >
        <PowerOff v-if="plugin.is_enabled" class="w-3.5 h-3.5" />
        <Power v-else class="w-3.5 h-3.5" />
        <span>{{ plugin.is_enabled ? 'Deaktivieren' : 'Aktivieren' }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.plugin-card {
  position: relative;
  padding: 1rem;
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.plugin-card:hover {
  border-color: var(--color-iridescent-2);
  background: var(--color-bg-tertiary);
}

.plugin-card--disabled {
  opacity: 0.6;
}

.plugin-card--executing {
  border-color: var(--color-warning);
}

.plugin-card__header {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.plugin-card__title-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.plugin-card__name {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
}

.plugin-card__status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.plugin-card__status {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-size: var(--text-xxs);
  font-weight: 600;
  padding: 2px 6px;
  border-radius: var(--radius-full);
}

.plugin-card__status-dot--active {
  background: var(--color-success);
  box-shadow: 0 0 4px var(--color-success);
}

.plugin-card__status-dot--disabled {
  background: var(--color-text-muted);
}

.plugin-card__status--active {
  color: var(--color-success);
  background: color-mix(in srgb, var(--color-success) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-success) 30%, transparent);
}

.plugin-card__status--disabled {
  color: var(--color-text-secondary);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
}

.plugin-card__category {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.plugin-card__description {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  line-height: 1.4;
  margin: 0;
}

.plugin-card__capabilities {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
}

.plugin-card__capability-chip {
  font-size: 0.625rem;
  padding: 0.125rem 0.375rem;
  background: rgba(129, 140, 248, 0.08);
  color: var(--color-iridescent-2);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(129, 140, 248, 0.15);
}

.plugin-card__last-exec {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.plugin-card__exec-icon {
  width: 14px;
  height: 14px;
}

.plugin-card__exec-icon--success {
  color: var(--color-success);
}

.plugin-card__exec-icon--failure,
.plugin-card__exec-icon--error {
  color: var(--color-error);
}

.plugin-card__exec-icon--running {
  color: var(--color-warning);
  animation: spin 1s linear infinite;
}

.plugin-card__exec-icon--timeout {
  color: var(--color-text-muted);
}

.plugin-card__exec-text {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.plugin-card__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin-top: auto;
  padding-top: 0.375rem;
}

.plugin-card__action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.25rem;
  min-height: 32px;
  padding: 0 0.5rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
  font-size: var(--text-xs);
  font-weight: 500;
}

.plugin-card__action-btn:hover:not(:disabled) {
  border-color: var(--color-iridescent-2);
  color: var(--color-text-primary);
}

.plugin-card__action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.plugin-card__action-btn--execute:hover:not(:disabled) {
  border-color: var(--color-success);
  color: var(--color-success);
}

.plugin-card__action-btn--disable:hover {
  border-color: var(--color-error);
  color: var(--color-error);
}

.plugin-card__action-btn--enable:hover {
  border-color: var(--color-success);
  color: var(--color-success);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
