export interface RuleValidationIssue {
  loc?: Array<string | number>
  msg?: string
  type?: string
}

export interface RuleNodeValidationErrors {
  [nodeId: string]: Record<string, string[]>
}

export interface RuleMetadataValidationErrors {
  [field: string]: string[]
}

export interface RuleValidationMappingResult {
  nodeErrors: RuleNodeValidationErrors
  metadataErrors: RuleMetadataValidationErrors
  summary: string[]
}

export interface RuleValidationNodeMap {
  conditionNodeIds: string[]
  actionNodeIds: string[]
}

function toFieldName(raw: string): string {
  const map: Record<string, string> = {
    esp_id: 'espId',
    sensor_type: 'sensorType',
    start_hour: 'startHour',
    start_minute: 'startMinute',
    end_hour: 'endHour',
    end_minute: 'endMinute',
    days_of_week: 'daysOfWeek',
    message_template: 'messageTemplate',
    duration_seconds: 'duration',
    cooldown_seconds: 'cooldown_seconds',
  }
  return map[raw] ?? raw
}

function pushNodeError(
  out: RuleNodeValidationErrors,
  nodeId: string,
  field: string,
  message: string
): void {
  if (!out[nodeId]) out[nodeId] = {}
  if (!out[nodeId][field]) out[nodeId][field] = []
  out[nodeId][field].push(message)
}

function pushMetadataError(
  out: RuleMetadataValidationErrors,
  field: string,
  message: string
): void {
  if (!out[field]) out[field] = []
  out[field].push(message)
}

function toMessage(issue: RuleValidationIssue): string {
  if (typeof issue.msg === 'string' && issue.msg.trim().length > 0) return issue.msg
  return 'Ungueltiger Wert'
}

export function extractRuleValidationIssues(error: unknown): RuleValidationIssue[] {
  const data = (error as { response?: { data?: { detail?: unknown } } })?.response?.data
  const detail = (data as { detail?: unknown })?.detail
  if (!Array.isArray(detail)) return []
  return detail.filter((item): item is RuleValidationIssue => typeof item === 'object' && item !== null)
}

export function mapRuleValidationIssues(
  issues: RuleValidationIssue[],
  nodeMap: RuleValidationNodeMap
): RuleValidationMappingResult {
  const nodeErrors: RuleNodeValidationErrors = {}
  const metadataErrors: RuleMetadataValidationErrors = {}
  const summary: string[] = []

  for (const issue of issues) {
    const loc = Array.isArray(issue.loc) ? issue.loc : []
    const msg = toMessage(issue)
    if (msg) summary.push(msg)

    if (loc.length >= 4 && loc[0] === 'body' && loc[1] === 'conditions' && typeof loc[2] === 'number') {
      const idx = loc[2]
      const nodeId = nodeMap.conditionNodeIds[idx]
      const field = typeof loc[3] === 'string' ? toFieldName(loc[3]) : 'general'
      if (nodeId) {
        pushNodeError(nodeErrors, nodeId, field, msg)
      } else {
        pushMetadataError(metadataErrors, 'conditions', msg)
      }
      continue
    }

    if (loc.length >= 4 && loc[0] === 'body' && loc[1] === 'actions' && typeof loc[2] === 'number') {
      const idx = loc[2]
      const nodeId = nodeMap.actionNodeIds[idx]
      const field = typeof loc[3] === 'string' ? toFieldName(loc[3]) : 'general'
      if (nodeId) {
        pushNodeError(nodeErrors, nodeId, field, msg)
      } else {
        pushMetadataError(metadataErrors, 'actions', msg)
      }
      continue
    }

    if (loc.length >= 2 && loc[0] === 'body' && typeof loc[1] === 'string') {
      pushMetadataError(metadataErrors, toFieldName(loc[1]), msg)
      continue
    }

    pushMetadataError(metadataErrors, 'general', msg)
  }

  return { nodeErrors, metadataErrors, summary }
}
