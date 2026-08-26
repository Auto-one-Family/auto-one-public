<script setup lang="ts">
/**
 * RuleFlowEditor
 *
 * Node-RED-inspired visual rule editor using Vue Flow.
 * Custom node types for AutomationOne's sensor → logic → actuator pipeline.
 *
 * Features:
 * - Custom glassmorphism nodes for each type (sensor, time, logic, actuator, notification, delay)
 * - Animated iridescent edges
 * - Drag & drop from palette to canvas
 * - Rule ↔ Graph conversion
 * - Live execution flash (via logicStore.activeExecutions)
 * - Auto-layout for imported rules
 */

import { ref, watch } from 'vue'
import { VueFlow, Position, MarkerType, useVueFlow } from '@vue-flow/core'
import type { DefaultEdgeOptions, SnapGrid } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import type { Node, Edge, Connection } from '@vue-flow/core'
import { Handle } from '@vue-flow/core'
import {
  Thermometer,
  Clock,
  GitMerge,
  Power,
  Bell,
  Timer,
  Droplets,
  Gauge,
  Sun,
  Wind,
  Waves,
  Leaf,
  Zap,
  Undo2,
  Redo2,
  Puzzle,
  Stethoscope,
  ArrowLeftRight,
  ListOrdered,
  ShieldOff,
} from 'lucide-vue-next'
import type { Component } from 'vue'
import type { LogicRule, SensorCondition, TimeCondition, HysteresisCondition, CompoundCondition, ActuatorAction, NotificationAction, DelayAction, PluginAction, DiagnosticsCondition, DiagnosticsAction, LogicCondition, LogicAction, SensorDiffCondition, NotRunningCondition, SequenceAction, SequenceStepServer, SequenceStepDraft } from '@/types/logic'
import type { MeasureBinding } from '@/types/measureBinding'
import { useLogicStore } from '@/shared/stores/logic.store'
import { useEspStore } from '@/stores/esp'
import { parseLocaleNumber } from '@/utils/parseLocaleNumber'
import {
  effectiveBandFromPlan,
  formatDeadbandEdge,
  nodeBandFromFlowSensorData,
  planMeasureToSensorType,
  type NodeBandKind,
} from '@/utils/planDeadbandDisplay'
import { useToast } from '@/composables/useToast'
import { getSensorAggCategory, getSensorUnit, inferInterfaceType } from '@/utils/sensorDefaults'
import {
  createEmptyMeasureBindingNodeData,
  getMeasureBindings,
  isTwoSensorMeasureFormula,
  measureBindingFromNodeData,
  measureBindingToNodeData,
} from '@/utils/measureBindings'
import {
  sequenceStepNumber,
  sequenceStepTypeLabel,
  sequenceStepPrimaryLabel,
  sequenceStepDetailLabel,
} from '@/utils/sequenceStepDisplay'
import {
  faceActuatorPrimary as faceActuatorPrimaryLabel,
  faceSensorPrimary as faceSensorPrimaryLabel,
  faceDeviceGpioSecondary,
  faceNotRunningPrimary as faceNotRunningPrimaryLabel,
  faceNotRunningSecondary as faceNotRunningSecondaryLabel,
  faceSensorDiffLabel as faceSensorDiffLabelUtil,
} from '@/utils/ruleNodeDisplay'
import { tokens } from '@/utils/cssTokens'

// Vue Flow CSS
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

interface Props {
  rule: LogicRule | null
  metadata?: {
    priority?: number
    cooldown_seconds?: number
    max_dose_ml_per_day?: number
  }
  /** AUT-1389: Plan-Abo — Knoten zeigt plan-abgeleitete Schwellen statt Node-Static. */
  followsPlan?: boolean
  planMeasure?: string | null
  /** Aktueller Plan-Soll (Plan@now / applied), null = noch kein Wert */
  planValue?: number | null
}

const props = withDefaults(defineProps<Props>(), {
  followsPlan: false,
  planMeasure: null,
  planValue: null,
})

const emit = defineEmits<{
  'node-selected': [node: Node | null]
  'graph-changed': []
  'metadata-restored': [metadata: { priority?: number; cooldown_seconds?: number; max_dose_ml_per_day?: number }]
}>()

const logicStore = useLogicStore()
const espStore = useEspStore()
const toast = useToast()

// Vue Flow instance
// Options passed as <VueFlow> props (not useVueFlow()) — avoids the "options
// parameter is deprecated" warning, which only fires when useVueFlow() is
// called with an options object from outside the VueFlow component itself.
const FLOW_SNAP_GRID_SIZE = 20
const flowDefaultEdgeOptions: DefaultEdgeOptions = {
  animated: true,
  type: 'smoothstep',
  markerEnd: MarkerType.ArrowClosed,
}
const flowSnapGrid: SnapGrid = [FLOW_SNAP_GRID_SIZE, FLOW_SNAP_GRID_SIZE]

const {
  nodes,
  edges,
  addNodes,
  addEdges,
  removeNodes,
  removeEdges,
  onConnect,
  project,
  fitView,
  onNodeClick,
  onNodeDragStop,
  getNode,
  onNodesInitialized,
  setNodes,
  setEdges,
} = useVueFlow()

const flowWrapper = ref<HTMLElement | null>(null)
const isDragOver = ref(false)
let nodeIdCounter = 0
let pendingFitView = false
let templateLoadGuard = false  // Prevents watch from clearing nodes after loadFromRuleData
const validationErrorsByNodeId = ref<Record<string, Record<string, string[]>>>({})

// Initial node dimensions prevent Vue Flow clampNodeExtent crash (dimensions undefined before render)
const NODE_INIT_DIMS: Record<string, { width: number; height: number }> = {
  sensor: { width: 210, height: 120 },
  sensor_diff: { width: 210, height: 120 },
  time: { width: 210, height: 100 },
  logic: { width: 160, height: 70 },
  actuator: { width: 210, height: 120 },
  notification: { width: 210, height: 100 },
  delay: { width: 210, height: 80 },
  plugin: { width: 210, height: 100 },
  diagnostics_status: { width: 210, height: 100 },
  not_running: { width: 220, height: 110 },
  run_diagnostic: { width: 210, height: 80 },
  // AUT-1281: breiter + hoeher fuer die Schritt-Abfolge im Node-Gesicht (siehe #node-sequence).
  // Statischer Init-Wert nur zur Crash-Vermeidung — Vue Flow misst danach die reale Hoehe.
  sequence: { width: 260, height: 190 },
}

// Fit view only after Vue Flow has measured node dimensions
onNodesInitialized(() => {
  if (pendingFitView) {
    pendingFitView = false
    fitView({ padding: 0.3 })
  }
})

// Consolidated sensor configuration: icon, unit, and label per sensor type
interface SensorMeta {
  icon: Component
  unit: string
  label: string
}

const SENSOR_CONFIG: Record<string, SensorMeta> = {
  DS18B20:       { icon: Thermometer, unit: '°C',   label: 'Temperatur' },
  sht31_temp:    { icon: Thermometer, unit: '°C',   label: 'Temperatur' },
  sht31_humidity:{ icon: Droplets,    unit: '%RH',  label: 'Luftfeuchte' },
  bmp280_temp:   { icon: Thermometer, unit: '°C',   label: 'Temperatur' },
  bmp280_pressure:{ icon: Gauge,      unit: 'hPa',  label: 'Druck' },
  bme280_temp:   { icon: Thermometer, unit: '°C',   label: 'Temperatur' },
  bme280_humidity:{ icon: Droplets,   unit: '%RH',  label: 'Luftfeuchte' },
  bme280_pressure:{ icon: Gauge,      unit: 'hPa',  label: 'Druck' },
  pH:            { icon: Gauge,       unit: 'pH',   label: 'pH-Wert' },
  // AUT-1271: unit display comes from getSensorUnit (SSOT µS/cm); local unit is fallback only
  EC:            { icon: Zap,          unit: 'µS/cm', label: 'Leitfähigkeit' },
  moisture:      { icon: Waves,        unit: '%',    label: 'Bodenfeuchte' },
  light:         { icon: Sun,          unit: 'lux',  label: 'Beleuchtungsstärke' },
  co2:           { icon: Wind,         unit: 'ppm',  label: 'CO₂' },
  flow:          { icon: Waves,        unit: 'L/m',  label: 'Durchfluss' },
  level:         { icon: Leaf,         unit: '%',    label: 'Füllstand' },
}

function sensorConfigEntry(type: string): SensorMeta | undefined {
  if (!type) return undefined
  return SENSOR_CONFIG[type] ?? SENSOR_CONFIG[type.toLowerCase()] ?? SENSOR_CONFIG[type.toUpperCase()]
}

// Helper accessors for template readability
function sensorIcon(type: string): Component {
  return sensorConfigEntry(type)?.icon ?? Thermometer
}

/** AUT-1271: canonical unit from sensorDefaults (case-insensitive); EC → µS/cm */
function sensorUnit(type: string): string {
  const fromDefaults = getSensorUnit(type)
  if (fromDefaults && fromDefaults !== 'raw') return fromDefaults
  return sensorConfigEntry(type)?.unit ?? ''
}

function sensorLabel(type: string): string {
  return sensorConfigEntry(type)?.label ?? type
}

/** AUT-1389: Plan-abgeleitete Knoten-Anzeige (Breite aus Node, Mitte aus Plan). */
function planFaceForSensor(data: Record<string, unknown>): {
  kind: NodeBandKind
  low: number
  high: number
  setpoint: number
} | null {
  if (!props.followsPlan || props.planValue == null || !Number.isFinite(props.planValue)) {
    return null
  }
  const planSt = planMeasureToSensorType(props.planMeasure)
  if (!planSt) return null
  const nodeSt = String(data.sensorType ?? '')
  const matches =
    nodeSt.toLowerCase() === planSt.toLowerCase() ||
    getSensorAggCategory(nodeSt) === planSt
  if (!matches) return null
  const band = nodeBandFromFlowSensorData(data)
  if (!band) return null
  const eff = effectiveBandFromPlan(props.planValue, band, 'plan_segment')
  return { kind: band.kind, low: eff.low, high: eff.high, setpoint: eff.setpoint }
}

// Operator display mapping
const operatorDisplay: Record<string, string> = {
  '>': '>',
  '>=': '≥',
  '<': '<',
  '<=': '≤',
  '==': '=',
  '!=': '≠',
  between: '↔',
}

// Command display mapping
const commandDisplay: Record<string, string> = {
  ON: 'AN',
  OFF: 'AUS',
  PWM: 'PWM',
  TOGGLE: '⇄',
}

// Notification channel display mapping
const channelDisplay: Record<string, string> = {
  email: 'E-Mail',
  webhook: 'Webhook',
  websocket: 'Dashboard',
}

// Format GPIO pin number
function formatGpio(gpio: number | undefined): string {
  if (gpio === undefined || gpio === null) return '—'
  return `GPIO ${gpio}`
}

// AUT-1134 (B7-Nebenbefund): ANALOG sensors (pH, EC, moisture, ...) are read via an internal
// ADC or external ADS1115 channel, not a dedicated GPIO pin — showing "GPIO 0" for two different
// sensors sharing the same channel index is misleading. Label those as "Kanal" instead.
function formatSensorGpio(gpio: number | undefined, sensorType: string | undefined): string {
  if (gpio === undefined || gpio === null) return '—'
  if (sensorType && inferInterfaceType(sensorType) === 'ANALOG') {
    return `Kanal ${gpio}`
  }
  return `GPIO ${gpio}`
}

// ======================== DROP HANDLING ========================

function onDragOverCanvas(event: DragEvent) {
  event.preventDefault()
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'move'
  }
  isDragOver.value = true
}

function onDragLeave() {
  isDragOver.value = false
}

