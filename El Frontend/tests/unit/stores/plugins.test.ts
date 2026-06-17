/**
 * Plugin Store Unit Tests
 *
 * Tests for plugin state management: fetch, execute, toggle, config update.
 * Follows existing store test patterns (auth.test.ts, esp.test.ts).
 */

import { describe, it, expect, vi, beforeAll, afterAll, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePluginsStore } from '@/shared/stores/plugins.store'
import { server } from '../../mocks/server'
import { http, HttpResponse } from 'msw'
import { mockPlugin, mockPluginDisabled, mockPluginWithSelect } from '../../mocks/handlers'

// =============================================================================
// MSW Server Lifecycle
// =============================================================================
beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterAll(() => server.close())
afterEach(() => server.resetHandlers())

// =============================================================================
// Mock Dependencies
// =============================================================================

vi.mock('@/services/websocket', () => ({
  websocketService: {
    disconnect: vi.fn(),
    connect: vi.fn(),
    isConnected: vi.fn(() => false),
    getStatus: vi.fn(() => 'disconnected'),
    onStatusChange: vi.fn(() => () => undefined),
    on: vi.fn(() => () => undefined),
    subscribe: vi.fn(() => 'sub-1'),
    unsubscribe: vi.fn(),
  },
}))

// =============================================================================
// INITIAL STATE
// =============================================================================

describe('Plugin Store - Initial State', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('has empty plugins list on initialization', () => {
    const store = usePluginsStore()
    expect(store.plugins).toEqual([])
  })

  it('has null selectedPlugin on initialization', () => {
    const store = usePluginsStore()
    expect(store.selectedPlugin).toBeNull()
  })

  it('has empty execution history on initialization', () => {
    const store = usePluginsStore()
    expect(store.executionHistory).toEqual([])
  })

  it('is not loading on initialization', () => {
    const store = usePluginsStore()
    expect(store.isLoading).toBe(false)
    expect(store.isExecuting).toBe(false)
  })
})

// =============================================================================
// FETCH PLUGINS
// =============================================================================

describe('Plugin Store - fetchPlugins', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('fetches all plugins from API', async () => {
    const store = usePluginsStore()
    await store.fetchPlugins()

    expect(store.plugins).toHaveLength(3)
    expect(store.plugins[0].plugin_id).toBe('health_check')
    expect(store.plugins[1].plugin_id).toBe('system_cleanup')
    expect(store.plugins[2].plugin_id).toBe('esp_configurator')
  })

  it('sets isLoading during fetch', async () => {
    const store = usePluginsStore()
    expect(store.isLoading).toBe(false)

    const promise = store.fetchPlugins()
    expect(store.isLoading).toBe(true)

    await promise
    expect(store.isLoading).toBe(false)
  })

  it('handles API errors gracefully', async () => {
    server.use(
      http.get('/api/v1/plugins', () => {
        return HttpResponse.json({ detail: 'Server error' }, { status: 500 })
      }),
    )

    const store = usePluginsStore()
    await store.fetchPlugins()

    expect(store.plugins).toEqual([])
    expect(store.isLoading).toBe(false)
  })
})

// =============================================================================
// COMPUTED GETTERS
// =============================================================================

describe('Plugin Store - Computed Getters', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('enabledPlugins filters correctly', async () => {
    const store = usePluginsStore()
    await store.fetchPlugins()

    expect(store.enabledPlugins).toHaveLength(2)
    expect(store.enabledPlugins.every(p => p.is_enabled)).toBe(true)
  })

  it('disabledPlugins filters correctly', async () => {
    const store = usePluginsStore()
    await store.fetchPlugins()

    expect(store.disabledPlugins).toHaveLength(1)
    expect(store.disabledPlugins[0].plugin_id).toBe('system_cleanup')
  })

  it('pluginsByCategory groups correctly', async () => {
    const store = usePluginsStore()
    await store.fetchPlugins()

    const grouped = store.pluginsByCategory
    expect(grouped['monitoring']).toHaveLength(1)
    expect(grouped['maintenance']).toHaveLength(1)
    expect(grouped['automation']).toHaveLength(1)
  })

  it('pluginOptions maps plugin_id to value', async () => {
    const store = usePluginsStore()
    await store.fetchPlugins()

    expect(store.pluginOptions).toHaveLength(3)
    expect(store.pluginOptions[0]).toEqual({
      value: 'health_check',
      label: 'Health Check',
      disabled: false,
    })
  })

  it('pluginOptions marks disabled plugins', async () => {
    const store = usePluginsStore()
    await store.fetchPlugins()

    const disabledOption = store.pluginOptions.find(o => o.value === 'system_cleanup')
    expect(disabledOption?.disabled).toBe(true)
  })
})

