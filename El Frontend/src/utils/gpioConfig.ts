/**
 * GPIO Configuration Utility
 *
 * Provides ESP32 GPIO pin information with recommendations for sensors and actuators.
 * Based on ESP32-WROOM and XIAO ESP32-C3 hardware specifications.
 */

// =============================================================================
// TYPES
// =============================================================================

export type GpioCategory = 'recommended' | 'available' | 'caution' | 'avoid' | 'input_only'

export type GpioFeature = 'ADC' | 'DAC' | 'PWM' | 'I2C' | 'SPI' | 'UART' | 'Touch' | 'RTC'

export type GpioUsage = 'sensor' | 'actuator' | 'both'

export interface GpioPin {
  /** GPIO pin number */
  gpio: number
  /** Category for recommendations */
  category: GpioCategory
  /** German label/description */
  label: string
  /** Available features */
  features: GpioFeature[]
  /** Recommended usage */
  recommendedFor: GpioUsage
  /** Warning message (if any) */
  warning?: string
  /** Additional notes */
  notes?: string
}

export type HardwareType = 'ESP32_WROOM' | 'XIAO_ESP32_C3' | 'ESP32_S3_DEVKITC1'

// =============================================================================
// ESP32-WROOM GPIO CONFIGURATION
// =============================================================================

