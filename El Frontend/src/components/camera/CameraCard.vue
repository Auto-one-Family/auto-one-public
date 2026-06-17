<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Camera, RefreshCw, AlertCircle, Maximize2, X } from 'lucide-vue-next'
import { cameraApi, type CameraStatus } from '@/api/camera'
import { useDragStateStore } from '@/shared/stores'
import { createLogger } from '@/utils/logger'

const logger = createLogger('CameraCard')

// ── Stores ─────────────────────────────────────────────────────────────────
const dragStore = useDragStateStore()

// ── Camera state ───────────────────────────────────────────────────────────
const status = ref<CameraStatus | null>(null)
const isLoading = ref(true)
const snapshotBlobUrl = ref<string | null>(null)
const imageError = ref(false)
const pollTimer = ref<ReturnType<typeof setInterval> | null>(null)
const statusTimer = ref<ReturnType<typeof setInterval> | null>(null)

// ── Drag state (visual feedback while dragging) ────────────────────────────
const isDragActive = ref(false)

function onDragStart(e: DragEvent): void {
  e.dataTransfer?.setData('camera-drag', '1')
  isDragActive.value = true
  dragStore.startCameraDrag()
}

function onDragEnd(): void {
  isDragActive.value = false
  dragStore.endCameraDrag()
}


// ── Expand modal ───────────────────────────────────────────────────────────
const isExpanded = ref(false)

// ── Computed ───────────────────────────────────────────────────────────────
const isEnabled = computed(() => status.value?.enabled === true)
const isAvailable = computed(() => status.value?.available === true)

const pollInterval = computed<number>(() => {
  const secs = status.value?.interval_seconds
  return (typeof secs === 'number' && secs > 0 ? secs : 5) * 1000
})

const lastCaptureLabel = computed<string>(() => {
  const ts = status.value?.last_capture
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return ts
  }
})

const statusBarClass = computed(() => {
  if (!isEnabled.value) return 'camera-card__status-bar--inactive'
  if (isAvailable.value) return 'camera-card__status-bar--active'
  if (status.value?.error) return 'camera-card__status-bar--error'
  return 'camera-card__status-bar--warning'
})

const statusBadgeClass = computed(() => {
  if (!isEnabled.value) return 'badge--inactive'
  if (isAvailable.value) return 'badge--available'
  return 'badge--unavailable'
})

const statusLabel = computed(() => {
  if (!isEnabled.value) return 'Inaktiv'
  if (isAvailable.value) return 'Verfügbar'
  return 'Nicht verfügbar'
})

// ── API helpers ────────────────────────────────────────────────────────────
async function fetchStatus(): Promise<void> {
  try {
    status.value = await cameraApi.getStatus()
  } catch (err) {
    logger.error('Failed to fetch camera status', err)
    status.value = { enabled: false, available: false }
  } finally {
    isLoading.value = false
  }
}

async function refreshSnapshot(): Promise<void> {
  imageError.value = false
  try {
    const newBlobUrl = await cameraApi.fetchSnapshot()
    // Preload fully in background before swapping to avoid blank flash
    await new Promise<void>((resolve) => {
      const img = new Image()
      img.onload = () => resolve()
      img.onerror = () => resolve()
      img.src = newBlobUrl
    })
    const prevUrl = snapshotBlobUrl.value
    snapshotBlobUrl.value = newBlobUrl
    if (prevUrl) URL.revokeObjectURL(prevUrl)
  } catch {
    imageError.value = true
  }
}

function startPolling(): void {
  if (pollTimer.value) clearInterval(pollTimer.value)
  pollTimer.value = setInterval(refreshSnapshot, pollInterval.value)
}

function stopPolling(): void {
  if (pollTimer.value) { clearInterval(pollTimer.value); pollTimer.value = null }
}

// ── Lifecycle ──────────────────────────────────────────────────────────────
onMounted(async () => {
  await fetchStatus()

  if (isEnabled.value && isAvailable.value) {
    await refreshSnapshot()
    startPolling()
  }

  statusTimer.value = setInterval(async () => {
    const wasAvailable = isAvailable.value
    await fetchStatus()
    if (!wasAvailable && isAvailable.value) {
      await refreshSnapshot()
      startPolling()
    } else if (wasAvailable && !isAvailable.value) {
      stopPolling()
    } else if (isAvailable.value) {
      startPolling()
    }
  }, 30_000)
})

onUnmounted(() => {
  stopPolling()
  if (statusTimer.value) { clearInterval(statusTimer.value); statusTimer.value = null }
  if (snapshotBlobUrl.value) { URL.revokeObjectURL(snapshotBlobUrl.value); snapshotBlobUrl.value = null }
})
</script>

