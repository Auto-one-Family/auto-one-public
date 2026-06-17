export interface HardwareRouteFallbackInput {
  currentLevel: 1 | 2
  selectedEspId: string | null
  nextDeviceExists: boolean
  previousDeviceExists: boolean
}

export function shouldFallbackToHardwareOverview(input: HardwareRouteFallbackInput): boolean {
  return (
    input.currentLevel === 2
    && Boolean(input.selectedEspId)
    && !input.nextDeviceExists
    && input.previousDeviceExists
  )
}