const ESP32_WROOM_PINS: GpioPin[] = [
  // === RECOMMENDED (Safe, versatile pins) ===
  {
    gpio: 14,
    category: 'recommended',
    label: 'GPIO 14',
    features: ['ADC', 'PWM', 'Touch'],
    recommendedFor: 'both',
  },
  {
    gpio: 16,
    category: 'recommended',
    label: 'GPIO 16',
    features: ['PWM'],
    recommendedFor: 'actuator',
  },
  {
    gpio: 17,
    category: 'recommended',
    label: 'GPIO 17',
    features: ['PWM'],
    recommendedFor: 'actuator',
  },
  {
    gpio: 18,
    category: 'recommended',
    label: 'GPIO 18',
    features: ['PWM', 'SPI'],
    recommendedFor: 'both',
  },
  {
    gpio: 19,
    category: 'recommended',
    label: 'GPIO 19',
    features: ['PWM', 'SPI'],
    recommendedFor: 'both',
  },
  {
    gpio: 23,
    category: 'recommended',
    label: 'GPIO 23',
    features: ['PWM', 'SPI'],
    recommendedFor: 'both',
  },
  {
    gpio: 25,
    category: 'recommended',
    label: 'GPIO 25',
    features: ['ADC', 'DAC', 'PWM'],
    recommendedFor: 'both',
  },
  {
    gpio: 26,
    category: 'recommended',
    label: 'GPIO 26',
    features: ['ADC', 'DAC', 'PWM'],
    recommendedFor: 'both',
  },
  {
    gpio: 27,
    category: 'recommended',
    label: 'GPIO 27',
    features: ['ADC', 'PWM', 'Touch'],
    recommendedFor: 'both',
  },

  // === AVAILABLE (Good for specific uses) ===
  {
    gpio: 4,
    category: 'available',
    label: 'GPIO 4',
    features: ['ADC', 'PWM', 'Touch'],
    recommendedFor: 'both',
  },
  {
    gpio: 5,
    category: 'available',
    label: 'GPIO 5 (Strapping)',
    features: ['PWM'],
    recommendedFor: 'actuator',
    notes: 'Strapping-Pin, muss beim Boot LOW sein',
  },
  {
    gpio: 21,
    category: 'available',
    label: 'GPIO 21 (I2C SDA)',
    features: ['I2C', 'PWM'],
    recommendedFor: 'sensor',
    notes: 'Standard I2C Data',
  },
  {
    gpio: 22,
    category: 'available',
    label: 'GPIO 22 (I2C SCL)',
    features: ['I2C', 'PWM'],
    recommendedFor: 'sensor',
    notes: 'Standard I2C Clock',
  },
  {
    gpio: 32,
    category: 'available',
    label: 'GPIO 32',
    features: ['ADC', 'PWM', 'Touch'],
    recommendedFor: 'sensor',
  },
  {
    gpio: 33,
    category: 'available',
    label: 'GPIO 33',
    features: ['ADC', 'PWM', 'Touch'],
    recommendedFor: 'sensor',
  },

  // === INPUT ONLY (No internal pull-up) ===
  {
    gpio: 34,
    category: 'input_only',
    label: 'GPIO 34 (Nur Eingang)',
    features: ['ADC'],
    recommendedFor: 'sensor',
    warning: 'Nur als Eingang verwendbar, kein interner Pull-up',
  },
  {
    gpio: 35,
    category: 'input_only',
    label: 'GPIO 35 (Nur Eingang)',
    features: ['ADC'],
    recommendedFor: 'sensor',
    warning: 'Nur als Eingang verwendbar, kein interner Pull-up',
  },
  {
    gpio: 36,
    category: 'input_only',
    label: 'GPIO 36 / VP (Nur Eingang)',
    features: ['ADC'],
    recommendedFor: 'sensor',
    warning: 'Nur als Eingang verwendbar, Sensor VP',
  },
  {
    gpio: 39,
    category: 'input_only',
    label: 'GPIO 39 / VN (Nur Eingang)',
    features: ['ADC'],
    recommendedFor: 'sensor',
    warning: 'Nur als Eingang verwendbar, Sensor VN',
  },

  // === CAUTION (Usable with care) ===
  {
    gpio: 2,
    category: 'caution',
    label: 'GPIO 2 (Onboard LED)',
    features: ['ADC', 'PWM', 'Touch'],
    recommendedFor: 'actuator',
    warning: 'Verbunden mit Onboard-LED bei vielen Boards',
  },
  {
    gpio: 15,
    category: 'caution',
    label: 'GPIO 15 (Strapping)',
    features: ['ADC', 'PWM', 'Touch'],
    recommendedFor: 'both',
    warning: 'PWM-Signal beim Boot, Strapping-Pin',
  },

  // === AVOID (System reserved) ===
  {
    gpio: 0,
    category: 'avoid',
    label: 'GPIO 0 (Boot-Modus)',
    features: [],
    recommendedFor: 'both',
    warning: 'Steuert Boot-Modus - NICHT VERWENDEN',
  },
  {
    gpio: 12,
    category: 'avoid',
    label: 'GPIO 12 (Flash-Strapping RESERVIERT)',
    features: ['ADC', 'PWM', 'Touch'],
    recommendedFor: 'both',
    warning: 'Flash-Spannungs-Strapping — HIGH beim Boot brickt das Board. RESERVIERT.',
  },
  {
    gpio: 13,
    category: 'avoid',
    label: 'GPIO 13 (RESERVIERT)',
    features: ['ADC', 'PWM', 'Touch'],
    recommendedFor: 'both',
    warning: 'Systemseitig reserviert (JTAG MTCK) — NICHT VERWENDEN',
  },
  {
    gpio: 1,
    category: 'avoid',
    label: 'GPIO 1 (TX0)',
    features: ['UART'],
    recommendedFor: 'both',
    warning: 'UART0 TX - Debugging - NICHT VERWENDEN',
  },
  {
    gpio: 3,
    category: 'avoid',
    label: 'GPIO 3 (RX0)',
    features: ['UART'],
    recommendedFor: 'both',
    warning: 'UART0 RX - Debugging - NICHT VERWENDEN',
  },
  {
    gpio: 6,
    category: 'avoid',
    label: 'GPIO 6-11 (Flash)',
    features: [],
    recommendedFor: 'both',
    warning: 'Verbunden mit internem Flash - NICHT VERWENDEN',
  },
]

// =============================================================================
// ESP32-S3-DevKitC-1 GPIO CONFIGURATION
// =============================================================================

