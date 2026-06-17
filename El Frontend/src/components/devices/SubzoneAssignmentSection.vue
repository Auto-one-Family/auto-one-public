<script setup lang="ts">
/**
 * SubzoneAssignmentSection — Reusable subzone selector with "Create new" option
 *
 * Used in SensorConfigPanel and ActuatorConfigPanel.
 * Allows selecting existing subzone or creating a new one and assigning this device's GPIO.
 */

import { ref, computed, onMounted, watch } from 'vue'
import { Check, X } from 'lucide-vue-next'
import { subzonesApi } from '@/api/subzones'
import { useEspStore } from '@/stores/esp'
import { useToast } from '@/composables/useToast'

interface Props {
  espId: string
  gpio: number
  modelValue: string | null
  zoneId?: string | null
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  zoneId: null,
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string | null]
}>()

const toast = useToast()
const espStore = useEspStore()

const availableSubzones = ref<{ id: string; name: string }[]>([])
const isLoading = ref(true)
const newSubzoneName = ref('')
const createLoading = ref(false)

const CREATE_OPTION = '__create_new__'
/** Sentinel for "Keine Subzone" — avoids HTML select coercing null to string "null" */
const NONE_OPTION = '__none__'
const isCreating = ref(false)

const selectedValue = computed({
  get: () => {
    if (isCreating.value) return CREATE_OPTION
    const v = props.modelValue
    return v == null || v === '' ? NONE_OPTION : v
  },
  set: (v) => {
    if (v === CREATE_OPTION) {
      isCreating.value = true
    } else {
      const emitted = v === NONE_OPTION || v == null || v === '' ? null : String(v)
      emit('update:modelValue', emitted)
      isCreating.value = false
    }
  },
})

const showCreateInput = computed(() => isCreating.value)

const selectOptions = computed(() => {
  const opts = [
    { value: NONE_OPTION, label: 'Keine Subzone' },
    ...availableSubzones.value.map((sz) => ({ value: sz.id, label: sz.name })),
    { value: CREATE_OPTION, label: '+ Neue Subzone erstellen...' },
  ]
  return opts
})

async function loadSubzones() {
  isLoading.value = true
  try {
    const result = await subzonesApi.getSubzones(props.espId)
    const list = (result as { subzones?: Array<{ subzone_id?: string; subzone_name?: string; id?: string; name?: string }> }).subzones ?? []
    availableSubzones.value = list.map((sz: any) => ({
      id: sz.subzone_id ?? sz.id ?? '',
      name: sz.subzone_name ?? sz.name ?? sz.subzone_id ?? sz.id ?? '',
    }))
  } catch {
    availableSubzones.value = []
  } finally {
    isLoading.value = false
  }
}

async function confirmCreateSubzone() {
  const name = newSubzoneName.value.trim()
  if (!name) return
  createLoading.value = true
  try {
    const device = espStore.devices.find((d) => espStore.getDeviceId(d) === props.espId)
    const zoneId = props.zoneId ?? device?.zone_id ?? null
    // Server accepts only letters, numbers, underscores (schemas/subzone.py)
    const subzoneId = name
      .toLowerCase()
      .replace(/\s+/g, '_')
      .replace(/-/g, '_')
      .replace(/[^a-z0-9_]/g, '_')
    await subzonesApi.assignSubzone(props.espId, {
      subzone_id: subzoneId,
      subzone_name: name,
      parent_zone_id: zoneId ?? undefined,
      assigned_gpios: [props.gpio],
    })
    await espStore.fetchAll()
    await loadSubzones()
    emit('update:modelValue', subzoneId)
    isCreating.value = false
    newSubzoneName.value = ''
    toast.success(`Subzone "${name}" erstellt und zugewiesen`)
  } catch {
    toast.error('Subzone konnte nicht erstellt werden')
  } finally {
    createLoading.value = false
  }
}

function cancelCreateSubzone() {
  isCreating.value = false
  newSubzoneName.value = ''
}

watch(showCreateInput, (show) => {
  if (show) {
    isCreating.value = true
    newSubzoneName.value = ''
  }
})

// Reload subzones when switching to a different ESP (e.g. different sensor in list)
watch(() => props.espId, () => loadSubzones(), { immediate: false })

onMounted(loadSubzones)
</script>

<template>
  <div class="subzone-assignment">
    <label class="subzone-assignment__label">Subzone</label>
    <div class="subzone-assignment__controls">
      <select
        v-model="selectedValue"
        class="subzone-assignment__select"
        :disabled="disabled || isLoading"
      >
        <option v-for="opt in selectOptions" :key="String(opt.value)" :value="opt.value">
          {{ opt.label }}
        </option>
      </select>
      <template v-if="showCreateInput">
        <div class="subzone-assignment__create-row">
          <input
            v-model="newSubzoneName"
            class="subzone-assignment__input"
            type="text"
            placeholder="Subzone-Name eingeben..."
            :disabled="createLoading"
            @keyup.enter="confirmCreateSubzone"
            @keyup.escape="cancelCreateSubzone"
          />
          <button
            class="subzone-assignment__btn subzone-assignment__btn--confirm"
            :disabled="!newSubzoneName.trim() || createLoading"
            @click="confirmCreateSubzone"
          >
            <Check class="w-3.5 h-3.5" />
          </button>
          <button
            class="subzone-assignment__btn"
            :disabled="createLoading"
            @click="cancelCreateSubzone"
          >
            <X class="w-3.5 h-3.5" />
          </button>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.subzone-assignment {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.subzone-assignment__label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.subzone-assignment__controls {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.subzone-assignment__select {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  outline: none;
}

.subzone-assignment__select:focus {
  border-color: var(--color-accent);
}

.subzone-assignment__create-row {
  display: flex;
  gap: var(--space-1);
  align-items: center;
}

.subzone-assignment__input {
  flex: 1;
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  outline: none;
}

.subzone-assignment__input:focus {
  border-color: var(--color-accent);
}

.subzone-assignment__btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-2);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.subzone-assignment__btn:hover:not(:disabled) {
  border-color: var(--color-text-muted);
  color: var(--color-text-primary);
}

.subzone-assignment__btn--confirm:hover:not(:disabled) {
  border-color: var(--color-success);
  color: var(--color-success);
}

.subzone-assignment__btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
