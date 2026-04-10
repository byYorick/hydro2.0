<template>
  <div class="space-y-4">
    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
      <div>
        <label
          for="recipe-name"
          class="block text-xs text-[color:var(--text-muted)] mb-1"
        >Название</label>
        <input
          id="recipe-name"
          v-model="form.name"
          data-testid="recipe-name-input"
          class="input-field"
        />
      </div>
      <div>
        <label
          for="recipe-description"
          class="block text-xs text-[color:var(--text-muted)] mb-1"
        >Описание</label>
        <input
          id="recipe-description"
          v-model="form.description"
          data-testid="recipe-description-input"
          class="input-field"
        />
      </div>
      <div v-if="!hidePlantSelect">
        <label
          for="recipe-plant"
          class="block text-xs text-[color:var(--text-muted)] mb-1"
        >Культура</label>
        <select
          id="recipe-plant"
          v-model.number="form.plant_id"
          class="input-field"
          :disabled="plantsLoading"
        >
          <option :value="null">
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
      </div>
      <div
        v-else
        class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-muted)] px-3 py-2 text-sm text-[color:var(--text-muted)]"
      >
        Культура: <span class="font-semibold text-[color:var(--text-primary)]">{{ lockedPlantLabel || 'Выбрана на предыдущем шаге' }}</span>
      </div>
    </div>

    <div class="flex items-center justify-between">
      <div class="text-sm font-semibold">
        Фазы
      </div>
      <Button
        type="button"
        size="sm"
        variant="secondary"
        data-testid="add-phase-button"
        @click="$emit('add-phase')"
      >
        Добавить фазу
      </Button>
    </div>

    <div class="space-y-3">
      <section
        v-for="(phase, index) in sortedPhases"
        :key="phase.id || index"
        :data-testid="`phase-item-${index}`"
        class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-4 space-y-4"
      >
        <div class="flex items-center justify-between gap-3">
          <div class="text-sm font-semibold">
            Фаза {{ index + 1 }}
          </div>
          <Button
            v-if="form.phases.length > 1"
            type="button"
            size="sm"
            variant="secondary"
            @click="$emit('remove-phase', form.phases.indexOf(phase))"
          >
            Удалить
          </Button>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label class="block text-xs text-[color:var(--text-muted)] mb-1">Индекс</label>
            <input
              v-model.number="phase.phase_index"
              :data-testid="`phase-index-input-${index}`"
              type="number"
              min="0"
              class="input-field"
            />
          </div>
          <div>
            <label class="block text-xs text-[color:var(--text-muted)] mb-1">Название</label>
            <input
              v-model="phase.name"
              :data-testid="`phase-name-input-${index}`"
              class="input-field"
            />
          </div>
          <div>
            <label class="block text-xs text-[color:var(--text-muted)] mb-1">Длительность, часов</label>
            <input
              v-model.number="phase.duration_hours"
              :data-testid="`phase-duration-input-${index}`"
              type="number"
              min="1"
              class="input-field"
            />
          </div>
        </div>

        <div class="rounded-lg border border-[color:var(--border-muted)] p-3 space-y-3">
          <div class="text-xs font-semibold uppercase tracking-[0.18em] text-[color:var(--text-dim)]">
            Цели
          </div>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">pH target</label>
              <input
                v-model.number="phase.ph_target"
                type="number"
                step="0.1"
                class="input-field"
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">pH min</label>
              <input
                v-model.number="phase.ph_min"
                type="number"
                step="0.1"
                class="input-field"
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">pH max</label>
              <input
                v-model.number="phase.ph_max"
                type="number"
                step="0.1"
                class="input-field"
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">EC target</label>
              <input
                v-model.number="phase.ec_target"
                type="number"
                step="0.1"
                class="input-field"
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">EC min</label>
              <input
                v-model.number="phase.ec_min"
                type="number"
                step="0.1"
                class="input-field"
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">EC max</label>
              <input
                v-model.number="phase.ec_max"
                type="number"
                step="0.1"
                class="input-field"
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Температура</label>
              <input
                v-model.number="phase.temp_air_target"
                type="number"
                step="0.1"
                class="input-field"
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Влажность</label>
              <input
                v-model.number="phase.humidity_target"
                type="number"
                step="1"
                class="input-field"
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Свет, часов</label>
              <input
                v-model.number="phase.lighting_photoperiod_hours"
                type="number"
                min="0"
                max="24"
                class="input-field"
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Старт света</label>
              <input
                v-model="phase.lighting_start_time"
                type="time"
                class="input-field"
              />
            </div>
          </div>
        </div>

        <div class="rounded-lg border border-[color:var(--border-muted)] p-3 space-y-3">
          <div class="text-xs font-semibold uppercase tracking-[0.18em] text-[color:var(--text-dim)]">
            Полив
          </div>
          <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Режим</label>
              <select
                v-model="phase.irrigation_mode"
                class="input-field"
              >
                <option value="SUBSTRATE">
                  SUBSTRATE
                </option>
                <option value="RECIRC">
                  RECIRC
                </option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Тип системы</label>
              <select
                v-model="phase.irrigation_system_type"
                class="input-field"
              >
                <option value="drip">
                  drip
                </option>
                <option value="substrate_trays">
                  substrate_trays
                </option>
                <option value="nft">
                  nft
                </option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Интервал, сек</label>
              <input
                v-model.number="phase.irrigation_interval_sec"
                type="number"
                min="0"
                class="input-field"
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Длительность, сек</label>
              <input
                v-model.number="phase.irrigation_duration_sec"
                type="number"
                min="0"
                class="input-field"
              />
            </div>
          </div>

          <div class="mt-3 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-muted)] p-3 space-y-3">
            <div class="text-xs font-semibold uppercase tracking-[0.18em] text-[color:var(--text-dim)]">
              Умный полив (soil moisture target)
            </div>
            <p class="text-xs text-[color:var(--text-dim)]">
              Эти цели используются decision-controller’ом `smart_soil_v1` в автоматизации зоны. Единицы: % (0..100).
            </p>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label class="block text-xs text-[color:var(--text-muted)] mb-1">Soil moisture day (%)</label>
                <input
                  v-model.number="phase.day_night.soil_moisture.day"
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  class="input-field"
                />
              </div>
              <div>
                <label class="block text-xs text-[color:var(--text-muted)] mb-1">Soil moisture night (%)</label>
                <input
                  v-model.number="phase.day_night.soil_moisture.night"
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  class="input-field"
                />
              </div>
            </div>
          </div>
        </div>

        <details class="rounded-lg border border-[color:var(--border-muted)] p-3">
          <summary class="cursor-pointer text-sm font-semibold">
            Питание
          </summary>
          <div class="mt-3 space-y-3">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                <label class="block text-xs text-[color:var(--text-muted)] mb-1">Программа</label>
                <input
                  v-model="phase.nutrient_program_code"
                  class="input-field"
                />
              </div>
              <div>
                <label class="block text-xs text-[color:var(--text-muted)] mb-1">Режим питания</label>
                <select
                  v-model="phase.nutrient_mode"
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
              </div>
              <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-muted)] px-3 py-2 text-xs">
                Сумма ratio: {{ nutrientRatioSum(phase).toFixed(2) }}%
                <button
                  type="button"
                  class="ml-2 text-[color:var(--accent-primary)]"
                  @click="normalizePhaseRatios(phase)"
                >
                  Нормализовать
                </button>
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
              <RecipeEditorProductField
                v-model:product-id="phase.nutrient_npk_product_id"
                v-model:ratio="phase.nutrient_npk_ratio_pct"
                v-model:dose="phase.nutrient_npk_dose_ml_l"
                label="NPK"
                :products="npkProducts"
              />
              <RecipeEditorProductField
                v-model:product-id="phase.nutrient_calcium_product_id"
                v-model:ratio="phase.nutrient_calcium_ratio_pct"
                v-model:dose="phase.nutrient_calcium_dose_ml_l"
                label="Кальций"
                :products="calciumProducts"
              />
              <RecipeEditorProductField
                v-model:product-id="phase.nutrient_magnesium_product_id"
                v-model:ratio="phase.nutrient_magnesium_ratio_pct"
                v-model:dose="phase.nutrient_magnesium_dose_ml_l"
                label="Магний"
                :products="magnesiumProducts"
              />
              <RecipeEditorProductField
                v-model:product-id="phase.nutrient_micro_product_id"
                v-model:ratio="phase.nutrient_micro_ratio_pct"
                v-model:dose="phase.nutrient_micro_dose_ml_l"
                label="Микро"
                :products="microProducts"
              />
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                <label class="block text-xs text-[color:var(--text-muted)] mb-1">Пауза доз, сек</label>
                <input
                  v-model.number="phase.nutrient_dose_delay_sec"
                  type="number"
                  min="0"
                  class="input-field"
                />
              </div>
              <div>
                <label class="block text-xs text-[color:var(--text-muted)] mb-1">EC stop tolerance</label>
                <input
                  v-model.number="phase.nutrient_ec_stop_tolerance"
                  type="number"
                  step="0.01"
                  class="input-field"
                />
              </div>
              <div>
                <label class="block text-xs text-[color:var(--text-muted)] mb-1">Объём раствора, л</label>
                <input
                  v-model.number="phase.nutrient_solution_volume_l"
                  type="number"
                  min="0"
                  step="0.1"
                  class="input-field"
                />
              </div>
            </div>
          </div>
        </details>

        <details class="rounded-lg border border-[color:var(--border-muted)] p-3">
          <summary class="cursor-pointer text-sm font-semibold">
            Advanced day/night
          </summary>
          <div class="mt-3 grid grid-cols-1 md:grid-cols-4 gap-3">
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">pH день</label>
              <input
                v-model.number="phase.day_night.ph.day"
                type="number"
                step="0.1"
                class="input-field"
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">pH ночь</label>
              <input
                v-model.number="phase.day_night.ph.night"
                type="number"
                step="0.1"
                class="input-field"
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">EC день</label>
              <input
                v-model.number="phase.day_night.ec.day"
                type="number"
                step="0.1"
                class="input-field"
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">EC ночь</label>
              <input
                v-model.number="phase.day_night.ec.night"
                type="number"
                step="0.1"
                class="input-field"
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Температура день</label>
              <input
                v-model.number="phase.day_night.temperature.day"
                type="number"
                step="0.1"
                class="input-field"
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Температура ночь</label>
              <input
                v-model.number="phase.day_night.temperature.night"
                type="number"
                step="0.1"
                class="input-field"
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Влажность день</label>
              <input
                v-model.number="phase.day_night.humidity.day"
                type="number"
                step="1"
                class="input-field"
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Влажность ночь</label>
              <input
                v-model.number="phase.day_night.humidity.night"
                type="number"
                step="1"
                class="input-field"
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Старт дня</label>
              <input
                v-model="phase.day_night.lighting.day_start_time"
                type="time"
                class="input-field"
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Свет день, часов</label>
              <input
                v-model.number="phase.day_night.lighting.day_hours"
                type="number"
                min="0"
                max="24"
                class="input-field"
              />
            </div>
          </div>
        </details>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Button from '@/Components/Button.vue'
import RecipeEditorProductField from '@/Components/RecipeEditorProductField.vue'
import type { NutrientProduct } from '@/types'
import type { PlantOption, RecipeEditorFormState, RecipePhaseFormState } from '@/composables/recipeEditorShared'
import { normalizePhaseRatios, nutrientRatioSum } from '@/composables/recipeEditorShared'

interface Props {
  plants: PlantOption[]
  plantsLoading?: boolean
  npkProducts: NutrientProduct[]
  calciumProducts: NutrientProduct[]
  magnesiumProducts: NutrientProduct[]
  microProducts: NutrientProduct[]
  hidePlantSelect?: boolean
  lockedPlantLabel?: string | null
}

withDefaults(defineProps<Props>(), {
  plantsLoading: false,
  hidePlantSelect: false,
  lockedPlantLabel: null,
})

const form = defineModel<RecipeEditorFormState>('form', { required: true })

defineEmits<{
  'add-phase': []
  'remove-phase': [index: number]
}>()

const sortedPhases = computed<RecipePhaseFormState[]>(() => {
  return [...form.value.phases].sort((left, right) => left.phase_index - right.phase_index)
})
</script>
