<template>
  <Modal
    :open="show"
    title="Сохранить как профиль автоматики"
    size="large"
    data-testid="save-preset-wizard"
    @close="$emit('close')"
  >
    <div class="space-y-4">
      <p class="text-xs text-[color:var(--text-muted)]">
        Сохраните текущую конфигурацию автоматики как профиль для быстрого применения на других зонах.
      </p>

      <!-- Шаг 1: Имя и описание -->
      <div class="space-y-3">
        <label class="block">
          <span class="text-xs font-medium text-[color:var(--text-primary)]">Название профиля *</span>
          <input
            v-model="form.name"
            type="text"
            class="input-field mt-1 w-full"
            placeholder="Например: Томаты DWC — агрессивная коррекция"
            data-testid="preset-name-input"
          />
        </label>

        <label class="block">
          <span class="text-xs font-medium text-[color:var(--text-primary)]">Описание</span>
          <textarea
            v-model="form.description"
            class="input-field mt-1 w-full"
            rows="3"
            placeholder="Опишите для какой системы и условий подходит этот профиль. Например: тип полива, объём бака, особенности коррекции..."
            data-testid="preset-description-input"
          ></textarea>
          <span class="mt-0.5 block text-[10px] text-[color:var(--text-dim)]">
            Хорошее описание поможет вам и коллегам быстро понять назначение профиля.
          </span>
        </label>
      </div>

      <!-- Шаг 2: Обзор параметров -->
      <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-main)] p-3 space-y-2">
        <div class="text-xs font-medium text-[color:var(--text-primary)]">Что будет сохранено:</div>

        <div class="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
          <div class="text-[color:var(--text-muted)]">Тип системы</div>
          <div class="text-[color:var(--text-primary)]">{{ irrigationSystemType }}</div>

          <div class="text-[color:var(--text-muted)]">Количество баков</div>
          <div class="text-[color:var(--text-primary)]">{{ waterForm.tanksCount }}</div>

          <div class="text-[color:var(--text-muted)]">Профиль коррекции</div>
          <div class="text-[color:var(--text-primary)]">{{ correctionProfileLabel }}</div>

          <div class="mt-1 col-span-2 border-t border-[color:var(--border-muted)] pt-1 text-[10px] font-medium text-[color:var(--text-muted)]">
            Полив
          </div>

          <div class="text-[color:var(--text-muted)]">Интервал полива</div>
          <div class="text-[color:var(--text-primary)]">{{ waterForm.intervalMinutes }} мин</div>

          <div class="text-[color:var(--text-muted)]">Длительность полива</div>
          <div class="text-[color:var(--text-primary)]">{{ waterForm.durationSeconds }} сек</div>

          <div class="text-[color:var(--text-muted)]">Коррекция во время полива</div>
          <div class="text-[color:var(--text-primary)]">{{ waterForm.correctionDuringIrrigation ? 'Да' : 'Нет' }}</div>

          <div class="text-[color:var(--text-muted)]">Стратегия решения</div>
          <div class="text-[color:var(--text-primary)]">{{ waterForm.irrigationDecisionStrategy ?? 'task' }}</div>

          <div class="mt-1 col-span-2 border-t border-[color:var(--border-muted)] pt-1 text-[10px] font-medium text-[color:var(--text-muted)]">
            Таймауты запуска
          </div>

          <div class="text-[color:var(--text-muted)]">Заполнение чистой воды</div>
          <div class="text-[color:var(--text-primary)]">{{ formatTimeout(waterForm.startupCleanFillTimeoutSeconds) }}</div>

          <div class="text-[color:var(--text-muted)]">Заполнение раствора</div>
          <div class="text-[color:var(--text-primary)]">{{ formatTimeout(waterForm.startupSolutionFillTimeoutSeconds) }}</div>

          <div class="text-[color:var(--text-muted)]">Рециркуляция</div>
          <div class="text-[color:var(--text-primary)]">{{ formatTimeout(waterForm.startupPrepareRecirculationTimeoutSeconds) }}</div>
        </div>
      </div>

      <!-- Ошибка -->
      <div
        v-if="error"
        class="rounded-lg border border-[color:var(--badge-error-border)] bg-[color:var(--badge-error-bg)] p-2 text-xs text-[color:var(--badge-error-text)]"
      >
        {{ error }}
      </div>
    </div>

    <template #footer>
      <Button
        size="sm"
        :disabled="!canSave || saving"
        data-testid="save-preset-confirm"
        @click="save"
      >
        {{ saving ? 'Сохранение...' : 'Сохранить профиль' }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'
import type { WaterFormState } from '@/composables/zoneAutomationTypes'
import type { ZoneAutomationPreset, IrrigationSystemType, CorrectionProfile } from '@/types/ZoneAutomationPreset'
import { buildPresetFromWaterForm } from '@/composables/useZoneAutomationPresets'
import { api } from '@/services/api'

const props = defineProps<{
  show: boolean
  waterForm: WaterFormState
  irrigationSystemType: IrrigationSystemType
  correctionPresetId?: number | null
  correctionProfile?: CorrectionProfile | null
}>()

const emit = defineEmits<{
  close: []
  saved: [preset: ZoneAutomationPreset]
}>()

const form = ref({
  name: '',
  description: '',
})

const saving = ref(false)
const error = ref<string | null>(null)

const canSave = computed(() => form.value.name.trim().length > 0)

const correctionProfileLabel = computed(() => {
  const labels: Record<string, string> = {
    safe: 'Мягкий',
    balanced: 'Оптимальный',
    aggressive: 'Агрессивный',
    test: 'Тестовый',
  }
  return props.correctionProfile ? labels[props.correctionProfile] ?? props.correctionProfile : 'Не выбран'
})

function formatTimeout(seconds?: number): string {
  if (seconds === undefined || seconds === null) return '—'
  if (seconds < 60) return `${seconds} сек`
  return `${Math.round(seconds / 60)} мин`
}

async function save() {
  if (!canSave.value) return

  saving.value = true
  error.value = null

  try {
    const payload = buildPresetFromWaterForm(props.waterForm, {
      name: form.value.name.trim(),
      description: form.value.description.trim() || null,
      irrigationSystemType: props.irrigationSystemType,
      correctionPresetId: props.correctionPresetId,
      correctionProfile: props.correctionProfile,
    })

    const created = await api.zoneAutomationPresets.create(payload)
    form.value.name = ''
    form.value.description = ''
    emit('saved', created)
    emit('close')
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Не удалось сохранить профиль'
  } finally {
    saving.value = false
  }
}
</script>
