/**
 * useSensorSubzoneCoverage — dünner n:m Read/Write-Baustein (Sensor↔Subzone)
 *
 * AUT-1161 / geteilt mit AUT-1321 (dort read-only).
 *
 * Einziger FE-Pfad zur Junction:
 *   GET/POST/DELETE …/subzones/{id}/sensors  via subzonesApi.*
 *
 * Doppelpfad-Vorrangregel:
 * 1) Abdeckung (Ist/Soll) → NUR diese Junction-Methoden
 * 2) Heimat-/GPIO (Einzelfall) → assignSubzone / assigned_gpios — nicht hier
 * 3) assigned_subzones JSON bleibt tot
 *
 * Kein Aktor-/Steuerbezug — reine Verortung.
 */

import { subzonesApi } from '@/api/subzones'
import type { SensorSubzoneAssignmentInfo } from '@/types'

export interface SubzoneCoverageRef {
  id: string
  name: string
}

export interface SensorCoverageEntry {
  subzoneId: string
  name: string
}

/**
 * Thin API wrapper — no UI state. Safe to share across views.
 */
export function useSensorSubzoneCoverage() {
  /** Sensors explicitly assigned to one subzone (junction only). */
  async function listSensorsForSubzone(
    espId: string,
    subzoneId: string,
  ): Promise<SensorSubzoneAssignmentInfo[]> {
    const res = await subzonesApi.getSensorAssignments(espId, subzoneId)
    return res.assignments ?? []
  }

  /**
   * Which subzones does this sensor cover? Scans junction GET per subzone.
   * GPIO-first-match is intentionally ignored.
   */
  async function listSubzonesForSensor(
    espId: string,
    sensorConfigId: string,
    subzones: SubzoneCoverageRef[],
  ): Promise<SensorCoverageEntry[]> {
    const entries = await Promise.all(
      subzones.map(async (sz) => {
        try {
          const assignments = await listSensorsForSubzone(espId, sz.id)
          const hit = assignments.some((a) => a.sensor_config_id === sensorConfigId)
          return hit ? ({ subzoneId: sz.id, name: sz.name } satisfies SensorCoverageEntry) : null
        } catch {
          return null
        }
      }),
    )
    return entries.filter((e): e is SensorCoverageEntry => e != null)
  }

  async function assignSensor(
    espId: string,
    subzoneId: string,
    sensorConfigId: string,
  ): Promise<SensorSubzoneAssignmentInfo> {
    return subzonesApi.assignSensor(espId, subzoneId, sensorConfigId)
  }

  async function removeSensor(
    espId: string,
    subzoneId: string,
    sensorConfigId: string,
  ): Promise<void> {
    await subzonesApi.removeSensor(espId, subzoneId, sensorConfigId)
  }

  /**
   * Apply Soll vs Ist for one sensor — only junction POST/DELETE, no GPIO side effects.
   */
  async function syncSensorCoverage(
    espId: string,
    sensorConfigId: string,
    istSubzoneIds: string[],
    sollSubzoneIds: string[],
  ): Promise<void> {
    const ist = new Set(istSubzoneIds)
    const soll = new Set(sollSubzoneIds)
    const toAdd = [...soll].filter((id) => !ist.has(id))
    const toRemove = [...ist].filter((id) => !soll.has(id))

    await Promise.all([
      ...toAdd.map((subzoneId) => assignSensor(espId, subzoneId, sensorConfigId)),
      ...toRemove.map((subzoneId) => removeSensor(espId, subzoneId, sensorConfigId)),
    ])
  }

  return {
    listSensorsForSubzone,
    listSubzonesForSensor,
    assignSensor,
    removeSensor,
    syncSensorCoverage,
  }
}
