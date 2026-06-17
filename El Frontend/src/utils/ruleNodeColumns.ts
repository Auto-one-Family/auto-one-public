/**
 * Rule Node Column Mapping (AUT-249)
 *
 * Pure helpers that classify rule-flow node types into the three visual
 * editor columns ("Wann starten?" / "Wenn auch" / "Dann ausführen") and
 * provide horizontal placement suggestions for drag-and-drop / migration.
 *
 * Visual layout only — does not change the LogicRule schema or any
 * server-side validation. The Vue Flow drag-and-drop mechanism is unaffected.
 */

/** Logical column an editor node belongs to. */
export type RuleNodeColumn = 'trigger' | 'condition' | 'action'

/** Horizontal x-position fractions per column (relative to canvas width). */
export const COLUMN_X_FRACTION: Record<RuleNodeColumn, number> = {
  trigger: 0.1,
  condition: 0.4,
  action: 0.7,
}

/** Tolerance band (fraction of canvas width) used for migration-only checks. */
export const COLUMN_MIGRATION_TOLERANCE = 0.15

/**
 * Resolve the editor column for a given rule-flow node type.
 *
 * Mapping mirrors the visual layout requirement in AUT-249:
 *  - trigger:   sensor (incl. hysteresis), time, diagnostics_status, sensor_diff
 *  - condition: logic (compound AND/OR)
 *  - action:    actuator, notification, delay, plugin, run_diagnostic
 *
 * Unknown node types fall back to "condition" (middle column) — this keeps
 * the canvas usable even when new node kinds are introduced before this
 * helper is updated.
 */
export function getNodeColumn(nodeType: string | undefined | null): RuleNodeColumn {
  switch (nodeType) {
    // Trigger column — "Wann starten?"
    case 'sensor':
    case 'sensor_threshold':
    case 'time':
    case 'time_window':
    case 'hysteresis':
    case 'diagnostics_status':
    case 'sensor_diff':
      return 'trigger'

    // Condition column — "Wenn auch"
    case 'logic':
    case 'compound':
      return 'condition'

    // Action column — "Dann ausführen"
    case 'actuator':
    case 'actuator_command':
    case 'notification':
    case 'delay':
    case 'plugin':
    case 'autoops_trigger':
    case 'run_diagnostic':
      return 'action'

    default:
      return 'condition'
  }
}

/**
 * Compute the x coordinate (in pixels) that places a node into its column.
 *
 * @param nodeType  The rule-flow node type identifier.
 * @param canvasWidth  Visible canvas width in pixels.
 * @returns Suggested x position for new or migrated nodes.
 */
export function getNodeColumnX(nodeType: string | undefined | null, canvasWidth: number): number {
  const column = getNodeColumn(nodeType)
  const safeWidth = Number.isFinite(canvasWidth) && canvasWidth > 0 ? canvasWidth : 900
  return Math.round(safeWidth * COLUMN_X_FRACTION[column])
}

/**
 * Decide whether an existing node position deviates strongly enough from
 * its target column to justify a soft migration on initial load.
 *
 * Returns `true` when the node sits clearly outside its column band —
 * i.e. the user has not deliberately placed it there. We do NOT migrate
 * minor offsets so manual layouts stay intact.
 */
export function shouldMigrateNodePosition(
  nodeType: string | undefined | null,
  currentX: number,
  canvasWidth: number,
): boolean {
  if (!Number.isFinite(currentX)) return true
  const safeWidth = Number.isFinite(canvasWidth) && canvasWidth > 0 ? canvasWidth : 900
  const targetX = getNodeColumnX(nodeType, safeWidth)
  const tolerance = safeWidth * COLUMN_MIGRATION_TOLERANCE
  return Math.abs(currentX - targetX) > tolerance
}
