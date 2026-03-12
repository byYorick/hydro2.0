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
              :class="form.errors['name'] ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''"
            />
            <div
              v-if="form.errors['name']"
              class="text-xs text-[color:var(--badge-danger-text)] mt-1"
            >
              {{ form.errors['name'] }}
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
              :class="form.errors['description'] ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''"
            />
            <div
              v-if="form.errors['description']"
              class="text-xs text-[color:var(--badge-danger-text)] mt-1"
            >
              {{ form.errors['description'] }}
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
              :class="form.errors['plant_id'] ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''"
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
              v-if="form.errors['plant_id']"
              class="text-xs text-[color:var(--badge-danger-text)] mt-1"
            >
              {{ form.errors['plant_id'] }}
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
import { Link } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import { useRecipeEdit } from '@/composables/useRecipeEdit'

const {
  recipe,
  form,
  plants,
  plantsLoading,
  nutrientProducts,
  nutrientProductsLoading,
  npkProducts,
  calciumProducts,
  magnesiumProducts,
  microProducts,
  sortedPhases,
  nutrientRatioSum,
  isNutrientRatioValid,
  normalizePhaseRatios,
  onAddPhase,
  onSave,
} = useRecipeEdit()
</script>
