<template>
  <AppLayout>
    <div class="recipe-workbench space-y-5">
      <header class="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div class="space-y-1.5">
          <p class="text-[11px] uppercase tracking-[.2em] text-[color:var(--text-muted)]">
            Агрономия / рецепты
          </p>
          <h1 class="text-2xl font-semibold">
            {{ form.id ? 'Редактировать рецепт' : 'Создать рецепт' }}
          </h1>
          <p class="text-sm text-[color:var(--text-muted)]">
            Черновик, публикация и изменение активного цикла — отдельные действия.
          </p>
        </div>
        <Link
          v-if="form.id"
          :href="`/recipes/${form.id}`"
          class="btn btn-outline min-h-11 text-sm"
        >
          К рецепту
        </Link>
      </header>
      <div class="recipe-workbench-grid">
        <Card class="min-w-0">
          <fieldset
            :disabled="processing"
            class="min-w-0"
          >
            <RecipeEditor
              v-model:form="form"
              :plants="plants"
              :plants-loading="plantsLoading"
              :npk-products="npkProducts"
              :calcium-products="calciumProducts"
              :magnesium-products="magnesiumProducts"
              :micro-products="microProducts"
              :substrates="substrates"
              single-phase
              save-label="Сохранить черновик"
              @add-phase="addPhase"
              @remove-phase="removePhase"
              @plant-created="onPlantCreated"
              @product-created="onProductCreated"
              @substrate-created="onSubstrateCreated"
              @save="onSave"
            />
          </fieldset>
        </Card>
        <aside class="surface-card h-fit space-y-5 p-4 sm:p-5">
          <div>
            <h2 class="font-semibold">
              Ревизия и изменения
            </h2><p class="mt-1 text-xs text-[color:var(--text-muted)]">
              {{ savedDraft ? 'Черновик сохранён' : form.draft_revision_id ? 'Редактируется черновик' : 'Будет создана новая ревизия' }}
            </p>
          </div>
          <div>
            <p class="text-xs text-[color:var(--text-muted)]">
              Изменения с открытия редактора
            </p>
            <ul
              v-if="changes.length"
              class="mt-2 space-y-2 text-sm"
            >
              <li
                v-for="change in changes"
                :key="change"
              >
                {{ change }}
              </li>
            </ul>
            <p
              v-else
              class="mt-2 text-sm"
            >
              Изменений пока нет
            </p>
          </div>
          <details
            v-if="parameterChanges.length"
            open
            class="text-xs"
          >
            <summary class="cursor-pointer font-semibold">
              Сравнение параметров по порядку фаз
            </summary>
            <dl class="mt-3 space-y-3">
              <div
                v-for="change in parameterChanges"
                :key="change.label"
              >
                <dt class="text-[color:var(--text-muted)]">
                  {{ change.label }}
                </dt>
                <dd class="mt-1 font-medium tabular-nums">
                  <del class="text-[color:var(--text-muted)]">{{ change.before }}</del> → {{ change.after }}
                </dd>
              </div>
            </dl>
          </details>
          <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3 text-xs leading-relaxed">
            <strong class="text-[color:var(--text-primary)]">Область применения</strong>
            <p class="mt-2">
              Публикация сделает ревизию доступной для новых запусков и явного переключения. Активные циклы продолжат работать на своих ревизиях.
            </p>
          </div>
          <div
            v-if="activeUsage && activeUsage.count > 0"
            data-testid="recipe-active-usage-warning"
            class="space-y-2 text-xs text-[color:var(--text-muted)]"
          >
            <strong>Рецепт используется: {{ activeUsage.count }}</strong>
            <ul class="space-y-1">
              <li
                v-for="item in activeUsage.active_cycles"
                :key="item.cycle_id"
              >
                {{ item.zone_name || `Зона #${item.zone_id}` }} · ревизия {{ item.revision_number ?? '—' }}
              </li>
            </ul>
          </div>
          <p
            v-if="usageError"
            class="text-xs text-[color:var(--status-warning)]"
          >
            Список активных циклов недоступен. Публикация не переключает их ревизии.
          </p>
          <div class="flex flex-col gap-2">
            <Button
              :disabled="processing"
              variant="secondary"
              data-testid="save-recipe-button"
              @click="onSave"
            >
              {{ processing ? 'Сохранение…' : 'Сохранить черновик' }}
            </Button>
            <Button
              :disabled="processing"
              @click="reviewPublication"
            >
              Проверить и опубликовать
            </Button>
          </div>
        </aside>
      </div>
      <Modal
        :open="publicationOpen"
        title="Опубликовать ревизию рецепта?"
        size="large"
        hide-default-cancel
        @close="closePublication"
      >
        <p class="mb-4 text-sm">
          {{ form.name }}. Будут опубликованы все {{ form.phases.length }} фаз(ы) черновика. Активные циклы не переключатся.
        </p>
        <div class="space-y-3">
          <div
            v-for="phase in form.phases"
            :key="phase.phase_index"
            class="rounded-lg border border-[color:var(--border-muted)] p-3"
          >
            <strong class="text-[color:var(--text-primary)]">{{ phase.name }}</strong>
            <p class="mt-1 text-xs">
              {{ phase.duration_hours }} ч · pH {{ phase.ph_min }}–{{ phase.ph_max }} (цель {{ phase.ph_target }}) · EC {{ phase.ec_min }}–{{ phase.ec_max }} мСм/см (цель {{ phase.ec_target }})
            </p>
            <p class="mt-1 text-xs">
              Свет {{ phase.lighting_photoperiod_hours ?? '—' }} ч · полив {{ phase.irrigation_interval_sec ?? '—' }} / {{ phase.irrigation_duration_sec ?? '—' }} с
            </p>
          </div>
        </div>
        <template #footer>
          <Button
            :disabled="processing"
            variant="secondary"
            @click="closePublication"
          >
            Вернуться к редактированию
          </Button><Button
            :disabled="processing"
            @click="publish"
          >
            {{ processing ? 'Публикация…' : 'Опубликовать ревизию' }}
          </Button>
        </template>
      </Modal>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Link, router, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Modal from '@/Components/Modal.vue'
