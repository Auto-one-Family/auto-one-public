/**
 * Sensor Type Configuration
 *
 * Defines default values, units, and metadata for each sensor type.
 * CRITICAL: This fixes the bug where pH sensors showed "°C" instead of "pH".
 */

import type { SensorOperatingMode } from '@/types'

export interface SensorTypeConfig {
  /** Human-readable label: "Temperatur (DS18B20)" */
  label: string
  /** Correct unit: "°C", "pH", "% RH" */
  unit: string
  /** Minimum valid value */
  min: number
  /** Maximum valid value */
  max: number
  /** Decimal places for display */
  decimals: number
  /** Lucide icon name */
  icon: string
  /** Sensible default value for new sensors */
  defaultValue: number
  /** Tooltip description */
  description?: string
  /** Category for grouping in sidebar: 'temperature', 'water', 'soil', 'air', 'light', 'other' */
  category: SensorCategoryId
  // =========================================================================
  // OPERATING MODE RECOMMENDATIONS (Phase 2B)
  // =========================================================================
  /** Empfohlener Betriebsmodus für diesen Sensor-Typ */
  recommendedMode?: SensorOperatingMode
  /** Empfohlener Timeout in Sekunden (0 = kein Timeout) */
  recommendedTimeout?: number
  /** Ob dieser Sensor-Typ On-Demand-Messungen unterstuetzt */
  supportsOnDemand?: boolean
  /** Default read interval in seconds (for AddSensorModal type-aware defaults) */
  defaultIntervalSeconds?: number
  // =========================================================================
  // ONEWIRE SUPPORT (Phase 6 - DS18B20)
  // =========================================================================
  /** Requires OneWire address scanning before configuration */
  requiresAddressScanning?: boolean
  /** Multiple sensors can share the same GPIO pin (OneWire bus) */
  supportsMultipleOnSamePin?: boolean
  /** Recommended GPIO pins for this sensor type */
  recommendedGpios?: number[]
  // =========================================================================
  // DATASHEET METADATA (AUT-252) — read-only, displayed in SensorConfigPanel
  // =========================================================================
  /** Manufacturer name (e.g. "Sensirion") */
  manufacturer?: string
  /** Accuracy specification (e.g. "±0.3°C / ±2% RH") */
  accuracy?: string
  /** Whether this sensor type requires periodic calibration (false = factory-calibrated) */
  calibrationRequired?: boolean
  /** Free-text calibration hint shown in the sensor datasheet accordion (AUT-252) */
  calibrationNote?: string
  /** Datasheet URL (manufacturer documentation) */
  datasheetUrl?: string
  /** Recommended replacement / re-calibration interval in years */
  maintenanceYears?: number
}

/**
 * Sensor Category IDs for grouping
 */
export type SensorCategoryId = 'temperature' | 'water' | 'soil' | 'air' | 'light' | 'other'

/**
 * Category Configuration
 */
export interface SensorCategory {
  name: string
  icon: string
  order: number
}

/**
 * SENSOR_CATEGORIES
 *
 * Categories for grouping sensor types in the sidebar.
 * Used by SensorSidebar.vue for collapsible sections.
 */
export const SENSOR_CATEGORIES: Record<SensorCategoryId, SensorCategory> = {
  temperature: { name: 'Temperatur', icon: 'Thermometer', order: 1 },
  water: { name: 'Wasser', icon: 'Droplet', order: 2 },
  soil: { name: 'Boden', icon: 'Leaf', order: 3 },
  air: { name: 'Luft', icon: 'Wind', order: 4 },
  light: { name: 'Licht', icon: 'Sun', order: 5 },
  other: { name: 'Sonstige', icon: 'Settings', order: 6 }
}

/**
 * SENSOR_TYPE_CONFIG
 * 
 * Central configuration for all sensor types.
 * Used by:
 * - MockEspDetailView (sensor creation form)
 * - SensorValueCard (display)
 * - Validation logic
 */