const ESP32_S3_DEVKITC1_PINS: GpioPin[] = [
  // === RECOMMENDED (Safe, versatile output pins) ===
  { gpio: 5,  category: 'recommended', label: 'GPIO 5',  features: ['ADC', 'PWM'], recommendedFor: 'both' },
  { gpio: 10, category: 'recommended', label: 'GPIO 10', features: ['PWM'],         recommendedFor: 'actuator' },
  { gpio: 11, category: 'recommended', label: 'GPIO 11', features: ['PWM'],         recommendedFor: 'actuator' },
  { gpio: 12, category: 'recommended', label: 'GPIO 12', features: ['PWM'],         recommendedFor: 'actuator' },
  { gpio: 13, category: 'recommended', label: 'GPIO 13', features: ['PWM'],         recommendedFor: 'both' },
  { gpio: 14, category: 'recommended', label: 'GPIO 14', features: ['PWM'],         recommendedFor: 'both' },
  { gpio: 15, category: 'recommended', label: 'GPIO 15', features: ['PWM'],         recommendedFor: 'both' },
  { gpio: 16, category: 'recommended', label: 'GPIO 16', features: ['PWM'],         recommendedFor: 'actuator' },
  { gpio: 17, category: 'recommended', label: 'GPIO 17', features: ['PWM'],         recommendedFor: 'actuator' },
  { gpio: 18, category: 'recommended', label: 'GPIO 18', features: ['PWM'],         recommendedFor: 'actuator' },
  { gpio: 21, category: 'recommended', label: 'GPIO 21', features: ['PWM'],         recommendedFor: 'both' },
  { gpio: 39, category: 'recommended', label: 'GPIO 39', features: ['PWM'],         recommendedFor: 'both' },
  { gpio: 40, category: 'recommended', label: 'GPIO 40', features: ['PWM'],         recommendedFor: 'both' },
  { gpio: 41, category: 'recommended', label: 'GPIO 41', features: ['PWM'],         recommendedFor: 'both' },
  { gpio: 42, category: 'recommended', label: 'GPIO 42', features: ['PWM'],         recommendedFor: 'both' },
  { gpio: 47, category: 'recommended', label: 'GPIO 47', features: ['PWM'],         recommendedFor: 'both' },

  // === AVAILABLE (ADC1 + OneWire + I2C) ===
  { gpio: 1,  category: 'available', label: 'GPIO 1 (ADC1)',      features: ['ADC', 'PWM'], recommendedFor: 'sensor', notes: 'ADC1 Channel 0' },
  { gpio: 2,  category: 'available', label: 'GPIO 2 (ADC1)',      features: ['ADC', 'PWM'], recommendedFor: 'sensor', notes: 'ADC1 Channel 1' },
  { gpio: 4,  category: 'available', label: 'GPIO 4 (ADC1/OneWire)', features: ['ADC', 'PWM'], recommendedFor: 'sensor', notes: 'ADC1 Ch3, Standard OneWire' },
  { gpio: 6,  category: 'available', label: 'GPIO 6 (ADC1)',      features: ['ADC', 'PWM'], recommendedFor: 'sensor', notes: 'ADC1 Channel 5' },
  { gpio: 7,  category: 'available', label: 'GPIO 7 (ADC1)',      features: ['ADC', 'PWM'], recommendedFor: 'sensor', notes: 'ADC1 Channel 6' },
  { gpio: 8,  category: 'available', label: 'GPIO 8 (I2C SDA)',   features: ['I2C', 'PWM'], recommendedFor: 'sensor', notes: 'Standard I2C Data (S3)' },
  { gpio: 9,  category: 'available', label: 'GPIO 9 (I2C SCL)',   features: ['I2C', 'PWM'], recommendedFor: 'sensor', notes: 'Standard I2C Clock (S3)' },

  // === AVOID (System reserved — Flash/PSRAM/USB/Strapping/RGB) ===
  { gpio: 0,  category: 'avoid', label: 'GPIO 0 (Strapping)',      features: [],       recommendedFor: 'both', warning: 'Boot-Strapping — NICHT VERWENDEN' },
  { gpio: 3,  category: 'avoid', label: 'GPIO 3 (JTAG)',           features: [],       recommendedFor: 'both', warning: 'JTAG MTDO — NICHT VERWENDEN' },
  { gpio: 19, category: 'avoid', label: 'GPIO 19-20 (USB D-/D+)', features: [],       recommendedFor: 'both', warning: 'USB — NICHT VERWENDEN' },
  { gpio: 26, category: 'avoid', label: 'GPIO 26-37 (Flash/PSRAM)', features: [],     recommendedFor: 'both', warning: 'Flash/PSRAM intern — NICHT VERWENDEN' },
  { gpio: 38, category: 'avoid', label: 'GPIO 38 (RGB LED)',       features: [],       recommendedFor: 'both', warning: 'Onboard RGB LED — NICHT VERWENDEN' },
  { gpio: 43, category: 'avoid', label: 'GPIO 43-44 (UART0)',     features: ['UART'], recommendedFor: 'both', warning: 'UART0 TX/RX Debug — MIT VORSICHT' },
  { gpio: 45, category: 'avoid', label: 'GPIO 45-46 (Strapping)', features: [],       recommendedFor: 'both', warning: 'Strapping-Pins — NICHT VERWENDEN' },
  { gpio: 48, category: 'avoid', label: 'GPIO 48 (RGB LED Ctrl)', features: [],       recommendedFor: 'both', warning: 'RGB LED Control — NICHT VERWENDEN' },
]

