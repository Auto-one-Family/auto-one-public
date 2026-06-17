/**
 * WebSocket Mock
 *
 * Provides a mock WebSocket service for testing real-time features.
 * Simulates WebSocket events without actual network connections.
 *
 * Interface matches the real WebSocket service (websocket.ts) for type consistency.
 */

import { vi } from 'vitest'

// =============================================================================
// Types (matching @/services/websocket and @/types)
// =============================================================================

export type MessageType =
  | 'sensor_data'
  | 'actuator_status'
  | 'esp_health'
  | 'config_response'
  | 'device_discovered'
  | 'device_approved'
  | 'device_rejected'
  | 'device_rediscovered'
  | 'actuator_response'
  | 'actuator_alert'
  | 'actuator_command'
  | 'actuator_command_failed'
  | 'config_published'
  | 'config_failed'
  | 'zone_assignment'
  | 'logic_execution'
  | 'system_event'
  | 'notification'
  | 'error_event'
  | 'sensor_health'
  | 'sequence_started'
  | 'sequence_step'
  | 'sequence_completed'
  | 'sequence_error'
  | 'sequence_cancelled'

/**
 * WebSocket message structure - matches service interface
 */
export interface WebSocketMessage {
  type: MessageType | string
  timestamp: number
  data: Record<string, unknown>
}

/**
 * Subscription filters - matches service interface
 */
export interface WebSocketFilters {
  types?: MessageType[]
  esp_ids?: string[]
  sensor_types?: string[]
  topicPattern?: string
}

/**
 * Internal subscription storage
 */
export interface WebSocketSubscription {
  filters: WebSocketFilters
  callback: (message: WebSocketMessage) => void
}

export type MessageHandler = (message: WebSocketMessage) => void

// =============================================================================
// Mock WebSocket Service
// =============================================================================

export class MockWebSocketService {
  private handlers = new Map<MessageType | string, Set<MessageHandler>>()
  private globalHandlers = new Set<MessageHandler>()
  private statusChangeCallbacks = new Set<(status: string) => void>()
  private onConnectCallbacks: Set<() => void> = new Set()
  private _isConnected = false
  private _status: 'disconnected' | 'connecting' | 'connected' | 'error' = 'disconnected'
  private _reconnectAttempts = 0
  private _lastConnectedAt: number | null = null
  private _lastDisconnectAt: number | null = null

  // Subscription management
  private subscriptions = new Map<string, WebSocketSubscription>()
  private _nextSubId = 1

  // Connection status (getter for backward compatibility)
  get connected(): boolean {
    return this._isConnected
  }

  get status(): string {
    return this._status
  }

  /**
   * Check if connected (method - matches service interface)
   */
  isConnected(): boolean {
    return this._isConnected
  }

  getStatus(): string {
    return this._status
  }

  getReconnectAttempts(): number {
    return this._reconnectAttempts
  }

  getLastConnectedAt(): number | null {
    return this._lastConnectedAt
  }

  getLastDisconnectAt(): number | null {
    return this._lastDisconnectAt
  }

  /**
   * Connect to WebSocket (mock)
   * No delay - immediate connection for fast unit tests
   */
  async connect(): Promise<void> {
    this._status = 'connecting'
    this.notifyStatusChange('connecting')
    // Immediate resolution - no delay for unit tests
    this._isConnected = true
    this._status = 'connected'
    this._reconnectAttempts = 0
    this._lastConnectedAt = Date.now()
    this._lastDisconnectAt = null
    this.notifyStatusChange('connected')
    this.onConnectCallbacks.forEach((cb) => cb())
  }

  /**
   * Register connect callback (mirrors websocket.ts onConnect).
   * Returns unsubscribe function. (AUT-837 Nebenbefund: Mock-Drift)
   */
  onConnect(callback: () => void): () => void {
    this.onConnectCallbacks.add(callback)
    return () => {
      this.onConnectCallbacks.delete(callback)
    }
  }

  /**
   * Disconnect from WebSocket (mock)
   */
  disconnect(): void {
    this._isConnected = false
    this._status = 'disconnected'
    this._reconnectAttempts = 0
    this.notifyStatusChange('disconnected')
    this.handlers.clear()
    this.globalHandlers.clear()
    this.subscriptions.clear()
  }

  /**
   * Subscribe to messages matching filters
   * Returns subscription ID for later unsubscribe
   */
  subscribe(filters: WebSocketFilters, callback: (message: WebSocketMessage) => void): string {
    const subscriptionId = `sub_${this._nextSubId++}`
    this.subscriptions.set(subscriptionId, { filters, callback })
    return subscriptionId
  }

  /**
   * Unsubscribe from messages
   */
  unsubscribe(subscriptionId: string): void {
    this.subscriptions.delete(subscriptionId)
  }

