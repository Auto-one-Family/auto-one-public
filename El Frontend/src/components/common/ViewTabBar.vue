<script setup lang="ts">
/**
 * ViewTabBar — Shared Tab Navigation for Dashboards/Monitor/Editor
 *
 * A sticky tab bar displayed at the top of the content area on the main
 * views. Uses RouterLink for URL-based navigation so browser back/forward
 * works correctly.
 *
 * Active tab is determined by the current route name and path.
 * Viewer role sees only [Dashboards | Monitor].
 */
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { LayoutGrid, Activity, PenTool } from 'lucide-vue-next'
import { useAuthStore } from '@/shared/stores/auth.store'

const route = useRoute()
const authStore = useAuthStore()

const allTabs = [
  { key: 'dashboards', path: '/dashboards', label: 'Dashboards', icon: LayoutGrid },
  { key: 'monitor', path: '/monitor', label: 'Monitor', icon: Activity },
  { key: 'editor', path: '/editor', label: 'Editor', icon: PenTool },
] as const

const tabs = computed(() =>
  authStore.isViewer
    ? allTabs.filter(t => t.key !== 'editor')
    : allTabs
)

const activeTab = computed(() => {
  if (route.name === 'editor-dashboard') return 'editor'
  if (route.path.startsWith('/dashboards')) return 'dashboards'
  if (route.path.startsWith('/editor')) return 'editor'
  if (route.path.startsWith('/monitor')) return 'monitor'
  return 'dashboards'
})
</script>

<template>
  <nav class="view-tab-bar" aria-label="Hauptansichten">
    <RouterLink
      v-for="tab in tabs"
      :key="tab.key"
      :to="tab.path"
      :class="['view-tab-bar__tab', { 'view-tab-bar__tab--active': activeTab === tab.key }]"
    >
      <component :is="tab.icon" class="view-tab-bar__icon" />
      <span class="view-tab-bar__label">{{ tab.label }}</span>
    </RouterLink>
  </nav>
</template>

<style scoped>
.view-tab-bar {
  display: flex;
  gap: 2px;
  padding: 3px;
  background: var(--glass-bg-l1);
  -webkit-backdrop-filter: blur(var(--glass-blur-l1));
  backdrop-filter: blur(var(--glass-blur-l1));
  border: 1px solid var(--glass-border-l1);
  border-radius: var(--radius-md);
  box-shadow: var(--glass-shadow-l1);
  min-height: 41px;
  width: 100%;
  margin-bottom: var(--space-2);
}

.view-tab-bar__tab {
  display: flex;
  flex: 1 1 0;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-muted);
  text-decoration: none;
  transition: all var(--transition-fast);
  white-space: nowrap;
  position: relative;
}

.view-tab-bar__tab:hover {
  color: var(--color-text-secondary);
  background: var(--glass-bg-l2);
}

.view-tab-bar__tab--active {
  color: var(--color-text-primary);
  background: var(--color-bg-tertiary);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
}

.view-tab-bar__tab--active::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 50%;
  transform: translateX(-50%);
  width: 24px;
  height: 2px;
  background: var(--gradient-iridescent);
  border-radius: 1px;
  box-shadow: 0 0 8px var(--color-iridescent-glow-hover);
}

.view-tab-bar__tab--active .view-tab-bar__icon {
  color: var(--color-accent-bright);
}

.view-tab-bar__icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  transition: color var(--transition-fast);
}

.view-tab-bar__label {
  display: inline;
}

@media (max-width: 480px) {
  .view-tab-bar__tab {
    padding: var(--space-2) var(--space-2);
  }

  .view-tab-bar__label {
    display: none;
  }
}
</style>
