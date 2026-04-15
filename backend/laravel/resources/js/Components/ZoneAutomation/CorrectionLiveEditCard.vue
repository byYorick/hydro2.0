<template>
  <section
    class="surface-card surface-card--elevated border border-amber-300/50 dark:border-amber-700/60 rounded-2xl p-4 space-y-4 bg-amber-50/30 dark:bg-amber-950/10"
    data-testid="correction-live-edit"
  >
    <header class="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
      <div>
        <div class="flex items-center gap-2">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            Тонкая настройка correction runtime в режиме live
          </h3>
          <Badge variant="warning">
            режим live
          </Badge>
        </div>
        <p class="text-xs text-[color:var(--text-dim)] mt-1 max-w-3xl">
          Здесь можно быстро и безопасно подправить live-конфигурацию correction без полного редактора authority-конфига. Карточка отправляет только разрешённые поля, а endpoint принимает один общий `phase`, поэтому базовую correction-конфигурацию, `generic` process calibration и фазовые process calibration иногда нужно сохранять отдельными запросами.
        </p>
      </div>

      <div class="flex flex-wrap items-center gap-2 text-xs text-[color:var(--text-dim)]">
        <span v-if="correctionVersion !== null">Версия correction: {{ correctionVersion }}</span>
        <Button
          size="sm"
          variant="secondary"
          :disabled="loading || saving"
          data-testid="correction-live-reload"
          @click="loadDocuments"
        >
          {{ loading ? 'Загрузка...' : 'Перечитать значения' }}
        </Button>
      </div>
    </header>

    <p
      v-if="loading"
      class="text-xs text-[color:var(--text-dim)] animate-pulse"
    >
      Загрузка текущих live-снимков correction runtime...
    </p>
    <p
      v-else-if="loadError"
      class="text-xs text-rose-500 dark:text-rose-400"
      data-testid="correction-live-load-error"
    >
      {{ loadError }}
    </p>

    <form
      v-else
      class="space-y-4"
      data-testid="correction-live-form"
      @submit.prevent="submit"
    >
      <div class="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
        <label class="space-y-1.5">
          <span class="block text-xs font-medium text-[color:var(--text-muted)]">
            Куда писать correction
          </span>
          <select
            v-model="correctionTarget"
            class="input-select w-full"
            data-testid="correction-live-correction-target"
          >
            <option value="base">Базовая конфигурация</option>
            <option
              v-for="phase in CORRECTION_PHASES"
              :key="phase"
              :value="phase"
            >
              {{ correctionTargetLabel(phase) }}
            </option>
          </select>
          <span class="block text-[11px] text-[color:var(--text-dim)]">
            Базовый режим меняет `base_config.*`. Фазовый режим пишет только в `phase_overrides.{phase}.*` и влияет на выбранную фазу, не трогая остальные.
          </span>
        </label>

        <label class="space-y-1.5">
          <span class="block text-xs font-medium text-[color:var(--text-muted)]">
            Куда писать process calibration
          </span>
          <select
            v-model="calibrationTarget"
            class="input-select w-full"
            data-testid="correction-live-calibration-target"
          >
            <option value="none">Не менять process calibration</option>
            <option
              v-for="mode in CALIBRATION_TARGETS"
              :key="mode"
              :value="mode"
            >
              {{ calibrationTargetLabel(mode) }}
            </option>
          </select>
          <span class="block text-[11px] text-[color:var(--text-dim)]">
            Фазовые режимы меняют `zone.process_calibration.{phase}`. `generic` — общий fallback-профиль; его нужно отправлять отдельно без correction-изменений.
          </span>
        </label>

        <div class="flex items-end">
          <Button
            size="sm"
            variant="secondary"
            :disabled="saving"
            data-testid="correction-live-reset"
            @click.prevent="resetForms"
          >
            Сбросить форму
          </Button>
        </div>
      </div>

      <label class="flex items-center gap-2 text-sm">
        <input
          v-model="advancedMode"
          type="checkbox"
          data-testid="correction-live-toggle-advanced"
        />
        <span>Показать расширенные параметры</span>
      </label>

      <div class="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
        <div class="space-y-3">
          <details
            v-for="section in visibleCorrectionSections"
            :key="section.key"
            class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)]"
            :open="section.key === 'timing' || section.key === 'retry'"
          >
            <summary class="cursor-pointer list-none px-4 py-3">
              <div class="text-sm font-semibold text-[color:var(--text-primary)]">
                {{ section.label }}
              </div>
              <div class="mt-1 text-xs text-[color:var(--text-dim)]">
                {{ section.description }}
              </div>
            </summary>

            <div class="border-t border-[color:var(--border-muted)] p-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              <div
                v-for="field in section.fields"
                :key="field.path"
                class="space-y-1.5"
              >
                <label class="block text-xs font-medium text-[color:var(--text-muted)]">
                  {{ field.label }}
                </label>

                <label
                  v-if="field.type === 'boolean'"
                  class="flex items-center gap-2 text-sm"
                >
                  <input
                    :checked="Boolean(getByPath(correctionForm, field.path))"
                    :data-testid="fieldTestId('correction-live-field', field.path)"
                    type="checkbox"
                    @change="setByPath(correctionForm, field.path, ($event.target as HTMLInputElement).checked)"
                  />
                  <span>Включить параметр</span>
                </label>

                <select
                  v-else-if="field.type === 'enum'"
                  :value="String(getByPath(correctionForm, field.path) ?? '')"
                  :data-testid="fieldTestId('correction-live-field', field.path)"
                  class="input-select w-full"
                  :disabled="Boolean(field.readonly)"
                  @change="setByPath(correctionForm, field.path, ($event.target as HTMLSelectElement).value)"
                >
                  <option
                    v-for="option in field.options || []"
                    :key="option"
                    :value="option"
                  >
                    {{ option }}
                  </option>
                </select>

                <input
                  v-else
                  :value="String(getByPath(correctionForm, field.path) ?? '')"
                  :data-testid="fieldTestId('correction-live-field', field.path)"
                  :type="field.type === 'string' ? 'text' : 'number'"
                  :step="field.step ?? (field.type === 'integer' ? 1 : 'any')"
                  :min="field.min"
                  :max="field.max"
                  :disabled="Boolean(field.readonly)"
                  class="input-field w-full"
                  @input="handleScalarInput(correctionForm, field, $event)"
                />

                <p class="text-[11px] text-[color:var(--text-dim)]">
                  {{ field.description }}
                </p>
              </div>
            </div>
          </details>
        </div>

        <div class="space-y-4">
          <section class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-4 space-y-4">
            <div>
              <div class="text-sm font-semibold text-[color:var(--text-primary)]">
                Правка process calibration
              </div>
              <div class="mt-1 text-xs text-[color:var(--text-dim)]">
                Эти поля сохраняются в `zone.process_calibration.{phase}`. AE3 подхватит их на ближайшем checkpoint и начнёт использовать новые задержки, gain-коэффициенты и confidence без полного restart workflow.
              </div>
            </div>

            <div
              v-if="calibrationTarget === 'none'"
              class="text-xs text-[color:var(--text-dim)]"
            >
              Выберите целевой calibration-профиль, если нужно править transport delay, settle, process gain или confidence.
            </div>

            <div
              v-else
              class="grid gap-4 md:grid-cols-2"
            >
              <div
                v-for="field in CALIBRATION_FIELDS"
                :key="field.path"
                class="space-y-1.5"
              >
                <label class="block text-xs font-medium text-[color:var(--text-muted)]">
                  {{ field.label }}
                </label>
                <input
                  :value="String(getByPath(calibrationForm, field.path) ?? '')"
                  :data-testid="fieldTestId('correction-live-calibration-field', field.path)"
                  type="number"
                  :step="field.step ?? 'any'"
                  :min="field.min"
                  :max="field.max"
                  class="input-field w-full"
                  @input="handleScalarInput(calibrationForm, field, $event)"
                />
                <p class="text-[11px] text-[color:var(--text-dim)]">
                  {{ field.description }}
                </p>
              </div>
            </div>
          </section>

          <section class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-4 space-y-3">
            <div class="text-sm font-semibold text-[color:var(--text-primary)]">
              Что уйдёт в запрос
            </div>

            <dl class="grid gap-2 text-xs">
              <div class="flex items-center justify-between gap-3">
                <dt class="text-[color:var(--text-muted)]">
                  Полей correction
                </dt>
                <dd
                  class="font-medium text-[color:var(--text-primary)]"
                  data-testid="correction-live-correction-dirty"
                >
                  {{ correctionPatchKeys.length }} полей
                </dd>
              </div>
              <div class="flex items-center justify-between gap-3">
                <dt class="text-[color:var(--text-muted)]">
                  Полей process calibration
                </dt>
                <dd
                  class="font-medium text-[color:var(--text-primary)]"
                  data-testid="correction-live-calibration-dirty"
                >
                  {{ calibrationPatchKeys.length }} полей
                </dd>
              </div>
              <div class="flex items-center justify-between gap-3">
                <dt class="text-[color:var(--text-muted)]">
                  Фаза запроса
                </dt>
                <dd class="font-medium text-[color:var(--text-primary)]">
                  {{ requestPhaseLabel }}
                </dd>
              </div>
            </dl>

            <label class="space-y-1.5">
              <span class="block text-xs font-medium text-[color:var(--text-muted)]">
                Причина изменения (обязательно, не короче 3 символов)
              </span>
              <textarea
                v-model="reason"
                rows="3"
                maxlength="500"
                class="input-field w-full min-h-[96px]"
                data-testid="correction-live-reason"
              ></textarea>
              <span class="block text-[11px] text-[color:var(--text-dim)]">
                Коротко опишите, зачем меняете live runtime: например, «увеличиваю окно наблюдения из-за медленного отклика EC» или «снижаю Kp pH, чтобы убрать перерегулирование».
              </span>
            </label>

            <p
              v-if="errorMessage"
              class="text-xs text-rose-500 dark:text-rose-400"
              data-testid="correction-live-error"
            >
              {{ errorMessage }}
            </p>
            <p
              v-else-if="saving"
              class="text-xs text-[color:var(--text-dim)] animate-pulse"
            >
              Сохранение...
            </p>
            <p
              v-else-if="lastRevision !== null"
              class="text-xs text-emerald-600 dark:text-emerald-400"
              data-testid="correction-live-success"
            >
              ✓ сохранено, ревизия {{ lastRevision }}
            </p>
            <p
              v-else-if="submitBlocker"
              class="text-xs text-amber-700 dark:text-amber-300"
              data-testid="correction-live-blocker"
            >
              {{ submitBlocker }}
            </p>

            <div class="flex justify-end">
              <Button
                size="sm"
                type="submit"
                :disabled="!canSubmit"
                data-testid="correction-live-submit"
              >
                Применить live-правку
              </Button>
            </div>
          </section>
        </div>
      </div>
    </form>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import { processCalibrationNamespace } from '@/composables/processCalibrationAuthority'
