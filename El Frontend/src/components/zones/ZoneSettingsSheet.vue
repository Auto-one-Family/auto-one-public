<script setup lang="ts">
/**
 * ZoneSettingsSheet — SlideOver panel for zone entity management.
 *
 * Sections:
 * 1. Zone name (inline editable)
 * 2. Zone description (textarea)
 * 3. Status badge (active/archived)
 * 4. Actions: Archive/Reactivate
 * 5. Danger zone: Delete (only when 0 devices)
 *
 * Pattern: Follows ESPSettingsSheet.vue structure.
 */

import { ref, computed, watch, nextTick } from 'vue'
import {
  Pencil, Check, X, Loader2, AlertTriangle,
  Archive, RotateCcw, Trash2, Tag, FileText, Activity,
} from 'lucide-vue-next'
import SlideOver from '@/shared/design/primitives/SlideOver.vue'
import { useZoneStore } from '@/shared/stores/zone.store'
import { useUiStore } from '@/shared/stores/ui.store'
import { useToast } from '@/composables/useToast'
import { createLogger } from '@/utils/logger'
import type { ZoneEntity } from '@/types'

const logger = createLogger('ZoneSettings')

interface Props {
  zone: ZoneEntity
  isOpen: boolean
  deviceCount: number
}

const props = defineProps<Props>()

const emit = defineEmits<{
  close: []
  'zone-updated': []
  'zone-archived': []
  'zone-reactivated': []
}>()

const zoneStore = useZoneStore()
const uiStore = useUiStore()
const { success: showSuccess, error: showError } = useToast()

// ── Name Editing ─────────────────────────────────────────────────────────
const isEditingName = ref(false)
const editedName = ref('')
const isSavingName = ref(false)
const nameInputRef = ref<HTMLInputElement | null>(null)

function startEditName() {
  editedName.value = props.zone.name
  isEditingName.value = true
  nextTick(() => {
    nameInputRef.value?.focus()
    nameInputRef.value?.select()
  })
}

function cancelEditName() {
  isEditingName.value = false
  editedName.value = ''
}

async function saveName() {
  if (isSavingName.value) return
  const trimmed = editedName.value.trim()
  if (!trimmed || trimmed === props.zone.name) {
    cancelEditName()
    return
  }

  isSavingName.value = true
  try {
    await zoneStore.updateZone(props.zone.zone_id, { name: trimmed })
    isEditingName.value = false
    showSuccess(`Zone umbenannt zu "${trimmed}"`)
    emit('zone-updated')
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Name konnte nicht gespeichert werden')
    logger.error('Failed to update zone name', e)
  } finally {
    isSavingName.value = false
  }
}

function handleNameKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter') {
    event.preventDefault()
    saveName()
  } else if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    cancelEditName()
  }
}

// ── Description Editing ──────────────────────────────────────────────────
const editedDescription = ref('')
const isSavingDescription = ref(false)
const descriptionDirty = computed(() =>
  editedDescription.value !== (props.zone.description ?? ''),
)

watch(
  () => props.isOpen,
  (open) => {
    if (open) {
      editedDescription.value = props.zone.description ?? ''
    }
  },
)

async function saveDescription() {
  if (isSavingDescription.value || !descriptionDirty.value) return

  isSavingDescription.value = true
  try {
    await zoneStore.updateZone(props.zone.zone_id, {
      description: editedDescription.value.trim() || null,
    })
    showSuccess('Beschreibung gespeichert')
    emit('zone-updated')
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Beschreibung konnte nicht gespeichert werden')
    logger.error('Failed to update zone description', e)
  } finally {
    isSavingDescription.value = false
  }
}

// ── Status ───────────────────────────────────────────────────────────────
const isActive = computed(() => props.zone.status === 'active')
const isArchived = computed(() => props.zone.status === 'archived')
const canDeleteZone = computed(() => props.deviceCount === 0)

// ── Actions ──────────────────────────────────────────────────────────────
const isActionLoading = ref(false)

