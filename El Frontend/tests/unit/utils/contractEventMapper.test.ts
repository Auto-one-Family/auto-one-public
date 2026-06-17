import { describe, expect, it } from 'vitest'
import {
  buildContractIntegritySignal,
  CONTRACT_OPERATOR_ACTION,
  extractIntegrationIssueSnapshot,
  extractCorrelationId,
  extractEspId,
  extractRequestId,
  getDataSourceForEventType,
  inferFallbackSeverity,
  INTENT_CONTRACT_INVENTORY,
  validateContractEvent,
} from '@/utils/contractEventMapper'

describe('contractEventMapper', () => {
  it('validates known actuator contract event as ok', () => {
    const result = validateContractEvent('actuator_response', {
      esp_id: 'ESP_0001',
      gpio: 5,
      success: true,
      command: 'ON',
    })
    expect(result.kind).toBe('ok')
  })

  it('reports unknown websocket event types', () => {
    const result = validateContractEvent('future_event', {})
    expect(result.kind).toBe('unknown_event')
  })

  it('accepts documented server broadcasts omitted from whitelist previously (AUT-111 / backup)', () => {
    expect(
      validateContractEvent('rule_degraded', {
        rule_id: 'uuid',
      }).kind,
    ).toBe('ok')
    expect(
      validateContractEvent('rule_recovered', {
        rule_id: 'uuid',
      }).kind,
    ).toBe('ok')
    expect(
      validateContractEvent('events_restored', {
        backup_id: 'b1',
        restored_count: 3,
        event_ids: ['e1'],
        message: 'ok',
      }).kind,
    ).toBe('ok')
    expect(
      validateContractEvent('esp_reconnect_phase', {
        esp_id: 'ESP_1',
        phase: 'adopt',
        timestamp: Date.now(),
      }).kind,
    ).toBe('ok')
  })

  it('reports actuator schema mismatch with concrete reason', () => {
    const result = validateContractEvent('actuator_response', {
      esp_id: 'ESP_0001',
      gpio: 5,
      command: 'ON',
    })
    expect(result.kind).toBe('mismatch')
    if (result.kind === 'mismatch') {
      expect(result.reason).toContain('success-Boolean')
    }
  })

  it('treats terminal config events without correlation_id as mismatch', () => {
    const result = validateContractEvent('config_response', {
      esp_id: 'ESP_0001',
      status: 'success',
    })
    expect(result.kind).toBe('mismatch')
    if (result.kind === 'mismatch') {
      expect(result.reason).toContain('correlation_id')
    }
  })

  it('maps datasource for lifecycle events', () => {
    expect(getDataSourceForEventType('actuator_command')).toBe('actuators')
    expect(getDataSourceForEventType('config_published')).toBe('audit_log')
    expect(getDataSourceForEventType('sensor_data')).toBe('sensor_data')
  })

  it('extracts correlation/request ids and esp id safely', () => {
    const data = {
      device_id: 'ESP_0099',
      correlation_id: 'corr-1',
      request_id: 'req-1',
    }
    expect(extractEspId(data)).toBe('ESP_0099')
    expect(extractCorrelationId(data)).toBe('corr-1')
    expect(extractRequestId(data)).toBe('req-1')
  })

  it('exposes intent contract inventory for actuator/config/sequence', () => {
    expect(INTENT_CONTRACT_INVENTORY.actuator.wsTerminalEvents).toContain('actuator_response')
    expect(INTENT_CONTRACT_INVENTORY.config.wsTerminalEvents).toContain('config_response')
    expect(INTENT_CONTRACT_INVENTORY.sequence.wsProgressEvents).toContain('sequence_step')
  })

  it('builds centralized integration signal payload for schema mismatch', () => {
    const signal = buildContractIntegritySignal({
      kind: 'mismatch',
      incomingEventType: 'actuator_response',
      reason: 'actuator_response ohne success-Boolean',
      incomingData: { esp_id: 'ESP_0001', gpio: 5 },
      correlationId: 'corr-1',
      requestId: 'req-1',
    })

    expect(signal.eventType).toBe('contract_mismatch')
    expect(signal.message).toContain('Integrationsstoerung')
    expect(signal.data.contract_issue).toBe('schema_mismatch')
    expect(signal.data.operator_action).toBe(CONTRACT_OPERATOR_ACTION)
    expect(signal.data.raw_context).toBeDefined()
  })

  it('extracts integration snapshot from contract events', () => {
    const snapshot = extractIntegrationIssueSnapshot({
      event_type: 'contract_unknown_event',
      correlation_id: 'corr-2',
      request_id: 'req-2',
      data: {
        contract_issue: 'unknown_event_type',
        original_event_type: 'future_event',
        mismatch_reason: 'Unbekannter Event-Typ "future_event"',
        operator_action: 'Contract-Pruefung erforderlich',
        raw_context: { event_type: 'future_event', payload: {} },
      },
    })

    expect(snapshot.isIntegrationIssue).toBe(true)
    expect(snapshot.issueType).toBe('unknown_event_type')
    expect(snapshot.originalEventType).toBe('future_event')
    expect(snapshot.operatorAction).toBe(CONTRACT_OPERATOR_ACTION)
    expect(snapshot.rawContext).toBeDefined()
  })

  it('infers fallback severity for events without server severity', () => {
    expect(inferFallbackSeverity('actuator_response', { success: false })).toBe('error')
    expect(inferFallbackSeverity('sensor_health', { status: 'stale' })).toBe('warning')
    expect(inferFallbackSeverity('system_event', { event_type: 'sync_warning' })).toBe('warning')
    expect(inferFallbackSeverity('device_online', {})).toBe('info')
    expect(inferFallbackSeverity('rule_degraded', {})).toBe('warning')
    expect(inferFallbackSeverity('rule_recovered', {})).toBe('info')
    expect(inferFallbackSeverity('events_restored', {})).toBe('info')
  })
})
