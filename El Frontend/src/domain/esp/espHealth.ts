/**
 * esp_health payload normalization (P0-C).
 * Server spreads runtime_telemetry keys flat into WebSocket data (event_contract_serializers).
 */

export interface EspHealthViewModel {
  persistenceDegraded: boolean
  persistenceDegradedReason: string | null
  runtimeStateDegraded: boolean
  networkDegraded: boolean
  mqttCircuitBreakerOpen: boolean
  wifiCircuitBreakerOpen: boolean
  /**
   * Aggregated runtime-degradation marker from backend (AUT-124).
   * When true, the device is operationally degraded; the primary reason is in `degradedReason`.
   */
  degraded: boolean
  /** Primary degradation reason code (machine-readable, e.g. 'mqtt_disconnected'). */
  degradedReason: string | null
  /** Additional reason codes contributing to the degraded state. */
  degradedReasonCodes: string[]
  handover: {
    epoch: number | null
    rejectStartup: number
    rejectRuntime: number
    rejectTotal: number
  }
  /** AUT-133: Heartbeat counter indicators surfaced as structured ViewModel fields. */
  metrics: {
    criticalOutcomeDropCount: number
    publishOutboxDropCount: number
    persistenceDriftCount: number
    heartbeatDegradedCount: number
    publishQueueDropCount: number
  }
  /** Telemetry keys not mapped above (debug / forward-compatible) */
  rawTelemetry: Record<string, unknown>
}

/** In ViewModel als booleans/sparse Felder gemappt — nicht doppelt in rawTelemetry */
const MAPPED_TELEMETRY_FLAG_KEYS = new Set([
  'persistence_degraded',
  'persistence_degraded_reason',
  'runtime_state_degraded',
  'network_degraded',
  'mqtt_circuit_breaker_open',
  'wifi_circuit_breaker_open',
  'handover_contract_reject_startup',
  'handover_contract_reject_runtime',
  'handover_contract_reject',
  'handover_epoch',
  'session_epoch',
  // AUT-124: aggregated degradation fields
  'degraded',
  'degraded_reason',
  'degraded_reason_codes',
  // AUT-133: heartbeat counter indicators
  'critical_outcome_drop_count',
  'publish_outbox_drop_count',
  'persistence_drift_count',
  'heartbeat_degraded_count',
  'publish_queue_drop_count',
  'safe_publish_retry_count',
])

const STANDARD_TOP_LEVEL_KEYS = new Set([
  'esp_id',
  'device_id',
  'status',
  'timestamp',
  'last_seen',
  'uptime',
  'heap_free',
  'wifi_rssi',
  'sensor_count',
  'actuator_count',
  'name',
  'source',
  'reason',
  'gpio_status',
  'actuator_states_reset',
  'ip_address',
  'connected',
  'system_state',
  'metrics_delta_ts',
  'metrics_freshness_seconds',
])

function asBool(v: unknown): boolean {
  return v === true || v === 'true'
}

function asStr(v: unknown): string | null {
  return typeof v === 'string' && v.trim().length > 0 ? v : null
}

