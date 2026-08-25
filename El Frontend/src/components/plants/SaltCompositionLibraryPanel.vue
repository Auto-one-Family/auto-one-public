<script setup lang="ts">
/**
 * SaltCompositionLibraryPanel — editierbare Salz-Referenzbibliothek (AUT-1422 / B5).
 *
 * Reine CRUD-Oberfläche für /v1/salt-compositions. Kein Recipe-Recompute.
 * Muster: Formular/Speichern/Toast wie TankStockMixRecipePanel Edit.
 */

import { computed, onMounted, ref } from 'vue'
import { BookOpen } from 'lucide-vue-next'
import {
  saltCompositionsApi,
  saltSourceTypeLabel,
  validateSaltCompositionWrite,
  type SaltComposition,
  type SaltCompositionWriteBody,
  type SaltSourceType,
} from '@/api/saltCompositions'
import { formatUiApiError, toUiApiError } from '@/api/uiApiError'
import { useUiStore } from '@/shared/stores/ui.store'
import { useToast } from '@/composables/useToast'
import BaseButton from '@/shared/design/primitives/BaseButton.vue'
import BaseInput from '@/shared/design/primitives/BaseInput.vue'
import BaseSelect from '@/shared/design/primitives/BaseSelect.vue'
import BaseSpinner from '@/shared/design/primitives/BaseSpinner.vue'
import EmptyState from '@/shared/design/patterns/EmptyState.vue'
import ErrorState from '@/shared/design/patterns/ErrorState.vue'
import { createLogger } from '@/utils/logger'

const logger = createLogger('SaltCompositionLibraryPanel')
const toast = useToast()
const uiStore = useUiStore()