import type { AutomationDocument } from '@/composables/useAutomationConfig'
import { automationConfigsApi } from '@/services/api/automationConfigs'
import {
  type CorrectionLiveEditPayload,
  type CorrectionLiveEditPhase,
  zoneConfigModeApi,
} from '@/services/api/zoneConfigMode'
import type {
  CorrectionCatalogField,
  CorrectionCatalogSection,
  CorrectionPhase,
  ZoneCorrectionConfigPayload,
} from '@/types/CorrectionConfig'
import type { ProcessCalibrationMode } from '@/types/ProcessCalibration'

interface Props {
  zoneId: number
}

type CorrectionTarget = 'base' | CorrectionPhase
type CalibrationTarget = 'none' | ProcessCalibrationMode

interface CalibrationFieldDescriptor extends Pick<CorrectionCatalogField, 'path' | 'label' | 'description' | 'type' | 'min' | 'max' | 'step'> {}
interface LocalizedCorrectionText {
  label: string
  description: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'applied', revision: number): void
}>()

const CORRECTION_PHASES: CorrectionPhase[] = ['solution_fill', 'tank_recirc', 'irrigation']
const CALIBRATION_TARGETS: ProcessCalibrationMode[] = ['solution_fill', 'tank_recirc', 'irrigation', 'generic']
const CORRECTION_PHASE_LABELS: Record<CorrectionPhase, string> = {
  solution_fill: 'Наполнение',
  tank_recirc: 'Рециркуляция',
  irrigation: 'Полив',
}
const PROCESS_CALIBRATION_LABELS: Record<ProcessCalibrationMode, string> = {
  solution_fill: 'Наполнение',
  tank_recirc: 'Рециркуляция',
  irrigation: 'Полив',
  generic: 'Общий fallback (generic)',
}
const CORRECTION_SECTION_TEXTS: Record<string, LocalizedCorrectionText> = {
  timing: {
    label: 'Временные окна',
    description: 'Здесь настраиваются задержки чтения телеметрии, тайминги ожидания и интервалы, от которых зависит темп correction workflow.',
  },
  retry: {
    label: 'Повторы и лимиты',
    description: 'Лимиты correction-циклов и задержки повторных попыток, когда окно наблюдения ещё не готово или телеметрия временно непригодна.',
  },
  dosing: {
    label: 'Объём дозирования',
    description: 'Ограничения на разовый объём дозы и расчётный объём раствора, который planner использует при оценке ожидаемого эффекта.',
  },
  safety: {
    label: 'Защитные флаги',
    description: 'Fail-safe поведение correction path, когда система видит отсутствие реакции, накопившийся alert или риск деградации раствора.',
  },
  tolerance: {
    label: 'Допуски цели',
    description: 'Ширина допустимого окна вокруг целевых pH/EC, по которому runtime решает, что раствор уже достаточно близок к цели.',
  },
  'controllers.ph': {
    label: 'PID-контур pH',
    description: 'Параметры planner-а и наблюдения для pH-коррекции: коэффициенты PID, ограничения дозы, anti-windup и контроль устойчивости окна.',
  },
  'controllers.ec': {
    label: 'PID-контур EC',
    description: 'Параметры planner-а и наблюдения для EC-коррекции: коэффициенты PID, ограничения дозы, anti-windup и критерии наличия эффекта.',
  },
}
const LIVE_EDITABLE_CORRECTION_FIELDS = new Set<string>([
  'timing.stabilization_sec',
  'timing.telemetry_max_age_sec',
  'timing.irr_state_max_age_sec',
  'timing.level_poll_interval_sec',
  'timing.sensor_mode_stabilization_time_sec',
  'retry.max_ec_correction_attempts',
  'retry.max_ph_correction_attempts',
  'retry.prepare_recirculation_max_attempts',
  'retry.prepare_recirculation_max_correction_attempts',
  'retry.prepare_recirculation_timeout_sec',
  'retry.prepare_recirculation_correction_slack_sec',
  'retry.telemetry_stale_retry_sec',
  'retry.decision_window_retry_sec',
  'retry.low_water_retry_sec',
  'dosing.max_ec_dose_ml',
  'dosing.max_ph_dose_ml',
  'dosing.solution_volume_l',
  'safety.safe_mode_on_no_effect',
  'safety.block_on_active_no_effect_alert',
  'tolerance.prepare_tolerance.ph_pct',
  'tolerance.prepare_tolerance.ec_pct',
  'controllers.ph.kp',
  'controllers.ph.ki',
  'controllers.ph.kd',
  'controllers.ph.deadband',
  'controllers.ph.max_dose_ml',
  'controllers.ph.min_interval_sec',
  'controllers.ph.max_integral',
  'controllers.ph.derivative_filter_alpha',
  'controllers.ph.anti_windup.enabled',
  'controllers.ph.overshoot_guard.enabled',
  'controllers.ph.overshoot_guard.hard_min',
  'controllers.ph.overshoot_guard.hard_max',
  'controllers.ph.no_effect.enabled',
  'controllers.ph.no_effect.max_count',
  'controllers.ph.observe.telemetry_period_sec',
  'controllers.ph.observe.window_min_samples',
  'controllers.ph.observe.decision_window_sec',
  'controllers.ph.observe.observe_poll_sec',
  'controllers.ph.observe.min_effect_fraction',
  'controllers.ph.observe.stability_max_slope',
  'controllers.ph.observe.no_effect_consecutive_limit',
  'controllers.ec.kp',
  'controllers.ec.ki',
  'controllers.ec.kd',
  'controllers.ec.deadband',
  'controllers.ec.max_dose_ml',
  'controllers.ec.min_interval_sec',
  'controllers.ec.max_integral',
  'controllers.ec.derivative_filter_alpha',
  'controllers.ec.anti_windup.enabled',
  'controllers.ec.overshoot_guard.enabled',
  'controllers.ec.overshoot_guard.hard_min',
  'controllers.ec.overshoot_guard.hard_max',
  'controllers.ec.no_effect.enabled',
  'controllers.ec.no_effect.max_count',
  'controllers.ec.observe.telemetry_period_sec',
  'controllers.ec.observe.window_min_samples',
  'controllers.ec.observe.decision_window_sec',
  'controllers.ec.observe.observe_poll_sec',
  'controllers.ec.observe.min_effect_fraction',
  'controllers.ec.observe.stability_max_slope',
  'controllers.ec.observe.no_effect_consecutive_limit',
])
const CORRECTION_FIELD_TEXTS: Record<string, LocalizedCorrectionText> = {
  'timing.stabilization_sec': {
    label: 'Стабилизация перед corr_check',
    description: 'Сколько секунд runtime ждёт после активации сенсоров, прежде чем впервые оценивать pH/EC и принимать решение о дозе.',
  },
  'timing.telemetry_max_age_sec': {
    label: 'Максимальная давность телеметрии',
    description: 'Если свежие pH/EC sample старше этого порога, correction считает телеметрию устаревшей и не принимает решение по ней.',
  },
  'timing.irr_state_max_age_sec': {
    label: 'Максимальная давность IRR state',
    description: 'Порог актуальности снимка состояния исполнительных каналов. Нужен, чтобы correction не работал по старому состоянию потока и клапанов.',
  },
  'timing.level_poll_interval_sec': {
    label: 'Интервал проверки уровней',
    description: 'Как часто runtime перепроверяет level-switch и защитные условия, пока stage находится в ожидании или деградированном режиме.',
  },
  'timing.sensor_mode_stabilization_time_sec': {
    label: 'Стабилизация sensor_mode',
    description: 'Время, которое передаётся в команду sensor mode для прогрева и стабилизации датчиков перед измерением.',
  },
  'retry.max_ec_correction_attempts': {
    label: 'Лимит EC-попыток',
    description: 'Максимум EC-доз в одном correction-окне, после которого runtime считает EC-контур исчерпанным и выходит по fail path.',
  },
  'retry.max_ph_correction_attempts': {
    label: 'Лимит pH-попыток',
    description: 'Максимум pH-доз в одном correction-окне, после которого runtime прекращает pH-коррекцию и завершает окно по safety-логике.',
  },
  'retry.prepare_recirculation_max_attempts': {
    label: 'Лимит окон подготовки',
    description: 'Сколько раз runtime может заходить в prepare recirculation window, прежде чем признать фазу неуспешной.',
  },
  'retry.prepare_recirculation_max_correction_attempts': {
    label: 'Лимит correction-циклов в подготовке',
    description: 'Общий потолок correction-циклов внутри prepare recirculation, даже если отдельные pH/EC лимиты ещё не исчерпаны.',
  },
  'retry.prepare_recirculation_timeout_sec': {
    label: 'Таймаут подготовки',
    description: 'Максимальная длительность prepare recirculation stage. После истечения окна runtime должен выйти по timeout branch.',
  },
  'retry.prepare_recirculation_correction_slack_sec': {
    label: 'Запас времени на correction',
    description: 'Резерв секунд перед дедлайном prepare recirculation, после которого runtime уже не начинает новый correction-цикл.',
  },
  'retry.telemetry_stale_retry_sec': {
    label: 'Повтор после stale telemetry',
    description: 'Через сколько секунд correction повторит попытку, если pH/EC telemetry признана устаревшей и решение сейчас принимать нельзя.',
  },
  'retry.decision_window_retry_sec': {
    label: 'Повтор при неготовом окне',
    description: 'Пауза перед следующим чтением, если decision window ещё не набрало достаточно samples или не прошло критерий устойчивости.',
  },
  'retry.low_water_retry_sec': {
    label: 'Повтор после low-water guard',
    description: 'Задержка до следующей попытки correction, если runtime временно остановился из-за low-water или low-solution guard.',
  },
  'dosing.max_ec_dose_ml': {
    label: 'Максимум EC за один шаг',
    description: 'Жёсткий потолок EC-дозы в миллилитрах за один correction step, даже если planner считает, что нужно больше.',
  },
  'dosing.max_ph_dose_ml': {
    label: 'Максимум pH за один шаг',
    description: 'Жёсткий потолок pH-up/pH-down дозы за один correction step, чтобы ограничить риск резкого перерегулирования.',
  },
  'dosing.solution_volume_l': {
    label: 'Расчётный объём раствора',
    description: 'Объём раствора в литрах, относительно которого planner оценивает ожидаемый эффект дозы и рассчитывает величину коррекции.',
  },
  'safety.safe_mode_on_no_effect': {
    label: 'Safe mode при отсутствии реакции',
    description: 'Если после доз система не видит ожидаемого отклика, runtime может перейти в более осторожный режим и не продолжать агрессивную correction.',
  },
  'safety.block_on_active_no_effect_alert': {
    label: 'Блокировать correction по активному no-effect alert',
    description: 'Запрещает новые correction-циклы, пока в `pid_state` активен накопленный no-effect alert и оператор не подтвердил дальнейшую работу.',
  },
  'tolerance.prepare_tolerance.ph_pct': {
    label: 'Допуск pH',
    description: 'Процентное окно вокруг target pH, в пределах которого runtime считает значение достаточно близким к цели.',
  },
  'tolerance.prepare_tolerance.ec_pct': {
    label: 'Допуск EC',
    description: 'Процентное окно вокруг target EC, в пределах которого correction может считаться успешной без дополнительных доз.',
  },
  ...buildControllerFieldTexts('ph'),
  ...buildControllerFieldTexts('ec'),
}
const CALIBRATION_FIELDS: CalibrationFieldDescriptor[] = [
  {
    path: 'transport_delay_sec',
    label: 'Транспортная задержка',
    description: 'Сколько секунд проходит между дозой и первым измеримым откликом в датчике. Если занизить значение, runtime начнёт анализ реакции слишком рано.',
    type: 'integer',
    step: 1,
    min: 0,
    max: 120,
  },
  {
    path: 'settle_sec',
    label: 'Время стабилизации',
    description: 'Дополнительное окно после transport delay, в котором раствор должен успокоиться, а telemetry window — стать устойчивым для анализа.',
    type: 'integer',
    step: 1,
    min: 0,
    max: 300,
  },
  {
    path: 'ec_gain_per_ml',
    label: 'Коэффициент отклика EC',
    description: 'Показывает, на сколько единиц EC обычно меняется раствор после 1 мл EC-дозы. Используется planner-ом для расчёта требуемой дозы.',
    type: 'number',
    step: 0.001,
    min: 0.001,
    max: 10,
  },
  {
    path: 'ph_up_gain_per_ml',
    label: 'Коэффициент pH-up',
    description: 'Насколько в среднем меняется pH после 1 мл щёлочи. Нужен для прогноза pH-up correction и ограничения перерегулирования.',
    type: 'number',
    step: 0.001,
    min: 0.001,
    max: 5,
  },
  {
    path: 'ph_down_gain_per_ml',
    label: 'Коэффициент pH-down',
    description: 'Насколько в среднем меняется pH после 1 мл кислоты. Нужен для прогноза pH-down correction и оценки безопасной дозы.',
    type: 'number',
    step: 0.001,
    min: 0.001,
    max: 5,
  },
  {
    path: 'ph_per_ec_ml',
    label: 'Поправка pH от EC',
    description: 'Cross-coupling коэффициент: как EC-доза косвенно влияет на pH. Нужен, чтобы planner учитывал вторичный эффект и не завышал «чистый» EC-ответ.',
    type: 'number',
    step: 0.001,
    min: -2,
    max: 2,
  },
  {
    path: 'ec_per_ph_ml',
    label: 'Поправка EC от pH',
    description: 'Cross-coupling коэффициент: как pH-доза косвенно влияет на EC. Помогает точнее прогнозировать состояние раствора после pH-коррекции.',
    type: 'number',
    step: 0.001,
    min: -2,
    max: 2,
  },
  {
    path: 'confidence',
    label: 'Доверие к калибровке',
    description: 'Оценка качества текущей process calibration в диапазоне 0..1. Чем ниже значение, тем осторожнее нужно трактовать эти коэффициенты.',
    type: 'number',
    step: 0.01,
    min: 0,
    max: 1,
  },
]

