<template>
  <Modal
    :open="show"
    title="Калибровка дозирующих насосов"
    size="large"
    @close="$emit('close')"
  >
    <div class="space-y-4">
      <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-3 text-xs text-[color:var(--text-muted)]">
        <div>1. Запустите насос на заданное время и измерьте фактический объём.</div>
        <div>2. Для ΔEC-калибровки укажите объём тестового бака и EC до/после дозы (опционально).</div>
        <div>3. Сохраните калибровку в конфиг ноды: `ml_per_sec` и коэффициент `k` (если рассчитан).</div>
        <div>4. После сохранения форма автоматически переключится на следующий насос.</div>
      </div>

      <div
        v-if="pumpChannels.length === 0"
        class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-3 text-sm text-[color:var(--text-muted)]"
      >
        В зоне не найдено каналов актуаторов для калибровки.
      </div>

      <template v-else>
        <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
          <label class="text-xs text-[color:var(--text-muted)]">
            Компонент
            <select
              v-model="form.component"
              class="input-select mt-1 w-full"
              data-testid="pump-calibration-component"
            >
              <option
                v-for="option in componentOptions"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </option>
            </select>
          </label>

          <label class="text-xs text-[color:var(--text-muted)]">
            Канал помпы
            <select
              v-model.number="form.node_channel_id"
              class="input-select mt-1 w-full"
              data-testid="pump-calibration-channel"
            >
              <option
                v-for="channel in pumpChannels"
                :key="channel.id"
                :value="channel.id"
              >
                {{ channel.label }}
              </option>
            </select>
          </label>

          <label class="text-xs text-[color:var(--text-muted)]">
            Время запуска (сек)
            <input
              v-model.number="form.duration_sec"
              type="number"
              :min="pumpSettings.calibration_duration_min_sec"
              :max="pumpSettings.calibration_duration_max_sec"
              step="1"
              class="input-field mt-1 w-full"
              data-testid="pump-calibration-duration"
            />
          </label>

          <label class="text-xs text-[color:var(--text-muted)]">
            Фактический объём (мл)
            <input
              v-model.number="form.actual_ml"
              type="number"
              min="0.01"
              max="100000"
              step="0.01"
              class="input-field mt-1 w-full"
              data-testid="pump-calibration-actual-ml"
            />
          </label>

          <label class="text-xs text-[color:var(--text-muted)]">
            Объём теста (л)
            <input
              v-model.number="form.test_volume_l"
              type="number"
              min="0.1"
              max="1000"
              step="0.1"
              class="input-field mt-1 w-full"
              data-testid="pump-calibration-test-volume"
            />
          </label>

          <label class="text-xs text-[color:var(--text-muted)]">
            EC до дозы (mS/cm)
            <input
              v-model.number="form.ec_before_ms"
              type="number"
              min="0"
              max="20"
              step="0.001"
              class="input-field mt-1 w-full"
              data-testid="pump-calibration-ec-before"
            />
          </label>

          <label class="text-xs text-[color:var(--text-muted)]">
            EC после дозы (mS/cm)
            <input
              v-model.number="form.ec_after_ms"
              type="number"
              min="0"
              max="20"
              step="0.001"
              class="input-field mt-1 w-full"
              data-testid="pump-calibration-ec-after"
            />
          </label>

          <label class="text-xs text-[color:var(--text-muted)]">
            Температура (°C, опц.)
            <input
              v-model.number="form.temperature_c"
              type="number"
              min="0"
              max="50"
              step="0.1"
              class="input-field mt-1 w-full"
              data-testid="pump-calibration-temperature"
            />
          </label>
        </div>

        <div
          v-if="selectedCalibration"
          class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-3 text-xs text-[color:var(--text-muted)]"
          data-testid="pump-calibration-current"
        >
          <div class="font-medium text-[color:var(--text-primary)]">
            Текущая калибровка канала: {{ selectedChannel?.label }}
          </div>
          <div class="mt-1">
            {{ selectedCalibration.ml_per_sec ?? '-' }} мл/сек
            · {{ selectedCalibration.actual_ml ?? '-' }} мл за {{ selectedCalibration.duration_sec ?? '-' }} сек
          </div>
          <div
            v-if="selectedCalibration.k_ms_per_ml_l !== undefined && selectedCalibration.k_ms_per_ml_l !== null"
            class="mt-1"
          >
            k: {{ selectedCalibration.k_ms_per_ml_l }} mS/(мл/л)
          </div>
          <div
            v-if="selectedCalibration.calibrated_at"
            class="mt-1 text-[color:var(--text-dim)]"
          >
            Обновлено: {{ formatDateTime(selectedCalibration.calibrated_at) }}
          </div>
        </div>

        <div
          v-if="estimatedK !== null"
          class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-3 text-xs text-[color:var(--text-muted)]"
        >
          Расчёт k по введённым данным: <span class="font-semibold text-[color:var(--text-primary)]">{{ estimatedK.toFixed(6) }}</span> mS/(мл/л)
        </div>

        <div
          v-if="calibratedChannels.length > 0"
          class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-3"
        >
          <div class="text-xs font-medium text-[color:var(--text-primary)]">
            Сохранённые калибровки
          </div>
          <div class="mt-2 space-y-1 text-xs text-[color:var(--text-muted)]">
            <div
              v-for="channel in calibratedChannels"
              :key="`cal-${channel.id}`"
            >
              {{ channel.label }}:
              {{ channel.calibration?.ml_per_sec ?? '-' }} мл/сек
            </div>
          </div>
        </div>

        <div
          v-if="formError"
          class="text-sm text-[color:var(--accent-red)]"
          data-testid="pump-calibration-error"
        >
          {{ formError }}
        </div>

        <div class="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            :disabled="loadingRun"
            data-testid="pump-calibration-start-btn"
            @click="onStart"
          >
            {{ loadingRun ? 'Запуск...' : 'Запустить калибровку' }}
          </Button>
          <Button
            type="button"
            :disabled="loadingSave"
            data-testid="pump-calibration-save-btn"
            @click="onSave"
          >
            {{ loadingSave ? 'Сохранение...' : 'Сохранить фактический объём' }}
          </Button>
        </div>
      </template>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'
