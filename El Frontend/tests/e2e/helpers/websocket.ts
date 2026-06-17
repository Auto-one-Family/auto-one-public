/**
 * WebSocket Helper for Playwright E2E Tests
 *
 * Provides utilities to intercept and wait for WebSocket messages
 * during browser-based E2E testing.
 *
 * WebSocket URL pattern: /api/v1/ws/realtime/{client_id}?token={jwt_token}
 */

import { Page, WebSocket } from '@playwright/test'

/**
 * WebSocket message structure (from backend)
 */
export interface WebSocketMessage {
  type: string
  timestamp: number
  data: Record<string, unknown>
}

/**
 * WebSocket helper for E2E tests
 */
export interface WebSocketHelper {
  /** All received messages */
  messages: WebSocketMessage[]

  /** Wait for a message of specific type */
  waitForMessage: (type: string, timeout?: number) => Promise<WebSocketMessage>

  /** Wait for message matching predicate */
  waitForMessageMatching: (
    predicate: (msg: WebSocketMessage) => boolean,
    timeout?: number
  ) => Promise<WebSocketMessage>

  /** Clear message buffer */
  clearMessages: () => void

  /** Get last message of type */
  getLastMessage: (type: string) => WebSocketMessage | undefined

  /** Check if connected */
  isConnected: () => boolean

  /** Wait for WebSocket to be connected (call after page load) */
  waitForConnection: (timeoutMs?: number) => Promise<void>
}

/**
 * Create a WebSocket helper for the given page
 *
 * Usage:
 * ```ts
 * const wsHelper = await createWebSocketHelper(page)
 * await page.goto('/dashboard')
 *
 * // Trigger MQTT event...
 *
 * const msg = await wsHelper.waitForMessage('device.online')
 * expect(msg.data.esp_id).toBe('ESP_12AB34CD')
 * ```
 */
export async function createWebSocketHelper(page: Page): Promise<WebSocketHelper> {
  const messages: WebSocketMessage[] = []
  let currentWs: WebSocket | null = null
  const pendingWaiters: Array<{
    resolve: (msg: WebSocketMessage) => void
    predicate: (msg: WebSocketMessage) => boolean
    timer: ReturnType<typeof setTimeout>
  }> = []

  // Listen for WebSocket connections
  page.on('websocket', (ws) => {
    const url = ws.url()

    // Match our WebSocket endpoint: /api/v1/ws/realtime/
    if (url.includes('/api/v1/ws/realtime/')) {
      console.log(`[WS Helper] Connected to ${url}`)
      currentWs = ws

      // Handle incoming messages
      ws.on('framereceived', (frame) => {
        try {
          const msg: WebSocketMessage = JSON.parse(frame.payload as string)
          console.log(`[WS Helper] Received: ${msg.type}`, msg.data)
          messages.push(msg)

          // Check pending waiters
          for (let i = pendingWaiters.length - 1; i >= 0; i--) {
            const waiter = pendingWaiters[i]
            if (waiter.predicate(msg)) {
              clearTimeout(waiter.timer)
              waiter.resolve(msg)
              pendingWaiters.splice(i, 1)
            }
          }
        } catch (error) {
          console.log('[WS Helper] Failed to parse message:', frame.payload)
        }
      })

      ws.on('close', () => {
        console.log('[WS Helper] WebSocket closed')
        currentWs = null
      })
    }
  })

  return {
    messages,

    async waitForMessage(type: string, timeout = 10000): Promise<WebSocketMessage> {
      return this.waitForMessageMatching((msg) => msg.type === type, timeout)
    },

    async waitForMessageMatching(
      predicate: (msg: WebSocketMessage) => boolean,
      timeout = 10000
    ): Promise<WebSocketMessage> {
      // Check already received messages first
      const existing = messages.find(predicate)
      if (existing) {
        return existing
      }

      // Wait for new message
      return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
          const index = pendingWaiters.findIndex((w) => w.resolve === resolve)
          if (index !== -1) {
            pendingWaiters.splice(index, 1)
          }
          reject(new Error(`Timeout waiting for WebSocket message (${timeout}ms)`))
        }, timeout)

        pendingWaiters.push({
          resolve,
          predicate,
          timer,
        })
      })
    },

    clearMessages(): void {
      messages.length = 0
    },

    getLastMessage(type: string): WebSocketMessage | undefined {
      for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i].type === type) {
          return messages[i]
        }
      }
      return undefined
    },

    isConnected(): boolean {
      return currentWs !== null && !currentWs.isClosed()
    },

    async waitForConnection(timeoutMs = 10000): Promise<void> {
      const start = Date.now()
      while (Date.now() - start < timeoutMs) {
        if (this.isConnected()) return
        await new Promise((r) => setTimeout(r, 100))
      }
      throw new Error(`WebSocket did not connect within ${timeoutMs}ms`)
    },
  }
}

/**
 * Common WebSocket message types (from backend)
 *
 * Must match server broadcast events (WEBSOCKET_EVENTS.md):
 * - device_discovered, esp_health (not device.online)
 * - actuator_alert (not actuator.alert)
 * - sensor_data (not sensor.data)
 */
export const WS_MESSAGE_TYPES = {
  // Device events (server uses underscore naming)
  DEVICE_DISCOVERED: 'device_discovered',
  DEVICE_ONLINE: 'esp_health', // online heartbeat update
  DEVICE_OFFLINE: 'esp_health', // status: offline in data
  DEVICE_UPDATED: 'device_updated',
  DEVICE_APPROVED: 'device_approved',
  DEVICE_REJECTED: 'device_rejected',

  // Sensor events
  SENSOR_DATA: 'sensor_data',
  SENSOR_ALERT: 'sensor_alert',
  SENSOR_HEALTH: 'sensor_health',

  // Actuator events
  ACTUATOR_STATE: 'actuator_status',
  ACTUATOR_COMMAND: 'actuator_command',
  ACTUATOR_RESPONSE: 'actuator_response',
  ACTUATOR_ALERT: 'actuator_alert',

  // System events (emergency uses actuator_alert with alert_type)
  EMERGENCY_STOP: 'actuator_alert', // msg.data.alert_type === 'emergency_stop'
  EMERGENCY_CLEAR: 'emergency.clear',
  SYSTEM_STATUS: 'system.status',
} as const

export type WebSocketMessageType = (typeof WS_MESSAGE_TYPES)[keyof typeof WS_MESSAGE_TYPES]
