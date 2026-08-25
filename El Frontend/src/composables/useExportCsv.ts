import { ref } from 'vue'
import { sensorsApi } from '@/api/sensors'
import type { SensorDataResolution, SensorReading } from '@/types'

/**
 * Server-Default von GET /api/v1/sensors/export (`_EXPORT_DEFAULT_COLUMNS`).
 * Ein Kopf für Dashboard, History und Monitor — keine eigenen Client-Header.
 */
export const SENSOR_EXPORT_DEFAULT_COLUMNS = [
  'timestamp',
  'processed_value',
  'unit',
  'quality',
  'sensor_type',
] as const

/** Export parameters for a single sensor */
export interface CsvExportParams {
  espId: string
  gpio: number
  sensorType: string
  sensorName: string
  zoneName?: string
  startTime: Date
  endTime: Date
  resolution: SensorDataResolution
}

const SENSOR_TYPE_UNITS: Record<string, string> = {
  sht31_temp: '°C',
  sht31_humidity: '%RH',
  temperature: '°C',
  humidity: '%RH',
  ph: 'pH',
  ec: 'µS/cm',
  pressure: 'hPa',
  co2: 'ppm',
  light: 'lux',
  soil_moisture: '%',
  flow: 'L/min',
}

/**
 * Sanitize a string for use in filenames:
 * - Replace German umlauts (ae/oe/ue/ss)
 * - Replace spaces with underscores
 * - Remove non-alphanumeric characters (except underscore/hyphen)
 * - Truncate to maxLen
 */
function sanitizeFilename(input: string, maxLen = 100): string {
  return input
    .replace(/ä/g, 'ae').replace(/Ä/g, 'Ae')
    .replace(/ö/g, 'oe').replace(/Ö/g, 'Oe')
    .replace(/ü/g, 'ue').replace(/Ü/g, 'Ue')
    .replace(/ß/g, 'ss')
    .replace(/\s+/g, '_')
    .replace(/[^a-zA-Z0-9_\-]/g, '')
    .slice(0, maxLen)
}

function formatDateForFilename(date: Date): string {
  return date.toISOString().slice(0, 10) // "2026-03-26"
}

function buildFilename(params: CsvExportParams): string {
  const zone = params.zoneName ? sanitizeFilename(params.zoneName) : 'export'
  const from = formatDateForFilename(params.startTime)
  const to = formatDateForFilename(params.endTime)
  const name = `${zone}_${params.sensorType}_${from}_${to}.csv`
  return sanitizeFilename(name, 100) + (name.length > 100 ? '' : '')
}

export function readingsToCsv(
  readings: SensorReading[],
  fallbackSensorType = '',
): string {
  const header = SENSOR_EXPORT_DEFAULT_COLUMNS.join(',')
  const rows: string[] = []
  for (const point of readings) {
    const processed = point.processed_value
    const unit = point.unit ?? SENSOR_TYPE_UNITS[fallbackSensorType] ?? ''
    const quality = point.quality ?? ''
    const sensorType = point.sensor_type ?? fallbackSensorType
    rows.push(`${point.timestamp},${processed ?? ''},${unit},${quality},${sensorType}`)
  }
  return [header, ...rows].join('\n')
}

function triggerDownload(csvContent: string, filename: string): void {
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

/**
 * Composable for CSV export of sensor data.
 *
 * Uses the existing GET /sensors/data API, converts JSON to CSV client-side,
 * and triggers a browser download.
 */
export function useExportCsv() {
  const isExporting = ref(false)
  const exportError = ref<string | null>(null)

  async function exportSensorCsv(params: CsvExportParams): Promise<void> {
    isExporting.value = true
    exportError.value = null

    try {
      const response = await sensorsApi.queryData({
        esp_id: params.espId,
        gpio: params.gpio,
        sensor_type: params.sensorType,
        start_time: params.startTime.toISOString(),
        end_time: params.endTime.toISOString(),
        resolution: params.resolution,
        limit: 1000,
      })

      if (!response.readings || response.readings.length === 0) {
        exportError.value = 'Keine Daten im gewählten Zeitraum vorhanden.'
        setTimeout(() => { exportError.value = null }, 5000)
        return
      }

      const csv = readingsToCsv(response.readings, params.sensorType)
      const filename = buildFilename(params)
      triggerDownload(csv, filename)
    } catch (e) {
      exportError.value = e instanceof Error ? e.message : 'Export fehlgeschlagen'
      setTimeout(() => { exportError.value = null }, 5000)
    } finally {
      isExporting.value = false
    }
  }

  return { isExporting, exportError, exportSensorCsv }
}
