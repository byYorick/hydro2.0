<template>
  <Modal
    :open="show"
    title="Калибровка дозирующих насосов"
    size="large"
    @close="$emit('close')"
  >
    <div class="pump-calibration-modal space-y-4">
      <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-3">
        <div class="text-xs font-medium text-[color:var(--text-primary)]">
          Порядок калибровки
        </div>
        <div class="mt-2 grid gap-2 text-xs text-[color:var(--text-muted)] md:grid-cols-2">
          <div>1. Выберите компонент, канал и время тестового запуска.</div>
          <div>2. Запустите насос и измерьте фактический объём дозы.</div>
          <div>3. Для ΔEC-калибровки при необходимости заполните тестовый бак и EC до/после дозы.</div>
          <div>4. Сохраните `ml_per_sec` и, если рассчитан, коэффициент `k`.</div>
        </div>
      </div>

      <div
        v-if="pumpChannels.length === 0"
        class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-3 text-sm text-[color:var(--text-muted)]"
      >
        В зоне не найдено каналов актуаторов для калибровки.
      </div>

      <template v-else>
        <div class="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(19rem,0.85fr)]">
          <section class="space-y-4">
            <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-3">
              <div class="text-sm font-semibold text-[color:var(--text-primary)]">
                1. Выбор насоса
              </div>
              <div class="mt-1 text-xs text-[color:var(--text-dim)]">
                Сначала зафиксируйте, какой dosing-компонент и какой канал сейчас калибруете.
              </div>
              <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('component')"
                >
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

                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('node_channel_id')"
                >
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

                <label
                  class="text-xs text-[color:var(--text-muted)] md:col-span-2"
                  :title="fieldHelp('duration_sec')"
                >
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
              </div>
            </div>

            <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-3">
              <div class="text-sm font-semibold text-[color:var(--text-primary)]">
                2. Измерение дозы
              </div>
              <div class="mt-1 text-xs text-[color:var(--text-dim)]">
                Для базовой калибровки обязателен только фактический объём. ΔEC-поля заполняйте, если хотите сразу оценить `k`.
              </div>
              <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('actual_ml')"
                >
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

                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('temperature_c')"
                >
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

                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('test_volume_l')"
                >
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

                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('ec_before_ms')"
                >
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

                <label
                  class="text-xs text-[color:var(--text-muted)] md:col-span-2"
                  :title="fieldHelp('ec_after_ms')"
                >
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
              </div>
            </div>

            <div
              v-if="formError"
              class="rounded-xl border border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)] p-3 text-sm text-[color:var(--badge-danger-text)]"
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
          </section>

          <section class="space-y-4">
            <div
              class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-3 text-xs text-[color:var(--text-muted)]"
              data-testid="pump-calibration-current"
            >
              <div class="text-sm font-semibold text-[color:var(--text-primary)]">
                3. Текущий канал
              </div>
              <div class="mt-1">
                {{ selectedChannel?.label ?? 'Канал ещё не выбран' }}
              </div>
              <template v-if="selectedCalibration">
                <div class="mt-3 font-medium text-[color:var(--text-primary)]">
                  Сохранённая калибровка
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
              </template>
              <div
                v-else
                class="mt-3 rounded-lg bg-[color:var(--bg-elevated)] px-3 py-2 text-[color:var(--text-dim)]"
              >
                Для выбранного канала ещё нет сохранённой калибровки.
              </div>
            </div>

            <div
              class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-3 text-xs text-[color:var(--text-muted)]"
              data-testid="pump-calibration-readiness"
            >
              <div class="text-sm font-semibold text-[color:var(--text-primary)]">
                4. Влияние на correction runtime
              </div>
              <div class="mt-1">
                Выбранный компонент относится к {{ currentPathLabel }}.
              </div>
              <div class="mt-2 flex flex-wrap gap-2">
                <span
                  v-for="item in currentPathStatuses"
                  :key="item.component"
                  class="inline-flex items-center rounded-full border px-2 py-1"
                  :class="item.calibrated ? 'border-[color:var(--accent-green)] text-[color:var(--accent-green)]' : (item.current ? 'border-[color:var(--accent-yellow)] text-[color:var(--accent-yellow)]' : 'border-[color:var(--border-muted)] text-[color:var(--text-dim)]')"
                >
                  {{ item.label }}: {{ item.stateLabel }}
                </span>
              </div>
              <div class="mt-2">
                {{ currentPathSummary }}
              </div>
            </div>

            <div
              v-if="estimatedK !== null"
              class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-3 text-xs text-[color:var(--text-muted)]"
            >
              <div class="text-sm font-semibold text-[color:var(--text-primary)]">
                5. Расчёт коэффициента
              </div>
              <div class="mt-1">
                Расчётный `k` по введённым данным:
                <span class="font-semibold text-[color:var(--text-primary)]">{{ estimatedK.toFixed(6) }}</span>
                mS/(мл/л)
              </div>
            </div>

            <div
              v-if="calibratedChannels.length > 0"
              class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-3"
            >
              <div class="text-sm font-semibold text-[color:var(--text-primary)]">
                6. Уже сохранено
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
          </section>
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
import type { PumpCalibrationComponent, PumpCalibrationRunPayload, PumpCalibrationSavePayload } from '@/types/Calibration'
import { usePumpCalibration } from '@/composables/usePumpCalibration'
import type { PumpCalibrationSettings } from '@/types/SystemSettings'
import { computed } from 'vue'

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

