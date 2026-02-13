<template>
  <AppLayout>
    <h1 class="text-lg font-semibold mb-4">
      {{ recipe.id ? 'Редактировать рецепт' : 'Создать рецепт' }}
    </h1>
    <Card>
      <form
        class="space-y-3"
        @submit.prevent="onSave"
      >
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label
              for="recipe-name"
              class="block text-xs text-[color:var(--text-muted)] mb-1"
            >Название</label>
            <input
              id="recipe-name"
              v-model="form.name"
              name="name"
              data-testid="recipe-name-input"
              class="input-field"
              :class="(form.errors as any).name ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''"
            />
            <div
              v-if="(form.errors as any).name"
              class="text-xs text-[color:var(--badge-danger-text)] mt-1"
            >
              {{ (form.errors as any).name }}
            </div>
          </div>
          <div>
            <label
              for="recipe-description"
              class="block text-xs text-[color:var(--text-muted)] mb-1"
            >Описание</label>
            <input
              id="recipe-description"
              v-model="form.description"
              name="description"
              data-testid="recipe-description-input"
              class="input-field"
              :class="(form.errors as any).description ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''"
            />
            <div
              v-if="(form.errors as any).description"
              class="text-xs text-[color:var(--badge-danger-text)] mt-1"
            >
              {{ (form.errors as any).description }}
            </div>
          </div>
          <div>
            <label
              for="recipe-plant"
              class="block text-xs text-[color:var(--text-muted)] mb-1"
            >Культура</label>
            <select
              id="recipe-plant"
              v-model.number="form.plant_id"
              name="plant_id"
              class="input-field"
              :disabled="plantsLoading"
              :class="(form.errors as any).plant_id ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''"
            >
              <option
                :value="null"
                disabled
              >
                Выберите культуру
              </option>
              <option
                v-for="plant in plants"
                :key="plant.id"
                :value="plant.id"
              >
                {{ plant.name }}
              </option>
            </select>
            <div
              v-if="(form.errors as any).plant_id"
              class="text-xs text-[color:var(--badge-danger-text)] mt-1"
            >
              {{ (form.errors as any).plant_id }}
            </div>
            <div
              v-else-if="!plantsLoading && plants.length === 0"
              class="text-xs text-[color:var(--text-dim)] mt-1"
            >
              Нет доступных культур — добавьте культуру в справочнике.
            </div>
          </div>
        </div>

        <div>
          <div class="text-sm font-semibold mb-2">
            Фазы
          </div>
          <div
            v-for="(p, i) in sortedPhases"
            :key="p.id || i"
            :data-testid="`phase-item-${i}`"
            class="rounded-lg border border-[color:var(--border-muted)] p-3 mb-2"
          >
            <div class="grid grid-cols-1 md:grid-cols-6 gap-2">
              <div>
                <label
                  :for="`phase-${i}-index`"
                  class="sr-only"
                >Индекс фазы</label>
                <input
                  :id="`phase-${i}-index`"
                  v-model.number="p.phase_index"
                  :name="`phases[${i}][phase_index]`"
                  type="number"
                  min="0"
                  placeholder="Индекс"
                  :data-testid="`phase-index-input-${i}`"
                  class="input-field"
                  :class="form.errors[`phases.${i}.phase_index`] ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''"
                />
                <div
                  v-if="form.errors[`phases.${i}.phase_index`]"
                  class="text-xs text-[color:var(--badge-danger-text)] mt-1"
                >
                  {{ form.errors[`phases.${i}.phase_index`] }}
                </div>
              </div>
              <div>
                <label
                  :for="`phase-${i}-name`"
                  class="sr-only"
                >Имя фазы</label>
                <input
                  :id="`phase-${i}-name`"
                  v-model="p.name"
                  :name="`phases[${i}][name]`"
                  placeholder="Имя фазы"
                  :data-testid="`phase-name-input-${i}`"
                  class="input-field"
                  :class="form.errors[`phases.${i}.name`] ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''"
                />
                <div
                  v-if="form.errors[`phases.${i}.name`]"
                  class="text-xs text-[color:var(--badge-danger-text)] mt-1"
                >
                  {{ form.errors[`phases.${i}.name`] }}
                </div>
              </div>
              <div>
                <label
                  :for="`phase-${i}-duration`"
                  class="sr-only"
                >Длительность (часов)</label>
                <input
                  :id="`phase-${i}-duration`"
                  v-model.number="p.duration_hours"
                  :name="`phases[${i}][duration_hours]`"
                  type="number"
                  min="1"
                  placeholder="часов"
                  :data-testid="`phase-duration-input-${i}`"
                  class="input-field"
                  :class="form.errors[`phases.${i}.duration_hours`] ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''"
                />
                <div
                  v-if="form.errors[`phases.${i}.duration_hours`]"
                  class="text-xs text-[color:var(--badge-danger-text)] mt-1"
                >
                  {{ form.errors[`phases.${i}.duration_hours`] }}
                </div>
              </div>
              <div>
                <label
                  :for="`phase-${i}-ph-min`"
                  class="sr-only"
                >pH минимум</label>
                <input
                  :id="`phase-${i}-ph-min`"
                  v-model.number="p.targets.ph.min"
                  :name="`phases[${i}][targets][ph][min]`"
                  type="number"
                  step="0.1"
                  placeholder="pH min"
                  class="input-field"
                  :class="form.errors[`phases.${i}.targets.ph.min`] ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''"
                />
                <div
                  v-if="form.errors[`phases.${i}.targets.ph.min`]"
                  class="text-xs text-[color:var(--badge-danger-text)] mt-1"
                >
                  {{ form.errors[`phases.${i}.targets.ph.min`] }}
                </div>
              </div>
              <div>
                <label
                  :for="`phase-${i}-ph-max`"
                  class="sr-only"
                >pH максимум</label>
                <input
                  :id="`phase-${i}-ph-max`"
                  v-model.number="p.targets.ph.max"
                  :name="`phases[${i}][targets][ph][max]`"
                  type="number"
                  step="0.1"
                  placeholder="pH max"
                  class="input-field"
                  :class="form.errors[`phases.${i}.targets.ph.max`] ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''"
                />
                <div
                  v-if="form.errors[`phases.${i}.targets.ph.max`]"
                  class="text-xs text-[color:var(--badge-danger-text)] mt-1"
                >
                  {{ form.errors[`phases.${i}.targets.ph.max`] }}
                </div>
              </div>
              <div class="md:col-span-2 grid grid-cols-2 gap-2">
                <div>
                  <label
                    :for="`phase-${i}-ec-min`"
                    class="sr-only"
                  >EC минимум</label>
                  <input
                    :id="`phase-${i}-ec-min`"
                    v-model.number="p.targets.ec.min"
                    :name="`phases[${i}][targets][ec][min]`"
                    type="number"
                    step="0.1"
                    placeholder="EC min"
                    class="input-field"
                    :class="form.errors[`phases.${i}.targets.ec.min`] ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''"
                  />
                  <div
                    v-if="form.errors[`phases.${i}.targets.ec.min`]"
                    class="text-xs text-[color:var(--badge-danger-text)] mt-1"
                  >
                    {{ form.errors[`phases.${i}.targets.ec.min`] }}
                  </div>
                </div>
                <div>
                  <label
                    :for="`phase-${i}-ec-max`"
                    class="sr-only"
                  >EC максимум</label>
                  <input
                    :id="`phase-${i}-ec-max`"
                    v-model.number="p.targets.ec.max"
                    :name="`phases[${i}][targets][ec][max]`"
                    type="number"
                    step="0.1"
                    placeholder="EC max"
                    class="input-field"
                    :class="form.errors[`phases.${i}.targets.ec.max`] ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''"
                  />
                  <div
                    v-if="form.errors[`phases.${i}.targets.ec.max`]"
                    class="text-xs text-[color:var(--badge-danger-text)] mt-1"
                  >
                    {{ form.errors[`phases.${i}.targets.ec.max`] }}
                  </div>
                </div>
              </div>

              <div class="md:col-span-6 grid grid-cols-3 gap-2 mt-2">
                <input
                  :id="`phase-${i}-temp-air`"
                  v-model.number="p.targets.temp_air"
                  :name="`phases[${i}][targets][temp_air]`"
                  type="number"
                  step="0.1"
                  placeholder="Температура"
                  class="input-field"
                />
                <input
                  :id="`phase-${i}-humidity-air`"
                  v-model.number="p.targets.humidity_air"
                  :name="`phases[${i}][targets][humidity_air]`"
                  type="number"
                  step="0.1"
                  placeholder="Влажность"
                  class="input-field"
                />
                <input
                  :id="`phase-${i}-light-hours`"
                  v-model.number="p.targets.light_hours"
                  :name="`phases[${i}][targets][light_hours]`"
                  type="number"
                  placeholder="Свет (часов)"
                  class="input-field"
                />
              </div>

              <div class="md:col-span-6 grid grid-cols-2 gap-2 mt-2">
                <input
                  :id="`phase-${i}-irrigation-interval`"
                  v-model.number="p.targets.irrigation_interval_sec"
                  :name="`phases[${i}][targets][irrigation_interval_sec]`"
                  type="number"
                  placeholder="Интервал полива (сек)"
                  class="input-field"
                />
                <input
                  :id="`phase-${i}-irrigation-duration`"
                  v-model.number="p.targets.irrigation_duration_sec"
                  :name="`phases[${i}][targets][irrigation_duration_sec]`"
                  type="number"
                  placeholder="Длительность полива (сек)"
                  class="input-field"
                />
              </div>

              <div class="md:col-span-6 border-t border-[color:var(--border-muted)] pt-3 mt-2">
                <div class="text-xs font-semibold uppercase tracking-wide text-[color:var(--text-muted)] mb-2">
                  Питание (NPK / Кальций / Магний / Микро)
                </div>

                <div class="grid grid-cols-1 md:grid-cols-3 gap-2">
                  <input
                    :id="`phase-${i}-nutrient-program-code`"
                    v-model="p.nutrient_program_code"
                    :name="`phases[${i}][nutrient_program_code]`"
                    type="text"
                    placeholder="Код программы питания"
                    class="input-field md:col-span-2"
                    data-testid="nutrient-program-code-input"
                  />
                  <input
                    :id="`phase-${i}-nutrient-dose-delay`"
                    v-model.number="p.nutrient_dose_delay_sec"
                    :name="`phases[${i}][nutrient_dose_delay_sec]`"
                    type="number"
                    min="0"
                    placeholder="Пауза между дозами (сек)"
                    class="input-field"
                    data-testid="nutrient-dose-delay-input"
                  />
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2">
                  <select
                    :id="`phase-${i}-nutrient-mode`"
                    v-model="p.nutrient_mode"
                    :name="`phases[${i}][nutrient_mode]`"
                    class="input-field"
                  >
                    <option value="ratio_ec_pid">
                      ratio_ec_pid
                    </option>
                    <option value="delta_ec_by_k">
                      delta_ec_by_k
                    </option>
                    <option value="dose_ml_l_only">
                      dose_ml_l_only
                    </option>
                  </select>
                  <input
                    :id="`phase-${i}-nutrient-solution-volume`"
                    v-model.number="p.nutrient_solution_volume_l"
                    :name="`phases[${i}][nutrient_solution_volume_l]`"
                    type="number"
                    step="0.1"
                    min="0.1"
                    placeholder="Объём раствора (л), для delta_ec_by_k"
                    class="input-field"
                  />
                </div>

                <div class="grid grid-cols-1 md:grid-cols-4 gap-2 mt-2">
                  <select
                    :id="`phase-${i}-npk-product`"
                    v-model="p.nutrient_npk_product_id"
                    :name="`phases[${i}][nutrient_npk_product_id]`"
                    class="input-field"
                    :disabled="nutrientProductsLoading"
                    data-testid="nutrient-npk-product-select"
                  >
                    <option :value="null">
                      NPK: не выбрано
                    </option>
                    <option
                      v-for="product in npkProducts"
                      :key="`npk-${product.id}`"
                      :value="product.id"
                    >
                      {{ product.manufacturer }} · {{ product.name }}
                    </option>
                  </select>

                  <select
                    :id="`phase-${i}-calcium-product`"
                    v-model="p.nutrient_calcium_product_id"
                    :name="`phases[${i}][nutrient_calcium_product_id]`"
                    class="input-field"
                    :disabled="nutrientProductsLoading"
                    data-testid="nutrient-calcium-product-select"
                  >
                    <option :value="null">
                      Кальций: не выбрано
                    </option>
                    <option
                      v-for="product in calciumProducts"
                      :key="`calcium-${product.id}`"
                      :value="product.id"
                    >
                      {{ product.manufacturer }} · {{ product.name }}
                    </option>
                  </select>

                  <select
                    :id="`phase-${i}-magnesium-product`"
                    v-model="p.nutrient_magnesium_product_id"
                    :name="`phases[${i}][nutrient_magnesium_product_id]`"
                    class="input-field"
                    :disabled="nutrientProductsLoading"
                    data-testid="nutrient-magnesium-product-select"
                  >
                    <option :value="null">
                      Магний: не выбрано
                    </option>
                    <option
                      v-for="product in magnesiumProducts"
                      :key="`magnesium-${product.id}`"
                      :value="product.id"
                    >
                      {{ product.manufacturer }} · {{ product.name }}
                    </option>
                  </select>

                  <select
                    :id="`phase-${i}-micro-product`"
                    v-model="p.nutrient_micro_product_id"
                    :name="`phases[${i}][nutrient_micro_product_id]`"
                    class="input-field"
                    :disabled="nutrientProductsLoading"
                    data-testid="nutrient-micro-product-select"
                  >
                    <option :value="null">
                      Микро: не выбрано
                    </option>
                    <option
                      v-for="product in microProducts"
                      :key="`micro-${product.id}`"
                      :value="product.id"
                    >
                      {{ product.manufacturer }} · {{ product.name }}
                    </option>
                  </select>
                </div>

                <div
                  v-if="!nutrientProductsLoading && nutrientProducts.length === 0"
                  class="text-xs text-[color:var(--text-dim)] mt-2"
                >
                  Справочник удобрений пуст. Добавьте продукты в `nutrient_products`.
                </div>

                <div class="grid grid-cols-1 md:grid-cols-4 gap-2 mt-2">
                  <input
                    :id="`phase-${i}-nutrient-npk-ratio`"
                    v-model.number="p.nutrient_npk_ratio_pct"
                    :name="`phases[${i}][nutrient_npk_ratio_pct]`"
                    type="number"
                    step="0.01"
                    min="0"
                    max="100"
                    placeholder="NPK ratio, %"
                    class="input-field"
                  />
                  <input
                    :id="`phase-${i}-nutrient-calcium-ratio`"
                    v-model.number="p.nutrient_calcium_ratio_pct"
                    :name="`phases[${i}][nutrient_calcium_ratio_pct]`"
                    type="number"
                    step="0.01"
                    min="0"
                    max="100"
                    placeholder="Calcium ratio, %"
                    class="input-field"
                  />
                  <input
                    :id="`phase-${i}-nutrient-magnesium-ratio`"
                    v-model.number="p.nutrient_magnesium_ratio_pct"
                    :name="`phases[${i}][nutrient_magnesium_ratio_pct]`"
                    type="number"
                    step="0.01"
                    min="0"
                    max="100"
                    placeholder="Magnesium ratio, %"
                    class="input-field"
                  />
                  <input
                    :id="`phase-${i}-nutrient-micro-ratio`"
                    v-model.number="p.nutrient_micro_ratio_pct"
                    :name="`phases[${i}][nutrient_micro_ratio_pct]`"
                    type="number"
                    step="0.01"
                    min="0"
                    max="100"
                    placeholder="Micro ratio, %"
                    class="input-field"
                  />
                </div>
                <div class="flex items-center justify-between gap-2 mt-1">
                  <div
                    class="text-xs"
                    :class="isNutrientRatioValid(p) ? 'text-[color:var(--text-dim)]' : 'text-[color:var(--badge-danger-text)]'"
                  >
                    Сумма ratio: {{ nutrientRatioSum(p).toFixed(2) }}%
                  </div>
                  <Button
                    size="sm"
                    variant="secondary"
                    type="button"
                    data-testid="normalize-ratio-button"
                    @click="normalizePhaseRatios(p)"
                  >
                    Нормализовать ratio
                  </Button>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-4 gap-2 mt-2">
                  <input
                    :id="`phase-${i}-nutrient-npk-dose`"
                    v-model.number="p.nutrient_npk_dose_ml_l"
                    :name="`phases[${i}][nutrient_npk_dose_ml_l]`"
                    type="number"
                    step="0.001"
                    min="0"
                    placeholder="NPK мл/л"
                    class="input-field"
                  />
                  <input
                    :id="`phase-${i}-nutrient-calcium-dose`"
                    v-model.number="p.nutrient_calcium_dose_ml_l"
                    :name="`phases[${i}][nutrient_calcium_dose_ml_l]`"
                    type="number"
                    step="0.001"
                    min="0"
                    placeholder="Calcium мл/л"
                    class="input-field"
                  />
                  <input
                    :id="`phase-${i}-nutrient-magnesium-dose`"
                    v-model.number="p.nutrient_magnesium_dose_ml_l"
                    :name="`phases[${i}][nutrient_magnesium_dose_ml_l]`"
                    type="number"
                    step="0.001"
                    min="0"
                    placeholder="Magnesium мл/л"
                    class="input-field"
                  />
                  <input
                    :id="`phase-${i}-nutrient-micro-dose`"
                    v-model.number="p.nutrient_micro_dose_ml_l"
                    :name="`phases[${i}][nutrient_micro_dose_ml_l]`"
                    type="number"
                    step="0.001"
                    min="0"
                    placeholder="Micro мл/л"
                    class="input-field"
                  />
                </div>

                <div class="grid grid-cols-1 md:grid-cols-3 gap-2 mt-2">
                  <input
                    :id="`phase-${i}-nutrient-ec-stop-tolerance`"
                    v-model.number="p.nutrient_ec_stop_tolerance"
                    :name="`phases[${i}][nutrient_ec_stop_tolerance]`"
                    type="number"
                    step="0.001"
                    min="0"
                    placeholder="EC stop tolerance"
                    class="input-field"
                    data-testid="nutrient-ec-stop-tolerance-input"
                  />
                </div>
              </div>
            </div>
          </div>

          <Button
            size="sm"
            variant="secondary"
            type="button"
            data-testid="add-phase-button"
            @click="onAddPhase"
          >
            Добавить фазу
          </Button>
        </div>

        <div class="flex justify-end gap-2">
          <Link href="/recipes">
            <Button
              size="sm"
              variant="secondary"
              type="button"
              data-testid="cancel-button"
            >
              Отмена
            </Button>
          </Link>
          <Button
            size="sm"
            type="submit"
            :disabled="form.processing"
            data-testid="save-recipe-button"
          >
            {{ form.processing ? 'Сохранение...' : 'Сохранить' }}
          </Button>
        </div>
      </form>
    </Card>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Link, usePage, router, useForm } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import type { NutrientProduct, Recipe, RecipePhase } from '@/types'