export const SENSOR_TYPE_CONFIG: Record<string, SensorTypeConfig> = {
  'DS18B20': {
    label: 'Temperatur',
    unit: '°C',
    min: -55,
    max: 125,
    decimals: 1,
    icon: 'Thermometer',
    defaultValue: 20.0,
    description: 'Digitaler Temperatursensor, wasserdicht. Ideal für Flüssigkeiten und Umgebungstemperatur.',
    category: 'temperature',
    // Operating Mode (Phase 2B)
    recommendedMode: 'continuous',
    recommendedTimeout: 180,
    supportsOnDemand: false,
    defaultIntervalSeconds: 30,
    // OneWire (Phase 6)
    requiresAddressScanning: true,
    supportsMultipleOnSamePin: true,
    recommendedGpios: [4, 5, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33],
    // Datasheet (AUT-252)
    manufacturer: 'Dallas Semiconductor / Maxim',
    accuracy: '±0.5°C (-10…+85 °C)',
    calibrationRequired: false,
    calibrationNote: 'Kalibrierung im bekannten Referenzwasser (0 °C / 100 °C).',
    datasheetUrl: 'https://www.analog.com/media/en/technical-documentation/data-sheets/DS18B20.pdf',
    maintenanceYears: 10,
  },

  // Lowercase variant for consistency (ESP32 may send lowercase)
  'ds18b20': {
    label: 'Temperatur',
    unit: '°C',
    min: -55,
    max: 125,
    decimals: 1,
    icon: 'Thermometer',
    defaultValue: 20.0,
    description: 'Digitaler Temperatursensor, wasserdicht. Ideal für Flüssigkeiten und Umgebungstemperatur.',
    category: 'temperature',
    recommendedMode: 'continuous',
    recommendedTimeout: 180,
    supportsOnDemand: false,
    defaultIntervalSeconds: 30,
    requiresAddressScanning: true,
    supportsMultipleOnSamePin: true,
    recommendedGpios: [4, 5, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33],
    // Datasheet (AUT-252)
    manufacturer: 'Dallas Semiconductor / Maxim',
    accuracy: '±0.5°C (-10…+85 °C)',
    calibrationRequired: false,
    calibrationNote: 'Kalibrierung im bekannten Referenzwasser (0 °C / 100 °C).',
    datasheetUrl: 'https://www.analog.com/media/en/technical-documentation/data-sheets/DS18B20.pdf',
    maintenanceYears: 10,
  },

  'pH': {
    label: 'pH-Wert',
    unit: 'pH',  // NICHT °C!
    min: 0,
    max: 14,
    decimals: 2,
    icon: 'Droplet',
    defaultValue: 7.0,
    description: 'Säuregrad der Lösung. 0-6 = sauer, 7 = neutral, 8-14 = basisch.',
    category: 'water',
    // Operating Mode (Phase 2B)
    recommendedMode: 'on_demand',
    recommendedTimeout: 0,
    supportsOnDemand: true,
    // Datasheet (AUT-252)
    manufacturer: 'Generisch (analoge pH-Sonde)',
    accuracy: '±0.1 pH',
    calibrationRequired: true,
    calibrationNote: '2-Punkt-Kalibrierung mit pH 4.0 und pH 7.0 Pufferlösung alle 30 Tage.',
    datasheetUrl: 'https://wiki.dfrobot.com/Gravity__Analog_pH_Sensor_Meter_Kit_V2_SKU_SEN0161-V2',
    maintenanceYears: 1,
  },

  'EC': {
    label: 'Leitfähigkeit',
    unit: 'µS/cm',
    min: 0,
    max: 5000,
    decimals: 0,
    icon: 'Zap',
    defaultValue: 1200,
    description: 'Elektrische Leitfähigkeit. Zeigt Nährstoffgehalt der Lösung an.',
    category: 'water',
    // Operating Mode (Phase 2B)
    recommendedMode: 'on_demand',
    recommendedTimeout: 0,
    supportsOnDemand: true,
    // Datasheet (AUT-252)
    manufacturer: 'Generisch (EC-Sonde)',
    accuracy: '±2 % FS',
    calibrationRequired: true,
    calibrationNote: 'Kalibrierung mit 1413 µS/cm Standardlösung alle 30 Tage.',
    datasheetUrl: 'https://wiki.dfrobot.com/Gravity__Analog_Electrical_Conductivity_Sensor___Meter_V2__K%3D1__SKU_DFR0300',
    maintenanceYears: 2,
  },
  
  // SHT31 base/alias keys: Backward compat when API/DB sends "SHT31". Add-Dropdown shows only "sht31" (getSensorTypeOptions).
  'SHT31': {
    label: 'SHT31',
    unit: '°C',
    min: -40,
    max: 125,
    decimals: 1,
    icon: 'Thermometer',
    defaultValue: 22.0,
    description: 'Präziser Temperatur- und Feuchtesensor (I2C). Multi-Value-Sensor: Temperatur + Luftfeuchtigkeit.',
    category: 'temperature',
    // Operating Mode (Phase 2B)
    recommendedMode: 'continuous',
    recommendedTimeout: 180,
    supportsOnDemand: false,
    defaultIntervalSeconds: 30,
    // Datasheet (AUT-252)
    manufacturer: 'Sensirion',
    accuracy: '±0.3°C / ±2% RH',
    calibrationRequired: false,
    datasheetUrl: 'https://sensirion.com/products/catalog/SHT31-DIS-B',
    maintenanceYears: 5,
  },

  // Lowercase variants for consistency
  'sht31': {
    label: 'SHT31',
    unit: '°C',
    min: -40,
    max: 125,
    decimals: 1,
    icon: 'Thermometer',
    defaultValue: 22.0,
    description: 'Präziser Temperatur- und Feuchtesensor (I2C). Multi-Value-Sensor: Temperatur + Luftfeuchtigkeit.',
    category: 'temperature',
    recommendedMode: 'continuous',
    recommendedTimeout: 180,
    supportsOnDemand: false,
    defaultIntervalSeconds: 30,
    manufacturer: 'Sensirion',
    accuracy: '±0.3°C / ±2% RH',
    calibrationRequired: false,
    datasheetUrl: 'https://sensirion.com/products/catalog/SHT31-DIS-B',
    maintenanceYears: 5,
  },

  'sht31_temp': {
    label: 'Temperatur',
    unit: '°C',
    min: -40,
    max: 125,
    decimals: 1,
    icon: 'Thermometer',
    defaultValue: 22.0,
    description: 'SHT31 Temperaturwert. RAW-Konversion: -45 + (175 × raw / 65535)',
    category: 'temperature',
    recommendedMode: 'continuous',
    recommendedTimeout: 180,
    supportsOnDemand: false,
    defaultIntervalSeconds: 30,
    manufacturer: 'Sensirion',
    accuracy: '±0.3°C',
    calibrationRequired: false,
    datasheetUrl: 'https://sensirion.com/products/catalog/SHT31-DIS-B',
    maintenanceYears: 5,
  },

  'sht31_humidity': {
    label: 'Luftfeuchte',
    unit: '%RH',
    min: 0,
    max: 100,
    decimals: 1,
    icon: 'Droplets',
    defaultValue: 50.0,
    description: 'SHT31 Luftfeuchtigkeit. RAW-Konversion: 100 × raw / 65535',
    category: 'air',
    recommendedMode: 'continuous',
    recommendedTimeout: 180,
    supportsOnDemand: false,
    defaultIntervalSeconds: 30,
    manufacturer: 'Sensirion',
    accuracy: '±2% RH',
    calibrationRequired: false,
    datasheetUrl: 'https://sensirion.com/products/catalog/SHT31-DIS-B',
    maintenanceYears: 5,
  },

  // Alias for DB/API sending "SHT31_humidity"; value-type sht31_humidity is canonical.
  'SHT31_humidity': {
    label: 'Luftfeuchte',
    unit: '%RH',
    min: 0,
    max: 100,
    decimals: 1,
    icon: 'Droplets',
    defaultValue: 50.0,
    description: 'Relative Luftfeuchtigkeit. Optimal für Pflanzen: 40-70%.',
    category: 'air',
    // Operating Mode (Phase 2B)
    recommendedMode: 'continuous',
    recommendedTimeout: 180,
    supportsOnDemand: false,
    manufacturer: 'Sensirion',
    accuracy: '±2% RH',
    calibrationRequired: false,
    datasheetUrl: 'https://sensirion.com/products/catalog/SHT31-DIS-B',
    maintenanceYears: 5,
  },

  'BME280': {
    label: 'Temperatur',
    unit: '°C',
    min: -40,
    max: 85,
    decimals: 1,
    icon: 'Thermometer',
    defaultValue: 22.0,
    description: 'Temperatur-, Feuchte- und Drucksensor.',
    category: 'temperature',
    // Operating Mode (Phase 2B)
    recommendedMode: 'continuous',
    recommendedTimeout: 180,
    supportsOnDemand: false,
    defaultIntervalSeconds: 60,
    // Datasheet (AUT-252)
    manufacturer: 'Bosch Sensortec',
    accuracy: '±1°C / ±3% RH / ±1 hPa',
    calibrationRequired: false,
    datasheetUrl: 'https://www.bosch-sensortec.com/products/environmental-sensors/humidity-sensors-bme280/',
    maintenanceYears: 5,
  },

  'BME280_humidity': {
    label: 'Luftfeuchte',
    unit: '%RH',
    min: 0,
    max: 100,
    decimals: 1,
    icon: 'Droplets',
    defaultValue: 50.0,
    description: 'Relative Luftfeuchtigkeit.',
    category: 'air',
    // Operating Mode (Phase 2B)
    recommendedMode: 'continuous',
    recommendedTimeout: 180,
    supportsOnDemand: false,
    manufacturer: 'Bosch Sensortec',
    accuracy: '±3% RH',
    calibrationRequired: false,
    datasheetUrl: 'https://www.bosch-sensortec.com/products/environmental-sensors/humidity-sensors-bme280/',
    maintenanceYears: 5,
  },

  'BME280_pressure': {
    label: 'Luftdruck',
    unit: 'hPa',
    min: 300,
    max: 1100,
    decimals: 1,
    icon: 'Gauge',
    defaultValue: 1013.25,
    description: 'Atmosphärischer Luftdruck in Hektopascal.',
    category: 'air',
    // Operating Mode (Phase 2B)
    recommendedMode: 'continuous',
    recommendedTimeout: 300,
    supportsOnDemand: false,
    manufacturer: 'Bosch Sensortec',
    accuracy: '±1 hPa',
    calibrationRequired: false,
    datasheetUrl: 'https://www.bosch-sensortec.com/products/environmental-sensors/humidity-sensors-bme280/',
    maintenanceYears: 5,
  },

  // Lowercase variants (API/Firmware send lowercase sensor_type)
  // Phase C: Bosch BME280/BMP280 Datasheet — Operating range -40…+85 °C, 0…100 %RH, 300…1100 hPa
  'bmp280_temp': {
    label: 'BMP280 Temperatur',
    unit: '°C',
    min: -40,
    max: 85,
    decimals: 1,
    icon: 'Thermometer',
    defaultValue: 22.0,
    description: 'BMP280 Temperatur. Bosch Datasheet: -40…+85 °C.',
    category: 'temperature',
    recommendedMode: 'continuous',
    recommendedTimeout: 180,
    supportsOnDemand: false,
    defaultIntervalSeconds: 60,
    manufacturer: 'Bosch Sensortec',
    accuracy: '±1°C',
    calibrationRequired: false,
    datasheetUrl: 'https://www.bosch-sensortec.com/products/environmental-sensors/pressure-sensors/bmp280/',
    maintenanceYears: 5,
  },

  'bmp280_pressure': {
    label: 'BMP280 Druck',
    unit: 'hPa',
    min: 300,
    max: 1100,
    decimals: 1,
    icon: 'Gauge',
    defaultValue: 1013.25,
    description: 'BMP280 Luftdruck. Bosch Datasheet: 300…1100 hPa.',
    category: 'air',
    recommendedMode: 'continuous',
    recommendedTimeout: 300,
    supportsOnDemand: false,
    defaultIntervalSeconds: 60,
    manufacturer: 'Bosch Sensortec',
    accuracy: '±1 hPa',
    calibrationRequired: false,
    datasheetUrl: 'https://www.bosch-sensortec.com/products/environmental-sensors/pressure-sensors/bmp280/',
    maintenanceYears: 5,
  },

  'bme280_temp': {
    label: 'BME280 Temperatur',
    unit: '°C',
    min: -40,
    max: 85,
    decimals: 1,
    icon: 'Thermometer',
    defaultValue: 22.0,
    description: 'BME280 Temperatur. Bosch Datasheet: -40…+85 °C.',
    category: 'temperature',
    recommendedMode: 'continuous',
    recommendedTimeout: 180,
    supportsOnDemand: false,
    defaultIntervalSeconds: 60,
    manufacturer: 'Bosch Sensortec',
    accuracy: '±1°C',
    calibrationRequired: false,
    datasheetUrl: 'https://www.bosch-sensortec.com/products/environmental-sensors/humidity-sensors-bme280/',
    maintenanceYears: 5,
  },

  'bme280_humidity': {
    label: 'BME280 Feuchte',
    unit: '%RH',
    min: 0,
    max: 100,
    decimals: 1,
    icon: 'Droplets',
    defaultValue: 50.0,
    description: 'BME280 relative Luftfeuchtigkeit. Bosch Datasheet: 0…100 %RH.',
    category: 'air',
    recommendedMode: 'continuous',
    recommendedTimeout: 180,
    supportsOnDemand: false,
    defaultIntervalSeconds: 60,
    manufacturer: 'Bosch Sensortec',
    accuracy: '±3% RH',
    calibrationRequired: false,
    datasheetUrl: 'https://www.bosch-sensortec.com/products/environmental-sensors/humidity-sensors-bme280/',
    maintenanceYears: 5,
  },

  'bme280_pressure': {
    label: 'BME280 Druck',
    unit: 'hPa',
    min: 300,
    max: 1100,
    decimals: 1,
    icon: 'Gauge',
    defaultValue: 1013.25,
    description: 'BME280 Luftdruck. Bosch Datasheet: 300…1100 hPa.',
    category: 'air',
    recommendedMode: 'continuous',
    recommendedTimeout: 300,
    supportsOnDemand: false,
    defaultIntervalSeconds: 60,
    manufacturer: 'Bosch Sensortec',
    accuracy: '±1 hPa',
    calibrationRequired: false,
    datasheetUrl: 'https://www.bosch-sensortec.com/products/environmental-sensors/humidity-sensors-bme280/',
    maintenanceYears: 5,
  },

  'analog': {
    label: 'Analog-Eingang',
    unit: 'raw',
    min: 0,
    max: 4095,
    decimals: 0,
    icon: 'Activity',
    defaultValue: 2048,
    description: 'Rohwert des ADC (12-bit: 0-4095).',
    category: 'other',
    // Operating Mode (Phase 2B)
    recommendedMode: 'continuous',
    recommendedTimeout: 180,
    supportsOnDemand: true,
  },

  'digital': {
    label: 'Digital-Eingang',
    unit: '',
    min: 0,
    max: 1,
    decimals: 0,
    icon: 'ToggleLeft',
    defaultValue: 0,
    description: 'Digitaler Eingang (0 = LOW, 1 = HIGH).',
    category: 'other',
    // Operating Mode (Phase 2B)
    recommendedMode: 'continuous',
    recommendedTimeout: 60,
    supportsOnDemand: false,
  },

  'flow': {
    label: 'Durchfluss',
    unit: 'L/min',
    min: 0,
    max: 60,
    decimals: 2,
    icon: 'Waves',
    defaultValue: 0,
    description: 'Durchflussrate in Liter pro Minute (FS300A: 1–60 L/min).',
    category: 'water',
    // Operating Mode (Phase 2B)
    recommendedMode: 'continuous',
    recommendedTimeout: 60,
    supportsOnDemand: false,
    // Datasheet (AUT-252 / AUT-849): FS300A G3/4 = 330 Pulse/L, 1–60 L/min
    manufacturer: 'FS300A G3/4 (Hall-Effekt; Legacy YF-S201 = 450 Pulse/L)',
    accuracy: '±3 %',
    calibrationRequired: true,
    calibrationNote: 'Default 330 Impulse/Liter (FS300A). Messbereich 1–60 L/min — unter 1 L/min ggf. kein zuverlässiges Signal.',
    maintenanceYears: 3,
  },

  'liquid_level': {
    label: 'Füllstand (digital)',
    unit: '',
    min: 0,
    max: 1,
    decimals: 0,
    icon: 'ToggleLeft',
    defaultValue: 0,
    description: 'Kapazitiver Füllstandsschalter (PNP/NPN, berührungslos). Polarität im Config-Panel einstellbar.',
    category: 'water',
    // Operating Mode (Phase 2B)
    recommendedMode: 'continuous',
    recommendedTimeout: 60,
    supportsOnDemand: false,
    // Datasheet
    manufacturer: 'XKC Technology Co. Ltd. (z.B. XKC-Y25-NPN oder XKC-Y26S-PNP, berührungslos, IP67)',
    accuracy: 'Digital (0/1)',
    maintenanceYears: 5,
  },

  'level': {
    label: 'Füllstand',
    unit: '%',
    min: 0,
    max: 100,
    decimals: 1,
    icon: 'Layers',
    defaultValue: 50,
    description: 'Füllstand des Behälters in Prozent.',
    category: 'water',
    // Operating Mode (Phase 2B)
    recommendedMode: 'continuous',
    recommendedTimeout: 300,
    supportsOnDemand: false,
  },

  'light': {
    label: 'Licht',
    unit: 'lux',
    min: 0,
    max: 100000,
    decimals: 0,
    icon: 'Sun',
    defaultValue: 500,
    description: 'Beleuchtungsstärke in Lux.',
    category: 'light',
    // Operating Mode (Phase 2B)
    recommendedMode: 'continuous',
    recommendedTimeout: 180,
    supportsOnDemand: false,
    // Datasheet (AUT-252)
    manufacturer: 'Generisch (BH1750/VEML7700)',
    accuracy: '±20%',
    calibrationRequired: false,
    maintenanceYears: 5,
  },

  'co2': {
    label: 'CO2',
    unit: 'ppm',
    min: 400,
    max: 5000,
    decimals: 0,
    icon: 'Cloud',
    defaultValue: 400,
    description: 'CO2-Konzentration in ppm. Normal: 400-1000 ppm.',
    category: 'air',
    // Operating Mode (Phase 2B)
    recommendedMode: 'continuous',
    recommendedTimeout: 180,
    supportsOnDemand: false,
    // Datasheet (AUT-252)
    manufacturer: 'NDIR CO₂-Sensor (z.B. MH-Z19B)',
    accuracy: '±50 ppm + 5 % Messwert',
    calibrationRequired: true,
    calibrationNote: 'ABC-Autokalibrierung aktiv; manuelle Basiskalibrierung an Frischluft (~400 ppm).',
    datasheetUrl: 'https://www.winsen-sensor.com/d/files/MH-Z19B.pdf',
    maintenanceYears: 5,
  },

  'moisture': {
    label: 'Bodenfeuchte',
    unit: '%',
    min: 0,
    max: 100,
    decimals: 0,
    icon: 'Droplets',
    defaultValue: 50,
    description: 'Bodenfeuchtigkeit in Prozent. Kapazitiver oder resistiver Sensor.',
    category: 'soil',
    // Operating Mode (Phase 2B)
    recommendedMode: 'continuous',
    recommendedTimeout: 300,
    supportsOnDemand: false,
    defaultIntervalSeconds: 60,
    recommendedGpios: [32, 33, 34, 35, 36, 39],
    // Datasheet (AUT-252)
    manufacturer: 'Generisch (kapazitiv)',
    accuracy: '±3 % (kapazitiv) / ±10 % (resistiv)',
    calibrationRequired: true,
    calibrationNote: '2-Punkt-Kalibrierung: trocken (Luft) und nass (Wasser).',
    maintenanceYears: 2,
  },

  'soil_moisture': {
    label: 'Bodenfeuchte',
    unit: '%',
    min: 0,
    max: 100,
    decimals: 0,
    icon: 'Droplets',
    defaultValue: 50,
    description: 'Bodenfeuchtigkeit in Prozent. Kapazitiver oder resistiver Sensor.',
    category: 'soil',
    // Operating Mode (Phase 2B)
    recommendedMode: 'continuous',
    recommendedTimeout: 300,
    supportsOnDemand: false,
    defaultIntervalSeconds: 60,
    recommendedGpios: [32, 33, 34, 35, 36, 39],
    manufacturer: 'Generisch (kapazitiv)',
    accuracy: '±3 % (kapazitiv) / ±10 % (resistiv)',
    calibrationRequired: true,
    calibrationNote: '2-Punkt-Kalibrierung: trocken (Luft) und nass (Wasser).',
    maintenanceYears: 2,
  },

  // =========================================================================
  // COMPUTED / VIRTUAL SENSORS (PB-01)
  // =========================================================================

  'vpd': {
    label: 'VPD',
    unit: 'kPa',
    min: 0,
    max: 3,
    decimals: 2,
    icon: 'Droplets',
    defaultValue: 1.0,
    description: 'Vapor Pressure Deficit. Berechnet aus Temperatur und Luftfeuchte (SHT31).',
    category: 'air',
  },

  // =========================================================================
  // MULTISPEQ SNAPSHOT SENSORS (Wave 1)
  // Photosynthesis spot measurements; sensor_kind = 'snapshot'.
  // =========================================================================

  'phi2': {
    label: 'Phi2 (Φ)',
    unit: 'Φ',
    min: 0,
    max: 1,
    decimals: 3,
    icon: 'Leaf',
    defaultValue: 0.5,
    description: 'PSII operating efficiency (Φ). MultispeQ Snapshot-Messung.',
    category: 'light',
  },

  'fv_fm': {
    label: 'Fv/Fm',
    unit: 'Fv/Fm',
    min: 0,
    max: 1,
    decimals: 3,
    icon: 'Activity',
    defaultValue: 0.8,
    description: 'Maximum quantum yield of PSII. MultispeQ Snapshot-Messung.',
    category: 'light',
  },

  'npqt': {
    label: 'NPQt',
    unit: 'NPQt',
    min: 0,
    max: 10,
    decimals: 2,
    icon: 'Sun',
    defaultValue: 1.0,
    description: 'Non-photochemical quenching (transient). MultispeQ Snapshot-Messung.',
    category: 'light',
  },

  'lef': {
    label: 'LEF',
    unit: 'μmol e⁻/m²/s',
    min: 0,
    max: 500,
    decimals: 1,
    icon: 'Zap',
    defaultValue: 100,
    description: 'Linear Electron Flow. MultispeQ Snapshot-Messung.',
    category: 'light',
  },

  'par_internal': {
    label: 'PAR (intern)',
    unit: 'μmol/m²/s',
    min: 0,
    max: 2500,
    decimals: 0,
    icon: 'Sun',
    defaultValue: 500,
    description: 'Photosynthetically Active Radiation (interner Sensor). MultispeQ Snapshot-Messung.',
    category: 'light',
  },

  'ppfd': {
    label: 'PPFD',
    unit: 'μmol/m²/s',
    min: 0,
    max: 2500,
    decimals: 0,
    icon: 'Sun',
    defaultValue: 500,
    description: 'Photosynthetic Photon Flux Density. MultispeQ Snapshot-Messung.',
    category: 'light',
  },

  'chlorophyll_spad': {
    label: 'Chlorophyll SPAD',
    unit: 'SPAD',
    min: 0,
    max: 100,
    decimals: 1,
    icon: 'Leaf',
    defaultValue: 40,
    description: 'Chlorophyll-Index nach SPAD. MultispeQ Snapshot-Messung.',
    category: 'soil',
  },

  'leaf_temp': {
    label: 'Blatttemperatur',
    unit: '°C',
    min: -10,
    max: 60,
    decimals: 1,
    icon: 'Thermometer',
    defaultValue: 22,
    description: 'Blatttemperatur (IR-Thermometer). MultispeQ Snapshot-Messung.',
    category: 'temperature',
  },

  'anthocyanin_index': {
    label: 'Anthocyanin ARI',
    unit: 'ARI',
    min: 0,
    max: 5,
    decimals: 2,
    icon: 'Droplet',
    defaultValue: 1.0,
    description: 'Anthocyanin Reflectance Index. MultispeQ Snapshot-Messung.',
    category: 'other',
  },
}

