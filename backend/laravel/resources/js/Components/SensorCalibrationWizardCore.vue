<template>
  <div class="sensor-calibration-wizard space-y-4">
    <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3 text-sm text-[color:var(--text-muted)]">
      Канал: {{ overview.channel_uid }} · Узел: {{ overview.node_uid || 'unknown' }}
    </div>

    <div class="space-y-2">
      <div class="text-sm font-medium">
        Шаг 1. Подготовка
      </div>
      <div class="text-xs text-[color:var(--text-dim)]">
        {{ recommendedValuesLine }}
      </div>
      <div
        v-if="overview.sensor_type === 'ph'"
        class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3 text-xs text-[color:var(--text-dim)] space-y-2"
      >
        <p class="font-medium text-[color:var(--text-muted)]">
          Trema pH (I2C), iArduino
        </p>
        <ul class="list-disc pl-4 space-y-1">
          <li>Двухточечная калибровка: два разных буфера (часто ~4.01 и ~9.18 по документации модуля).</li>
          <li>Держите электрод в каждом буфере несколько минут до стабилизации, между точками промывайте дистиллятом.</li>
          <li>По индикации Trema: после старта стадии 1 обычно мигает <strong>светодиод 1</strong>; после её завершения часто <strong>чередуются 1 и 2</strong> — модуль ждёт второй буфер; на стадии 2 обычно мигает <strong>светодиод 2</strong>, затем оба гаснут.</li>
          <li>Команда на узле дождётся завершения этапа на модуле; при ошибке расчёта на модуле вернётся ERROR.</li>
        </ul>
      </div>
      <div
        v-if="sessionLoading"
        class="text-xs text-[color:var(--text-dim)]"
      >
        Загрузка активной сессии...
      </div>
      <Button
        v-if="!calibration"
        size="sm"
        :disabled="busy || sessionLoading"
        @click="start"
      >
        Начать калибровку
      </Button>
    </div>

    <div
      v-if="calibration"
      class="space-y-4"
    >
      <div
        v-if="isPhSensor && phTremaPanelPhase !== 'hidden'"
        class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-4 space-y-3"
      >
        <div class="text-[10px] font-bold uppercase tracking-widest text-[color:var(--text-dim)]">
          Процесс на модуле Trema
        </div>

        <div
          v-if="phTremaPanelPhase === 'before_point1'"
          class="space-y-3"
        >
          <p class="text-sm text-[color:var(--text-muted)]">
            Перед отправкой убедитесь, что электрод стоит в <strong>первом (кислом) буфере</strong> и показания стабилизировались.
            После нажатия «Калибровать точку 1» узел запустит стадию 1 — на модуле по документации iArduino обычно начинает мигать <strong>индикатор 1</strong>.
          </p>
        </div>

        <div
          v-else-if="phTremaPanelPhase === 'stage1_module'"
          class="flex flex-col gap-3 sm:flex-row sm:items-start"
        >
          <div
            class="shrink-0 w-10 h-10 rounded-full border-2 border-brand border-t-transparent animate-spin"
            aria-hidden="true"
          />
          <div class="min-w-0 space-y-2 flex-1">
            <div class="text-sm font-semibold text-[color:var(--text-primary)]">
              Стадия 1 на модуле
            </div>
            <p class="text-xs text-[color:var(--text-dim)] leading-relaxed">
              Ожидайте ответ узла. На плате Trema в этот период обычно <strong>мигает только светодиод 1</strong> — идёт расчёт первой точки.
              Не извлекайте электрод из буфера и не прерывайте питание.
            </p>
          </div>
        </div>

        <div
          v-else-if="phTremaPanelPhase === 'await_step2'"
          class="space-y-3"
        >
          <div class="text-sm font-semibold text-[color:var(--text-primary)]">
            Режим ожидания шага 2
          </div>
          <p class="text-xs text-[color:var(--text-dim)] leading-relaxed">
            Первая точка принята бэкендом. На модуле по документации Trema часто включается индикация <strong>поочерёдного мигания 1 и 2</strong> —
            это пауза перед второй стадией: промойте электрод, погрузите во <strong>второй (щелочной) буфер</strong>,
            дождитесь стабилизации и нажмите «Калибровать точку 2».
          </p>
        </div>

        <div
          v-else-if="phTremaPanelPhase === 'stage2_module'"
          class="flex flex-col gap-3 sm:flex-row sm:items-start"
        >
          <div
            class="shrink-0 w-10 h-10 rounded-full border-2 border-brand border-t-transparent animate-spin"
            aria-hidden="true"
          />
          <div class="min-w-0 space-y-2 flex-1">
            <div class="text-sm font-semibold text-[color:var(--text-primary)]">
              Стадия 2 на модуле
            </div>
            <p class="text-xs text-[color:var(--text-dim)] leading-relaxed">
              Ожидайте ответ узла. Обычно мигает <strong>светодиод 2</strong>, затем <strong>оба гаснут</strong> — калибровка на модуле завершена.
            </p>
          </div>
        </div>

        <div
          v-else-if="phTremaPanelPhase === 'persist_config'"
          class="flex flex-col gap-3 sm:flex-row sm:items-start"
        >
          <div
            class="shrink-0 w-10 h-10 rounded-full border-2 border-[color:var(--border-muted)] border-t-[color:var(--text-muted)] animate-spin"
            aria-hidden="true"
          />
          <div class="min-w-0 space-y-1 flex-1">
            <div class="text-sm font-semibold text-[color:var(--text-primary)]">
              Сохранение калибровки в узле
            </div>
            <p class="text-xs text-[color:var(--text-dim)] leading-relaxed">
              Команда со стороны узла завершена; ожидается <code class="text-[11px]">config_report</code> с записанной калибровкой в NVS.
            </p>
          </div>
        </div>

        <div
          v-if="phTremaPanelPhase !== 'persist_config'"
          class="flex items-center justify-center gap-8 pt-2"
          aria-hidden="true"
        >
          <div class="flex flex-col items-center gap-1">
            <div :class="[tremaLedDiskBase, tremaLedDisks.d1]" />
            <span class="text-[10px] text-[color:var(--text-dim)] font-mono">1</span>
          </div>
          <div class="flex flex-col items-center gap-1">
            <div :class="[tremaLedDiskBase, tremaLedDisks.d2]" />
            <span class="text-[10px] text-[color:var(--text-dim)] font-mono">2</span>
          </div>
        </div>

        <p class="text-[10px] text-[color:var(--text-dim)] leading-snug border-t border-[color:var(--border-muted)] pt-3 mt-1">
          Индикация соответствует типичному поведению Trema Flash-I2C (iArduino). Фактический вид зависит от ревизии модуля и прошивки STM32 на плате.
        </p>
      </div>

      <div class="rounded-lg border border-[color:var(--border-muted)] p-3 space-y-3">
        <div class="text-sm font-medium">
          {{ step2Title }}
        </div>
        <label
          class="text-xs text-[color:var(--text-muted)] block"
          :title="fieldHelp('point_1_reference')"
        >
          {{ point1FieldLabel }}
          <input
            v-model.number="point1Value"
            type="number"
            step="0.01"
            class="input-field mt-1 w-full"
          />
        </label>
        <div class="text-xs text-[color:var(--text-dim)]">
          {{ point1StatusLine }}
        </div>
        <div
          v-if="calibration.point_1_error"
          class="text-xs text-[color:var(--accent-red)] space-y-1"
        >
          <p class="leading-snug">
            {{ point1ErrorHuman }}
          </p>
          <p
            v-if="point1ErrorShowOriginal"
            class="text-[10px] text-[color:var(--text-dim)] font-mono leading-snug"
          >
            Ответ узла: {{ calibration.point_1_error }}
          </p>
        </div>
        <Button
          size="sm"
          :disabled="busy || calibration.status !== 'started'"
          @click="submitPoint(1)"
        >
          Калибровать точку 1
        </Button>
      </div>

      <div
        class="rounded-lg border border-[color:var(--border-muted)] p-3 space-y-3 transition-opacity"
        :class="point2SectionDimmed ? 'opacity-55' : ''"
      >
        <div class="text-sm font-medium">
          {{ step3Title }}
        </div>
        <label
          class="text-xs text-[color:var(--text-muted)] block"
          :title="fieldHelp('point_2_reference')"
        >
          {{ point2FieldLabel }}
          <input
            v-model.number="point2Value"
            type="number"
            step="0.01"
            class="input-field mt-1 w-full"
          />
        </label>
        <div class="text-xs text-[color:var(--text-dim)]">
          {{ point2StatusLine }}
        </div>
        <div
          v-if="calibration.point_2_error"
          class="text-xs text-[color:var(--accent-red)] space-y-1"
        >
          <p class="leading-snug">
            {{ point2ErrorHuman }}
          </p>
          <p
            v-if="point2ErrorShowOriginal"
            class="text-[10px] text-[color:var(--text-dim)] font-mono leading-snug"
          >
            Ответ узла: {{ calibration.point_2_error }}
          </p>
        </div>
        <Button
          size="sm"
          :disabled="busy || calibration.status !== 'point_1_done'"
          @click="submitPoint(2)"
        >
          Калибровать точку 2
        </Button>
      </div>

      <div
        v-if="calibration.status === 'point_2_pending' && calibration.point_2_result === 'DONE' && calibration.meta?.awaiting_config_report"
        class="rounded-lg border border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] p-3 text-sm text-[color:var(--badge-warning-text)]"
      >
        Команда принята нодой. Ожидается `config_report` с сохранённой calibration, после этого сессия завершится автоматически.
      </div>
      <div
        v-if="calibration.status === 'completed'"
        class="rounded-lg border border-[color:var(--badge-success-border)] bg-[color:var(--badge-success-bg)] p-3 text-sm text-[color:var(--badge-success-text)]"
      >
        Калибровка завершена.
      </div>
      <div
        v-else-if="calibration.status === 'failed'"
        class="rounded-lg border border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)] p-3 text-sm text-[color:var(--badge-danger-text)] space-y-2"
      >
        <p>Калибровка завершилась ошибкой. Для повтора создайте новую сессию.</p>
        <p
          v-if="sessionFailureSummary"
          class="text-xs leading-relaxed opacity-95"
        >
          {{ sessionFailureSummary }}
        </p>
      </div>
    </div>

    <div class="flex gap-2">
      <Button
        size="sm"
        variant="secondary"
        @click="$emit('close')"
      >
        Закрыть
      </Button>
      <Button
        v-if="calibration && !['completed', 'failed', 'cancelled'].includes(calibration.status)"
        size="sm"
        variant="secondary"
        :disabled="busy"
        @click="cancel"
      >
        Отменить сессию
      </Button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import Button from '@/Components/Button.vue'