<template>
  <div
    v-if="!isLoading && isEnabled"
    class="camera-card"
    :class="{ 'camera-card--dragging': isDragActive }"
    draggable="true"
    @dragstart="onDragStart"
    @dragend="onDragEnd"
  >
    <!-- Status indicator bar (left border, same pattern as ESPCard) -->
    <div :class="['camera-card__status-bar', statusBarClass]" />

    <div class="camera-card__content">
      <!-- Header: Icon + Title + Model + Status badge -->
      <div class="camera-card__header">
        <div class="camera-card__name-group">
          <div class="camera-card__name-row">
            <Camera class="camera-card__icon" :size="16" aria-hidden="true" />
            <span class="camera-card__name">Kamera</span>
          </div>
          <span v-if="status?.model" class="camera-card__model">{{ status.model }}</span>
        </div>
        <div class="camera-card__badges">
          <span :class="['camera-card__badge', statusBadgeClass]">{{ statusLabel }}</span>
        </div>
      </div>

      <!-- Snapshot body — clickable to expand -->
      <div class="camera-card__body" @click="isAvailable && snapshotBlobUrl ? isExpanded = true : undefined">
        <template v-if="isAvailable">
          <img
            v-if="snapshotBlobUrl && !imageError"
            :src="snapshotBlobUrl"
            class="camera-card__image"
            alt="Kamera-Snapshot"
            :class="{ 'camera-card__image--clickable': !!snapshotBlobUrl }"
          />
          <div v-else-if="imageError" class="camera-card__state">
            <AlertCircle :size="20" />
            <span>Bild konnte nicht geladen werden</span>
            <button class="camera-card__retry-btn" @click.stop="refreshSnapshot">Wiederholen</button>
          </div>
          <div v-else class="camera-card__state">
            <RefreshCw :size="20" class="animate-spin" />
            <span>Lade Bild…</span>
          </div>
        </template>
        <div v-else class="camera-card__state">
          <AlertCircle :size="20" />
          <span>{{ status?.error ?? 'Kamera nicht verfügbar' }}</span>
        </div>
      </div>

      <!-- Footer: timestamp + actions -->
      <div class="camera-card__footer">
        <span class="camera-card__timestamp">{{ lastCaptureLabel }}</span>
        <div class="camera-card__footer-actions">
          <button
            v-if="isAvailable"
            class="camera-card__action-btn"
            title="Snapshot aktualisieren"
            @click="refreshSnapshot"
          >
            <RefreshCw :size="14" />
          </button>
          <button
            v-if="isAvailable && snapshotBlobUrl"
            class="camera-card__action-btn camera-card__action-btn--expand"
            title="Vollbild"
            @click="isExpanded = true"
          >
            <Maximize2 :size="14" />
            Vollbild
          </button>
        </div>
      </div>
    </div>

    <!-- Fullscreen overlay (custom, not BaseModal — width must not depend on Tailwind JIT) -->
    <Teleport to="body">
      <Transition name="camera-overlay-anim">
        <div
          v-if="isExpanded"
          class="camera-overlay"
          @click.self="isExpanded = false"
        >
          <div class="camera-overlay__panel">
            <div class="camera-overlay__header">
              <div class="camera-overlay__title">
                <Camera :size="16" aria-hidden="true" />
                <span>Kamera</span>
                <span v-if="status?.model" class="camera-card__model">{{ status.model }}</span>
                <span class="camera-card__timestamp">{{ lastCaptureLabel }}</span>
              </div>
              <div class="camera-overlay__actions">
                <button class="camera-card__action-btn" title="Aktualisieren" @click="refreshSnapshot">
                  <RefreshCw :size="14" />
                </button>
                <button class="camera-overlay__close-btn" title="Schließen" @click="isExpanded = false">
                  <X :size="18" />
                </button>
              </div>
            </div>
            <div class="camera-overlay__body">
              <img
                v-if="snapshotBlobUrl && !imageError"
                :src="snapshotBlobUrl"
                class="camera-overlay__image"
                alt="Kamera-Snapshot (Vollbild)"
              />
              <div v-else class="camera-card__state">
                <AlertCircle :size="24" />
                <span>Kein Bild verfügbar</span>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
/* ── Card shell (same skeleton as ESPCard) ─────────────────────────────── */
.camera-card {
  position: relative;
  display: flex;
  background-color: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  overflow: hidden;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, opacity 0.15s ease;
  cursor: grab;
}

.camera-card:hover {
  border-color: rgba(96, 165, 250, 0.25);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

/* ── Status bar (left border indicator) ───────────────────────────────── */
.camera-card__status-bar {
  width: 4px;
  flex-shrink: 0;
}

.camera-card__status-bar--active   { background-color: var(--color-success); }
.camera-card__status-bar--warning  { background-color: var(--color-warning); }
.camera-card__status-bar--error    { background-color: var(--color-error); }
.camera-card__status-bar--inactive { background-color: var(--color-text-muted); }

/* ── Content ───────────────────────────────────────────────────────────── */
.camera-card__content {
  flex: 1;
  padding: 1rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
  min-width: 0;
}

/* ── Header ────────────────────────────────────────────────────────────── */
.camera-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
}

