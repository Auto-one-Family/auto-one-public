<script setup lang="ts">
/**
 * TankEditModal — Nennwert + Frischwasser-EC/pH nachträglich ändern (AUT-1388).
 *
 * PATCH via tanksApi.updateTank / useTankStore.updateTank — kein neuer Endpoint.
 * Pattern: TankCreateModal (BaseModal + gleiche Feld-Semantik).
 * Scope: kein gemessener Frischwasser-Liter-Wert (→ AUT-1398 M-6).
 */

import { ref, watch } from 'vue'
import BaseModal from '@/shared/design/primitives/BaseModal.vue'
import { useToast } from '@/composables/useToast'
import { useTankStore } from '@/shared/stores/tank.store'
import { parseLocaleNumber } from '@/utils/parseLocaleNumber'
import type { Tank } from '@/types'

interface Props {
  open: boolean
  tank: Tank | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
  saved: [tank: Tank]
}>()

const tankStore = useTankStore()
const toast = useToast()

interface FormState {
  nominal_volume_l: string | number
  fresh_water_ec_us_cm: string | number
  fresh_water_ph: string | number
}

/** Parse optional ≥0 number from number-input v-model (string or number). */
function parseOptionalNumber(
  raw: string | number,
): { ok: true; value: number | null } | { ok: false } {
  if (raw === '') {
    return { ok: true, value: null }
  }
  const n = typeof raw === 'number' ? raw : parseLocaleNumber(String(raw))
  if (!Number.isFinite(n) || n < 0) {
    return { ok: false }
  }
  return { ok: true, value: n }
}

function formFromTank(tank: Tank): FormState {
  return {
    nominal_volume_l:
      typeof tank.nominal_volume_l === 'number' && Number.isFinite(tank.nominal_volume_l)
        ? tank.nominal_volume_l
        : '',
    fresh_water_ec_us_cm:
      typeof tank.fresh_water_ec_us_cm === 'number' &&
      Number.isFinite(tank.fresh_water_ec_us_cm)
        ? tank.fresh_water_ec_us_cm
        : '',
    fresh_water_ph:
      typeof tank.fresh_water_ph === 'number' && Number.isFinite(tank.fresh_water_ph)
        ? tank.fresh_water_ph
        : '',
  }
}

const form = ref<FormState>({
  nominal_volume_l: '',
  fresh_water_ec_us_cm: '',
  fresh_water_ph: '',
})
const isSubmitting = ref(false)
const errorMessage = ref<string | null>(null)

watch(
  () => [props.open, props.tank] as const,
  ([isOpen, tank]) => {
    if (isOpen && tank) {
      errorMessage.value = null
      form.value = formFromTank(tank)
    }
  },
)

async function handleSubmit(): Promise<void> {
  if (isSubmitting.value || !props.tank) return
  errorMessage.value = null

  const parsedVolume = parseOptionalNumber(form.value.nominal_volume_l)
  if (!parsedVolume.ok) {
    errorMessage.value = 'Nennwert muss eine Zahl ≥ 0 sein.'
    return
  }
  const parsedEc = parseOptionalNumber(form.value.fresh_water_ec_us_cm)
  if (!parsedEc.ok) {
    errorMessage.value = 'Frischwasser-EC muss eine Zahl ≥ 0 sein (µS/cm).'
    return
  }
  const parsedPh = parseOptionalNumber(form.value.fresh_water_ph)
  if (!parsedPh.ok) {
    errorMessage.value = 'Frischwasser-pH muss eine Zahl ≥ 0 sein.'
    return
  }
  if (parsedPh.value != null && parsedPh.value > 14) {
    errorMessage.value = 'Frischwasser-pH muss ≤ 14 sein.'
    return
  }

  isSubmitting.value = true
  try {
    const tank = await tankStore.updateTank(props.tank.id, {
      nominal_volume_l: parsedVolume.value,
      fresh_water_ec_us_cm: parsedEc.value,
      fresh_water_ph: parsedPh.value,
    })
    toast.success(`Tank „${tank.name}“ aktualisiert`)
    emit('saved', tank)
    emit('close')
  } catch (e) {
    errorMessage.value =
      e instanceof Error ? e.message : 'Tank konnte nicht aktualisiert werden'
  } finally {
    isSubmitting.value = false
  }
}