// =============================================================================
// VIRTUAL SENSOR METADATA (V19-F03)
// =============================================================================

/** Source information for server-computed (virtual) sensors */
export const VIRTUAL_SENSOR_META: Record<string, { sources: string[]; formula: string; description?: string }> = {
  vpd: {
    sources: ['Temperatur (SHT31)', 'Luftfeuchtigkeit (SHT31)'],
    formula: 'Magnus-Tetens (Air-VPD)',
    description: 'VPD (Dampfdruckdefizit) zeigt, wie viel Feuchtigkeit die Luft noch aufnehmen kann. Werte zwischen 0,8 und 1,2 kPa gelten als optimal für die meisten Pflanzen. Berechnet aus Temperatur und Luftfeuchte.',
  },
}

/**
 * Air-VPD (kPa) from dry-bulb temperature (°C) and relative humidity (%RH).
 * Tetens-style saturation vapor pressure (kPa), aligned with {@link VIRTUAL_SENSOR_META} vpd.
 */
export function computeAirVpdKpaFromTempRh(tempC: number, rhPercent: number): number | null {
  if (!Number.isFinite(tempC) || !Number.isFinite(rhPercent)) return null
  if (rhPercent < 0 || rhPercent > 100) return null
  if (tempC < -40 || tempC > 60) return null
  const es = 0.6108 * Math.exp((17.27 * tempC) / (tempC + 237.3))
  const ea = (rhPercent / 100) * es
  const vpd = es - ea
  if (!Number.isFinite(vpd) || vpd < 0) return null
  return vpd
}

