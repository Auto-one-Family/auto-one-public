<script setup lang="ts">
/**
 * WidgetWrapper — Container for Dashboard Widgets
 *
 * Provides a consistent header (title, config, remove) and body
 * for any dashboard widget type. The body slot renders the actual
 * widget component (chart, sensor card, etc.)
 */
import { ref } from 'vue'
import { Settings2, X } from 'lucide-vue-next'

interface Props {
  title: string
  widgetId: string
  showConfig?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showConfig: false,
})

const emit = defineEmits<{
  remove: [widgetId: string]
  configure: [widgetId: string]
}>()

const showConfigPanel = ref(false)

function toggleConfig() {
  showConfigPanel.value = !showConfigPanel.value
  if (showConfigPanel.value) {
    emit('configure', props.widgetId)
  }
}
</script>

<template>
  <div class="widget-wrapper">
    <div class="widget-wrapper__header gs-drag-handle">
      <span class="widget-wrapper__title">{{ title }}</span>
      <div class="widget-wrapper__actions">
        <button
          v-if="showConfig"
          class="widget-wrapper__btn"
          title="Konfigurieren"
          @click.stop="toggleConfig"
        >
          <Settings2 class="w-3.5 h-3.5" />
        </button>
        <button
          class="widget-wrapper__btn widget-wrapper__btn--remove"
          title="Widget entfernen"
          @click.stop="emit('remove', widgetId)"
        >
          <X class="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
    <div class="widget-wrapper__body">
      <slot />
    </div>
    <div v-if="showConfigPanel" class="widget-wrapper__config">
      <slot name="config" />
    </div>
  </div>
</template>

<style scoped>
.widget-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.widget-wrapper__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--glass-border);
  cursor: move;
  flex-shrink: 0;
}

.widget-wrapper__title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.widget-wrapper__actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}

.widget-wrapper__btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.widget-wrapper__btn:hover {
  color: var(--color-text-secondary);
  background: var(--color-bg-quaternary);
}

.widget-wrapper__btn--remove:hover {
  color: var(--color-error);
}

.widget-wrapper__body {
  flex: 1;
  padding: var(--space-2);
  min-height: 0;
  overflow: hidden;
}

.widget-wrapper__config {
  padding: var(--space-2) var(--space-3);
  border-top: 1px solid var(--glass-border);
  background: var(--color-bg-quaternary);
  flex-shrink: 0;
}
</style>
