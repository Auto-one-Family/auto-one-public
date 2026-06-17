import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useOpsLifecycleStore } from '@/shared/stores/ops-lifecycle.store'

describe('OpsLifecycle Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('erstellt initiated Eintrag und setzt running/success', () => {
    const store = useOpsLifecycleStore()
    const id = store.startLifecycle({
      scope: 'plugin_execute',
      title: 'Plugin-Ausführung',
      risk: 'high',
      execution_id: 'exec-123',
    })

    expect(store.entries).toHaveLength(1)
    expect(store.entries[0].status).toBe('initiated')

    store.markRunning(id, 'läuft')
    expect(store.entries[0].status).toBe('running')

    store.markSuccess(id, 'ok')
    expect(store.entries[0].status).toBe('success')
    expect(store.entries[0].finished_at).toBeTruthy()
  })

  it('mapped externe Status über execution_id korrekt', () => {
    const store = useOpsLifecycleStore()
    store.startLifecycle({
      id: 'plugin_exec_exec-999',
      scope: 'plugin_execute',
      title: 'Plugin-Ausführung',
      risk: 'high',
      execution_id: 'exec-999',
    })

    store.updateByExecutionId('exec-999', 'running', { summary: 'ack running' })
    expect(store.entries[0].status).toBe('running')
    expect(store.entries[0].summary).toBe('ack running')

    store.updateByExecutionId('exec-999', 'timeout', { reason_text: 'kein ack' })
    expect(store.entries[0].status).toBe('failed')
    expect(store.entries[0].reason_text).toBe('kein ack')
  })
})
