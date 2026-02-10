<template>
  <Modal
    :open="open"
    title="Редактирование автоматизации"
    size="large"
    @close="$emit('close')"
  >
    <div class="space-y-4">
      <div class="flex flex-wrap items-center gap-2">
        <button
          v-for="item in steps"
          :key="item.id"
          type="button"
          class="btn btn-outline h-9 px-3 text-xs"
          :class="item.id === step ? 'border-[color:var(--accent-green)] text-[color:var(--text-primary)]' : ''"
          @click="step = item.id"
        >
          {{ item.label }}
        </button>
      </div>

      <section
        v-if="step === 1"
        class="grid grid-cols-1 md:grid-cols-2 gap-3"
      >
        <label class="text-xs text-[color:var(--text-muted)]">
          Автоклимат
          <select
            v-model="climateForm.enabled"
            class="input-select mt-1 w-full"
          >
            <option :value="true">Включен</option>
            <option :value="false">Выключен</option>
          </select>
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Температура день
          <input
            v-model.number="climateForm.dayTemp"
            type="number"
            min="10"
            max="35"
            step="0.5"
            class="input-field mt-1 w-full"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Температура ночь
          <input
            v-model.number="climateForm.nightTemp"
            type="number"
            min="10"
            max="35"
            step="0.5"
            class="input-field mt-1 w-full"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Влажность день
          <input
            v-model.number="climateForm.dayHumidity"
            type="number"
            min="30"
            max="90"
            class="input-field mt-1 w-full"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Влажность ночь
          <input
            v-model.number="climateForm.nightHumidity"
            type="number"
            min="30"
            max="90"
            class="input-field mt-1 w-full"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Min форточек (%)
          <input
            v-model.number="climateForm.ventMinPercent"
            type="number"
            min="0"
            max="100"
            class="input-field mt-1 w-full"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Max форточек (%)
          <input
            v-model.number="climateForm.ventMaxPercent"
            type="number"
            min="0"
            max="100"
            class="input-field mt-1 w-full"
          />
        </label>
      </section>

      <section
        v-else-if="step === 2"
        class="space-y-3"
      >
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
          <label class="text-xs text-[color:var(--text-muted)]">
            Тип системы
            <select
              v-model="waterForm.systemType"
              class="input-select mt-1 w-full"
              :disabled="isSystemTypeLocked"
            >
              <option value="drip">drip</option>
              <option value="substrate_trays">substrate_trays</option>
              <option value="nft">nft</option>
            </select>
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            target pH
            <input
              v-model.number="waterForm.targetPh"
              type="number"
              min="4"
              max="9"
              step="0.1"
              class="input-field mt-1 w-full"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            target EC
            <input
              v-model.number="waterForm.targetEc"
              type="number"
              min="0.1"
              max="10"
              step="0.1"
              class="input-field mt-1 w-full"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Интервал полива (мин)
            <input
              v-model.number="waterForm.intervalMinutes"
              type="number"
              min="5"
              max="1440"
              class="input-field mt-1 w-full"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Длительность (сек)
            <input
              v-model.number="waterForm.durationSeconds"
              type="number"
              min="1"
              max="3600"
              class="input-field mt-1 w-full"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Баков
            <input
              v-model.number="waterForm.tanksCount"
              type="number"
              min="2"
              max="3"
              class="input-field mt-1 w-full"
            />
          </label>
        </div>
        <p
          v-if="isSystemTypeLocked"
          class="text-xs text-[color:var(--text-dim)]"
        >
          Тип системы нельзя менять в активном цикле. Он задаётся только при старте.
        </p>
      </section>

      <section
        v-else
        class="grid grid-cols-1 md:grid-cols-3 gap-3"
      >
        <label class="text-xs text-[color:var(--text-muted)]">
          Досветка
          <select
            v-model="lightingForm.enabled"
            class="input-select mt-1 w-full"
          >
            <option :value="true">Включена</option>
            <option :value="false">Выключена</option>
          </select>
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Lux day
          <input
            v-model.number="lightingForm.luxDay"
            type="number"
            min="0"
            max="120000"
            class="input-field mt-1 w-full"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Lux night
          <input
            v-model.number="lightingForm.luxNight"
            type="number"
            min="0"
            max="120000"
            class="input-field mt-1 w-full"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Часов света
          <input
            v-model.number="lightingForm.hoursOn"
            type="number"
            min="0"
            max="24"
            step="0.5"
            class="input-field mt-1 w-full"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Начало
          <input
            v-model="lightingForm.scheduleStart"
            type="time"
            class="input-field mt-1 w-full"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Конец
          <input
            v-model="lightingForm.scheduleEnd"
            type="time"
            class="input-field mt-1 w-full"
          />
        </label>
      </section>
    </div>

    <template #footer>
      <Button
        type="button"
        variant="outline"
        @click="$emit('reset')"
      >
        Сбросить к рецепту
      </Button>
      <Button
        v-if="step > 1"
        type="button"
        variant="secondary"
        @click="step = step - 1"
      >
        Назад
      </Button>
      <Button
        v-if="step < 3"
        type="button"
        @click="step = step + 1"
      >
        Далее
      </Button>
      <Button
        v-else
        type="button"
        :disabled="isApplying"
        @click="$emit('apply')"
      >
        {{ isApplying ? 'Отправка...' : 'Сохранить' }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'
import type {
  ClimateFormState,
  LightingFormState,
  WaterFormState,
} from '@/composables/zoneAutomationTypes'

interface Props {
  open: boolean
  climateForm: ClimateFormState
  waterForm: WaterFormState
  lightingForm: LightingFormState
  isApplying: boolean
  isSystemTypeLocked: boolean
}

defineEmits<{
  (e: 'close'): void
  (e: 'apply'): void
  (e: 'reset'): void
}>()

const props = defineProps<Props>()

const steps = [
  { id: 1, label: 'Климат' },
  { id: 2, label: 'Водный узел' },
  { id: 3, label: 'Досветка' },
] as const

const step = ref<1 | 2 | 3>(1)

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      step.value = 1
    }
  },
)
</script>
