/**
 * Shared chart color palette for dashboard widgets.
 *
 * Token-bound palette for charts/widgets.
 * Colors are resolved from `tokens.css` at runtime (SSOT).
 *
 * Used by: WidgetConfigPanel (color swatches), MultiSensorWidget (line colors)
 */
import { getCssToken, tokens } from '@/utils/cssTokens'

export const CHART_COLOR_TOKENS = [
  '--color-iridescent-1',
  '--color-success',
  '--color-warning',
  '--color-error',
  '--color-iridescent-3',
  '--color-real',
  '--color-iridescent-4',
  '--color-accent',
] as const

export const CHART_COLORS = CHART_COLOR_TOKENS.map((token) => `var(${token})`) as readonly string[]

function resolveChartToken(token: string): string {
  return getCssToken(token, ['--color-accent', '--color-info']) || tokens.accent || tokens.info
}

export function getChartColors(): string[] {
  return CHART_COLOR_TOKENS.map((token) => resolveChartToken(token))
}

export type ChartColor = string
