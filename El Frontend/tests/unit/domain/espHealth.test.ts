import { describe, it, expect } from 'vitest'
import { espHealthPresentation, normalizeEspHealthPayload } from '@/domain/esp/espHealth'

describe('normalizeEspHealthPayload', () => {
  it('maps degradation flags and keeps extra telemetry', () => {
    const vm = normalizeEspHealthPayload({
      esp_id: 'ESP_X',
      status: 'online',
      persistence_degraded: true,
      persistence_degraded_reason: 'flash_busy',
      network_degraded: false,
      metrics_schema_version: 2,
      custom_fw_counter: 3,
    })
    expect(vm.persistenceDegraded).toBe(true)
    expect(vm.persistenceDegradedReason).toBe('flash_busy')
    expect(vm.networkDegraded).toBe(false)
    expect(vm.rawTelemetry.metrics_schema_version).toBe(2)
    expect(vm.rawTelemetry.custom_fw_counter).toBe(3)
    expect(vm.rawTelemetry.persistence_degraded).toBeUndefined()
  })

  it('excludes metrics_delta_ts and metrics_freshness_seconds from rawTelemetry', () => {
    const vm = normalizeEspHealthPayload({
      esp_id: 'ESP_X',
      status: 'online',
      metrics_delta_ts: 1714000000,
      metrics_freshness_seconds: 12,
      custom_fw_counter: 5,
    })
    expect(vm.rawTelemetry.metrics_delta_ts).toBeUndefined()
    expect(vm.rawTelemetry.metrics_freshness_seconds).toBeUndefined()
    expect(vm.rawTelemetry.custom_fw_counter).toBe(5)
  })

  it('handles payload with no timestamp (backward compat)', () => {
    const vm = normalizeEspHealthPayload({
      esp_id: 'ESP_X',
      status: 'online',
      heap_free: 120000,
    })
    expect(vm.persistenceDegraded).toBe(false)
    expect(vm.rawTelemetry.esp_id).toBeUndefined()
    expect(vm.rawTelemetry.heap_free).toBeUndefined()
  })
})

describe('espHealthPresentation', () => {
  it('shows warning badge when online and degraded', () => {
    const vm = normalizeEspHealthPayload({
      esp_id: 'ESP_X',
      persistence_degraded: true,
    })
    const p = espHealthPresentation(vm, true)
    expect(p.showBadge).toBe(true)
    expect(p.severity).toBe('warning')
    expect(p.tooltipLines.some(l => l.includes('Persistenz'))).toBe(true)
  })

  it('does not show degradation badge when device not reported online', () => {
    const vm = normalizeEspHealthPayload({ esp_id: 'ESP_X', persistence_degraded: true })
    const p = espHealthPresentation(vm, false)
    expect(p.showBadge).toBe(false)
  })

  it('maps degraded reason codes to operator-focused cause and action', () => {
    const vm = normalizeEspHealthPayload({
      esp_id: 'ESP_X',
      degraded_reason_codes: ['mqtt_disconnected'],
    })
    const p = espHealthPresentation(vm, true)
    expect(p.tooltipLines.some(l => l.includes('MQTT-Verbindung'))).toBe(true)
    expect(p.recommendedAction).toContain('MQTT-Broker')
  })

  it('prioritizes circuit-breaker action over generic runtime hints', () => {
    const vm = normalizeEspHealthPayload({
      esp_id: 'ESP_X',
      runtime_state_degraded: true,
      mqtt_circuit_breaker_open: true,
    })
    const p = espHealthPresentation(vm, true)
    expect(p.tooltipLines.some(l => l.includes('MQTT-Circuit-Breaker offen'))).toBe(true)
    expect(p.recommendedAction).toContain('automatische Recovery')
  })

  it('includes handover conflict details in the operator tooltip', () => {
    const vm = normalizeEspHealthPayload({
      esp_id: 'ESP_X',
      handover_contract_reject_startup: 2,
      handover_contract_reject_runtime: 1,
      handover_epoch: 7,
    })
    const p = espHealthPresentation(vm, true)
    expect(p.tooltipLines.some(l => l.includes('Übergabe-Konflikte'))).toBe(true)
    expect(p.tooltipLines.some(l => l.includes('Epoche 7'))).toBe(true)
  })
})