  /**
   * Subscribe to specific message type
   */
  on(type: MessageType | string, handler: MessageHandler): () => void {
    if (!this.handlers.has(type)) {
      this.handlers.set(type, new Set())
    }
    this.handlers.get(type)!.add(handler)

    // Return unsubscribe function
    return () => {
      this.handlers.get(type)?.delete(handler)
      if (this.handlers.get(type)?.size === 0) {
        this.handlers.delete(type)
      }
    }
  }

  /**
   * Register callback for connection status changes (matches service interface)
   */
  onStatusChange(callback: (status: string) => void): () => void {
    this.statusChangeCallbacks.add(callback)
    return () => {
      this.statusChangeCallbacks.delete(callback)
    }
  }

  /**
   * Subscribe to all messages
   */
  onAny(handler: MessageHandler): () => void {
    this.globalHandlers.add(handler)
    return () => {
      this.globalHandlers.delete(handler)
    }
  }

  /**
   * Simulate receiving a message (for tests)
   * Routes to both type-specific handlers AND filter-based subscriptions
   */
  simulateMessage(type: MessageType | string, data: Record<string, unknown>): void {
    const message: WebSocketMessage = {
      type,
      data,
      timestamp: Date.now()
    }

    // Call type-specific handlers
    const typeHandlers = this.handlers.get(type)
    if (typeHandlers) {
      typeHandlers.forEach((handler) => handler(message))
    }

    // Call global handlers
    this.globalHandlers.forEach((handler) => handler(message))

    // Route to filter-based subscriptions
    for (const [, subscription] of this.subscriptions.entries()) {
      if (this.matchesFilters(message, subscription.filters)) {
        subscription.callback(message)
      }
    }
  }

  /**
   * Check if message matches subscription filters
   */
  private matchesFilters(message: WebSocketMessage, filters: WebSocketFilters): boolean {
    // Type filter
    if (filters.types && filters.types.length > 0) {
      if (!filters.types.includes(message.type as MessageType)) {
        return false
      }
    }

    // ESP ID filter
    if (filters.esp_ids && filters.esp_ids.length > 0) {
      const espId = message.data.esp_id || message.data.device_id
      if (!espId || !filters.esp_ids.includes(espId as string)) {
        return false
      }
    }

    // Sensor type filter
    if (filters.sensor_types && filters.sensor_types.length > 0) {
      const sensorType = message.data.sensor_type
      if (!sensorType || !filters.sensor_types.includes(sensorType as string)) {
        return false
      }
    }

    // Topic pattern filter
    if (filters.topicPattern) {
      const topic = message.data.topic as string
      if (!topic || !topic.match(filters.topicPattern)) {
        return false
      }
    }

    return true
  }

  /**
   * Simulate connection error (for tests)
   */
  simulateError(): void {
    this._isConnected = false
    this._status = 'error'
    this._lastDisconnectAt = Date.now()
    this.notifyStatusChange('error')
  }

  /**
   * Simulate reconnection (for tests)
   */
  simulateReconnect(): void {
    this._isConnected = true
    this._status = 'connected'
    this._reconnectAttempts = 0
    this._lastConnectedAt = Date.now()
    this._lastDisconnectAt = null
    this.notifyStatusChange('connected')
    this.onConnectCallbacks.forEach((cb) => cb())
  }

  /**
   * Abnormal disconnect with pending reconnect attempts (AUT-200 tests)
   */
  simulateAbnormalDisconnectState(attempts: number): void {
    this._isConnected = false
    this._status = 'disconnected'
    this._reconnectAttempts = attempts
    this._lastDisconnectAt = Date.now()
    this.notifyStatusChange('disconnected')
  }

  /**
   * Connecting state with prior attempt counter (backoff / retry UI)
   */
  simulateConnectingWithAttempts(attempts: number): void {
    this._isConnected = false
    this._status = 'connecting'
    this._reconnectAttempts = attempts
    this.notifyStatusChange('connecting')
  }

  /**
   * Notify all status change callbacks
   */
  private notifyStatusChange(status: string): void {
    this.statusChangeCallbacks.forEach(callback => {
      try { callback(status) } catch { /* ignore */ }
    })
  }

  /**
   * Get handler count (for assertions)
   */
  getHandlerCount(type?: MessageType | string): number {
    if (type) {
      return this.handlers.get(type)?.size || 0
    }
    let total = this.globalHandlers.size
    this.handlers.forEach((handlers) => {
      total += handlers.size
    })
    return total
  }

  /**
   * Get subscription count (for assertions)
   */
  getSubscriptionCount(): number {
    return this.subscriptions.size
  }

  /**
   * Get subscription by ID (for assertions)
   */
  getSubscription(subscriptionId: string): WebSocketSubscription | undefined {
    return this.subscriptions.get(subscriptionId)
  }