function onDrop(event: DragEvent) {
  event.preventDefault()
  isDragOver.value = false

  const rawData = event.dataTransfer?.getData('application/rulenode')
  if (!rawData) return

  const data = JSON.parse(rawData)
  const bounds = flowWrapper.value?.getBoundingClientRect()
  if (!bounds) return

  const position = project({
    x: event.clientX - bounds.left,
    y: event.clientY - bounds.top,
  })

  const id = `${data.type}-${Date.now()}-${nodeIdCounter++}`
  const nodeData = getDefaultNodeData(data.type, data.defaults || {})
  const dims = NODE_INIT_DIMS[data.type] || { width: 210, height: 100 }

  addNodes([
    {
      id,
      type: data.type,
      position,
      data: nodeData,
      width: dims.width,
      height: dims.height,
    } as Node,
  ])

  // Snapshot for undo after adding node
  logicStore.pushToHistory(
    JSON.parse(JSON.stringify(nodes.value)),
    JSON.parse(JSON.stringify(edges.value)),
    props.metadata
  )

  emit('graph-changed')
}

// ======================== DEFAULT NODE DATA ========================

function getDefaultNodeData(type: string, defaults: Record<string, unknown> = {}): Record<string, unknown> {
  switch (type) {
    case 'sensor':
      return {
        espId: '',
        gpio: 0,
        sensorType: defaults.sensorType || 'DS18B20',
        operator: defaults.operator || '>',
        value: defaults.value ?? 25,
        min: defaults.min,
        max: defaults.max,
        ...defaults,
      }
    case 'time':
      return {
        startHour: defaults.startHour ?? 8,
        startMinute: defaults.startMinute ?? 0,
        endHour: defaults.endHour ?? 18,
        endMinute: defaults.endMinute ?? 0,
        daysOfWeek: defaults.daysOfWeek || [0, 1, 2, 3, 4],
        ...defaults,
      }
    case 'logic':
      return {
        operator: defaults.operator || 'AND',
        ...defaults,
      }
    case 'actuator':
      return {
        espId: '',
        gpio: null,
        command: defaults.command || 'ON',
        pwmValue: defaults.pwmValue,
        duration: defaults.duration,
        ...defaults,
      }
    case 'notification':
      return {
        channel: defaults.channel || 'websocket',
        target: defaults.target || '',
        messageTemplate: defaults.messageTemplate || '',
        ...defaults,
      }
    case 'delay':
      return {
        seconds: defaults.seconds ?? 60,
        ...defaults,
      }
    case 'plugin':
      return {
        pluginId: defaults.pluginId || '',
        config: defaults.config || {},
        ...defaults,
      }
    case 'diagnostics_status':
      return {
        checkName: defaults.checkName || 'mqtt',
        expectedStatus: defaults.expectedStatus || 'critical',
        operator: defaults.operator || '==',
        ...defaults,
      }
    case 'not_running':
      return {
        target: defaults.target || 'actuator',
        ruleId: defaults.ruleId || '',
        espId: defaults.espId || '',
        gpio: defaults.gpio ?? null,
        ...defaults,
      }
    case 'run_diagnostic':
      return {
        checkName: defaults.checkName || '',
        ...defaults,
      }
    case 'sequence':
      return {
        steps: defaults.steps ?? [],
        abortOnFailure: defaults.abortOnFailure ?? true,
        maxDurationSeconds: defaults.maxDurationSeconds ?? 300,
        ...defaults,
      }
    case 'sensor_diff':
      // AUT-1399: Mess-Bindung (umgewidmet) — measure_bindings, nie trigger_conditions
      return {
        ...createEmptyMeasureBindingNodeData(),
        ...defaults,
      }
    default:
      return { ...defaults }
  }
}

// ======================== CONNECT HANDLING (with validation) ========================

onConnect((connection: Connection) => {
  // Validate connection using logic store rules
  const sourceNode = getNode.value(connection.source!)
  const targetNode = getNode.value(connection.target!)

  const validation = logicStore.isValidConnection(
    sourceNode?.type,
    targetNode?.type,
    connection.source!,
    connection.target!,
  )

  if (!validation.valid) {
    toast.warning(validation.reason || 'Verbindung nicht erlaubt')
    return
  }

  addEdges([
    {
      id: `e-${connection.source}-${connection.target}-${Date.now()}`,
      source: connection.source!,
      target: connection.target!,
      sourceHandle: connection.sourceHandle || undefined,
      targetHandle: connection.targetHandle || undefined,
      animated: true,
      type: 'smoothstep',
      markerEnd: MarkerType.ArrowClosed,
    },
  ])

  // Push to undo history
  logicStore.pushToHistory(
    JSON.parse(JSON.stringify(nodes.value)),
    JSON.parse(JSON.stringify(edges.value)),
    props.metadata
  )

  emit('graph-changed')
})

// ======================== NODE SELECTION ========================

onNodeClick(({ node }) => {
  emit('node-selected', node)
})

// ======================== NODE DRAG STOP → UNDO HISTORY ========================

onNodeDragStop(() => {
  logicStore.pushToHistory(
    JSON.parse(JSON.stringify(nodes.value)),
    JSON.parse(JSON.stringify(edges.value)),
    props.metadata
  )
})

// ======================== RULE ↔ GRAPH CONVERSION ========================

/**
 * Convert a LogicRule to Vue Flow nodes and edges
 */
function ruleToGraph(rule: LogicRule): { nodes: Node[]; edges: Edge[] } {
  const resultNodes: Node[] = []
  const resultEdges: Edge[] = []
  const COLUMN_SPACING = 300
  const ROW_SPACING = 140

  // Create condition nodes (left column, x=50)
  const conditionIds: string[] = []
  let nodeRow = 0
  rule.conditions.forEach((cond, i) => {
    const id = `cond-${i}`

    if (cond.type === 'sensor' || cond.type === 'sensor_threshold') {
      conditionIds.push(id)
      const sc = cond as SensorCondition
      resultNodes.push({
        id,
        type: 'sensor',
        position: { x: 50, y: 60 + nodeRow * ROW_SPACING },
        data: {
          espId: sc.esp_id,
          gpio: sc.gpio,
          sensorType: sc.sensor_type,
          operator: sc.operator,
          value: sc.value,
          min: sc.min,
          max: sc.max,
          // AUT-995 Feld 4: round-trip freshness gate so the toggle reflects saved state on reload.
          require_fresh_data: sc.require_fresh_data,
        },
      })
      nodeRow++
    } else if (cond.type === 'time_window' || cond.type === 'time') {
      conditionIds.push(id)
      const tc = cond as TimeCondition
      const legacyStartTime = (tc as unknown as { start_time?: string }).start_time
      const legacyEndTime = (tc as unknown as { end_time?: string }).end_time
      const parsedStartMinute = typeof legacyStartTime === 'string' && legacyStartTime.includes(':')
        ? Number(legacyStartTime.split(':')[1])
        : 0
      const parsedEndMinute = typeof legacyEndTime === 'string' && legacyEndTime.includes(':')
        ? Number(legacyEndTime.split(':')[1])
        : 0
      resultNodes.push({
        id,
        type: 'time',
        position: { x: 50, y: 60 + nodeRow * ROW_SPACING },
        data: {
          startHour: tc.start_hour,
          startMinute: tc.start_minute ?? (Number.isFinite(parsedStartMinute) ? parsedStartMinute : 0),
          endHour: tc.end_hour,
          endMinute: tc.end_minute ?? (Number.isFinite(parsedEndMinute) ? parsedEndMinute : 0),
          daysOfWeek: tc.days_of_week || [],
        },
      })
      nodeRow++
    } else if (cond.type === 'hysteresis') {
      conditionIds.push(id)
      const hc = cond as HysteresisCondition
      resultNodes.push({
        id,
        type: 'sensor',
        position: { x: 50, y: 60 + nodeRow * ROW_SPACING },
        data: {
          espId: hc.esp_id,
          gpio: hc.gpio,
          sensorType: hc.sensor_type || 'hysteresis',
          operator: 'hysteresis',
          value: hc.activate_above ?? hc.activate_below ?? 0,
          isHysteresis: true,
          activateAbove: hc.activate_above,
          deactivateBelow: hc.deactivate_below,
          activateBelow: hc.activate_below,
          deactivateAbove: hc.deactivate_above,
        },
      })
      nodeRow++
    } else if (cond.type === 'diagnostics_status') {
      conditionIds.push(id)
      const dc = cond as DiagnosticsCondition
      resultNodes.push({
        id,
        type: 'diagnostics_status',
        position: { x: 50, y: 60 + nodeRow * ROW_SPACING },
        data: {
          checkName: dc.check_name,
          expectedStatus: dc.expected_status,
          operator: dc.operator || '==',
        },
      })
      nodeRow++
    } else if (cond.type === 'sensor_diff') {
      // AUT-1399: skip in conditionIds — loaded as Mess-Bindung nodes below (never Trigger)
    } else if (cond.type === 'not_running') {
      // AUT-1333: Interlock-Condition — Round-Trip, sonst streicht Save die API-Config
      conditionIds.push(id)
      const nr = cond as NotRunningCondition
      resultNodes.push({
        id,
        type: 'not_running',
        position: { x: 50, y: 60 + nodeRow * ROW_SPACING },
        data: {
          target: nr.target,
          ruleId: nr.rule_id || '',
          espId: nr.esp_id || '',
          gpio: nr.gpio ?? null,
        },
      })
      nodeRow++
    } else if (cond.type === 'compound') {
      // Flatten compound conditions: render sub-conditions as individual nodes
      // Parent compound ID is NOT added — only sub-condition nodes get IDs
      const cc = cond as CompoundCondition
      cc.conditions.forEach((subCond, j) => {
        if (subCond.type === 'sensor' || subCond.type === 'sensor_threshold') {
          const sc = subCond as SensorCondition
          const subId = `cond-${i}-sub-${j}`
          conditionIds.push(subId)
          resultNodes.push({
            id: subId,
            type: 'sensor',
            position: { x: 50, y: 60 + nodeRow * ROW_SPACING },
            data: {
              espId: sc.esp_id,
              gpio: sc.gpio,
              sensorType: sc.sensor_type,
              operator: sc.operator,
              value: sc.value,
              min: sc.min,
              max: sc.max,
            },
          })
          nodeRow++
        }
      })
    }
  })

  // AUT-1399: Mess-Bindung-Knoten aus measure_bindings (primär); Legacy sensor_diff-Conditions nur Fallback.
  // Nie in conditionIds — Kanten erzeugen keine condition_refs.
  const metaBindings = getMeasureBindings(rule.rule_metadata)
  if (metaBindings.length > 0) {
    metaBindings.forEach((binding, mi) => {
      const id = `measure-${mi}`
      resultNodes.push({
        id,
        type: 'sensor_diff',
        position: { x: 50, y: 60 + nodeRow * ROW_SPACING },
        data: measureBindingToNodeData(binding),
      })
      nodeRow++
    })
  } else {
    rule.conditions.forEach((cond, i) => {
      if (cond.type !== 'sensor_diff') return
      const sdc = cond as SensorDiffCondition
      const id = `measure-legacy-${i}`
      const legacyData = createEmptyMeasureBindingNodeData()
      // Best-effort: alte config_ids nur als Label-Hinweis (keine Trigger-Semantik)
      legacyData.label = 'Mess-Bindung'
      if (sdc.sensor_a_id) {
        legacyData.sensorType = 'legacy'
        legacyData.sensorEspId = sdc.sensor_a_id
      }
      resultNodes.push({
        id,
        type: 'sensor_diff',
        position: { x: 50, y: 60 + nodeRow * ROW_SPACING },
        data: legacyData,
      })
      nodeRow++
    })
  }

  // AUT-1318 (R-S4): reconstruct edges from condition_refs when present.
  // Legacy (no refs): Conditions → Logic → all Actions (flat gate, D4).
  // Routed: Condition[i] → Action with refs; flat actions still via Logic.
  const actionHasRefs = (action: LogicAction): boolean =>
    Array.isArray(action.condition_refs) && action.condition_refs.length > 0
  const anyRouted = rule.actions.some(actionHasRefs)
  const anyFlat = rule.actions.length === 0 || rule.actions.some((a) => !actionHasRefs(a))

  let logicId: string | null = null
  if (!anyRouted || anyFlat) {
    const flatLogicId = 'logic-0'
    logicId = flatLogicId
    const avgY = conditionIds.length > 0
      ? (conditionIds.length - 1) * ROW_SPACING / 2 + 60
      : 60
    resultNodes.push({
      id: flatLogicId,
      type: 'logic',
      position: { x: 50 + COLUMN_SPACING, y: avgY },
      data: { operator: rule.logic_operator },
    })

    conditionIds.forEach((condId) => {
      resultEdges.push({
        id: `e-${condId}-${flatLogicId}`,
        source: condId,
        target: flatLogicId,
        animated: true,
        type: 'smoothstep',
        markerEnd: MarkerType.ArrowClosed,
      })
    })
  }

  // Create action nodes (right column)
  const actionX = 50 + COLUMN_SPACING * 2
  rule.actions.forEach((action, i) => {
    const id = `action-${i}`
    const routingData = {
      ...(action.condition_op ? { condition_op: action.condition_op } : {}),
      ...(Array.isArray(action.condition_refs) && action.condition_refs.length > 0
        ? { condition_refs: [...action.condition_refs] }
        : {}),
    }

    if (action.type === 'actuator' || action.type === 'actuator_command') {
      const aa = action as ActuatorAction
      resultNodes.push({
        id,
        type: 'actuator',
        position: { x: actionX, y: 60 + i * ROW_SPACING },
        data: {
          espId: aa.esp_id,
          gpio: aa.gpio,
          command: aa.command,
          pwmValue: aa.value !== undefined ? Math.round(aa.value * 100) : undefined,
          duration: aa.duration ?? aa.duration_seconds,
          // AUT-995 Feld 2: round-trip dose_ml so the input reflects saved state on reload.
          dose_ml: aa.dose_ml,
          ...(aa.is_safety_critical ? { is_safety_critical: true } : {}),
          ...routingData,
        },
      })
    } else if (action.type === 'notification') {
      const na = action as NotificationAction
      resultNodes.push({
        id,
        type: 'notification',
        position: { x: actionX, y: 60 + i * ROW_SPACING },
        data: {
          channel: na.channel,
          target: na.target,
          messageTemplate: na.message_template,
          ...routingData,
        },
      })
    } else if (action.type === 'delay') {
      const da = action as DelayAction
      resultNodes.push({
        id,
        type: 'delay',
        position: { x: actionX, y: 60 + i * ROW_SPACING },
        data: { seconds: da.seconds, ...routingData },
      })
    } else if (action.type === 'plugin' || action.type === 'autoops_trigger') {
      const pa = action as PluginAction
      const cfg = pa.config || {}
      // Expand config into cfg_* for RuleConfigPanel schema fields
      const cfgFields = Object.fromEntries(
        Object.entries(cfg).map(([k, v]) => [`cfg_${k}`, v]),
      )
      resultNodes.push({
        id,
        type: 'plugin',
        position: { x: actionX, y: 60 + i * ROW_SPACING },
        data: {
          pluginId: pa.plugin_id,
          config: cfg,
          ...cfgFields,
          ...routingData,
        },
      })
    } else if (action.type === 'run_diagnostic') {
      const da = action as DiagnosticsAction
      resultNodes.push({
        id,
        type: 'run_diagnostic',
        position: { x: actionX, y: 60 + i * ROW_SPACING },
        data: {
          checkName: da.check_name || '',
          ...routingData,
        },
      })
    } else if (action.type === 'sequence') {
      const sa = action as SequenceAction
      resultNodes.push({
        id,
        type: 'sequence',
        position: { x: actionX, y: 60 + i * ROW_SPACING },
        data: {
          abortOnFailure: sa.abort_on_failure ?? true,
          maxDurationSeconds: sa.max_duration_seconds ?? 300,
          steps: (sa.steps ?? []).map((step: SequenceStepServer): SequenceStepDraft => {
            if (step.delay_seconds !== undefined && !step.action) {
              return {
                stepType: 'delay',
                name: step.name ?? '',
                seconds: step.delay_seconds,
                onFailure: step.on_failure ?? 'abort',
              }
            }
            const act = step.action as ActuatorAction | undefined
            const cmd = (act?.command ?? 'ON').toUpperCase()
            return {
              stepType: 'actuator',
              name: step.name ?? '',
              espId: act?.esp_id ?? '',
              gpio: act?.gpio ?? 0,
              command: cmd,
              duration: act?.duration_seconds ?? act?.duration ?? 0,
              // AUT-1281: dose_ml round-trip (AUT-1111 engine bereits wirksam; Frontend zog nicht nach)
              dose_ml: act?.dose_ml,
              // AUT-1390: FE-Intent Modus Roundtrip (Step-Meta, kein Server-Dosier-Pfad)
              dose_mode: step.dose_mode,
              onFailure: step.on_failure ?? 'abort',
              // AUT-1306: before/after am Aktor-Schritt nur Roundtrip-Preserve (kein UI-Neubau)
              delay_before_seconds: step.delay_before_seconds,
              delay_after_seconds: step.delay_after_seconds,
            }
          }),
          ...routingData,
        },
      })
    }

    // AUT-1318: routed actions ← condition_refs; flat actions ← logic gate
    if (actionHasRefs(action)) {
      for (const ref of action.condition_refs as number[]) {
        const condId = conditionIds[ref]
        if (!condId) continue
        resultEdges.push({
          id: `e-${condId}-${id}`,
          source: condId,
          target: id,
          animated: true,
          type: 'smoothstep',
          markerEnd: MarkerType.ArrowClosed,
        })
      }
    } else if (logicId) {
      resultEdges.push({
        id: `e-${logicId}-${id}`,
        source: logicId,
        target: id,
        animated: true,
        type: 'smoothstep',
        markerEnd: MarkerType.ArrowClosed,
      })
    }
  })

  // Set initial dimensions on all nodes to prevent Vue Flow clampNodeExtent crash
  for (const node of resultNodes) {
    const dims = NODE_INIT_DIMS[node.type || '']
    if (dims) {
      ;(node as unknown as Record<string, unknown>).width = dims.width
      ;(node as unknown as Record<string, unknown>).height = dims.height
    }
  }

  return { nodes: resultNodes, edges: resultEdges }
}

