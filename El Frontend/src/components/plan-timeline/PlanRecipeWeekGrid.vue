<script setup lang="ts">
/**
 * Recipe grid — tabular view of nutrient plan staffeln (AUT-1235 / AUT-1420/1421).
 *
 * Columns = echte EC/pH-Plansegmente (Zeitraum + Ziele + phase_ref), nicht Kalenderwochen.
 * Zellen: erreichte Nährstoffprofil der fertigen Lösung (A+B × Dosis → mg/L, elementar).
 */

import { computed, ref, watch } from 'vue'
import { stockMixRecipesApi, type StockMixPhaseResolve } from '@/api/stockMixRecipes'
import type { PlanSegment } from '@/types/planSegment'
import type { PlanTimelineWindow } from '@/components/plan-timeline/planTimelineTracks'
import {
  buildRecipeGridColumns,
  buildWeekGridCell,
  formatTargetGoals,
  phaseKeyFromSegment,
  type GoalDisplayLine,
  type RecipeGridColumn,
  type WeekGridCellModel,
} from '@/components/plan-timeline/recipeWeekGridDisplay'
import { createLogger } from '@/utils/logger'

const logger = createLogger('PlanRecipeWeekGrid')

interface Props {
  segments: PlanSegment[]
  /** Optional clip; omit/null = alle Staffeln der Zone (wie EC/pH-Editor). */
  window?: PlanTimelineWindow | null
  zoneId?: string | null
}

const props = defineProps<Props>()

const columns = computed((): RecipeGridColumn[] => {
  if (!props.zoneId) return []
  return buildRecipeGridColumns(
    props.segments,
    props.zoneId,
    props.window ?? null,
  )
})

const resolveCache = ref<Record<string, StockMixPhaseResolve>>({})
const loadingResolve = ref(false)
let resolveSeq = 0

/** Stable signature of phases in columns — avoids deep-watch refetch storms. */
const phaseKeysSignature = computed((): string => {
  const phases = new Set<string>()
  for (const col of columns.value) {
    const key = col.phaseKey ?? phaseKeyFromSegment(col.phaseSource)
    if (key) phases.add(key)
  }
  return [...phases].sort().join('\0')
})

async function refreshResolves(): Promise<void> {
  const phases = phaseKeysSignature.value
    ? phaseKeysSignature.value.split('\0').filter(Boolean)
    : []
  if (phases.length === 0) {
    resolveCache.value = {}
    return
  }
  const missing = phases.filter((phase) => !(phase in resolveCache.value))
  if (missing.length === 0) return

  const seq = ++resolveSeq
  loadingResolve.value = true
  const next: Record<string, StockMixPhaseResolve> = { ...resolveCache.value }
  try {
    await Promise.all(
      missing.map(async (phase) => {
        try {
          next[phase] = await stockMixRecipesApi.resolvePhase(phase)
        } catch (err) {
          logger.warn('resolve-phase failed', { phase, err })
          next[phase] = {
            nutrient_phase: phase,
            part_a: null,
            part_b: null,
            resolved: false,
            detail: 'keine Rezeptur hinterlegt',
          }
        }
      }),
    )
    if (seq === resolveSeq) {
      resolveCache.value = next
    }
  } finally {
    if (seq === resolveSeq) {
      loadingResolve.value = false
    }
  }
}

watch(
  phaseKeysSignature,
  () => {
    void refreshResolves()
  },
  { immediate: true },
)

const cellModels = computed((): Record<string, WeekGridCellModel> => {
  const out: Record<string, WeekGridCellModel> = {}
  for (const col of columns.value) {
    const phaseKey = col.phaseKey ?? phaseKeyFromSegment(col.phaseSource)
    const resolved = phaseKey ? resolveCache.value[phaseKey] : undefined
    out[col.key] = buildWeekGridCell({
      phaseKey,
      fallbackLabel: col.phaseSource.recipe_ref || col.phaseSource.phase_ref || col.title,
      partA: resolved?.part_a ?? null,
      partB: resolved?.part_b ?? null,
      resolved: resolved?.resolved ?? false,
    })
  }
  return out
})

const goalLines = computed((): Record<string, GoalDisplayLine[]> => {
  const out: Record<string, GoalDisplayLine[]> = {}
  for (const col of columns.value) {
    out[col.key] = formatTargetGoals(col)
  }
  return out
})

const isEmptyScaffold = computed(() => columns.value.length === 0)
</script>

