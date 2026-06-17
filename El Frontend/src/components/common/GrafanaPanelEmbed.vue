<script setup lang="ts">
/**
 * GrafanaPanelEmbed
 *
 * Embeds a single Grafana panel via iframe.
 * Handles loading state, error fallback, and dark theme matching.
 *
 * Prerequisites (docker-compose.yml grafana service):
 *   GF_SECURITY_ALLOW_EMBEDDING=true
 *   GF_AUTH_ANONYMOUS_ENABLED=true
 *   GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer
 */

import { ref, computed, onMounted } from 'vue'
import { BarChart3, ExternalLink } from 'lucide-vue-next'
import {
  useGrafana,
  GRAFANA_DASHBOARDS,
  type GrafanaPanelOptions,
} from '@/composables/useGrafana'

interface Props {
  /** Dashboard UID (default: system-health) */
  dashboardUid?: string
  /** Panel ID within the dashboard */
  panelId: number
  /** Panel title for display */
  title?: string
  /** Height of the embed area */
  height?: string
  /** Time range start (Grafana syntax) */
  from?: string
  /** Time range end */
  to?: string
  /** Auto-refresh interval */
  refresh?: string
}

const props = withDefaults(defineProps<Props>(), {
  dashboardUid: GRAFANA_DASHBOARDS.SYSTEM_HEALTH,
  title: '',
  height: '200px',
  from: 'now-1h',
  to: 'now',
  refresh: '30s',
})

const panelOptions = computed<GrafanaPanelOptions>(() => ({
  dashboardUid: props.dashboardUid,
  panelId: props.panelId,
  from: props.from,
  to: props.to,
  refresh: props.refresh,
  theme: 'dark',
}))

const { panelUrl, GRAFANA_BASE_URL } = useGrafana(panelOptions)

const isLoading = ref(true)
const hasError = ref(false)

function onIframeLoad() {
  isLoading.value = false
}

function onIframeError() {
  isLoading.value = false
  hasError.value = true
}

/** Open full Grafana dashboard in new tab */
function openInGrafana() {
  const url = `${GRAFANA_BASE_URL}/d/${props.dashboardUid}?viewPanel=${props.panelId}&from=${props.from}&to=${props.to}`
  window.open(url, '_blank')
}

// Check if Grafana is reachable
onMounted(async () => {
  try {
    await fetch(`${GRAFANA_BASE_URL}/api/health`, {
      mode: 'no-cors',
      signal: AbortSignal.timeout(3000),
    })
    // no-cors gives opaque response, but if fetch doesn't throw, the server is reachable
    hasError.value = false
  } catch {
    hasError.value = true
    isLoading.value = false
  }
})
</script>

<template>
  <div class="grafana-embed" :style="{ '--embed-height': height }">
    <!-- Header (optional title + external link) -->
    <div v-if="title || !hasError" class="grafana-embed__header">
      <div class="grafana-embed__title">
        <BarChart3 class="w-3.5 h-3.5" />
        <span v-if="title">{{ title }}</span>
      </div>
      <button
        v-if="!hasError"
        class="grafana-embed__external"
        title="In Grafana öffnen"
        @click="openInGrafana"
      >
        <ExternalLink class="w-3.5 h-3.5" />
      </button>
    </div>

    <!-- Loading skeleton -->
    <div v-if="isLoading && !hasError" class="grafana-embed__loading">
      <div class="grafana-embed__skeleton" />
    </div>

    <!-- Error fallback -->
    <div v-if="hasError" class="grafana-embed__error">
      <BarChart3 class="w-8 h-8" />
      <p>Grafana nicht erreichbar</p>
      <p class="grafana-embed__error-hint">
        Monitoring-Stack starten: <code>docker compose --profile monitoring up -d</code>
      </p>
    </div>

    <!-- Iframe -->
    <iframe
      v-if="!hasError"
      :src="panelUrl"
      class="grafana-embed__iframe"
      frameborder="0"
      :style="{ opacity: isLoading ? 0 : 1 }"
      @load="onIframeLoad"
      @error="onIframeError"
    />
  </div>
</template>

<style scoped>
.grafana-embed {
  display: flex;
  flex-direction: column;
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.grafana-embed__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--glass-border);
}

.grafana-embed__title {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--color-text-secondary);
}

.grafana-embed__external {
  padding: 0.25rem;
  background: none;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
}

.grafana-embed__external:hover {
  color: var(--color-iridescent-1);
  background: var(--color-bg-tertiary);
}

.grafana-embed__loading {
  height: var(--embed-height);
  padding: 1rem;
}

.grafana-embed__skeleton {
  width: 100%;
  height: 100%;
  background: linear-gradient(
    90deg,
    var(--color-bg-tertiary) 25%,
    var(--color-bg-secondary) 50%,
    var(--color-bg-tertiary) 75%
  );
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.5s ease-in-out infinite;
  border-radius: var(--radius-sm);
}

@keyframes skeleton-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.grafana-embed__error {
  height: var(--embed-height);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  color: var(--color-text-muted);
  font-size: 0.8125rem;
}

.grafana-embed__error-hint {
  font-size: 0.6875rem;
  opacity: 0.7;
}

.grafana-embed__error-hint code {
  padding: 0.125rem 0.375rem;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  font-size: 0.625rem;
}

.grafana-embed__iframe {
  width: 100%;
  height: var(--embed-height);
  border: none;
  transition: opacity 0.3s ease;
}
</style>