/**
 * Zonal VPD from Monitor L1 Ø-KPI buckets (temperature + humidity category averages).
 */
export function computeZoneVpdKpaFromKpiSensorTypes(
  sensorTypes: Array<{ type: string; avg: number; count: number }>,
): number | null {
  const t = sensorTypes.find(s => s.type === 'temperature')
  const rh = sensorTypes.find(s => s.type === 'humidity')
  if (!t || !rh || t.count === 0 || rh.count === 0) return null
  return computeAirVpdKpaFromTempRh(t.avg, rh.avg)
}

/**
 * Case-insensitive lookup map built once from SENSOR_TYPE_CONFIG.
 * Handles runtime sensor_type values like 'ph', 'ec', 'ds18b20'
 * that don't match the mixed-case config keys 'pH', 'EC', 'DS18B20'.
 */
const _sensorConfigByLowerKey: Record<string, SensorTypeConfig> = Object.fromEntries(
  Object.entries(SENSOR_TYPE_CONFIG).map(([k, v]) => [k.toLowerCase(), v]),
)

/**
 * Retrieve sensor config with case-insensitive matching.
 * Always prefer this over direct SENSOR_TYPE_CONFIG[sensorType] access.
 */
export function getSensorConfig(sensorType: string): SensorTypeConfig | undefined {
  return SENSOR_TYPE_CONFIG[sensorType] ?? _sensorConfigByLowerKey[sensorType.toLowerCase()] ?? undefined
}

/**
 * Get the correct unit for a sensor type
 * @param sensorType - The sensor type key (e.g., 'pH', 'DS18B20')
 * @returns The unit string or 'raw' if unknown
 */
export function getSensorUnit(sensorType: string): string {
  return getSensorConfig(sensorType)?.unit ?? 'raw'
}

/**
 * Get the default value for a sensor type
 * @param sensorType - The sensor type key
 * @returns The default value or 0 if unknown
 */
export function getSensorDefault(sensorType: string): number {
  return SENSOR_TYPE_CONFIG[sensorType]?.defaultValue ?? 0
}


/**
 * Get human-readable label for a sensor type
 * @param sensorType - The sensor type key
 * @returns The label or the original type if unknown
 */
export function getSensorLabel(sensorType: string): string {
  return getSensorConfig(sensorType)?.label ?? sensorType
}

/**
 * Validate if a value is within the valid range for a sensor type
 * @param sensorType - The sensor type key
 * @param value - The value to validate
 * @returns true if valid, false otherwise
 */
export function isValidSensorValue(sensorType: string, value: number): boolean {
  const config = SENSOR_TYPE_CONFIG[sensorType]
  if (!config) return true // Unknown types are always valid
  return value >= config.min && value <= config.max
}

/**
 * Get all available sensor types as options for select elements (Add-Sensor dropdown).
 * Returns a DEVICE list: one option per multi-value device (canonical key, e.g. "sht31"),
 * plus all single-value sensor types. Value-types (sht31_temp, sht31_humidity) and
 * duplicate base keys (SHT31, SHT31_humidity) are excluded so the dropdown does not show 5 SHT31 variants.
 * Duplicates like DS18B20/ds18b20 are deduplicated (lowercase preferred as canonical).
 * @returns Array of { value, label } objects
 */
export function getSensorTypeOptions(): Array<{ value: string; label: string }> {
  const valueTypeSet = new Set(
    Object.values(MULTI_VALUE_DEVICES).flatMap((d) => d.sensorTypes)
  )
  const deviceKeySet = new Set(
    Object.keys(MULTI_VALUE_DEVICES).map((k) => k.toLowerCase())
  )

  const deviceOptions = Object.entries(MULTI_VALUE_DEVICES).map(([deviceType, cfg]) => ({
    value: deviceType,
    label: cfg.label ?? getMultiValueDeviceFallbackLabel(deviceType)
  }))

  const singleValueEntries = Object.entries(SENSOR_TYPE_CONFIG)
    .filter(([key]) => {
      if (valueTypeSet.has(key)) return false
      if (valueTypeSet.has(key.toLowerCase())) return false // e.g. SHT31_humidity → sht31_humidity
      if (deviceKeySet.has(key.toLowerCase())) return false // SHT31, sht31 → already in deviceOptions
      if (getDeviceTypeFromSensorType(key) !== null) return false
      return true
    })
    .sort((a, b) => {
      const aLower = a[0].toLowerCase()
      const bLower = b[0].toLowerCase()
      if (aLower !== bLower) return aLower.localeCompare(bLower)
      // Same normalized key: prefer lowercase variant (e.g. ds18b20 before DS18B20)
      return (a[0] === aLower ? 0 : 1) - (b[0] === bLower ? 0 : 1)
    })

  const addedLowercase = new Set<string>()
  const singleValueOptions = singleValueEntries
    .filter(([key]) => {
      const lower = key.toLowerCase()
      if (addedLowercase.has(lower)) return false
      addedLowercase.add(lower)
      return true
    })
    .map(([key, config]) => ({ value: key, label: config.label }))

  return [...deviceOptions, ...singleValueOptions]
}

