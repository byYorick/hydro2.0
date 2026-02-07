<template>
  <AppLayout>
    <div class="flex items-center justify-between mb-3">
      <div>
        <div class="text-lg font-semibold">
          {{ recipe.name }}
        </div>
        <div class="text-xs text-[color:var(--text-muted)]">
          {{ recipe.description || 'Без описания' }} · Фаз: {{ recipe.phases?.length || 0 }}
        </div>
      </div>
      <div class="flex gap-2">
        <Button
          size="sm"
          variant="secondary"
        >
          Создать копию
        </Button>
        <Link :href="`/recipes/${recipe.id}/edit`">
          <Button size="sm">
            Редактировать
          </Button>
        </Link>
      </div>
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-3 gap-3">
      <Card class="xl:col-span-2">
        <div class="text-sm font-semibold mb-2">
          Фазы
        </div>
        <ul class="text-sm text-[color:var(--text-muted)] space-y-2">
          <li
            v-for="(p, i) in sortedPhases"
            :key="p.id || i"
            class="pb-2 border-b last:border-b-0 border-[color:var(--border-muted)]"
          >
            <div>
              {{ p.phase_index + 1 }}. {{ p.name }} —
              {{ formatDuration(p.duration_hours) }} —
              <span v-if="p.targets?.ph">pH {{ p.targets.ph.min || '-' }}–{{ p.targets.ph.max || '-' }}</span>
              <span v-if="p.targets?.ec">, EC {{ p.targets.ec.min || '-' }}–{{ p.targets.ec.max || '-' }}</span>
            </div>

            <div
              v-if="hasNutrition(p)"
              class="text-xs text-[color:var(--text-dim)] mt-1"
            >
              <div>
                Программа: {{ p.nutrient_program_code || '-' }}
              </div>
              <div>
                Режим: {{ p.nutrient_mode || 'ratio_ec_pid' }}
                <span v-if="p.nutrient_solution_volume_l">
                  · Объём: {{ formatNumber(p.nutrient_solution_volume_l) }} л
                </span>
              </div>
              <div>
                NPK: {{ formatNumber(p.nutrient_npk_ratio_pct) }}% / {{ formatNumber(p.nutrient_npk_dose_ml_l) }} мл/л / {{ resolveProductLabel(p.npk_product, p.nutrient_npk_product_id) }}
              </div>
              <div>
                Кальций: {{ formatNumber(p.nutrient_calcium_ratio_pct) }}% / {{ formatNumber(p.nutrient_calcium_dose_ml_l) }} мл/л / {{ resolveProductLabel(p.calcium_product, p.nutrient_calcium_product_id) }}
              </div>
              <div>
                Магний: {{ formatNumber(p.nutrient_magnesium_ratio_pct) }}% / {{ formatNumber(p.nutrient_magnesium_dose_ml_l) }} мл/л / {{ resolveProductLabel(p.magnesium_product, p.nutrient_magnesium_product_id) }}
              </div>
              <div>
                Микро: {{ formatNumber(p.nutrient_micro_ratio_pct) }}% / {{ formatNumber(p.nutrient_micro_dose_ml_l) }} мл/л / {{ resolveProductLabel(p.micro_product, p.nutrient_micro_product_id) }}
              </div>
              <div>
                Пауза доз: {{ formatNumber(p.nutrient_dose_delay_sec) }} сек, EC stop tolerance: {{ formatNumber(p.nutrient_ec_stop_tolerance) }}
              </div>
            </div>
          </li>
        </ul>
      </Card>
      <Card>
        <div class="text-sm font-semibold mb-2">
          Цели по умолчанию
        </div>
        <div class="text-sm text-[color:var(--text-muted)]">
          Температура: 22–24°C
        </div>
        <div class="text-sm text-[color:var(--text-muted)]">
          Влажность: 50–60%
        </div>
        <div class="text-sm text-[color:var(--text-muted)]">
          Свет: 16ч
        </div>
      </Card>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Link } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import { usePageProps } from '@/composables/usePageProps'
