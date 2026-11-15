<template>
  <div class="rounded-md border border-[color:var(--border-muted)] p-2.5 space-y-2">
    <div class="text-[12px] font-bold uppercase tracking-[0.16em] text-[color:var(--text-muted)]">
      Климат
    </div>
    <!-- Режим: одно значение на день+ночь -->
    <div
      v-if="!phase.day_night_enabled"
      class="grid grid-cols-2 gap-3 max-w-md"
    >
      <div>
        <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Температура, °C</label>
        <div class="stepper">
          <button
            type="button"
            class="stepper__btn"
            @click="phase.temp_air_target = +((phase.temp_air_target ?? 0) - 0.5).toFixed(1)"
          >
            −
          </button>
          <input
            v-model.number="phase.temp_air_target"
            type="number"
            step="0.1"
            class="stepper__input"
          />
          <button
            type="button"
            class="stepper__btn"
            @click="phase.temp_air_target = +((phase.temp_air_target ?? 0) + 0.5).toFixed(1)"
          >
            +
          </button>
        </div>
      </div>
      <div>
        <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Влажность, %</label>
        <div class="stepper">
          <button
            type="button"
            class="stepper__btn"
            @click="phase.humidity_target = Math.max(0, (phase.humidity_target ?? 0) - 1)"
          >
            −
          </button>
          <input
            v-model.number="phase.humidity_target"
            type="number"
            step="1"
            class="stepper__input"
          />
          <button
            type="button"
            class="stepper__btn"
            @click="phase.humidity_target = Math.min(100, (phase.humidity_target ?? 0) + 1)"
          >
            +
          </button>
        </div>
      </div>
    </div>
    <!-- Режим: раздельно день/ночь — таблица -->
    <div
      v-else
      class="grid grid-cols-[140px_1fr_1fr] gap-x-3 gap-y-2 items-center max-w-lg"
    >
      <div></div>
      <div class="text-[10px] text-[color:var(--text-dim)] uppercase tracking-wider text-center">
        ☀ день
      </div>
      <div class="text-[10px] text-[color:var(--text-dim)] uppercase tracking-wider text-center">
        ☾ ночь
      </div>
      <label class="text-[12px] text-[color:var(--text-primary)] font-medium">Температура, °C</label>
      <div class="stepper">
        <button
          type="button"
          class="stepper__btn"
          @click="phase.day_night.temperature.day = +((phase.day_night.temperature.day ?? 0) - 0.5).toFixed(1)"
        >
          −
        </button>
        <input
          v-model.number="phase.day_night.temperature.day"
          type="number"
          step="0.1"
          class="stepper__input"
        />
        <button
          type="button"
          class="stepper__btn"
          @click="phase.day_night.temperature.day = +((phase.day_night.temperature.day ?? 0) + 0.5).toFixed(1)"
        >
          +
        </button>
      </div>
      <div class="stepper">
        <button
          type="button"
          class="stepper__btn"
          @click="phase.day_night.temperature.night = +((phase.day_night.temperature.night ?? 0) - 0.5).toFixed(1)"
        >
          −
        </button>
        <input
          v-model.number="phase.day_night.temperature.night"
          type="number"
          step="0.1"
          class="stepper__input"
        />
        <button
          type="button"
          class="stepper__btn"
          @click="phase.day_night.temperature.night = +((phase.day_night.temperature.night ?? 0) + 0.5).toFixed(1)"
        >
          +
        </button>
      </div>
      <label class="text-[12px] text-[color:var(--text-primary)] font-medium">Влажность, %</label>
      <div class="stepper">
        <button
          type="button"
          class="stepper__btn"
          @click="phase.day_night.humidity.day = Math.max(0, (phase.day_night.humidity.day ?? 0) - 1)"
        >
          −
        </button>
        <input
          v-model.number="phase.day_night.humidity.day"
          type="number"
          step="1"
          class="stepper__input"
        />
        <button
          type="button"
          class="stepper__btn"
          @click="phase.day_night.humidity.day = Math.min(100, (phase.day_night.humidity.day ?? 0) + 1)"
        >
          +
        </button>
      </div>
      <div class="stepper">
        <button
          type="button"
          class="stepper__btn"
          @click="phase.day_night.humidity.night = Math.max(0, (phase.day_night.humidity.night ?? 0) - 1)"
        >
          −
        </button>
        <input
          v-model.number="phase.day_night.humidity.night"
          type="number"
          step="1"
          class="stepper__input"
        />
        <button
          type="button"
          class="stepper__btn"
          @click="phase.day_night.humidity.night = Math.min(100, (phase.day_night.humidity.night ?? 0) + 1)"
        >
          +
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { RecipePhaseFormState } from '@/composables/recipeEditorShared'
const phase = defineModel<RecipePhaseFormState>('phase', { required: true })

</script>
