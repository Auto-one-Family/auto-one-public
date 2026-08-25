<script setup lang="ts">
/**
 * TankCreateModal — Tank anlegen (AUT-1215)
 *
 * POST /v1/tanks (+ optional POST /v1/tanks/{id}/subzones).
 * Pattern: PlantCreateModal (BaseModal + zone select).
 */

import { computed, ref, watch } from 'vue'
import BaseModal from '@/shared/design/primitives/BaseModal.vue'
import { useToast } from '@/composables/useToast'
import { useTankStore } from '@/shared/stores/tank.store'
import { useZoneStore } from '@/shared/stores/zone.store'
import { usePlantsStore } from '@/shared/stores/plants.store'
import { parseLocaleNumber } from '@/utils/parseLocaleNumber'
import type { TankOperationMode } from '@/types'
import { TANK_OPERATION_MODES } from '@/types'
import { TANK_OPERATION_MODE_LABELS } from '@/components/plants/tankLabels'

interface Props {
  open: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
  created: [tankId: string]
}>()

const tankStore = useTankStore()
const zoneStore = useZoneStore()
const plantsStore = usePlantsStore()
const toast = useToast()

interface FormState {
  zone_id: string
  name: string
  operation_mode: TankOperationMode
  /**
   * Optional volume. Typed as string|number because `<input type="number">`
   * + v-model can yield a number at runtime (not only string).
   */
  nominal_volume_l: string | number
  /** AUT-1381: Frischwasser-EC (µS/cm); leer = nicht konfiguriert */
  fresh_water_ec_us_cm: string | number
  fresh_water_ph: string | number
  /** Optional subzone_config UUIDs (from plants in zone). */
  subzone_config_ids: string[]
}

/** Parse optional ≥0 number from number-input v-model (string or number). */
function parseOptionalVolumeL(
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

function emptyForm(): FormState {
  return {
    zone_id: '',
    name: '',
    operation_mode: 'drain_to_waste',
    nominal_volume_l: '',
    fresh_water_ec_us_cm: '',
    fresh_water_ph: '',
    subzone_config_ids: [],
  }
}

const form = ref<FormState>(emptyForm())
const isSubmitting = ref(false)
const errorMessage = ref<string | null>(null)

const availableZones = computed(() => zoneStore.activeZones)

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * Subzone options: plant.subzone_id is the subzone_configs UUID required by
 * TankSubzoneAssignRequest. Device.subzones only expose string slugs, so we
 * collect UUIDs from the plant inventory and label them with plant names.
 */
const availableSubzones = computed(() => {
  const byId = new Map<string, string[]>()
  for (const plant of plantsStore.plants) {
    const sid = plant.subzone_id
    if (!sid || !UUID_RE.test(sid)) continue
    if (plant.parent_zone_id && form.value.zone_id && plant.parent_zone_id !== form.value.zone_id) {
      continue
    }
    const labels = byId.get(sid) ?? []
    labels.push(plant.genotype_label || plant.qr_code || plant.plant_id.slice(0, 8))
    byId.set(sid, labels)
  }
  return Array.from(byId.entries())
    .map(([id, labels]) => ({
      id,
      name: `${labels.slice(0, 3).join(', ')}${labels.length > 3 ? '…' : ''} (${id.slice(0, 8)}…)`,
    }))
    .sort((a, b) => a.name.localeCompare(b.name))
})

watch(
  () => form.value.zone_id,
  () => {
    form.value.subzone_config_ids = []
  },
)

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      errorMessage.value = null
      form.value = emptyForm()
      if (zoneStore.zoneEntities.length === 0 && !zoneStore.isLoadingZones) {
        void zoneStore.fetchZoneEntities()
      }
      if (plantsStore.plants.length === 0 && !plantsStore.isLoading) {
        void plantsStore.fetchPlants()
      }
    }
  },
)

function toggleSubzone(id: string): void {
  const list = form.value.subzone_config_ids
  const idx = list.indexOf(id)
  if (idx >= 0) {
    form.value.subzone_config_ids = list.filter((x) => x !== id)
  } else {
    form.value.subzone_config_ids = [...list, id]
  }
}

