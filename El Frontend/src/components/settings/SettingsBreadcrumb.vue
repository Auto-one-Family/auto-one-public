<script setup lang="ts">
/**
 * SettingsBreadcrumb — Context path for settings panels
 *
 * Displays the hierarchical path Zone -> Subzone -> ESP -> GPIO
 * as a non-intrusive breadcrumb at the top of settings panels.
 *
 * Zone and Subzone are clickable (emit events). ESP and GPIO are
 * read-only context indicators.
 *
 * Used in SensorConfigPanel and ActuatorConfigPanel to make the
 * Zone vs. Subzone hierarchy visible without offering misleading
 * inline edit controls.
 */

interface Props {
  zone?: string | null
  subzone?: string | null
  espId?: string | null
  gpio?: number | null
}

defineProps<Props>()

const emit = defineEmits<{
  (e: 'zone-click'): void
  (e: 'subzone-click'): void
}>()
</script>

<template>
  <nav class="settings-breadcrumb" aria-label="Kontextpfad">
    <span
      v-if="zone"
      class="settings-breadcrumb__segment settings-breadcrumb__segment--clickable"
      @click="emit('zone-click')"
    >
      {{ zone }}
    </span>
    <span v-if="zone && subzone" class="settings-breadcrumb__sep">›</span>
    <span
      v-if="subzone"
      class="settings-breadcrumb__segment settings-breadcrumb__segment--clickable"
      @click="emit('subzone-click')"
    >
      {{ subzone }}
    </span>
    <span v-if="(zone || subzone) && espId" class="settings-breadcrumb__sep">›</span>
    <span v-if="espId" class="settings-breadcrumb__segment">{{ espId }}</span>
    <span v-if="espId && gpio != null" class="settings-breadcrumb__sep">›</span>
    <span v-if="gpio != null" class="settings-breadcrumb__segment">GPIO {{ gpio }}</span>
  </nav>
</template>

<style scoped>
.settings-breadcrumb {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-1);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin-bottom: var(--space-2);
}

.settings-breadcrumb__segment {
  color: var(--color-text-secondary);
}

.settings-breadcrumb__segment--clickable {
  cursor: pointer;
  color: var(--color-accent-bright);
  text-decoration: underline;
  text-decoration-style: dotted;
}

.settings-breadcrumb__segment--clickable:hover {
  color: var(--color-text-primary);
}

.settings-breadcrumb__sep {
  opacity: 0.4;
  font-size: var(--text-xxs);
}
</style>