// =============================================================================
// XIAO ESP32-C3 GPIO CONFIGURATION
// =============================================================================

const XIAO_ESP32_C3_PINS: GpioPin[] = [
  // XIAO ESP32-C3 has fewer GPIOs available
  {
    gpio: 2,
    category: 'recommended',
    label: 'D0 / GPIO 2',
    features: ['ADC', 'PWM'],
    recommendedFor: 'both',
  },
  {
    gpio: 3,
    category: 'recommended',
    label: 'D1 / GPIO 3',
    features: ['ADC', 'PWM'],
    recommendedFor: 'both',
  },
  {
    gpio: 4,
    category: 'recommended',
    label: 'D2 / GPIO 4',
    features: ['ADC', 'PWM'],
    recommendedFor: 'both',
  },
  {
    gpio: 5,
    category: 'recommended',
    label: 'D3 / GPIO 5',
    features: ['ADC', 'PWM'],
    recommendedFor: 'both',
  },
  {
    gpio: 6,
    category: 'available',
    label: 'D4 / GPIO 6 (I2C SDA)',
    features: ['I2C', 'PWM'],
    recommendedFor: 'sensor',
    notes: 'Standard I2C Data',
  },
  {
    gpio: 7,
    category: 'available',
    label: 'D5 / GPIO 7 (I2C SCL)',
    features: ['I2C', 'PWM'],
    recommendedFor: 'sensor',
    notes: 'Standard I2C Clock',
  },
  {
    gpio: 8,
    category: 'available',
    label: 'D6 / GPIO 8 (SPI SCK)',
    features: ['SPI', 'PWM'],
    recommendedFor: 'both',
  },
  {
    gpio: 9,
    category: 'available',
    label: 'D7 / GPIO 9 (SPI MISO)',
    features: ['SPI', 'PWM'],
    recommendedFor: 'both',
  },
  {
    gpio: 10,
    category: 'available',
    label: 'D8 / GPIO 10 (SPI MOSI)',
    features: ['SPI', 'PWM'],
    recommendedFor: 'both',
  },
  {
    gpio: 20,
    category: 'caution',
    label: 'D9 / GPIO 20 (RX)',
    features: ['UART'],
    recommendedFor: 'both',
    warning: 'UART RX - Mit Vorsicht verwenden',
  },
  {
    gpio: 21,
    category: 'caution',
    label: 'D10 / GPIO 21 (TX)',
    features: ['UART'],
    recommendedFor: 'both',
    warning: 'UART TX - Mit Vorsicht verwenden',
  },
]

// =============================================================================
// GPIO CONFIG MAP
// =============================================================================

const GPIO_CONFIGS: Record<HardwareType, GpioPin[]> = {
  ESP32_WROOM: ESP32_WROOM_PINS,
  ESP32_S3_DEVKITC1: ESP32_S3_DEVKITC1_PINS,
  XIAO_ESP32_C3: XIAO_ESP32_C3_PINS,
}

// =============================================================================
// PUBLIC API
// =============================================================================