import { useSensorCalibration } from '@/composables/useSensorCalibration'
import { coerceLegacyPhCalibrationPointPair } from '@/composables/useSensorCalibrationSettings'
import { formatSensorCalibrationPointError } from '@/utils/sensorCalibrationHumanError'
import type {
  SensorCalibration,
  SensorCalibrationOverview,
  SensorCalibrationSessionOutcome,
} from '@/types/SensorCalibration'
import type { SensorCalibrationSettings } from '@/types/SystemSettings'

const props = defineProps<{
  zoneId: number
  overview: SensorCalibrationOverview
  settings: SensorCalibrationSettings
  /** Когда false — сбросить локальное состояние (drawer закрыт) */
  active: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  /** Терминальное состояние сессии (успех / ошибка / отмена) — для обновления списков. */
  (e: 'session-finished', outcome: SensorCalibrationSessionOutcome): void
}>()

function fieldHelp(key: 'point_1_reference' | 'point_2_reference'): string {
  if (props.overview.sensor_type === 'ph') {
    if (key === 'point_1_reference') {
      return 'Эталон pH первого буфера (Trema I2C: обычно кислый, напр. 4.01; перед отправкой дайте электроду стабилизироваться в растворе).'
    }

    return 'Эталон pH второго буфера (обычно щелочной, напр. 9.18; значение должно заметно отличаться от первой точки).'
  }

  if (key === 'point_1_reference') {
    return 'Эталон TDS (ppm) для первой точки — обычно меньший из двух рекомендуемых в системных настройках.'
  }

  return 'Эталон TDS (ppm) для второй точки — обычно больший из двух рекомендуемых в системных настройках.'
}