const advancedMode = ref(false)
const loading = ref(true)
const saving = ref(false)
const loadError = ref<string | null>(null)
const errorMessage = ref<string | null>(null)
const lastRevision = ref<number | null>(null)
const reason = ref('')
const correctionVersion = ref<number | null>(null)
const correctionTarget = ref<CorrectionTarget>('base')
const calibrationTarget = ref<CalibrationTarget>('none')
const correctionSections = ref<CorrectionCatalogSection[]>([])
const correctionSnapshots = ref<Record<CorrectionTarget, Record<string, unknown>>>({
  base: {},
  solution_fill: {},
  tank_recirc: {},
  irrigation: {},
})
const calibrationSnapshots = ref<Record<ProcessCalibrationMode, Record<string, unknown>>>({
  generic: {},
  solution_fill: {},
  tank_recirc: {},
  irrigation: {},
})
const initialCorrectionSnapshot = ref<Record<string, unknown>>({})
const initialCalibrationSnapshot = ref<Record<string, unknown>>({})
const correctionForm = reactive<Record<string, unknown>>({})
const calibrationForm = reactive<Record<string, unknown>>({})

const visibleCorrectionSections = computed(() =>
  correctionSections.value
    .map((section) => ({
      ...section,
      fields: section.fields.filter((field) => advancedMode.value || !field.advanced_only),
    }))
    .filter((section) => section.fields.length > 0),
)

