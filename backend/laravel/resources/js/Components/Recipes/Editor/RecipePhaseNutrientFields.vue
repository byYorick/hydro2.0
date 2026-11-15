<template>
  <div
    v-if="isAdvanced"
    class="rounded-md border border-[color:var(--border-muted)] p-2.5 space-y-2"
  >
    <div class="text-[12px] font-bold uppercase tracking-[0.16em] text-[color:var(--text-muted)]">
      Питание
    </div>
    <div class="flex flex-wrap gap-2">
      <div>
        <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Режим питания</label>
        <SelectField
          v-model="phase.nutrient_mode"
          class="!min-w-[200px]"
        >
          <option value="ratio_ec_pid">
            PID по EC + доли
          </option>
          <option value="delta_ec_by_k">
            По дельте EC (k)
          </option>
          <option value="dose_ml_l_only">
            Фикс. доза мл/л
          </option>
        </SelectField>
        <p class="text-[12px] text-[color:var(--text-muted)] mt-1 leading-snug">
          <template v-if="phase.nutrient_mode === 'ratio_ec_pid'">
            PID-регулятор по EC, доза распределяется по долям компонентов
          </template>
          <template v-else-if="phase.nutrient_mode === 'delta_ec_by_k'">
            Расчёт дозы через разницу EC, коэффициент k и объём раствора
          </template>
          <template v-else>
            Фиксированная доза мл/л для каждого компонента, без PID
          </template>
        </p>
      </div>
      <div v-if="phase.nutrient_mode !== 'dose_ml_l_only'">
        <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Режим дозирования</label>
        <SelectField
          v-model="phase.nutrient_ec_dosing_mode"
          class="!min-w-[200px]"
        >
          <option value="sequential">
            Последовательный
          </option>
          <option value="parallel">
            Параллельный
          </option>
        </SelectField>
        <p class="text-[12px] text-[color:var(--text-muted)] mt-1 leading-snug">
          <template v-if="phase.nutrient_ec_dosing_mode === 'parallel'">
            Ca, Mg, Micro дозируются одновременно в одном окне коррекции
          </template>
          <template v-else>
            Ca &rarr; Mg &rarr; Micro по очереди, каждый ждёт подтверждения
          </template>
        </p>
      </div>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-4 gap-2">
      <RecipeEditorProductField
        v-model:product-id="phase.nutrient_npk_product_id"
        v-model:ratio="phase.nutrient_npk_ratio_pct"
        v-model:dose="phase.nutrient_npk_dose_ml_l"
        label="NPK"
        description="Азот, фосфор, калий — основа роста"
        component="npk"
        :products="npkProducts"
        @product-created="onProductCreated"
      />
      <RecipeEditorProductField
        v-model:product-id="phase.nutrient_calcium_product_id"
        v-model:ratio="phase.nutrient_calcium_ratio_pct"
        v-model:dose="phase.nutrient_calcium_dose_ml_l"
        label="Кальций"
        description="Укрепление клеток, профилактика вершинной гнили"
        component="calcium"
        :products="calciumProducts"
        @product-created="onProductCreated"
      />
      <RecipeEditorProductField
        v-model:product-id="phase.nutrient_magnesium_product_id"
        v-model:ratio="phase.nutrient_magnesium_ratio_pct"
        v-model:dose="phase.nutrient_magnesium_dose_ml_l"
        label="Магний"
        description="Фотосинтез, хлорофилл, усвоение фосфора"
        component="magnesium"
        :products="magnesiumProducts"
        @product-created="onProductCreated"
      />
      <RecipeEditorProductField
        v-model:product-id="phase.nutrient_micro_product_id"
        v-model:ratio="phase.nutrient_micro_ratio_pct"
        v-model:dose="phase.nutrient_micro_dose_ml_l"
        label="Микро"
        description="Fe, Mn, Zn, Cu, B, Mo — ферменты и иммунитет"
        component="micro"
        :products="microProducts"
        @product-created="onProductCreated"
      />
    </div>
    <!-- Ratio + Нормализация -->
    <div class="flex flex-col items-end gap-1">
      <div class="text-right">
        <div
          class="text-sm font-bold"
          :class="Math.abs(nutrientRatioSum(phase) - 100) <= 0.01 ? 'text-[color:var(--status-ok)]' : 'text-[color:var(--badge-warning-text)]'"
        >
          {{ nutrientRatioSum(phase).toFixed(1) }}%
        </div>
        <div class="text-[11px] text-[color:var(--text-muted)]">
          сумма долей
        </div>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-[12px] text-[color:var(--text-muted)]">Привести сумму долей к 100%</span>
        <button
          type="button"
          class="soft-btn"
          @click="normalizePhaseRatios(phase)"
        >
          <svg
            class="w-3.5 h-3.5"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.2"
            stroke-linecap="round"
            stroke-linejoin="round"
          ><polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" /><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" /></svg>
          Нормализовать
        </button>
      </div>
    </div>
    <!-- EC breakdown — красивые карточки день / ночь -->
    <div
      v-if="phase.day_night_enabled ? ecBreakdownsDayNight(phase) : ecBreakdown(phase).total > 0 && ecBreakdown(phase).npkShare > 0 && ecBreakdown(phase).npkShare < 1"
      class="grid gap-3"
      :class="phase.day_night_enabled ? 'md:grid-cols-2' : 'grid-cols-1'"
    >
      <!-- Карточка день (и одиночная когда свитч выключен) -->
      <div class="ec-breakdown-card">
        <div class="ec-breakdown-card__header">
          <span class="ec-breakdown-card__title">
            <span v-if="phase.day_night_enabled">☀ День</span>
            <span v-else>Расход EC по компонентам</span>
          </span>
          <span class="ec-breakdown-card__total">EC {{ phase.day_night_enabled ? ecBreakdownForTarget(phase, phase.ph_target /* unused */, phase.ec_target).total : ecBreakdown(phase).total }}</span>
        </div>
        <div class="ec-breakdown-card__chips">
          <div class="ec-chip ec-chip--npk">
            <span class="ec-chip__label">NPK</span>
            <span class="ec-chip__value">{{ phase.day_night_enabled ? ecBreakdownForTarget(phase, 0, phase.ec_target).npk : ecBreakdown(phase).npk }}</span>
          </div>
          <div class="ec-chip ec-chip--ca">
            <span class="ec-chip__label">Ca</span>
            <span class="ec-chip__value">{{ phase.day_night_enabled ? ecBreakdownForTarget(phase, 0, phase.ec_target).calcium : ecBreakdown(phase).calcium }}</span>
          </div>
          <div class="ec-chip ec-chip--mg">
            <span class="ec-chip__label">Mg</span>
            <span class="ec-chip__value">{{ phase.day_night_enabled ? ecBreakdownForTarget(phase, 0, phase.ec_target).magnesium : ecBreakdown(phase).magnesium }}</span>
          </div>
          <div class="ec-chip ec-chip--micro">
            <span class="ec-chip__label">Micro</span>
            <span class="ec-chip__value">{{ phase.day_night_enabled ? ecBreakdownForTarget(phase, 0, phase.ec_target).micro : ecBreakdown(phase).micro }}</span>
          </div>
        </div>
        <div class="ec-breakdown-card__flow">
          <div class="ec-flow-stage">
            <span class="ec-flow-stage__icon">◐</span>
            <span class="ec-flow-stage__label">Подготовка</span>
            <span class="ec-flow-stage__value">{{ phase.day_night_enabled ? ecBreakdownForTarget(phase, 0, phase.ec_target).npk : ecBreakdown(phase).npk }}</span>
          </div>
          <span class="ec-flow-arrow">→</span>
          <div class="ec-flow-stage">
            <span class="ec-flow-stage__icon">●</span>
            <span class="ec-flow-stage__label">Полив</span>
            <span class="ec-flow-stage__value">{{ phase.day_night_enabled ? ecBreakdownForTarget(phase, 0, phase.ec_target).total : ecBreakdown(phase).total }}</span>
          </div>
        </div>
      </div>

      <!-- Карточка ночь -->
      <div
        v-if="phase.day_night_enabled"
        class="ec-breakdown-card ec-breakdown-card--night"
      >
        <div class="ec-breakdown-card__header">
          <span class="ec-breakdown-card__title">☾ Ночь</span>
          <span class="ec-breakdown-card__total">EC {{ ecBreakdownForTarget(phase, 0, phase.day_night.ec.night ?? 0).total }}</span>
        </div>
        <div class="ec-breakdown-card__chips">
          <div class="ec-chip ec-chip--npk">
            <span class="ec-chip__label">NPK</span>
            <span class="ec-chip__value">{{ ecBreakdownForTarget(phase, 0, phase.day_night.ec.night ?? 0).npk }}</span>
          </div>
          <div class="ec-chip ec-chip--ca">
            <span class="ec-chip__label">Ca</span>
            <span class="ec-chip__value">{{ ecBreakdownForTarget(phase, 0, phase.day_night.ec.night ?? 0).calcium }}</span>
          </div>
          <div class="ec-chip ec-chip--mg">
            <span class="ec-chip__label">Mg</span>
            <span class="ec-chip__value">{{ ecBreakdownForTarget(phase, 0, phase.day_night.ec.night ?? 0).magnesium }}</span>
          </div>
          <div class="ec-chip ec-chip--micro">
            <span class="ec-chip__label">Micro</span>
            <span class="ec-chip__value">{{ ecBreakdownForTarget(phase, 0, phase.day_night.ec.night ?? 0).micro }}</span>
          </div>
        </div>
        <div class="ec-breakdown-card__flow">
          <div class="ec-flow-stage">
            <span class="ec-flow-stage__icon">◐</span>
            <span class="ec-flow-stage__label">Подготовка</span>
            <span class="ec-flow-stage__value">{{ ecBreakdownForTarget(phase, 0, phase.day_night.ec.night ?? 0).npk }}</span>
          </div>
          <span class="ec-flow-arrow">→</span>
          <div class="ec-flow-stage">
            <span class="ec-flow-stage__icon">●</span>
            <span class="ec-flow-stage__label">Полив</span>
            <span class="ec-flow-stage__value">{{ ecBreakdownForTarget(phase, 0, phase.day_night.ec.night ?? 0).total }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { RecipePhaseFormState } from '@/composables/recipeEditorShared'
const phase = defineModel<RecipePhaseFormState>('phase', { required: true })
import SelectField from '@/Components/SelectField.vue'

import { ecBreakdown, ecBreakdownForTarget, ecBreakdownsDayNight } from '@/composables/recipePhaseFields'
import type { NutrientProduct } from '@/types'
import RecipeEditorProductField from '@/Components/RecipeEditorProductField.vue'
import { normalizePhaseRatios, nutrientRatioSum } from '@/composables/recipeEditorShared'
defineProps<{ isAdvanced: boolean; npkProducts: NutrientProduct[]; calciumProducts: NutrientProduct[]; magnesiumProducts: NutrientProduct[]; microProducts: NutrientProduct[] }>()
const emit = defineEmits<{ 'product-created': [product: NutrientProduct] }>()
function onProductCreated(product: NutrientProduct): void { emit('product-created', product) }
</script>