function handleClose(): void {
  if (!isSubmitting.value) emit('close')
}
</script>

<template>
  <BaseModal
    :open="props.open"
    title="Tank bearbeiten"
    max-width="max-w-lg"
    @close="handleClose"
  >
    <form
      v-if="props.tank"
      class="tank-form"
      aria-label="Nennwert und Frischwasser bearbeiten"
      @submit.prevent="handleSubmit"
    >
      <p class="tank-form__intro">
        <strong>{{ props.tank.name }}</strong>
        — Nennwert und Frischwasser-Kennwerte (eine Stelle). Leer =
        nicht konfiguriert. Der Ist-Füllstand (Anker ± Flow) wird hier nicht
        geändert.
      </p>

      <label class="tank-form__field">
        <span class="tank-form__label">Nennwert (L)</span>
        <input
          v-model="form.nominal_volume_l"
          type="number"
          min="0"
          step="any"
          class="tank-form__input"
          placeholder="nicht konfiguriert"
          aria-label="Nennwert in Litern"
        />
        <span class="tank-form__hint">
          Angenommene volle Tankgröße — nicht der gemessene Ist-Füllstand.
        </span>
      </label>

      <fieldset class="tank-form__fieldset">
        <legend class="tank-form__label">Frischwasser (Leitung)</legend>
        <p class="tank-form__hint">
          Kennwerte für den Assist (Verdünnung). Ohne Eintrag: nicht konfiguriert
          — kein stilles Hardcode.
        </p>
        <div class="tank-form__row">
          <label class="tank-form__field">
            <span class="tank-form__label">Frischwasser-EC (µS/cm)</span>
            <input
              v-model="form.fresh_water_ec_us_cm"
              type="text"
              inputmode="decimal"
              class="tank-form__input"
              placeholder="nicht konfiguriert"
              aria-label="Frischwasser-EC in Mikrosiemens pro Zentimeter"
            />
          </label>
          <label class="tank-form__field">
            <span class="tank-form__label">Frischwasser-pH</span>
            <input
              v-model="form.fresh_water_ph"
              type="text"
              inputmode="decimal"
              class="tank-form__input"
              placeholder="z. B. 5,9"
              aria-label="Frischwasser-pH"
            />
          </label>
        </div>
      </fieldset>

      <div v-if="errorMessage" class="tank-form__error" role="alert">
        {{ errorMessage }}
      </div>
    </form>

    <template #footer>
      <div class="tank-form__actions">
        <button
          type="button"
          class="plant-btn plant-btn--ghost"
          :disabled="isSubmitting"
          @click="handleClose"
        >
          Abbrechen
        </button>
        <button
          type="button"
          class="plant-btn plant-btn--primary"
          :disabled="isSubmitting || !props.tank"
          @click="handleSubmit"
        >
          {{ isSubmitting ? 'Wird gespeichert…' : 'Speichern' }}
        </button>
      </div>
    </template>
  </BaseModal>
</template>

<style scoped>
.tank-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.tank-form__intro {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  line-height: 1.45;
}

.tank-form__row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
}

.tank-form__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.tank-form__label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.tank-form__input {
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-family: inherit;
  outline: none;
  min-height: 38px;
}

.tank-form__input:focus {
  border-color: var(--color-accent);
}

.tank-form__hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  line-height: 1.4;
}

.tank-form__fieldset {
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-sm);
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
}

.tank-form__error {
  color: var(--color-danger);
  font-size: var(--text-sm);
}

.tank-form__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.plant-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  font-weight: 600;
  border: 1px solid transparent;
  cursor: pointer;
  min-height: 38px;
}

.plant-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.plant-btn--ghost {
  background: transparent;
  border-color: var(--glass-border);
  color: var(--color-text-secondary);
}

.plant-btn--primary {
  background: var(--color-accent);
  color: var(--color-text-on-accent, #fff);
}

@media (max-width: 375px) {
  .tank-form__row {
    grid-template-columns: 1fr;
  }
}
</style>