<template>
  <section class="recipe-grid glass-panel" aria-label="Rezeptur nach Plansegmenten">
    <header class="recipe-grid__header">
      <h2 class="recipe-grid__title">Rezeptur nach Plansegmenten</h2>
      <p class="recipe-grid__hint">
        Spalten = deine EC/pH-Ziele mit Zeitraum und Nährstoffphase (dieselbe Staffelung wie oben).
        Nährstoffprofil theoretisch aus der Rezeptur, nicht gemessen — bei angegebener Dosis.
      </p>
    </header>

    <p v-if="isEmptyScaffold" class="recipe-grid__empty">
      Noch keine EC/pH-Plansegmente — lege oben einen Zeitraum mit Zielen und Phase an.
    </p>

    <div v-else class="recipe-grid__table-wrap">
      <table class="recipe-grid__table">
        <thead>
          <tr>
            <th scope="col">Zeitraum</th>
            <th
              v-for="col in columns"
              :key="col.key"
              scope="col"
              class="recipe-grid__col-head"
              :title="col.rangeTitle"
            >
              <div class="recipe-grid__col-title">{{ col.title }}</div>
              <div class="recipe-grid__col-range">{{ col.rangeLabel }}</div>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">Ziele</th>
            <td
              v-for="col in columns"
              :key="`goals-${col.key}`"
              class="recipe-grid__cell recipe-grid__cell--goals"
            >
              <div
                v-for="(goal, idx) in goalLines[col.key]"
                :key="`${col.key}-g-${idx}`"
                class="recipe-grid__goal"
              >
                <span class="recipe-grid__label">{{ goal.label }}</span>
                <span
                  v-if="goal.valueDisplay != null"
                  class="recipe-grid__num"
                  :title="goal.valueTitle ?? undefined"
                >{{ goal.valueDisplay }}</span>
                <span v-else class="recipe-grid__num recipe-grid__num--empty">—</span>
                <span v-if="goal.unit" class="recipe-grid__unit">{{ goal.unit }}</span>
              </div>
            </td>
          </tr>
          <tr>
            <th scope="row">Rezeptur</th>
            <td
              v-for="col in columns"
              :key="`recipe-${col.key}`"
              class="recipe-grid__cell recipe-grid__cell--recipe"
              :data-status="cellModels[col.key]?.status"
            >
              <template v-if="!cellModels[col.key] || cellModels[col.key].phaseLabel === '—'">
                —
              </template>
              <div
                v-else
                class="recipe-grid__recipe"
                :class="{
                  'recipe-grid__recipe--warn': cellModels[col.key].status === 'incomplete',
                  'recipe-grid__recipe--muted': cellModels[col.key].status === 'unresolved',
                }"
                :title="cellModels[col.key].stockDetailTitle ?? undefined"
              >
                <template v-if="cellModels[col.key].macros.length">
                  <div
                    v-if="cellModels[col.key].suggestedNpkDisplay || cellModels[col.key].npkRatioDisplay"
                    class="recipe-grid__ratio"
                    :title="cellModels[col.key].npkRatioTitle
                      ? `Dein Rezept auf dieselbe N-Skala wie der Vorschlag normiert (Oxid N‑P₂O₅‑K₂O): ${cellModels[col.key].npkRatioTitle}`
                      : 'Vorgeschlagenes NPK in Oxidform (N‑P₂O₅‑K₂O)'"
                  >
                    <template v-if="cellModels[col.key].suggestedNpkDisplay">
                      <span class="recipe-grid__label">vorgeschlagenes NPK</span>
                      <span class="recipe-grid__num recipe-grid__num--ratio">
                        {{ cellModels[col.key].suggestedNpkDisplay }}
                      </span>
                    </template>
                    <span
                      v-if="cellModels[col.key].suggestedNpkDisplay && cellModels[col.key].npkRatioDisplay"
                      class="recipe-grid__ratio-sep"
                      aria-hidden="true"
                    >·</span>
                    <template v-if="cellModels[col.key].npkRatioDisplay">
                      <span class="recipe-grid__label">dein Rezept</span>
                      <span class="recipe-grid__num recipe-grid__num--ratio">
                        {{ cellModels[col.key].npkRatioDisplay }}
                      </span>
                    </template>
                  </div>

                  <div
                    class="recipe-grid__profile"
                    aria-label="Erreichtes Nährstoffprofil der fertigen Lösung"
                  >
                    <span class="recipe-grid__profile-caption">Profil (elementar, mg/L)</span>
                    <div
                      v-for="macro in cellModels[col.key].macros"
                      :key="macro.key"
                      class="recipe-grid__profile-row"
                    >
                      <span class="recipe-grid__label">{{ macro.label }}</span>
                      <span
                        class="recipe-grid__num"
                        :title="macro.title"
                      >{{ macro.display }}</span>
                    </div>
                    <span class="recipe-grid__unit recipe-grid__unit--block">mg/L</span>
                  </div>

                  <div
                    v-if="cellModels[col.key].tracesLabel"
                    class="recipe-grid__traces"
                    :title="cellModels[col.key].tracesTitle ?? undefined"
                  >
                    {{ cellModels[col.key].tracesLabel }}
                  </div>
                </template>

                <p
                  v-else-if="cellModels[col.key].message"
                  class="recipe-grid__message"
                >{{ cellModels[col.key].message }}</p>

                <div
                  v-if="cellModels[col.key].doseLine"
                  class="recipe-grid__dose"
                >
                  So mischst du es:
                  <span class="recipe-grid__num">{{ cellModels[col.key].doseA ?? '—' }}</span>
                  <span class="recipe-grid__unit">ml A</span>
                  +
                  <span class="recipe-grid__num">{{ cellModels[col.key].doseB ?? '—' }}</span>
                  <span class="recipe-grid__unit">ml B je L</span>
                </div>

                <p
                  v-for="(warn, wIdx) in cellModels[col.key].warnings"
                  :key="`${col.key}-w-${wIdx}`"
                  class="recipe-grid__warn"
                >{{ warn }}</p>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="loadingResolve" class="recipe-grid__hint" aria-live="polite">
      Rezepturen werden aufgelöst…
    </p>
  </section>
