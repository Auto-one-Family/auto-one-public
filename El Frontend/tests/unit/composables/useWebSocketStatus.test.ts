import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { nextTick } from 'vue'
import { mockWebSocketService, createWebSocketMock } from '../../mocks/websocket'

vi.mock('@/services/websocket', () => createWebSocketMock())

import { useWebSocketStatus } from '@/composables/useWebSocketStatus'

describe('useWebSocketStatus', () => {
  const cleanups: Array<() => void> = []

  beforeEach(() => {
    vi.useFakeTimers()
    mockWebSocketService.reset()
    cleanups.length = 0
  })

  afterEach(() => {
    cleanups.forEach((fn) => fn())
    cleanups.length = 0
    vi.clearAllTimers()
    vi.useRealTimers()
  })

  it('reflects connected state after mock connect', async () => {
    const s = useWebSocketStatus()
    cleanups.push(s.stop)
    await mockWebSocketService.connect()
    await nextTick()
    expect(s.isConnected.value).toBe(true)
    expect(s.status.value).toBe('connected')
    expect(s.reconnectAttempts.value).toBe(0)
    expect(s.lastConnected.value).not.toBeNull()
    expect(s.lastDisconnectAt.value).toBeNull()
  })

  it('tracks connecting with prior attempts via status callback', async () => {
    const s = useWebSocketStatus()
    cleanups.push(s.stop)
    mockWebSocketService.simulateConnectingWithAttempts(2)
    await nextTick()
    expect(s.status.value).toBe('connecting')
    expect(s.reconnectAttempts.value).toBe(2)
    expect(s.showReconnectingUi.value).toBe(true)
  })

  it('tracks abnormal disconnect timestamp and attempts', async () => {
    const s = useWebSocketStatus()
    cleanups.push(s.stop)
    mockWebSocketService.simulateAbnormalDisconnectState(3)
    await nextTick()
    expect(s.lastDisconnectAt.value).not.toBeNull()
    expect(s.reconnectAttempts.value).toBe(3)
    expect(s.isConnected.value).toBe(false)
  })

  it('maps error status with disconnect metadata', async () => {
    const s = useWebSocketStatus()
    cleanups.push(s.stop)
    await mockWebSocketService.connect()
    mockWebSocketService.simulateError()
    await nextTick()
    expect(s.status.value).toBe('error')
    expect(s.isDegraded.value).toBe(true)
    expect(s.lastDisconnectAt.value).not.toBeNull()
  })
})
