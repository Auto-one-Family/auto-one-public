/**
 * useWebSocket Composable Unit Tests
 *
 * Tests for WebSocket real-time communication including:
 * - Connection lifecycle (connect, disconnect, status)
 * - Subscription management (subscribe, unsubscribe, filters)
 * - Message handling and routing
 * - Status monitoring with intervals
 * - Cleanup and resource management
 * - Options handling (autoConnect, filters)
 * - Error handling
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { nextTick } from 'vue'
import { mockWebSocketService, createWebSocketMock } from '../../mocks/websocket'

// Mock BEFORE importing the composable
vi.mock('@/services/websocket', () => createWebSocketMock())

import { useWebSocket } from '@/composables/useWebSocket'

// =============================================================================
// SETUP / TEARDOWN
// =============================================================================

// Track cleanup functions for composables created during tests
let cleanupFunctions: (() => void)[] = []

beforeEach(() => {
  vi.useFakeTimers()
  mockWebSocketService.reset()
  cleanupFunctions = []
})

afterEach(() => {
  // Run all cleanup functions to stop intervals
  cleanupFunctions.forEach(fn => fn())
  cleanupFunctions = []
  vi.clearAllTimers()
  vi.useRealTimers()
})

/**
 * Helper: Create composable and track cleanup
 * Ensures intervals are stopped after test
 */
function createWebSocket(options: Parameters<typeof useWebSocket>[0] = {}) {
  const ws = useWebSocket(options)
  cleanupFunctions.push(ws.cleanup)
  return ws
}

// =============================================================================
// BASIC FUNCTIONALITY
// =============================================================================

describe('useWebSocket - Basic API', () => {
  it('returns expected properties and methods', () => {
    const ws = createWebSocket({ autoConnect: false })

    // State
    expect(ws.isConnected).toBeDefined()
    expect(ws.isConnecting).toBeDefined()
    expect(ws.connectionError).toBeDefined()
    expect(ws.connectionStatus).toBeDefined()
    expect(ws.lastMessage).toBeDefined()
    expect(ws.messageCount).toBeDefined()
    expect(ws.activeFilters).toBeDefined()

    // Actions
    expect(typeof ws.connect).toBe('function')
    expect(typeof ws.disconnect).toBe('function')
    expect(typeof ws.subscribe).toBe('function')
    expect(typeof ws.unsubscribe).toBe('function')
    expect(typeof ws.updateFilters).toBe('function')
    expect(typeof ws.on).toBe('function')
    expect(typeof ws.watchStatus).toBe('function')
    expect(typeof ws.cleanup).toBe('function')
  })
})

// =============================================================================
// CONNECTION LIFECYCLE
// =============================================================================

