<template>
  <AppLayout>
    <div class="flex items-center justify-between mb-3">
      <div>
        <h1 class="text-lg font-semibold">
          {{ recipe.name }}
        </h1>
        <div class="text-xs text-[color:var(--text-muted)]">
          {{ recipe.description || 'Без описания' }} · Фаз: {{ recipe.phases?.length || 0 }}
        </div>
        <div class="mt-1 flex items-center gap-3 text-xs">
          <span class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-dim)]">
            Справочники
          </span>
          <Link
            href="/plants"
            class="text-[color:var(--accent-cyan)] hover:underline"
          >
            Культуры
          </Link>
          <Link
            href="/nutrients"
            class="text-[color:var(--accent-cyan)] hover:underline"
          >
            Удобрения
          </Link>
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

    <div
      v-if="phaseVisuals.length === 0"
      class="rounded-xl border border-dashed border-[color:var(--border-muted)] px-4 py-8 text-center text-sm text-[color:var(--text-dim)]"
    >
      У рецепта пока нет фаз — добавьте их в редакторе.
    </div>

    <div
      v-else
      class="space-y-3"
    >
      <Card class="space-y-4">
        <RecipeSummaryStats
          :summary="summary"
          :crop-label="cropLabel"
          :status-label="statusLabel"
          :active-zones="activeZonesCount"
        />
        <RecipePhaseTimeline
          :phases="phaseVisuals"
          :active-key="activePhaseKey"
          @select="focusPhase"
        />
      </Card>

      <Card class="space-y-3">
        <div class="text-sm font-semibold">
          Профиль параметров по фазам
        </div>
        <RecipePhaseChartsPanel :phases="phaseVisuals" />
      </Card>

      <div class="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <div class="space-y-3 xl:col-span-2">
          <div class="text-sm font-semibold">
            Фазы
          </div>
          <RecipePhaseCard
            v-for="phase in phaseVisuals"
            :id="phaseElementId(phase.key)"
            :key="phase.key"
            :phase="phase"
            :highlighted="phase.key === activePhaseKey"
          />
        </div>

        <div class="space-y-3">
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

          <Card v-if="phaseModes.length > 0">
            <div class="text-sm font-semibold mb-2">
              Режимы фаз
            </div>
            <ul class="space-y-2 text-xs text-[color:var(--text-muted)]">
              <li
                v-for="mode in phaseModes"
                :key="`mode-${mode.key}`"
                class="border-b border-[color:var(--border-muted)] pb-2 last:border-b-0 last:pb-0"
              >
                <div class="text-[color:var(--text-primary)]">
                  {{ mode.title }}
                </div>
                <div
                  v-for="line in mode.lines"
                  :key="line"
                >
                  {{ line }}
                </div>
              </li>
            </ul>
          </Card>
        </div>
      </div>

      <Card class="space-y-2">
        <div class="text-sm font-semibold">
          Сводная таблица фаз
        </div>
        <RecipePhasesSummary :phases="sortedPhases" />
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
import RecipePhaseCard from '@/Components/Recipes/RecipePhaseCard.vue'
import RecipePhaseChartsPanel from '@/Components/Recipes/RecipePhaseChartsPanel.vue'
import RecipePhaseTimeline from '@/Components/Recipes/RecipePhaseTimeline.vue'
import RecipeSummaryStats from '@/Components/Recipes/RecipeSummaryStats.vue'
import RecipePhasesSummary from '@/Components/Launch/RecipePhasesSummary.vue'
import { usePageProps } from '@/composables/usePageProps'
import { useRole } from '@/composables/useRole'
import { useToast } from '@/composables/useToast'
import { api } from '@/services/api'
import type { RecipeActiveUsage } from '@/services/api/recipes'
import { extractHumanErrorMessage } from '@/utils/errorMessage'
import {
  buildRecipePhaseVisuals,
  irrigationModeLabel,
  irrigationSystemLabel,
  progressModelLabel,
  summarizeRecipePhases,
} from '@/utils/recipeVisualization'
import type { Recipe, RecipePhase } from '@/types'

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
const activePhaseKey = ref<string | null>(null)

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

const sortedPhases = computed<RecipePhase[]>(() => {
  const phases = recipe.value.phases || []
  return [...phases].sort((a, b) => (a.phase_index || 0) - (b.phase_index || 0))
})

const phaseVisuals = computed(() => buildRecipePhaseVisuals(sortedPhases.value))
const summary = computed(() => summarizeRecipePhases(phaseVisuals.value))

const cropLabel = computed(() => {
  const names = (recipe.value.plants ?? []).map((plant) => plant.name).filter(Boolean)
  return names.length > 0 ? names.join(', ') : null
})

const statusLabel = computed(() =>
  recipe.value.latest_published_revision_id ? 'Опубликован' : 'Черновик',
)

const activeZonesCount = computed(() =>
  typeof recipe.value.active_zones_count === 'number' ? recipe.value.active_zones_count : null,
)

const phaseModes = computed(() =>
  phaseVisuals.value
    .map((phase) => {
      const lines: string[] = []
      if (phase.irrigation.mode || phase.irrigation.systemType) {
        lines.push(
          `${irrigationModeLabel(phase.irrigation.mode)} · ${irrigationSystemLabel(phase.irrigation.systemType)}`,
        )
      }
      if (phase.progressModel) {
        lines.push(`Переход: ${progressModelLabel(phase.progressModel)}`)
      }

      return {
        key: phase.key,
        title: `${phase.position + 1}. ${phase.name}`,
        lines,
      }
    })
    .filter((mode) => mode.lines.length > 0),
)

function phaseElementId(key: string): string {
  return `recipe-phase-${key}`
}

function focusPhase(key: string): void {
  activePhaseKey.value = key
  const element = typeof document === 'undefined' ? null : document.getElementById(phaseElementId(key))
  if (element && typeof element.scrollIntoView === 'function') {
    element.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}
</script>