const DEFAULT_NUTRIENT_PROGRAM_CODE = 'YARAREGA_CALCINIT_HAIFA_MICRO_V1'
const DEFAULT_NUTRIENT_DOSE_DELAY_SEC = 12
const DEFAULT_NUTRIENT_EC_STOP_TOLERANCE = 0.07

const { showToast } = useToast()
const { api } = useApi(showToast)

interface RecipePhaseForm {
  id?: number
  phase_index: number
  name: string
  duration_hours: number
  nutrient_program_code: string | null
  nutrient_mode: 'ratio_ec_pid' | 'delta_ec_by_k' | 'dose_ml_l_only'
  nutrient_npk_ratio_pct: number | null
  nutrient_calcium_ratio_pct: number | null
  nutrient_magnesium_ratio_pct: number | null
  nutrient_micro_ratio_pct: number | null
  nutrient_npk_dose_ml_l: number | null
  nutrient_calcium_dose_ml_l: number | null
  nutrient_magnesium_dose_ml_l: number | null
  nutrient_micro_dose_ml_l: number | null
  nutrient_npk_product_id: number | null
  nutrient_calcium_product_id: number | null
  nutrient_magnesium_product_id: number | null
  nutrient_micro_product_id: number | null
  nutrient_dose_delay_sec: number | null
  nutrient_ec_stop_tolerance: number | null
  nutrient_solution_volume_l: number | null
  targets: {
    ph: { min: number; max: number }
    ec: { min: number; max: number }
    temp_air: number | null
    humidity_air: number | null
    light_hours: number | null
    irrigation_interval_sec: number | null
    irrigation_duration_sec: number | null
  }
}

