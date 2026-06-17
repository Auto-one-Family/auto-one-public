<script setup lang="ts">
/**
 * DashboardsView — Standalone Dashboard List (/dashboards)
 *
 * Shows all dashboards with target.view='dashboards' (or no target) as live
 * panels via InlineDashboardPanel mode='manage'. Replaces the AUT-834 interim
 * card-link stand (7fc97aca).
 * TODO AUT-833: nach Done auf /dashboards/:id-Routing umverdrahten.
 */
import { LayoutGrid } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import ViewTabBar from '@/components/common/ViewTabBar.vue'
import InlineDashboardPanel from '@/components/dashboard/InlineDashboardPanel.vue'
import { useDashboardStore } from '@/shared/stores/dashboard.store'

const router = useRouter()
const dashStore = useDashboardStore()
</script>

<template>
  <div class="dashboards-view">
    <ViewTabBar />

    <div class="dashboards-view__content">
      <!-- Live dashboard panels -->
      <template v-if="dashStore.dashboardsTabLayouts.length > 0">
        <div
          v-for="layout in dashStore.dashboardsTabLayouts"
          :key="layout.id"
          class="dashboards-view__panel-wrapper"
        >
          <!-- InlineDashboardPanel renders only when widgets.length > 0 (own guard line 277) -->
          <InlineDashboardPanel :layout-id="layout.id" mode="manage" />
          <!-- Fallback for configured dashboards without widgets yet -->
          <div v-if="layout.widgets.length === 0" class="dashboards-view__no-widgets">
            <span class="dashboards-view__no-widgets-name">{{ layout.name }}</span>
            <p class="dashboards-view__no-widgets-text">Noch keine Widgets — im Editor hinzufügen.</p>
            <button class="dashboards-view__cta" @click="router.push(`/editor/${layout.id}`)">
              Im Editor öffnen
            </button>
          </div>
        </div>
      </template>

      <!-- Empty state -->
      <div v-else class="dashboards-view__empty">
        <LayoutGrid class="dashboards-view__empty-icon" />
        <p class="dashboards-view__empty-text">Noch keine Dashboards vorhanden.</p>
        <button class="dashboards-view__cta" @click="router.push('/editor')">
          Im Editor erstellen
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboards-view { display: flex; flex-direction: column; height: 100%; padding: var(--space-4); gap: var(--space-4); }
.dashboards-view__content { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: var(--space-6); }
.dashboards-view__panel-wrapper { display: flex; flex-direction: column; }
.dashboards-view__no-widgets { display: flex; flex-direction: column; align-items: flex-start; gap: var(--space-2); padding: var(--space-4); background: var(--color-bg-secondary); border: 1px solid var(--glass-border-l1); border-radius: var(--radius-md); }
.dashboards-view__no-widgets-name { font-size: var(--text-sm); font-weight: 500; color: var(--color-text-primary); }
.dashboards-view__no-widgets-text { font-size: var(--text-sm); color: var(--color-text-muted); }
.dashboards-view__empty { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--space-4); min-height: 300px; color: var(--color-text-muted); }
.dashboards-view__empty-icon { width: 48px; height: 48px; opacity: 0.3; }
.dashboards-view__empty-text { font-size: var(--text-base); }
.dashboards-view__cta { padding: var(--space-2) var(--space-6); background: var(--color-accent); color: var(--color-text-primary); border-radius: var(--radius-sm); font-size: var(--text-sm); font-weight: 500; cursor: pointer; transition: opacity var(--transition-fast); }
.dashboards-view__cta:hover { opacity: 0.85; }
</style>
