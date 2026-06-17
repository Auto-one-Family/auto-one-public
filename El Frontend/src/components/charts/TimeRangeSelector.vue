<script setup lang="ts">
/**
 * TimeRangeSelector Component
 *
 * Quick presets (1h, 6h, 24h, 7d) plus custom date-time range.
 */

import { ref, computed } from 'vue'

export type TimePreset = '1h' | '6h' | '12h' | '24h' | '7d' | 'custom'

interface Props {
  modelValue?: TimePreset
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '24h',
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: TimePreset): void
  (e: 'range-change', payload: { start: string; end: string }): void
}>()

const presets: { key: TimePreset; label: string; ms: number }[] = [
  { key: '1h', label: '1 Std', ms: 60 * 60 * 1000 },
  { key: '6h', label: '6 Std', ms: 6 * 60 * 60 * 1000 },
  { key: '12h', label: '12 Std', ms: 12 * 60 * 60 * 1000 },
  { key: '24h', label: '24 Std', ms: 24 * 60 * 60 * 1000 },
  { key: '7d', label: '7 Tage', ms: 7 * 24 * 60 * 60 * 1000 },
]

const showCustom = ref(false)
const customStart = ref('')
const customEnd = ref('')

const activePreset = computed(() => props.modelValue)

function selectPreset(preset: (typeof presets)[number]) {
  showCustom.value = false
  emit('update:modelValue', preset.key)

  const end = new Date()
  const start = new Date(end.getTime() - preset.ms)
  emit('range-change', {
    start: start.toISOString(),
    end: end.toISOString(),
  })
}

function toggleCustom() {
  showCustom.value = !showCustom.value
  if (showCustom.value) {
    emit('update:modelValue', 'custom')
    const now = new Date()
    const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000)
    customStart.value = yesterday.toISOString().slice(0, 16)
    customEnd.value = now.toISOString().slice(0, 16)
  }
}

function applyCustom() {
  if (!customStart.value || !customEnd.value) return
  emit('range-change', {
    start: new Date(customStart.value).toISOString(),
    end: new Date(customEnd.value).toISOString(),
  })
}
</script>

<template>
  <div class="time-range-selector">
    <div class="time-range-selector__presets">
      <button
        v-for="preset in presets"
        :key="preset.key"
        class="time-range-selector__btn"
        :class="{ 'time-range-selector__btn--active': activePreset === preset.key && !showCustom }"
        @click="selectPreset(preset)"
      >
        {{ preset.label }}
      </button>
      <button
        class="time-range-selector__btn"
        :class="{ 'time-range-selector__btn--active': showCustom }"
        @click="toggleCustom"
      >
        Benutzerdefiniert
      </button>
    </div>

    <div v-if="showCustom" class="time-range-selector__custom">
      <div class="time-range-selector__field">
        <label class="time-range-selector__label">Von</label>
        <input
          v-model="customStart"
          type="datetime-local"
          class="time-range-selector__input"
        />
      </div>
      <div class="time-range-selector__field">
        <label class="time-range-selector__label">Bis</label>
        <input
          v-model="customEnd"
          type="datetime-local"
          class="time-range-selector__input"
        />
      </div>
      <button class="time-range-selector__apply" @click="applyCustom">
        Anwenden
      </button>
    </div>
  </div>
</template>

<style scoped>
.time-range-selector {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.time-range-selector__presets {
  display: flex;
  gap: 0.375rem;
  flex-wrap: wrap;
}

.time-range-selector__btn {
  padding: 0.375rem 0.75rem;
  font-size: 0.75rem;
  font-weight: 500;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  background: var(--color-bg-secondary);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.15s;
}

.time-range-selector__btn:hover {
  border-color: var(--color-iridescent-1);
  color: var(--color-text-primary);
}

.time-range-selector__btn--active {
  border-color: var(--color-iridescent-1);
  background: rgba(167,139,250,0.12);
  color: var(--color-iridescent-1);
}

.time-range-selector__custom {
  display: flex;
  align-items: flex-end;
  gap: 0.625rem;
  flex-wrap: wrap;
}

.time-range-selector__field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.time-range-selector__label {
  font-size: 0.6875rem;
  color: var(--color-text-muted);
}

.time-range-selector__input {
  padding: 0.375rem 0.5rem;
  font-size: 0.75rem;
  font-family: 'JetBrains Mono', monospace;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
  outline: none;
  color-scheme: dark;
}

.time-range-selector__input:focus {
  border-color: var(--color-iridescent-1);
}

.time-range-selector__apply {
  padding: 0.375rem 0.875rem;
  font-size: 0.75rem;
  font-weight: 600;
  border-radius: var(--radius-sm);
  border: none;
  background: var(--color-iridescent-1);
  color: var(--color-text-inverse);
  cursor: pointer;
  transition: all 0.15s;
}

.time-range-selector__apply:hover {
  filter: brightness(1.1);
}
</style>
