<script setup lang="ts">
/**
 * PluginsView
 *
 * Phase 4C.2: Plugin Management UI.
 * Displays all AutoOps plugins with grid layout, detail slide-over,
 * config dialog, and execution history.
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Puzzle, Settings, History, RefreshCw } from 'lucide-vue-next'
import { usePluginsStore } from '@/shared/stores/plugins.store'
import { useOpsLifecycleStore } from '@/shared/stores/ops-lifecycle.store'
import PluginCard from '@/components/plugins/PluginCard.vue'
import PluginConfigDialog from '@/components/plugins/PluginConfigDialog.vue'
import PluginExecutionHistory from '@/components/plugins/PluginExecutionHistory.vue'
import SlideOver from '@/shared/design/primitives/SlideOver.vue'
import AccordionSection from '@/shared/design/primitives/AccordionSection.vue'
import type { PluginDetailDTO } from '@/api/plugins'
import { formatRelativeTime } from '@/utils/formatters'

const pluginsStore = usePluginsStore()
const opsLifecycle = useOpsLifecycleStore()

// ======================== STATE ========================

const activePluginId = ref<string | null>(null)
const showConfigDialog = ref(false)
const executingPluginId = ref<string | null>(null)
const activeFilter = ref<'all' | 'enabled' | 'disabled'>('all')

// ======================== COMPUTED ========================

const filteredPlugins = computed(() => {
  switch (activeFilter.value) {
    case 'enabled':
      return pluginsStore.enabledPlugins
    case 'disabled':
      return pluginsStore.disabledPlugins
    default:
      return pluginsStore.plugins
  }
})

const activePlugin = computed<PluginDetailDTO | null>(() =>
  pluginsStore.selectedPlugin,
)

const enabledCount = computed(() => pluginsStore.enabledPlugins.length)
const totalCount = computed(() => pluginsStore.plugins.length)
const pluginOpsEntries = computed(() =>
  opsLifecycle.sortedEntries.filter((entry) => entry.scope === 'plugin_execute'),
)

const latestPluginOps = computed(() => pluginOpsEntries.value[0] ?? null)

const activePluginOps = computed(() => {
  if (!activePluginId.value) return []
  return pluginOpsEntries.value.filter((entry) => entry.plugin_id === activePluginId.value).slice(0, 5)
})

const STATUS_LABELS: Record<string, string> = {
  initiated: 'Initiiert',
  running: 'Läuft',
  partial: 'Teilweise',
  success: 'Erfolgreich',
  failed: 'Fehlgeschlagen',
}

// ======================== METHODS ========================

async function selectPlugin(pluginId: string) {
  activePluginId.value = pluginId
  await pluginsStore.fetchPluginDetail(pluginId)
  await pluginsStore.fetchHistory(pluginId)
}

function closeDetail() {
  activePluginId.value = null
  pluginsStore.selectedPlugin = null
}

async function handleExecute(pluginId: string) {
  executingPluginId.value = pluginId
  await pluginsStore.executePlugin(pluginId)
  executingPluginId.value = null

  // Refresh detail if open
  if (activePluginId.value === pluginId) {
    await pluginsStore.fetchPluginDetail(pluginId)
    await pluginsStore.fetchHistory(pluginId)
  }
}

async function handleToggle(pluginId: string, enabled: boolean) {
  await pluginsStore.togglePlugin(pluginId, enabled)
}

function openConfigDialog() {
  showConfigDialog.value = true
}

async function handleSaveConfig(config: Record<string, unknown>) {
  if (!activePluginId.value) return
  await pluginsStore.updateConfig(activePluginId.value, config)
  showConfigDialog.value = false

  // Refresh detail
  await pluginsStore.fetchPluginDetail(activePluginId.value)
}

async function refreshPlugins() {
  await pluginsStore.fetchPlugins()
}

// ======================== LIFECYCLE ========================

onMounted(async () => {
  pluginsStore.startLifecycleMonitoring()
  await pluginsStore.fetchPlugins()
  await pluginsStore.reconcileRunningExecutions()
})

onUnmounted(() => {
  pluginsStore.stopLifecycleMonitoring()
})
</script>

<template>
  <div class="plugins-view">
    <!-- Header -->
    <div class="plugins-view__header">
      <div class="plugins-view__title-row">
        <Puzzle class="plugins-view__title-icon" />
        <h1 class="plugins-view__title">AutoOps Plugins</h1>
        <span class="plugins-view__count">
          {{ enabledCount }}/{{ totalCount }} aktiv
        </span>
      </div>

      <div class="plugins-view__toolbar">
        <!-- Filter Chips -->
        <div class="plugins-view__filters">
          <button
            v-for="filter in (['all', 'enabled', 'disabled'] as const)"
            :key="filter"
            class="plugins-view__filter-chip"
            :class="{ 'plugins-view__filter-chip--active': activeFilter === filter }"
            @click="activeFilter = filter"
          >
            {{ filter === 'all' ? 'Alle' : filter === 'enabled' ? 'Aktiv' : 'Deaktiviert' }}
          </button>
        </div>

        <button
          class="plugins-view__refresh-btn"
          :disabled="pluginsStore.isLoading"
          @click="refreshPlugins"
          title="Plugin-Liste aktualisieren"
        >
          <RefreshCw
            class="w-4 h-4"
            :class="{ 'animate-spin': pluginsStore.isLoading }"
          />
          <span>Aktualisieren</span>
        </button>
      </div>
    </div>

    <div v-if="latestPluginOps" class="plugins-view__ops-banner">
      <span class="plugins-view__ops-label">Ops-Lifecycle</span>
      <span
        class="plugins-view__ops-status"
        :class="`plugins-view__ops-status--${latestPluginOps.status}`"
      >
        {{ STATUS_LABELS[latestPluginOps.status] }}
      </span>
      <span class="plugins-view__ops-text">{{ latestPluginOps.title }}</span>
      <span class="plugins-view__ops-time">
        {{ formatRelativeTime(new Date(latestPluginOps.updated_at)) }}
      </span>
    </div>

    <!-- Plugin Grid -->
    <div class="plugins-view__grid grid-auto-md">
      <PluginCard
        v-for="plugin in filteredPlugins"
        :key="plugin.plugin_id"
        :plugin="plugin"
        :is-executing="executingPluginId === plugin.plugin_id"
        @select="selectPlugin"
        @execute="handleExecute"
        @toggle="handleToggle"
      />

      <!-- Empty State -->
      <div v-if="filteredPlugins.length === 0 && !pluginsStore.isLoading" class="plugins-view__empty">
        <Puzzle class="plugins-view__empty-icon" />
        <p>Keine Plugins gefunden</p>
      </div>
    </div>

    <!-- Detail SlideOver -->
    <SlideOver
      :open="!!activePluginId"
      :title="activePlugin?.display_name || 'Plugin'"
      @close="closeDetail"
    >
      <template v-if="activePlugin">
        <div class="plugin-detail">
          <!-- Status & Description -->
          <div class="plugin-detail__info">
            <div class="plugin-detail__status-row">
              <span
                class="plugin-detail__status-badge"
                :class="activePlugin.is_enabled
                  ? 'plugin-detail__status-badge--enabled'
                  : 'plugin-detail__status-badge--disabled'"
              >
                {{ activePlugin.is_enabled ? 'Aktiv' : 'Deaktiviert' }}
              </span>
              <span class="plugin-detail__category">
                {{ activePlugin.category }}
              </span>
            </div>
            <p class="plugin-detail__description">{{ activePlugin.description }}</p>
          </div>

          <!-- Quick Actions -->
          <div class="plugin-detail__actions">
            <button
              class="plugin-detail__action-btn plugin-detail__action-btn--execute"
              :disabled="!activePlugin.is_enabled || pluginsStore.isExecuting"
              @click="handleExecute(activePlugin.plugin_id)"
            >
              <RefreshCw class="w-4 h-4" />
              Ausführen
            </button>
            <button
              class="plugin-detail__action-btn plugin-detail__action-btn--config"
              @click="openConfigDialog"
            >
              <Settings class="w-4 h-4" />
              Konfiguration
            </button>
          </div>

          <AccordionSection
            v-if="activePluginOps.length > 0"
            title="Lifecycle (High-Risk)"
            storage-key="ao-plugin-lifecycle"
          >
            <div class="plugin-detail__lifecycle-list">
              <div
                v-for="entry in activePluginOps"
                :key="entry.id"
                class="plugin-detail__lifecycle-item"
              >
                <span
                  class="plugin-detail__lifecycle-badge"
                  :class="`plugin-detail__lifecycle-badge--${entry.status}`"
                >
                  {{ STATUS_LABELS[entry.status] }}
                </span>
                <div class="plugin-detail__lifecycle-body">
                  <div class="plugin-detail__lifecycle-title">
                    {{ entry.summary || entry.title }}
                  </div>
                  <div class="plugin-detail__lifecycle-meta">
                    <span v-if="entry.execution_id">Execution: {{ entry.execution_id }}</span>
                    <span>{{ formatRelativeTime(new Date(entry.updated_at)) }}</span>
                  </div>
                  <div v-if="entry.reason_text" class="plugin-detail__lifecycle-reason">
                    {{ entry.reason_text }}
                  </div>
                </div>
              </div>
            </div>
          </AccordionSection>

          <!-- Capabilities -->
          <AccordionSection
            v-if="activePlugin.capabilities.length > 0"
            title="Fähigkeiten"
            storage-key="ao-plugin-capabilities"
          >
            <div class="plugin-detail__capabilities">
              <span
                v-for="cap in activePlugin.capabilities"
                :key="cap"
                class="plugin-detail__capability-chip"
              >
                {{ cap }}
              </span>
            </div>
          </AccordionSection>

          <!-- Execution History -->
          <AccordionSection
            title="Ausführungshistorie"
            storage-key="ao-plugin-history"
          >
            <template #header-extra>
              <History class="w-3.5 h-3.5" style="color: var(--color-text-muted)" />
            </template>
            <PluginExecutionHistory
              :executions="pluginsStore.executionHistory"
              :is-loading="pluginsStore.isLoading"
            />
          </AccordionSection>
        </div>
      </template>
    </SlideOver>

    <!-- Config Dialog -->
    <PluginConfigDialog
      v-if="activePlugin"
      :visible="showConfigDialog"
      :plugin-id="activePlugin.plugin_id"
      :plugin-name="activePlugin.display_name"
      :config="activePlugin.config"
      :config-schema="activePlugin.config_schema"
      @close="showConfigDialog = false"
      @save="handleSaveConfig"
    />
  </div>
</template>

<style scoped>
.plugins-view {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding: 1.25rem 1.5rem;
  height: 100%;
  overflow-y: auto;
}

.plugins-view__header {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.plugins-view__title-row {
  display: flex;
  align-items: center;
  gap: 0.625rem;
}

.plugins-view__title-icon {
  width: 22px;
  height: 22px;
  color: var(--color-iridescent-2);
}

.plugins-view__title {
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0;
}

.plugins-view__count {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  padding: 0.125rem 0.5rem;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
}

.plugins-view__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.plugins-view__filters {
  display: flex;
  gap: 0.375rem;
}

.plugins-view__filter-chip {
  padding: 0.375rem 0.75rem;
  font-size: var(--text-xs);
  font-weight: 500;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.plugins-view__filter-chip:hover {
  border-color: var(--color-iridescent-2);
  color: var(--color-text-primary);
}

.plugins-view__filter-chip--active {
  background: rgba(129, 140, 248, 0.1);
  border-color: var(--color-iridescent-2);
  color: var(--color-iridescent-2);
}

.plugins-view__refresh-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-1);
  min-height: 32px;
  padding: 0 var(--space-2);
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.plugins-view__refresh-btn:hover:not(:disabled) {
  border-color: var(--color-iridescent-2);
  color: var(--color-text-primary);
}

.plugins-view__refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.plugins-view__grid {
  gap: 1rem;
}

.plugins-view__ops-banner {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 0.875rem;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
}

.plugins-view__ops-label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
}

.plugins-view__ops-status {
  font-size: var(--text-xs);
  font-weight: 600;
  padding: 0.125rem 0.5rem;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
}

.plugins-view__ops-status--initiated,
.plugin-detail__lifecycle-badge--initiated {
  color: var(--color-info);
  border-color: color-mix(in srgb, var(--color-info) 35%, transparent);
}

.plugins-view__ops-status--running,
.plugin-detail__lifecycle-badge--running {
  color: var(--color-warning);
  border-color: color-mix(in srgb, var(--color-warning) 35%, transparent);
}

.plugins-view__ops-status--partial,
.plugin-detail__lifecycle-badge--partial {
  color: var(--color-warning);
  border-color: color-mix(in srgb, var(--color-warning) 35%, transparent);
}

.plugins-view__ops-status--success,
.plugin-detail__lifecycle-badge--success {
  color: var(--color-success);
  border-color: color-mix(in srgb, var(--color-success) 35%, transparent);
}

.plugins-view__ops-status--failed,
.plugin-detail__lifecycle-badge--failed {
  color: var(--color-error);
  border-color: color-mix(in srgb, var(--color-error) 35%, transparent);
}

.plugins-view__ops-text {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.plugins-view__ops-time {
  margin-left: auto;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.plugins-view__empty {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  padding: 3rem;
  color: var(--color-text-muted);
}

.plugins-view__empty-icon {
  width: 40px;
  height: 40px;
  opacity: 0.3;
}

/* Detail SlideOver Content */
.plugin-detail {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.plugin-detail__info {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.plugin-detail__status-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.plugin-detail__status-badge {
  font-size: var(--text-xs);
  font-weight: 600;
  padding: 0.125rem 0.5rem;
  border-radius: var(--radius-sm);
}

.plugin-detail__status-badge--enabled {
  background: rgba(52, 211, 153, 0.1);
  color: var(--color-success);
  border: 1px solid rgba(52, 211, 153, 0.2);
}

.plugin-detail__status-badge--disabled {
  background: rgba(248, 113, 113, 0.1);
  color: var(--color-error);
  border: 1px solid rgba(248, 113, 113, 0.2);
}

.plugin-detail__category {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.plugin-detail__description {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  line-height: 1.5;
  margin: 0;
}

.plugin-detail__actions {
  display: flex;
  gap: 0.5rem;
}

.plugin-detail__action-btn {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 0.875rem;
  font-size: var(--text-sm);
  font-weight: 500;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.plugin-detail__action-btn--execute {
  background: rgba(52, 211, 153, 0.08);
  color: var(--color-success);
  border-color: rgba(52, 211, 153, 0.2);
}

.plugin-detail__action-btn--execute:hover:not(:disabled) {
  background: rgba(52, 211, 153, 0.15);
}

.plugin-detail__action-btn--execute:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.plugin-detail__action-btn--config {
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
}

.plugin-detail__action-btn--config:hover {
  color: var(--color-text-primary);
  border-color: var(--color-iridescent-2);
}

.plugin-detail__capabilities {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  padding: 0.5rem 0;
}

.plugin-detail__capability-chip {
  font-size: var(--text-xs);
  padding: 0.25rem 0.5rem;
  background: rgba(129, 140, 248, 0.08);
  color: var(--color-iridescent-2);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(129, 140, 248, 0.15);
}

.plugin-detail__lifecycle-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.5rem 0;
}

.plugin-detail__lifecycle-item {
  display: flex;
  gap: 0.5rem;
  align-items: flex-start;
}

.plugin-detail__lifecycle-badge {
  font-size: var(--text-xs);
  padding: 0.125rem 0.5rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  white-space: nowrap;
}

.plugin-detail__lifecycle-body {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.plugin-detail__lifecycle-title {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.plugin-detail__lifecycle-meta {
  display: flex;
  gap: 0.5rem;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.plugin-detail__lifecycle-reason {
  font-size: var(--text-xs);
  color: var(--color-error);
}
</style>
