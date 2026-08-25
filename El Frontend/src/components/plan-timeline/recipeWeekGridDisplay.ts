/**
 * Display helpers for PlanRecipeWeekGrid (AUT-1420 B3 / AUT-1421 B4).
 * Pure — no network. Formats resolved stock_mix recipes for the existing table.
 *
 * Columns follow real nutrient_solution plan staffeln (EC/pH Ziele + phase_ref),
 * not calendar weeks — same pairing as TankEcPhPlanEditor / buildEcPhStaffeln.
 *
 * Solution profile (A+B × dose → mg/L) uses server `computed_elements`
 * (g_per_l_stock, elemental) — same salt→element basis as stock_mix_npk.py.
 */

import { getPlantPhaseLabel } from '@/components/plants/plantLabels'
import type { StockMixRecipe } from '@/api/stockMixRecipes'
import type { PlanSegment } from '@/types/planSegment'
import {
  buildEcPhStaffeln,
  formatStaffelRange,
  type EcPhStaffel,
} from '@/components/plants/tankEcPhPlanStaffel'

/** Oxide → elemental mass factors (standard fertilizer conversions). */
export const P2O5_TO_P = 0.4364
export const K2O_TO_K = 0.8302

/** Phase name + suggested oxid-form NPK (NOT tank-solution mg/L). */
export interface PhaseDisplayMeta {
  name: string
  /** Suggested N-P₂O₅-K₂O tag for the phase; display-only. */
  oxidLabel: string | null
}

export const RECIPE_PHASE_META: Record<string, PhaseDisplayMeta> = {
  'veg-frueh': { name: 'Vegetation', oxidLabel: '16-7-20' },
  'veg-spaet': { name: 'Vegetation', oxidLabel: '16-7-20' },
  'uebergang-vorbluete': { name: 'Übergang/Vorblüte', oxidLabel: '8-6-12' },
  'bluete-stretch': { name: 'Blüte', oxidLabel: '8-11-16' },
  'bluete-bulk': { name: 'Blüte', oxidLabel: '8-11-16' },
  'bluete-ende': { name: 'Blüte', oxidLabel: '8-11-16' },
}

export function parseNpkRatio(label: string): { n: number; p: number; k: number } | null {
  const m = label.trim().match(/^(\d+(?:[.,]\d+)?)-(\d+(?:[.,]\d+)?)-(\d+(?:[.,]\d+)?)$/)
  if (!m) return null
  const n = Number(m[1].replace(',', '.'))
  const p = Number(m[2].replace(',', '.'))
  const k = Number(m[3].replace(',', '.'))
  if (![n, p, k].every((v) => Number.isFinite(v))) return null
  return { n, p, k }
}

export function formatNpkRatio(n: number, p: number, k: number): string {
  return `${n}-${p}-${k}`
}

/**
 * Convert oxid-form N-P₂O₅-K₂O label → rounded elemental N-P-K.
 * Display aid only — not the tank mg/L profile.
 */
export function oxidLabelToElementalNpk(oxidLabel: string): string | null {
  const parsed = parseNpkRatio(oxidLabel)
  if (!parsed) return null
  return formatNpkRatio(
    Math.round(parsed.n),
    Math.round(parsed.p * P2O5_TO_P),
    Math.round(parsed.k * K2O_TO_K),
  )
}

/** @deprecated use RECIPE_PHASE_META — kept for any external Klartext reads */
export const RECIPE_PHASE_LABELS: Record<string, string> = Object.fromEntries(
  Object.entries(RECIPE_PHASE_META).map(([k, v]) => [
    k,
    v.oxidLabel ? `${v.name} ${v.oxidLabel}` : v.name,
  ]),
)

/** Map free-text recipe_ref / legacy labels → phase key (best effort). */
const RECIPE_REF_TO_PHASE: Array<{ match: RegExp; phase: string }> = [
  { match: /vegetat|veg\b|16-7-20/i, phase: 'veg-frueh' },
  { match: /uebergang|übergang|vorbluet|vorblüt|8-6-12/i, phase: 'uebergang-vorbluete' },
  { match: /bluete|blüte|8-11-16/i, phase: 'bluete-stretch' },
]