const correctionPatch = computed<Record<string, unknown>>(() => {
  const patch: Record<string, unknown> = {}
  const fields = correctionSections.value.flatMap((section) => section.fields)

  for (const field of fields) {
    const before = getByPath(initialCorrectionSnapshot.value, field.path)
    const after = getByPath(correctionForm, field.path)
    if (!areLeafValuesEqual(before, after)) {
      patch[field.path] = after
    }
  }

  return patch
})

const calibrationPatch = computed<Record<string, unknown>>(() => {
  if (calibrationTarget.value === 'none') {
    return {}
  }

  const patch: Record<string, unknown> = {}
  for (const field of CALIBRATION_FIELDS) {
    const before = getByPath(initialCalibrationSnapshot.value, field.path)
    const after = getByPath(calibrationForm, field.path)
    if (!areLeafValuesEqual(before, after)) {
      patch[field.path] = after
    }
  }

  return patch
})

const correctionPatchKeys = computed(() => Object.keys(correctionPatch.value))
const calibrationPatchKeys = computed(() => Object.keys(calibrationPatch.value))
const correctionDirty = computed(() => correctionPatchKeys.value.length > 0)
const calibrationDirty = computed(() => calibrationPatchKeys.value.length > 0)
const submitBlocker = computed<string | null>(() => {
  if (!correctionDirty.value && !calibrationDirty.value) {
    return 'Измените хотя бы одно поле correction или process calibration.'
  }

  if (reason.value.trim().length < 3) {
    return 'Укажите причину длиной не менее 3 символов.'
  }

  if (correctionDirty.value && calibrationDirty.value) {
    if (correctionTarget.value === 'base') {
      return 'Базовую correction-конфигурацию и process calibration нельзя отправить одним запросом: endpoint использует один общий phase.'
    }
    if (calibrationTarget.value === 'generic') {
      return '`generic` process calibration нужно сохранять отдельным запросом без correction-изменений.'
    }
    if (correctionTarget.value !== calibrationTarget.value) {
      return 'Совмещённая отправка разрешена только когда correction phase и process calibration phase совпадают.'
    }
  }

  return null
})
const canSubmit = computed(() => !saving.value && submitBlocker.value === null)
const requestPhase = computed<CorrectionLiveEditPhase | null>(() => {
  if (correctionDirty.value) {
    return correctionTarget.value === 'base' ? null : correctionTarget.value
  }
  if (calibrationDirty.value && calibrationTarget.value !== 'none') {
    return calibrationTarget.value
  }
  return null
})
const requestPhaseLabel = computed(() => requestPhase.value ? phaseLabel(requestPhase.value) : 'без phase')

