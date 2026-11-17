<template>
  <section
    :data-testid="`phase-item-${index}`"
    class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-3 space-y-2.5"
  >
    <div class="flex items-center justify-between gap-2">
      <div class="flex flex-wrap items-end gap-3">
        <div>
          <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Название</label>
          <TextField
            v-model="phase.name"
            :data-testid="`phase-name-input-${index}`"
            class="!w-40"
            placeholder="VEG / BLOOM"
          />
        </div>
        <div>
          <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Длительность (дни:часы)</label>
          <TextField
            :model-value="durationDisplay(phase)"
            :error="Number.isNaN(phase.duration_hours) ? 'Укажите дни и часы: ДД:ЧЧ, часы от 00 до 23.' : ''"
            :data-testid="`phase-duration-input-${index}`"
            type="text"
            placeholder="0 : 00"
            class="!w-24"
            input-class="text-center tracking-widest"
            @change="setDurationFromString(phase, ($event.target as HTMLInputElement).value)"
          />
        </div>
        <div v-if="isAdvanced">
          <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Раздельно день / ночь</label>
          <label class="md-switch">
            <input
              v-model="phase.day_night_enabled"
              type="checkbox"
            />
            <span class="md-switch__track">
              <span class="md-switch__thumb"></span>
            </span>
            <span class="md-switch__label">{{ phase.day_night_enabled ? 'Вкл' : 'Выкл' }}</span>
          </label>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <Button
          v-if="canRemove"
          type="button"
          size="sm"
          variant="secondary"
          @click="emit('remove')"
        >
          Удалить
        </Button>
        <div class="flex flex-col items-center">
          <span class="inline-flex items-center justify-center w-6 h-6 rounded-full bg-[color:var(--series-primary)]/10 text-[11px] font-bold text-[color:var(--series-primary)]">{{ index + 1 }}</span>
          <span class="text-[8px] text-[color:var(--text-dim)] mt-0.5">фаза</span>
        </div>
      </div>
    </div>
    <RecipePhaseIrrigationFields
      v-model:phase="phase"
      :is-advanced="isAdvanced"
      :recipe-irrigation-mode="recipeIrrigationMode"
      :substrate-options="substrateOptions"
      @create-substrate="emit('create-substrate')"
    />
    <RecipePhaseSolutionFields v-model:phase="phase" />
    <RecipePhaseNutrientFields
      v-model:phase="phase"
      :is-advanced="isAdvanced"
      :npk-products="npkProducts"
      :calcium-products="calciumProducts"
      :magnesium-products="magnesiumProducts"
      :micro-products="microProducts"
      @product-created="emit('product-created', $event)"
    />
    <RecipePhaseClimateFields v-model:phase="phase" />
    <RecipePhaseSolutionHealthFields v-model:phase="phase" />
    <RecipePhaseLightingFields v-model:phase="phase" />
  </section>
</template>

<script setup lang="ts">
import type { RecipePhaseFormState } from '@/composables/recipeEditorShared'
const phase = defineModel<RecipePhaseFormState>('phase', { required: true })

import TextField from '@/Components/TextField.vue'
import { durationDisplay, setDurationFromString } from '@/composables/recipePhaseFields'
import Button from '@/Components/Button.vue'
import RecipePhaseIrrigationFields from './RecipePhaseIrrigationFields.vue'
import RecipePhaseSolutionFields from './RecipePhaseSolutionFields.vue'
import RecipePhaseNutrientFields from './RecipePhaseNutrientFields.vue'
import RecipePhaseClimateFields from './RecipePhaseClimateFields.vue'
import RecipePhaseSolutionHealthFields from './RecipePhaseSolutionHealthFields.vue'
import RecipePhaseLightingFields from './RecipePhaseLightingFields.vue'
import type { NutrientProduct } from '@/types'
import type { RecipeIrrigationMode } from '@/composables/recipeEditorShared'
import type { SubstrateOption } from '@/composables/useRecipeIrrigation'
defineProps<{ index: number; canRemove: boolean; isAdvanced: boolean; recipeIrrigationMode: RecipeIrrigationMode; substrateOptions: SubstrateOption[]; npkProducts: NutrientProduct[]; calciumProducts: NutrientProduct[]; magnesiumProducts: NutrientProduct[]; microProducts: NutrientProduct[] }>()
const emit = defineEmits<{ remove: []; 'product-created': [product: NutrientProduct]; 'create-substrate': [] }>()
</script>
<style scoped src="./recipePhaseFields.css"></style>