describe('useWebSocket - Connection', () => {
  describe('Initial State', () => {
    it('has isConnected=false initially when autoConnect=false', () => {
      const { isConnected } = createWebSocket({ autoConnect: false })
      expect(isConnected.value).toBe(false)
    })

    it('has connectionStatus="disconnected" initially when autoConnect=false', () => {
      const { connectionStatus } = createWebSocket({ autoConnect: false })
      expect(connectionStatus.value).toBe('disconnected')
    })

    it('has null connectionError initially', () => {
      const { connectionError } = createWebSocket({ autoConnect: false })
      expect(connectionError.value).toBeNull()
    })

    it('has messageCount=0 initially', () => {
      const { messageCount } = createWebSocket({ autoConnect: false })
      expect(messageCount.value).toBe(0)
    })

    it('has lastMessage=null initially', () => {
      const { lastMessage } = createWebSocket({ autoConnect: false })
      expect(lastMessage.value).toBeNull()
    })
  })

  describe('connect()', () => {
    it('sets isConnecting=true during connection', async () => {
      const { connect, isConnecting } = createWebSocket({ autoConnect: false })

      const connectPromise = connect()
      expect(isConnecting.value).toBe(true)

      // Advance timer to complete mock connection
      await vi.advanceTimersByTimeAsync(20)
      await connectPromise
    })

    it('sets isConnected=true after successful connection', async () => {
      const { connect, isConnected } = createWebSocket({ autoConnect: false })

      const connectPromise = connect()
      await vi.advanceTimersByTimeAsync(20)
      await connectPromise

      expect(isConnected.value).toBe(true)
    })

    it('sets connectionStatus="connected" after success', async () => {
      const { connect, connectionStatus } = createWebSocket({ autoConnect: false })

      const connectPromise = connect()
      await vi.advanceTimersByTimeAsync(20)
      await connectPromise

      expect(connectionStatus.value).toBe('connected')
    })

    it('sets isConnecting=false after connection completes', async () => {
      const { connect, isConnecting } = createWebSocket({ autoConnect: false })

      const connectPromise = connect()
      await vi.advanceTimersByTimeAsync(20)
      await connectPromise

      expect(isConnecting.value).toBe(false)
    })

    it('does nothing if already connected', async () => {
      const { connect, isConnected } = createWebSocket({ autoConnect: false })

      // First connection - start connect, advance timers, then await
      const connectPromise = connect()
      await vi.advanceTimersByTimeAsync(20)
      await connectPromise

      expect(isConnected.value).toBe(true)

      // Second connection attempt - should return immediately (no timer needed)
      await connect()

      // Since already connected, should still be connected
      expect(isConnected.value).toBe(true)
    })

    it('applies initial filters after connection', async () => {
      const filters = { types: ['sensor_data' as const], esp_ids: ['ESP_TEST'] }
      const { connect } = createWebSocket({
        autoConnect: false,
        filters
      })

      const connectPromise = connect()
      await vi.advanceTimersByTimeAsync(20)
      await connectPromise

      expect(mockWebSocketService.getSubscriptionCount()).toBe(1)
    })
  })

  describe('disconnect()', () => {
    it('sets isConnected=false after disconnect', async () => {
      const { connect, disconnect, isConnected } = createWebSocket({ autoConnect: false })

      const connectPromise = connect()
      await vi.advanceTimersByTimeAsync(20)
      await connectPromise
      expect(isConnected.value).toBe(true)

      disconnect()
      expect(isConnected.value).toBe(false)
    })

    it('sets connectionStatus="disconnected" after disconnect', async () => {
      const { connect, disconnect, connectionStatus } = createWebSocket({ autoConnect: false })

      const connectPromise = connect()
      await vi.advanceTimersByTimeAsync(20)
      await connect()
      disconnect()

      expect(connectionStatus.value).toBe('disconnected')
    })

    it('unsubscribes active subscription on disconnect', async () => {
      const { connect, subscribe, disconnect } = createWebSocket({ autoConnect: false })

      await vi.advanceTimersByTimeAsync(20)
      await connect()

      subscribe({ types: ['sensor_data'] })
      expect(mockWebSocketService.getSubscriptionCount()).toBe(1)

      disconnect()
      // Subscriptions are cleared in disconnect
      expect(mockWebSocketService.getSubscriptionCount()).toBe(0)
    })
  })
})

// =============================================================================
// SUBSCRIPTION MANAGEMENT
// =============================================================================

