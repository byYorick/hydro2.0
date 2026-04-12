<template>
  <div class="space-y-3">
    <!-- ── 1. Культура ────────────────────────────────────────── -->
    <div v-if="!hidePlantSelect" class="rounded-md border border-[color:var(--border-muted)] p-2.5 space-y-2">
      <div class="text-[10px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-dim)]">Культура</div>

      <div v-if="plantMode === 'select'" class="grid gap-2 md:grid-cols-[1fr_auto]">
        <select id="recipe-plant" v-model.number="form.plant_id" class="input-field" :disabled="plantsLoading">
          <option :value="null">Выберите культуру</option>
          <option v-for="plant in plants" :key="plant.id" :value="plant.id">{{ plant.name }}</option>
        </select>
        <Button size="sm" variant="secondary" @click="plantMode = 'create'">Создать</Button>
      </div>

      <div v-else class="space-y-2">
        <div class="grid grid-cols-1 md:grid-cols-3 gap-2">
          <div>
            <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Название растения</label>
            <input v-model="newPlantName" class="input-field" placeholder="Томат Черри" />
          </div>
          <div>
            <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Вид (species)</label>
            <input v-model="newPlantSpecies" class="input-field" placeholder="Solanum lycopersicum" />
          </div>
          <div>
            <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Сорт (variety)</label>
            <input v-model="newPlantVariety" class="input-field" placeholder="Cherry" />
          </div>
        </div>
        <div class="flex gap-2">
          <Button size="sm" :disabled="!newPlantName.trim() || creatingPlant" @click="createPlant">
            {{ creatingPlant ? 'Создание...' : 'Создать растение' }}
          </Button>
          <Button size="sm" variant="secondary" @click="plantMode = 'select'">Отмена</Button>
        </div>
      </div>
    </div>
    <div v-else class="rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-muted)] px-2.5 py-1.5 text-xs text-[color:var(--text-muted)]">
      Культура: <span class="font-semibold text-[color:var(--text-primary)]">{{ lockedPlantLabel || 'Выбрана на предыдущем шаге' }}</span>
    </div>

    <!-- ── 2. Название рецепта ────────────────────────────────── -->
    <div>
      <div class="text-[10px] text-[color:var(--text-muted)] mb-0.5">Название рецепта</div>
      <div class="text-xs font-semibold text-[color:var(--text-primary)]" data-testid="recipe-name-display">{{ recipeName }}</div>
      <input
        id="recipe-description"
        v-model="recipeLabel"
        data-testid="recipe-name-input"
        class="input-field mt-1"
        placeholder="Veg+Bloom, зима 2026..."
      />
    </div>

    <!-- ── 3. Фазы ────────────────────────────────────────────── -->
    <div class="text-xs font-semibold">Фазы роста</div>

    <div class="space-y-3">
      <section
        v-for="(phase, index) in sortedPhases"
        :key="phase.id || index"
        :data-testid="`phase-item-${index}`"
        class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-3 space-y-2.5"
      >
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-center gap-2">
            <input v-model="phase.name" :data-testid="`phase-name-input-${index}`" class="input-field !w-40" placeholder="VEG / BLOOM" />
            <input v-model.number="phase.duration_hours" :data-testid="`phase-duration-input-${index}`" type="number" min="1" class="input-field !w-20 text-center" placeholder="ч" />
            <span class="text-[10px] text-[color:var(--text-dim)]">ч</span>
          </div>
          <div class="flex items-center gap-2">
            <Button v-if="form.phases.length > 1" type="button" size="sm" variant="secondary" @click="$emit('remove-phase', form.phases.indexOf(phase))">Удалить</Button>
            <div class="flex flex-col items-center">
              <span class="inline-flex items-center justify-center w-6 h-6 rounded-full bg-[color:var(--accent-primary)]/10 text-[11px] font-bold text-[color:var(--accent-primary)]">{{ index + 1 }}</span>
              <span class="text-[8px] text-[color:var(--text-dim)] mt-0.5">фаза</span>
            </div>
          </div>
        </div>

        <!-- Раствор (pH / EC) -->
        <div class="rounded-md border border-[color:var(--border-muted)] p-2.5 space-y-2">
          <div class="text-[10px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-dim)]">Раствор</div>
          <div class="max-w-sm space-y-2">
            <!-- pH -->
            <div>
              <div class="text-sm font-extrabold text-[color:var(--text-primary)] mb-1 tracking-widest uppercase">pH</div>
              <div class="target-row">
                <div class="target-row__side">
                  <span class="target-row__label">мин</span>
                  <input v-model.number="phase.ph_min" type="number" step="0.1" class="target-row__input hide-spin" />
                </div>
                <div class="target-row__center">
                  <button type="button" class="target-row__btn" @click="phase.ph_target = +((phase.ph_target ?? 0) - 0.1).toFixed(1); onPhTargetChange(phase)">&minus;</button>
                  <input v-model.number="phase.ph_target" type="number" step="0.1" class="target-row__input target-row__input--main hide-spin" @input="onPhTargetChange(phase)" />
                  <button type="button" class="target-row__btn" @click="phase.ph_target = +((phase.ph_target ?? 0) + 0.1).toFixed(1); onPhTargetChange(phase)">+</button>
                </div>
                <div class="target-row__side">
                  <span class="target-row__label">макс</span>
                  <input v-model.number="phase.ph_max" type="number" step="0.1" class="target-row__input hide-spin" />
                </div>
              </div>
            </div>
            <!-- EC -->
            <div>
              <div class="text-sm font-extrabold text-[color:var(--text-primary)] mb-1 tracking-widest uppercase">EC</div>
              <div class="target-row">
                <div class="target-row__side">
                  <span class="target-row__label">мин</span>
                  <input v-model.number="phase.ec_min" type="number" step="0.1" class="target-row__input hide-spin" />
                </div>
                <div class="target-row__center">
                  <button type="button" class="target-row__btn" @click="phase.ec_target = +((phase.ec_target ?? 0) - 0.1).toFixed(1); onEcTargetChange(phase)">&minus;</button>
                  <input v-model.number="phase.ec_target" type="number" step="0.1" class="target-row__input target-row__input--main hide-spin" @input="onEcTargetChange(phase)" />
                  <button type="button" class="target-row__btn" @click="phase.ec_target = +((phase.ec_target ?? 0) + 0.1).toFixed(1); onEcTargetChange(phase)">+</button>
                </div>
                <div class="target-row__side">
                  <span class="target-row__label">макс</span>
                  <input v-model.number="phase.ec_max" type="number" step="0.1" class="target-row__input hide-spin" />
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Питание -->
        <div class="rounded-md border border-[color:var(--border-muted)] p-2.5 space-y-2">
          <div class="text-[10px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-dim)]">Питание</div>
          <div class="flex flex-wrap gap-2">
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Режим питания</label>
              <select v-model="phase.nutrient_mode" class="input-field !min-w-[200px]">
                <option value="ratio_ec_pid">PID по EC + доли</option>
                <option value="delta_ec_by_k">По дельте EC (k)</option>
                <option value="dose_ml_l_only">Фикс. доза мл/л</option>
              </select>
              <p class="text-[11px] text-[color:var(--text-muted)] mt-1 leading-snug">
                <template v-if="phase.nutrient_mode === 'ratio_ec_pid'">PID-регулятор по EC, доза распределяется по долям компонентов</template>
                <template v-else-if="phase.nutrient_mode === 'delta_ec_by_k'">Расчёт дозы через разницу EC, коэффициент k и объём раствора</template>
                <template v-else>Фиксированная доза мл/л для каждого компонента, без PID</template>
              </p>
            </div>
            <div v-if="phase.nutrient_mode !== 'dose_ml_l_only'">
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Режим дозирования</label>
              <select v-model="phase.nutrient_ec_dosing_mode" class="input-field !min-w-[200px]">
                <option value="sequential">Последовательный</option>
                <option value="parallel">Параллельный</option>
              </select>
              <p class="text-[11px] text-[color:var(--text-muted)] mt-1 leading-snug">
                <template v-if="phase.nutrient_ec_dosing_mode === 'parallel'">Ca, Mg, Micro дозируются одновременно в одном окне коррекции</template>
                <template v-else>Ca &rarr; Mg &rarr; Micro по очереди, каждый ждёт подтверждения</template>
              </p>
            </div>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-4 gap-2">
            <RecipeEditorProductField label="NPK" description="Азот, фосфор, калий — основа роста" :products="npkProducts" v-model:product-id="phase.nutrient_npk_product_id" v-model:ratio="phase.nutrient_npk_ratio_pct" v-model:dose="phase.nutrient_npk_dose_ml_l" />
            <RecipeEditorProductField label="Кальций" description="Укрепление клеток, профилактика вершинной гнили" :products="calciumProducts" v-model:product-id="phase.nutrient_calcium_product_id" v-model:ratio="phase.nutrient_calcium_ratio_pct" v-model:dose="phase.nutrient_calcium_dose_ml_l" />
            <RecipeEditorProductField label="Магний" description="Фотосинтез, хлорофилл, усвоение фосфора" :products="magnesiumProducts" v-model:product-id="phase.nutrient_magnesium_product_id" v-model:ratio="phase.nutrient_magnesium_ratio_pct" v-model:dose="phase.nutrient_magnesium_dose_ml_l" />
            <RecipeEditorProductField label="Микро" description="Fe, Mn, Zn, Cu, B, Mo — ферменты и иммунитет" :products="microProducts" v-model:product-id="phase.nutrient_micro_product_id" v-model:ratio="phase.nutrient_micro_ratio_pct" v-model:dose="phase.nutrient_micro_dose_ml_l" />
          </div>
          <!-- Ratio + Нормализация -->
          <div class="flex flex-col items-end gap-1">
            <div class="text-right">
              <div class="text-sm font-bold" :class="Math.abs(nutrientRatioSum(phase) - 100) <= 0.01 ? 'text-[color:var(--accent-green)]' : 'text-[color:var(--badge-warning-text)]'">
                {{ nutrientRatioSum(phase).toFixed(1) }}%
              </div>
              <div class="text-[9px] text-[color:var(--text-muted)]">сумма долей</div>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-[10px] text-[color:var(--text-muted)]">Привести сумму долей к 100%</span>
              <button type="button" class="rounded-md bg-emerald-50 dark:bg-emerald-900/20 px-3 py-1.5 text-xs font-semibold text-[color:var(--text-primary)] hover:bg-emerald-100 dark:hover:bg-emerald-900/30 transition-colors" @click="normalizePhaseRatios(phase)">Нормализовать</button>
            </div>
          </div>
          <div
            v-if="ecBreakdown(phase).total > 0 && ecBreakdown(phase).npkShare > 0 && ecBreakdown(phase).npkShare < 1"
            class="rounded bg-[color:var(--bg-muted)] px-2.5 py-2 space-y-1"
          >
            <div class="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-0.5 text-[11px]">
              <span class="text-[color:var(--text-muted)]">NPK: <span class="font-semibold text-[color:var(--text-primary)]">{{ ecBreakdown(phase).npk }}</span> mS/cm</span>
              <span class="text-[color:var(--text-muted)]">Ca: <span class="font-semibold text-[color:var(--text-primary)]">{{ ecBreakdown(phase).calcium }}</span> mS/cm</span>
              <span class="text-[color:var(--text-muted)]">Mg: <span class="font-semibold text-[color:var(--text-primary)]">{{ ecBreakdown(phase).magnesium }}</span> mS/cm</span>
              <span class="text-[color:var(--text-muted)]">Micro: <span class="font-semibold text-[color:var(--text-primary)]">{{ ecBreakdown(phase).micro }}</span> mS/cm</span>
            </div>
            <div class="text-[10px] text-[color:var(--text-muted)]">
              Подготовка &rarr; {{ ecBreakdown(phase).npk }} (NPK)
              &middot;
              Полив &rarr; {{ ecBreakdown(phase).total }} (+ Ca/Mg/Micro)
            </div>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Пауза между дозами, сек</label>
              <input v-model.number="phase.nutrient_dose_delay_sec" type="number" min="0" class="input-field" />
              <p class="text-[11px] text-[color:var(--text-muted)] mt-1 leading-snug">Задержка перед следующей дозой — раствор должен перемешаться и сенсор EC стабилизироваться</p>
            </div>
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">EC tolerance, mS/cm</label>
              <input v-model.number="phase.nutrient_ec_stop_tolerance" type="number" step="0.01" class="input-field" />
              <p class="text-[11px] text-[color:var(--text-muted)] mt-1 leading-snug">Допустимое отклонение EC от цели — когда попал в ±tolerance, коррекция считается завершённой</p>
            </div>
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Объём раствора, л</label>
              <input v-model.number="phase.nutrient_solution_volume_l" type="number" min="0" step="0.1" class="input-field" />
              <p class="text-[11px] text-[color:var(--text-muted)] mt-1 leading-snug">Общий объём бака с раствором — используется для расчёта дозы по формуле мл/л</p>
            </div>
          </div>
        </div>

        <!-- Климат -->
        <div class="rounded-md border border-[color:var(--border-muted)] p-2.5 space-y-2">
          <div class="text-[10px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-dim)]">Климат и свет</div>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Температура</label>
              <input v-model.number="phase.temp_air_target" type="number" step="0.1" class="input-field" />
            </div>
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Влажность, %</label>
              <input v-model.number="phase.humidity_target" type="number" step="1" class="input-field" />
            </div>
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Свет, часов</label>
              <input v-model.number="phase.lighting_photoperiod_hours" type="number" min="0" max="24" class="input-field" />
            </div>
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Старт света</label>
              <input v-model="phase.lighting_start_time" type="time" class="input-field" />
            </div>
          </div>
        </div>

        <!-- Полив -->
        <div class="rounded-md border border-[color:var(--border-muted)] p-2.5 space-y-2">
          <div class="text-[10px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-dim)]">Полив</div>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Режим</label>
              <select v-model="phase.irrigation_mode" class="input-field">
                <option value="SUBSTRATE">SUBSTRATE</option>
                <option value="RECIRC">RECIRC</option>
              </select>
            </div>
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Тип системы</label>
              <select v-model="phase.irrigation_system_type" class="input-field">
                <option value="drip">drip</option>
                <option value="substrate_trays">substrate_trays</option>
                <option value="nft">nft</option>
              </select>
            </div>
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Интервал, сек</label>
              <input v-model.number="phase.irrigation_interval_sec" type="number" min="0" class="input-field" />
            </div>
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Длительность, сек</label>
              <input v-model.number="phase.irrigation_duration_sec" type="number" min="0" class="input-field" />
            </div>
          </div>
          <div
            v-if="phase.irrigation_system_type === 'substrate_trays'"
            class="grid grid-cols-1 md:grid-cols-2 gap-2"
          >
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Влажность субстрата день, %</label>
              <input v-model.number="phase.day_night.soil_moisture.day" type="number" step="1" class="input-field" />
            </div>
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Влажность субстрата ночь, %</label>
              <input v-model.number="phase.day_night.soil_moisture.night" type="number" step="1" class="input-field" />
            </div>
          </div>
        </div>

        <!-- День/ночь (collapsed) -->
        <details class="rounded-lg border border-[color:var(--border-muted)] p-3">
          <summary class="cursor-pointer text-xs font-semibold uppercase tracking-[0.18em] text-[color:var(--text-dim)]">День / ночь (расширенные)</summary>
          <div class="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">pH день</label>
              <input v-model.number="phase.day_night.ph.day" type="number" step="0.1" class="input-field" />
            </div>
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">pH ночь</label>
              <input v-model.number="phase.day_night.ph.night" type="number" step="0.1" class="input-field" />
            </div>
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">EC день</label>
              <input v-model.number="phase.day_night.ec.day" type="number" step="0.1" class="input-field" />
            </div>
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">EC ночь</label>
              <input v-model.number="phase.day_night.ec.night" type="number" step="0.1" class="input-field" />
            </div>
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Температура день</label>
              <input v-model.number="phase.day_night.temperature.day" type="number" step="0.1" class="input-field" />
            </div>
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Температура ночь</label>
              <input v-model.number="phase.day_night.temperature.night" type="number" step="0.1" class="input-field" />
            </div>
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Влажность день</label>
              <input v-model.number="phase.day_night.humidity.day" type="number" step="1" class="input-field" />
            </div>
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Влажность ночь</label>
              <input v-model.number="phase.day_night.humidity.night" type="number" step="1" class="input-field" />
            </div>
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Старт дня</label>
              <input v-model="phase.day_night.lighting.day_start_time" type="time" class="input-field" />
            </div>
            <div>
              <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Свет день, часов</label>
              <input v-model.number="phase.day_night.lighting.day_hours" type="number" min="0" max="24" class="input-field" />
            </div>
          </div>
        </details>
      </section>
    </div>

    <!-- ── Кнопки внизу ──────────────────────────────────────── -->
    <div class="flex items-center justify-between pt-2">
      <Button type="button" size="sm" variant="secondary" data-testid="add-phase-button" @click="$emit('add-phase')">Добавить фазу</Button>
      <Button type="button" size="sm" data-testid="save-recipe-bottom-button" @click="$emit('save')">Сохранить</Button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Button from '@/Components/Button.vue'
