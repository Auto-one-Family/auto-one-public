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

// Mock WebSocket service (imported by auth store)
vi.mock('@/services/websocket', () => ({
  websocketService: {
    disconnect: vi.fn(),
    connect: vi.fn(),
    isConnected: vi.fn(() => false),
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

  it('adds X-Request-ID header to every request', async () => {
    let capturedRequestId: string | null = null

    // Intercept the request to capture the header
    server.use(
      http.get('/api/v1/test', ({ request }) => {
        capturedRequestId = request.headers.get('X-Request-ID')
        return HttpResponse.json({ ok: true })
      }),
    )

    const { default: api } = await import('@/api/index')
    await api.get('/test')

    expect(capturedRequestId).not.toBeNull()
    expect(capturedRequestId).toMatch(UUID_V4_REGEX)
  })

  it('generates unique request IDs per request', async () => {
    const capturedIds: string[] = []

    server.use(
      http.get('/api/v1/unique-test', ({ request }) => {
        const rid = request.headers.get('X-Request-ID')
        if (rid) capturedIds.push(rid)
        return HttpResponse.json({ ok: true })
      }),
    )

    const { default: api } = await import('@/api/index')
    await api.get('/unique-test')
    await api.get('/unique-test')

    expect(capturedIds).toHaveLength(2)
    expect(capturedIds[0]).not.toBe(capturedIds[1])
  })
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