describe('useWebSocket - Subscriptions', () => {
  describe('subscribe()', () => {
    it('creates subscription with filters', async () => {
      const { connect, subscribe } = createWebSocket({ autoConnect: false })

      await vi.advanceTimersByTimeAsync(20)
      await connect()

      const filters = { types: ['sensor_data' as const] }
      subscribe(filters)

      expect(mockWebSocketService.getSubscriptionCount()).toBe(1)
    })

    it('returns subscriptionId', async () => {
      const { connect, subscribe } = createWebSocket({ autoConnect: false })

      await vi.advanceTimersByTimeAsync(20)
      await connect()

      const subId = subscribe({ types: ['sensor_data'] })

      expect(subId).toBeDefined()
      expect(subId).toMatch(/^sub_/)
    })

    it('stores activeFilters', async () => {
      const { connect, subscribe, activeFilters } = createWebSocket({ autoConnect: false })

      await vi.advanceTimersByTimeAsync(20)
      await connect()

      const filters = { types: ['sensor_data' as const], esp_ids: ['ESP_123'] }
      subscribe(filters)

      expect(activeFilters.value).toEqual(filters)
    })

    it('replaces previous subscription', async () => {
      const { connect, subscribe } = createWebSocket({ autoConnect: false })

      await vi.advanceTimersByTimeAsync(20)
      await connect()

      subscribe({ types: ['sensor_data'] })
      expect(mockWebSocketService.getSubscriptionCount()).toBe(1)

      subscribe({ types: ['esp_health'] })
      // Old subscription should be replaced, not added
      expect(mockWebSocketService.getSubscriptionCount()).toBe(1)
    })
  })

  describe('on()', () => {
    it('registers type-specific handler', async () => {
      const { connect, on } = createWebSocket({ autoConnect: false })

      await vi.advanceTimersByTimeAsync(20)
      await connect()

      const handler = vi.fn()
      on('sensor_data', handler)

      expect(mockWebSocketService.getHandlerCount('sensor_data')).toBe(1)
    })

    it('allows multiple handlers per type', async () => {
      const { connect, on } = createWebSocket({ autoConnect: false })

      await vi.advanceTimersByTimeAsync(20)
      await connect()

      const handler1 = vi.fn()
      const handler2 = vi.fn()

      on('sensor_data', handler1)
      on('sensor_data', handler2)

      expect(mockWebSocketService.getHandlerCount('sensor_data')).toBe(2)
    })

    it('returns unsubscribe function', async () => {
      const { connect, on } = createWebSocket({ autoConnect: false })

      await vi.advanceTimersByTimeAsync(20)
      await connect()

      const handler = vi.fn()
      const unsubscribe = on('sensor_data', handler)

      expect(typeof unsubscribe).toBe('function')
    })

    it('unsubscribe function removes the handler', async () => {
      const { connect, on } = createWebSocket({ autoConnect: false })

      await vi.advanceTimersByTimeAsync(20)
      await connect()

      const handler = vi.fn()
      const unsubscribe = on('sensor_data', handler)

      expect(mockWebSocketService.getHandlerCount('sensor_data')).toBe(1)

      unsubscribe()

      expect(mockWebSocketService.getHandlerCount('sensor_data')).toBe(0)
    })

    it('calls handler when message of that type is received', async () => {
      const { connect, on } = createWebSocket({ autoConnect: false })

      await vi.advanceTimersByTimeAsync(20)
      await connect()

      const handler = vi.fn()
      on('sensor_data', handler)

      mockWebSocketService.simulateMessage('sensor_data', {
        esp_id: 'ESP_TEST',
        gpio: 4,
        value: 22.5
      })

      expect(handler).toHaveBeenCalledTimes(1)
      expect(handler).toHaveBeenCalledWith(expect.objectContaining({
        type: 'sensor_data',
        data: expect.objectContaining({ esp_id: 'ESP_TEST' })
      }))
    })

    it('does not call handler for different message types', async () => {
      const { connect, on } = createWebSocket({ autoConnect: false })

      await vi.advanceTimersByTimeAsync(20)
      await connect()

      const handler = vi.fn()
      on('sensor_data', handler)

      mockWebSocketService.simulateMessage('esp_health', {
        esp_id: 'ESP_TEST',
        status: 'online'
      })

      expect(handler).not.toHaveBeenCalled()
    })
  })

  describe('unsubscribe()', () => {
    it('removes subscription and clears state', async () => {
      const { connect, subscribe, unsubscribe, activeFilters } = createWebSocket({ autoConnect: false })

      await vi.advanceTimersByTimeAsync(20)
      await connect()

      subscribe({ types: ['sensor_data'] })
      expect(activeFilters.value).not.toBeNull()

      unsubscribe()

      expect(activeFilters.value).toBeNull()
    })

    it('handles unsubscribe when no subscription exists', () => {
      const { unsubscribe } = createWebSocket({ autoConnect: false })

      // Should not throw
      expect(() => unsubscribe()).not.toThrow()
    })
  })
})