/** Fallback label for multi-value devices when label is missing */
function getMultiValueDeviceFallbackLabel(deviceType: string): string {
  const fallbacks: Record<string, string> = {
    sht31: 'SHT31 (Temp + Humidity)',
    bmp280: 'BMP280 (Druck + Temp)',
    bme280: 'BME280 (Druck + Temp + Feuchte)'
  }
  return fallbacks[deviceType.toLowerCase()] ?? deviceType
}

/**
 * Format a sensor value with its unit
 * @param value - The numeric value
 * @param sensorType - The sensor type key
 * @returns Formatted string like "23.5 °C"
 */
export function formatSensorValueWithUnit(value: number | null, sensorType: string): string {
  if (value === null || value === undefined) return '-'

  const config = SENSOR_TYPE_CONFIG[sensorType]
  if (!config) return `${value}`

  const formatted = new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: config.decimals,
    maximumFractionDigits: config.decimals,
  }).format(value)
  return `${formatted} ${config.unit}`
}

/**
 * Get the default read interval for a sensor type
 * @returns Interval in seconds, or 30 as fallback
 */
export function getDefaultInterval(sensorType: string): number {
  return SENSOR_TYPE_CONFIG[sensorType]?.defaultIntervalSeconds ?? 30
}

/**
 * Build a human-readable summary for sensor-type-aware defaults.
 *
 * @example
 * getSensorTypeAwareSummary('SHT31')
 * // "SHT31 auf I2C 0x44, misst Temperatur + Luftfeuchtigkeit alle 30s"
 */
export function getSensorTypeAwareSummary(sensorType: string): string | null {
  const config = SENSOR_TYPE_CONFIG[sensorType]
  if (!config) return null

  const iface = inferInterfaceType(sensorType)
  const interval = config.defaultIntervalSeconds ?? 30

  // Check if multi-value device
  const deviceType = getDeviceTypeFromSensorType(sensorType)
  const mvDevice = deviceType ? MULTI_VALUE_DEVICES[deviceType] : null

  const parts: string[] = [config.label || sensorType]

  if (iface === 'I2C' && mvDevice?.i2cAddress) {
    parts.push(`auf I2C ${mvDevice.i2cAddress}`)
  } else if (iface === 'ONEWIRE') {
    parts.push('auf OneWire-Bus')
  } else if (iface === 'UART') {
    parts.push('auf UART (RX-Pin)')
  }

  if (mvDevice) {
    const valueNames = mvDevice.values.map(v => v.label)
    parts.push(`misst ${valueNames.join(' + ')}`)
  } else {
    parts.push(`misst ${config.unit}`)
  }

  parts.push(`alle ${interval}s`)

  return parts.join(', ')
}

// ════════════════════════════════════════════════════════════════════════════
// MULTI-VALUE DEVICE REGISTRY (Phase 6)
// ════════════════════════════════════════════════════════════════════════════

/**
 * Configuration for a single value within a multi-value device
 */
export interface MultiValueConfig {
  /** Value key (e.g., "temp", "humidity") */
  key: string
  /** Full sensor_type string (e.g., "sht31_temp") */
  sensorType: string
  /** Display label */
  label: string
  /** Unit of measurement */
  unit: string
  /** Display order (lower = first) */
  order: number
  /** Icon for this specific value (optional) */
  icon?: string
}

/**
 * Configuration for a multi-value device
 */
export interface MultiValueDeviceConfig {
  /** Device type identifier (e.g., "sht31") */
  deviceType: string
  /** Human-readable device name */
  label: string
  /** All sensor_types this device produces */
  sensorTypes: string[]
  /** Detailed config for each value */
  values: MultiValueConfig[]
  /** Primary icon for the device */
  icon: string
  /** Interface type */
  interface: 'i2c' | 'onewire' | 'analog' | 'digital'
  /** Typical I2C address (if applicable) */
  i2cAddress?: string
}

/**
 * Registry of all known multi-value devices
 *
 * ⚠️ KRITISCH: sensor_type Strings müssen EXAKT mit ESP32-Code übereinstimmen!
 * Quelle: El Trabajante/src/models/sensor_registry.cpp (lines 88-140)
 */
export const MULTI_VALUE_DEVICES: Record<string, MultiValueDeviceConfig> = {
  sht31: {
    deviceType: 'sht31',
    label: 'SHT31 (Temp + Humidity)',
    sensorTypes: ['sht31_temp', 'sht31_humidity'],
    values: [
      { key: 'temp', sensorType: 'sht31_temp', label: 'Temperatur', unit: '°C', order: 1, icon: 'Thermometer' },
      { key: 'humidity', sensorType: 'sht31_humidity', label: 'Luftfeuchte', unit: '%RH', order: 2, icon: 'Droplets' }
    ],
    icon: 'Thermometer',
    interface: 'i2c',
    i2cAddress: '0x44'
  },

  bmp280: {
    deviceType: 'bmp280',
    label: 'BMP280 (Pressure + Temp)',
    sensorTypes: ['bmp280_pressure', 'bmp280_temp'],
    values: [
      { key: 'pressure', sensorType: 'bmp280_pressure', label: 'Luftdruck', unit: 'hPa', order: 1, icon: 'Gauge' },
      { key: 'temp', sensorType: 'bmp280_temp', label: 'Temperatur', unit: '°C', order: 2, icon: 'Thermometer' }
    ],
    icon: 'Gauge',
    interface: 'i2c',
    i2cAddress: '0x76'
  }
}

// ════════════════════════════════════════════════════════════════════════════
// MULTI-VALUE HELPER FUNCTIONS
// ════════════════════════════════════════════════════════════════════════════

/**
 * Maps base sensor types (from DB/Server) to their device type
 *
 * Problem: DB speichert "SHT31", aber Registry erwartet "sht31_temp"/"sht31_humidity"
 * Lösung: Diese Map erlaubt das Erkennen von Base-Types
 */
const BASE_TYPE_TO_DEVICE: Record<string, string> = {
  // SHT31 variants
  'sht31': 'sht31',
  'SHT31': 'sht31',
  'sht31_temp': 'sht31',
  'sht31_humidity': 'sht31',
  // BMP280 variants
  'bmp280': 'bmp280',
  'BMP280': 'bmp280',
  'bmp280_temp': 'bmp280',
  'bmp280_pressure': 'bmp280',
  // BME280 (same as BMP280 with humidity)
  'bme280': 'bme280',
  'BME280': 'bme280',
  'bme280_temp': 'bme280',
  'bme280_humidity': 'bme280',
  'bme280_pressure': 'bme280',
}

/**
 * Extended MULTI_VALUE_DEVICES with BME280 support
 */
const BME280_CONFIG: MultiValueDeviceConfig = {
  deviceType: 'bme280',
  label: 'BME280 (Temp + Humidity + Pressure)',
  sensorTypes: ['bme280_temp', 'bme280_humidity', 'bme280_pressure', 'BME280'],
  values: [
    { key: 'temp', sensorType: 'bme280_temp', label: 'Temperatur', unit: '°C', order: 1, icon: 'Thermometer' },
    { key: 'humidity', sensorType: 'bme280_humidity', label: 'Luftfeuchte', unit: '%RH', order: 2, icon: 'Droplets' },
    { key: 'pressure', sensorType: 'bme280_pressure', label: 'Druck', unit: 'hPa', order: 3, icon: 'Gauge' }
  ],
  icon: 'Thermometer',
  interface: 'i2c',
  i2cAddress: '0x76'
}

// Add BME280 to registry
MULTI_VALUE_DEVICES['bme280'] = BME280_CONFIG

/**
 * Check if a sensor_type belongs to a multi-value device
 * Now also checks base types like "SHT31" or "BME280"
 */
export function isMultiValueSensorType(sensorType: string): boolean {
  // Direct check in base type map
  if (BASE_TYPE_TO_DEVICE[sensorType]) return true

  // Check in device configs
  return Object.values(MULTI_VALUE_DEVICES).some(
    device => device.sensorTypes.includes(sensorType)
  )
}

/**
 * Get device type from sensor_type
 *
 * Extended to recognize base types like "SHT31", "BME280"
 *
 * @example
 * getDeviceTypeFromSensorType('sht31_temp') // 'sht31'
 * getDeviceTypeFromSensorType('SHT31') // 'sht31' (NEW!)
 * getDeviceTypeFromSensorType('BME280') // 'bme280' (NEW!)
 * getDeviceTypeFromSensorType('ds18b20') // null (single-value)
 */