async function handleArchive() {
  if (props.deviceCount > 0) {
    await uiStore.confirm({
      title: 'Archivierung aktuell gesperrt',
      message: `Zone "${props.zone.name}" hat noch ${props.deviceCount} Gerät${props.deviceCount !== 1 ? 'e' : ''} zugewiesen. Bitte Geräte zuerst verschieben oder entfernen.`,
      variant: 'warning',
      confirmText: 'Verstanden',
      cancelText: 'Schließen',
    })
    return
  }

  const confirmed = await uiStore.confirm({
    title: 'Zone archivieren',
    message: `Zone "${props.zone.name}" wird archiviert. Historische Daten bleiben erhalten und du kannst parallel eine neue Zone für neue Durchläufe verwenden.`,
    variant: 'warning',
    confirmText: 'Archivieren',
  })
  if (!confirmed) return

  isActionLoading.value = true
  try {
    await zoneStore.archiveZone(props.zone.zone_id)
    showSuccess(`Zone "${props.zone.name}" archiviert`)
    emit('zone-archived')
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Zone konnte nicht archiviert werden')
    logger.error('Failed to archive zone', e)
  } finally {
    isActionLoading.value = false
  }
}

async function handleReactivate() {
  isActionLoading.value = true
  try {
    await zoneStore.reactivateZone(props.zone.zone_id)
    showSuccess(`Zone "${props.zone.name}" reaktiviert`)
    emit('zone-reactivated')
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Zone konnte nicht reaktiviert werden')
    logger.error('Failed to reactivate zone', e)
  } finally {
    isActionLoading.value = false
  }
}

async function handleDelete() {
  if (!canDeleteZone.value) {
    showError('Zone kann erst gelöscht werden, wenn keine Geräte mehr zugewiesen sind')
    return
  }

  const firstConfirm = await uiStore.confirm({
    title: 'Zone löschen',
    message: `Löschen ist endgültig. Für Datenhistorie nutze stattdessen "Zone archivieren". Zone "${props.zone.name}" wird aus dem aktiven Betrieb und Archiv entfernt.`,
    variant: 'danger',
    confirmText: 'Weiter',
  })
  if (!firstConfirm) return

  const secondConfirm = await uiStore.confirm({
    title: 'Letzte Sicherheitsabfrage',
    message: `Bitte bestätige erneut: Zone "${props.zone.name}" wirklich löschen? Diese Aktion kann nicht rückgängig gemacht werden.`,
    variant: 'danger',
    confirmText: 'Endgültig löschen',
  })
  if (!secondConfirm) return

  isActionLoading.value = true
  try {
    await zoneStore.deleteZoneEntity(props.zone.zone_id)
    showSuccess(`Zone "${props.zone.name}" gelöscht`)
    emit('zone-updated')
    emit('close')
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Zone konnte nicht gelöscht werden')
    logger.error('Failed to delete zone', e)
  } finally {
    isActionLoading.value = false
  }
}

function close() {
  emit('close')
}
</script>