function asNum(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string' && v.trim().length > 0) {
    const parsed = Number(v)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

export function normalizeEspHealthPayload(raw: Record<string, unknown>): EspHealthViewModel {
  const rawTelemetry: Record<string, unknown> = {}

  for (const [key, value] of Object.entries(raw)) {
    if (STANDARD_TOP_LEVEL_KEYS.has(key) || MAPPED_TELEMETRY_FLAG_KEYS.has(key)) continue
    rawTelemetry[key] = value
  }

  const rejectStartup = asNum(raw.handover_contract_reject_startup) ?? 0
  const rejectRuntime = asNum(raw.handover_contract_reject_runtime) ?? 0
  const rejectRawTotal = asNum(raw.handover_contract_reject) ?? 0
  const rejectTotal = Math.max(rejectStartup + rejectRuntime, rejectRawTotal)

  // AUT-124: extract aggregated degradation fields
  const degradedReasonCodes: string[] = []
  const rawCodes = raw.degraded_reason_codes
  if (Array.isArray(rawCodes)) {
    for (const item of rawCodes) {
      if (typeof item === 'string' && item.trim().length > 0) {
        degradedReasonCodes.push(item.trim().toLowerCase())
      }
    }
  }

  return {
    persistenceDegraded: asBool(raw.persistence_degraded),
    persistenceDegradedReason: asStr(raw.persistence_degraded_reason),
    runtimeStateDegraded: asBool(raw.runtime_state_degraded),
    networkDegraded: asBool(raw.network_degraded),
    mqttCircuitBreakerOpen: asBool(raw.mqtt_circuit_breaker_open),
    wifiCircuitBreakerOpen: asBool(raw.wifi_circuit_breaker_open),
    degraded: asBool(raw.degraded),
    degradedReason: asStr(raw.degraded_reason),
    degradedReasonCodes,
    handover: {
      epoch: asNum(raw.handover_epoch) ?? asNum(raw.session_epoch) ?? null,
      rejectStartup,
      rejectRuntime,
      rejectTotal,
    },
    metrics: {
      criticalOutcomeDropCount: asNum(raw.critical_outcome_drop_count) ?? 0,
      publishOutboxDropCount: asNum(raw.publish_outbox_drop_count) ?? 0,
      persistenceDriftCount: asNum(raw.persistence_drift_count) ?? 0,
      heartbeatDegradedCount: asNum(raw.heartbeat_degraded_count) ?? 0,
      publishQueueDropCount: asNum(raw.publish_queue_drop_count) ?? 0,
    },
    rawTelemetry,
  }
}

export interface EspHealthPresentation {
  severity: 'ok' | 'warning'
  showBadge: boolean
  badgeLabel: string
  /**
   * Human-readable label of the primary (highest-priority) cause.
   * AUT-124: used as sublabel directly on the device card to surface the
   * cause of "Eingeschränkt" without requiring tooltip hover.
   */
  primaryReasonLabel?: string
  tooltipLines: string[]
  recommendedAction: string | null
}

interface OperatorReason {
  code: string
  label: string
  detail?: string
  action: string
}

interface ReasonMeta {
  label: string
  action: string
}

const REASON_CODE_META: Record<string, ReasonMeta> = {
  mqtt_disconnected: {
    label: 'MQTT-Verbindung getrennt',
    action: 'MQTT-Broker und Netzwerkanbindung prüfen, dann Reconnect abwarten.',
  },
  persistence_degraded: {
    label: 'Persistenz eingeschränkt',
    action: 'Persistenz-/Speicherzustand prüfen und Warnungen im Server-Log kontrollieren.',
  },
  runtime_state_degraded: {
    label: 'Laufzeitstatus eingeschränkt',
    action: 'Systemzustand und letzte Fehlerereignisse im System-Monitor prüfen.',
  },
  network_degraded: {
    label: 'Netzwerk eingeschränkt',
    action: 'Signalqualität und Erreichbarkeit des Geräts prüfen.',
  },
  mqtt_circuit_breaker_open: {
    label: 'MQTT-Circuit-Breaker offen',
    action: 'MQTT-Fehlerursache beheben und automatische Recovery beobachten.',
  },
  wifi_circuit_breaker_open: {
    label: 'WiFi-Circuit-Breaker offen',
    action: 'WLAN-Verbindung und Zugangsdaten am Gerät prüfen.',
  },
  handover_contract_reject: {
    label: 'Übergabe-Konflikte',
    action: 'Korrelations- und Übergabe-Events prüfen, dann betroffene Aktion erneut auslösen.',
  },
  degraded_operation: {
    label: 'Server im Degraded-Betrieb',
    action: 'Runtime-Health im System-Monitor prüfen und Betriebslast reduzieren.',
  },
}

function humanizeReasonCode(code: string): string {
  const normalized = code.trim().toLowerCase()
  const mapped = REASON_CODE_META[normalized]
  if (mapped) return mapped.label
  return normalized
    .split('_')
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function actionForReason(code: string): string {
  return REASON_CODE_META[code.trim().toLowerCase()]?.action
    ?? 'System-Monitor und Geräte-Details prüfen, dann bei anhaltendem Zustand eskalieren.'
}

function extractReasonCodes(vm: EspHealthViewModel): string[] {
  const result = new Set<string>()

  // AUT-124: prefer typed VM fields (also populates from primary degraded_reason)
  for (const code of vm.degradedReasonCodes) {
    if (code.length > 0) result.add(code)
  }
  if (vm.degradedReason && vm.degradedReason.trim().length > 0) {
    result.add(vm.degradedReason.trim().toLowerCase())
  }

  return Array.from(result)
}

function pushReason(reasons: OperatorReason[], reason: OperatorReason): void {
  if (reasons.some(existing => existing.code === reason.code)) return
  reasons.push(reason)
}

const REASON_PRIORITY: Record<string, number> = {
  mqtt_circuit_breaker_open: 1,
  wifi_circuit_breaker_open: 2,
  mqtt_disconnected: 3,
  network_degraded: 4,
  persistence_degraded: 5,
  runtime_state_degraded: 6,
  handover_contract_reject: 7,
}

function selectPrimaryReason(reasons: OperatorReason[]): OperatorReason | null {
  if (reasons.length === 0) return null
  const ranked = [...reasons].sort((a, b) => {
    const pa = REASON_PRIORITY[a.code] ?? 99
    const pb = REASON_PRIORITY[b.code] ?? 99
    return pa - pb
  })
  return ranked[0] ?? null
}

export function espHealthPresentation(
  vm: EspHealthViewModel,
  deviceReportsOnline: boolean,
): EspHealthPresentation {
  const reasons: OperatorReason[] = []

  if (vm.persistenceDegraded) {
    pushReason(reasons, {
      code: 'persistence_degraded',
      label: REASON_CODE_META.persistence_degraded.label,
      detail: vm.persistenceDegradedReason ?? undefined,
      action: actionForReason('persistence_degraded'),
    })
  }
  if (vm.runtimeStateDegraded) {
    pushReason(reasons, {
      code: 'runtime_state_degraded',
      label: REASON_CODE_META.runtime_state_degraded.label,
      action: actionForReason('runtime_state_degraded'),
    })
  }
  if (vm.networkDegraded) {
    pushReason(reasons, {
      code: 'network_degraded',
      label: REASON_CODE_META.network_degraded.label,
      action: actionForReason('network_degraded'),
    })
  }
  if (vm.mqttCircuitBreakerOpen) {
    pushReason(reasons, {
      code: 'mqtt_circuit_breaker_open',
      label: REASON_CODE_META.mqtt_circuit_breaker_open.label,
      action: actionForReason('mqtt_circuit_breaker_open'),
    })
  }
  if (vm.wifiCircuitBreakerOpen) {
    pushReason(reasons, {
      code: 'wifi_circuit_breaker_open',
      label: REASON_CODE_META.wifi_circuit_breaker_open.label,
      action: actionForReason('wifi_circuit_breaker_open'),
    })
  }
  if (vm.handover.rejectTotal > 0) {
    const epochText = vm.handover.epoch === null ? '' : ` (Epoche ${vm.handover.epoch})`
    pushReason(reasons, {
      code: 'handover_contract_reject',
      label: REASON_CODE_META.handover_contract_reject.label,
      detail: `Erkannt${epochText}: Start ${vm.handover.rejectStartup}, Laufzeit ${vm.handover.rejectRuntime}`,
      action: actionForReason('handover_contract_reject'),
    })
  }

  for (const code of extractReasonCodes(vm)) {
    pushReason(reasons, {
      code,
      label: humanizeReasonCode(code),
      action: actionForReason(code),
    })
  }

  // AUT-124: aggregated degraded flag without granular reason → generic marker
  // ensures the badge can still surface a cause if backend only sets `degraded=true`.
  if (vm.degraded && reasons.length === 0) {
    pushReason(reasons, {
      code: 'degraded_operation',
      label: REASON_CODE_META.degraded_operation.label,
      action: actionForReason('degraded_operation'),
    })
  }

  const lines: string[] = reasons.flatMap((reason, index) => {
    const prefix = index === 0 ? 'Ursache' : 'Weitere Ursache'
    return reason.detail
      ? [`${prefix}: ${reason.label}`, `Detail: ${reason.detail}`]
      : [`${prefix}: ${reason.label}`]
  })

  const unknownKeys = Object.keys(vm.rawTelemetry).filter(
    k => !['metrics_schema_version'].includes(k),
  )
  if (unknownKeys.length > 0) {
    lines.push(`Weitere Telemetrie: ${unknownKeys.slice(0, 6).join(', ')}${unknownKeys.length > 6 ? '…' : ''}`)
  }

  // AUT-133: Counter-Indikatoren strukturiert anzeigen
  const { metrics } = vm
  const counterLines: string[] = []
  if (metrics.criticalOutcomeDropCount > 0)
    counterLines.push(`Kritische Drops: ${metrics.criticalOutcomeDropCount}`)
  if (metrics.publishOutboxDropCount > 0)
    counterLines.push(`Outbox-Drops: ${metrics.publishOutboxDropCount}`)
  if (metrics.persistenceDriftCount > 0)
    counterLines.push(`Persistenz-Drifts: ${metrics.persistenceDriftCount}`)
  if (metrics.publishQueueDropCount > 0)
    counterLines.push(`Queue-Drops: ${metrics.publishQueueDropCount}`)
  if (counterLines.length > 0) {
    lines.push('Metriken:', ...counterLines)
  }

  const hasDegradation = reasons.length > 0

  const showBadge = deviceReportsOnline && hasDegradation
  const primaryReason = selectPrimaryReason(reasons)

  return {
    severity: showBadge ? 'warning' : 'ok',
    showBadge,
    badgeLabel: 'Eingeschränkt',
    primaryReasonLabel: showBadge ? primaryReason?.label : undefined,
    tooltipLines: lines.length > 0 ? lines : ['Keine Degradations-Marker gesetzt'],
    recommendedAction: showBadge ? primaryReason?.action ?? actionForReason('degraded_operation') : null,
  }
}