const rows = ref<SaltComposition[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const editorOpen = ref(false)
const saving = ref(false)
const editingId = ref<string | null>(null)

interface EditorDraft {
  name: string
  formula: string
  n_pct: string
  p_pct: string
  k_pct: string
  ca_pct: string
  mg_pct: string
  s_pct: string
  source_type: SaltSourceType
  source_note: string
}

const draft = ref<EditorDraft>({
  name: '',
  formula: '',
  n_pct: '',
  p_pct: '',
  k_pct: '',
  ca_pct: '',
  mg_pct: '',
  s_pct: '',
  source_type: 'beleg_offen',
  source_note: '',
})

const sourceOptions = [
  { value: 'stoichiometric', label: 'stöchiometrisch abgeleitet' },
  { value: 'manufacturer_label', label: 'Hersteller-Etikett' },
  { value: 'beleg_offen', label: '[BELEG offen]' },
]

const editorTitle = computed(() =>
  editingId.value ? 'Salz bearbeiten' : 'Neues Salz anlegen',
)

function emptyDraft(): EditorDraft {
  return {
    name: '',
    formula: '',
    n_pct: '',
    p_pct: '',
    k_pct: '',
    ca_pct: '',
    mg_pct: '',
    s_pct: '',
    source_type: 'beleg_offen',
    source_note: '',
  }
}

function pctToInput(value: number | null): string {
  return value === null || value === undefined ? '' : String(value)
}

function parsePctInput(raw: string): number | null {
  if (raw.trim() === '') return null
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    rows.value = await saltCompositionsApi.list()
  } catch (err) {
    const msg = formatUiApiError(toUiApiError(err, 'Salz-Bibliothek laden fehlgeschlagen'))
    error.value = msg
    logger.error('load failed', err)
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  editingId.value = null
  draft.value = emptyDraft()
  editorOpen.value = true
}

function openEdit(row: SaltComposition): void {
  editingId.value = row.id
  draft.value = {
    name: row.name,
    formula: row.formula ?? '',
    n_pct: pctToInput(row.n_pct),
    p_pct: pctToInput(row.p_pct),
    k_pct: pctToInput(row.k_pct),
    ca_pct: pctToInput(row.ca_pct),
    mg_pct: pctToInput(row.mg_pct),
    s_pct: pctToInput(row.s_pct),
    source_type: row.source_type,
    source_note: row.source_note,
  }
  editorOpen.value = true
}

function closeEditor(): void {
  editorOpen.value = false
  editingId.value = null
}

async function save(): Promise<void> {
  const body: SaltCompositionWriteBody = {
    name: draft.value.name.trim(),
    formula: draft.value.formula.trim() || null,
    n_pct: parsePctInput(draft.value.n_pct),
    p_pct: parsePctInput(draft.value.p_pct),
    k_pct: parsePctInput(draft.value.k_pct),
    ca_pct: parsePctInput(draft.value.ca_pct),
    mg_pct: parsePctInput(draft.value.mg_pct),
    s_pct: parsePctInput(draft.value.s_pct),
    source_type: draft.value.source_type,
    source_note: draft.value.source_note.trim(),
  }
  const validationError = validateSaltCompositionWrite(body)
  if (validationError) {
    toast.error(validationError)
    return
  }

  saving.value = true
  try {
    if (editingId.value) {
      await saltCompositionsApi.update(editingId.value, body)
      toast.success('Salz-Eintrag gespeichert')
    } else {
      await saltCompositionsApi.create(body)
      toast.success('Salz-Eintrag angelegt')
    }
    closeEditor()
    await load()
  } catch (err) {
    toast.error(formatUiApiError(toUiApiError(err, 'Speichern fehlgeschlagen')))
  } finally {
    saving.value = false
  }
}

async function deactivate(row: SaltComposition): Promise<void> {
  const ok = await uiStore.confirm({
    title: 'Salz deaktivieren?',
    message: `„${row.name}“ wird ausgeblendet (kein Hard-Delete).`,
    variant: 'warning',
    confirmText: 'Deaktivieren',
  })
  if (!ok) return
  try {
    await saltCompositionsApi.softDelete(row.id)
    toast.success('Salz deaktiviert')
    await load()
  } catch (err) {
    toast.error(formatUiApiError(toUiApiError(err, 'Deaktivieren fehlgeschlagen')))
  }
}

function formatPct(value: number | null): string {
  if (value === null || value === undefined) return '—'
  return String(value)
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="salt-lib" aria-label="Salz-Referenzbibliothek">
    <header class="salt-lib__head">
      <div class="salt-lib__title-row">
        <BookOpen class="salt-lib__icon" aria-hidden="true" />
        <h3 class="salt-lib__title">Salz-Bibliothek</h3>
      </div>
      <p class="salt-lib__helper">
        Garantierte Analyse je Salz (elementar %). Berechnetes NPK an der Rezeptur
        nutzt diese Werte — hier nur Pflege der Bibliothek.
      </p>
      <BaseButton
        type="button"
        variant="secondary"
        size="sm"
        aria-label="Neues Salz anlegen"
        @click="openCreate"
      >
        Neues Salz
      </BaseButton>
    </header>

    <BaseSpinner v-if="loading" label="Salz-Bibliothek wird geladen" />
    <ErrorState v-else-if="error" :message="error" @retry="load" />
    <EmptyState
      v-else-if="rows.length === 0"
      title="Keine Salze"
      description="Noch keine Einträge in der Salz-Bibliothek."
    />

    <div v-else class="salt-lib__list" role="list">
      <article
        v-for="row in rows"
        :key="row.id"
        class="salt-lib__row"
        role="listitem"
      >
        <div class="salt-lib__row-main">
          <p class="salt-lib__name">{{ row.name }}</p>
          <p v-if="row.formula" class="salt-lib__formula">{{ row.formula }}</p>
          <p class="salt-lib__source">
            Herkunft: {{ saltSourceTypeLabel(row.source_type) }}
          </p>
          <p class="salt-lib__pcts">
            N {{ formatPct(row.n_pct) }} · P {{ formatPct(row.p_pct) }} · K
            {{ formatPct(row.k_pct) }} · Ca {{ formatPct(row.ca_pct) }} · Mg
            {{ formatPct(row.mg_pct) }} · S {{ formatPct(row.s_pct) }}
          </p>
        </div>
        <div class="salt-lib__actions">
          <BaseButton
            type="button"
            variant="ghost"
            size="sm"
            :aria-label="`${row.name} bearbeiten`"
            @click="openEdit(row)"
          >
            Bearbeiten
          </BaseButton>
          <BaseButton
            type="button"
            variant="ghost"
            size="sm"
            :aria-label="`${row.name} deaktivieren`"
            @click="deactivate(row)"
          >
            Deaktivieren
          </BaseButton>
        </div>
      </article>
    </div>

    <div v-if="editorOpen" class="salt-lib__editor" data-testid="salt-lib-editor">
      <h4 class="salt-lib__editor-title">{{ editorTitle }}</h4>
      <div class="salt-lib__fields">
        <BaseInput
          v-model="draft.name"
          label="Salzname"
          aria-label="Salzname"
        />
        <BaseInput
          v-model="draft.formula"
          label="Formel (optional)"
          aria-label="Chemische Formel optional"
        />
        <BaseSelect
          v-model="draft.source_type"
          label="Herkunft"
          :options="sourceOptions"
          aria-label="Herkunft der Elementwerte"
        />
        <BaseInput
          v-model="draft.source_note"
          label="Quellenangabe"
          helper="Bei Etikett: Produkt/Charge; bei stöchiometrisch: kurze Rechnung"
          aria-label="Quellenangabe"
        />
        <div class="salt-lib__pct-grid">
          <BaseInput
            v-model="draft.n_pct"
            type="number"
            label="N %"
            :min="0"
            :max="100"
            :step="0.0001"
            aria-label="Stickstoff Prozent"
          />
          <BaseInput
            v-model="draft.p_pct"
            type="number"
            label="P %"
            :min="0"
            :max="100"
            :step="0.0001"
            aria-label="Phosphor Prozent"
          />
          <BaseInput
            v-model="draft.k_pct"
            type="number"
            label="K %"
            :min="0"
            :max="100"
            :step="0.0001"
            aria-label="Kalium Prozent"
          />
          <BaseInput
            v-model="draft.ca_pct"
            type="number"
            label="Ca %"
            :min="0"
            :max="100"
            :step="0.0001"
            aria-label="Calcium Prozent"
          />
          <BaseInput
            v-model="draft.mg_pct"
            type="number"
            label="Mg %"
            :min="0"
            :max="100"
            :step="0.0001"
            aria-label="Magnesium Prozent"
          />
          <BaseInput
            v-model="draft.s_pct"
            type="number"
            label="S %"
            :min="0"
            :max="100"
            :step="0.0001"
            aria-label="Schwefel Prozent"
          />
        </div>
        <p class="salt-lib__helper">
          Keine Platzhalter-Werte — leere Felder bleiben leer ([BELEG offen] möglich).
        </p>
      </div>
      <div class="salt-lib__editor-actions">
        <BaseButton
          type="button"
          variant="ghost"
          size="sm"
          aria-label="Bearbeitung abbrechen"
          @click="closeEditor"
        >
          Abbrechen
        </BaseButton>
        <BaseButton
          type="button"
          variant="primary"
          size="sm"
          :loading="saving"
          aria-label="Salz-Eintrag speichern"
          @click="save"
        >
          Speichern
        </BaseButton>
      </div>
    </div>
  </section>
</template>

<style scoped>
.salt-lib {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  min-width: 0;
  max-width: 100%;
  padding: var(--space-3);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  background: var(--color-dark-100);
}

.salt-lib__head {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.salt-lib__title-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.salt-lib__icon {
  width: 1.1rem;
  height: 1.1rem;
  color: var(--color-iridescent-2);
}

.salt-lib__title,
.salt-lib__editor-title {
  margin: 0;
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-dark-950);
}

.salt-lib__helper {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-dark-700);
}

.salt-lib__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.salt-lib__row {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-2);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
}

.salt-lib__name {
  margin: 0;
  font-weight: 600;
  color: var(--color-dark-950);
}

.salt-lib__formula,
.salt-lib__source,
.salt-lib__pcts {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-dark-700);
}

.salt-lib__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.salt-lib__editor {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding-top: var(--space-2);
  border-top: 1px solid var(--glass-border);
}

.salt-lib__fields {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.salt-lib__pct-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-2);
}

@media (min-width: 640px) {
  .salt-lib__pct-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

.salt-lib__editor-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  justify-content: flex-end;
}
</style>