const { startCalibration, submitPoint: submitCalibrationPoint, cancelCalibration, getCalibration } = useSensorCalibration(
  () => props.zoneId,
)

const calibration = ref<SensorCalibration | null>(null)
const busy = ref(false)
const sessionLoading = ref(false)
const point1Value = ref(0)
const point2Value = ref(0)
let pollHandle: number | null = null
let loadSequence = 0

const isPhSensor = computed(() => props.overview.sensor_type === 'ph')

type PhTremaPanelPhase =
  | 'hidden'
  | 'before_point1'
  | 'stage1_module'
  | 'await_step2'
  | 'stage2_module'
  | 'persist_config'

const phTremaPanelPhase = computed((): PhTremaPanelPhase => {
  if (!isPhSensor.value || !calibration.value) {
    return 'hidden'
  }
  const c = calibration.value
  const s = c.status
  if (s === 'completed' || s === 'failed' || s === 'cancelled') {
    return 'hidden'
  }
  if (s === 'started') {
    return 'before_point1'
  }
  if (s === 'point_1_pending') {
    return 'stage1_module'
  }
  if (s === 'point_1_done') {
    return 'await_step2'
  }
  if (s === 'point_2_pending') {
    const meta = c.meta as Record<string, unknown> | undefined
    if (c.point_2_result === 'DONE' && meta?.awaiting_config_report === true) {
      return 'persist_config'
    }
    return 'stage2_module'
  }
  return 'hidden'
})