/**
 * Convert Vue Flow graph back to LogicRule partial
 */
function graphToRuleData(): {
  conditions: LogicCondition[]
  actions: LogicAction[]
  logic_operator: 'AND' | 'OR'
  priority?: number
  cooldown_seconds?: number
  max_dose_ml_per_day?: number
  conditionNodeIds: string[]
  actionNodeIds: string[]
  /** AUT-1399: from sensor_diff nodes — exclusively measure_bindings, never trigger_conditions */
  measure_bindings: MeasureBinding[]
} {
  const conditions: LogicCondition[] = []
  const actions: LogicAction[] = []
  const conditionNodeIds: string[] = []
  const actionNodeIds: string[] = []
  const measure_bindings: MeasureBinding[] = []
  let logicOperator: 'AND' | 'OR' = 'AND'

  for (const node of nodes.value) {
    switch (node.type) {
      case 'sensor': {
        const isHysteresis = node.data?.isHysteresis === true || node.data?.operator === 'hysteresis'
        if (isHysteresis) {
          // Hysterese: Kühlung (activate_above/deactivate_below) oder Heizung (activate_below/deactivate_above)
          const hyst: HysteresisCondition = {
            type: 'hysteresis',
            esp_id: node.data.espId || '',
            gpio: node.data.gpio || 0,
            ...(node.data.sensorType ? { sensor_type: node.data.sensorType as string } : {}),
          }
          if (node.data.activateAbove != null && node.data.deactivateBelow != null) {
            hyst.activate_above = parseLocaleNumber(node.data.activateAbove as string | number)
            hyst.deactivate_below = parseLocaleNumber(node.data.deactivateBelow as string | number)
          }
          if (node.data.activateBelow != null && node.data.deactivateAbove != null) {
            hyst.activate_below = parseLocaleNumber(node.data.activateBelow as string | number)
            hyst.deactivate_above = parseLocaleNumber(node.data.deactivateAbove as string | number)
          }
          conditions.push(hyst)
          conditionNodeIds.push(node.id)
        } else {
          const sensorValue = node.data.value
          const sensorMin = node.data.min
          const sensorMax = node.data.max
          conditions.push({
            type: 'sensor',
            esp_id: node.data.espId || '',
            gpio: node.data.gpio || 0,
            sensor_type: node.data.sensorType || 'DS18B20',
            operator: node.data.operator || '>',
            value:
              sensorValue === '' || sensorValue == null
                ? 0
                : parseLocaleNumber(sensorValue as string | number),
            ...(sensorMin !== undefined && sensorMin !== ''
              ? { min: parseLocaleNumber(sensorMin as string | number) }
              : {}),
            ...(sensorMax !== undefined && sensorMax !== ''
              ? { max: parseLocaleNumber(sensorMax as string | number) }
              : {}),
            // AUT-995 Feld 4: require_fresh_data (additive) — server freshness gate (AO-3).
            ...(node.data.require_fresh_data ? { require_fresh_data: true } : {}),
          } as SensorCondition)
          conditionNodeIds.push(node.id)
        }
        break
      }

      case 'time':
        {
          const startMinute = Number(node.data.startMinute ?? 0)
          const endMinute = Number(node.data.endMinute ?? 0)
          const normalizedStartMinute = Number.isFinite(startMinute)
            ? Math.min(Math.max(Math.trunc(startMinute), 0), 59)
            : 0
          const normalizedEndMinute = Number.isFinite(endMinute)
            ? Math.min(Math.max(Math.trunc(endMinute), 0), 59)
            : 0
        conditions.push({
          type: 'time_window',
          start_hour: node.data.startHour ?? 0,
          start_minute: normalizedStartMinute,
          end_hour: node.data.endHour ?? 23,
          end_minute: normalizedEndMinute,
          ...(node.data.daysOfWeek?.length ? { days_of_week: node.data.daysOfWeek } : {}),
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        } as TimeCondition)
        conditionNodeIds.push(node.id)
        break
        }

      case 'logic':
        logicOperator = node.data.operator || 'AND'
        break

      case 'actuator': {
        // GPIO 0 is never a valid actuator (I2C/sensor convention). Skip unconfigured nodes
        // to prevent phantom actions from uninitialized actuator nodes (AUT-654 / AUT-565 class).
        if (!node.data.gpio) break
        // Backend ActuatorCommandAction requires 'value' field (0.0-1.0)
        // PWM: use slider value / 100, ON: 1.0, OFF: 0.0
        const cmd = (node.data.command || 'ON').toUpperCase()
        const pwmVal = node.data.pwmValue !== undefined
          ? node.data.pwmValue / 100
          : (cmd === 'OFF' ? 0.0 : 1.0)
        actions.push({
          type: 'actuator',
          esp_id: node.data.espId || '',
          gpio: node.data.gpio,
          command: cmd,
          value: pwmVal,
          ...(node.data.duration ? { duration_seconds: node.data.duration } : { duration_seconds: 0 }),
          // AUT-995 Feld 2c: dose_ml (additive) — server (AO-2) resolves to duration_seconds via flow_rate_ml_s.
          ...(node.data.dose_ml ? { dose_ml: node.data.dose_ml } : {}),
          ...(node.data.is_safety_critical ? { is_safety_critical: true } : {}),
          ...(node.data.condition_op === 'AND' || node.data.condition_op === 'OR'
            ? { condition_op: node.data.condition_op }
            : {}),
        } as ActuatorAction)
        actionNodeIds.push(node.id)
        break
      }

      case 'notification':
        actions.push({
          type: 'notification',
          channel: node.data.channel || 'websocket',
          target: node.data.target || '',
          message_template: node.data.messageTemplate || '',
          ...(node.data.condition_op === 'AND' || node.data.condition_op === 'OR'
            ? { condition_op: node.data.condition_op }
            : {}),
        } as NotificationAction)
        actionNodeIds.push(node.id)
        break

      case 'delay':
        actions.push({
          type: 'delay',
          seconds: node.data.seconds || 60,
          ...(node.data.condition_op === 'AND' || node.data.condition_op === 'OR'
            ? { condition_op: node.data.condition_op }
            : {}),
        } as DelayAction)
        actionNodeIds.push(node.id)
        break

      case 'plugin': {
        // Merge config object + cfg_* fields (RuleConfigPanel stores schema fields as cfg_key)
        const config: Record<string, unknown> = { ...(node.data.config as Record<string, unknown> || {}) }
        for (const [k, v] of Object.entries(node.data)) {
          if (k.startsWith('cfg_') && v !== undefined) {
            config[k.slice(4)] = v
          }
        }
        actions.push({
          type: 'plugin',
          plugin_id: node.data.pluginId || '',
          config,
          ...(node.data.condition_op === 'AND' || node.data.condition_op === 'OR'
            ? { condition_op: node.data.condition_op }
            : {}),
        } as PluginAction)
        actionNodeIds.push(node.id)
        break
      }

      case 'diagnostics_status':
        conditions.push({
          type: 'diagnostics_status',
          check_name: node.data.checkName || 'mqtt',
          expected_status: node.data.expectedStatus || 'critical',
          operator: (node.data.operator as '==' | '!=' | undefined) || '==',
        } as DiagnosticsCondition)
        conditionNodeIds.push(node.id)
        break

      case 'run_diagnostic':
        actions.push({
          type: 'run_diagnostic',
          ...(node.data.checkName ? { check_name: node.data.checkName as string } : {}),
          ...(node.data.condition_op === 'AND' || node.data.condition_op === 'OR'
            ? { condition_op: node.data.condition_op }
            : {}),
        } as DiagnosticsAction)
        actionNodeIds.push(node.id)
        break

      case 'sequence': {
        const steps = ((node.data.steps ?? []) as SequenceStepDraft[]).map(step => {
          if (step.stepType === 'delay') {
            return {
              name: step.name || undefined,
              delay_seconds: step.seconds ?? 60,
              on_failure: step.onFailure ?? 'abort',
            }
          }
          const cmd = (step.command ?? 'ON').toUpperCase()
          // AUT-1281: dose_ml gewinnt (analog Top-Level-Actuator, logic_engine.py:1330-1331) —
          // duration_seconds bleibt optional erhalten (Fallback/Anzeige), Action-Type immer 'actuator'.
          const hasDose = step.dose_ml != null && step.dose_ml > 0
          return {
            name: step.name || undefined,
            action: {
              type: 'actuator' as const,
              esp_id: step.espId ?? '',
              gpio: step.gpio ?? 0,
              command: cmd,
              value: cmd === 'OFF' ? 0.0 : 1.0,
              duration_seconds: step.duration ?? 0,
              ...(hasDose ? { dose_ml: step.dose_ml } : {}),
            },
            on_failure: step.onFailure ?? 'abort',
            // AUT-1390: FE-Intent Modus am Step (nicht in action — validation List[Any])
            ...(step.dose_mode
              ? { dose_mode: step.dose_mode }
              : {}),
            // AUT-1306: Server-Felder delay_before/after nur durchreichen (kein UI)
            ...(step.delay_before_seconds != null
              ? { delay_before_seconds: step.delay_before_seconds }
              : {}),
            ...(step.delay_after_seconds != null
              ? { delay_after_seconds: step.delay_after_seconds }
              : {}),
          }
        })
        actions.push({
          type: 'sequence',
          abort_on_failure: node.data.abortOnFailure ?? true,
          max_duration_seconds: node.data.maxDurationSeconds ?? 300,
          steps,
          ...(node.data.condition_op === 'AND' || node.data.condition_op === 'OR'
            ? { condition_op: node.data.condition_op }
            : {}),
        } as SequenceAction)
        actionNodeIds.push(node.id)
        break
      }

      case 'sensor_diff':
        // AUT-1399: Mess-Bindung → measure_bindings only (never conditions / condition_refs)
        measure_bindings.push(measureBindingFromNodeData(node.data))
        break

      case 'not_running': {
        const target = (node.data.target as NotRunningCondition['target']) || 'actuator'
        const nr: NotRunningCondition = { type: 'not_running', target }
        if (target === 'sequence') {
          nr.rule_id = (node.data.ruleId as string) || ''
        } else {
          nr.esp_id = (node.data.espId as string) || ''
          nr.gpio = Number(node.data.gpio ?? 0)
        }
        conditions.push(nr)
        conditionNodeIds.push(node.id)
        break
      }
    }
  }

  // AUT-1318 (R-S4): edges → condition_refs (direct Condition→Action only).
  // Edges via logic gate leave refs empty → legacy global gate (D4).
  // AUT-1399: sensor_diff (Mess-Bindung) is NOT a condition — edges must not create condition_refs.
  const CONDITION_NODE_TYPES = new Set([
    'sensor',
    'time',
    'diagnostics_status',
    'not_running',
  ])
  const ACTION_NODE_TYPES = new Set([
    'actuator',
    'notification',
    'delay',
    'plugin',
    'run_diagnostic',
    'sequence',
  ])
  const condIndexById = new Map(conditionNodeIds.map((id, i) => [id, i]))
  const actionIndexById = new Map(actionNodeIds.map((id, i) => [id, i]))
  const nodeTypeById = new Map(nodes.value.map((n) => [n.id, n.type || '']))
  const refsByActionIndex = new Map<number, Set<number>>()

  for (const edge of edges.value) {
    const srcType = nodeTypeById.get(edge.source)
    const tgtType = nodeTypeById.get(edge.target)
    if (!srcType || !tgtType) continue
    if (!CONDITION_NODE_TYPES.has(srcType) || !ACTION_NODE_TYPES.has(tgtType)) continue
    const ci = condIndexById.get(edge.source)
    const ai = actionIndexById.get(edge.target)
    if (ci === undefined || ai === undefined) continue
    let set = refsByActionIndex.get(ai)
    if (!set) {
      set = new Set<number>()
      refsByActionIndex.set(ai, set)
    }
    set.add(ci)
  }

  for (const [ai, refs] of refsByActionIndex) {
    if (refs.size === 0) continue
    const sorted = Array.from(refs).sort((a, b) => a - b)
    actions[ai] = {
      ...actions[ai],
      condition_refs: sorted,
    }
  }

  return {
    conditions,
    actions,
    logic_operator: logicOperator,
    priority: props.metadata?.priority,
    cooldown_seconds: props.metadata?.cooldown_seconds,
    max_dose_ml_per_day: props.metadata?.max_dose_ml_per_day,
    conditionNodeIds,
    actionNodeIds,
    measure_bindings,
  }
}