const MACRO_KEYS = ['n', 'p', 'k', 'ca', 'mg', 's'] as const
const TRACE_KEYS = ['b', 'cu', 'fe', 'mn', 'mo', 'zn'] as const
const MACRO_LABELS: Record<(typeof MACRO_KEYS)[number], string> = {
  n: 'N',
  p: 'P',
  k: 'K',
  ca: 'Ca',
  mg: 'Mg',
  s: 'S',
}
const TRACE_LABELS: Record<(typeof TRACE_KEYS)[number], string> = {
  b: 'B',
  cu: 'Cu',
  fe: 'Fe',
  mn: 'Mn',
  mo: 'Mo',
  zn: 'Zn',
}

export type MacroElementKey = (typeof MACRO_KEYS)[number]

export function phaseKeyFromSegment(input: {
  phase_ref?: string | null
  recipe_ref?: string | null
}): string | null {
  const phase = (input.phase_ref ?? '').trim()
  if (phase) return phase
  const ref = (input.recipe_ref ?? '').trim()
  if (!ref) return null
  // UUID → not a phase key; caller may resolve by id later
  if (/^[0-9a-f-]{36}$/i.test(ref)) return null
  for (const row of RECIPE_REF_TO_PHASE) {
    if (row.match.test(ref)) return row.phase
  }
  return null
}

/** Phase name only (no oxid tag). */
export function phaseDisplayLabel(phaseKey: string | null, fallback?: string | null): string {
  if (phaseKey && RECIPE_PHASE_META[phaseKey]) return RECIPE_PHASE_META[phaseKey].name
  if (fallback && fallback.trim()) {
    // Strip trailing oxid-looking tags from free-text fallbacks
    return fallback.trim().replace(/\s+\d+-\d+-\d+\s*$/, '').trim() || fallback.trim()
  }
  if (phaseKey) return getPlantPhaseLabel(phaseKey)
  return '—'
}

export function phaseOxidLabel(phaseKey: string | null): string | null {
  if (phaseKey && RECIPE_PHASE_META[phaseKey]) return RECIPE_PHASE_META[phaseKey].oxidLabel
  return null
}

/** Short DE date for grid headers (dd.mm.). */
export function formatPlanRangeShort(fromTs: string, toTs: string | null): string {
  const fmt = (iso: string): string => {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })
  }
  if (!toTs) return `ab ${fmt(fromTs)}`
  return `${fmt(fromTs)} – ${fmt(toTs)}`
}

export interface RecipeGridColumn {
  key: string
  /** Phase name only (header title). */
  title: string
  /** Suggested oxid-form N-P₂O₅-K₂O for the phase — not tank mg/L. */
  oxidLabel: string | null
  /** Short date range for header. */
  rangeLabel: string
  /** Longer range (YYYY-MM-DD) for a11y/title. */
  rangeTitle: string
  startMs: number
  endMs: number
  phaseKey: string | null
  targetEcUsCm: number | null
  targetPh: number | null
  phaseSource: { phase_ref?: string | null; recipe_ref?: string | null }
}

function staffelOverlapsWindow(
  row: EcPhStaffel,
  window: { startMs: number; endMs: number },
): boolean {
  const fromMs = Date.parse(row.fromTs)
  if (Number.isNaN(fromMs)) return false
  const toMs = row.toTs == null ? Number.POSITIVE_INFINITY : Date.parse(row.toTs)
  if (row.toTs != null && Number.isNaN(toMs)) return false
  return fromMs < window.endMs && toMs > window.startMs
}

/**
 * One column per EC/pH plan staffel (operator-assigned Zeitraum + Ziele).
 * Optional window filter — omit to show all zone staffeln.
 */
