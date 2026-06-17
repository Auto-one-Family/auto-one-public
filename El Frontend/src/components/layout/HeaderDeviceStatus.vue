<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useDashboardStore } from '@/shared/stores/dashboard.store'
import { useAlertCenterStore } from '@/shared/stores'

const router = useRouter()
const dashStore = useDashboardStore()
const alertStore = useAlertCenterStore()

const onlineCount = computed(() => dashStore.statusCounts.online)
const offlineCount = computed(() => dashStore.statusCounts.offline)
const alarmCount = computed(() => alertStore.alertStats?.active_count ?? 0)

function navigateAndFilter(statusKey: 'online' | 'offline') {
  router.push('/hardware')
  dashStore.resetFilters()
  dashStore.toggleStatusFilter(statusKey)
}
</script>

<template>
  <div class="hds" aria-label="Gerätestatus">
    <button
      class="hds__chip hds__chip--online"
      :title="`${onlineCount} Geräte online — in Hardware filtern`"
      @click="navigateAndFilter('online')"
    >
      <span class="hds__dot hds__dot--online" aria-hidden="true" />
      <span class="hds__label">{{ onlineCount }} Online</span>
    </button>

    <button
      class="hds__chip hds__chip--offline"
      :title="`${offlineCount} Geräte offline — in Hardware filtern`"
      @click="navigateAndFilter('offline')"
    >
      <span class="hds__dot hds__dot--offline" aria-hidden="true" />
      <span class="hds__label">{{ offlineCount }} Offline</span>
    </button>

    <span
      v-if="alarmCount > 0"
      class="hds__chip hds__chip--alarm"
      :title="`${alarmCount} aktive Alarme`"
    >
      <span class="hds__label" aria-hidden="true">&#9888;</span>
      <span class="hds__label">{{ alarmCount }}</span>
    </span>

  </div>
</template>

<style scoped>
.hds {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  flex-shrink: 0;
}

.hds__chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px var(--space-2);
  border-radius: var(--radius-full);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  font-size: var(--text-xs);
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
  transition: background var(--transition-fast), border-color var(--transition-fast);
}

.hds__chip:hover {
  background: var(--color-bg-tertiary);
  border-color: var(--glass-border-hover);
}

.hds__chip--online {
  color: var(--color-success);
}

.hds__chip--offline {
  color: var(--color-text-muted);
}

.hds__chip--alarm {
  color: var(--color-error);
  background: rgba(248, 113, 113, 0.08);
  border-color: rgba(248, 113, 113, 0.25);
  cursor: default;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.hds__dot {
  width: 6px;
  height: 6px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
}

.hds__dot--online {
  background-color: var(--color-success);
  box-shadow: 0 0 4px var(--color-success);
}

.hds__dot--offline {
  background-color: var(--color-text-muted);
}

.hds__label {
  font-variant-numeric: tabular-nums;
}

@media (max-width: 767px) {
  .hds {
    gap: var(--space-1);
  }
}

@media (max-width: 1366px), (max-height: 820px) {
  .hds__chip {
    background: var(--color-bg-tertiary);
    border-color: var(--glass-border-hover);
    box-shadow: none;
  }
}
</style>
