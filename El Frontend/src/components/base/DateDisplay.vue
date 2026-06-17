<script setup lang="ts">
import { computed } from 'vue'
import { formatRelativeTime, formatDateTime } from '@/utils/formatters'

interface Props {
  date: string | Date | null | undefined
  format?: 'relative' | 'absolute'
}

const props = withDefaults(defineProps<Props>(), {
  format: 'relative',
})

const absoluteText = computed(() => formatDateTime(props.date))
const relativeText = computed(() => formatRelativeTime(props.date))
const displayText = computed(() =>
  props.format === 'absolute' ? absoluteText.value : relativeText.value,
)
const tooltipText = computed(() =>
  props.format === 'relative' ? absoluteText.value : undefined,
)
</script>

<template>
  <time class="date-display" :title="tooltipText">{{ displayText }}</time>
</template>

<style scoped>
.date-display {
  font-variant-numeric: tabular-nums;
}
</style>