import RecipeEditorProductField from '@/Components/RecipeEditorProductField.vue'
import type { NutrientProduct } from '@/types'
import type { PlantOption, RecipeEditorFormState, RecipePhaseFormState } from '@/composables/recipeEditorShared'
import { computeEcBreakdown, normalizePhaseRatios, nutrientRatioSum } from '@/composables/recipeEditorShared'
import type { EcBreakdown } from '@/composables/recipeEditorShared'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { useToast } from '@/composables/useToast'
import { api } from '@/services/api'

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

const props = withDefaults(defineProps<Props>(), {
  plantsLoading: false,
  hidePlantSelect: false,
  lockedPlantLabel: null,
})

const form = defineModel<RecipeEditorFormState>('form', { required: true })

const emit = defineEmits<{
  'add-phase': []
  'remove-phase': [index: number]
  'plant-created': [plant: PlantOption]
  'save': []
}>()

const { showToast } = useToast()

const plantMode = ref<'select' | 'create'>('select')
const newPlantName = ref('')
const newPlantSpecies = ref('')
const newPlantVariety = ref('')
const creatingPlant = ref(false)
const recipeLabel = ref(form.value.description || '')

const selectedPlantName = computed(() => {
  const plant = props.plants.find(p => p.id === form.value.plant_id)
  return plant?.name ?? ''
})

