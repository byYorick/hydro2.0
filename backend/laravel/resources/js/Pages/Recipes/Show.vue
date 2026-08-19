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
          v-if="canEditRecipes"
          size="sm"
          variant="secondary"
          :disabled="copying"
          data-testid="recipe-duplicate-button"
          @click="duplicateRecipe"
        >
          {{ copying ? 'Создание копии…' : 'Создать копию' }}
        </Button>
        <Link href="/launch">
          <Button
            size="sm"
            variant="secondary"
          >
            Применить к зоне
          </Button>
        </Link>
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
            <div class="text-xs text-[color:var(--text-dim)] mt-1">
              <span v-if="p.lighting_photoperiod_hours || p.targets?.light_hours">
                Свет {{ p.lighting_photoperiod_hours ?? p.targets?.light_hours }} ч
              </span>
              <span v-if="p.irrigation_interval_sec || p.targets?.irrigation_interval_sec">
                · Полив {{ p.irrigation_interval_sec ?? p.targets?.irrigation_interval_sec }} сек
              </span>
            </div>

            <details
              v-if="hasNutrition(p)"
              class="text-xs text-[color:var(--text-dim)] mt-1"
              data-testid="recipe-nutrition-details"
            >
              <summary class="cursor-pointer text-[color:var(--text-muted)]">
                Питание и PID
              </summary>
              <div class="mt-1 space-y-0.5">
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
            </details>
          </li>
        </ul>
      </Card>
      <Card>
        <div class="text-sm font-semibold mb-2">
          Сводка по фазам
        </div>
        <div class="space-y-2 text-sm text-[color:var(--text-muted)]">
          <div>
            Температура: {{ summary.temperature }}
          </div>
          <div>
            Влажность: {{ summary.humidity }}
          </div>
          <div>
            Свет: {{ summary.lighting }}
          </div>
          <div>
            Полив: {{ summary.irrigation }}
          </div>
        </div>
      </Card>
      <Card>
        <div class="text-sm font-semibold mb-2">
          Используется в зонах
        </div>
        <div
          v-if="activeUsageLoading"
          class="text-sm text-[color:var(--text-dim)]"
        >
          Загрузка…
        </div>
        <ul
          v-else-if="activeUsage && activeUsage.count > 0"
          class="text-sm text-[color:var(--text-muted)] space-y-1"
          data-testid="recipe-used-in-zones"
        >
          <li
            v-for="item in activeUsage.active_cycles"
            :key="item.cycle_id"
          >
            <Link
              :href="`/zones/${item.zone_id}`"
              class="text-[color:var(--accent-cyan)] hover:underline"
            >
              {{ item.zone_name || `Зона #${item.zone_id}` }}
            </Link>
          </li>
        </ul>
        <div
          v-else
          class="text-sm text-[color:var(--text-dim)]"
        >
          Нет активных зон
        </div>
      </Card>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Link, router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import { usePageProps } from '@/composables/usePageProps'
import { useRole } from '@/composables/useRole'
import { useToast } from '@/composables/useToast'
import { api } from '@/services/api'
import type { RecipeActiveUsage } from '@/services/api/recipes'
import { extractHumanErrorMessage } from '@/utils/errorMessage'
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
const { canEditRecipes } = useRole()
const { showToast } = useToast()
const copying = ref(false)
const activeUsage = ref<RecipeActiveUsage | null>(null)
const activeUsageLoading = ref(false)

async function loadActiveUsage(): Promise<void> {
  const recipeId = recipe.value.id
  if (!recipeId) {
    activeUsage.value = null
    return
  }
  activeUsageLoading.value = true
  try {
    activeUsage.value = await api.recipes.getActiveUsage(recipeId)
  } catch {
    activeUsage.value = null
  } finally {
    activeUsageLoading.value = false
  }
}

onMounted(() => {
  void loadActiveUsage()
})

function resolveSourcePlantId(): number | null {
  const plants = recipe.value.plants
  const firstPlantId = plants?.[0]?.id
  return typeof firstPlantId === 'number' ? firstPlantId : null
}

async function duplicateRecipe(): Promise<void> {
  if (copying.value || !canEditRecipes.value) {
    return
  }

  const source = recipe.value
  const publishedRevisionId = source.latest_published_revision_id
  if (typeof publishedRevisionId !== 'number') {
    showToast('Нет опубликованной ревизии — копию создать нельзя', 'error')
    return
  }

  const plantId = resolveSourcePlantId()
  if (!plantId) {
    showToast('У рецепта нет культуры — копию создать нельзя', 'error')
    return
  }

  copying.value = true
  try {
    const created = await api.recipes.create({
      name: `${source.name} (копия)`,
      description: source.description?.trim() ? source.description : null,
      plant_id: plantId,
    })
    const createdId = typeof created?.id === 'number' ? created.id : null
    if (!createdId) {
      throw new Error('Recipe ID missing')
    }

    await api.recipes.createRevision(createdId, {
      clone_from_revision_id: publishedRevisionId,
      description: `Копия рецепта «${source.name}»`,
    })

    router.visit(`/recipes/${createdId}/edit`)
  } catch (error) {
    showToast(extractHumanErrorMessage(error, 'Не удалось создать копию рецепта'), 'error')
  } finally {
    copying.value = false
  }
}

const sortedPhases = computed<RecipePhaseWithNutrition[]>(() => {
  const phases = (recipe.value.phases || []) as RecipePhaseWithNutrition[]
  return [...phases].sort((a, b) => (a.phase_index || 0) - (b.phase_index || 0))
})

const summary = computed(() => {
  const phases = sortedPhases.value
  const formatRange = (values: Array<number | null | undefined>, suffix: string): string => {
    const normalized = values
      .map((value) => (value === null || value === undefined ? null : Number(value)))
      .filter((value): value is number => Number.isFinite(value))
    if (normalized.length === 0) {
      return '-'
    }
    const min = Math.min(...normalized)
    const max = Math.max(...normalized)
    return min === max ? `${min}${suffix}` : `${min}–${max}${suffix}`
  }

  return {
    temperature: formatRange(phases.map((phase) => phase.temp_air_target ?? phase.targets?.temp_air), '°C'),
    humidity: formatRange(phases.map((phase) => phase.humidity_target ?? phase.targets?.humidity_air), '%'),
    lighting: formatRange(phases.map((phase) => phase.lighting_photoperiod_hours ?? phase.targets?.light_hours), ' ч'),
    irrigation: formatRange(phases.map((phase) => phase.irrigation_interval_sec ?? phase.targets?.irrigation_interval_sec), ' сек'),
  }
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
