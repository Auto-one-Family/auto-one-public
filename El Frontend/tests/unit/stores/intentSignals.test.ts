import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useIntentSignalsStore } from '@/shared/stores/intentSignals.store'

describe('intentSignals store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('lifecycle then terminal outcome clears lifecycle summary', () => {
    const s = useIntentSignalsStore()
    s.ingestLifecycle(
      { esp_id: 'ESP_1', event_type: 'pending', reason_code: 'WAIT' },
      'corr-a',
    )
    expect(s.getDisplayForEsp('ESP_1')?.lifecycleSummary).toContain('Zwischenstand')
    s.ingestOutcome({
      esp_id: 'ESP_1',
      flow: 'config',
      outcome: 'persisted',
      is_final: true,
      correlation_id: 'corr-b',
      code: 'OK',
    })
    const d = s.getDisplayForEsp('ESP_1')
    expect(d?.hasTerminalResult).toBe(true)
    expect(d?.lifecycleSummary).toBeNull()
    expect(d?.resultSummary).toContain('Ergebnis')
    expect(d?.firmwareCode).toBe('OK')
  })

  it('ignores lifecycle after terminal until non-terminal outcome', () => {
    const s = useIntentSignalsStore()
    s.ingestOutcome({
      esp_id: 'ESP_2',
      flow: 'command',
      outcome: 'persisted',
      is_final: true,
      correlation_id: 'c1',
    })
    s.ingestLifecycle({ esp_id: 'ESP_2', event_type: 'x', reason_code: 'y' })
    expect(s.getDisplayForEsp('ESP_2')?.lifecycleSummary).toBeNull()
    s.ingestOutcome({
      esp_id: 'ESP_2',
      flow: 'command',
      outcome: 'accepted',
      is_final: false,
      correlation_id: 'c2',
    })
    s.ingestLifecycle({ esp_id: 'ESP_2', event_type: 'boot', reason_code: 'Z' })
    expect(s.getDisplayForEsp('ESP_2')?.lifecycleSummary).toContain('boot')
  })
})