// ======================== LOAD RULE INTO GRAPH ========================

watch(
  () => props.rule,
  (newRule) => {
    if (newRule) {
      try {
        const graph = ruleToGraph(newRule)
        // Use setNodes/setEdges (NOT nodes.value =) to go through parseNode pipeline
        // parseNode initializes dimensions: { width: 0, height: 0 } which prevents
        // clampNodeExtent crash in Vue Flow v1.48.2
        setNodes(graph.nodes)
        setEdges(graph.edges)
        // Defer fitView until Vue Flow has measured real node dimensions
        pendingFitView = true
      } catch (err) {
        console.error('[RuleFlowEditor] Failed to convert rule to graph:', err)
        toast.error('Regel konnte nicht geladen werden')
        nodes.value = []
        edges.value = []
      }
    } else if (templateLoadGuard) {
      // Template was loaded via loadFromRuleData — do NOT clear the canvas
      templateLoadGuard = false
    } else {
      nodes.value = []
      edges.value = []
    }
  },
  { immediate: true }
)

// ======================== EXPOSED METHODS ========================

function updateNodeData(nodeId: string, data: Record<string, unknown>) {
  const node = getNode.value(nodeId)
  if (node) {
    node.data = { ...data }
    emit('graph-changed')
  }
}

function deleteNode(nodeId: string) {
  // Snapshot BEFORE deletion for undo
  logicStore.pushToHistory(
    JSON.parse(JSON.stringify(nodes.value)),
    JSON.parse(JSON.stringify(edges.value)),
    props.metadata
  )

  // Remove connected edges first
  const connectedEdges = edges.value.filter(
    (e) => e.source === nodeId || e.target === nodeId
  )
  removeEdges(connectedEdges.map((e) => e.id))
  removeNodes([nodeId])
  emit('node-selected', null)
  emit('graph-changed')
}

function duplicateNode(nodeId: string) {
  const node = getNode.value(nodeId)
  if (!node) return

  const newId = `${node.type}-${Date.now()}-${nodeIdCounter++}`
  addNodes([
    {
      id: newId,
      type: node.type!,
      position: { x: node.position.x + 40, y: node.position.y + 40 },
      data: { ...node.data },
    },
  ])

  // Snapshot after duplication
  logicStore.pushToHistory(
    JSON.parse(JSON.stringify(nodes.value)),
    JSON.parse(JSON.stringify(edges.value)),
    props.metadata
  )

  emit('graph-changed')
}

function clearCanvas() {
  nodes.value = []
  edges.value = []
  emit('node-selected', null)
  emit('graph-changed')
}

// Check if a node belongs to an active rule execution
function isNodeActive(_nodeId: string): boolean {
  if (!props.rule) return false
  return logicStore.isRuleActive(props.rule.id)
}

// AUT-632 / AUT-1248: Gerätename nur aus vorhandenem device.name — nie UUID-Fragment.
function lookupDevice(espId: string | undefined) {
  if (!espId) return undefined
  // not_running speichert DB-UUID; Aktor/Sensor-Nodes nutzen device_id (ESP_XXXX)
  return espStore.devices.find(
    (d) => espStore.getDeviceId(d) === espId || d.id === espId,
  )
}

function getEspName(espId: string): string {
  if (!espId) return ''
  const name = lookupDevice(espId)?.name?.trim()
  return name || ''
}

function lookupActuator(espId: string | undefined, gpio: number | null | undefined) {
  if (gpio == null) return undefined
  return lookupDevice(espId)?.actuators?.find((a) => a.gpio === gpio)
}

function lookupSensor(
  espId: string | undefined,
  gpio: number | null | undefined,
  sensorType?: string,
) {
  if (gpio == null) return undefined
  const sensors = lookupDevice(espId)?.sensors || []
  if (sensorType) {
    const byType = sensors.find((s) => s.gpio === gpio && s.sensor_type === sensorType)
    if (byType) return byType
  }
  return sensors.find((s) => s.gpio === gpio)
}

/** Nur echter Config-Name — kein erfundener Typ-Label (Leitplanke AUT-1334 R3). */
function configuredActuatorName(
  espId: string | undefined,
  gpio: number | null | undefined,
): string | null {
  const name = lookupActuator(espId, gpio)?.name?.trim()
  return name || null
}

function configuredSensorName(
  espId: string | undefined,
  gpio: number | null | undefined,
  sensorType?: string,
): string | null {
  const name = lookupSensor(espId, gpio, sensorType)?.name?.trim()
  return name || null
}

function faceSensorPrimary(data: {
  espId?: string
  gpio?: number | null
  sensorType?: string
}): string {
  return faceSensorPrimaryLabel(
    configuredSensorName(data.espId, data.gpio, data.sensorType),
    sensorLabel(data.sensorType || ''),
  )
}

function faceActuatorPrimary(data: { espId?: string; gpio?: number | null }): string {
  return faceActuatorPrimaryLabel(configuredActuatorName(data.espId, data.gpio))
}

function faceSecondaryDeviceGpio(
  espId: string | undefined,
  gpioLabel: string,
): { text: string; title: string } {
  return faceDeviceGpioSecondary(espId ? getEspName(espId) : '', gpioLabel)
}

function faceNotRunningPrimary(data: {
  target?: string
  ruleId?: string
  espId?: string
  gpio?: number | null
}): string {
  const rule = data.ruleId ? logicStore.getRuleById?.(data.ruleId) : undefined
  return faceNotRunningPrimaryLabel({
    target: data.target,
    actuatorName: configuredActuatorName(data.espId, data.gpio),
    ruleName: rule?.name ?? null,
  })
}