<template>
  <SlideOver
    :open="isOpen"
    title="Zone-Einstellungen"
    width="lg"
    @close="close"
  >
    <div class="sheet-body">
      <!-- IDENTIFICATION -->
      <section class="sheet-section">
        <h4 class="sheet-section__title">
          <Tag class="w-3.5 h-3.5" />
          Zone
        </h4>
        <div class="sheet-section__content">
          <!-- Name (Editable) -->
          <div class="info-row info-row--name">
            <span class="info-row__label">Name</span>
            <template v-if="isEditingName">
              <div class="name-edit">
                <input
                  ref="nameInputRef"
                  v-model="editedName"
                  type="text"
                  class="name-edit__input"
                  placeholder="Zone-Name eingeben..."
                  maxlength="60"
                  :disabled="isSavingName"
                  @keydown="handleNameKeydown"
                  @blur="saveName"
                />
                <div class="name-edit__actions">
                  <button
                    v-if="isSavingName"
                    class="name-edit__btn"
                    disabled
                  >
                    <Loader2 class="w-4 h-4 animate-spin" />
                  </button>
                  <template v-else>
                    <button
                      class="name-edit__btn name-edit__btn--save"
                      title="Speichern (Enter)"
                      @mousedown.prevent="saveName"
                    >
                      <Check class="w-4 h-4" />
                    </button>
                    <button
                      class="name-edit__btn name-edit__btn--cancel"
                      title="Abbrechen (Escape)"
                      @mousedown.prevent="cancelEditName"
                    >
                      <X class="w-4 h-4" />
                    </button>
                  </template>
                </div>
              </div>
            </template>
            <template v-else>
              <div
                class="name-display"
                title="Klicken zum Bearbeiten"
                @click="startEditName"
              >
                <span class="info-row__value info-row__value--name">{{ zone.name }}</span>
                <Pencil class="name-display__pencil w-4 h-4" />
              </div>
            </template>
          </div>

          <!-- Zone ID -->
          <div class="info-row">
            <span class="info-row__label">Zone-ID</span>
            <code class="info-row__value info-row__value--mono">{{ zone.zone_id }}</code>
          </div>

          <!-- Device Count -->
          <div class="info-row">
            <span class="info-row__label">Geräte</span>
            <span class="info-row__value">{{ deviceCount }}</span>
          </div>
        </div>
      </section>

      <!-- DESCRIPTION -->
      <section class="sheet-section">
        <h4 class="sheet-section__title">
          <FileText class="w-3.5 h-3.5" />
          Beschreibung
        </h4>
        <div class="sheet-section__content">
          <textarea
            v-model="editedDescription"
            class="zone-description"
            placeholder="Optionale Beschreibung für diese Zone..."
            rows="3"
            maxlength="500"
          />
          <button
            v-if="descriptionDirty"
            class="action-btn action-btn--save"
            :disabled="isSavingDescription"
            @click="saveDescription"
          >
            <Loader2 v-if="isSavingDescription" class="w-4 h-4 animate-spin" />
            <Check v-else class="w-4 h-4" />
            <span>Beschreibung speichern</span>
          </button>
        </div>
      </section>

      <!-- STATUS -->
      <section class="sheet-section">
        <h4 class="sheet-section__title">
          <Activity class="w-3.5 h-3.5" />
          Status
        </h4>
        <div class="sheet-section__content">
          <div class="info-row">
            <span class="info-row__label">Aktuell</span>
            <span
              class="status-badge"
              :class="isActive ? 'status-badge--active' : 'status-badge--archived'"
            >
              <span
                class="status-badge__dot"
                :style="{ backgroundColor: isActive ? 'var(--color-success)' : 'var(--color-text-muted)' }"
              />
              {{ isActive ? 'Aktiv' : 'Archiviert' }}
            </span>
          </div>

          <!-- Archive / Reactivate -->
          <button
            v-if="isActive"
            class="action-btn action-btn--archive"
            :disabled="isActionLoading"
            @click="handleArchive"
          >
            <Loader2 v-if="isActionLoading" class="w-4 h-4 animate-spin" />
            <Archive v-else class="w-4 h-4" />
            <span>Zone archivieren</span>
          </button>
          <button
            v-if="isArchived"
            class="action-btn action-btn--reactivate"
            :disabled="isActionLoading"
            @click="handleReactivate"
          >
            <Loader2 v-if="isActionLoading" class="w-4 h-4 animate-spin" />
            <RotateCcw v-else class="w-4 h-4" />
            <span>Zone reaktivieren</span>
          </button>
        </div>
      </section>

      <!-- DELETE (double-confirmed) -->
      <section class="sheet-section sheet-section--danger">
        <h4 class="sheet-section__title">
          <AlertTriangle class="w-4 h-4" />
          Löschen
        </h4>
        <div class="sheet-section__content">
          <button
            class="action-btn action-btn--danger-outline"
            :disabled="isActionLoading || !canDeleteZone"
            @click="handleDelete"
          >
            <Loader2 v-if="isActionLoading" class="w-4 h-4 animate-spin" />
            <Trash2 v-else class="w-4 h-4" />
            <span>Zone löschen</span>
          </button>
          <p class="action-hint action-hint--danger">
            Löschen ist doppelt abgesichert und endgültig. Für Historie und alte Durchläufe immer archivieren.
          </p>
          <p v-if="!canDeleteZone" class="action-hint">
            Löschen aktuell gesperrt: {{ deviceCount }} Gerät{{ deviceCount !== 1 ? 'e' : '' }} sind noch zugewiesen.
            Bitte Geräte zuerst in eine andere Zone verschieben oder entkoppeln.
          </p>
        </div>
      </section>
    </div>
  </SlideOver>
</template>

<style scoped>
.sheet-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.sheet-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.sheet-section__title {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-secondary);
  margin: 0;
  padding-bottom: var(--space-1);
  border-bottom: 1px solid var(--glass-border);
}

.sheet-section__content {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.sheet-section--danger {
  background-color: rgba(239, 68, 68, 0.04);
  border: 1px solid rgba(239, 68, 68, 0.15);
  border-radius: var(--radius-md);
  padding: 0.875rem;
}

.sheet-section--danger .sheet-section__title {
  color: var(--color-error);
  border-color: rgba(239, 68, 68, 0.2);
}

/* ── Info Rows ── */
.info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  min-height: 28px;
}

