<template>
  <div class="rounded-md border border-[color:var(--border-muted)] p-2.5 space-y-2">
    <div class="text-[12px] font-bold uppercase tracking-[0.16em] text-[color:var(--text-muted)]">
      Свет
    </div>
    <div class="grid grid-cols-2 md:grid-cols-2 gap-3 max-w-md">
      <div>
        <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Фотопериод, часов</label>
        <div class="stepper">
          <button
            type="button"
            class="stepper__btn"
            @click="phase.lighting_photoperiod_hours = Math.max(0, (phase.lighting_photoperiod_hours ?? 0) - 1)"
          >
            −
          </button>
          <input
            v-model.number="phase.lighting_photoperiod_hours"
            type="number"
            min="0"
            max="24"
            class="stepper__input"
          />
          <button
            type="button"
            class="stepper__btn"
            @click="phase.lighting_photoperiod_hours = Math.min(24, (phase.lighting_photoperiod_hours ?? 0) + 1)"
          >
            +
          </button>
        </div>
      </div>
      <div>
        <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Старт дня</label>
        <TextField
          v-model="phase.lighting_start_time"
          type="time"
        />
      </div>
      <div class="col-span-2">
        <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">DLI, моль/м²·сутки</label>
        <TextField
          data-testid="recipe-phase-dli-target"
          type="number"
          step="0.01"
          :model-value="cropDayInputValue(phase.dli_target)"
          @input="setCropDayNumber(phase, 'dli_target', $event)"
        />
        <p class="text-[12px] text-[color:var(--text-muted)] mt-1 mb-0 leading-snug">
          Нужен канал с единицей PPFD. Люксы не пересчитываются. Если цель задана, внутри окна появятся проверочные тики света.
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { RecipePhaseFormState } from '@/composables/recipeEditorShared'
const phase = defineModel<RecipePhaseFormState>('phase', { required: true })

import TextField from '@/Components/TextField.vue'
import { cropDayInputValue, setCropDayNumber } from '@/composables/recipePhaseFields'
</script>