  /**
   * Reset (for cleanup between tests)
   */
  reset(): void {
    this.handlers.clear()
    this.globalHandlers.clear()
    this.statusChangeCallbacks.clear()
    this.onConnectCallbacks.clear()
    this.subscriptions.clear()
    this._isConnected = false
    this._status = 'disconnected'
    this._reconnectAttempts = 0
    this._lastConnectedAt = null
    this._lastDisconnectAt = null
    this._nextSubId = 1
  }
}

// =============================================================================
// Singleton Mock Instance
// =============================================================================

export const mockWebSocketService = new MockWebSocketService()

// =============================================================================
// Factory for vi.mock
// =============================================================================

/**
 * Creates a mock module for the WebSocket service.
 * Use with: vi.mock('@/services/websocket', () => createWebSocketMock())
 *
 * Exports match the real websocket.ts module exports
 */
export function createWebSocketMock() {
  return {
    default: mockWebSocketService,
    websocketService: mockWebSocketService,
    WebSocketService: {
      getInstance: () => mockWebSocketService
    },
    // Re-export types for proper typing in tests
    WebSocketMessage: {} as WebSocketMessage,
    WebSocketFilters: {} as WebSocketFilters
  }
}

// =============================================================================
// Test Helpers
// =============================================================================

/**
 * Simulates a sensor data event
 */
export function simulateSensorData(
  espId: string,
  gpio: number,
  value: number,
  options: {
    unit?: string
    quality?: 'excellent' | 'good' | 'fair' | 'poor' | 'error'
    sensorType?: string
  } = {}
): void {
  mockWebSocketService.simulateMessage('sensor_data', {
    esp_id: espId,
    gpio,
    sensor_type: options.sensorType || 'ds18b20',
    value,
    unit: options.unit || '°C',
    quality: options.quality || 'excellent'
  })
}

/**
 * Simulates an ESP health event
 */
export function simulateEspHealth(
  espId: string,
  status: 'online' | 'offline',
  options: {
    heapFree?: number
    wifiRssi?: number
    uptime?: number
  } = {}
): void {
  mockWebSocketService.simulateMessage('esp_health', {
    esp_id: espId,
    status,
    heap_free: options.heapFree || 128000,
    wifi_rssi: options.wifiRssi || -65,
    uptime: options.uptime || 3600
  })
}

/**
 * Simulates an actuator status event
 */
export function simulateActuatorStatus(
  espId: string,
  gpio: number,
  state: 'on' | 'off',
  options: {
    pwmValue?: number
    actuatorType?: string
  } = {}
): void {
  mockWebSocketService.simulateMessage('actuator_status', {
    esp_id: espId,
    gpio,
    actuator_type: options.actuatorType || 'relay',
    state,
    pwm_value: options.pwmValue
  })
}

/**
 * Simulates a config response event
 */
export function simulateConfigResponse(
  espId: string,
  configType: 'sensor' | 'actuator',
  status: 'success' | 'partial_success' | 'error',
  options: {
    count?: number
    message?: string
    errorCode?: number
  } = {}
): void {
  mockWebSocketService.simulateMessage('config_response', {
    esp_id: espId,
    config_type: configType,
    status,
    count: options.count || 1,
    message: options.message || 'Configuration applied',
    error_code: options.errorCode
  })
}

/**
 * Simulates a logic execution event
 */
export function simulateLogicExecution(
  ruleId: string,
  ruleName: string,
  success: boolean,
  options: {
    trigger?: string
    action?: string
  } = {}
): void {
  mockWebSocketService.simulateMessage('logic_execution', {
    rule_id: ruleId,
    rule_name: ruleName,
    success,
    trigger: options.trigger || 'sensor_threshold',
    action: options.action || 'actuator_on'
  })
}

/**
 * Simulates a device discovered event
 */
export function simulateDeviceDiscovered(
  deviceId: string,
  options: {
    heapFree?: number
    wifiRssi?: number
    sensorCount?: number
    actuatorCount?: number
  } = {}
): void {
  mockWebSocketService.simulateMessage('device_discovered', {
    device_id: deviceId,
    esp_id: deviceId,
    discovered_at: new Date().toISOString(),
    heap_free: options.heapFree || 128000,
    wifi_rssi: options.wifiRssi || -65,
    sensor_count: options.sensorCount || 0,
    actuator_count: options.actuatorCount || 0
  })
}

/**
 * Simulates an error event
 */
export function simulateErrorEvent(
  espId: string,
  errorCode: number,
  message: string,
  options: {
    category?: string
    recoverable?: boolean
    userActionRequired?: boolean
  } = {}
): void {
  mockWebSocketService.simulateMessage('error_event', {
    esp_id: espId,
    error_code: errorCode,
    message,
    category: options.category || 'general',
    recoverable: options.recoverable ?? true,
    user_action_required: options.userActionRequired ?? false
  })
}