/**
 * Get all GPIO pins for a hardware type.
 *
 * @param hardwareType - Hardware type (defaults to ESP32_WROOM)
 * @returns Array of GPIO pin configurations
 */
export function getGpioConfig(hardwareType: HardwareType = 'ESP32_WROOM'): GpioPin[] {
  return GPIO_CONFIGS[hardwareType] || GPIO_CONFIGS.ESP32_WROOM
}

/**
 * Get available GPIO pins (excludes pins already in use).
 *
 * @param hardwareType - Hardware type
 * @param usedPins - Array of already used GPIO pins
 * @returns Filtered array of available GPIO pins
 */
export function getAvailablePins(
  hardwareType: HardwareType = 'ESP32_WROOM',
  usedPins: number[] = []
): GpioPin[] {
  const allPins = getGpioConfig(hardwareType)
  return allPins.filter(pin => !usedPins.includes(pin.gpio))
}

/**
 * Get GPIO pins grouped by category.
 *
 * @param hardwareType - Hardware type
 * @param usedPins - Already used pins (will be marked as unavailable)
 */
export function getGpiosByCategory(
  hardwareType: HardwareType = 'ESP32_WROOM',
  usedPins: number[] = []
): Record<GpioCategory, GpioPin[]> {
  const allPins = getGpioConfig(hardwareType)

  const grouped: Record<GpioCategory, GpioPin[]> = {
    recommended: [],
    available: [],
    input_only: [],
    caution: [],
    avoid: [],
  }

  for (const pin of allPins) {
    if (!usedPins.includes(pin.gpio)) {
      grouped[pin.category].push(pin)
    }
  }

  return grouped
}

/**
 * Get GPIO pins suitable for sensors.
 */
export function getSensorGpios(
  hardwareType: HardwareType = 'ESP32_WROOM',
  usedPins: number[] = []
): GpioPin[] {
  return getAvailablePins(hardwareType, usedPins).filter(
    pin =>
      pin.category !== 'avoid' &&
      (pin.recommendedFor === 'sensor' || pin.recommendedFor === 'both')
  )
}

/**
 * Get GPIO pins suitable for actuators.
 */
export function getActuatorGpios(
  hardwareType: HardwareType = 'ESP32_WROOM',
  usedPins: number[] = []
): GpioPin[] {
  return getAvailablePins(hardwareType, usedPins).filter(
    pin =>
      pin.category !== 'avoid' &&
      pin.category !== 'input_only' &&
      (pin.recommendedFor === 'actuator' || pin.recommendedFor === 'both')
  )
}

/**
 * Get information about a specific GPIO pin.
 */
export function getGpioInfo(
  gpio: number,
  hardwareType: HardwareType = 'ESP32_WROOM'
): GpioPin | undefined {
  return getGpioConfig(hardwareType).find(pin => pin.gpio === gpio)
}

/**
 * Check if a GPIO is recommended for use.
 */
export function isGpioRecommended(
  gpio: number,
  hardwareType: HardwareType = 'ESP32_WROOM'
): boolean {
  const pin = getGpioInfo(gpio, hardwareType)
  return pin?.category === 'recommended'
}

/**
 * Check if a GPIO should be avoided.
 */
export function isGpioAvoid(
  gpio: number,
  hardwareType: HardwareType = 'ESP32_WROOM'
): boolean {
  const pin = getGpioInfo(gpio, hardwareType)
  return pin?.category === 'avoid'
}

/**
 * Get warning message for a GPIO pin.
 */
export function getGpioWarning(
  gpio: number,
  hardwareType: HardwareType = 'ESP32_WROOM'
): string | null {
  const pin = getGpioInfo(gpio, hardwareType)
  return pin?.warning || null
}

/**
 * Get German category label.
 */
export function getCategoryLabel(category: GpioCategory): string {
  const labels: Record<GpioCategory, string> = {
    recommended: 'Empfohlen',
    available: 'Verfügbar',
    input_only: 'Nur Eingang',
    caution: 'Mit Vorsicht',
    avoid: 'Vermeiden',
  }
  return labels[category]
}

/**
 * Get category color class.
 */
