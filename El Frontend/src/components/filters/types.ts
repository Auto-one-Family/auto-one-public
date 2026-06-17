export type StatusFilter = 'online' | 'offline' | 'warning' | 'safemode'
export type TypeFilter = 'all' | 'mock' | 'real'
export type TimeRange = '1h' | '6h' | '24h' | '7d' | 'all'

export interface FilterCounts {
  // Status counts
  online?: number
  offline?: number
  warning?: number
  safemode?: number
  // Type counts
  all?: number
  mock?: number
  real?: number
}