.info-row--name { flex-wrap: wrap; }

.info-row__label {
  font-size: 0.8125rem;
  color: var(--color-text-muted);
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.info-row__value {
  font-size: 0.8125rem;
  color: var(--color-text-primary);
  font-weight: 500;
  text-align: right;
}

.info-row__value--name {
  font-weight: 600;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.info-row__value--mono {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  background-color: var(--color-bg-tertiary);
  padding: 0.25rem 0.5rem;
  border-radius: var(--radius-xs);
}

/* ── Name Edit ── */
.name-display {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  margin: -0.25rem -0.5rem;
  border-radius: var(--radius-sm);
  transition: background-color 0.15s ease;
}

.name-display:hover { background-color: var(--glass-bg); }
.name-display:hover .name-display__pencil { opacity: 1; }

.name-display__pencil {
  color: var(--color-text-muted);
  opacity: 0.3;
  transition: opacity 0.15s ease;
  flex-shrink: 0;
}

.name-edit {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 1;
  min-width: 0;
}

.name-edit__input {
  flex: 1;
  min-width: 0;
  padding: 0.375rem 0.5rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-text-primary);
  background-color: transparent;
  border: none;
  border-bottom: 2px solid var(--color-iridescent-1);
  outline: none;
  font-family: inherit;
}

.name-edit__input::placeholder {
  color: var(--color-text-muted);
  font-weight: 400;
}

.name-edit__input:disabled { opacity: 0.6; }

.name-edit__actions {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.name-edit__btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: var(--radius-sm);
  background-color: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.15s ease;
}

.name-edit__btn:hover:not(:disabled) { background-color: var(--glass-bg); }
.name-edit__btn:disabled { cursor: not-allowed; }

.name-edit__btn--save:hover:not(:disabled) {
  color: var(--color-success);
  background-color: rgba(34, 197, 94, 0.1);
}

.name-edit__btn--cancel:hover:not(:disabled) {
  color: var(--color-error);
  background-color: rgba(239, 68, 68, 0.1);
}

/* ── Description ── */
.zone-description {
  width: 100%;
  min-height: 60px;
  padding: 0.5rem;
  font-size: 0.8125rem;
  color: var(--color-text-primary);
  background-color: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  outline: none;
  font-family: inherit;
  resize: vertical;
  transition: border-color 0.15s ease;
}

.zone-description:focus {
  border-color: var(--color-iridescent-1);
}

.zone-description::placeholder {
  color: var(--color-text-muted);
}

/* ── Status Badge ── */
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px;
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: 600;
}

.status-badge__dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
}

.status-badge--active {
  background: rgba(34, 197, 94, 0.1);
  color: var(--color-success);
  border: 1px solid rgba(34, 197, 94, 0.2);
}

.status-badge--archived {
  background: rgba(112, 112, 128, 0.1);
  color: var(--color-text-muted);
  border: 1px solid rgba(112, 112, 128, 0.2);
}

/* ── Action Buttons ── */
.action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.625rem 1rem;
  font-size: 0.8125rem;
  font-weight: 500;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.15s ease;
  border: none;
  width: 100%;
}

.action-btn:disabled { opacity: 0.6; cursor: not-allowed; }

.action-btn--save {
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.3);
  color: var(--color-success);
}

.action-btn--save:hover:not(:disabled) {
  background: rgba(34, 197, 94, 0.2);
  border-color: rgba(34, 197, 94, 0.5);
}

.action-btn--archive {
  background: rgba(251, 191, 36, 0.08);
  border: 1px solid rgba(251, 191, 36, 0.25);
  color: var(--color-warning);
}

.action-btn--archive:hover:not(:disabled) {
  background: rgba(251, 191, 36, 0.15);
  border-color: rgba(251, 191, 36, 0.4);
}

.action-btn--reactivate {
  background: rgba(96, 165, 250, 0.08);
  border: 1px solid rgba(96, 165, 250, 0.25);
  color: var(--color-iridescent-1);
}

.action-btn--reactivate:hover:not(:disabled) {
  background: rgba(96, 165, 250, 0.15);
  border-color: rgba(96, 165, 250, 0.4);
}

.action-btn--danger-outline {
  background: transparent;
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: var(--color-error);
}

.action-btn--danger-outline:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.5);
}

.action-hint {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  line-height: 1.4;
}

.action-hint--danger {
  color: var(--color-error);
}
</style>