export function getCategoryColorClass(category: GpioCategory): string {
  const classes: Record<GpioCategory, string> = {
    recommended: 'text-success',
    available: 'text-info',
    input_only: 'text-warning',
    caution: 'text-warning',
    avoid: 'text-error',
  }
  return classes[category]
}

// =============================================================================
// GPIO RECOMMENDATIONS (Phase 5)
// =============================================================================

// =============================================================================
// BOARD-SPECIFIC GPIO RECOMMENDATIONS
// =============================================================================

const WROOM_RECOMMENDATIONS: Record<string, number[]> = {
  'ds18b20':     [4, 5, 14, 15],
  'temperature': [4, 5, 14, 15],
  'sht31':       [21, 22],
  'bme280':      [21, 22],
  'aht20':       [21, 22],
  'humidity':    [21, 22],
  'i2c':         [21, 22],
  // ADC1 pins (no WiFi conflict): 32-39
  'ph':           [32, 33, 34, 35, 36, 39],
  'ec':           [32, 33, 34, 35, 36, 39],
  'moisture':     [32, 33, 34, 35, 36, 39],
  'soil_moisture':[32, 33, 34, 35, 36, 39],
  'water_level':  [32, 33, 34, 35, 36, 39],
  'light':        [32, 33, 34, 35, 36, 39],
  'ldr':          [32, 33, 34, 35, 36, 39],
  'analog':       [32, 33, 34, 35, 36, 39],
  'co2':          [16],
  'scd30':        [21, 22],
  'scd40':        [21, 22],
  'pressure':     [21, 22],
  'bmp280':       [21, 22],
  'flow':         [4, 5, 14, 15, 16, 17, 18, 19],
  'relay':        [4, 5, 14, 15, 16, 17, 18, 19, 23, 25, 26, 27],
  'pump':         [4, 5, 14, 15, 16, 17, 18, 19, 23, 25, 26, 27],
  'valve':        [4, 5, 14, 15, 16, 17, 18, 19, 23, 25, 26, 27],
  'heater':       [4, 5, 14, 15, 16, 17, 18, 19, 23, 25, 26, 27],
  'cooler':       [4, 5, 14, 15, 16, 17, 18, 19, 23, 25, 26, 27],
  'pwm':          [4, 5, 14, 15, 16, 17, 18, 19, 21, 22, 23, 25, 26, 27],
  'fan':          [4, 5, 14, 15, 16, 17, 18, 19, 25, 26, 27],
  'led':          [4, 5, 14, 15, 16, 17, 18, 19, 25, 26, 27],
  'dimmer':       [4, 5, 14, 15, 16, 17, 18, 19, 25, 26, 27],
}

// S3 ADC1 safe pins: 1,2,4,6,7 (avoid 5=strapping-adjacent on some boards, 3=JTAG, 8/9=I2C)
const S3_RECOMMENDATIONS: Record<string, number[]> = {
  'ds18b20':     [4, 5, 13, 14],
  'temperature': [4, 5, 13, 14],
  // I2C default on S3: GPIO 8 (SDA) / 9 (SCL)
  'sht31':       [8, 9],
  'bme280':      [8, 9],
  'aht20':       [8, 9],
  'humidity':    [8, 9],
  'i2c':         [8, 9],
  // ADC1 pins on S3: 1-10 (safe subset without I2C/strapping pins)
  'ph':           [1, 2, 4, 6, 7],
  'ec':           [1, 2, 4, 6, 7],
  'moisture':     [1, 2, 4, 6, 7],
  'soil_moisture':[1, 2, 4, 6, 7],
  'water_level':  [1, 2, 4, 6, 7],
  'light':        [1, 2, 4, 6, 7],
  'ldr':          [1, 2, 4, 6, 7],
  'analog':       [1, 2, 4, 6, 7],
  'co2':          [18],
  'scd30':        [8, 9],
  'scd40':        [8, 9],
  'pressure':     [8, 9],
  'bmp280':       [8, 9],
  'flow':         [4, 5, 13, 14, 16, 17, 18, 21],
  'relay':        [10, 11, 12, 13, 16, 17, 18, 21, 39, 40, 41, 42],
  'pump':         [10, 11, 12, 13, 16, 17, 18, 21, 39, 40, 41, 42],
  'valve':        [10, 11, 12, 13, 16, 17, 18, 21, 39, 40, 41, 42],
  'heater':       [10, 11, 12, 13, 16, 17, 18, 21, 39, 40, 41, 42],
  'cooler':       [10, 11, 12, 13, 16, 17, 18, 21, 39, 40, 41, 42],
  'pwm':          [10, 11, 13, 16, 17, 18, 21, 39, 40, 41, 42, 47],
  'fan':          [10, 11, 13, 16, 17, 18, 39, 40, 41, 42, 47],
  'led':          [10, 11, 13, 16, 17, 18, 39, 40, 41, 42, 47],
  'dimmer':       [10, 11, 13, 16, 17, 18, 39, 40, 41, 42, 47],
}