const recipeName = computed(() => {
  const plant = selectedPlantName.value
  const label = recipeLabel.value.trim()
  if (plant && label) return `${plant} ${label}`
  if (plant) return plant
  return label || ''
})

watch(recipeName, (name) => { form.value.name = name }, { immediate: true })
watch(recipeLabel, (label) => { form.value.description = label })

async function createPlant(): Promise<void> {
  const name = newPlantName.value.trim()
  if (!name) return
  creatingPlant.value = true
  try {
    const plant = await api.plants.create({
      name,
      species: newPlantSpecies.value.trim() || null,
      variety: newPlantVariety.value.trim() || null,
    })
    form.value.plant_id = plant.id
    emit('plant-created', { id: plant.id, name: plant.name })
    plantMode.value = 'select'
    newPlantName.value = ''
    newPlantSpecies.value = ''
    newPlantVariety.value = ''
    showToast(`Растение "${plant.name}" создано`, 'success', TOAST_TIMEOUT.NORMAL)
  } catch (err: unknown) {
    showToast('Ошибка создания растения', 'error', TOAST_TIMEOUT.NORMAL)
  } finally {
    creatingPlant.value = false
  }
}

function onPhTargetChange(phase: RecipePhaseFormState): void {
  const t = phase.ph_target ?? 0
  phase.ph_min = +(t - 0.1).toFixed(2)
  phase.ph_max = +(t + 0.1).toFixed(2)
}