export function buildRecipeGridColumns(
  segments: readonly PlanSegment[],
  zoneId: string,
  window?: { startMs: number; endMs: number } | null,
): RecipeGridColumn[] {
  if (!zoneId) return []
  let staffeln = buildEcPhStaffeln(segments, zoneId)
  if (window) {
    staffeln = staffeln.filter((row) => staffelOverlapsWindow(row, window))
  }

  return staffeln.map((row) => {
    const phaseCarrier = row.ec ?? row.ph
    const phaseSource = {
      phase_ref: phaseCarrier?.phase_ref ?? null,
      recipe_ref: phaseCarrier?.recipe_ref ?? null,
    }
    const phaseKey = phaseKeyFromSegment(phaseSource)
    const endMs =
      row.toTs == null
        ? Number.POSITIVE_INFINITY
        : Date.parse(row.toTs)
    return {
      key: row.key,
      title: phaseDisplayLabel(
        phaseKey,
        phaseSource.phase_ref || phaseSource.recipe_ref || 'ohne Phase',
      ),
      oxidLabel: phaseOxidLabel(phaseKey),
      rangeLabel: formatPlanRangeShort(row.fromTs, row.toTs),
      rangeTitle: formatStaffelRange(row.fromTs, row.toTs),
      startMs: Date.parse(row.fromTs),
      endMs: Number.isNaN(endMs) ? Number.POSITIVE_INFINITY : endMs,
      phaseKey,
      targetEcUsCm:
        row.ec?.value != null && Number.isFinite(Number(row.ec.value))
          ? Number(row.ec.value)
          : null,
      targetPh:
        row.ph?.value != null && Number.isFinite(Number(row.ph.value))
          ? Number(row.ph.value)
          : null,
      phaseSource,
    }
  })
}

/** Structured EC/pH goal line for readable table rendering. */
export interface GoalDisplayLine {
  kind: 'ec' | 'ph'
  label: string
  /** Display-rounded value; null → em dash. */
  valueDisplay: string | null
  /** Exact raw value for title tooltip. */
  valueTitle: string | null
  unit: string | null
}

export function formatTargetGoals(col: RecipeGridColumn): GoalDisplayLine[] {
  const goals: GoalDisplayLine[] = []
  if (col.targetEcUsCm != null) {
    goals.push({
      kind: 'ec',
      label: 'EC',
      valueDisplay: col.targetEcUsCm.toLocaleString('de-DE', { maximumFractionDigits: 0 }),
      valueTitle: String(col.targetEcUsCm),
      unit: 'µS/cm',
    })
  } else {
    goals.push({
      kind: 'ec',
      label: 'EC',
      valueDisplay: null,
      valueTitle: null,
      unit: 'µS/cm',
    })
  }
  if (col.targetPh != null) {
    goals.push({
      kind: 'ph',
      label: 'pH',
      valueDisplay: col.targetPh.toLocaleString('de-DE', {
        maximumFractionDigits: 1,
        minimumFractionDigits: 1,
      }),
      valueTitle: String(col.targetPh),
      unit: null,
    })
  } else {
    goals.push({
      kind: 'ph',
      label: 'pH',
      valueDisplay: null,
      valueTitle: null,
      unit: null,
    })
  }
  return goals
}

/** Legacy string lines (tests / fallback). */
export function formatTargetGoalsLine(col: RecipeGridColumn): string[] {
  return formatTargetGoals(col).map((g) => {
    if (g.valueDisplay == null) return `${g.label} —`
    return g.unit ? `${g.label} ${g.valueDisplay} ${g.unit}` : `${g.label} ${g.valueDisplay}`
  })
}

function formatMl(value: unknown): string | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return value.toLocaleString('de-DE', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  })
}

function readDoseMl(recipe: StockMixRecipe | null | undefined): {
  a: number | null
  b: number | null
} {
  const meta = recipe?.metadata ?? {}
  const dose = meta.dose_ml_per_l
  if (!dose || typeof dose !== 'object') return { a: null, b: null }
  const d = dose as Record<string, unknown>
  const a = typeof d.part_a === 'number' && Number.isFinite(d.part_a) ? d.part_a : null
  const b = typeof d.part_b === 'number' && Number.isFinite(d.part_b) ? d.part_b : null
  return { a, b }
}

/** Exact locale string for tooltip — no forced rounding. */
function formatExactNumber(v: number): string {
  return v.toLocaleString('de-DE', {
    maximumFractionDigits: 6,
    minimumFractionDigits: 0,
  })
}