const XIAO_RECOMMENDATIONS: Record<string, number[]> = {
  'ds18b20':     [2, 4, 5, 8, 9, 10],
  'temperature': [2, 4, 5, 8, 9, 10],
  'sht31':       [6, 7],
  'bme280':      [6, 7],
  'aht20':       [6, 7],
  'humidity':    [6, 7],
  'i2c':         [6, 7],
  'ph':           [2, 3, 4, 5],
  'ec':           [2, 3, 4, 5],
  'moisture':     [2, 3, 4, 5],
  'soil_moisture':[2, 3, 4, 5],
  'water_level':  [2, 3, 4, 5],
  'light':        [2, 3, 4, 5],
  'ldr':          [2, 3, 4, 5],
  'analog':       [2, 3, 4, 5],
  'co2':          [6, 7],
  'scd30':        [6, 7],
  'scd40':        [6, 7],
  'pressure':     [6, 7],
  'bmp280':       [6, 7],
  'flow':         [2, 4, 5, 8, 9, 10],
  'relay':        [2, 4, 5, 8, 9, 10],
  'pump':         [2, 4, 5, 8, 9, 10],
  'valve':        [2, 4, 5, 8, 9, 10],
  'heater':       [2, 4, 5, 8, 9, 10],
  'cooler':       [2, 4, 5, 8, 9, 10],
  'pwm':          [2, 4, 5, 8, 9, 10],
  'fan':          [2, 4, 5, 8, 9, 10],
  'led':          [2, 4, 5, 8, 9, 10],
  'dimmer':       [2, 4, 5, 8, 9, 10],
}

const BOARD_RECOMMENDATIONS: Record<HardwareType, Record<string, number[]>> = {
  ESP32_WROOM:      WROOM_RECOMMENDATIONS,
  ESP32_S3_DEVKITC1: S3_RECOMMENDATIONS,
  XIAO_ESP32_C3:    XIAO_RECOMMENDATIONS,
}

/**
 * Get recommended GPIOs for a specific sensor/actuator type.
 *
 * Returns pins that are particularly suitable based on:
 * - Electrical characteristics (ADC for analog sensors)
 * - Common usage patterns
 * - Hardware limitations
 *
 * @param componentType - Sensor or actuator type (e.g., "DS18B20", "pH", "pump")
 * @param category - 'sensor' or 'actuator' (default: 'sensor')
 * @param hardwareType - Board variant (defaults to ESP32_WROOM when omitted)
 * @returns Array of recommended GPIO numbers
 *
 * @example
 * getRecommendedGpios('ph', 'sensor', 'ESP32_WROOM')       // [32,33,34,35,36,39]
 * getRecommendedGpios('ph', 'sensor', 'ESP32_S3_DEVKITC1') // [1,2,4,6,7]
 * getRecommendedGpios('pump', 'actuator', 'ESP32_S3_DEVKITC1') // [10,11,12,13,16,17,18,21,39,40,41,42]
 */