import { buildRecipePhasePayload, createRecipeEditorFormState } from '@/composables/recipeEditorShared'
import type { RecipePhaseFormState } from '@/composables/recipeEditorShared'
import Button from '@/Components/Button.vue'
import RecipeEditor from '@/Components/RecipeEditor.vue'
import { useRecipeEditor } from '@/composables/useRecipeEditor'
import { api } from '@/services/api'
import type { RecipeActiveUsage } from '@/services/api/recipes'
import type { Recipe, NutrientProduct } from '@/types'
import type { Substrate } from '@/services/api/substrates'

const page = usePage<{ recipe?: Recipe }>()
const recipe = page.props.recipe ?? null

const {
  form,
  processing,
  plants,
  plantsLoading,
  nutrientProducts,
  npkProducts,
  calciumProducts,
  magnesiumProducts,
  microProducts,
  substrates,
  loadPlants,
  loadNutrientProducts,
  loadSubstrates,
  addPhase,
  removePhase,
  saveRecipe,
  validate,
} = useRecipeEditor(recipe)

const activeUsage = ref<RecipeActiveUsage | null>(null)
const usageError = ref(false)
const publicationOpen = ref(false)
const savedFormSnapshot = ref<string | null>(null)
const savedDraft = computed(() => savedFormSnapshot.value === JSON.stringify(form))
const baseline = createRecipeEditorFormState(recipe)
const changes = computed(() => {
  const items: string[] = []
  if (form.name !== baseline.name) items.push('Название рецепта изменено')
  if (form.plant_id !== baseline.plant_id) items.push('Культура изменена')
  for (const phase of form.phases) {
    const original = baseline.phases.find(p => p.phase_index === phase.phase_index)
    if (!original) { items.push(`Добавлена фаза «${phase.name}»`); continue }
    if (JSON.stringify(buildRecipePhasePayload(original)) !== JSON.stringify(buildRecipePhasePayload(phase))) items.push(`Изменена фаза «${phase.name}»`)
  }
  if (form.phases.length < baseline.phases.length) items.push('Удалены фазы рецепта')
  return items
})
const parameterFields: Array<{ key: keyof RecipePhaseFormState; label: string }> = [
  { key: 'name', label: 'Название' }, { key: 'duration_hours', label: 'Продолжительность, ч' },
  { key: 'ph_target', label: 'Целевой pH' }, { key: 'ph_min', label: 'pH минимум' }, { key: 'ph_max', label: 'pH максимум' },
  { key: 'ec_target', label: 'Целевой EC, мСм/см' }, { key: 'ec_min', label: 'EC минимум' }, { key: 'ec_max', label: 'EC максимум' },
  { key: 'lighting_photoperiod_hours', label: 'Свет, ч' }, { key: 'irrigation_interval_sec', label: 'Интервал полива, с' }, { key: 'irrigation_duration_sec', label: 'Длительность полива, с' },
]
const parameterChanges = computed(() => form.phases.flatMap(phase => {
  const original = baseline.phases.find(item => item.phase_index === phase.phase_index)
  if (!original) return []
  return parameterFields.filter(field => original[field.key] !== phase[field.key]).map(field => ({
    label: `Фаза ${phase.phase_index + 1} · ${field.label}`,
    before: String(original[field.key] ?? '—'), after: String(phase[field.key] ?? '—'),
  }))
}))

async function loadActiveUsage(): Promise<void> {
  if (!form.id) return
  try {
    activeUsage.value = await api.recipes.getActiveUsage(form.id)
    usageError.value = false
  } catch {
    activeUsage.value = null
    usageError.value = true
  }
}

onMounted(() => {
  void loadPlants()
  void loadNutrientProducts()
  void loadSubstrates()
  void loadActiveUsage()
})

function onPlantCreated(plant: { id: number; name: string }): void {
  if (!plants.value.some(p => p.id === plant.id)) {
    plants.value.push(plant)
  }
}

function onProductCreated(product: NutrientProduct): void {
  if (!nutrientProducts.value.some(p => p.id === product.id)) {
    nutrientProducts.value.push(product)
  }
}

function onSubstrateCreated(substrate: Substrate): void {
  if (!substrates.value.some(s => s.id === substrate.id)) {
    substrates.value.push(substrate)
  }
}

async function onSave(): Promise<void> {
  const wasNew = !form.id
  const saved = await saveRecipe({ publish: false })
  if (!saved) return
  savedFormSnapshot.value = JSON.stringify(form)
  if (wasNew) router.visit(`/recipes/${saved.id}/edit`)
}

function reviewPublication(): void {
  if (!processing.value && validate()) publicationOpen.value = true
}

async function publish(): Promise<void> {
  const saved = await saveRecipe({ publish: true, redirectToRecipe: true })
  if (saved) publicationOpen.value = false
}

function closePublication(): void {
  if (!processing.value) publicationOpen.value = false
}
</script>

<style scoped>
.recipe-workbench { container: recipe / inline-size; }
.recipe-workbench-grid { display:grid; grid-template-columns:minmax(0,1fr); gap:1.25rem; }
@container recipe (min-width:1000px) {
  .recipe-workbench-grid { grid-template-columns:minmax(0,1fr) 17rem; align-items:start; }
  .recipe-workbench-grid > aside { position:sticky; top:1rem; }
}
</style>