watch(correctionTarget, () => {
  applyCorrectionSnapshot(correctionTarget.value)
})

watch(calibrationTarget, () => {
  applyCalibrationSnapshot(calibrationTarget.value)
})

onMounted(loadDocuments)

async function loadDocuments(): Promise<void> {
  loading.value = true
  loadError.value = null
  errorMessage.value = null

  try {
    const correctionDocument = await automationConfigsApi.get<ZoneCorrectionConfigPayload>(
      'zone',
      props.zoneId,
      'zone.correction',
    )

    const calibrationDocuments = await Promise.all(
      CALIBRATION_TARGETS.map((mode) =>
        automationConfigsApi.get<AutomationDocument<Record<string, unknown>>>(
          'zone',
          props.zoneId,
          processCalibrationNamespace(mode),
        ),
      ),
    )

    correctionSections.value = (correctionDocument.meta?.field_catalog ?? [])
      .map(localizeCorrectionSection)
      .map((section) => ({
        ...section,
        fields: section.fields.filter((field) => LIVE_EDITABLE_CORRECTION_FIELDS.has(field.path)),
      }))
      .filter((section) => section.fields.length > 0)

    correctionVersion.value = correctionDocument.version ?? null

    const resolvedBase = cloneRecord(
      asOptionalRecord(correctionDocument.resolved_config?.base)
      ?? asOptionalRecord(correctionDocument.base_config)
      ?? {},
    )
    const resolvedPhases = asRecord(correctionDocument.resolved_config?.phases)

    correctionSnapshots.value = {
      base: resolvedBase,
      solution_fill: cloneRecord(asOptionalRecord(resolvedPhases.solution_fill) ?? resolvedBase),
      tank_recirc: cloneRecord(asOptionalRecord(resolvedPhases.tank_recirc) ?? resolvedBase),
      irrigation: cloneRecord(asOptionalRecord(resolvedPhases.irrigation) ?? resolvedBase),
    }

    calibrationSnapshots.value = {
      solution_fill: snapshotFromCalibrationDocument(calibrationDocuments[0]),
      tank_recirc: snapshotFromCalibrationDocument(calibrationDocuments[1]),
      irrigation: snapshotFromCalibrationDocument(calibrationDocuments[2]),
      generic: snapshotFromCalibrationDocument(calibrationDocuments[3]),
    }

    applyCorrectionSnapshot(correctionTarget.value)
    applyCalibrationSnapshot(calibrationTarget.value)
  } catch (err: unknown) {
    loadError.value = extractError(err) ?? 'Не удалось загрузить текущие live-снимки correction runtime.'
  } finally {
    loading.value = false
  }
}

