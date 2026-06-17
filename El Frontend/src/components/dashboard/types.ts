export interface ComponentCardItem {
  type: 'sensor' | 'actuator'
  gpio: number
  sensorType?: string
  actuatorType?: string
  name: string | null
  value: number | null
  unit: string
  quality?: string
  state?: boolean
  emergencyStopped?: boolean
  espId: string
  espName: string | null
  zoneName: string | null
  zoneId: string | null
  subzoneName: string | null
  subzoneId: string | null
  isStale?: boolean
}
