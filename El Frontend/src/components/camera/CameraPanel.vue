<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { Camera, RefreshCw, AlertCircle } from 'lucide-vue-next'
import { cameraApi, type CameraStatus } from '@/api/camera'
import { createLogger } from '@/utils/logger'

const logger = createLogger('CameraPanel')

const status = ref<CameraStatus | null>(null)
const isLoading = ref(true)
const snapshotBlobUrl = ref<string | null>(null)
const imageError = ref(false)
const pollTimer = ref<ReturnType<typeof setInterval> | null>(null)
const statusTimer = ref<ReturnType<typeof setInterval> | null>(null)

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
    const prevUrl = snapshotBlobUrl.value
    snapshotBlobUrl.value = await cameraApi.fetchSnapshot()
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

onMounted(async () => {
  await fetchStatus()

  if (isEnabled.value && isAvailable.value) {
    await refreshSnapshot()
    startPolling()
  }

  // Re-check status every 30s to react when camera service comes back up
  statusTimer.value = setInterval(async () => {
    const wasAvailable = isAvailable.value
    await fetchStatus()
    if (!wasAvailable && isAvailable.value) {
      await refreshSnapshot()
      startPolling()
    } else if (wasAvailable && !isAvailable.value) {
      stopPolling()
    } else if (isAvailable.value) {
      // Interval may have changed — restart poll timer with updated interval
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
  <div v-if="!isLoading && isEnabled" class="camera-panel card">
    <div class="camera-panel__header">
      <Camera class="camera-panel__icon" :size="16" aria-hidden="true" />
      <span class="camera-panel__title">Kamera</span>
      <span v-if="status?.model" class="camera-panel__model">{{ status.model }}</span>
      <span class="camera-panel__spacer" />
      <button
        v-if="isAvailable"
        class="camera-panel__refresh"
        :title="`Aufnahme: ${lastCaptureLabel}`"
        @click="refreshSnapshot"
      >
        <RefreshCw :size="14" />
        {{ lastCaptureLabel }}
      </button>
    </div>

    <div class="camera-panel__body">
      <template v-if="isAvailable">
        <img
          v-if="snapshotBlobUrl && !imageError"
          :src="snapshotBlobUrl"
          class="camera-panel__image"
          alt="Kamera-Snapshot"
        />
        <div v-else-if="imageError" class="camera-panel__error">
          <AlertCircle :size="20" />
          <span>Bild konnte nicht geladen werden</span>
          <button class="btn-ghost text-sm" @click="refreshSnapshot">Wiederholen</button>
        </div>
        <div v-else class="camera-panel__unavailable">
          <RefreshCw :size="20" class="animate-spin" />
          <span>Lade Bild…</span>
        </div>
      </template>
      <div v-else class="camera-panel__unavailable">
        <AlertCircle :size="20" />
        <span>{{ status?.error ?? 'Kamera nicht verfügbar' }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.camera-panel {
  padding: 0;
  overflow: hidden;
  border-radius: var(--radius-md);
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
}

.camera-panel__header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--color-border);
  font-size: var(--text-sm);
}

.camera-panel__icon {
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.camera-panel__title {
  font-weight: 600;
  color: var(--color-text-primary);
}

.camera-panel__model {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.camera-panel__spacer {
  flex: 1;
}

.camera-panel__refresh {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  transition: var(--transition-fast);
}

.camera-panel__refresh:hover {
  background: var(--color-surface-3);
  color: var(--color-text-secondary);
}

.camera-panel__body {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 160px;
  max-height: 400px;
}

.camera-panel__image {
  width: 100%;
  height: auto;
  max-height: 400px;
  object-fit: contain;
  display: block;
  transform: rotate(180deg);
}

.camera-panel__error,
.camera-panel__unavailable {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px;
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}
</style>