function resetForms(): void {
  errorMessage.value = null
  lastRevision.value = null
  reason.value = ''
  applyCorrectionSnapshot(correctionTarget.value)
  applyCalibrationSnapshot(calibrationTarget.value)
}

async function submit(): Promise<void> {
  if (!canSubmit.value) {
    return
  }

  errorMessage.value = null
  lastRevision.value = null
  saving.value = true

  const payload: CorrectionLiveEditPayload = {
    reason: reason.value.trim(),
  }

  if (requestPhase.value !== null) {
    payload.phase = requestPhase.value
  }
  if (correctionDirty.value) {
    payload.correction_patch = correctionPatch.value
  }
  if (calibrationDirty.value) {
    payload.calibration_patch = calibrationPatch.value
  }

  try {
    const response = await zoneConfigModeApi.updateCorrectionLiveEdit(props.zoneId, payload)
    await loadDocuments()
    lastRevision.value = response.config_revision
    reason.value = ''
    emit('applied', response.config_revision)
  } catch (err: unknown) {
    errorMessage.value = extractError(err) ?? 'Не удалось применить live-правку.'
  } finally {
    saving.value = false
  }
}

function applyCorrectionSnapshot(target: CorrectionTarget): void {
  replaceRecord(correctionForm, correctionSnapshots.value[target])
  initialCorrectionSnapshot.value = cloneRecord(correctionSnapshots.value[target])
}