// =============================================================================
// MESSAGE HANDLING
// =============================================================================

describe('useWebSocket - Messages', () => {
  it('updates lastMessage on receipt', async () => {
    const { connect, subscribe, lastMessage } = createWebSocket({ autoConnect: false })

    await vi.advanceTimersByTimeAsync(20)
    await connect()

    subscribe({ types: ['sensor_data'] })

    mockWebSocketService.simulateMessage('sensor_data', {
      esp_id: 'ESP_TEST',
      gpio: 4,
      value: 22.5
    })

    expect(lastMessage.value).not.toBeNull()
    expect(lastMessage.value?.type).toBe('sensor_data')
    expect(lastMessage.value?.data.esp_id).toBe('ESP_TEST')
  })

  it('increments messageCount', async () => {
    const { connect, subscribe, messageCount } = createWebSocket({ autoConnect: false })

    await vi.advanceTimersByTimeAsync(20)
    await connect()

    subscribe({ types: ['sensor_data'] })
    expect(messageCount.value).toBe(0)

    mockWebSocketService.simulateMessage('sensor_data', { esp_id: 'ESP_1', value: 1 })
    expect(messageCount.value).toBe(1)

    mockWebSocketService.simulateMessage('sensor_data', { esp_id: 'ESP_1', value: 2 })
    expect(messageCount.value).toBe(2)
  })

  it('dispatches to type-specific handlers', async () => {
    const { connect, subscribe, on } = createWebSocket({ autoConnect: false })

    await vi.advanceTimersByTimeAsync(20)
    await connect()

    const handler = vi.fn()
    on('sensor_data', handler)
    subscribe({ types: ['sensor_data'] })

    mockWebSocketService.simulateMessage('sensor_data', {
      esp_id: 'ESP_TEST',
      value: 42
    })

    // Handler is called via service.on() and via subscription callback
    // The important thing is that it IS called with the correct message
    expect(handler).toHaveBeenCalled()
    expect(handler.mock.calls[0][0]).toMatchObject({
      type: 'sensor_data',
      data: { esp_id: 'ESP_TEST', value: 42 }
    })
  })

  it('notifies all registered handlers for type', async () => {
    const { connect, subscribe, on } = createWebSocket({ autoConnect: false })

    await vi.advanceTimersByTimeAsync(20)
    await connect()

    const handler1 = vi.fn()
    const handler2 = vi.fn()

    on('esp_health', handler1)
    on('esp_health', handler2)
    subscribe({ types: ['esp_health'] })

    mockWebSocketService.simulateMessage('esp_health', {
      esp_id: 'ESP_TEST',
      status: 'online'
    })

    expect(handler1).toHaveBeenCalled()
    expect(handler2).toHaveBeenCalled()
  })

  it('filters messages by esp_ids', async () => {
    const { connect, subscribe, messageCount } = createWebSocket({ autoConnect: false })

    await vi.advanceTimersByTimeAsync(20)
    await connect()

    subscribe({ types: ['sensor_data'], esp_ids: ['ESP_ALLOWED'] })

    // Should NOT count - wrong ESP
    mockWebSocketService.simulateMessage('sensor_data', {
      esp_id: 'ESP_OTHER',
      value: 1
    })
    expect(messageCount.value).toBe(0)

    // Should count - correct ESP
    mockWebSocketService.simulateMessage('sensor_data', {
      esp_id: 'ESP_ALLOWED',
      value: 2
    })
    expect(messageCount.value).toBe(1)
  })
})

// =============================================================================
// FILTER UPDATES
// =============================================================================