export function getDeviceTypeFromSensorType(sensorType: string): string | null {
  // First check base type map (handles uppercase variants)
  if (BASE_TYPE_TO_DEVICE[sensorType]) {
    return BASE_TYPE_TO_DEVICE[sensorType]
  }

  // Then check device configs
  for (const [deviceType, config] of Object.entries(MULTI_VALUE_DEVICES)) {
    if (config.sensorTypes.includes(sensorType)) {
      return deviceType
    }
  }
  return null
}

/**
 * Get all sensor_types for a device type
 *
 * @example
 * getSensorTypesForDevice('sht31') // ['sht31_temp', 'sht31_humidity']
 */
export function getSensorTypesForDevice(deviceType: string): string[] {
  return MULTI_VALUE_DEVICES[deviceType]?.sensorTypes ?? []
}

/**
 * Get device config by device type
 */
export function getMultiValueDeviceConfig(deviceType: string): MultiValueDeviceConfig | null {
  return MULTI_VALUE_DEVICES[deviceType] ?? null
}

/**
 * Get device config by any of its sensor_types
 */
export function getMultiValueDeviceConfigBySensorType(sensorType: string): MultiValueDeviceConfig | null {
  const deviceType = getDeviceTypeFromSensorType(sensorType)
  return deviceType ? MULTI_VALUE_DEVICES[deviceType] : null
}

/**
 * Check if sensor_type is a multi-value base type (e.g. "SHT31", "sht31")
 * that should be replaced with an explicit sub-type (sht31_temp, sht31_humidity).
 *
 * @example
 * isMultiValueBaseType('SHT31') // true
 * isMultiValueBaseType('sht31_temp') // false
 */
export function isMultiValueBaseType(sensorType: string): boolean {
  const lower = sensorType.toLowerCase()
  return lower in MULTI_VALUE_DEVICES
}

/**
 * Get value config for a specific sensor_type within a multi-value device
 */
export function getValueConfigForSensorType(sensorType: string): MultiValueConfig | null {
  const deviceConfig = getMultiValueDeviceConfigBySensorType(sensorType)
  if (!deviceConfig) return null

  return deviceConfig.values.find(v => v.sensorType === sensorType) ?? null
}

// =============================================================================
// DISPLAY NAME (Multi-Value Disambiguation)
// =============================================================================

/**
 * Get display name for a sensor, differentiating multi-value siblings.
 *
 * Multi-value sensors (SHT31, BMP280, BME280) create multiple sensor_configs
 * with the same sensor_name (e.g. both "Temp&Hum"). This function appends
 * the sub-type label to disambiguate.
 *
 * Fallback chain:
 * 1. name + sub-type suffix (for multi-value sub-types): "Temp&Hum (Temperatur)"
 * 2. name as-is (for single-value sensors): "Substrat"
 * 3. SENSOR_TYPE_CONFIG label (when no name set): "Temperatur"
 *
 * @example
 * getSensorDisplayName({ sensor_type: 'sht31_temp', name: 'Temp&Hum' })
 * // => "Temp&Hum (Temperatur)"
 *
 * getSensorDisplayName({ sensor_type: 'sht31_humidity', name: 'Temp&Hum' })
 * // => "Temp&Hum (Luftfeuchte)"
 *
 * getSensorDisplayName({ sensor_type: 'ds18b20', name: 'Substrat' })
 * // => "Substrat"
 *
 * getSensorDisplayName({ sensor_type: 'sht31_temp', name: null })
 * // => "Temperatur"
 */
export function getSensorDisplayName(sensor: { sensor_type: string; name?: string | null }): string {
  const typeConfig = SENSOR_TYPE_CONFIG[sensor.sensor_type]
  const typeLabel = typeConfig?.label ?? sensor.sensor_type

  // No name set → type label
  if (!sensor.name) {
    return typeLabel
  }

  // Multi-value sub-type → append sub-type label for disambiguation
  const valueConfig = getValueConfigForSensorType(sensor.sensor_type)
  if (valueConfig) {
    return `${sensor.name} (${valueConfig.label})`
  }

  // Single-value sensor → name as-is
  return sensor.name
}

// =============================================================================
// INTERFACE TYPE INFERENCE
// =============================================================================

export type InterfaceType = 'I2C' | 'ONEWIRE' | 'ANALOG' | 'DIGITAL' | 'UART'

/**
 * Infer interface type from sensor_type.
 *
 * Matches server-side logic in sensors.py:_infer_interface_type
 *
 * Rules:
 * - sht31*, bmp280*, bme280*, bh1750*, veml7700* → I2C
 * - ds18b20* → ONEWIRE
 * - co2*, mhz19* → UART (MH-Z19/SEN0220)
 * - Everything else → ANALOG (default)
 *
 * @example
 * inferInterfaceType('ds18b20') // 'ONEWIRE'
 * inferInterfaceType('sht31_temp') // 'I2C'
 * inferInterfaceType('ph') // 'ANALOG'
 */
export function inferInterfaceType(sensorType: string): InterfaceType {
  const lower = sensorType.toLowerCase()

  // I2C sensors
  if (
    lower.includes('sht31') ||
    lower.includes('bmp280') ||
    lower.includes('bme280') ||
    lower.includes('bh1750') ||
    lower.includes('veml7700')
  ) {
    return 'I2C'
  }

  // OneWire sensors
  if (lower.includes('ds18b20')) {
    return 'ONEWIRE'
  }

  // UART CO2 (MH-Z19 / SEN0220)
  if (lower.includes('co2') || lower.includes('mhz19')) {
    return 'UART'
  }

  // Digital level switch (XKC-Y25-NPN and similar NPN/PNP open-collector)
  if (lower.includes('liquid_level')) {
    return 'DIGITAL'
  }

  // Digital pulse-counting flow sensor (FS300A / YF-S201)
  if (lower.includes('flow') || lower.includes('yfs201')) {
    return 'DIGITAL'
  }

  // Default to ANALOG (pH, EC, moisture, ...).
  // NOTE: adc_source (internal vs. ads1115) is orthogonal to interface_type.
  // pH/EC stay ANALOG even when read via an external ADS1115 I2C ADC — the
  // firmware keeps them on the analog-probe path and only swaps the RAW source.
  return 'ANALOG'
}

/**
 * Get default I2C address for a sensor type (if applicable).
 *
 * @example
 * getDefaultI2CAddress('sht31_temp') // 0x44 (68 decimal)
 * getDefaultI2CAddress('ds18b20') // null (not I2C)
 */
export function getDefaultI2CAddress(sensorType: string): number | null {
  const deviceConfig = getMultiValueDeviceConfigBySensorType(sensorType)

  if (deviceConfig?.interface === 'i2c' && deviceConfig.i2cAddress) {
    // Convert hex string "0x44" to number
    return parseInt(deviceConfig.i2cAddress, 16)
  }

  return null
}

/**
 * Known I2C addresses for sensor types.
 * Used by AddSensorModal to show an address dropdown for I2C sensors.
 */
const I2C_ADDRESS_REGISTRY: Record<string, Array<{ value: number; hex: string; label: string }>> = {
  sht31: [
    { value: 0x44, hex: '0x44', label: '0x44 (Standard)' },
    { value: 0x45, hex: '0x45', label: '0x45 (ADDR HIGH)' },
  ],
  bmp280: [
    { value: 0x76, hex: '0x76', label: '0x76 (SDO LOW)' },
    { value: 0x77, hex: '0x77', label: '0x77 (SDO HIGH)' },
  ],
  bme280: [
    { value: 0x76, hex: '0x76', label: '0x76 (SDO LOW)' },
    { value: 0x77, hex: '0x77', label: '0x77 (SDO HIGH)' },
  ],
  bh1750: [
    { value: 0x23, hex: '0x23', label: '0x23 (ADDR LOW)' },
    { value: 0x5C, hex: '0x5C', label: '0x5C (ADDR HIGH)' },
  ],
  veml7700: [
    { value: 0x10, hex: '0x10', label: '0x10 (Standard)' },
  ],
}

/**
 * Get I2C address options for a sensor type.
 *
 * @example
 * getI2CAddressOptions('sht31_temp') // [{value: 0x44, hex: '0x44', label: '0x44 (Standard)'}, ...]
 * getI2CAddressOptions('ds18b20') // [] (not I2C)
 */
export function getI2CAddressOptions(sensorType: string): Array<{ value: number; hex: string; label: string }> {
  const lower = sensorType.toLowerCase()

  for (const [key, options] of Object.entries(I2C_ADDRESS_REGISTRY)) {
    if (lower.includes(key)) {
      return options
    }
  }

  return []
}

// ════════════════════════════════════════════════════════════════════════════
// SENSOR GROUPING & ZONE AGGREGATION (Dashboard Helpers)
// ════════════════════════════════════════════════════════════════════════════

/**
 * Minimal sensor shape from props.device.sensors (unknown[])
 */
export interface RawSensor {
  sensor_type: string
  raw_value: number | null
  name: string
  unit?: string
  gpio?: number
  quality?: string
}