interface RecipeFormData {
  name: string
  description: string
  plant_id: number | null
  phases: RecipePhaseForm[]
}

interface PageProps {
  recipe?: Recipe
  [key: string]: any
}

interface PlantOption {
  id: number
  name: string
}

const page = usePage<PageProps>()
const recipe = (page.props.recipe || {}) as Partial<Recipe>

const plants = ref<PlantOption[]>([])
const plantsLoading = ref(false)
const nutrientProducts = ref<NutrientProduct[]>([])
const nutrientProductsLoading = ref(false)
const initialPlantId = recipe.plants?.[0]?.id ?? null

function toNullableNumber(value: unknown, fallback: number | null = null): number | null {
  if (value === null || value === undefined || value === '') {
    return fallback
  }

  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function toNullableInt(value: unknown, fallback: number | null = null): number | null {
  const parsed = toNullableNumber(value, fallback)
  if (parsed === null) {
    return null
  }

  return Math.round(parsed)
}

function createDefaultPhase(phaseIndex: number): RecipePhaseForm {
  return {
    phase_index: phaseIndex,
    name: '',
    duration_hours: 24,
    nutrient_program_code: DEFAULT_NUTRIENT_PROGRAM_CODE,
    nutrient_mode: 'ratio_ec_pid',
    nutrient_npk_ratio_pct: 44,
    nutrient_calcium_ratio_pct: 36,
    nutrient_magnesium_ratio_pct: 17,
    nutrient_micro_ratio_pct: 3,
    nutrient_npk_dose_ml_l: 0.55,
    nutrient_calcium_dose_ml_l: 0.55,
    nutrient_magnesium_dose_ml_l: 0.25,
    nutrient_micro_dose_ml_l: 0.09,
    nutrient_npk_product_id: null,
    nutrient_calcium_product_id: null,
    nutrient_magnesium_product_id: null,
    nutrient_micro_product_id: null,
    nutrient_dose_delay_sec: DEFAULT_NUTRIENT_DOSE_DELAY_SEC,
    nutrient_ec_stop_tolerance: DEFAULT_NUTRIENT_EC_STOP_TOLERANCE,
    nutrient_solution_volume_l: null,
    targets: {
      ph: { min: 5.6, max: 6.0 },
      ec: { min: 1.2, max: 1.6 },
      temp_air: null,
      humidity_air: null,
      light_hours: null,
      irrigation_interval_sec: null,
      irrigation_duration_sec: null,
    },
  }
}

function mapRecipePhaseToForm(phase: RecipePhase & Record<string, any>): RecipePhaseForm {
  const phMin = toNullableNumber(phase.ph_min ?? phase.targets?.ph?.min, 5.8) ?? 5.8
  const phMax = toNullableNumber(phase.ph_max ?? phase.targets?.ph?.max, 6.0) ?? 6.0
  const ecMin = toNullableNumber(phase.ec_min ?? phase.targets?.ec?.min, 1.2) ?? 1.2
  const ecMax = toNullableNumber(phase.ec_max ?? phase.targets?.ec?.max, 1.6) ?? 1.6

  return {
    id: phase.id,
    phase_index: phase.phase_index || 0,
    name: phase.name || '',
    duration_hours: phase.duration_hours || 24,
    nutrient_program_code: typeof phase.nutrient_program_code === 'string' && phase.nutrient_program_code.trim().length > 0
      ? phase.nutrient_program_code
      : DEFAULT_NUTRIENT_PROGRAM_CODE,
    nutrient_mode: (phase.nutrient_mode === 'delta_ec_by_k' || phase.nutrient_mode === 'dose_ml_l_only')
      ? phase.nutrient_mode
      : 'ratio_ec_pid',
    nutrient_npk_ratio_pct: toNullableNumber(phase.nutrient_npk_ratio_pct, 44),
    nutrient_calcium_ratio_pct: toNullableNumber(phase.nutrient_calcium_ratio_pct, 36),
    nutrient_magnesium_ratio_pct: toNullableNumber(phase.nutrient_magnesium_ratio_pct, 17),
    nutrient_micro_ratio_pct: toNullableNumber(phase.nutrient_micro_ratio_pct, 3),
    nutrient_npk_dose_ml_l: toNullableNumber(phase.nutrient_npk_dose_ml_l, 0.55),
    nutrient_calcium_dose_ml_l: toNullableNumber(phase.nutrient_calcium_dose_ml_l, 0.55),
    nutrient_magnesium_dose_ml_l: toNullableNumber(phase.nutrient_magnesium_dose_ml_l, 0.25),
    nutrient_micro_dose_ml_l: toNullableNumber(phase.nutrient_micro_dose_ml_l, 0.09),
    nutrient_npk_product_id: toNullableInt(phase.nutrient_npk_product_id),
    nutrient_calcium_product_id: toNullableInt(phase.nutrient_calcium_product_id),
    nutrient_magnesium_product_id: toNullableInt(phase.nutrient_magnesium_product_id),
    nutrient_micro_product_id: toNullableInt(phase.nutrient_micro_product_id),
    nutrient_dose_delay_sec: toNullableInt(phase.nutrient_dose_delay_sec, DEFAULT_NUTRIENT_DOSE_DELAY_SEC),
    nutrient_ec_stop_tolerance: toNullableNumber(phase.nutrient_ec_stop_tolerance, DEFAULT_NUTRIENT_EC_STOP_TOLERANCE),
    nutrient_solution_volume_l: toNullableNumber(phase.nutrient_solution_volume_l),
    targets: {
      ph: { min: phMin, max: phMax },
      ec: { min: ecMin, max: ecMax },
      temp_air: toNullableNumber(phase.temp_air_target ?? phase.targets?.temp_air),
      humidity_air: toNullableNumber(phase.humidity_target ?? phase.targets?.humidity_air),
      light_hours: toNullableNumber(phase.lighting_photoperiod_hours ?? phase.targets?.light_hours),
      irrigation_interval_sec: toNullableInt(phase.irrigation_interval_sec ?? phase.targets?.irrigation_interval_sec),
      irrigation_duration_sec: toNullableInt(phase.irrigation_duration_sec ?? phase.targets?.irrigation_duration_sec),
    },
  }
}

const form = useForm<RecipeFormData>({
  name: recipe.name || '',
  description: recipe.description || '',
  plant_id: initialPlantId,
  phases: (recipe.phases || []).length > 0
    ? (recipe.phases || []).map((phase: RecipePhase & Record<string, any>) => mapRecipePhaseToForm(phase))
    : [createDefaultPhase(0)],
})

const npkProducts = computed<NutrientProduct[]>(() => {
  return nutrientProducts.value.filter((product) => String(product.component).toLowerCase() === 'npk')
})

const calciumProducts = computed<NutrientProduct[]>(() => {
  return nutrientProducts.value.filter((product) => String(product.component).toLowerCase() === 'calcium')
})

const magnesiumProducts = computed<NutrientProduct[]>(() => {
  return nutrientProducts.value.filter((product) => String(product.component).toLowerCase() === 'magnesium')
})

const microProducts = computed<NutrientProduct[]>(() => {
  return nutrientProducts.value.filter((product) => String(product.component).toLowerCase() === 'micro')
})

const loadPlants = async (): Promise<void> => {
  try {
    plantsLoading.value = true
    const response = await api.get('/plants')
    const data = response.data?.data || []
    plants.value = Array.isArray(data)
      ? data.map((plant: any) => ({ id: plant.id, name: plant.name }))
      : []

    if (!form.plant_id && recipe.id) {
      const recipeResponse = await api.get(`/recipes/${recipe.id}`)
      const recipeData = recipeResponse.data?.data || {}
      const apiPlantId = recipeData.plants?.[0]?.id ?? null
      if (apiPlantId) {
        form.plant_id = apiPlantId
      }
    }

    if (!form.plant_id && plants.value.length === 1) {
      form.plant_id = plants.value[0].id
    }
  } catch (error) {
    logger.error('Failed to load plants:', error)
    showToast('Не удалось загрузить список культур', 'error', TOAST_TIMEOUT.NORMAL)
  } finally {
    plantsLoading.value = false
  }
}

const loadNutrientProducts = async (): Promise<void> => {
  try {
    nutrientProductsLoading.value = true
    const response = await api.get('/nutrient-products')
    const data = response.data?.data || []

    nutrientProducts.value = Array.isArray(data)
      ? data.map((item: any) => ({
        id: item.id,
        manufacturer: item.manufacturer,
        name: item.name,
        component: item.component,
        composition: item.composition ?? null,
        recommended_stage: item.recommended_stage ?? null,
        notes: item.notes ?? null,
        metadata: item.metadata ?? null,
      }))
      : []
  } catch (error) {
    logger.error('Failed to load nutrient products:', error)
    showToast('Не удалось загрузить список удобрений', 'error', TOAST_TIMEOUT.NORMAL)
  } finally {
    nutrientProductsLoading.value = false
  }
}

onMounted(() => {
  void loadPlants()
  void loadNutrientProducts()
})

const sortedPhases = computed<RecipePhaseForm[]>(() => {
  return [...form.phases].sort((a, b) => (a.phase_index || 0) - (b.phase_index || 0))
})

function nutrientRatioSum(phase: RecipePhaseForm): number {
  const npk = toNullableNumber(phase.nutrient_npk_ratio_pct, 0) ?? 0
  const calcium = toNullableNumber(phase.nutrient_calcium_ratio_pct, 0) ?? 0
  const magnesium = toNullableNumber(phase.nutrient_magnesium_ratio_pct, 0) ?? 0
  const micro = toNullableNumber(phase.nutrient_micro_ratio_pct, 0) ?? 0
  return npk + calcium + magnesium + micro
}

function roundRatio(value: number): number {
  return Math.round(value * 100) / 100
}

function normalizePhaseRatios(phase: RecipePhaseForm): void {
  const npk = toNullableNumber(phase.nutrient_npk_ratio_pct, 0) ?? 0
  const calcium = toNullableNumber(phase.nutrient_calcium_ratio_pct, 0) ?? 0
  const magnesium = toNullableNumber(phase.nutrient_magnesium_ratio_pct, 0) ?? 0
  const micro = toNullableNumber(phase.nutrient_micro_ratio_pct, 0) ?? 0

  const sum = npk + calcium + magnesium + micro
  if (sum <= 0) {
    phase.nutrient_npk_ratio_pct = 44
    phase.nutrient_calcium_ratio_pct = 36
    phase.nutrient_magnesium_ratio_pct = 17
    phase.nutrient_micro_ratio_pct = 3
    return
  }

  const normalizedNpk = roundRatio((npk / sum) * 100)
  const normalizedCalcium = roundRatio((calcium / sum) * 100)
  const normalizedMagnesium = roundRatio((magnesium / sum) * 100)
  let normalizedMicro = roundRatio(100 - normalizedNpk - normalizedCalcium - normalizedMagnesium)

  if (normalizedMicro < 0) {
    normalizedMicro = 0
  }

  const normalizedSum = normalizedNpk + normalizedCalcium + normalizedMagnesium + normalizedMicro
  if (Math.abs(normalizedSum - 100) > 0.01) {
    normalizedMicro = roundRatio(normalizedMicro + (100 - normalizedSum))
  }

  phase.nutrient_npk_ratio_pct = normalizedNpk
  phase.nutrient_calcium_ratio_pct = normalizedCalcium
  phase.nutrient_magnesium_ratio_pct = normalizedMagnesium
  phase.nutrient_micro_ratio_pct = normalizedMicro
}

function isNutrientRatioValid(phase: RecipePhaseForm): boolean {
  return Math.abs(nutrientRatioSum(phase) - 100) <= 0.01
}

function validateAllPhaseRatios(phases: RecipePhaseForm[]): boolean {
  for (const phase of phases) {
    if (!isNutrientRatioValid(phase)) {
      const label = phase.name?.trim() || `Фаза #${(phase.phase_index ?? 0) + 1}`
      showToast(`Сумма ratio должна быть 100% (${label})`, 'error', TOAST_TIMEOUT.NORMAL)
      return false
    }
  }

  return true
}

const onAddPhase = (): void => {
  const maxIndex = form.phases.length > 0
    ? Math.max(...form.phases.map((phase) => phase.phase_index || 0))
    : -1

  form.phases.push(createDefaultPhase(maxIndex + 1))
}

function buildPhasePayload(phase: RecipePhaseForm): Record<string, any> {
  const phMin = phase.targets.ph.min
  const phMax = phase.targets.ph.max
  const ecMin = phase.targets.ec.min
  const ecMax = phase.targets.ec.max

  return {
    phase_index: phase.phase_index,
    name: phase.name,
    duration_hours: phase.duration_hours,
    ph_target: (phMin + phMax) / 2,
    ph_min: phMin,
    ph_max: phMax,
    ec_target: (ecMin + ecMax) / 2,
    ec_min: ecMin,
    ec_max: ecMax,
    temp_air_target: toNullableNumber(phase.targets.temp_air),
    humidity_target: toNullableNumber(phase.targets.humidity_air),
    lighting_photoperiod_hours: toNullableInt(phase.targets.light_hours),
    irrigation_interval_sec: toNullableInt(phase.targets.irrigation_interval_sec),
    irrigation_duration_sec: toNullableInt(phase.targets.irrigation_duration_sec),
    nutrient_program_code: phase.nutrient_program_code?.trim() || null,
    nutrient_mode: phase.nutrient_mode || 'ratio_ec_pid',
    nutrient_npk_ratio_pct: toNullableNumber(phase.nutrient_npk_ratio_pct),
    nutrient_calcium_ratio_pct: toNullableNumber(phase.nutrient_calcium_ratio_pct),
    nutrient_magnesium_ratio_pct: toNullableNumber(phase.nutrient_magnesium_ratio_pct),
    nutrient_micro_ratio_pct: toNullableNumber(phase.nutrient_micro_ratio_pct),
    nutrient_npk_dose_ml_l: toNullableNumber(phase.nutrient_npk_dose_ml_l),
    nutrient_calcium_dose_ml_l: toNullableNumber(phase.nutrient_calcium_dose_ml_l),
    nutrient_magnesium_dose_ml_l: toNullableNumber(phase.nutrient_magnesium_dose_ml_l),
    nutrient_micro_dose_ml_l: toNullableNumber(phase.nutrient_micro_dose_ml_l),
    nutrient_npk_product_id: toNullableInt(phase.nutrient_npk_product_id),
    nutrient_calcium_product_id: toNullableInt(phase.nutrient_calcium_product_id),
    nutrient_magnesium_product_id: toNullableInt(phase.nutrient_magnesium_product_id),
    nutrient_micro_product_id: toNullableInt(phase.nutrient_micro_product_id),
    nutrient_dose_delay_sec: toNullableInt(phase.nutrient_dose_delay_sec),
    nutrient_ec_stop_tolerance: toNullableNumber(phase.nutrient_ec_stop_tolerance),
    nutrient_solution_volume_l: toNullableNumber(phase.nutrient_solution_volume_l),
  }
}

const onSave = async (): Promise<void> => {
  if (!form.plant_id) {
    showToast('Выберите культуру для рецепта', 'error', TOAST_TIMEOUT.NORMAL)
    return
  }

  if (!validateAllPhaseRatios(form.phases)) {
    return
  }

  try {
    form.processing = true

    if (recipe.id) {
      await api.patch(`/recipes/${recipe.id}`, {
        name: form.name,
        description: form.description,
        plant_id: form.plant_id,
      })

      let draftRevisionId = (recipe as any).draft_revision_id as number | undefined
      const hasDraft = !!draftRevisionId

      if (!draftRevisionId) {
        const revisionResponse = await api.post<{ data?: { id: number } } | { id: number }>(
          `/recipes/${recipe.id}/revisions`,
          { description: 'Auto draft' }
        )
        const revision = (revisionResponse.data as { data?: { id: number } })?.data || (revisionResponse.data as { id: number })
        draftRevisionId = revision?.id
      }

      if (!draftRevisionId) {
        throw new Error('Draft revision ID not found')
      }

      const existingPhaseIds = hasDraft
        ? (recipe.phases || []).map((phase: any) => phase.id).filter((id: number | undefined) => !!id)
        : []
      const currentPhaseIds = form.phases
        .map((phase) => phase.id)
        .filter((id): id is number => !!id)

      for (const phase of form.phases) {
        const payload = buildPhasePayload(phase)

        if (hasDraft && phase.id) {
          await api.patch(`/recipe-revision-phases/${phase.id}`, payload)
        } else {
          await api.post(`/recipe-revisions/${draftRevisionId}/phases`, payload)
        }
      }

      if (hasDraft) {
        const removedIds = existingPhaseIds.filter((id) => !currentPhaseIds.includes(id))
        for (const removedId of removedIds) {
          await api.delete(`/recipe-revision-phases/${removedId}`)
        }
      }

      await api.post(`/recipe-revisions/${draftRevisionId}/publish`)
      showToast('Рецепт успешно обновлен', 'success', TOAST_TIMEOUT.NORMAL)
      router.visit(`/recipes/${recipe.id}`)
      return
    }

    const recipeResponse = await api.post<{ data?: { id: number } }>(
      '/recipes',
      {
        name: form.name,
        description: form.description,
        plant_id: form.plant_id,
      }
    )

    const recipeId = (recipeResponse.data as { data?: { id: number } })?.data?.id

    if (!recipeId) {
      throw new Error('Recipe ID not found in response')
    }

    const revisionResponse = await api.post<{ data?: { id: number } } | { id: number }>(
      `/recipes/${recipeId}/revisions`,
      { description: 'Initial revision' }
    )
    const revision = (revisionResponse.data as { data?: { id: number } })?.data || (revisionResponse.data as { id: number })
    const revisionId = revision?.id

    if (!revisionId) {
      throw new Error('Recipe revision ID not found in response')
    }

    for (const phase of form.phases) {
      await api.post(`/recipe-revisions/${revisionId}/phases`, buildPhasePayload(phase))
    }

    await api.post(`/recipe-revisions/${revisionId}/publish`)

    showToast('Рецепт успешно создан', 'success', TOAST_TIMEOUT.NORMAL)
    router.visit(`/recipes/${recipeId}`)
  } catch (error) {
    logger.error('Failed to save recipe:', error)
  } finally {
    form.processing = false
  }
}
</script>
