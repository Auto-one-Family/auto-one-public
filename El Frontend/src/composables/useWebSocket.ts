/**
 * WebSocket Composable
 * 
 * Vue composable for WebSocket real-time updates.
 * Uses the WebSocket service singleton for connection management.
 * Provides subscription system consistent with backend.
 */

import { ref, computed, onMounted, onUnmounted, watch, getCurrentInstance } from 'vue'
import { websocketService, type WebSocketMessage, type WebSocketFilters, type WebSocketStatus } from '@/services/websocket'
import type { MessageType } from '@/types'
import { createLogger } from '@/utils/logger'

const logger = createLogger('useWebSocket')

// =============================================================================
// Types
// =============================================================================

export interface UseWebSocketOptions {
  /** Auto-connect on mount */
  autoConnect?: boolean
  /** Auto-reconnect on disconnect */
  autoReconnect?: boolean
  /** Initial subscription filters */
  filters?: WebSocketFilters
}

// =============================================================================
// Composable
// =============================================================================

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const {
    autoConnect = true,
    autoReconnect: _autoReconnect = true,
    filters,
  } = options

  const readServiceStatus = (): WebSocketStatus => {
    if (typeof websocketService.getStatus === 'function') {
      return websocketService.getStatus()
    }
    return websocketService.isConnected() ? 'connected' : 'disconnected'
  }

  // Connection state
  const isConnected = ref(websocketService.isConnected())
  const isConnecting = ref(false)
  const connectionError = ref<string | null>(null)
  const reconnectAttempts = ref(0)
  const serviceStatus = ref<WebSocketStatus>(readServiceStatus())

  // Subscription state
  const subscriptionId = ref<string | null>(null)
  const activeFilters = ref<WebSocketFilters | null>(filters || null)

  // Message state
  const lastMessage = ref<WebSocketMessage | null>(null)
  const messageCount = ref(0)
  const rateLimitWarning = ref(false)

  // Event handlers
  const messageHandlers = new Map<string, Set<(message: WebSocketMessage) => void>>()

  // Computed
  const connectionStatus = computed(() => serviceStatus.value)

  // =============================================================================
  // Connection Management
  // =============================================================================

  /**
   * Connect to WebSocket
   */
  async function connect(): Promise<void> {
    if (isConnecting.value || isConnected.value) {
      // Wenn bereits verbunden, muessen late-subscribers ihre Filter trotzdem registrieren.
      if (isConnected.value && activeFilters.value && !subscriptionId.value) {
        subscribe(activeFilters.value)
      }
      return
    }

    isConnecting.value = true
    connectionError.value = null
    serviceStatus.value = 'connecting'

    try {
      await websocketService.connect()
      const connected = websocketService.isConnected()
      isConnected.value = connected
      serviceStatus.value = readServiceStatus()
      
      // Subscribe with filters if provided
      if (connected && activeFilters.value) {
        subscribe(activeFilters.value)
      }
    } catch (error) {
      logger.error('Connection error', error)
      connectionError.value = error instanceof Error ? error.message : 'Connection failed'
      isConnected.value = false
      serviceStatus.value = 'error'
    } finally {
      isConnecting.value = false
    }
  }

  /**
   * Disconnect from WebSocket
   */
  function disconnect(): void {
    if (subscriptionId.value) {
      websocketService.unsubscribe(subscriptionId.value)
      subscriptionId.value = null
    }
    
    websocketService.disconnect()
    isConnected.value = false
    isConnecting.value = false
    serviceStatus.value = 'disconnected'
  }

  // =============================================================================
  // Subscription Management
  // =============================================================================

  /**
   * Subscribe to messages matching filters
   */
  function subscribe(filters: WebSocketFilters, callback?: (message: WebSocketMessage) => void): string {
    // Unsubscribe existing subscription if any
    if (subscriptionId.value) {
      websocketService.unsubscribe(subscriptionId.value)
    }

    const handler = callback || ((message: WebSocketMessage) => {
      lastMessage.value = message
      messageCount.value++
      
      // Notify type-specific handlers
      const typeHandlers = messageHandlers.get(message.type)
      if (typeHandlers) {
        typeHandlers.forEach(h => h(message))
      }
    })

    subscriptionId.value = websocketService.subscribe(filters, handler)
    activeFilters.value = filters

    return subscriptionId.value
  }

  /**
   * Unsubscribe from messages
   */
  function unsubscribe(): void {
    if (subscriptionId.value) {
      websocketService.unsubscribe(subscriptionId.value)
      subscriptionId.value = null
      activeFilters.value = null
    }
  }

  /**
   * Subscribe to specific message type.
   *
   * If a filter-based subscription is active (from useWebSocket options),
   * messages are dispatched via routeMessage → subscription callback → messageHandlers.
   * Only registers on websocketService.on() when NO subscription exists,
   * to avoid double-dispatch (handler called 2x per message).
   */
  function on(type: MessageType | string, callback: (message: WebSocketMessage) => void): () => void {
    if (!messageHandlers.has(type)) {
      messageHandlers.set(type, new Set())
    }

    messageHandlers.get(type)!.add(callback)

    // Only register via service when no subscription exists AND none is pending.
    // activeFilters is set synchronously, while subscriptionId is set after async connect().
    // Without the activeFilters check, handlers registered between useWebSocket() and
    // connect() completion would be dispatched twice (via routeMessage AND listeners).
    let unsubscribeService: (() => void) | null = null
    if (!subscriptionId.value && !activeFilters.value) {
      unsubscribeService = websocketService.on(type, callback)
    }

    return () => {
      const handlers = messageHandlers.get(type)
      if (handlers) {
        handlers.delete(callback)
        if (handlers.size === 0) {
          messageHandlers.delete(type)
        }
      }
      unsubscribeService?.()
    }
  }

  /**
   * Update subscription filters
   */
  function updateFilters(filters: WebSocketFilters): void {
    if (subscriptionId.value) {
      unsubscribe()
    }
    subscribe(filters)
  }

  // =============================================================================
  // Status Monitoring
  // =============================================================================

  /**
   * Watch connection status
   */
  function watchStatus(callback: (status: string) => void): () => void {
    return watch(connectionStatus, callback, { immediate: true })
  }

  // =============================================================================
  // Lifecycle & Status Monitoring
  // =============================================================================

  // Detect whether we're in a Vue component context (has lifecycle) or store context (no lifecycle)
  const hasComponentContext = !!getCurrentInstance()

  // Status check interval - only used in component contexts
  let statusInterval: ReturnType<typeof setInterval> | null = null

  // Status change unsubscriber - used in store contexts
  let unsubscribeStatusChange: (() => void) | null = null

  /**
   * Start status monitoring via polling (component context only)
   */
  function startStatusMonitor(): void {
    if (statusInterval) return // Already running

    const checkStatus = () => {
      const status = readServiceStatus()
      serviceStatus.value = status
      isConnected.value = status === 'connected'
      isConnecting.value = status === 'connecting'
      if (status !== 'error') {
        connectionError.value = null
      }
    }

    statusInterval = setInterval(checkStatus, 1000)
  }

  /**
   * Start status monitoring via callback (store context - no polling)
   */
  function startStatusCallback(): void {
    if (unsubscribeStatusChange) return // Already registered

    unsubscribeStatusChange = websocketService.onStatusChange((status) => {
      serviceStatus.value = status
      isConnected.value = status === 'connected'
      isConnecting.value = status === 'connecting'
      if (status !== 'error') {
        connectionError.value = null
      }
    })
  }

  /**
   * Stop status monitoring (both polling and callback)
   */
  function stopStatusMonitor(): void {
    if (statusInterval) {
      clearInterval(statusInterval)
      statusInterval = null
    }
    if (unsubscribeStatusChange) {
      unsubscribeStatusChange()
      unsubscribeStatusChange = null
    }
  }

  /**
   * Full cleanup - call when done with this composable instance
   */
  function cleanup(): void {
    stopStatusMonitor()
    removeConnectResubscribe?.()
    removeConnectResubscribe = null
    messageHandlers.clear()
    if (subscriptionId.value) {
      unsubscribe()
    }
  }

  // Re-subscribe filtered handlers after every successful reconnect (auth/tab/visibility).
  let removeConnectResubscribe: (() => void) | null = null
  if (autoConnect && activeFilters.value) {
    removeConnectResubscribe = websocketService.onConnect(() => {
      if (activeFilters.value) {
        subscribe(activeFilters.value)
      }
    })
  }

  // Auto-connect immediately if enabled (works in both component and store contexts)
  if (autoConnect) {
    connect()
    // Use callback-based monitoring in store context (no setInterval leak),
    // polling in component context (cleaned up by onUnmounted)
    if (hasComponentContext) {
      startStatusMonitor()
    } else {
      startStatusCallback()
    }
  }

  // Vue component lifecycle hooks (only work when used in Vue components)
  if (hasComponentContext) {
    onMounted(() => {
      // Start status monitor if not already started
      if (!statusInterval) {
        startStatusMonitor()
      }
    })

    onUnmounted(() => {
      cleanup()
    })
  }

  // =============================================================================
  // Return
  // =============================================================================

  return {
    // State
    isConnected,
    isConnecting,
    connectionError,
    connectionStatus,
    reconnectAttempts,
    lastMessage,
    messageCount,
    rateLimitWarning,
    activeFilters,

    // Actions
    connect,
    disconnect,
    subscribe,
    unsubscribe,
    updateFilters,
    on,
    watchStatus,
    cleanup,
  }
}

