async function handleSubmit(): Promise<void> {
  if (isSubmitting.value) return
  errorMessage.value = null

  const name = form.value.name.trim()
  if (!form.value.zone_id) {
    errorMessage.value = 'Bitte eine Zone wählen.'
    return
  }
  if (!name) {
    errorMessage.value = 'Bitte einen Tank-Namen eingeben.'
    return
  }

  const parsedVolume = parseOptionalVolumeL(form.value.nominal_volume_l)
  if (!parsedVolume.ok) {
    errorMessage.value = 'Nennvolumen muss eine Zahl ≥ 0 sein.'
    return
  }
  const nominal = parsedVolume.value
  const parsedEc = parseOptionalVolumeL(form.value.fresh_water_ec_us_cm)
  if (!parsedEc.ok) {
    errorMessage.value = 'Frischwasser-EC muss eine Zahl ≥ 0 sein (µS/cm).'
    return
  }
  const parsedPh = parseOptionalVolumeL(form.value.fresh_water_ph)
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
    const tank = await tankStore.createTank({
      zone_id: form.value.zone_id,
      name,
      operation_mode: form.value.operation_mode,
      nominal_volume_l: nominal,
      fresh_water_ec_us_cm: parsedEc.value,
      fresh_water_ph: parsedPh.value,
    })

    if (form.value.subzone_config_ids.length > 0) {
      try {
        await tankStore.assignSubzones(tank.id, form.value.subzone_config_ids)
      } catch (assignErr) {
        toast.error(
          assignErr instanceof Error
            ? `Tank angelegt, Subzone-Zuordnung fehlgeschlagen: ${assignErr.message}`
            : 'Tank angelegt, Subzone-Zuordnung fehlgeschlagen',
        )
        emit('created', tank.id)
        emit('close')
        return
      }
    }

    toast.success(`Tank „${tank.name}" angelegt`)
    emit('created', tank.id)
    emit('close')
  } catch (e) {
    errorMessage.value =
      e instanceof Error ? e.message : 'Tank konnte nicht angelegt werden'
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
    title="Tank anlegen"
    max-width="max-w-lg"
    @close="handleClose"
  >
    <form class="tank-form" @submit.prevent="handleSubmit">
      <label class="tank-form__field">
        <span class="tank-form__label">Zone *</span>
        <select v-model="form.zone_id" class="tank-form__input" required aria-label="Zone">
          <option value="" disabled>Zone wählen</option>
          <option
            v-for="zone in availableZones"
            :key="zone.zone_id"
            :value="zone.zone_id"
          >
            {{ zone.name }}
          </option>
        </select>
      </label>

      <label class="tank-form__field">
        <span class="tank-form__label">Name *</span>
        <input
          v-model="form.name"
          type="text"
          class="tank-form__input"
          placeholder="z.B. Misch-Tank A"
          required
          maxlength="100"
          autofocus
          aria-label="Tank-Name"
        />
      </label>

      <div class="tank-form__row">
        <label class="tank-form__field">
          <span class="tank-form__label">Betriebsart *</span>
          <select
            v-model="form.operation_mode"
            class="tank-form__input"
            required
            aria-label="Betriebsart"
          >
            <option
              v-for="mode in TANK_OPERATION_MODES"
              :key="mode"
              :value="mode"
            >
              {{ TANK_OPERATION_MODE_LABELS[mode] }}
            </option>
          </select>
        </label>

        <label class="tank-form__field">
          <span class="tank-form__label">Nennvolumen (L)</span>
          <input
            v-model="form.nominal_volume_l"
            type="number"
            min="0"
            step="any"
            class="tank-form__input"
            placeholder="optional"
            aria-label="Nennvolumen in Litern"
          />
        </label>
      </div>

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

      <fieldset v-if="availableSubzones.length > 0" class="tank-form__fieldset">
        <legend class="tank-form__label">Subzonen zuordnen (optional)</legend>
        <p class="tank-form__hint">
          Zuordnung über bekannte Pflanzen-Subzonen (UUID). Keine Dosierpumpe nötig.
        </p>
        <label
          v-for="sz in availableSubzones"
          :key="sz.id"
          class="tank-form__check"
        >
          <input
            type="checkbox"
            :checked="form.subzone_config_ids.includes(sz.id)"
            :aria-label="`Subzone ${sz.name} zuordnen`"
            @change="toggleSubzone(sz.id)"
          />
          <span>{{ sz.name }}</span>
        </label>
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
          :disabled="isSubmitting"
          @click="handleSubmit"
        >
          {{ isSubmitting ? 'Wird angelegt…' : 'Tank anlegen' }}
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

.tank-form__fieldset {
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-sm);
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
}

.tank-form__check {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  cursor: pointer;
}

.tank-form__hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin: 0;
}

.tank-form__error {
  font-size: var(--text-sm);
  color: var(--color-danger);
  padding: var(--space-2) var(--space-3);
  background: color-mix(in srgb, var(--color-danger) 12%, transparent);
  border-radius: var(--radius-sm);
}

.tank-form__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}

.plant-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
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
  color: var(--color-text-primary);
}

.plant-btn--primary {
  background: var(--color-accent);
  color: var(--color-text-on-accent, #fff);
}
</style>