import type { Recipe, RecipePhase } from '@/types'

interface NutrientProductSummary {
  id: number
  manufacturer?: string
  name?: string
}

interface RecipePhaseWithNutrition extends RecipePhase {
  nutrient_program_code?: string | null
  nutrient_npk_ratio_pct?: number | string | null
  nutrient_calcium_ratio_pct?: number | string | null
  nutrient_magnesium_ratio_pct?: number | string | null
  nutrient_micro_ratio_pct?: number | string | null
  nutrient_npk_dose_ml_l?: number | string | null
  nutrient_calcium_dose_ml_l?: number | string | null
  nutrient_magnesium_dose_ml_l?: number | string | null
  nutrient_micro_dose_ml_l?: number | string | null
  nutrient_npk_product_id?: number | null
  nutrient_calcium_product_id?: number | null
  nutrient_magnesium_product_id?: number | null
  nutrient_micro_product_id?: number | null
  nutrient_dose_delay_sec?: number | null
  nutrient_ec_stop_tolerance?: number | string | null
  nutrient_solution_volume_l?: number | string | null
  npk_product?: NutrientProductSummary | null
  calcium_product?: NutrientProductSummary | null
  magnesium_product?: NutrientProductSummary | null
  micro_product?: NutrientProductSummary | null
}

interface PageProps {
  recipe?: Recipe
  [key: string]: any
}

const { recipe: recipeProp } = usePageProps<PageProps>(['recipe'])
const recipe = computed(() => (recipeProp.value || {}) as Recipe)

const sortedPhases = computed<RecipePhaseWithNutrition[]>(() => {
  const phases = (recipe.value.phases || []) as RecipePhaseWithNutrition[]
  return [...phases].sort((a, b) => (a.phase_index || 0) - (b.phase_index || 0))
})

function formatDuration(hours: number | null | undefined): string {
  if (!hours) return '-'
  if (hours < 24) return `${hours} ч`
  const days = Math.floor(hours / 24)
  const remainder = hours % 24
  if (remainder === 0) return `${days} дн`
  return `${days} дн ${remainder} ч`
}

function formatNumber(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === '') {
    return '-'
  }

  return String(value)
}

function resolveProductLabel(
  product: NutrientProductSummary | null | undefined,
  fallbackId: number | null | undefined,
): string {
  if (product?.manufacturer || product?.name) {
    return `${product?.manufacturer || '-'} · ${product?.name || '-'}`
  }

  if (fallbackId) {
    return `ID ${fallbackId}`
  }

  return '-'
}

function hasNutrition(phase: RecipePhaseWithNutrition): boolean {
  const hasValue = (value: unknown): boolean => value !== null && value !== undefined && value !== ''

  return Boolean(
    phase.nutrient_program_code
      || hasValue(phase.nutrient_npk_ratio_pct)
      || hasValue(phase.nutrient_calcium_ratio_pct)
      || hasValue(phase.nutrient_magnesium_ratio_pct)
      || hasValue(phase.nutrient_micro_ratio_pct)
      || hasValue(phase.nutrient_npk_dose_ml_l)
      || hasValue(phase.nutrient_calcium_dose_ml_l)
      || hasValue(phase.nutrient_magnesium_dose_ml_l)
      || hasValue(phase.nutrient_micro_dose_ml_l)
      || hasValue(phase.nutrient_npk_product_id)
      || hasValue(phase.nutrient_calcium_product_id)
      || hasValue(phase.nutrient_magnesium_product_id)
      || hasValue(phase.nutrient_micro_product_id)
      || hasValue(phase.nutrient_dose_delay_sec)
      || hasValue(phase.nutrient_ec_stop_tolerance)
      || hasValue(phase.nutrient_solution_volume_l)
  )
}
</script>
