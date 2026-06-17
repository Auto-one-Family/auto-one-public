import { computed, type Ref } from 'vue'

/** Server-normalized hardware_type values from esp_devices / heartbeat. */
export type HardwareBoardType =
  | 'ESP32_WROOM'
  | 'ESP32_S3_DEVKITC1'
  | 'XIAO_ESP32_C3'
  | 'MOCK_ESP32'

export interface BoardLayout {
  label: string
  reservedGpios: readonly number[]
  safeGpios: readonly number[]
  /** Pins that cannot be used as digital outputs (ADC1-only, no output mode). */
  inputOnlyGpios: readonly number[]
  adc1Pins: readonly number[]
  adc2WifiConflictPins: readonly number[]
  i2cSda: number
  i2cScl: number
  defaultOnewire: number
}

const ESP32_WROOM_LAYOUT: BoardLayout = {
  label: 'ESP32-WROOM-32',
  reservedGpios: [0, 1, 2, 3, 6, 7, 8, 9, 10, 11, 12, 13],
  safeGpios: [4, 5, 14, 15, 16, 17, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33, 34, 35, 36, 39],
  inputOnlyGpios: [34, 35, 36, 39],
  adc1Pins: [32, 33, 34, 35, 36, 39],
  adc2WifiConflictPins: [0, 2, 4, 12, 13, 14, 15, 25, 26, 27],
  i2cSda: 21,
  i2cScl: 22,
  defaultOnewire: 4,
}

const ESP32_S3_DEVKITC1_LAYOUT: BoardLayout = {
  label: 'ESP32-S3-DevKitC-1 N8R8',
  reservedGpios: [0, 3, 19, 20, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 43, 44, 45, 46, 48],
  safeGpios: [1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 21, 39, 40, 41, 42, 47],
  inputOnlyGpios: [],
  adc1Pins: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
  adc2WifiConflictPins: [11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
  i2cSda: 8,
  i2cScl: 9,
  defaultOnewire: 4,
}

const XIAO_ESP32_C3_LAYOUT: BoardLayout = {
  label: 'Seeed XIAO ESP32-C3',
  reservedGpios: [0, 1, 3, 18, 19],
  safeGpios: [2, 4, 5, 6, 7, 8, 9, 10, 21],
  inputOnlyGpios: [],
  adc1Pins: [0, 1, 2, 3, 4],
  adc2WifiConflictPins: [],
  i2cSda: 4,
  i2cScl: 5,
  defaultOnewire: 4,
}

const BOARD_LAYOUTS: Record<HardwareBoardType, BoardLayout> = {
  ESP32_WROOM: ESP32_WROOM_LAYOUT,
  ESP32_S3_DEVKITC1: ESP32_S3_DEVKITC1_LAYOUT,
  XIAO_ESP32_C3: XIAO_ESP32_C3_LAYOUT,
  MOCK_ESP32: ESP32_WROOM_LAYOUT,
}

function normalizeHardwareType(value: string | null | undefined): HardwareBoardType | null {
  if (!value) return null
  const trimmed = value.trim()
  if (trimmed in BOARD_LAYOUTS) {
    return trimmed as HardwareBoardType
  }
  return null
}

export function useBoardLayout(hardwareType: Ref<string | null | undefined>) {
  const normalizedType = computed(() => normalizeHardwareType(hardwareType.value))

  const layout = computed(() => {
    const key = normalizedType.value
    return key ? BOARD_LAYOUTS[key] : null
  })

  const isKnownBoard = computed(() => layout.value !== null)

  const i2cDefaultLabel = computed(() => {
    if (!layout.value) return null
    return `SDA=GPIO ${layout.value.i2cSda}, SCL=GPIO ${layout.value.i2cScl}`
  })

  const isReserved = (gpio: number): boolean =>
    layout.value?.reservedGpios.includes(gpio) ?? false

  const isSafe = (gpio: number): boolean => {
    if (!layout.value) return true
    return layout.value.safeGpios.includes(gpio)
  }

  const safeOutputGpios = computed(() => {
    if (!layout.value) return []
    const inputOnly = layout.value.inputOnlyGpios
    return layout.value.safeGpios.filter(g => !inputOnly.includes(g))
  })

  return {
    layout,
    normalizedType,
    isKnownBoard,
    i2cDefaultLabel,
    isReserved,
    isSafe,
    adc1Pins: computed(() => layout.value?.adc1Pins ?? []),
    safeOutputGpios,
  }
}
