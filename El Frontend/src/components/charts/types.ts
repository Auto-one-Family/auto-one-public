export interface ChartDataPoint {
  timestamp: string | Date
  value: number | null
  label?: string
}

export interface GaugeThreshold {
  /** Value at which this threshold starts */
  value: number
  /** Color for this segment (hex) */
  color: string
}

export interface StatusBarItem {
  /** Bar label */
  label: string
  /** Bar value */
  value: number
  /** Bar color (hex) */
  color?: string
  /** Maximum value for relative sizing */
  maxValue?: number
}