</template>

<style scoped>
.recipe-grid {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  border-radius: var(--radius-md);
  max-width: 100%;
  min-width: 0;
}

.recipe-grid__header {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.recipe-grid__title {
  margin: 0;
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text-primary);
}

.recipe-grid__hint {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.recipe-grid__empty {
  padding: var(--space-4);
  text-align: center;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-md);
}

.recipe-grid__table-wrap {
  overflow-x: auto;
  max-width: 100%;
  -webkit-overflow-scrolling: touch;
}

.recipe-grid__table {
  width: max-content;
  min-width: 100%;
  border-collapse: collapse;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.recipe-grid__table th,
.recipe-grid__table td {
  padding: var(--space-3);
  border: 1px solid var(--glass-border);
  text-align: left;
  vertical-align: top;
}

.recipe-grid__table th {
  color: var(--color-text-muted);
  font-weight: 500;
  background: var(--color-bg-tertiary);
}

.recipe-grid__col-head {
  white-space: normal;
  min-width: 9.5rem;
  text-align: center;
}

.recipe-grid__col-title {
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: var(--space-1);
}

.recipe-grid__col-range {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-weight: 400;
}

.recipe-grid__cell {
  min-width: 9.5rem;
  max-width: 14rem;
  white-space: normal;
}

.recipe-grid__cell--goals {
  text-align: left;
}

.recipe-grid__cell--recipe {
  padding: var(--space-3);
}

.recipe-grid__goal {
  display: flex;
  flex-wrap: nowrap;
  align-items: baseline;
  gap: var(--space-1);
  line-height: 1.5;
  white-space: nowrap;
}

.recipe-grid__goal + .recipe-grid__goal {
  margin-top: var(--space-1);
}

.recipe-grid__recipe {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--space-2);
  line-height: 1.5;
}

.recipe-grid__ratio {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-1) var(--space-2);
  line-height: 1.5;
}

.recipe-grid__ratio-sep {
  color: var(--color-text-muted);
  margin: 0 0.15rem;
}

.recipe-grid__num--ratio {
  font-size: var(--text-sm);
  letter-spacing: 0.02em;
}

.recipe-grid__profile {
  display: grid;
  grid-template-columns: auto minmax(2.5rem, 1fr);
  column-gap: var(--space-2);
  row-gap: var(--space-1);
  align-items: baseline;
}

.recipe-grid__profile-caption {
  grid-column: 1 / -1;
  font-size: var(--text-xs);
  font-weight: 400;
  color: var(--color-text-muted);
  margin-bottom: 0.1rem;
}

.recipe-grid__profile-row {
  display: contents;
}

.recipe-grid__profile-row .recipe-grid__label {
  text-align: left;
}

.recipe-grid__profile-row .recipe-grid__num {
  text-align: right;
}

.recipe-grid__traces {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  line-height: 1.5;
  cursor: help;
}

.recipe-grid__label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.recipe-grid__num {
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum' 1;
  color: var(--color-text-primary);
  font-weight: 600;
  white-space: nowrap;
  text-align: right;
}

.recipe-grid__num--empty {
  font-weight: 400;
  color: var(--color-text-muted);
}

.recipe-grid__unit {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-weight: 400;
  white-space: nowrap;
}

.recipe-grid__unit--block {
  grid-column: 1 / -1;
  justify-self: end;
  margin-top: 0.1rem;
}

.recipe-grid__dose {
  margin: 0;
  padding-top: var(--space-1);
  border-top: 1px solid var(--glass-border);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  line-height: 1.5;
  white-space: normal;
}

.recipe-grid__dose .recipe-grid__num {
  font-weight: 500;
  color: var(--color-text-secondary);
}

.recipe-grid__message {
  margin: 0;
  color: var(--color-text-muted);
  line-height: 1.5;
}

.recipe-grid__warn {
  margin: 0;
  color: var(--color-warning);
  line-height: 1.5;
}

.recipe-grid__recipe--muted .recipe-grid__message {
  color: var(--color-text-muted);
}
</style>
