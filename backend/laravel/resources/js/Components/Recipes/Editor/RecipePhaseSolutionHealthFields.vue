<template>
  <div class="rounded-md border border-[color:var(--border-muted)] p-2.5 space-y-2">
    <div class="text-[12px] font-bold uppercase tracking-[0.16em] text-[color:var(--text-muted)]">
      Температура раствора и подмена
    </div>
    <label class="flex items-center gap-2 text-[12px] text-[color:var(--text-primary)] font-medium">
      <input
        v-model="phase.solution_health_required"
        type="checkbox"
      />
      Температура раствора обязательна
    </label>
    <p class="text-[12px] text-[color:var(--text-muted)] m-0 leading-snug">
      Включается только вместе с min и max. Непрерывный выход за границы дольше удержания пропускает новый полив и не помечает задачу сбоем.
    </p>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-3 max-w-xl">
      <div>
        <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Мин. температура раствора, °C</label>
        <TextField
          type="number"
          step="0.1"
          :model-value="cropDayInputValue(phase.solution_temp_min)"
          @input="setCropDayNumber(phase, 'solution_temp_min', $event)"
        />
      </div>
      <div>
        <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Макс. температура раствора, °C</label>
        <TextField
          type="number"
          step="0.1"
          :model-value="cropDayInputValue(phase.solution_temp_max)"
          @input="setCropDayNumber(phase, 'solution_temp_max', $event)"
        />
      </div>
      <div>
        <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Удержание выхода за пределы, сек</label>
        <TextField
          type="number"
          step="1"
          :model-value="cropDayInputValue(phase.solution_health_breach_hold_sec)"
          @input="setCropDayNumber(phase, 'solution_health_breach_hold_sec', $event)"
        />
      </div>
      <div>
        <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Возраст раствора до рекомендации, дни</label>
        <TextField
          type="number"
          step="1"
          :model-value="cropDayInputValue(phase.solution_max_age_days)"
          @input="setCropDayNumber(phase, 'solution_max_age_days', $event)"
        />
      </div>
      <div>
        <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Объём доливов до рекомендации, мл</label>
        <TextField
          type="number"
          step="1"
          :model-value="cropDayInputValue(phase.solution_refresh_after_topup_ml)"
          @input="setCropDayNumber(phase, 'solution_refresh_after_topup_ml', $event)"
        />
      </div>
    </div>
    <p class="text-[12px] text-[color:var(--text-muted)] m-0 leading-snug">
      Пустое поле выключает порог и уходит как пустое, не как ноль.
    </p>
  </div>
</template>

<script setup lang="ts">
import type { RecipePhaseFormState } from '@/composables/recipeEditorShared'
const phase = defineModel<RecipePhaseFormState>('phase', { required: true })

import TextField from '@/Components/TextField.vue'
import { cropDayInputValue, setCropDayNumber } from '@/composables/recipePhaseFields'
</script>