export function getRecommendedGpios(
  componentType: string,
  category: 'sensor' | 'actuator' = 'sensor',
  hardwareType?: HardwareType | null
): number[] {
  const recommendations = hardwareType
    ? (BOARD_RECOMMENDATIONS[hardwareType] ?? WROOM_RECOMMENDATIONS)
    : WROOM_RECOMMENDATIONS

  const normalizedType = componentType.toLowerCase().trim()

  if (recommendations[normalizedType]) {
    return recommendations[normalizedType]
  }

  // Partial match (e.g., "ds18b20_temperature" matches "ds18b20")
  for (const [key, gpios] of Object.entries(recommendations)) {
    if (normalizedType.includes(key) || key.includes(normalizedType)) {
      return gpios
    }
  }

  // Default fallback based on category and board
  if (category === 'actuator') {
    if (hardwareType === 'ESP32_S3_DEVKITC1') return [10, 11, 12, 13, 16, 17, 18, 21, 39, 40, 41, 42]
    if (hardwareType === 'XIAO_ESP32_C3')     return [2, 4, 5, 8, 9, 10]
    return [4, 5, 14, 15, 16, 17, 18, 19, 23, 25, 26, 27]
  }

  if (hardwareType === 'ESP32_S3_DEVKITC1') return [4, 5, 13, 14, 16, 17, 18, 21]
  if (hardwareType === 'XIAO_ESP32_C3')     return [2, 4, 5, 6, 7, 8, 9, 10]
  return [4, 5, 14, 15, 16, 17, 18, 19, 23, 25, 26, 27]
}

// =============================================================================
// DYNAMIC STATUS INTEGRATION (Phase 3)
// =============================================================================

import type { GpioStatusResponse, GpioPinStatus } from '@/types/gpio'

/**
 * Merge static GPIO config with dynamic status from server.
 *
 * Combines hardware-specific pin definitions with actual usage status.
 * Used when you need both static pin info (features, warnings) and
 * dynamic status (available/reserved).
 *
 * @param hardwareType - ESP32 variant
 * @param dynamicStatus - Status from GET /gpio-status (or null if not loaded)
 * @returns Enriched pin list with both static info and usage status
 */
export function mergeGpioConfigWithStatus(
  hardwareType: HardwareType,
  dynamicStatus: GpioStatusResponse | null
): GpioPinStatus[] {
  const staticConfig = getGpioConfig(hardwareType)

  if (!dynamicStatus) {
    // Fallback: Only static info, all marked as unknown
    return staticConfig.map(pin => ({
      gpio: pin.gpio,
      available: false,  // Unknown = unavailable (safe default)
      owner: null,
      component: null,
      name: pin.label,
      statusClass: 'system' as const,
      tooltip: `GPIO ${pin.gpio} - Status unbekannt`
    }))
  }

  return staticConfig.map(pin => {
    // Check if in system pins
    if (dynamicStatus.system.includes(pin.gpio)) {
      return {
        gpio: pin.gpio,
        available: false,
        owner: 'system' as const,
        component: pin.label,
        name: null,
        statusClass: 'system' as const,
        tooltip: `GPIO ${pin.gpio} - System (${pin.label})`
      }
    }

    // Check if reserved
    const reserved = dynamicStatus.reserved.find(r => r.gpio === pin.gpio)
    if (reserved) {
      const ownerLabel = reserved.owner === 'sensor' ? 'Sensor' :
                         reserved.owner === 'actuator' ? 'Aktor' : 'System'
      return {
        gpio: pin.gpio,
        available: false,
        owner: reserved.owner,
        component: reserved.component,
        name: reserved.name,
        statusClass: reserved.owner as 'sensor' | 'actuator' | 'system',
        tooltip: `GPIO ${pin.gpio} - ${ownerLabel}: ${reserved.name || reserved.component}`
      }
    }

    // Available
    if (dynamicStatus.available.includes(pin.gpio)) {
      return {
        gpio: pin.gpio,
        available: true,
        owner: null,
        component: null,
        name: pin.label,
        statusClass: 'available' as const,
        tooltip: `GPIO ${pin.gpio} - Verfügbar (${pin.label})`
      }
    }

    // Unknown (not in any list)
    return {
      gpio: pin.gpio,
      available: false,
      owner: null,
      component: null,
      name: pin.label,
      statusClass: 'system' as const,
      tooltip: `GPIO ${pin.gpio} - Status unbekannt`
    }
  })
}