const tremaLedDiskBase =
  'w-8 h-8 rounded-full border-2 border-[color:var(--border-strong)] bg-[color:var(--bg-elevated)]'

const tremaLedDisks = computed(() => {
  const p = phTremaPanelPhase.value
  if (p === 'before_point1') {
    return { d1: 'opacity-40', d2: 'opacity-40' }
  }
  if (p === 'stage1_module') {
    return { d1: 'trema-led-pulse border-brand bg-brand-soft', d2: 'opacity-35' }
  }
  if (p === 'await_step2') {
    return {
      d1: 'trema-led-alternate-a border-brand bg-brand-soft',
      d2: 'trema-led-alternate-b border-brand bg-brand-soft',
    }
  }
  if (p === 'stage2_module') {
    return { d1: 'opacity-35', d2: 'trema-led-pulse border-brand bg-brand-soft' }
  }
  return { d1: 'opacity-40', d2: 'opacity-40' }
})

const defaults = computed(() => isPhSensor.value
  ? { point_1_value: props.settings.ph_point_1_value, point_2_value: props.settings.ph_point_2_value }
  : { point_1_value: props.settings.ec_point_1_tds, point_2_value: props.settings.ec_point_2_tds })

const step2Title = computed(() =>
  isPhSensor.value ? 'Шаг 2. Точка 1 — кислый буфер' : 'Шаг 2. Точка 1 — меньший эталон TDS',
)

const step3Title = computed(() =>
  isPhSensor.value ? 'Шаг 3. Точка 2 — щелочной буфер' : 'Шаг 3. Точка 2 — больший эталон TDS',
)

const recommendedValuesLine = computed(() => {
  const a = defaults.value.point_1_value
  const b = defaults.value.point_2_value
  if (isPhSensor.value) {
    return `Рекомендуемые эталоны pH: точка 1 (кислый) — ${a}, точка 2 (щелочной) — ${b}.`
  }
  return `Рекомендуемые эталоны TDS (ppm): точка 1 — ${a}, точка 2 — ${b}.`
})