/**
 * Grouped sensor output for DeviceMiniCard display
 */
export interface GroupedSensor {
  baseType: string
  label: string
  values: {
    type: string
    label: string
    value: number | null
    unit: string
    icon: string
    quality: 'normal' | 'warning' | 'stale' | 'unknown'
  }[]
}

/**
 * Determine value quality for display coloring.
 *
 * - normal: within plausible range
 * - warning: outside plausible range
 * - stale: value is 0 for a sensor that should never be 0 (e.g., humidity)
 * - unknown: null/missing value
 */
function assessValueQuality(
  value: number | null,
  sensorType: string,
): 'normal' | 'warning' | 'stale' | 'unknown' {
  if (value === null || value === undefined) return 'unknown'

  const config = SENSOR_TYPE_CONFIG[sensorType]
  if (!config) return 'normal'

  // Value outside plausible range
  if (value < config.min || value > config.max) return 'warning'

  // Value is 0 for sensors that should never be 0
  if (value === 0) {
    const lower = sensorType.toLowerCase()
    if (lower.includes('humid') || lower.includes('pressure')) return 'stale'
  }

  return 'normal'
}

/**
 * Format a raw sensor_type as a readable display name.
 * "sht31_temp" → "Sht31 Temp", "ds18b20" → "Ds18b20"
 */
export function formatSensorType(sensorType: string): string {
  return sensorType
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
}

/**
 * Groups sensors of a device by their base type.
 *
 * Multi-value sensors (SHT31, BME280) are resolved into individual value rows.
 * Single-value sensors (DS18B20, pH) become a group with one value.
 *
 * @example
 * Input:  [{sensor_type: 'sht31_temp', raw_value: 22}, {sensor_type: 'sht31_humidity', raw_value: 45}]
 * Output: [{baseType: 'sht31', label: 'SHT31', values: [{type: 'sht31_temp', label: 'Temperatur', ...}, ...]}]
 */
export function groupSensorsByBaseType(sensors: RawSensor[]): GroupedSensor[] {
  if (!sensors || sensors.length === 0) return []

  const groups = new Map<string, GroupedSensor>()

  for (const sensor of sensors) {
    const sType = sensor.sensor_type || ''
    if (!sType) continue

    // Check if this sensor belongs to a multi-value device
    const deviceType = getDeviceTypeFromSensorType(sType)
    const mvDevice = deviceType ? MULTI_VALUE_DEVICES[deviceType] : null

    if (mvDevice) {
      // Multi-value: group under device type
      if (!groups.has(deviceType!)) {
        groups.set(deviceType!, {
          baseType: deviceType!,
          label: mvDevice.label.split(' (')[0], // "SHT31" from "SHT31 (Temp + Humidity)"
          values: [],
        })
      }
      const group = groups.get(deviceType!)!

      // Find the specific value config for this sensor_type
      const valueConfig = mvDevice.values.find(v => v.sensorType === sType)

      // Check if this is a base type (e.g., "SHT31" instead of "sht31_temp")
      // If so, we need to expand it to all value types
      const isBaseType = sType.toLowerCase() === deviceType
        || sType.toUpperCase() === deviceType?.toUpperCase()
      const isAlreadyValueType = mvDevice.values.some(v => v.sensorType === sType)

      if (isBaseType && !isAlreadyValueType) {
        // This is a base type like "SHT31" — expand to all value types
        // but only if no individual value types exist yet
        const hasIndividualValues = sensors.some(s =>
          s.sensor_type !== sType && mvDevice.values.some(v => v.sensorType === s.sensor_type)
        )
        if (!hasIndividualValues) {
          // Show the base type as a single entry with its primary value config
          const primaryConfig = mvDevice.values[0]
          group.values.push({
            type: sType,
            label: (sensor.name && sensor.name.trim().length > 0) ? sensor.name : (primaryConfig?.label || getSensorLabel(sType)),
            value: sensor.raw_value,
            unit: primaryConfig?.unit || sensor.unit || getSensorUnit(sType),
            icon: primaryConfig?.icon || SENSOR_TYPE_CONFIG[sType]?.icon || 'Activity',
            quality: assessValueQuality(sensor.raw_value, sType),
          })
        }
        // If individual values exist, skip the base type entry
      } else if (valueConfig) {
        // Already-resolved value type — avoid duplicates
        const exists = group.values.some(v => v.type === sType)
        if (!exists) {
          group.values.push({
            type: sType,
            label: (sensor.name && sensor.name.trim().length > 0) ? sensor.name : valueConfig.label,
            value: sensor.raw_value,
            unit: valueConfig.unit,
            icon: valueConfig.icon || mvDevice.icon,
            quality: assessValueQuality(sensor.raw_value, sType),
          })
        }
      } else {
        // Unknown value type within the device — fallback
        const config = SENSOR_TYPE_CONFIG[sType]
        group.values.push({
          type: sType,
          label: (sensor.name && sensor.name.trim().length > 0) ? sensor.name : (config?.label || sType),
          value: sensor.raw_value,
          unit: config?.unit || sensor.unit || '',
          icon: config?.icon || 'Activity',
          quality: assessValueQuality(sensor.raw_value, sType),
        })
      }
    } else {
      // Single-value sensor (DS18B20, pH, etc.)
      // Use unique key per sensor to avoid collisions (e.g., 2x DS18B20)
      const uniqueKey = `${sType}_${sensor.gpio ?? sensors.indexOf(sensor)}`
      const config = SENSOR_TYPE_CONFIG[sType]
      const sensorName = (sensor.name && sensor.name.trim().length > 0) ? sensor.name : (config?.label || formatSensorType(sType))
      groups.set(uniqueKey, {
        baseType: sType,
        label: config?.label || formatSensorType(sType),
        values: [{
          type: sType,
          label: sensorName,
          value: sensor.raw_value,
          unit: config?.unit || sensor.unit || '',
          icon: config?.icon || 'Activity',
          quality: assessValueQuality(sensor.raw_value, sType),
        }],
      })
    }
  }

  // Sort multi-value groups by order
  for (const group of groups.values()) {
    if (group.values.length > 1) {
      const deviceType = getDeviceTypeFromSensorType(group.values[0]?.type || '')
      const mvDevice = deviceType ? MULTI_VALUE_DEVICES[deviceType] : null
      if (mvDevice) {
        group.values.sort((a, b) => {
          const orderA = mvDevice.values.find(v => v.sensorType === a.type)?.order ?? 99
          const orderB = mvDevice.values.find(v => v.sensorType === b.type)?.order ?? 99
          return orderA - orderB
        })
      }
    }
  }

  return Array.from(groups.values())
}

/**
 * Abstract sensor category for zone aggregation (device-independent)
 */
export type AggCategory =
  | 'temperature'
  | 'humidity'
  | 'pressure'
  | 'light'
  | 'co2'
  | 'moisture'
  | 'ph'
  | 'ec'
  | 'flow'
  | 'other'

/**
 * Map a sensor_type to an abstract category for aggregation
 */
export function getSensorAggCategory(sensorType: string): AggCategory {
  const lower = sensorType.toLowerCase()
  if (lower.includes('temp') || lower === 'ds18b20') return 'temperature'
  if (lower.includes('humid')) return 'humidity'
  if (lower.includes('pressure')) return 'pressure'
  if (lower.includes('light') || lower.includes('lux')) return 'light'
  if (lower.includes('co2')) return 'co2'
  if (lower.includes('moisture') || lower.includes('soil')) return 'moisture'
  if (lower === 'ph') return 'ph'
  if (lower === 'ec') return 'ec'
  if (lower.includes('flow')) return 'flow'
  if (lower === 'vpd') return 'other' // VPD (kPa) must not mix with humidity (%)

  // Fallback: multi-value base types (e.g. "sht31", "bme280") that don't match
  // string-based checks above. Use SENSOR_TYPE_CONFIG category to determine mapping.
  const config = SENSOR_TYPE_CONFIG[sensorType] || SENSOR_TYPE_CONFIG[lower]
  if (config) {
    const categoryToAgg: Partial<Record<SensorCategoryId, AggCategory>> = {
      temperature: 'temperature',
      air: 'humidity',
      soil: 'moisture',
      light: 'light',
      water: 'other',
      other: 'other',
    }
    return categoryToAgg[config.category] ?? 'other'
  }

  return 'other'
}

/** Priority for category display order (lower = first) */
const CATEGORY_PRIORITY: Record<AggCategory, number> = {
  temperature: 1,
  humidity: 2,
  pressure: 3,
  moisture: 4,
  light: 5,
  co2: 6,
  ph: 7,
  ec: 8,
  flow: 9,
  other: 99,
}