function faceNotRunningSecondary(data: {
  target?: string
  ruleId?: string
  espId?: string
  gpio?: number | null
}): { text: string; title: string } {
  return faceNotRunningSecondaryLabel({
    target: data.target,
    ruleId: data.ruleId,
    espName: data.espId ? getEspName(data.espId) : '',
    gpioLabel: formatGpio(data.gpio ?? undefined),
  })
}

/** AUT-1399 Mess-Bindung: Sensor-Klarname aus esp_id/gpio/type (nie Rohtyp allein als Titel). */
function faceMeasureSensorName(
  espId: string | undefined,
  gpio: number | null | undefined,
  sensorType: string | undefined,
): string {
  if (!espId || gpio == null || !sensorType) {
    return faceSensorDiffLabelUtil({ configId: '', resolved: false })
  }
  for (const device of espStore.devices) {
    const deviceId = espStore.getDeviceId(device)
    if (deviceId !== espId && device.id !== espId) continue
    const sensor = (device.sensors || []).find(
      (s) => s.gpio === gpio && s.sensor_type === sensorType,
    )
    if (!sensor) continue
    return faceSensorDiffLabelUtil({
      configId: `${espId}:${gpio}`,
      resolved: true,
      sensorName: sensor.name,
      typeLabel: sensorLabel(sensor.sensor_type),
    })
  }
  // Fallback: lesbarer Typ-Klarname, nicht UUID/Rohtyp allein
  return sensorLabel(sensorType) || 'Sensor'
}

function faceMeasureBindingTitle(data: Record<string, unknown>): string {
  const custom = typeof data.label === 'string' ? data.label.trim() : ''
  if (custom) return custom
  const name = faceMeasureSensorName(
    data.sensorEspId as string | undefined,
    data.sensorGpio as number | null | undefined,
    data.sensorType as string | undefined,
  )
  if (name && name !== '—') return name
  return 'Mess-Bindung'
}

function faceMeasurePointLabels(data: Record<string, unknown>): {
  twoSensors: boolean
  leftLabel: string
  leftValue: string
  rightLabel: string
  rightValue: string
  measureLine: string
} {
  const binding = measureBindingFromNodeData(data)
  const twoSensors = isTwoSensorMeasureFormula(binding.sensor_refs.length)
  const nameA = faceMeasureSensorName(
    data.sensorEspId as string | undefined,
    data.sensorGpio as number | null | undefined,
    data.sensorType as string | undefined,
  )
  const nameB = faceMeasureSensorName(
    data.sensorBEspId as string | undefined,
    data.sensorBGpio as number | null | undefined,
    data.sensorBType as string | undefined,
  )
  if (twoSensors) {
    return {
      twoSensors: true,
      leftLabel: 'Erster',
      leftValue: nameA,
      rightLabel: 'Zweiter',
      rightValue: nameB,
      measureLine: `Differenz: ${nameB} minus ${nameA}`,
    }
  }
  // Ein Sensor: Anfangs- und Endwert (Zeitpunkte = Häkchen im Panel, nicht die Linien)
  return {
    twoSensors: false,
    leftLabel: 'Anfang',
    leftValue: nameA,
    rightLabel: 'Ende',
    rightValue: nameA,
    measureLine:
      nameA && nameA !== '—'
        ? `Misst den Unterschied von Anfang bis Ende (${nameA})`
        : 'Misst den Unterschied von Anfang bis Ende',
  }
}

// AUT-1281: Aktorname fuer Sequenz-Schritte aus espStore (devices -> actuators by espId/gpio),
// Fallback auf den frei benannten Schritt-Namen bzw. GPIO-Anzeige.
function getStepActuatorName(espId: string | undefined, gpio: number | undefined, fallbackName?: string): string {
  if (fallbackName) return fallbackName
  if (!espId || gpio == null) return 'Nicht konfiguriert'
  return configuredActuatorName(espId, gpio) || `GPIO ${gpio}`
}

// AUT-1306: Node-Gesicht Nr · Typ · Primär · Detail (Helfer in sequenceStepDisplay.ts)
function faceStepPrimary(step: SequenceStepDraft): string {
  return sequenceStepPrimaryLabel(step, getStepActuatorName)
}

function faceStepDetail(step: SequenceStepDraft): string {
  return sequenceStepDetailLabel(step, formatDuration)
}