const point1FieldLabel = computed(() =>
  isPhSensor.value ? 'Значение эталона pH (кислый буфер)' : 'Значение эталона TDS, точка 1 (ppm)',
)

const point2FieldLabel = computed(() =>
  isPhSensor.value ? 'Значение эталона pH (щелочной буфер)' : 'Значение эталона TDS, точка 2 (ppm)',
)

const point2SectionDimmed = computed(() => {
  const cal = calibration.value
  if (!cal) return false
  return cal.status === 'started' || cal.status === 'point_1_pending'
})

const point1StatusLine = computed(() => {
  const cal = calibration.value
  if (!cal) return ''
  return `Статус сессии: ${cal.status}${cal.point_1_result ? ` · результат точки 1: ${cal.point_1_result}` : ''}`
})

const point2StatusLine = computed(() => {
  const cal = calibration.value
  if (!cal) return ''
  if (cal.status === 'started' || cal.status === 'point_1_pending') {
    return 'Точка 2 станет доступна после успешного завершения точки 1.'
  }
  if (cal.status === 'point_1_done') {
    return `Можно калибровать точку 2. Статус: ${cal.status}${cal.point_2_result ? ` · результат: ${cal.point_2_result}` : ''}`
  }
  return `Статус сессии: ${cal.status}${cal.point_2_result ? ` · результат точки 2: ${cal.point_2_result}` : ''}`
})

function metaErrorCode(meta: Record<string, unknown> | undefined, key: string): string | null {
  const v = meta?.[key]
  return typeof v === 'string' && v.length > 0 ? v : null
}

const point1ErrorHuman = computed(() => {
  const cal = calibration.value
  if (!cal?.point_1_error) {
    return ''
  }
  return formatSensorCalibrationPointError(
    cal.sensor_type,
    1,
    cal.point_1_error,
    metaErrorCode(cal.meta, 'point_1_error_code'),
  )
})

const point1ErrorShowOriginal = computed(() => {
  const cal = calibration.value
  if (!cal?.point_1_error) {
    return false
  }
  return !point1ErrorHuman.value.includes(cal.point_1_error.trim())
})

const point2ErrorHuman = computed(() => {
  const cal = calibration.value
  if (!cal?.point_2_error) {
    return ''
  }
  return formatSensorCalibrationPointError(
    cal.sensor_type,
    2,
    cal.point_2_error,
    metaErrorCode(cal.meta, 'point_2_error_code'),
  )
})

const point2ErrorShowOriginal = computed(() => {
  const cal = calibration.value
  if (!cal?.point_2_error) {
    return false
  }
  return !point2ErrorHuman.value.includes(cal.point_2_error.trim())
})

/** Краткое пояснение при терминальном failed (для баннера). */
const sessionFailureSummary = computed(() => {
  const cal = calibration.value
  if (!cal || cal.status !== 'failed') {
    return ''
  }
  if (cal.point_2_error) {
    return formatSensorCalibrationPointError(
      cal.sensor_type,
      2,
      cal.point_2_error,
      metaErrorCode(cal.meta, 'point_2_error_code'),
    )
  }
  if (cal.point_1_error) {
    return formatSensorCalibrationPointError(
      cal.sensor_type,
      1,
      cal.point_1_error,
      metaErrorCode(cal.meta, 'point_1_error_code'),
    )
  }
  return ''
})

function stopPolling(): void {
  if (pollHandle !== null) {
    window.clearInterval(pollHandle)
    pollHandle = null
  }
}

function startPolling(): void {
  stopPolling()
  pollHandle = window.setInterval(async () => {
    if (!calibration.value) return
    const latest = await getCalibration(calibration.value.id)
    calibration.value = latest
    if (['completed', 'failed', 'cancelled', 'point_1_done'].includes(latest.status)) {
      if (latest.status === 'completed') {
        stopPolling()
        emit('session-finished', 'success')
      } else if (latest.status === 'failed') {
        stopPolling()
        emit('session-finished', 'failed')
      } else if (latest.status === 'cancelled') {
        stopPolling()
        emit('session-finished', 'cancelled')
      } else if (latest.status === 'point_1_done') {
        stopPolling()
      }
    }
  }, 1500)
}

