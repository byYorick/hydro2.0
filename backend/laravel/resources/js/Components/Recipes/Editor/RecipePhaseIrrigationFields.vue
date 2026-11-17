<template>
  <div class="rounded-md border border-[color:var(--border-muted)] p-3 space-y-3">
    <div class="text-[12px] font-bold uppercase tracking-[0.16em] text-[color:var(--text-muted)]">
      Полив
    </div>
    <div
      v-if="isAdvanced"
      class="grid grid-cols-1 md:grid-cols-4 gap-4"
    >
      <div>
        <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Тип системы полива</label>
        <SelectField
          v-model="phase.irrigation_system_type"
          class="w-full"
        >
          <template v-if="recipeIrrigationMode === 'SUBSTRATE'">
            <option value="drip_tape">
              Капельная лента
            </option>
            <option value="drip_emitter">
              Капельные форсунки
            </option>
          </template>
          <template v-else>
            <option value="nft">
              NFT (Nutrient Film)
            </option>
            <option value="dwc">
              DWC (Deep Water Culture)
            </option>
            <option value="ebb_flow">
              Прилив-отлив (ebb &amp; flow)
            </option>
            <option value="aeroponics">
              Аэропоника
            </option>
          </template>
        </SelectField>
      </div>
      <div>
        <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Субстрат</label>
        <div class="flex gap-2">
          <SelectField
            v-model="phase.substrate_type"
            class="flex-1 min-w-0"
            :disabled="substrateOptions.length === 0"
          >
            <option
              v-for="opt in substrateOptions"
              :key="opt.value ?? 'null'"
              :value="opt.value"
            >
              {{ opt.label }}
            </option>
          </SelectField>
          <button
            type="button"
            class="pill-btn"
            title="Создать новый субстрат"
            @click="emit('create-substrate')"
          >
            <svg
              class="w-4 h-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            ><line
              x1="12"
              y1="5"
              x2="12"
              y2="19"
            /><line
              x1="5"
              y1="12"
              x2="19"
              y2="12"
            /></svg>
          </button>
        </div>
      </div>
      <!-- Влажность субстрата: одно поле или раздельные день/ночь -->
      <div v-if="recipeIrrigationMode === 'SUBSTRATE' && !phase.day_night_enabled">
        <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Влажность субстрата, %</label>
        <div class="stepper">
          <button
            type="button"
            class="stepper__btn"
            @click="phase.day_night.soil_moisture.day = Math.max(0, (phase.day_night.soil_moisture.day ?? 0) - 1)"
          >
            −
          </button>
          <input
            :value="phase.day_night.soil_moisture.day ?? ''"
            type="number"
            min="0"
            max="100"
            step="1"
            class="stepper__input"
            @input="setMoisture('day', $event)"
          />
          <button
            type="button"
            class="stepper__btn"
            @click="phase.day_night.soil_moisture.day = Math.min(100, (phase.day_night.soil_moisture.day ?? 0) + 1)"
          >
            +
          </button>
        </div>
      </div>
      <template v-if="recipeIrrigationMode === 'SUBSTRATE' && phase.day_night_enabled">
        <div>
          <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">☀ Влажность день, %</label>
          <div class="stepper">
            <button
              type="button"
              class="stepper__btn"
              @click="phase.day_night.soil_moisture.day = Math.max(0, (phase.day_night.soil_moisture.day ?? 0) - 1)"
            >
              −
            </button>
            <input
              :value="phase.day_night.soil_moisture.day ?? ''"
              type="number"
              min="0"
              max="100"
              step="1"
              class="stepper__input"
              @input="setMoisture('day', $event)"
            />
            <button
              type="button"
              class="stepper__btn"
              @click="phase.day_night.soil_moisture.day = Math.min(100, (phase.day_night.soil_moisture.day ?? 0) + 1)"
            >
              +
            </button>
          </div>
        </div>
        <div>
          <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">☾ Влажность ночь, %</label>
          <div class="stepper">
            <button
              type="button"
              class="stepper__btn"
              @click="phase.day_night.soil_moisture.night = Math.max(0, (phase.day_night.soil_moisture.night ?? 0) - 1)"
            >
              −
            </button>
            <input
              :value="phase.day_night.soil_moisture.night ?? ''"
              type="number"
              min="0"
              max="100"
              step="1"
              class="stepper__input"
              @input="setMoisture('night', $event)"
            />
            <button
              type="button"
              class="stepper__btn"
              @click="phase.day_night.soil_moisture.night = Math.min(100, (phase.day_night.soil_moisture.night ?? 0) + 1)"
            >
              +
            </button>
          </div>
        </div>
      </template>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-lg">
      <div>
        <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Интервал между поливами (ЧЧ:ММ)</label>
        <TextField
          :model-value="intervalDisplay(phase)"
          :error="Number.isNaN(phase.irrigation_interval_sec) ? 'Укажите часы и минуты: ЧЧ:ММ, минуты от 00 до 59.' : ''"
          type="text"
          placeholder="00 : 00"
          class="!w-32"
          input-class="text-center tracking-widest"
          @change="setIntervalFromString(phase, ($event.target as HTMLInputElement).value)"
        />
        <p class="text-[12px] text-[color:var(--text-muted)] mt-1 leading-snug">
          Время между началами циклов полива
        </p>
      </div>
      <div>
        <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Длительность полива (ММ:СС)</label>
        <TextField
          :model-value="durationIrrigDisplay(phase)"
          :error="Number.isNaN(phase.irrigation_duration_sec) ? 'Укажите минуты и секунды: ММ:СС, секунды от 00 до 59.' : ''"
          type="text"
          placeholder="00 : 00"
          class="!w-28"
          input-class="text-center tracking-widest"
          @change="setDurationIrrigFromString(phase, ($event.target as HTMLInputElement).value)"
        />
        <p class="text-[12px] text-[color:var(--text-muted)] mt-1 leading-snug">
          Сколько длится один цикл полива (подача раствора)
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { RecipePhaseFormState } from '@/composables/recipeEditorShared'
const phase = defineModel<RecipePhaseFormState>('phase', { required: true })
import SelectField from '@/Components/SelectField.vue'
import TextField from '@/Components/TextField.vue'
import { intervalDisplay, setIntervalFromString, durationIrrigDisplay, setDurationIrrigFromString } from '@/composables/recipePhaseFields'
import type { RecipeIrrigationMode } from '@/composables/recipeEditorShared'
import type { SubstrateOption } from '@/composables/useRecipeIrrigation'
defineProps<{ isAdvanced: boolean; recipeIrrigationMode: RecipeIrrigationMode; substrateOptions: SubstrateOption[] }>()
const emit = defineEmits<{ 'create-substrate': [] }>()
function setMoisture(profile: 'day' | 'night', event: Event) {
  const input = event.target as HTMLInputElement
  phase.value.day_night.soil_moisture[profile] = input.validity.badInput
    ? Number.NaN : input.value.trim() === '' ? null : Number(input.value)
}
</script>