const FIELD_HELP: Record<string, string> = {
  component: 'Какой dosing-компонент калибруется. От выбора зависит correction path и проверка готовности runtime.',
  node_channel_id: 'Конкретный actuator channel, на который будет отправлена команда запуска насоса и в который сохранится новая калибровка.',
  duration_sec: 'Сколько секунд крутить насос при тестовом запуске. По измеренному объёму рассчитывается ml_per_sec.',
  actual_ml: 'Фактически измеренный объём после тестового прогона. Это основной источник расчёта скорости насоса.',
  test_volume_l: 'Объём тестового бака для расчёта EC-коэффициента k. Нужен только для ΔEC-калибровки.',
  ec_before_ms: 'EC раствора до дозы. Вместе с объёмом бака и EC после дозы позволяет оценить коэффициент k.',
  ec_after_ms: 'EC раствора после дозы. Используется для вычисления k, если заполнены остальные тестовые данные.',
  temperature_c: 'Температура раствора во время теста. Сейчас хранится как метаданные для повторяемости калибровки.',
}

function fieldHelp(key: string): string {
  return FIELD_HELP[key] ?? 'Параметр pump calibration.'
}

const rawPumpSettings = usePageProp<'pumpCalibrationSettings', PumpCalibrationSettings>('pumpCalibrationSettings')
const pumpSettings = computed<PumpCalibrationSettings>(() => ({
  ml_per_sec_min: 0.001,
  ml_per_sec_max: 1000,
  min_dose_ms: 1,
  calibration_duration_min_sec: 1,
  calibration_duration_max_sec: 60,
  quality_score_basic: 0.5,
  quality_score_with_k: 0.8,
  quality_score_legacy: 0.3,
  age_warning_days: 30,
  age_critical_days: 60,
  default_run_duration_sec: 20,
  ...(rawPumpSettings.value || {}),
}))

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

const pathDefinitions: Record<'ph' | 'ec', { label: string; components: PumpCalibrationComponent[] }> = {
  ph: {
    label: 'pH dosing path',
    components: ['ph_up', 'ph_down'],
  },
  ec: {
    label: 'EC dosing path',
    components: ['npk', 'calcium', 'magnesium', 'micro'],
  },
}

const componentLabels: Record<PumpCalibrationComponent, string> = {
  npk: 'NPK',
  calcium: 'Calcium',
  magnesium: 'Magnesium',
  micro: 'Micro',
  ph_up: 'pH Up',
  ph_down: 'pH Down',
}

const currentPathKey = computed<'ph' | 'ec'>(() => (form.component === 'ph_up' || form.component === 'ph_down' ? 'ph' : 'ec'))
const currentPathLabel = computed(() => pathDefinitions[currentPathKey.value].label)

function isChannelCalibrated(channelId: number | null | undefined): boolean {
  if (!channelId) {
    return false
  }

  const channel = channelById.value.get(channelId)
  return Boolean(channel?.calibration && Number(channel.calibration.ml_per_sec) > 0)
}

const currentPathStatuses = computed(() => {
  return pathDefinitions[currentPathKey.value].components.map((component) => {
    const current = component === form.component
    const mappedChannelId = current ? form.node_channel_id : autoComponentMap.value[component]
    const calibrated = isChannelCalibrated(mappedChannelId)

    return {
      component,
      label: componentLabels[component],
      current,
      calibrated,
      stateLabel: calibrated
        ? 'Откалиброван'
        : (current ? 'Текущий выбор без сохранённой калибровки' : 'Нет калибровки'),
    }
  })
})

const currentPathSummary = computed(() => {
  const missing = currentPathStatuses.value.filter((item) => !item.calibrated)
  const currentSelected = currentPathStatuses.value.find((item) => item.current)

  if (missing.length === 0) {
    return `${currentPathLabel.value} уже закрыт полностью. Сохранение обновит существующую калибровку для выбранного компонента.`
  }

  if (currentSelected && !currentSelected.calibrated) {
    const remaining = missing.filter((item) => !item.current)
    if (remaining.length === 0) {
      return `После сохранения этот компонент закроет последний пробел в ${currentPathLabel.value}.`
    }

    return `После сохранения этот компонент перестанет блокировать ${currentPathLabel.value}. Затем останутся: ${remaining.map((item) => item.label).join(', ')}.`
  }

  return `Даже после обновления выбранного канала в ${currentPathLabel.value} ещё не хватает: ${missing.map((item) => item.label).join(', ')}.`
})

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

<style scoped>
.pump-calibration-modal :deep(label.text-xs) {
  display: grid;
  gap: 0.32rem;
  line-height: 1.35;
}

.pump-calibration-modal :deep(.input-field),
.pump-calibration-modal :deep(.input-select) {
  height: 2.2rem;
  padding: 0 0.7rem;
  font-size: 0.78rem;
  border-radius: 0.72rem;
}
</style>