// Format time with leading zero
function formatHourMinute(h: number, m: number | undefined): string {
  const minute = Number.isFinite(Number(m)) ? Number(m) : 0
  return `${String(h).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
}

// Format seconds to human-readable duration (AUT-632)
function formatDuration(seconds: number): string {
  if (seconds >= 3600) {
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    return m > 0 ? `${h} h ${m} min` : `${h} h`
  }
  if (seconds >= 60) {
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    return s > 0 ? `${m} min ${s} s` : `${m} min`
  }
  return `${seconds} s`
}

// MiniMap node color by type
function miniMapNodeColor(node: Node): string {
  const colors: Record<string, () => string> = {
    sensor: () => tokens.info,
    sensor_diff: () => tokens.info,
    time: () => tokens.warning,
    logic: () => tokens.mock,
    actuator: () => tokens.mock,
    notification: () => tokens.success,
    delay: () => tokens.textMuted,
    plugin: () => tokens.warning,
    diagnostics_status: () => tokens.real,
    not_running: () => tokens.warning,
    run_diagnostic: () => tokens.real,
  }
  return colors[node.type || '']?.() || tokens.textMuted
}

// ======================== UNDO/REDO ========================

function performUndo() {
  const state = logicStore.undo()
  if (state) {
    setNodes(state.nodes)
    setEdges(state.edges)
    if (state.metadata) emit('metadata-restored', state.metadata)
    emit('graph-changed')
  }
}

function performRedo() {
  const state = logicStore.redo()
  if (state) {
    setNodes(state.nodes)
    setEdges(state.edges)
    if (state.metadata) emit('metadata-restored', state.metadata)
    emit('graph-changed')
  }
}

function setValidationErrors(errors: Record<string, Record<string, string[]>>) {
  validationErrorsByNodeId.value = errors
}

function clearValidationErrors() {
  validationErrorsByNodeId.value = {}
}

function hasNodeValidationError(nodeId: string): boolean {
  return Boolean(validationErrorsByNodeId.value[nodeId] && Object.keys(validationErrorsByNodeId.value[nodeId]).length > 0)
}

function handleKeyboard(e: KeyboardEvent) {
  // Only handle when flow editor is focused (not in input/textarea)
  const tag = (e.target as HTMLElement)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return

  const isCtrlOrMeta = e.ctrlKey || e.metaKey

  if (isCtrlOrMeta && e.key === 'z' && !e.shiftKey) {
    e.preventDefault()
    performUndo()
  } else if (isCtrlOrMeta && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
    e.preventDefault()
    performRedo()
  }
}

/**
 * Load a partial rule (e.g. from a template) onto the canvas.
 * Converts conditions/actions/logic_operator into Vue Flow nodes and edges.
 */
function loadFromRuleData(ruleData: {
  conditions: LogicCondition[]
  actions: LogicAction[]
  logic_operator?: string
  priority?: number
  cooldown_seconds?: number
}) {
  // Set guard BEFORE nodes are loaded — prevents the props.rule watch
  // from clearing nodes when rule becomes null (template mode)
  templateLoadGuard = true

  const syntheticRule = {
    id: '',
    name: '',
    conditions: ruleData.conditions,
    actions: ruleData.actions,
    logic_operator: ruleData.logic_operator || 'AND',
    enabled: true,
    priority: ruleData.priority ?? 5,
    cooldown_seconds: ruleData.cooldown_seconds ?? 0,
  } as LogicRule

  try {
    const graph = ruleToGraph(syntheticRule)
    setNodes(graph.nodes)
    setEdges(graph.edges)
    pendingFitView = true
  } catch (err) {
    templateLoadGuard = false
    console.error('[RuleFlowEditor] Failed to load template data:', err)
    toast.error('Vorlage konnte nicht geladen werden')
  }
}

/** AUT-1399 Vitest: Kante setzen ohne UI-Drag (Nachweis: kein condition_ref). */
function addEdgeForTest(sourceId: string, targetId: string): void {
  addEdges([
    {
      id: `e-test-${sourceId}-${targetId}-${Date.now()}`,
      source: sourceId,
      target: targetId,
      animated: true,
      type: 'smoothstep',
      markerEnd: MarkerType.ArrowClosed,
    },
  ])
}

defineExpose({
  graphToRuleData,
  updateNodeData,
  deleteNode,
  duplicateNode,
  clearCanvas,
  loadFromRuleData,
  setValidationErrors,
  clearValidationErrors,
  fitView: () => fitView({ padding: 0.3 }),
  addEdgeForTest,
})
</script>

<template>
  <div
    ref="flowWrapper"
    class="flow-editor"
    :class="{ 'flow-editor--dragover': isDragOver }"
    tabindex="0"
    @dragover="onDragOverCanvas"
    @dragleave="onDragLeave"
    @drop="onDrop"
    @keydown="handleKeyboard"
  >
    <!-- Empty state hint -->
    <div v-if="nodes.length === 0" class="flow-editor__empty">
      <div class="flow-editor__empty-content">
        <div class="flow-editor__empty-arrows">
          <svg width="200" height="40" viewBox="0 0 200 40" fill="none">
            <path d="M20 20 L90 20" stroke="rgba(96,165,250,0.2)" stroke-width="1.5" stroke-dasharray="4 4">
              <animate attributeName="stroke-dashoffset" values="8;0" dur="1.5s" repeatCount="indefinite" />
            </path>
            <path d="M110 20 L180 20" stroke="rgba(192,132,252,0.2)" stroke-width="1.5" stroke-dasharray="4 4">
              <animate attributeName="stroke-dashoffset" values="8;0" dur="1.5s" repeatCount="indefinite" />
            </path>
            <circle cx="100" cy="20" r="3" fill="rgba(167,139,250,0.3)" />
          </svg>
        </div>
        <p class="flow-editor__empty-title">Arbeitsfläche bereit</p>
        <p class="flow-editor__empty-desc">
          Ziehe Bausteine aus der Palette hierher
        </p>
        <p class="flow-editor__empty-hint">
          Bedingungen &rarr; Logik &rarr; Aktionen
        </p>
      </div>
    </div>

    <!-- Drop overlay -->
    <Transition name="fade">
      <div v-if="isDragOver" class="flow-editor__drop-overlay">
        <div class="flow-editor__drop-text">Hier ablegen</div>
      </div>
    </Transition>

    <!-- Undo/Redo toolbar overlay -->
    <div class="flow-editor__undo-bar">
      <button
        class="flow-editor__undo-btn"
        :disabled="!logicStore.canUndo"
        title="Rückgängig (Ctrl+Z)"
        aria-label="Rückgängig"
        @click="performUndo"
      >
        <Undo2 class="w-3.5 h-3.5" />
      </button>
      <button
        class="flow-editor__undo-btn"
        :disabled="!logicStore.canRedo"
        title="Wiederholen (Ctrl+Shift+Z)"
        aria-label="Wiederholen"
        @click="performRedo"
      >
        <Redo2 class="w-3.5 h-3.5" />
      </button>
    </div>

    <VueFlow
      :class="{ 'flow-active': props.rule && logicStore.isRuleActive(props.rule.id) }"
      :default-zoom="1"
      :min-zoom="0.3"
      :max-zoom="2"
      :default-edge-options="flowDefaultEdgeOptions"
      :fit-view-on-init="false"
      :snap-to-grid="true"
      :snap-grid="flowSnapGrid"
    >
      <!-- ======================== SENSOR NODE ======================== -->
      <template #node-sensor="{ data, id }">
        <div
          class="rule-node rule-node--sensor"
          :class="{ 'rule-node--active': isNodeActive(id), 'rule-node--unconfigured': !data.espId, 'rule-node--validation-error': hasNodeValidationError(id) }"
        >
          <Handle type="source" :position="Position.Right" class="handle-source" />
          <div class="rule-node__header">
            <div class="rule-node__icon-wrap rule-node__icon-wrap--sensor">
              <component
                :is="sensorIcon(data.sensorType)"
                class="rule-node__icon"
              />
            </div>
            <div class="rule-node__header-text">
              <span
                class="rule-node__type"
                :class="{ 'rule-node__face-name': !!configuredSensorName(data.espId, data.gpio, data.sensorType) }"
              >{{ faceSensorPrimary(data) }}</span>
              <span class="rule-node__chip" :title="data.sensorType" style="display:none" aria-hidden="true">{{ data.sensorType }}</span>
            </div>
          </div>
          <div class="rule-node__body">
            <div class="rule-node__condition">
              <!-- AUT-1389: Plan-Abo → plan-abgeleitete Schwellen; sonst Node-Static -->
              <template v-for="face in [planFaceForSensor(data)]" :key="'sensor-face'">
                <template v-if="face">
                  <template v-if="face.kind === 'hysteresis_cooling'">
                    Ein &gt;{{ formatDeadbandEdge(face.high, data.sensorType) }}<span class="rule-node__unit">{{ sensorUnit(data.sensorType) }}</span>
                    · Aus &lt;{{ formatDeadbandEdge(face.low, data.sensorType) }}<span class="rule-node__unit">{{ sensorUnit(data.sensorType) }}</span>
                  </template>
                  <template v-else-if="face.kind === 'hysteresis_heating'">
                    Ein &lt;{{ formatDeadbandEdge(face.low, data.sensorType) }}<span class="rule-node__unit">{{ sensorUnit(data.sensorType) }}</span>
                    · Aus &gt;{{ formatDeadbandEdge(face.high, data.sensorType) }}<span class="rule-node__unit">{{ sensorUnit(data.sensorType) }}</span>
                  </template>
                  <template v-else-if="face.kind === 'between'">
                    {{ formatDeadbandEdge(face.low, data.sensorType) }}<span class="rule-node__unit">{{ sensorUnit(data.sensorType) }}</span>
                    {{ operatorDisplay.between }}
                    {{ formatDeadbandEdge(face.high, data.sensorType) }}<span class="rule-node__unit">{{ sensorUnit(data.sensorType) }}</span>
                  </template>
                  <template v-else>
                    Soll {{ formatDeadbandEdge(face.setpoint, data.sensorType) }}<span class="rule-node__unit">{{ sensorUnit(data.sensorType) }}</span>
                  </template>
                </template>
                <template v-else-if="data.operator === 'hysteresis' || data.isHysteresis">
                  <template v-if="data.activateAbove != null && data.deactivateBelow != null">
                    Ein &gt;{{ formatDeadbandEdge(Number(data.activateAbove), data.sensorType) }}<span class="rule-node__unit">{{ sensorUnit(data.sensorType) }}</span>
                    · Aus &lt;{{ formatDeadbandEdge(Number(data.deactivateBelow), data.sensorType) }}<span class="rule-node__unit">{{ sensorUnit(data.sensorType) }}</span>
                  </template>
                  <template v-else-if="data.activateBelow != null && data.deactivateAbove != null">
                    Ein &lt;{{ formatDeadbandEdge(Number(data.activateBelow), data.sensorType) }}<span class="rule-node__unit">{{ sensorUnit(data.sensorType) }}</span>
                    · Aus &gt;{{ formatDeadbandEdge(Number(data.deactivateAbove), data.sensorType) }}<span class="rule-node__unit">{{ sensorUnit(data.sensorType) }}</span>
                  </template>
                  <template v-else>
                    Hysterese
                  </template>
                </template>
                <template v-else-if="data.operator === 'between'">
                  {{ formatDeadbandEdge(Number(data.min), data.sensorType) }}<span class="rule-node__unit">{{ sensorUnit(data.sensorType) }}</span>
                  {{ operatorDisplay.between }}
                  {{ formatDeadbandEdge(Number(data.max), data.sensorType) }}<span class="rule-node__unit">{{ sensorUnit(data.sensorType) }}</span>
                </template>
                <template v-else>
                  {{ operatorDisplay[data.operator] || data.operator }} {{ formatDeadbandEdge(Number(data.value), data.sensorType) }}<span class="rule-node__unit">{{ sensorUnit(data.sensorType) }}</span>
                </template>
              </template>
            </div>
          </div>
          <div class="rule-node__footer">
            <template v-if="data.espId">
              <span
                class="rule-node__meta-item"
                :title="faceSecondaryDeviceGpio(data.espId, formatSensorGpio(data.gpio, data.sensorType)).title"
              >{{ faceSecondaryDeviceGpio(data.espId, formatSensorGpio(data.gpio, data.sensorType)).text }}</span>
            </template>
            <span v-else class="rule-node__unconfigured-hint">Nicht konfiguriert</span>
          </div>
        </div>
      </template>

      <!-- ======================== TIME NODE ======================== -->
      <template #node-time="{ data, id }">
        <div
          class="rule-node rule-node--time"
          :class="{ 'rule-node--active': isNodeActive(id), 'rule-node--validation-error': hasNodeValidationError(id) }"
        >
          <Handle type="source" :position="Position.Right" class="handle-source" />
          <div class="rule-node__header">
            <div class="rule-node__icon-wrap rule-node__icon-wrap--time">
              <Clock class="rule-node__icon" />
            </div>
            <span class="rule-node__type">Zeitfenster</span>
          </div>
          <div class="rule-node__body">
            <div class="rule-node__condition">
              {{ formatHourMinute(data.startHour, data.startMinute) }} – {{ formatHourMinute(data.endHour, data.endMinute) }}
            </div>
          </div>
          <div v-if="data.daysOfWeek?.length" class="rule-node__footer">
            <span class="rule-node__days-inline">
              {{ data.daysOfWeek.map((d: number) => ['So','Mo','Di','Mi','Do','Fr','Sa'][d]).join(' · ') }}
            </span>
          </div>
          <div v-else class="rule-node__footer">
            <span class="rule-node__meta-item">Täglich</span>
          </div>
        </div>
      </template>

      <!-- ======================== LOGIC NODE ======================== -->
      <template #node-logic="{ data, id }">
        <div
          class="rule-node rule-node--logic"
          :class="{ 'rule-node--active': isNodeActive(id), 'rule-node--validation-error': hasNodeValidationError(id) }"
        >
          <Handle
            type="target"
            :position="Position.Left"
            class="handle-target"
            title="Weitere Bedingung hinzufügen — ziehe einen Bedingungsblock hierher."
          />
          <Handle type="source" :position="Position.Right" class="handle-source" />
          <div class="rule-node__gate" :title="data.operator === 'AND' ? 'Alle Bedingungen müssen zutreffen' : 'Mindestens eine Bedingung muss zutreffen'">
            <div class="rule-node__icon-wrap rule-node__icon-wrap--logic">
              <GitMerge class="rule-node__gate-icon" />
            </div>
            <span class="rule-node__gate-label">{{ data.operator === 'AND' ? 'Alle müssen zutreffen' : 'Eines muss zutreffen' }}</span>
          </div>
        </div>
      </template>

      <!-- ======================== ACTUATOR NODE ======================== -->
      <template #node-actuator="{ data, id }">
        <div
          class="rule-node rule-node--actuator"
          :class="{ 'rule-node--active': isNodeActive(id), 'rule-node--unconfigured': !data.espId, 'rule-node--validation-error': hasNodeValidationError(id) }"
        >
          <Handle type="target" :position="Position.Left" class="handle-target" />
          <div class="rule-node__header">
            <div class="rule-node__icon-wrap rule-node__icon-wrap--actuator">
              <Power class="rule-node__icon" />
            </div>
            <span
              class="rule-node__type"
              :class="{ 'rule-node__face-name': !!configuredActuatorName(data.espId, data.gpio) }"
            >{{ faceActuatorPrimary(data) }}</span>
          </div>
          <div class="rule-node__body">
            <div class="rule-node__command" :class="`rule-node__command--${data.command?.toLowerCase()}`">
              {{ commandDisplay[data.command] || data.command }}
              <template v-if="data.command === 'PWM'"> {{ data.pwmValue ?? 0 }}%</template>
            </div>
            <div
              v-if="data.duration"
              class="rule-node__duration"
              :title="`Der Aktor schaltet automatisch aus, wenn er länger als ${formatDuration(data.duration)} aktiv ist — Sicherheitsschutz gegen unbeabsichtigten Dauerbetrieb.`"
            >
              <Timer class="rule-node__duration-icon" />
              Max. Laufzeit: {{ formatDuration(data.duration) }}
            </div>
          </div>
          <div class="rule-node__footer">
            <template v-if="data.espId">
              <span
                class="rule-node__meta-item"
                :title="faceSecondaryDeviceGpio(data.espId, formatGpio(data.gpio)).title"
              >{{ faceSecondaryDeviceGpio(data.espId, formatGpio(data.gpio)).text }}</span>
            </template>
            <span v-else class="rule-node__unconfigured-hint">Nicht konfiguriert</span>
          </div>
        </div>
      </template>

      <!-- ======================== NOTIFICATION NODE ======================== -->
      <template #node-notification="{ data, id }">
        <div
          class="rule-node rule-node--notification"
          :class="{ 'rule-node--active': isNodeActive(id), 'rule-node--validation-error': hasNodeValidationError(id) }"
        >
          <Handle type="target" :position="Position.Left" class="handle-target" />
          <div class="rule-node__header">
            <div class="rule-node__icon-wrap rule-node__icon-wrap--notification">
              <Bell class="rule-node__icon" />
            </div>
            <span class="rule-node__type">{{ channelDisplay[data.channel] || 'Dashboard' }}</span>
          </div>
          <div class="rule-node__body">
            <div v-if="data.target" class="rule-node__detail">
              <span class="rule-node__detail-value rule-node__detail-value--truncate">{{ data.target }}</span>
            </div>
            <div v-if="data.messageTemplate" class="rule-node__detail">
              <span class="rule-node__detail-value rule-node__detail-value--truncate rule-node__detail-value--dim">{{ data.messageTemplate }}</span>
            </div>
          </div>
          <div class="rule-node__footer">
            <span class="rule-node__meta-item">{{ data.channel || 'websocket' }}</span>
          </div>
        </div>
      </template>

      <!-- ======================== DELAY NODE ======================== -->
      <template #node-delay="{ data, id }">
        <div
          class="rule-node rule-node--delay"
          :class="{ 'rule-node--active': isNodeActive(id), 'rule-node--validation-error': hasNodeValidationError(id) }"
        >
          <Handle type="target" :position="Position.Left" class="handle-target" />
          <div class="rule-node__header">
            <div class="rule-node__icon-wrap rule-node__icon-wrap--delay">
              <Timer class="rule-node__icon" />
            </div>
            <span class="rule-node__type">Verzögerung</span>
          </div>
          <div class="rule-node__body">
            <div class="rule-node__condition">
              {{ data.seconds >= 60 ? `${Math.floor(data.seconds / 60)}m ${data.seconds % 60}s` : `${data.seconds}s` }}
            </div>
          </div>
        </div>
      </template>

      <!-- ======================== SEQUENCE NODE (AUT-1281 Hybrid-Redesign) ======================== -->
      <template #node-sequence="{ data, id }">
        <div
          class="rule-node rule-node--sequence"
          :class="{ 'rule-node--active': isNodeActive(id), 'rule-node--unconfigured': !data.steps?.length, 'rule-node--validation-error': hasNodeValidationError(id) }"
        >
          <Handle type="target" :position="Position.Left" class="handle-target" />
          <div class="rule-node__header">
            <div class="rule-node__icon-wrap rule-node__icon-wrap--sequence">
              <ListOrdered class="rule-node__icon" />
            </div>
            <span class="rule-node__type">Sequenz</span>
          </div>
          <div class="rule-node__body">
            <template v-if="data.steps?.length">
              <div class="rule-node__seq-steps" aria-label="Sequenz-Abfolge">
                <div
                  v-for="(step, idx) in (data.steps as SequenceStepDraft[])"
                  :key="idx"
                  class="rule-node__seq-step"
                  :class="{ 'rule-node__seq-step--pause': step.stepType === 'delay' }"
                >
                  <span class="rule-node__seq-step-index">{{ sequenceStepNumber(idx) }}</span>
                  <span
                    class="rule-node__seq-step-type"
                    :class="step.stepType === 'delay'
                      ? 'rule-node__seq-step-type--pause'
                      : 'rule-node__seq-step-type--actuator'"
                  >{{ sequenceStepTypeLabel(step.stepType) }}</span>
                  <span class="rule-node__seq-step-name">{{ faceStepPrimary(step) }}</span>
                  <span class="rule-node__seq-step-detail">{{ faceStepDetail(step) }}</span>
                </div>
              </div>
              <div v-if="data.maxDurationSeconds" class="rule-node__duration" title="Gesamtlimit aller Schritte">
                <Timer class="rule-node__duration-icon" />
                MAX. LAUFZEIT {{ formatDuration(data.maxDurationSeconds) }}
              </div>
            </template>
            <span v-else class="rule-node__unconfigured-hint">Keine Schritte</span>
          </div>
        </div>
      </template>

      <template #node-plugin="{ data, id }">
        <div
          class="rule-node rule-node--plugin"
          :class="{ 'rule-node--active': isNodeActive(id), 'rule-node--validation-error': hasNodeValidationError(id) }"
        >
          <Handle type="target" :position="Position.Left" class="handle-target" />
          <div class="rule-node__header">
            <div class="rule-node__icon-wrap rule-node__icon-wrap--plugin">
              <Puzzle class="rule-node__icon" />
            </div>
            <span class="rule-node__type">Plugin</span>
          </div>
          <div class="rule-node__body">
            <div class="rule-node__condition">
              {{ data.pluginId || 'Nicht konfiguriert' }}
            </div>
          </div>
        </div>
      </template>

      <!-- ======================== DIAGNOSTICS STATUS NODE (Condition) ======================== -->
      <template #node-diagnostics_status="{ data, id }">
        <div
          class="rule-node rule-node--diagnostics"
          :class="{ 'rule-node--active': isNodeActive(id), 'rule-node--validation-error': hasNodeValidationError(id) }"
        >
          <Handle type="source" :position="Position.Right" class="handle-source" />
          <div class="rule-node__header">
            <div class="rule-node__icon-wrap rule-node__icon-wrap--diagnostics">
              <Stethoscope class="rule-node__icon" />
            </div>
            <span class="rule-node__type">Diagnose-Status</span>
          </div>
          <div class="rule-node__body">
            <div class="rule-node__condition">
              {{ data.checkName || 'Nicht konfiguriert' }}
              {{ data.operator || '==' }}
              {{ data.expectedStatus || 'critical' }}
            </div>
          </div>
        </div>
      </template>

      <!-- ======================== RUN DIAGNOSTIC NODE (Action) ======================== -->
      <template #node-run_diagnostic="{ data, id }">
        <div
          class="rule-node rule-node--diagnostics"
          :class="{ 'rule-node--active': isNodeActive(id), 'rule-node--validation-error': hasNodeValidationError(id) }"
        >
          <Handle type="target" :position="Position.Left" class="handle-target" />
          <div class="rule-node__header">
            <div class="rule-node__icon-wrap rule-node__icon-wrap--diagnostics">
              <Stethoscope class="rule-node__icon" />
            </div>
            <span class="rule-node__type">Diagnose starten</span>
          </div>
          <div class="rule-node__body">
            <div class="rule-node__condition">
              {{ data.checkName || 'Vollständige Diagnose' }}
            </div>
          </div>
        </div>
      </template>

      <!-- ======================== MESS-BINDUNG (sensor_diff umgewidmet, AUT-1399) ======================== -->
      <template #node-sensor_diff="{ data, id }">
        <div
          class="rule-node rule-node--sensor"
          :class="{ 'rule-node--active': isNodeActive(id), 'rule-node--validation-error': hasNodeValidationError(id) }"
          data-testid="node-measure-binding"
        >
          <Handle type="target" :position="Position.Left" class="handle-target" />
          <Handle type="source" :position="Position.Right" class="handle-source" />
          <div class="rule-node__header">
            <div class="rule-node__icon-wrap rule-node__icon-wrap--sensor">
              <ArrowLeftRight class="rule-node__icon" />
            </div>
            <span class="rule-node__type rule-node__type--measure">{{ faceMeasureBindingTitle(data) }}</span>
          </div>
          <div class="rule-node__body">
            <div class="rule-node__condition rule-node__condition--compact">
              <span class="rule-node__meta-item" :title="faceMeasurePointLabels(data).leftValue">
                {{ faceMeasurePointLabels(data).leftLabel }}:
                {{ faceMeasurePointLabels(data).leftValue }}
              </span>
              <span class="rule-node__meta-sep" />
              <span class="rule-node__meta-item" :title="faceMeasurePointLabels(data).rightValue">
                {{ faceMeasurePointLabels(data).rightLabel }}:
                {{ faceMeasurePointLabels(data).rightValue }}
              </span>
            </div>
            <div class="rule-node__value rule-node__value--measure">
              {{ faceMeasurePointLabels(data).measureLine }}
            </div>
          </div>
        </div>
      </template>

      <!-- ======================== NOT RUNNING NODE (Interlock, AUT-1333) ======================== -->
      <template #node-not_running="{ data, id }">
        <div
          class="rule-node rule-node--not-running"
          :class="{ 'rule-node--active': isNodeActive(id), 'rule-node--validation-error': hasNodeValidationError(id) }"
        >
          <Handle type="source" :position="Position.Right" class="handle-source" />
          <div class="rule-node__header">
            <div class="rule-node__icon-wrap rule-node__icon-wrap--not-running">
              <ShieldOff class="rule-node__icon" />
            </div>
            <span class="rule-node__type">Nicht laufend</span>
          </div>
          <div class="rule-node__body">
            <div
              class="rule-node__condition rule-node__condition--compact"
              :title="faceNotRunningSecondary(data).title"
            >
              {{ faceNotRunningPrimary(data) }}
            </div>
            <div
              v-if="faceNotRunningSecondary(data).text"
              class="rule-node__meta-item"
              :title="faceNotRunningSecondary(data).title"
            >
              {{ faceNotRunningSecondary(data).text }}
            </div>
            <div class="rule-node__value">Interlock</div>
          </div>
        </div>
      </template>

      <!-- Background, Controls, MiniMap -->
      <Background :gap="20" :size="1" pattern-color="rgba(255,255,255,0.03)" />
      <Controls position="bottom-left" />
      <MiniMap
        :pannable="true"
        :zoomable="true"
        :node-color="miniMapNodeColor"
      />
    </VueFlow>
  </div>
</template>

<style scoped>
.flow-editor {
  flex: 1;
  position: relative;
  min-height: 0;
  border: 2px solid transparent;
  transition: border-color var(--transition-base);
}

.flow-editor--dragover {
  border-color: var(--color-iridescent-2);
}

/* Empty state */
.flow-editor__empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-dropdown);
  pointer-events: none;
}

.flow-editor__empty-content {
  text-align: center;
  max-width: 320px;
  animation: canvas-empty-in 0.4s ease-out;
}

@keyframes canvas-empty-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.flow-editor__empty-arrows {
  margin-bottom: 1rem;
  color: var(--color-text-muted);
  opacity: 0.5;
}

.flow-editor__empty-title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 0.375rem;
}

.flow-editor__empty-desc {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  line-height: 1.5;
  margin-bottom: 0.625rem;
}

.flow-editor__empty-hint {
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.1em;
  color: var(--color-iridescent-2);
  opacity: 0.5;
}

/* Drop overlay */
.flow-editor__drop-overlay {
  position: absolute;
  inset: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(129, 140, 248, 0.04);
  border: 2px dashed rgba(129, 140, 248, 0.3);
  border-radius: var(--radius-lg);
  z-index: var(--z-dropdown);
  pointer-events: none;
}

.flow-editor__drop-text {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-iridescent-2);
  padding: 0.625rem 1.25rem;
  background: rgba(13, 13, 22, 0.8);
  backdrop-filter: blur(12px);
  border-radius: var(--radius-md);
  border: 1px solid rgba(129, 140, 248, 0.2);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
}

/* ======================== CUSTOM NODES ======================== */

.rule-node {
  width: 210px;
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25), 0 0 1px rgba(255,255,255,0.05) inset;
  transition: all 0.2s var(--ease-out);
  overflow: hidden;
  position: relative;
}

.rule-node::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
  opacity: 0.9;
}

.rule-node:hover {
  border-color: var(--glass-border-hover);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35), 0 0 1px rgba(255,255,255,0.08) inset;
  transform: translateY(-1px);
}

/* Selected state */
:deep(.vue-flow__node.selected) .rule-node {
  border-color: var(--color-iridescent-2);
  box-shadow: 0 0 0 2px rgba(129, 140, 248, 0.15), 0 8px 32px rgba(0, 0, 0, 0.35);
}

/* Unconfigured state */
.rule-node--unconfigured {
  border-style: dashed;
  border-color: rgba(129, 140, 248, 0.25);
}

/* Active flash (rule executing) */
.rule-node--active {
  animation: node-execution-flash 0.8s ease;
}

.rule-node--validation-error {
  border-color: var(--color-error);
  box-shadow: 0 0 0 1px rgba(248, 113, 113, 0.35), 0 8px 32px rgba(0, 0, 0, 0.35);
}

@keyframes node-execution-flash {
  0% { box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25); }
  30% { box-shadow: 0 0 40px rgba(96, 165, 250, 0.5), 0 0 80px rgba(96, 165, 250, 0.2); }
  100% { box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25); }
}

/* Type-specific accent via ::before pseudo */
.rule-node--sensor::before {
  background: linear-gradient(90deg, var(--color-iridescent-1), rgba(96, 165, 250, 0.3));
}

.rule-node--time::before {
  background: linear-gradient(90deg, var(--color-warning), rgba(251, 191, 36, 0.3));
}

.rule-node--logic::before {
  background: linear-gradient(90deg, var(--color-iridescent-3), rgba(167, 139, 250, 0.3));
}

.rule-node--logic {
  width: auto;
  min-width: 160px;
}

.rule-node--actuator::before {
  background: linear-gradient(90deg, var(--color-iridescent-4), rgba(192, 132, 252, 0.3));
}

.rule-node--notification::before {
  background: linear-gradient(90deg, var(--color-success), rgba(52, 211, 153, 0.3));
}

.rule-node--delay::before {
  background: linear-gradient(90deg, var(--color-text-secondary), rgba(133, 133, 160, 0.3));
}

.rule-node--plugin::before {
  background: linear-gradient(90deg, var(--color-warning), rgba(245, 158, 11, 0.3));
}

.rule-node--diagnostics::before {
  background: linear-gradient(90deg, var(--color-real), rgba(34, 211, 238, 0.3));
}

.rule-node--not-running::before {
  background: linear-gradient(90deg, var(--color-warning), rgba(251, 191, 36, 0.35));
}

/* AUT-1281: Sequenz-Node — eigene Breite (schmaler als vorher, aber mehr Inhalt) + Akzentfarbe */
.rule-node--sequence {
  width: 260px;
}

.rule-node--sequence::before {
  background: linear-gradient(90deg, var(--color-real), rgba(34, 211, 238, 0.3));
}

/* Node inner layout */
.rule-node__header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 0.75rem 0.25rem;
}

.rule-node__header-text {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  min-width: 0;
}

/* Icon wrapper with background */
.rule-node__icon-wrap {
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}

.rule-node__icon-wrap--sensor {
  background: rgba(96, 165, 250, 0.12);
  color: var(--color-iridescent-1);
}

.rule-node__icon-wrap--time {
  background: rgba(251, 191, 36, 0.12);
  color: var(--color-warning);
}

.rule-node__icon-wrap--logic {
  background: rgba(167, 139, 250, 0.12);
  color: var(--color-iridescent-3);
}

.rule-node__icon-wrap--actuator {
  background: rgba(192, 132, 252, 0.12);
  color: var(--color-iridescent-4);
}

.rule-node__icon-wrap--notification {
  background: rgba(52, 211, 153, 0.12);
  color: var(--color-success);
}

.rule-node__icon-wrap--delay {
  background: rgba(133, 133, 160, 0.12);
  color: var(--color-text-secondary);
}

.rule-node__icon-wrap--plugin {
  background: rgba(245, 158, 11, 0.12);
  color: var(--color-warning);
}

.rule-node__icon-wrap--diagnostics {
  background: rgba(34, 211, 238, 0.12);
  color: var(--color-real);
}

.rule-node__icon-wrap--not-running {
  background: rgba(251, 191, 36, 0.12);
  color: var(--color-warning);
}

.rule-node__icon-wrap--sequence {
  background: rgba(34, 211, 238, 0.12);
  color: var(--color-real);
}

.rule-node__icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.rule-node__type {
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-text-muted);
  line-height: 1.3;
}

/* AUT-1399: Sensor-Klarname nicht als „FLOW“ per Uppercase entstellen */
.rule-node__type--measure {
  text-transform: none;
  letter-spacing: 0;
  font-size: var(--text-sm);
  color: var(--color-text-primary);
}

/* AUT-632: vergebener Name primär — nicht Uppercase-Kategorie */
.rule-node__face-name {
  font-size: 0.8125rem;
  font-weight: 600;
  text-transform: none;
  letter-spacing: 0;
  color: var(--color-text-primary);
  line-height: 1.3;
}

.rule-node__condition--compact {
  font-size: 0.875rem;
  font-weight: 600;
}

/* Sensor chip (e.g. "DS18B20") */
.rule-node__chip {
  font-size: 0.5625rem;
  font-weight: 600;
  padding: 1px 5px;
  border-radius: var(--radius-xs);
  background: rgba(255, 255, 255, 0.05);
  color: var(--color-text-muted);
  letter-spacing: 0.02em;
  white-space: nowrap;
  flex-shrink: 0;
}

.rule-node__body {
  padding: 0.125rem 0.75rem 0.5rem;
}

.rule-node__detail {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  margin-bottom: 0.25rem;
}

.rule-node__detail-label {
  font-size: 0.5625rem;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 1px 4px;
  background: rgba(255,255,255,0.04);
  border-radius: var(--radius-xs);
}

.rule-node__detail-value {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  font-weight: 500;
}

.rule-node__detail-value--truncate {
  max-width: 170px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rule-node__detail-value--dim {
  color: var(--color-text-muted);
  font-style: italic;
  font-size: 0.6875rem;
}

.rule-node__condition {
  font-size: clamp(1rem, 1.375rem, 1.375rem);
  font-weight: 700;
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em;
  line-height: 1.3;
  word-break: break-word;
}

.rule-node__unit {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--color-text-muted);
  margin-left: 1px;
}

/* Node footer with meta info */
.rule-node__footer {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.375rem 0.75rem;
  border-top: 1px solid rgba(255, 255, 255, 0.04);
  background: rgba(0, 0, 0, 0.12);
}

.rule-node__meta-item {
  font-size: 0.625rem;
  font-weight: 500;
  color: var(--color-text-muted);
  letter-spacing: 0.02em;
}

.rule-node__meta-sep {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--color-text-muted);
  opacity: 0.4;
  flex-shrink: 0;
}

.rule-node__unconfigured-hint {
  font-size: 0.625rem;
  font-weight: 500;
  color: var(--color-warning);
  font-style: italic;
  letter-spacing: 0.01em;
}

.rule-node__days-inline {
  font-size: 0.625rem;
  font-weight: 500;
  color: var(--color-text-muted);
  letter-spacing: 0.03em;
}

/* Logic gate node */
.rule-node__gate {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 1rem;
}

.rule-node__gate-icon {
  width: 16px;
  height: 16px;
  color: var(--color-iridescent-3);
}

.rule-node__gate-label {
  font-size: 1rem;
  font-weight: 800;
  color: var(--color-iridescent-3);
  letter-spacing: 0.08em;
}

/* Actuator command badge */
.rule-node__command {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.5rem;
  font-size: 0.8125rem;
  font-weight: 700;
  border-radius: var(--radius-sm);
  letter-spacing: 0.02em;
}

.rule-node__command--on {
  background: rgba(52, 211, 153, 0.12);
  color: var(--color-success);
  border: 1px solid rgba(52, 211, 153, 0.15);
}

.rule-node__command--off {
  background: rgba(248, 113, 113, 0.12);
  color: var(--color-error);
  border: 1px solid rgba(248, 113, 113, 0.15);
}

.rule-node__command--pwm {
  background: rgba(96, 165, 250, 0.12);
  color: var(--color-iridescent-1);
  border: 1px solid rgba(96, 165, 250, 0.15);
}

.rule-node__command--toggle {
  background: rgba(251, 191, 36, 0.12);
  color: var(--color-warning);
  border: 1px solid rgba(251, 191, 36, 0.15);
}

.rule-node__duration {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.6875rem;
  color: var(--color-text-muted);
  margin-top: 0.375rem;
}

/* AUT-1281/AUT-1306: Sequenz-Abfolge Nr · Typ · Primär · Detail im Node-Gesicht */
.rule-node__seq-steps {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 9.5rem;
  overflow-y: auto;
}

.rule-node__seq-step {
  display: flex;
  align-items: baseline;
  gap: 0.3rem;
  padding: 2px 0;
  font-size: 0.6875rem;
  line-height: 1.35;
}

.rule-node__seq-step-index {
  flex-shrink: 0;
  min-width: 12px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--color-text-muted);
  text-align: right;
}

.rule-node__seq-step-type {
  flex-shrink: 0;
  font-size: 0.625rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  padding: 0 0.25rem;
  border-radius: var(--radius-sm);
  line-height: 1.4;
}

.rule-node__seq-step-type--actuator {
  color: var(--color-real);
  background: color-mix(in srgb, var(--color-real) 18%, transparent);
}

.rule-node__seq-step-type--pause {
  color: var(--color-warning);
  background: color-mix(in srgb, var(--color-warning) 16%, transparent);
}

.rule-node__seq-step-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text-secondary);
  font-weight: 500;
}

.rule-node__seq-step--pause .rule-node__seq-step-name {
  color: var(--color-text-muted);
  font-style: italic;
}

.rule-node__seq-step-detail {
  flex-shrink: 0;
  color: var(--color-text-primary);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.rule-node__duration-icon {
  width: 11px;
  height: 11px;
  opacity: 0.6;
}

/* ======================== HANDLE STYLING ======================== */

:deep(.vue-flow__handle) {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--color-bg-primary);
  border: 2.5px solid rgba(129, 140, 248, 0.6);
  transition: all 0.15s var(--ease-out);
  z-index: var(--z-dropdown);
}

/* AUT-1318 / AUT-1138: Touch hit-target ≥44px; visual handle stays 18px (mouse look unchanged) */
:deep(.vue-flow__handle::after) {
  content: '';
  position: absolute;
  width: 44px;
  height: 44px;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  border-radius: 50%;
}

/* Source handles (output - right side) */
:deep(.vue-flow__handle.vue-flow__handle-right) {
  background: rgba(129, 140, 248, 0.25);
  border-color: rgba(129, 140, 248, 0.7);
  right: -9px;
}

/* Target handles (input - left side) */
:deep(.vue-flow__handle.vue-flow__handle-left) {
  background: var(--color-bg-primary);
  border-color: rgba(129, 140, 248, 0.5);
  left: -9px;
}

:deep(.vue-flow__handle:hover) {
  background: var(--color-iridescent-2);
  border-color: var(--color-iridescent-2);
  box-shadow: 0 0 16px rgba(129, 140, 248, 0.6);
  transform: scale(1.3);
}

:deep(.vue-flow__handle-connecting) {
  background: var(--color-iridescent-1);
  border-color: var(--color-iridescent-1);
  box-shadow: 0 0 20px rgba(96, 165, 250, 0.7);
  transform: scale(1.35);
}

:deep(.vue-flow__handle-valid) {
  background: var(--color-success);
  border-color: var(--color-success);
  box-shadow: 0 0 18px rgba(52, 211, 153, 0.6);
  transform: scale(1.35);
}

/* ======================== EDGE STYLING ======================== */

:deep(.vue-flow__edge-path) {
  stroke: rgba(129, 140, 248, 0.5);
  stroke-width: 2;
}

:deep(.vue-flow__edge.animated .vue-flow__edge-path) {
  stroke-dasharray: 6 4;
  animation: edge-flow 1.8s linear infinite;
}

:deep(.vue-flow__edge:hover .vue-flow__edge-path) {
  stroke: var(--color-iridescent-1);
  stroke-width: 2.5;
  filter: drop-shadow(0 0 6px rgba(96, 165, 250, 0.4));
}

:deep(.vue-flow__edge .vue-flow__edge-interaction) {
  stroke-width: 32;
}

:deep(.vue-flow__arrowhead) {
  fill: rgba(129, 140, 248, 0.6);
}

:deep(.vue-flow__edge:hover .vue-flow__arrowhead) {
  fill: var(--color-iridescent-1);
}

@keyframes edge-flow {
  from { stroke-dashoffset: 10; }
  to { stroke-dashoffset: 0; }

}

/* Connection line while dragging */
:deep(.vue-flow__connection-path) {
  stroke: var(--color-iridescent-2);
  stroke-width: 2;
  stroke-dasharray: 5 3;
}

/* Selection box */
:deep(.vue-flow__selection) {
  background: rgba(129, 140, 248, 0.06);
  border: 1px solid rgba(129, 140, 248, 0.25);
  border-radius: var(--radius-sm);
}

/* ======================== VUE FLOW THEME OVERRIDES ======================== */

:deep(.vue-flow) {
  background: var(--color-bg-primary);
}

:deep(.vue-flow__pane) {
  cursor: default;
}

:deep(.vue-flow__minimap) {
  background: rgba(13, 13, 22, 0.85);
  backdrop-filter: blur(8px);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  overflow: hidden;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
}

:deep(.vue-flow__minimap-mask) {
  fill: rgba(7, 7, 13, 0.75);
}

:deep(.vue-flow__controls) {
  display: flex;
  flex-direction: column;
  gap: 2px;
  background: transparent;
  border: none;
  box-shadow: none;
}

:deep(.vue-flow__controls-button) {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(13, 13, 22, 0.85);
  backdrop-filter: blur(8px);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

:deep(.vue-flow__controls-button:hover) {
  background: var(--color-bg-tertiary);
  border-color: rgba(129, 140, 248, 0.3);
  color: var(--color-text-primary);
}

:deep(.vue-flow__controls-button svg) {
  fill: currentColor;
  width: 14px;
  height: 14px;
}

/* Fade transition */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* ======================== REDUCED MOTION ======================== */

@media (prefers-reduced-motion: reduce) {
  .rule-node:hover {
    transform: none;
  }

  .rule-node--active {
    animation: none;
    box-shadow: 0 0 0 2px var(--color-iridescent-1);
  }

  :deep(.vue-flow__edge.animated .vue-flow__edge-path) {
    animation: none;
  }

  :deep(.vue-flow__handle:hover) {
    transform: none;
  }

  :deep(.vue-flow__handle-connecting),
  :deep(.vue-flow__handle-valid) {
    transform: none;
  }

  .flow-editor__empty-content {
    animation: none;
  }
}

/* ======================== UNDO/REDO OVERLAY ======================== */

.flow-editor__undo-bar {
  position: absolute;
  top: 0.625rem;
  left: 0.625rem;
  z-index: var(--z-dropdown);
  display: flex;
  gap: 2px;
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  padding: 2px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.flow-editor__undo-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.flow-editor__undo-btn:hover:not(:disabled) {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.flow-editor__undo-btn:disabled {
  opacity: 0.25;
  cursor: not-allowed;
}
</style>
