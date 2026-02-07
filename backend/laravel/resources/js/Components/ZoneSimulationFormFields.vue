<template>
  <div>
    <label
      for="simulation-duration-hours"
      class="block text-sm font-medium mb-1"
    >Длительность (часы)</label>
    <p class="text-xs text-[color:var(--text-muted)] mb-1">
      Сколько часов моделировать. Дольше = более долгий прогноз.
    </p>
    <input
      id="simulation-duration-hours"
      v-model.number="form.duration_hours"
      name="duration_hours"
      type="number"
      min="1"
      max="720"
      class="input-field h-9 w-full"
      required
    />
  </div>

  <div>
    <label
      for="simulation-step-minutes"
      class="block text-sm font-medium mb-1"
    >Шаг (минуты)</label>
    <p class="text-xs text-[color:var(--text-muted)] mb-1">
      Меньше шаг — выше детализация, но расчет дольше.
    </p>
    <input
      id="simulation-step-minutes"
      v-model.number="form.step_minutes"
      name="step_minutes"
      type="number"
      min="1"
      max="60"
      class="input-field h-9 w-full"
      required
    />
  </div>

  <div>
    <label
      for="simulation-real-duration-minutes"
      class="block text-sm font-medium mb-1"
    >Длительность прогона (минуты)</label>
    <p class="text-xs text-[color:var(--text-muted)] mb-1">
      Опционально: сколько минут длится весь прогон в реальном времени.
    </p>
    <input
      id="simulation-real-duration-minutes"
      v-model.number="form.sim_duration_minutes"
      name="sim_duration_minutes"
      type="number"
      min="1"
      max="10080"
      class="input-field h-9 w-full"
    />
  </div>

  <div class="flex items-start gap-2">
    <input
      id="simulation-full-mode"
      v-model="form.full_simulation"
      name="full_simulation"
      type="checkbox"
      :disabled="form.sim_duration_minutes === null"
      class="mt-1 h-4 w-4 rounded border-[color:var(--border-muted)] bg-transparent text-[color:var(--accent-cyan)] disabled:opacity-40"
    />
    <label
      for="simulation-full-mode"
      class="text-xs text-[color:var(--text-muted)]"
    >
      Полный прогон: создать зону, растение, рецепт и дополнительную ноду, пройти все фазы до отчета.
    </label>
  </div>

  <div>
    <label
      for="simulation-recipe-search"
      class="block text-sm font-medium mb-1"
    >Рецепт (необязательно)</label>
    <p class="text-xs text-[color:var(--text-muted)] mb-1">
      Выберите рецепт из базы или оставьте "по умолчанию", чтобы взять рецепт зоны.
    </p>
    <input
      id="simulation-recipe-search"
      v-model="recipeSearch"
      name="recipe_search"
      type="text"
      placeholder="Поиск по названию..."
      class="input-field h-9 w-full mb-2"
    />
    <select
      id="simulation-recipe-select"
      v-model="form.recipe_id"
      name="recipe_id"
      class="input-field h-9 w-full"
    >
      <option :value="null">
        Рецепт зоны (по умолчанию)
      </option>
      <option
        v-for="recipe in recipes"
        :key="recipe.id"
        :value="recipe.id"
      >
        {{ recipe.name }}
      </option>
    </select>
    <div
      v-if="recipesLoading"
      class="text-xs text-[color:var(--text-muted)] mt-1"
    >
      Загрузка рецептов...
    </div>
    <div
      v-else-if="recipesError"
      class="text-xs text-[color:var(--accent-red)] mt-1"
    >
      {{ recipesError }}
    </div>
  </div>

  <div class="border-t border-[color:var(--border-muted)] pt-4">
    <div class="text-sm font-medium mb-2">
      Начальные условия (необязательно)
    </div>
    <p class="text-xs text-[color:var(--text-muted)] mb-2">
      Заполните только то, что хотите переопределить. Пустые поля возьмутся из текущих данных.
    </p>
    <div class="grid grid-cols-2 gap-3">
      <div>
        <label
          for="simulation-initial-ph"
          class="block text-xs text-[color:var(--text-muted)] mb-1"
        >pH</label>
        <p class="text-[11px] text-[color:var(--text-dim)] mb-1">
          Обычно 5.5–6.5 для гидропоники.
        </p>
        <input
          id="simulation-initial-ph"
          v-model.number="form.initial_state.ph"
          name="initial_state_ph"
          type="number"
          step="0.0001"
          class="input-field h-8 w-full"
        />
      </div>
      <div>
        <label
          for="simulation-initial-ec"
          class="block text-xs text-[color:var(--text-muted)] mb-1"
        >EC</label>
        <p class="text-[11px] text-[color:var(--text-dim)] mb-1">
          Электропроводность раствора (мСм/см).
        </p>
        <input
          id="simulation-initial-ec"
          v-model.number="form.initial_state.ec"
          name="initial_state_ec"
          type="number"
          step="0.0001"
          class="input-field h-8 w-full"
        />
      </div>
      <div>
        <label
          for="simulation-initial-temp-air"
          class="block text-xs text-[color:var(--text-muted)] mb-1"
        >Температура воздуха (°C)</label>
        <p class="text-[11px] text-[color:var(--text-dim)] mb-1">
          Стартовая температура воздуха в зоне.
        </p>
        <input
          id="simulation-initial-temp-air"
          v-model.number="form.initial_state.temp_air"
          name="initial_state_temp_air"
          type="number"
          step="0.0001"
          class="input-field h-8 w-full"
        />
      </div>
      <div>
        <label
          for="simulation-initial-temp-water"
          class="block text-xs text-[color:var(--text-muted)] mb-1"
        >Температура воды (°C)</label>
        <p class="text-[11px] text-[color:var(--text-dim)] mb-1">
          Температура питательного раствора.
        </p>
        <input
          id="simulation-initial-temp-water"
          v-model.number="form.initial_state.temp_water"
          name="initial_state_temp_water"
          type="number"
          step="0.0001"
          class="input-field h-8 w-full"
        />
      </div>
      <div class="col-span-2">
        <label
          for="simulation-initial-humidity"
          class="block text-xs text-[color:var(--text-muted)] mb-1"
        >Влажность (%)</label>
        <p class="text-[11px] text-[color:var(--text-dim)] mb-1">
          Относительная влажность воздуха.
        </p>
        <input
          id="simulation-initial-humidity"
          v-model.number="form.initial_state.humidity_air"
          name="initial_state_humidity_air"
          type="number"
          step="0.0001"
          class="input-field h-8 w-full"
        />
      </div>
    </div>
  </div>

  <div class="border-t border-[color:var(--border-muted)] pt-4">
    <div class="text-sm font-medium mb-2">
      Дрифт параметров (node-sim)
    </div>
    <p class="text-xs text-[color:var(--text-muted)] mb-2">
      Задайте скорость изменения в единицах за минуту. Отрицательные значения допустимы.
    </p>
    <div class="flex flex-wrap items-center gap-2 mb-3">
      <Button
        type="button"
        variant="outline"
        size="sm"
        @click="$emit('applyAggressiveDrift')"
      >
        Пресет: агрессивный
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        @click="$emit('resetDriftValues')"
      >
        Сбросить дрифт
      </Button>
      <span class="text-[11px] text-[color:var(--text-dim)]">
        pH≈0.24, EC≈0.105 ед/мин
      </span>
    </div>
    <div class="grid grid-cols-2 gap-3">
      <div>
        <label
          for="simulation-drift-ph"
          class="block text-xs text-[color:var(--text-muted)] mb-1"
        >Дрифт pH (ед/мин)</label>
        <input
          id="simulation-drift-ph"
          v-model.number="driftPh"
          name="node_sim_drift_ph"
          type="number"
          step="0.0001"
          class="input-field h-8 w-full"
          @input="$emit('markDriftTouched', 'ph')"
        />
      </div>
      <div>
        <label
          for="simulation-drift-ec"
          class="block text-xs text-[color:var(--text-muted)] mb-1"
        >Дрифт EC (мСм/см/мин)</label>
        <input
          id="simulation-drift-ec"
          v-model.number="driftEc"
          name="node_sim_drift_ec"
          type="number"
          step="0.0001"
          class="input-field h-8 w-full"
          @input="$emit('markDriftTouched', 'ec')"
        />
      </div>
      <div>
        <label
          for="simulation-drift-temp-air"
          class="block text-xs text-[color:var(--text-muted)] mb-1"
        >Дрифт температуры воздуха (°C/мин)</label>
        <input
          id="simulation-drift-temp-air"
          v-model.number="driftTempAir"
          name="node_sim_drift_temp_air"
          type="number"
          step="0.0001"
          class="input-field h-8 w-full"
          @input="$emit('markDriftTouched', 'temp_air')"
        />
      </div>
      <div>
        <label
          for="simulation-drift-temp-water"
          class="block text-xs text-[color:var(--text-muted)] mb-1"
        >Дрифт температуры воды (°C/мин)</label>
        <input
          id="simulation-drift-temp-water"
          v-model.number="driftTempWater"
          name="node_sim_drift_temp_water"
          type="number"
          step="0.0001"
          class="input-field h-8 w-full"
          @input="$emit('markDriftTouched', 'temp_water')"
        />
      </div>
      <div>
        <label
          for="simulation-drift-humidity"
          class="block text-xs text-[color:var(--text-muted)] mb-1"
        >Дрифт влажности (%/мин)</label>
        <input
          id="simulation-drift-humidity"
          v-model.number="driftHumidity"
          name="node_sim_drift_humidity_air"
          type="number"
          step="0.0001"
          class="input-field h-8 w-full"
          @input="$emit('markDriftTouched', 'humidity_air')"
        />
      </div>
      <div>
        <label
          for="simulation-drift-noise"
          class="block text-xs text-[color:var(--text-muted)] mb-1"
        >Шум дрейфа (ед/мин)</label>
        <input
          id="simulation-drift-noise"
          v-model.number="driftNoise"
          name="node_sim_drift_noise"
          type="number"
          step="0.0001"
          class="input-field h-8 w-full"
          @input="$emit('markDriftTouched', 'noise')"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Button from '@/Components/Button.vue'
import type { RecipeOption } from '@/composables/useSimulationRecipes'
import type { SimulationSubmitForm } from '@/composables/useSimulationSubmit'

type DriftTouchedKey = 'ph' | 'ec' | 'temp_air' | 'temp_water' | 'humidity_air' | 'noise'

interface Props {
  recipes: RecipeOption[]
  recipesLoading: boolean
  recipesError: string | null
}

defineProps<Props>()

defineEmits<{
  markDriftTouched: [key: DriftTouchedKey]
  applyAggressiveDrift: []
  resetDriftValues: []
}>()

const form = defineModel<SimulationSubmitForm>('form', { required: true })
const recipeSearch = defineModel<string>('recipeSearch', { required: true })
const driftPh = defineModel<number | null>('driftPh', { required: true })
const driftEc = defineModel<number | null>('driftEc', { required: true })
const driftTempAir = defineModel<number | null>('driftTempAir', { required: true })
const driftTempWater = defineModel<number | null>('driftTempWater', { required: true })
const driftHumidity = defineModel<number | null>('driftHumidity', { required: true })
const driftNoise = defineModel<number | null>('driftNoise', { required: true })
</script>
