/**
 * Read-only WebSocket connectivity snapshot for operator-facing UI (AUT-200).
 * Uses websocketService — no duplicate connection logic.
 */

import { computed, onUnmounted, ref, getCurrentInstance } from 'vue'
import { websocketService, type WebSocketStatus } from '@/services/websocket'

/**
 * Defensive reads — same idea as useWebSocket readServiceStatus().
 * Vite HMR can keep a WebSocket singleton from before new methods existed on the class prototype.
 */
function readServiceStatus(): WebSocketStatus {
  if (typeof websocketService.getStatus === 'function') {
    return websocketService.getStatus()
  }
  return websocketService.isConnected() ? 'connected' : 'disconnected'
}

function readReconnectAttempts(): number {
  if (typeof websocketService.getReconnectAttempts === 'function') {
    return websocketService.getReconnectAttempts()
  }
  return 0
}

function readLastConnectedAtMs(): number | null {
  if (typeof websocketService.getLastConnectedAt === 'function') {
    return websocketService.getLastConnectedAt()
  }
  return null
}

function readLastDisconnectAtMs(): number | null {
  if (typeof websocketService.getLastDisconnectAt === 'function') {
    return websocketService.getLastDisconnectAt()
  }
  return null
}

export function useWebSocketStatus() {
  const status = ref<WebSocketStatus>(readServiceStatus())
  const reconnectAttempts = ref(readReconnectAttempts())
  const lastConnectedAtMs = ref<number | null>(readLastConnectedAtMs())
  const lastDisconnectAtMs = ref<number | null>(readLastDisconnectAtMs())

  function syncFromService(): void {
    status.value = readServiceStatus()
    reconnectAttempts.value = readReconnectAttempts()
    lastConnectedAtMs.value = readLastConnectedAtMs()
    lastDisconnectAtMs.value = readLastDisconnectAtMs()
  }

  let unsubscribeStatus: (() => void) | null = null
  let pollTimer: ReturnType<typeof setInterval> | null = null

  function start(): void {
    if (unsubscribeStatus || pollTimer) return
    syncFromService()
    unsubscribeStatus = websocketService.onStatusChange(() => {
      syncFromService()
    })
    pollTimer = setInterval(syncFromService, 1000)
  }

  function stop(): void {
    unsubscribeStatus?.()
    unsubscribeStatus = null
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  start()

  if (getCurrentInstance()) {
    onUnmounted(() => stop())
  }

  const isConnected = computed(() => status.value === 'connected')
  const isConnecting = computed(() => status.value === 'connecting')
  const isDegraded = computed(() => !isConnected.value)

  const lastConnected = computed(() =>
    lastConnectedAtMs.value != null ? new Date(lastConnectedAtMs.value) : null,
  )

  const lastDisconnectAt = computed(() =>
    lastDisconnectAtMs.value != null ? new Date(lastDisconnectAtMs.value) : null,
  )

  /** Yellow path: explicit connect in flight, or backoff with prior failures scheduled */
  const showReconnectingUi = computed(
    () =>
      isConnecting.value ||
      (reconnectAttempts.value > 0 && !isConnected.value && status.value !== 'error'),
  )

  return {
    status,
    isConnected,
    isConnecting,
    isDegraded,
    reconnectAttempts,
    lastConnected,
    lastDisconnectAt,
    showReconnectingUi,
    syncFromService,
    stop,
  }
}
