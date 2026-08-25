<script setup lang="ts">
import type { LogicRule } from '@/types/logic'

interface Props {
  rule: LogicRule
  isSelected?: boolean
  isActive?: boolean
  executionCount?: number
}

const props = withDefaults(defineProps<Props>(), {
  isSelected: false,
  isActive: false,
  executionCount: 0,
})

const emit = defineEmits<{
  select: [ruleId: string]
  toggle: [ruleId: string, enabled: boolean]
  delete: [ruleId: string]
}>()

function sensorLabel(): string {
  const condition = props.rule.conditions?.[0] as {
    type?: string
    sensor_type?: string
    operator?: string
    value?: number
    start_hour?: number
    end_hour?: number
  } | undefined
  if (!condition) return ''
  if (condition.type === 'time_window') return 'Zeit'
  if (condition.sensor_type) {
    return `${condition.sensor_type} ${condition.operator ?? ''} ${condition.value ?? ''}`.trim()
  }
  return ''
}

function actionLabel(): string {
  const action = props.rule.actions?.[0] as { type?: string; command?: string } | undefined
  if (!action) return ''
  if (action.type === 'notification') return 'Benachrichtigung'
  return action.command ?? ''
}

function onCardClick(): void {
  emit('select', props.rule.id)
}

function onToggle(event: Event): void {
  event.stopPropagation()
  emit('toggle', props.rule.id, !props.rule.enabled)
}

function onDelete(event: Event): void {
  event.stopPropagation()
  emit('delete', props.rule.id)
}
</script>

<template>
  <article
    class="rule-card"
    :class="{
      'rule-card--selected': isSelected,
      'rule-card--disabled': !rule.enabled,
      'rule-card--active': isActive,
    }"
    @click="onCardClick"
  >
    <button
      type="button"
      class="rule-card__status-dot"
      :class="rule.enabled ? 'rule-card__status-dot--on' : 'rule-card__status-dot--off'"
      @click="onToggle"
    />
    <div class="rule-card__name">{{ rule.name }}</div>
    <div class="rule-card__flow">
      <span class="rule-card__badge">{{ sensorLabel() }}</span>
      <span class="rule-card__arrow">→</span>
      <span class="rule-card__badge">{{ rule.logic_operator }}</span>
      <span class="rule-card__arrow">→</span>
      <span class="rule-card__badge">{{ actionLabel() }}</span>
    </div>
    <div class="rule-card__meta">
      <span v-if="executionCount > 0">{{ executionCount }}x/24h</span>
      <span>{{ rule.last_triggered ? 'Zuletzt' : 'Noch nie' }}</span>
    </div>
    <button type="button" class="rule-card__delete" @click="onDelete">Löschen</button>
  </article>
</template>