import { usePageProp } from '@/composables/usePageProps'
import type { Device } from '@/types'
import type { PumpCalibrationRunPayload, PumpCalibrationSavePayload } from '@/types/Calibration'
import { usePumpCalibration } from '@/composables/usePumpCalibration'
import type { PumpCalibrationSettings } from '@/types/SystemSettings'

interface Props {
  show?: boolean
  zoneId: number | null
  devices: Device[]
  loadingRun?: boolean
  loadingSave?: boolean
  saveSuccessSeq?: number
}

const props = withDefaults(defineProps<Props>(), {
  show: false,
  loadingRun: false,
  loadingSave: false,
  saveSuccessSeq: 0,
})

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'start', payload: PumpCalibrationRunPayload): void
  (e: 'save', payload: PumpCalibrationSavePayload): void
}>()

const pumpSettings = usePageProp<'pumpCalibrationSettings', PumpCalibrationSettings>('pumpCalibrationSettings')

const {
  form,
  formError,
  componentOptions,
  pumpChannels,
  channelById,
  selectedChannel,
  selectedCalibration,
  calibratedChannels,
  autoComponentMap,
  estimatedK,
  validateCommon,
  buildSavePayload,
  formatDateTime,
} = usePumpCalibration(props)

function onStart(): void {
  const err = validateCommon()
  if (err) {
    formError.value = err
    return
  }
  formError.value = null
  emit('start', {
    node_channel_id: form.node_channel_id!,
    duration_sec: Math.trunc(form.duration_sec),
    component: form.component,
  })
}

function onSave(): void {
  const err = validateCommon()
  if (err) {
    formError.value = err
    return
  }
  if (!Number.isFinite(form.actual_ml) || (form.actual_ml as number) <= 0) {
    formError.value = 'Введите фактический объём больше 0 мл.'
    return
  }
  formError.value = null
  emit('save', buildSavePayload())
}
</script>
