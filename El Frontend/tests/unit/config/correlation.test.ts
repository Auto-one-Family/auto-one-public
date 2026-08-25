/**
 * Correlation ID Unit Tests
 *
 * Tests for cross-layer request tracing:
 * - Axios request interceptor adds X-Request-ID header
 * - X-Request-ID is a valid UUID v4
 * - WebSocketMessage interface includes correlation_id
 */

import { describe, it, expect, vi, beforeAll, afterAll, afterEach, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { server } from '../../mocks/server'
import { http, HttpResponse } from 'msw'
import axios from 'axios'

// Mock WebSocket service (imported by auth store)
vi.mock('@/services/websocket', () => ({
  websocketService: {
    disconnect: vi.fn(),
    connect: vi.fn(),
    isConnected: vi.fn(() => false),
    onConnect: vi.fn(() => () => {}),
    onStatusChange: vi.fn(() => () => {}),
    getStatus: vi.fn(() => 'disconnected'),
    subscribe: vi.fn(() => 'sub-corr'),
    unsubscribe: vi.fn(),
    sendClientStageObservation: vi.fn(),
  },
}))

// =============================================================================
// MSW Server Lifecycle
// =============================================================================
beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterAll(() => server.close())
afterEach(() => server.resetHandlers())

// =============================================================================
// UUID Validation Helper
// =============================================================================
const UUID_V4_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

// =============================================================================
// AXIOS X-REQUEST-ID INTERCEPTOR
// =============================================================================

describe('Axios X-Request-ID Interceptor', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  async function captureRequestId(api: { interceptors: { request: { handlers: Array<{ fulfilled?: (config: any) => any } | null> } } }) {
    const headers = new axios.AxiosHeaders()
    let config: any = { method: 'get', url: '/test', headers }
    const handlers = api.interceptors.request.handlers.filter(Boolean)
    for (let i = handlers.length - 1; i >= 0; i--) {
      const fn = handlers[i]?.fulfilled
      if (fn) config = await fn(config)
    }
    return String(config.headers?.get?.('X-Request-ID') ?? config.headers?.['X-Request-ID'] ?? '')
  }

  it('adds X-Request-ID header to every request', async () => {
    const { default: api } = await import('@/api/index')
    const capturedRequestId = await captureRequestId(api)
    expect(capturedRequestId).not.toBeNull()
    expect(capturedRequestId).toMatch(UUID_V4_REGEX)
  }, 15000)

  it('generates unique request IDs per request', async () => {
    const { default: api } = await import('@/api/index')
    const a = await captureRequestId(api)
    const b = await captureRequestId(api)
    expect(a).toBeTruthy()
    expect(b).toBeTruthy()
    expect(a).not.toBe(b)
  }, 15000)
})

// =============================================================================
// WEBSOCKET MESSAGE CORRELATION
// =============================================================================

describe('WebSocketMessage correlation_id', () => {
  it('interface accepts messages with correlation_id', () => {
    // Type-level test: ensures the interface compiles with correlation_id
    const message: import('@/services/websocket').WebSocketMessage = {
      type: 'sensor_data',
      timestamp: Date.now(),
      data: { esp_id: 'ESP_001', value: 23.5 },
      correlation_id: 'ESP_001:data:42:1708704000000',
    }

    expect(message.correlation_id).toBe('ESP_001:data:42:1708704000000')
  })

  it('interface accepts messages without correlation_id', () => {
    // correlation_id is optional — messages from non-MQTT sources omit it
    const message: import('@/services/websocket').WebSocketMessage = {
      type: 'system_status',
      timestamp: Date.now(),
      data: { status: 'ok' },
    }

    expect(message.correlation_id).toBeUndefined()
  })
})