// =============================================================================
// EXECUTE PLUGIN
// =============================================================================

describe('Plugin Store - executePlugin', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('executes a plugin and returns execution result', async () => {
    const store = usePluginsStore()
    const result = await store.executePlugin('health_check')

    expect(result).not.toBeNull()
    expect(result?.status).toBe('success')
    expect(result?.plugin_id).toBe('health_check')
  })

  it('sets isExecuting during execution', async () => {
    const store = usePluginsStore()
    expect(store.isExecuting).toBe(false)

    const promise = store.executePlugin('health_check')
    expect(store.isExecuting).toBe(true)

    await promise
    expect(store.isExecuting).toBe(false)
  })

  it('returns null on execution failure', async () => {
    server.use(
      http.post('/api/v1/plugins/:pluginId/execute', () => {
        return HttpResponse.json({ detail: 'Execution failed' }, { status: 500 })
      }),
    )

    const store = usePluginsStore()
    const result = await store.executePlugin('health_check')

    expect(result).toBeNull()
    expect(store.isExecuting).toBe(false)
  })
})

// =============================================================================
// TOGGLE PLUGIN
// =============================================================================

describe('Plugin Store - togglePlugin', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('enables a disabled plugin', async () => {
    const store = usePluginsStore()
    await store.fetchPlugins()

    const before = store.plugins.find(p => p.plugin_id === 'system_cleanup')
    expect(before?.is_enabled).toBe(false)

    await store.togglePlugin('system_cleanup', true)

    const after = store.plugins.find(p => p.plugin_id === 'system_cleanup')
    expect(after?.is_enabled).toBe(true)
  })

  it('disables an enabled plugin', async () => {
    const store = usePluginsStore()
    await store.fetchPlugins()

    await store.togglePlugin('health_check', false)

    const plugin = store.plugins.find(p => p.plugin_id === 'health_check')
    expect(plugin?.is_enabled).toBe(false)
  })
})

// =============================================================================
// UPDATE CONFIG
// =============================================================================

describe('Plugin Store - updateConfig', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('updates plugin config in local state', async () => {
    const store = usePluginsStore()
    await store.fetchPlugins()

    const newConfig = { include_containers: false, alert_on_degraded: true }
    await store.updateConfig('health_check', newConfig)

    const plugin = store.plugins.find(p => p.plugin_id === 'health_check')
    expect(plugin?.config).toEqual(newConfig)
  })
})

// =============================================================================
// FETCH PLUGIN DETAIL
// =============================================================================

describe('Plugin Store - fetchPluginDetail', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('fetches plugin detail with recent executions', async () => {
    const store = usePluginsStore()
    await store.fetchPluginDetail('health_check')

    expect(store.selectedPlugin).not.toBeNull()
    expect(store.selectedPlugin?.plugin_id).toBe('health_check')
    expect(store.selectedPlugin?.recent_executions).toHaveLength(1)
  })

  it('handles not found plugin', async () => {
    server.use(
      http.get('/api/v1/plugins/:pluginId', () => {
        return HttpResponse.json({ detail: 'Not found' }, { status: 404 })
      }),
    )

    const store = usePluginsStore()
    await store.fetchPluginDetail('nonexistent')

    expect(store.selectedPlugin).toBeNull()
  })
})

// =============================================================================
// FETCH HISTORY
// =============================================================================

describe('Plugin Store - fetchHistory', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('fetches execution history for a plugin', async () => {
    const store = usePluginsStore()
    await store.fetchHistory('health_check')

    expect(store.executionHistory).toHaveLength(1)
    expect(store.executionHistory[0].status).toBe('success')
  })

  it('returns empty array for plugin with no history', async () => {
    const store = usePluginsStore()
    await store.fetchHistory('system_cleanup')

    expect(store.executionHistory).toEqual([])
  })
})