function onEcTargetChange(phase: RecipePhaseFormState): void {
  const t = phase.ec_target ?? 0
  phase.ec_min = +(t - 0.1).toFixed(2)
  phase.ec_max = +(t + 0.1).toFixed(2)
}

function ecBreakdown(phase: RecipePhaseFormState): EcBreakdown {
  return computeEcBreakdown(phase)
}

const sortedPhases = computed<RecipePhaseFormState[]>(() => {
  return [...form.value.phases].sort((left, right) => left.phase_index - right.phase_index)
})
</script>

<style scoped>
.hide-spin::-webkit-outer-spin-button,
.hide-spin::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
.hide-spin {
  -moz-appearance: textfield;
}

.target-row {
  display: flex;
  align-items: stretch;
  border: 1px solid var(--border-muted);
  border-radius: 0.6rem;
  overflow: hidden;
  background: var(--bg-elevated);
}
.target-row__side {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 4.5rem;
  padding: 0.15rem 0;
}
.target-row__label {
  font-size: 0.65rem;
  font-weight: 600;
  color: var(--text-muted);
  line-height: 1;
  letter-spacing: 0.03em;
  margin-bottom: 0.1rem;
}
.target-row__center {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border-left: 1px solid var(--border-muted);
  border-right: 1px solid var(--border-muted);
  background: color-mix(in srgb, var(--accent-green) 6%, var(--bg-elevated));
}
.target-row__input {
  width: 100%;
  height: 2.2rem;
  border: none;
  background: transparent;
  text-align: center;
  font-size: 0.8rem;
  color: var(--text-primary);
  outline: none;
}
.target-row__input:focus {
  outline: none;
  box-shadow: none;
}
.target-row__input--main {
  flex: 1;
  min-width: 0;
  font-size: 1.1rem;
  font-weight: 700;
}
.target-row__btn {
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--accent-green);
  background: color-mix(in srgb, var(--accent-green) 10%, transparent);
  border: none;
  border-radius: 50%;
  margin: 0 0.15rem;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s, transform 0.1s;
}
.target-row__btn:hover {
  background: color-mix(in srgb, var(--accent-green) 20%, transparent);
}
.target-row__btn:active {
  transform: scale(0.9);
}
</style>
