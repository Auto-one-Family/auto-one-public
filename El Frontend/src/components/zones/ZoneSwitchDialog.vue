<script setup lang="ts">
/**
 * ZoneSwitchDialog — Modal for zone change strategy selection
 *
 * When an ESP changes zones, the user must decide what happens
 * to existing subzone assignments. Three strategies:
 * - transfer: Move subzones and assignments to new zone (recommended)
 * - reset: Clear subzones, ESP starts fresh in new zone
 * - copy: Duplicate subzones, originals remain in old zone
 */

import { ref } from 'vue'
import { ArrowRightLeft, RotateCcw, Copy } from 'lucide-vue-next'
import BaseModal from '@/shared/design/primitives/BaseModal.vue'

type SubzoneStrategy = 'transfer' | 'copy' | 'reset'

interface Props {
  isOpen: boolean
  deviceName: string
  currentZoneName: string
  targetZoneName: string
}

defineProps<Props>()

const emit = defineEmits<{
  close: []
  confirm: [strategy: SubzoneStrategy]
}>()

const selectedStrategy = ref<SubzoneStrategy>('transfer')

const strategies: Array<{
  value: SubzoneStrategy
  label: string
  description: string
  icon: typeof ArrowRightLeft
  recommended?: boolean
}> = [
  {
    value: 'transfer',
    label: 'Uebertragen',
    description: 'Subzonen und Zuordnungen in die neue Zone mitnehmen',
    icon: ArrowRightLeft,
    recommended: true,
  },
  {
    value: 'reset',
    label: 'Zuruecksetzen',
    description: 'ESP startet ohne Subzonen in der neuen Zone',
    icon: RotateCcw,
  },
  {
    value: 'copy',
    label: 'Kopieren',
    description: 'Subzonen kopieren, Originale bleiben in der alten Zone',
    icon: Copy,
  },
]

function handleConfirm() {
  emit('confirm', selectedStrategy.value)
}

function handleClose() {
  selectedStrategy.value = 'transfer'
  emit('close')
}
</script>

<template>
  <BaseModal
    :open="isOpen"
    title="Zone wechseln"
    max-width="max-w-md"
    @close="handleClose"
  >
    <div class="zone-switch">
      <!-- Context info -->
      <p class="zone-switch__context">
        <strong>{{ deviceName }}</strong> wechselt von
        <span class="zone-switch__zone-name">{{ currentZoneName }}</span>
        zu
        <span class="zone-switch__zone-name">{{ targetZoneName }}</span>
      </p>

      <p class="zone-switch__question">
        Was soll mit den Subzonen passieren?
      </p>

      <!-- Strategy radio group -->
      <div class="zone-switch__options" role="radiogroup" aria-label="Subzone-Strategie">
        <label
          v-for="s in strategies"
          :key="s.value"
          :class="[
            'zone-switch__option',
            { 'zone-switch__option--selected': selectedStrategy === s.value },
          ]"
        >
          <input
            v-model="selectedStrategy"
            type="radio"
            name="subzone-strategy"
            :value="s.value"
            class="zone-switch__radio"
          />
          <component :is="s.icon" class="zone-switch__option-icon" />
          <div class="zone-switch__option-text">
            <span class="zone-switch__option-label">
              {{ s.label }}
              <span v-if="s.recommended" class="zone-switch__recommended">empfohlen</span>
            </span>
            <span class="zone-switch__option-desc">{{ s.description }}</span>
          </div>
        </label>
      </div>
    </div>

    <template #footer>
      <div class="zone-switch__actions">
        <button
          class="zone-switch__btn zone-switch__btn--cancel"
          @click="handleClose"
        >
          Abbrechen
        </button>
        <button
          class="zone-switch__btn zone-switch__btn--confirm"
          @click="handleConfirm"
        >
          Zone wechseln
        </button>
      </div>
    </template>
  </BaseModal>
</template>

<style scoped>
.zone-switch {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.zone-switch__context {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  line-height: 1.5;
  margin: 0;
}

.zone-switch__zone-name {
  font-weight: 600;
  color: var(--color-iridescent-1);
}

.zone-switch__question {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-primary);
  margin: 0;
}

/* Radio group */
.zone-switch__options {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.zone-switch__option {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
  background: transparent;
}

.zone-switch__option:hover {
  border-color: var(--color-text-muted);
  background: rgba(255, 255, 255, 0.02);
}

.zone-switch__option--selected {
  border-color: var(--color-iridescent-1);
  background: rgba(96, 165, 250, 0.06);
}

.zone-switch__option--selected:hover {
  border-color: var(--color-iridescent-1);
}

.zone-switch__radio {
  appearance: none;
  width: 16px;
  height: 16px;
  border: 2px solid var(--color-text-muted);
  border-radius: var(--radius-full);
  flex-shrink: 0;
  margin-top: 2px;
  transition: all var(--transition-fast);
  position: relative;
}

.zone-switch__radio:checked {
  border-color: var(--color-iridescent-1);
}

.zone-switch__radio:checked::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  background: var(--color-iridescent-1);
}

.zone-switch__option-icon {
  width: 16px;
  height: 16px;
  color: var(--color-text-muted);
  flex-shrink: 0;
  margin-top: 2px;
}

.zone-switch__option--selected .zone-switch__option-icon {
  color: var(--color-iridescent-1);
}

.zone-switch__option-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.zone-switch__option-label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.zone-switch__recommended {
  font-size: var(--text-xxs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-success);
  background: rgba(52, 211, 153, 0.1);
  padding: 1px var(--space-2);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(52, 211, 153, 0.2);
}

.zone-switch__option-desc {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  line-height: 1.4;
}

/* Footer actions */
.zone-switch__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
}

.zone-switch__btn {
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  min-height: 40px;
  border: none;
}

.zone-switch__btn--cancel {
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  border: 1px solid var(--glass-border);
}

.zone-switch__btn--cancel:hover {
  background-color: var(--color-bg-quaternary);
  color: var(--color-text-primary);
}

.zone-switch__btn--confirm {
  background-color: var(--color-iridescent-1);
  color: var(--color-text-inverse);
}

.zone-switch__btn--confirm:hover {
  background-color: var(--color-accent-bright);
}

.zone-switch__btn:focus-visible {
  outline: 2px solid var(--color-iridescent-2);
  outline-offset: 2px;
}
</style>