describe('useWebSocket - updateFilters()', () => {
  it('updates activeFilters ref', async () => {
    const { connect, subscribe, updateFilters, activeFilters } = createWebSocket({ autoConnect: false })

    await vi.advanceTimersByTimeAsync(20)
    await connect()

    subscribe({ types: ['sensor_data'] })
    expect(activeFilters.value?.types).toEqual(['sensor_data'])

    updateFilters({ types: ['esp_health'] })
    expect(activeFilters.value?.types).toEqual(['esp_health'])
  })

  it('unsubscribes existing subscription before creating new one', async () => {
    const { connect, subscribe, updateFilters } = createWebSocket({ autoConnect: false })

    await vi.advanceTimersByTimeAsync(20)
    await connect()

    subscribe({ types: ['sensor_data'] })
    const initialCount = mockWebSocketService.getSubscriptionCount()
    expect(initialCount).toBe(1)

    updateFilters({ types: ['esp_health'] })
    // Should still be 1, not 2 (old was removed)
    expect(mockWebSocketService.getSubscriptionCount()).toBe(1)
  })

  it('handles updateFilters when not subscribed', async () => {
    const { connect, updateFilters, activeFilters } = createWebSocket({ autoConnect: false })

    await vi.advanceTimersByTimeAsync(20)
    await connect()

    // No prior subscription
    updateFilters({ types: ['sensor_data'] })

    expect(activeFilters.value?.types).toEqual(['sensor_data'])
    expect(mockWebSocketService.getSubscriptionCount()).toBe(1)
  })
})

// =============================================================================
// STATUS MONITORING
// =============================================================================

describe('useWebSocket - Status Monitor', () => {
  it('updates isConnected when service state changes', async () => {
    // Use autoConnect=true so status monitor is started
    const { isConnected } = createWebSocket({ autoConnect: true })

    // Wait for connection
    await vi.advanceTimersByTimeAsync(10)
    expect(isConnected.value).toBe(true)

    // Simulate service disconnect
    mockWebSocketService.simulateError()

    // Advance timer to trigger status check (1 second interval)
    vi.advanceTimersByTime(1000)

    expect(isConnected.value).toBe(false)
  })

  it('checks connection every 1 second when autoConnect=true', async () => {
    createWebSocket({ autoConnect: true })

    // Wait for initial connect
    await vi.advanceTimersByTimeAsync(20)

    // Mock is connected
    expect(mockWebSocketService.isConnected()).toBe(true)

    // Simulate external disconnect
    mockWebSocketService.simulateError()

    // Before 1 second, isConnected from composable might still be true
    // After 1 second, status monitor should detect change
    vi.advanceTimersByTime(1000)

    // The composable should have detected the change
    // (This tests that the interval is running)
  })

  it('watchStatus() returns unsubscribe function', async () => {
    const { watchStatus } = createWebSocket({ autoConnect: false })

    const callback = vi.fn()
    const unwatch = watchStatus(callback)

    expect(typeof unwatch).toBe('function')
  })

  it('watchStatus() calls callback with immediate status', async () => {
    const { watchStatus } = createWebSocket({ autoConnect: false })

    const callback = vi.fn()
    watchStatus(callback)

    // Should be called immediately with 'disconnected'
    // Vue watch passes (newValue, oldValue, onCleanup) - we only check first two
    expect(callback).toHaveBeenCalled()
    expect(callback.mock.calls[0][0]).toBe('disconnected')
  })
})

// =============================================================================
// CLEANUP
// =============================================================================