.camera-card__name-group {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 0;
  flex: 1;
}

.camera-card__name-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.camera-card__icon { color: var(--color-text-muted); flex-shrink: 0; }

.camera-card__name {
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.camera-card__model {
  font-size: 0.75rem;
  color: var(--color-text-muted);
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
}

.camera-card__badges { display: flex; align-items: center; gap: 0.375rem; flex-shrink: 0; }

/* Status badges */
.camera-card__badge {
  display: inline-flex;
  align-items: center;
  padding: 0.2rem 0.5rem;
  font-size: 0.6875rem;
  font-weight: 600;
  border-radius: 999px;
  border: 1px solid;
}

.badge--available   { color: var(--color-success); border-color: rgba(52, 211, 153, 0.3); background: rgba(52, 211, 153, 0.08); }
.badge--unavailable { color: var(--color-warning);  border-color: rgba(251, 191, 36, 0.3);  background: rgba(251, 191, 36, 0.08); }
.badge--inactive    { color: var(--color-text-muted); border-color: var(--glass-border); background: transparent; }

/* ── Drag state ────────────────────────────────────────────────────────── */
.camera-card--dragging {
  opacity: 0.6;
  cursor: grabbing;
}

/* ── Snapshot body ─────────────────────────────────────────────────────── */
.camera-card__body {
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: var(--color-bg-tertiary);
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.camera-card__image {
  width: 100%;
  height: auto;
  max-height: 320px;
  object-fit: contain;
  display: block;
  transform: rotate(180deg);
}

.camera-card__image--clickable {
  cursor: zoom-in;
  transition: opacity 0.15s;
}

.camera-card__image--clickable:hover { opacity: 0.9; }

.camera-card__state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 1.5rem;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.camera-card__retry-btn {
  margin-top: 0.25rem;
  padding: 0.25rem 0.75rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.15s;
}

.camera-card__retry-btn:hover {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

/* ── Footer ────────────────────────────────────────────────────────────── */
.camera-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 0.75rem;
  border-top: 1px solid var(--glass-border);
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.camera-card__footer-actions {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.camera-card__action-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.5rem;
  font-size: 0.8125rem;
  color: var(--color-text-muted);
  background: transparent;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.15s;
}

.camera-card__action-btn:hover {
  color: var(--color-text-primary);
  background: var(--glass-bg);
  border-color: rgba(96, 165, 250, 0.3);
}

.camera-card__action-btn--expand {
  color: var(--color-iridescent-1);
  border-color: rgba(96, 165, 250, 0.25);
}

.camera-card__action-btn--expand:hover {
  background: rgba(96, 165, 250, 0.08);
  border-color: rgba(96, 165, 250, 0.4);
  box-shadow: 0 0 8px rgba(96, 165, 250, 0.15);
}

/* ── Fullscreen overlay ────────────────────────────────────────────────── */
.camera-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-dialog);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  background: rgba(0, 0, 0, 0.85);
  backdrop-filter: blur(4px);
}

.camera-overlay__panel {
  width: 95vw;
  max-height: 92vh;
  display: flex;
  flex-direction: column;
  background-color: var(--glass-bg-l3);
  backdrop-filter: blur(var(--glass-blur-l3));
  border: 1px solid var(--glass-border-l3);
  border-radius: var(--radius-md);
  box-shadow: var(--glass-shadow-l3);
  overflow: hidden;
}

.camera-overlay__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
}

.camera-overlay__title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.camera-overlay__actions {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.camera-overlay__close-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 44px;
  min-height: 44px;
  padding: 0.5rem;
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: all 0.2s;
}

.camera-overlay__close-btn:hover {
  color: var(--color-text-primary);
  background-color: var(--color-bg-tertiary);
}

.camera-overlay__body {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-tertiary);
  overflow: hidden;
}

.camera-overlay__image {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
  transform: rotate(180deg);
}

/* Overlay transition */
.camera-overlay-anim-enter-active,
.camera-overlay-anim-leave-active {
  transition: opacity 0.2s ease;
}

.camera-overlay-anim-enter-active .camera-overlay__panel,
.camera-overlay-anim-leave-active .camera-overlay__panel {
  transition: transform 0.2s ease, opacity 0.2s ease;
}

.camera-overlay-anim-enter-from,
.camera-overlay-anim-leave-to {
  opacity: 0;
}

.camera-overlay-anim-enter-from .camera-overlay__panel,
.camera-overlay-anim-leave-to .camera-overlay__panel {
  transform: scale(0.96) translateY(-8px);
  opacity: 0;
}

.camera-card__timestamp { font-variant-numeric: tabular-nums; }

/* Touch: grabbing cursor not applicable, draggable still works via touch events */
@media (hover: none) {
  .camera-card { cursor: default; }
}
</style>
