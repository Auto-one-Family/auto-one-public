/**
 * Monitor L2 — Zone Monitor Data Types
 *
 * Mirrors server response from GET /zone/{zone_id}/monitor-data.
 * Used by MonitorView L2 for subzone accordion display.
 */

export interface SubzoneSensorEntry {
  esp_id: string
  gpio: number
  sensor_type: string
  name: string | null
  raw_value: number | null
  unit: string
  quality: string
  last_read: string | null
  /** Operating mode from sensor config — 'continuous' | 'on_demand' | 'scheduled' | 'paused' */
  operating_mode?: string | null
  /** Server-side staleness flag */
  is_stale?: boolean
}

export interface SubzoneActuatorEntry {
  esp_id: string
  gpio: number
  actuator_type: string
  name: string | null
  state: boolean
  pwm_value: number
  emergency_stopped: boolean
}

export interface SubzoneGroup {
  subzone_id: string | null
  subzone_name: string
  sensors: SubzoneSensorEntry[]
  actuators: SubzoneActuatorEntry[]
}

export interface ZoneMonitorData {
  zone_id: string
  zone_name: string
  subzones: SubzoneGroup[]
  sensor_count: number
  actuator_count: number
  alarm_count: number
}
