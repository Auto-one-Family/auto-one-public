<script setup lang="ts">
/**
 * QuickActionMenu — Expanding panel shown when the FAB is clicked.
 *
 * Renders context-specific actions. Glassmorphism styling consistent
 * with design tokens.
 */

import { computed } from 'vue'
import { useQuickActionStore } from '@/shared/stores/quickAction.store'
import QuickActionItem from './QuickActionItem.vue'
import { useEspStore } from '@/stores/esp'

const store = useQuickActionStore()
const espStore = useEspStore()

const contextActions = computed(() => store.contextActions)
const hasContextActions = computed(() => contextActions.value.length > 0)

function handleAction(actionId: string) {
  store.executeAction(actionId)
}
</script>

<template>
  <div class="qa-menu" role="menu" aria-label="Quick Actions">
    <div v-if="hasContextActions" class="qa-menu__section">
      <QuickActionItem
        v-for="action in contextActions"
        :key="action.id"
        :icon="action.icon"
        :label="action.label"
        :badge="action.id === 'hw-pending-devices'
          ? (espStore.pendingCount > 0 ? espStore.pendingCount : undefined)
          : action.badge"
        :badge-variant="action.id === 'hw-pending-devices' && espStore.pendingCount > 0
          ? 'info'
          : action.badgeVariant"
        :shortcut-hint="action.shortcutHint"
        :disabled="action.disabled"
        :data-testid="`quick-action-item-${action.id}`"
        role="menuitem"
        @click="handleAction(action.id)"
      />
    </div>
  </div>
</template>

<style scoped>
.qa-menu {
  position: absolute;
  bottom: calc(100% + var(--space-2));
  right: 0;
  min-width: 240px;
  max-width: 300px;
  padding: var(--space-2);
  border-radius: var(--radius-md);
  background: rgba(20, 20, 30, 0.85);
  -webkit-backdrop-filter: blur(16px);
  backdrop-filter: blur(16px);
  border: 1px solid var(--glass-border);
  box-shadow: var(--elevation-floating);
  transform-origin: bottom right;
}

.qa-menu__section {
  display: flex;
  flex-direction: column;
}
</style>