function applyCalibrationSnapshot(target: CalibrationTarget): void {
  if (target === 'none') {
    replaceRecord(calibrationForm, {})
    initialCalibrationSnapshot.value = {}
    return
  }

  replaceRecord(calibrationForm, calibrationSnapshots.value[target])
  initialCalibrationSnapshot.value = cloneRecord(calibrationSnapshots.value[target])
}

function snapshotFromCalibrationDocument(
  document: AutomationDocument<Record<string, unknown>>,
): Record<string, unknown> {
  const payload = asRecord(document.payload)

  return CALIBRATION_FIELDS.reduce<Record<string, unknown>>((acc, field) => {
    acc[field.path] = payload[field.path] ?? null
    return acc
  }, {})
}

function correctionTargetLabel(target: CorrectionTarget): string {
  return target === 'base' ? 'Базовая конфигурация' : `Фазовое переопределение для ${phaseLabel(target)}`
}

function calibrationTargetLabel(target: ProcessCalibrationMode): string {
  return target === 'generic'
    ? PROCESS_CALIBRATION_LABELS.generic
    : `Профиль process calibration для ${phaseLabel(target)}`
}

function phaseLabel(target: CorrectionPhase | ProcessCalibrationMode): string {
  if (target === 'generic') {
    return PROCESS_CALIBRATION_LABELS.generic
  }

  return CORRECTION_PHASE_LABELS[target]
}

function localizeCorrectionSection(section: CorrectionCatalogSection): CorrectionCatalogSection {
  const sectionText = CORRECTION_SECTION_TEXTS[section.key]

  return {
    ...section,
    label: sectionText?.label ?? section.label,
    description: sectionText?.description ?? section.description,
    fields: section.fields.map(localizeCorrectionField),
  }
}

function localizeCorrectionField(field: CorrectionCatalogField): CorrectionCatalogField {
  const fieldText = CORRECTION_FIELD_TEXTS[field.path]
  if (!fieldText) {
    return field
  }

  return {
    ...field,
    label: fieldText.label,
    description: fieldText.description,
  }
}

function fieldTestId(prefix: string, path: string): string {
  return `${prefix}-${path.split('.').join('__')}`
}

function replaceRecord(target: Record<string, unknown>, source: Record<string, unknown>): void {
  Object.keys(target).forEach((key) => {
    delete target[key]
  })

  for (const [key, value] of Object.entries(cloneRecord(source))) {
    target[key] = value
  }
}

function cloneRecord<T extends Record<string, unknown> | null | undefined>(value: T): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {}
  }

  return JSON.parse(JSON.stringify(value)) as Record<string, unknown>
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {}
  }

  return value as Record<string, unknown>
}

function asOptionalRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }

  return value as Record<string, unknown>
}

function getByPath(target: Record<string, unknown>, path: string): unknown {
  return path.split('.').reduce<unknown>((current, segment) => {
    if (!current || typeof current !== 'object' || Array.isArray(current)) {
      return undefined
    }
    return (current as Record<string, unknown>)[segment]
  }, target)
}

function setByPath(target: Record<string, unknown>, path: string, value: unknown): void {
  const segments = path.split('.')
  let current = target

  segments.slice(0, -1).forEach((segment) => {
    const next = current[segment]
    if (!next || typeof next !== 'object' || Array.isArray(next)) {
      current[segment] = {}
    }
    current = current[segment] as Record<string, unknown>
  })

  current[segments[segments.length - 1]] = value
}

function normalizeScalar(
  field: Pick<CorrectionCatalogField, 'type'>,
  raw: string,
): string | number {
  if (field.type === 'string') {
    return raw
  }

  const numeric = Number(raw)
  if (!Number.isFinite(numeric)) {
    return field.type === 'integer' ? 0 : 0
  }

  return field.type === 'integer' ? Math.round(numeric) : numeric
}

function handleScalarInput(
  target: Record<string, unknown>,
  field: Pick<CorrectionCatalogField, 'path' | 'type'>,
  event: Event,
): void {
  const element = event.target as HTMLInputElement
  setByPath(target, field.path, normalizeScalar(field, element.value))
}

function areLeafValuesEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right)
}

function extractError(err: unknown): string | null {
  if (typeof err === 'object' && err !== null) {
    const anyErr = err as { response?: { data?: { message?: string; code?: string } } }
    return anyErr.response?.data?.message ?? anyErr.response?.data?.code ?? null
  }

  return null
}