function resetSessionState(): void {
  loadSequence += 1
  stopPolling()
  calibration.value = null
  sessionLoading.value = false
  point1Value.value = defaults.value.point_1_value
  point2Value.value = defaults.value.point_2_value
}

async function hydrateActiveCalibration(): Promise<void> {
  const activeCalibrationId = props.overview.active_calibration_id
  if (!props.active || !activeCalibrationId) {
    return
  }

  const sequence = ++loadSequence
  sessionLoading.value = true
  try {
    const activeCalibration = await getCalibration(activeCalibrationId)
    if (!props.active || sequence !== loadSequence) {
      return
    }

    calibration.value = activeCalibration
    point1Value.value = activeCalibration.point_1_reference ?? defaults.value.point_1_value
    point2Value.value = activeCalibration.point_2_reference ?? defaults.value.point_2_value

    if (['point_1_pending', 'point_2_pending'].includes(activeCalibration.status)) {
      startPolling()
    }
  } finally {
    if (sequence === loadSequence) {
      sessionLoading.value = false
    }
  }
}

async function start(): Promise<void> {
  busy.value = true
  try {
    const started = await startCalibration(props.overview.node_channel_id, props.overview.sensor_type)
    calibration.value = started.calibration
    if (props.overview.sensor_type === 'ph') {
      const c = coerceLegacyPhCalibrationPointPair(started.defaults.point_1_value, started.defaults.point_2_value)
      point1Value.value = c.p1
      point2Value.value = c.p2
    } else {
      point1Value.value = started.defaults.point_1_value
      point2Value.value = started.defaults.point_2_value
    }
  } finally {
    busy.value = false
  }
}

async function submitPoint(stage: 1 | 2): Promise<void> {
  if (!calibration.value) return
  busy.value = true
  try {
    calibration.value = await submitCalibrationPoint(
      calibration.value.id,
      stage,
      stage === 1 ? point1Value.value : point2Value.value,
    )
    startPolling()
  } finally {
    busy.value = false
  }
}

async function cancel(): Promise<void> {
  if (!calibration.value) return
  busy.value = true
  try {
    await cancelCalibration(calibration.value.id)
    stopPolling()
    emit('session-finished', 'cancelled')
    emit('close')
  } finally {
    busy.value = false
  }
}

watch(
  () => [props.active, props.overview.node_channel_id, props.overview.active_calibration_id] as const,
  ([isActive]) => {
    if (!isActive) {
      resetSessionState()
      return
    }

    resetSessionState()
    point1Value.value = defaults.value.point_1_value
    point2Value.value = defaults.value.point_2_value
    void hydrateActiveCalibration()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<style scoped>
.sensor-calibration-wizard :deep(label.text-xs) {
  display: grid;
  gap: 0.32rem;
  line-height: 1.35;
}

.sensor-calibration-wizard :deep(.input-field) {
  height: 2.2rem;
  padding: 0 0.7rem;
  font-size: 0.78rem;
  border-radius: 0.72rem;
}

@keyframes trema-led-pulse-kf {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
    box-shadow: 0 0 0 0 rgb(59 130 246 / 0%);
  }

  50% {
    opacity: 0.42;
    transform: scale(0.94);
    box-shadow: 0 0 14px 2px rgb(59 130 246 / 45%);
  }
}

.trema-led-pulse {
  animation: trema-led-pulse-kf 1s ease-in-out infinite;
}

@keyframes trema-led-alternate-kf {
  0%,
  45% {
    opacity: 1;
  }

  50%,
  95% {
    opacity: 0.18;
  }

  100% {
    opacity: 1;
  }
}

.trema-led-alternate-a {
  animation: trema-led-alternate-kf 1.2s ease-in-out infinite;
}

.trema-led-alternate-b {
  animation: trema-led-alternate-kf 1.2s ease-in-out infinite;
  animation-delay: 0.6s;
}
</style>