/** Display rounding for stock g/L (1 decimal) — presentation / tests. */
export function formatNpkDisplay(v: number): string {
  return v.toLocaleString('de-DE', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })
}

/** Display rounding for solution mg/L (integer). */
export function formatMgPerLDisplay(v: number): string {
  return v.toLocaleString('de-DE', {
    maximumFractionDigits: 0,
  })
}

function numFromRecord(
  src: Record<string, unknown> | null | undefined,
  key: string,
): number | null {
  if (!src || typeof src !== 'object') return null
  const v = src[key]
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

/**
 * Elemental g/L in stock concentrate from server compute
 * (computed_elements preferred; computed_npk fallback for N/P/K).
 */
export function readStockElementGPerL(
  recipe: StockMixRecipe | null | undefined,
): Record<string, number> {
  const out: Record<string, number> = {}
  if (!recipe) return out
  const elements = recipe.computed_elements ?? null
  const npk = recipe.computed_npk ?? null
  for (const key of [...MACRO_KEYS, ...TRACE_KEYS]) {
    const fromEl = numFromRecord(elements as Record<string, unknown> | null, key)
    if (fromEl != null) {
      out[key] = fromEl
      continue
    }
    if (key === 'n' || key === 'p' || key === 'k') {
      const fromNpk = numFromRecord(npk as Record<string, unknown> | null, key)
      if (fromNpk != null) out[key] = fromNpk
    }
  }
  return out
}

/**
 * Finished-solution mg/L: Σ dose_ml_per_l(stock) × g_per_l_stock(element).
 * Same basis as stock_mix_npk (elemental % × target_g_per_l).
 */
export function combineSolutionMgPerL(
  partA: StockMixRecipe | null | undefined,
  partB: StockMixRecipe | null | undefined,
): {
  mgPerL: Record<string, number>
  doseA: number
  doseB: number
  hasElements: boolean
} {
  const doseAMeta = readDoseMl(partA)
  const doseBMeta = readDoseMl(partB)
  const doseA = doseAMeta.a ?? doseBMeta.a ?? 0
  const doseB = doseAMeta.b ?? doseBMeta.b ?? 0
  const elA = readStockElementGPerL(partA)
  const elB = readStockElementGPerL(partB)
  const keys = new Set([...Object.keys(elA), ...Object.keys(elB)])
  const mgPerL: Record<string, number> = {}
  for (const key of keys) {
    mgPerL[key] = doseA * (elA[key] ?? 0) + doseB * (elB[key] ?? 0)
  }
  return {
    mgPerL,
    doseA,
    doseB,
    hasElements: keys.size > 0,
  }
}

/**
 * Dose-independent elemental NPK ratio parts (normalized to equal-dose g/L sum
 * when A/B doses match; otherwise proportional to mg/L).
 */
export function elementalNpkRatioParts(
  mgPerL: Record<string, number>,
  doseA: number,
  doseB: number,
): { n: number; p: number; k: number } {
  const n = mgPerL.n ?? 0
  const p = mgPerL.p ?? 0
  const k = mgPerL.k ?? 0
  const equalDose = doseA > 0 && doseB > 0 && Math.abs(doseA - doseB) < 1e-9
  const scale = equalDose ? doseA : 1
  return { n: n / scale, p: p / scale, k: k / scale }
}

/** Elemental N-P-K parts → oxid-form N-P₂O₅-K₂O (same convention as header label). */
export function elementalPartsToOxidNpk(
  n: number,
  p: number,
  k: number,
): { n: number; p: number; k: number } {
  return {
    n,
    p: p / P2O5_TO_P,
    k: k / K2O_TO_K,
  }
}

export function formatOxidNpkRatio(n: number, pOxide: number, kOxide: number): {
  display: string
  title: string
} {
  return {
    display: formatNpkRatio(Math.round(n), Math.round(pOxide), Math.round(kOxide)),
    title: `${formatExactNumber(n)}-${formatExactNumber(pOxide)}-${formatExactNumber(kOxide)} (N-P₂O₅-K₂O)`,
  }
}

/**
 * Scale oxid-form NPK so N matches the suggested phase label (display only).
 * Makes "dein Rezept" digit-comparable with "vorgeschlagenes NPK".
 */
export function normalizeOxidNpkToTargetN(
  oxidN: number,
  oxidP: number,
  oxidK: number,
  targetN: number,
): { n: number; p: number; k: number } {
  if (!(oxidN > 0) || !(targetN > 0) || !Number.isFinite(oxidN) || !Number.isFinite(targetN)) {
    return { n: oxidN, p: oxidP, k: oxidK }
  }
  const factor = targetN / oxidN
  return {
    n: targetN,
    p: oxidP * factor,
    k: oxidK * factor,
  }
}

/** @deprecated prefer formatOxidNpkRatio — kept for older tests */
export function formatElementalNpkRatio(n: number, p: number, k: number): {
  display: string
  title: string
} {
  return {
    display: `${Math.round(n)}–${Math.round(p)}–${Math.round(k)}`,
    title: `${formatExactNumber(n)}–${formatExactNumber(p)}–${formatExactNumber(k)}`,
  }
}

function stockBreakdownTitle(
  partA: StockMixRecipe | null | undefined,
  partB: StockMixRecipe | null | undefined,
): string | null {
  const parts: string[] = []
  for (const [label, recipe] of [
    ['Stock A', partA],
    ['Stock B', partB],
  ] as const) {
    const el = readStockElementGPerL(recipe)
    if (Object.keys(el).length === 0) continue
    const bits = MACRO_KEYS.filter((k) => el[k] != null).map(
      (k) => `${MACRO_LABELS[k]} ${formatExactNumber(el[k]!)}`,
    )
    if (bits.length) parts.push(`${label} (g/L): ${bits.join(' · ')}`)
  }
  return parts.length ? parts.join('\n') : null
}

export interface NutrientAmountDisplay {
  key: MacroElementKey
  label: string
  mgPerL: number
  display: string
  title: string
}

export interface WeekGridCellModel {
  phaseLabel: string
  /** Legacy short lines (tests / unresolved fallback). */
  lines: string[]
  /** complete | incomplete | unresolved */
  status: 'complete' | 'incomplete' | 'unresolved'
  /** Suggested phase NPK (oxid), e.g. "8-6-12". */
  suggestedNpkDisplay: string | null
  /**
   * Recipe NPK in oxid form, normalized to the same N as suggestedNpkDisplay
   * (display-only scale; mg/L profile unchanged).
   */
  npkRatioDisplay: string | null
  npkRatioTitle: string | null
  /** Macro nutrients of finished solution at stated dose (mg/L). */
  macros: NutrientAmountDisplay[]
  /** Compact traces cue; detail in tracesTitle. */
  tracesLabel: string | null
  tracesTitle: string | null
  doseA: string | null
  doseB: string | null
  /** Action footer, e.g. "So mischst du es: 4 ml A + 4 ml B je L". */
  doseLine: string | null
  /** Optional A/B g/L breakdown for tooltip only. */
  stockDetailTitle: string | null
  warnings: string[]
  message: string | null
}

export function buildWeekGridCell(input: {
  phaseKey: string | null
  fallbackLabel?: string | null
  partA?: StockMixRecipe | null
  partB?: StockMixRecipe | null
  resolved?: boolean
}): WeekGridCellModel {
  const phaseLabel = phaseDisplayLabel(input.phaseKey, input.fallbackLabel)
  const suggestedNpkDisplay = phaseOxidLabel(input.phaseKey)
  if (!input.resolved || (!input.partA && !input.partB)) {
    return {
      phaseLabel,
      lines: ['keine Rezeptur hinterlegt'],
      status: 'unresolved',
      suggestedNpkDisplay,
      npkRatioDisplay: null,
      npkRatioTitle: null,
      macros: [],
      tracesLabel: null,
      tracesTitle: null,
      doseA: null,
      doseB: null,
      doseLine: null,
      stockDetailTitle: null,
      warnings: [],
      message: 'keine Rezeptur hinterlegt',
    }
  }

  const { mgPerL, doseA, doseB, hasElements } = combineSolutionMgPerL(
    input.partA,
    input.partB,
  )

  const missing = new Set<string>()
  for (const r of [input.partA, input.partB]) {
    if (!r) continue
    if (r.npk_status === 'incomplete') {
      for (const name of r.npk_missing_salts ?? []) {
        if (typeof name === 'string' && name.trim()) missing.add(name.trim())
      }
    }
  }
  const incomplete = missing.size > 0
    || input.partA?.npk_status === 'incomplete'
    || input.partB?.npk_status === 'incomplete'

  const doseADisplay = formatMl(doseA > 0 ? doseA : null)
  const doseBDisplay = formatMl(doseB > 0 ? doseB : null)
  const doseLine =
    doseADisplay != null || doseBDisplay != null
      ? `So mischst du es: ${doseADisplay ?? '—'} ml A + ${doseBDisplay ?? '—'} ml B je L`
      : null

  const warnings: string[] = []
  if (incomplete) {
    const miss = [...missing].join(', ')
    warnings.push(miss ? `unvollständig (${miss})` : 'unvollständig')
  }

  if (!hasElements) {
    const lines = ['NPK noch nicht berechnet']
    if (doseLine) lines.push(doseLine)
    lines.push(...warnings)
    return {
      phaseLabel,
      lines,
      status: incomplete ? 'incomplete' : 'complete',
      suggestedNpkDisplay,
      npkRatioDisplay: null,
      npkRatioTitle: null,
      macros: [],
      tracesLabel: null,
      tracesTitle: null,
      doseA: doseADisplay,
      doseB: doseBDisplay,
      doseLine,
      stockDetailTitle: null,
      warnings,
      message: 'NPK noch nicht berechnet',
    }
  }

  const ratioParts = elementalNpkRatioParts(mgPerL, doseA, doseB)
  const oxidParts = elementalPartsToOxidNpk(ratioParts.n, ratioParts.p, ratioParts.k)
  const suggestedParsed = suggestedNpkDisplay
    ? parseNpkRatio(suggestedNpkDisplay)
    : null
  const normalizedOxid = suggestedParsed
    ? normalizeOxidNpkToTargetN(
      oxidParts.n,
      oxidParts.p,
      oxidParts.k,
      suggestedParsed.n,
    )
    : oxidParts
  const ratio = formatOxidNpkRatio(
    normalizedOxid.n,
    normalizedOxid.p,
    normalizedOxid.k,
  )

  const macros: NutrientAmountDisplay[] = MACRO_KEYS.map((key) => {
    const mg = mgPerL[key] ?? 0
    return {
      key,
      label: MACRO_LABELS[key],
      mgPerL: mg,
      display: formatMgPerLDisplay(mg),
      title: `${formatExactNumber(mg)} mg/L`,
    }
  })

  const traceBits: string[] = []
  for (const key of TRACE_KEYS) {
    const mg = mgPerL[key] ?? 0
    if (mg > 0) {
      traceBits.push(`${TRACE_LABELS[key]} ${formatExactNumber(mg)} mg/L`)
    }
  }

  const lines: string[] = [
    ...macros.map((m) => `${m.label} ${m.display} mg/L`),
  ]
  if (traceBits.length) lines.push(`+ Spurenelemente (${traceBits.join(', ')})`)
  if (doseLine) lines.push(doseLine)
  lines.push(...warnings)

  return {
    phaseLabel,
    lines,
    status: incomplete ? 'incomplete' : 'complete',
    suggestedNpkDisplay,
    npkRatioDisplay: ratio.display,
    npkRatioTitle: ratio.title,
    macros,
    tracesLabel: traceBits.length ? '+ Spurenelemente' : null,
    tracesTitle: traceBits.length ? traceBits.join(' · ') : null,
    doseA: doseADisplay,
    doseB: doseBDisplay,
    doseLine,
    stockDetailTitle: stockBreakdownTitle(input.partA, input.partB),
    warnings,
    message: null,
  }
}