/** Category display labels */
const CATEGORY_LABELS: Record<AggCategory, string> = {
  temperature: 'Temperatur',
  humidity: 'Luftfeuchte',
  pressure: 'Luftdruck',
  moisture: 'Bodenfeuchte',
  light: 'Licht',
  co2: 'CO2',
  ph: 'pH',
  ec: 'Leitfähigkeit',
  flow: 'Durchfluss',
  other: 'Sonstige',
}

/** Category default units */
const CATEGORY_UNITS: Record<AggCategory, string> = {
  temperature: '°C',
  humidity: '%RH',
  pressure: 'hPa',
  moisture: '%',
  light: 'lux',
  co2: 'ppm',
  ph: 'pH',
  ec: 'µS/cm',
  flow: 'L/min',
  other: '',
}

/** Decimal places per aggregation category — drives all numeric displays (KPIs, aggregations, subzone headers) */
export const CATEGORY_DECIMALS: Record<AggCategory, number> = {
  temperature: 1,
  humidity: 1,
  pressure: 1,
  moisture: 0,
  light: 0,
  co2: 0,
  ph: 2,
  ec: 0,
  flow: 2,
  other: 1,
}

/**
 * Y-Achsen-Defaults für kompakte Gauges, wenn der Wert aus {@link aggregateZoneSensors}
 * (AggCategory) kommt — konsistent mit ZoneTileCard-KPI, nicht mit Einzelsensor-IDs.
 */
const AGG_CATEGORY_GAUGE_RANGE: Record<Exclude<AggCategory, 'other'>, { min: number; max: number }> = {
  temperature: { min: -20, max: 55 },
  humidity: { min: 0, max: 100 },
  pressure: { min: 800, max: 1100 },
  light: { min: 0, max: 100_000 },
  co2: { min: 300, max: 5000 },
  moisture: { min: 0, max: 100 },
  ph: { min: 0, max: 14 },
  ec: { min: 0, max: 5000 },
  flow: { min: 0, max: 100 },
}

export function getAggCategoryGaugeRange(category: AggCategory): { min: number; max: number } | null {
  if (category === 'other') return null
  return AGG_CATEGORY_GAUGE_RANGE[category]
}

/**
 * Monitor L1 zone-tile Auto-Gauges (Preset „Klima (Ø)“): Pick-Reihenfolge für `ensureZoneTileDashboard` in MonitorView.
 * Kein `vpd`: VPD wird in {@link aggregateZoneSensors} nicht als Kategorie geführt — ein VPD-Spot-Gauge würde die Ø-KPI-Zeile nicht spiegeln.
 */
export const ZONE_TILE_AUTO_SENSOR_PRIORITY: readonly string[] = [
  'temp', 'humi', 'ph', 'ec', 'co2', 'soil', 'light', 'pressure', 'flow',
]

/** Sort key for {@link ZONE_TILE_AUTO_SENSOR_PRIORITY} (Monitor L1 zone-tile lead sensor pick). */
export function getZoneTileSensorPriority(sensorType: string): number {
  const st = sensorType.toLowerCase()
  const idx = ZONE_TILE_AUTO_SENSOR_PRIORITY.findIndex(p => st.includes(p))
  return idx >= 0 ? idx : ZONE_TILE_AUTO_SENSOR_PRIORITY.length
}

/**
 * Monitor L2 subzone accordion header: KPI string aligned with {@link aggregateZoneSensors}
 * (same AggCategory buckets, units, priority, max 3 segments). Does not mix unrelated
 * physical quantities that shared SENSOR_TYPE_CONFIG.category "air".
 */
export function formatSubzoneKpiLine(
  sensors: { sensor_type: string; raw_value: number | null; unit: string; quality: string }[],
): string {
  const buckets = new Map<AggCategory, { sum: number; count: number }>()

  for (const s of sensors) {
    if (s.raw_value === null || s.raw_value === undefined) continue
    if (s.quality === 'stale') continue
    if (s.raw_value === 0 && (!s.quality || s.quality === 'unknown')) continue
    if (s.sensor_type === 'vpd' && s.raw_value <= 0) continue

    const category = getSensorAggCategory(s.sensor_type)
    if (category === 'other') continue

    if (!buckets.has(category)) {
      buckets.set(category, { sum: 0, count: 0 })
    }
    const entry = buckets.get(category)!
    entry.sum += s.raw_value
    entry.count++
  }

  const ordered: { category: AggCategory; avg: number }[] = []
  for (const [category, v] of buckets) {
    if (v.count === 0) continue
    ordered.push({
      category,
      avg: v.count > 1 ? v.sum / v.count : v.sum,
    })
  }
  ordered.sort((a, b) => CATEGORY_PRIORITY[a.category] - CATEGORY_PRIORITY[b.category])

  const parts: string[] = []
  for (const { category, avg } of ordered.slice(0, 3)) {
    const unit = CATEGORY_UNITS[category]
    const dec = CATEGORY_DECIMALS[category]
    const num = new Intl.NumberFormat('de-DE', { minimumFractionDigits: dec, maximumFractionDigits: dec }).format(avg)
    parts.push(`${num}${unit}`)
  }
  return parts.join(' · ')
}

/**
 * Zone-level sensor aggregation result
 */
export interface ZoneAggregation {
  sensorTypes: {
    type: AggCategory
    label: string
    avg: number
    min: number
    max: number
    count: number
    unit: string
    decimals: number
  }[]
  /** Number of categories truncated (beyond the visible 3) */
  extraTypeCount: number
  deviceCount: number
  onlineCount: number
}

/**
 * Aggregates sensor data across all devices in a zone.
 *
 * Groups by abstract sensor category (all temperature sensors together,
 * regardless of whether SHT31, DS18B20, or BME280).
 *
 * Returns max 3 sensor types, sorted by priority (temperature > humidity > rest).
 */
export function aggregateZoneSensors(devices: any[]): ZoneAggregation {
  const deviceCount = devices.length
  const onlineCount = devices.filter(d =>
    d.status === 'online' || d.connected === true
  ).length

  if (deviceCount === 0) {
    return { sensorTypes: [], extraTypeCount: 0, deviceCount: 0, onlineCount: 0 }
  }

  // Collect all sensor values grouped by category
  const categoryValues = new Map<AggCategory, number[]>()

  for (const device of devices) {
    const sensors = (device.sensors as RawSensor[] | undefined) || []
    const grouped = groupSensorsByBaseType(sensors)

    for (const group of grouped) {
      for (const val of group.values) {
        if (val.value === null || val.value === undefined) continue
        if (val.quality === 'stale') continue // Skip stale data
        if (val.value === 0 && val.quality === 'unknown') continue // Skip DB init value (no live data yet)
        if (val.type === 'vpd' && val.value <= 0) continue // VPD=0 is physically unrealistic

        const category = getSensorAggCategory(val.type)
        if (category === 'other') continue // Skip uncategorized

        if (!categoryValues.has(category)) {
          categoryValues.set(category, [])
        }
        categoryValues.get(category)!.push(val.value)
      }
    }
  }

  // Build aggregation per category
  const sensorTypes: ZoneAggregation['sensorTypes'] = []

  for (const [category, values] of categoryValues) {
    if (values.length === 0) continue

    const sum = values.reduce((a, b) => a + b, 0)
    sensorTypes.push({
      type: category,
      label: CATEGORY_LABELS[category],
      avg: sum / values.length,
      min: Math.min(...values),
      max: Math.max(...values),
      count: values.length,
      unit: CATEGORY_UNITS[category],
      decimals: CATEGORY_DECIMALS[category],
    })
  }

  // Sort by priority — show all types, no artificial cap
  sensorTypes.sort((a, b) => CATEGORY_PRIORITY[a.type] - CATEGORY_PRIORITY[b.type])
  const extraTypeCount = 0

  return { sensorTypes, extraTypeCount, deviceCount, onlineCount }
}

/**
 * Formats an aggregated sensor value for the zone header.
 *
 * 1 value:    "22.0 °C" (thin space before unit)
 * 2+ values:  "18.3 – 22.5 °C" (range min – max)
 * Same min/max: "22.0 °C (2)" (count in parens)
 */
export function formatAggregatedValue(
  agg: ZoneAggregation['sensorTypes'][0],
  _deviceCount: number,
): string {
  if (agg.count === 0) return ''

  const dec = agg.decimals
  const fmt = (v: number) => new Intl.NumberFormat('de-DE', { minimumFractionDigits: dec, maximumFractionDigits: dec }).format(v)

  if (agg.count === 1) {
    return `${fmt(agg.min)}\u2009${agg.unit}`
  }

  // Multiple values: show range
  const minStr = fmt(agg.min)
  const maxStr = fmt(agg.max)

  if (minStr === maxStr) {
    // Same value across sensors — show count
    return `${minStr}\u2009${agg.unit} (${agg.count})`
  }

  return `${minStr} – ${maxStr}\u2009${agg.unit}`
}





