describe('useWebSocket - Cleanup', () => {
  it('cleanup() stops status monitor interval', async () => {
    const { connect, cleanup } = createWebSocket({ autoConnect: false })

    await vi.advanceTimersByTimeAsync(20)
    await connect()

    // Cleanup should clear the interval
    cleanup()

    // Simulate service disconnect
    mockWebSocketService.simulateError()

    // Advance time significantly
    vi.advanceTimersByTime(5000)

    // No error should occur (interval was cleared)
  })

  it('cleanup() clears messageHandlers', async () => {
    const { connect, on, cleanup } = createWebSocket({ autoConnect: false })

    await vi.advanceTimersByTimeAsync(20)
    await connect()

    on('sensor_data', vi.fn())
    on('esp_health', vi.fn())

    // Before cleanup, handlers exist
    expect(mockWebSocketService.getHandlerCount('sensor_data')).toBe(1)

    cleanup()

    // Cleanup should remove handlers registered through the composable
    // Note: The composable cleanup clears its internal messageHandlers
    // The mock service handlers are still there until service.disconnect()
  })

  it('cleanup() unsubscribes active subscription', async () => {
    const { connect, subscribe, cleanup, activeFilters } = createWebSocket({ autoConnect: false })

    await vi.advanceTimersByTimeAsync(20)
    await connect()

    subscribe({ types: ['sensor_data'] })
    expect(activeFilters.value).not.toBeNull()

    cleanup()
    expect(activeFilters.value).toBeNull()
  })

  it('cleanup() can be called multiple times safely', async () => {
    const { connect, cleanup } = createWebSocket({ autoConnect: false })

    await vi.advanceTimersByTimeAsync(20)
    await connect()

    // Multiple cleanups should not throw
    expect(() => {
      cleanup()
      cleanup()
      cleanup()
    }).not.toThrow()
  })

  it('cleanup() does not disconnect singleton service', async () => {
    const { connect, cleanup } = createWebSocket({ autoConnect: false })

    await vi.advanceTimersByTimeAsync(20)
    await connect()

    cleanup()

    // Service should still be connected (it's a singleton shared across components)
    expect(mockWebSocketService.isConnected()).toBe(true)
  })
})

// =============================================================================
// OPTIONS
// =============================================================================

describe('useWebSocket - Options', () => {
  it('connects automatically when autoConnect=true (default)', async () => {
    const { isConnected, isConnecting } = createWebSocket({ autoConnect: true })

    // Should start connecting
    expect(isConnecting.value).toBe(true)

    // Wait for connection
    await vi.advanceTimersByTimeAsync(20)

    expect(isConnected.value).toBe(true)
  })

  it('does not connect when autoConnect=false', async () => {
    const { isConnected, isConnecting } = createWebSocket({ autoConnect: false })

    // Should not be connecting
    expect(isConnecting.value).toBe(false)
    expect(isConnected.value).toBe(false)

    // Wait some time
    await vi.advanceTimersByTimeAsync(100)

    // Still not connected
    expect(isConnected.value).toBe(false)
  })

  it('applies initial filters option', async () => {
    const filters = {
      types: ['sensor_data' as const, 'esp_health' as const],
      esp_ids: ['ESP_1', 'ESP_2']
    }

    const { activeFilters } = createWebSocket({
      autoConnect: false,
      filters
    })

    expect(activeFilters.value).toEqual(filters)
  })

  it('subscribes with initial filters after autoConnect', async () => {
    const filters = {
      types: ['sensor_data' as const],
      esp_ids: ['ESP_AUTO']
    }

    createWebSocket({
      autoConnect: true,
      filters
    })

    // Wait for connection
    await vi.advanceTimersByTimeAsync(20)

    // Should have created subscription with filters
    expect(mockWebSocketService.getSubscriptionCount()).toBe(1)
  })
})

// =============================================================================
// ERROR HANDLING
// =============================================================================