function buildControllerFieldTexts(kind: 'ph' | 'ec'): Record<string, LocalizedCorrectionText> {
  const metricLabel = kind === 'ph' ? 'pH' : 'EC'
  const contourLabel = kind === 'ph' ? 'pH-контур' : 'EC-контур'
  const doseLabel = kind === 'ph' ? 'pH-коррекции' : 'EC-коррекции'
  const basePath = `controllers.${kind}`

  return {
    [`${basePath}.kp`]: {
      label: 'Kp',
      description: `Пропорциональный коэффициент ${contourLabel}. Чем выше значение, тем агрессивнее runtime реагирует на текущее отклонение ${metricLabel} от цели.`,
    },
    [`${basePath}.ki`]: {
      label: 'Ki',
      description: `Интегральный коэффициент ${contourLabel}. Накопляет историю прошлых отклонений и помогает дотянуть ${metricLabel} до target без постоянной остаточной ошибки.`,
    },
    [`${basePath}.kd`]: {
      label: 'Kd',
      description: `Дифференциальный коэффициент ${contourLabel}. Смягчает резкие изменения и помогает заранее тормозить correction при быстром движении ${metricLabel} к цели.`,
    },
    [`${basePath}.deadband`]: {
      label: 'Deadband',
      description: `Мёртвая зона вокруг target ${metricLabel}. Пока отклонение меньше этого порога, runtime не считает, что нужна новая ${doseLabel}.`,
    },
    [`${basePath}.max_dose_ml`]: {
      label: 'Максимум дозы контроллера',
      description: `Дополнительный лимит объёма для ${contourLabel}. Не даёт planner-у выдать слишком большую ${doseLabel} даже при крупной ошибке.`,
    },
    [`${basePath}.min_interval_sec`]: {
      label: 'Минимальный интервал между дозами',
      description: 'Минимальная пауза между двумя дозами одного контура. Нужна, чтобы раствор успел проявить эффект, а runtime не ушёл в частую «стрельбу».',
    },
    [`${basePath}.max_integral`]: {
      label: 'Предел интегратора',
      description: `Ограничивает накопление integral term в ${contourLabel}. Защищает от windup, когда система долго не может сдвинуть ${metricLabel}.`,
    },
    [`${basePath}.derivative_filter_alpha`]: {
      label: 'Фильтр производной',
      description: `Сглаживание derivative term для ${contourLabel}. Чем выше фильтр, тем меньше влияние шумных скачков телеметрии на решение о дозе.`,
    },
    [`${basePath}.anti_windup.enabled`]: {
      label: 'Anti-windup',
      description: `Разрешает защиту от накопления избыточного integral term, когда ${contourLabel} упирается в лимиты дозы или долго не видит эффекта.`,
    },
    [`${basePath}.overshoot_guard.enabled`]: {
      label: 'Overshoot guard',
      description: `Включает жёсткую защиту от перерегулирования: runtime ограничивает correction, если прогнозирует выход ${metricLabel} за допустимый диапазон.`,
    },
    [`${basePath}.overshoot_guard.hard_min`]: {
      label: 'Жёсткий минимум',
      description: `Нижняя граница ${metricLabel}, ниже которой planner не должен проталкивать раствор даже при сильном отклонении от target.`,
    },
    [`${basePath}.overshoot_guard.hard_max`]: {
      label: 'Жёсткий максимум',
      description: `Верхняя граница ${metricLabel}, выше которой planner не должен проталкивать раствор даже если формально correction ещё не завершена.`,
    },
    [`${basePath}.no_effect.enabled`]: {
      label: 'Контроль отсутствия эффекта',
      description: `Включает накопление no-effect сигналов, если после доз ${contourLabel} не видит ожидаемого изменения ${metricLabel}.`,
    },
    [`${basePath}.no_effect.max_count`]: {
      label: 'Лимит no-effect событий',
      description: 'Сколько подряд безрезультатных correction-событий допускается, прежде чем runtime поднимет проблему и начнёт деградировать или блокироваться.',
    },
    [`${basePath}.observe.telemetry_period_sec`]: {
      label: 'Период телеметрии',
      description: `Ожидаемый шаг новых samples для ${contourLabel}. Используется при оценке полноты и плотности decision window.`,
    },
    [`${basePath}.observe.window_min_samples`]: {
      label: 'Минимум samples в окне',
      description: `Минимальное число точек телеметрии, без которого correction не считает decision window пригодным для анализа ${metricLabel}.`,
    },
    [`${basePath}.observe.decision_window_sec`]: {
      label: 'Длина decision window',
      description: `Сколько секунд истории ${metricLabel} берётся в окно принятия решения. Чем окно больше, тем устойчивее оценка, но тем медленнее реакция runtime.`,
    },
    [`${basePath}.observe.observe_poll_sec`]: {
      label: 'Шаг перепроверки окна',
      description: 'Как часто correction перепроверяет, набралось ли достаточное и устойчивое окно наблюдения после дозы.',
    },
    [`${basePath}.observe.min_effect_fraction`]: {
      label: 'Минимальная доля эффекта',
      description: 'Какую долю от ожидаемого эффекта нужно увидеть, чтобы correction признала дозу результативной, а не no-effect случаем.',
    },
    [`${basePath}.observe.stability_max_slope`]: {
      label: 'Порог устойчивости slope',
      description: `Максимально допустимый slope в decision window. Если тренд ${metricLabel} слишком крутой, окно считается ещё нестабильным и решение откладывается.`,
    },
    [`${basePath}.observe.no_effect_consecutive_limit`]: {
      label: 'Лимит подряд идущих no-effect',
      description: `Сколько подряд неудачных correction-циклов для ${contourLabel} допускается до срабатывания no-effect protection.`,
    },
  }
}
</script>