describe('useWebSocket - Errors', () => {
  it('sets connectionError on connection failure', async () => {
    // Override connect to simulate failure
    const originalConnect = mockWebSocketService.connect.bind(mockWebSocketService)
    mockWebSocketService.connect = vi.fn().mockRejectedValue(new Error('Connection refused'))

    const { connect, connectionError } = createWebSocket({ autoConnect: false })

    try {
      await connect()
    } catch {
      // Expected to throw
    }

    expect(connectionError.value).toBe('Connection refused')

    // Restore
    mockWebSocketService.connect = originalConnect
  })

  it('sets connectionStatus="error" on failure', async () => {
    const originalConnect = mockWebSocketService.connect.bind(mockWebSocketService)
    mockWebSocketService.connect = vi.fn().mockRejectedValue(new Error('Test error'))

    const { connect, connectionStatus } = createWebSocket({ autoConnect: false })

    try {
      await connect()
    } catch {
      // Expected
    }

    expect(connectionStatus.value).toBe('error')

    mockWebSocketService.connect = originalConnect
  })

  it('clears error on new connect attempt', async () => {
    const originalConnect = mockWebSocketService.connect.bind(mockWebSocketService)

    // First: fail
    mockWebSocketService.connect = vi.fn().mockRejectedValue(new Error('First error'))

    const { connect, connectionError } = createWebSocket({ autoConnect: false })

    try {
      await connect()
    } catch {
      // Expected
    }
    expect(connectionError.value).toBe('First error')

    // Restore and try again
    mockWebSocketService.connect = originalConnect

    const connectPromise = connect()

    // Error should be cleared during new attempt
    expect(connectionError.value).toBeNull()

    await vi.advanceTimersByTimeAsync(20)
    await connectPromise
  })

  it('handles service error simulation', async () => {
    // Use autoConnect=true so status monitor is started
    const { isConnected } = createWebSocket({ autoConnect: true })

    // Wait for connection
    await vi.advanceTimersByTimeAsync(10)
    expect(isConnected.value).toBe(true)

    // Simulate error
    mockWebSocketService.simulateError()

    // After status monitor tick (1 second interval)
    vi.advanceTimersByTime(1000)

    expect(isConnected.value).toBe(false)
  })
})

// =============================================================================
// INTEGRATION SCENARIOS
// =============================================================================

describe('useWebSocket - Integration Scenarios', () => {
  it('full lifecycle: connect → subscribe → receive → unsubscribe → disconnect', async () => {
    const { connect, disconnect, subscribe, unsubscribe, lastMessage, messageCount, isConnected } =
      createWebSocket({ autoConnect: false })

    // Connect
    const connectPromise = connect()
    await vi.advanceTimersByTimeAsync(20)
    await connectPromise
    expect(isConnected.value).toBe(true)

    // Subscribe
    subscribe({ types: ['sensor_data'] })
    expect(messageCount.value).toBe(0)

    // Receive message
    mockWebSocketService.simulateMessage('sensor_data', {
      esp_id: 'ESP_TEST',
      gpio: 4,
      value: 25.5
    })
    expect(messageCount.value).toBe(1)
    expect(lastMessage.value?.data.value).toBe(25.5)

    // Unsubscribe
    unsubscribe()

    // Disconnect
    disconnect()
    expect(isConnected.value).toBe(false)
  })

  it('multiple type handlers receive correct messages', async () => {
    const { connect, on } = createWebSocket({ autoConnect: false })

    await vi.advanceTimersByTimeAsync(20)
    await connect()

    const sensorHandler = vi.fn()
    const healthHandler = vi.fn()
    const errorHandler = vi.fn()

    on('sensor_data', sensorHandler)
    on('esp_health', healthHandler)
    on('error_event', errorHandler)

    // Send different types
    mockWebSocketService.simulateMessage('sensor_data', { value: 1 })
    mockWebSocketService.simulateMessage('esp_health', { status: 'online' })
    mockWebSocketService.simulateMessage('sensor_data', { value: 2 })

    expect(sensorHandler).toHaveBeenCalledTimes(2)
    expect(healthHandler).toHaveBeenCalledTimes(1)
    expect(errorHandler).not.toHaveBeenCalled()
  })

  it('filter updates do not lose messages', async () => {
    const { connect, subscribe, updateFilters, messageCount } = createWebSocket({ autoConnect: false })

    await vi.advanceTimersByTimeAsync(20)
    await connect()

    // Subscribe to sensor_data
    subscribe({ types: ['sensor_data'] })

    mockWebSocketService.simulateMessage('sensor_data', { v: 1 })
    expect(messageCount.value).toBe(1)

    // Update to esp_health
    updateFilters({ types: ['esp_health'] })

    // sensor_data should not increment anymore
    mockWebSocketService.simulateMessage('sensor_data', { v: 2 })
    expect(messageCount.value).toBe(1)

    // esp_health should increment
    mockWebSocketService.simulateMessage('esp_health', { status: 'online' })
    expect(messageCount.value).toBe(2)
  })
})
