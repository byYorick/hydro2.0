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
        class="space-y-4"
      >
        <div class="rounded-xl border border-[color:var(--border-muted)] p-3 space-y-3">
          <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
            Климат и вентиляция
          </h4>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <label class="text-xs text-[color:var(--text-muted)]">
              Автоклимат
              <select
                v-model="draftClimateForm.enabled"
                class="input-select mt-1 w-full"
              >
                <option :value="true">Включен</option>
                <option :value="false">Выключен</option>
              </select>
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Интервал климата (мин)
              <input
                v-model.number="draftClimateForm.intervalMinutes"
                type="number"
                min="1"
                max="1440"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Ручной override (мин)
              <input
                v-model.number="draftClimateForm.overrideMinutes"
                type="number"
                min="5"
                max="120"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Температура день
              <input
                v-model.number="draftClimateForm.dayTemp"
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
                v-model.number="draftClimateForm.nightTemp"
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
                v-model.number="draftClimateForm.dayHumidity"
                type="number"
                min="30"
                max="90"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Влажность ночь
              <input
                v-model.number="draftClimateForm.nightHumidity"
                type="number"
                min="30"
                max="90"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Min форточек (%)
              <input
                v-model.number="draftClimateForm.ventMinPercent"
                type="number"
                min="0"
                max="100"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Max форточек (%)
              <input
                v-model.number="draftClimateForm.ventMaxPercent"
                type="number"
                min="0"
                max="100"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              День начинается
              <input
                v-model="draftClimateForm.dayStart"
                type="time"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Ночь начинается
              <input
                v-model="draftClimateForm.nightStart"
                type="time"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Внешняя телеметрия
              <select
                v-model="draftClimateForm.useExternalTelemetry"
                class="input-select mt-1 w-full"
              >
                <option :value="true">Использовать</option>
                <option :value="false">Игнорировать</option>
              </select>
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Мин. внешняя t°C
              <input
                v-model.number="draftClimateForm.outsideTempMin"
                type="number"
                min="-30"
                max="45"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Макс. внешняя t°C
              <input
                v-model.number="draftClimateForm.outsideTempMax"
                type="number"
                min="-30"
                max="45"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Макс. внешняя влажность (%)
              <input
                v-model.number="draftClimateForm.outsideHumidityMax"
                type="number"
                min="20"
                max="100"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)] md:col-span-2">
              Ручной override климата
              <select
                v-model="draftClimateForm.manualOverrideEnabled"
                class="input-select mt-1 w-full"
              >
                <option :value="true">Включен</option>
                <option :value="false">Выключен</option>
              </select>
            </label>
          </div>
        </div>
      </section>

      <section
        v-else-if="step === 2"
        class="space-y-4"
      >
        <div class="rounded-xl border border-[color:var(--border-muted)] p-3 space-y-3">
          <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
            Полив и баки
          </h4>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <label class="text-xs text-[color:var(--text-muted)]">
              Тип системы
              <select
                v-model="draftWaterForm.systemType"
                class="input-select mt-1 w-full"
                :disabled="isSystemTypeLocked"
              >
                <option value="drip">drip</option>
                <option value="substrate_trays">substrate_trays</option>
                <option value="nft">nft</option>
              </select>
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Баков
              <input
                v-model.number="draftWaterForm.tanksCount"
                type="number"
                min="2"
                max="3"
                class="input-field mt-1 w-full"
                :disabled="isSystemTypeLocked || draftWaterForm.systemType === 'drip'"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Целевой pH
              <input
                v-model.number="draftWaterForm.targetPh"
                type="number"
                min="4"
                max="9"
                step="0.1"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Целевой EC
              <input
                v-model.number="draftWaterForm.targetEc"
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
                v-model.number="draftWaterForm.intervalMinutes"
                type="number"
                min="5"
                max="1440"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Длительность полива (сек)
              <input
                v-model.number="draftWaterForm.durationSeconds"
                type="number"
                min="1"
                max="3600"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Объём чистого бака (л)
              <input
                v-model.number="draftWaterForm.cleanTankFillL"
                type="number"
                min="10"
                max="5000"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Объём бака раствора (л)
              <input
                v-model.number="draftWaterForm.nutrientTankTargetL"
                type="number"
                min="10"
                max="5000"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Порция полива (л)
              <input
                v-model.number="draftWaterForm.irrigationBatchL"
                type="number"
                min="1"
                max="500"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Температура набора (°C)
              <input
                v-model.number="draftWaterForm.fillTemperatureC"
                type="number"
                min="5"
                max="35"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Окно набора от
              <input
                v-model="draftWaterForm.fillWindowStart"
                type="time"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Окно набора до
              <input
                v-model="draftWaterForm.fillWindowEnd"
                type="time"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Ручной полив (сек)
              <input
                v-model.number="draftWaterForm.manualIrrigationSeconds"
                type="number"
                min="1"
                max="3600"
                class="input-field mt-1 w-full"
              />
            </label>
          </div>
        </div>

        <div class="rounded-xl border border-[color:var(--border-muted)] p-3 space-y-3">
          <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
            Диагностика и startup runtime
          </h4>
          <details class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3">
            <summary class="cursor-pointer text-xs font-semibold text-[color:var(--text-primary)]">
              Подробное описание параметров AE (на русском)
            </summary>
            <dl class="mt-2 grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-2 text-xs">
              <div>
                <dt class="font-mono text-[color:var(--text-primary)]">
                  diagnostics.workflow
                </dt>
                <dd class="text-[color:var(--text-dim)]">
                  Выбирает сценарий старта: `startup` для 2 баков, `cycle_start` для 3 баков, `diagnostics` только диагностика.
                </dd>
              </div>
              <div>
                <dt class="font-mono text-[color:var(--text-primary)]">
                  diagnostics.interval_sec
                </dt>
                <dd class="text-[color:var(--text-dim)]">
                  Период запуска диагностики и проверок в рантайме.
                </dd>
              </div>
              <div>
                <dt class="font-mono text-[color:var(--text-primary)]">
                  refill.duration_sec / refill.timeout_sec
                </dt>
                <dd class="text-[color:var(--text-dim)]">
                  Длительность одной попытки refill и общий таймаут ожидания её завершения.
                </dd>
              </div>
              <div>
                <dt class="font-mono text-[color:var(--text-primary)]">
                  startup.*_timeout_sec
                </dt>
                <dd class="text-[color:var(--text-dim)]">
                  Лимиты времени для фаз clean_fill, solution_fill и prepare_recirculation в startup.
                </dd>
              </div>
              <div>
                <dt class="font-mono text-[color:var(--text-primary)]">
                  startup.clean_fill_retry_cycles
                </dt>
                <dd class="text-[color:var(--text-dim)]">
                  Сколько раз можно повторить clean_fill, если фаза не завершилась успешно.
                </dd>
              </div>
              <div>
                <dt class="font-mono text-[color:var(--text-primary)]">
                  irrigation_recovery.max_continue_attempts / timeout_sec
                </dt>
                <dd class="text-[color:var(--text-dim)]">
                  Сколько попыток recovery допускается и сколько максимум длится recovery-сценарий.
                </dd>
              </div>
              <div>
                <dt class="font-mono text-[color:var(--text-primary)]">
                  prepare_tolerance.ec_pct / ph_pct
                </dt>
                <dd class="text-[color:var(--text-dim)]">
                  Допуски по EC/pH, при которых подготовка раствора считается достаточной для продолжения.
                </dd>
              </div>
              <div>
                <dt class="font-mono text-[color:var(--text-primary)]">
                  correction.max_ec_correction_attempts / max_ph_correction_attempts
                </dt>
                <dd class="text-[color:var(--text-dim)]">
                  Лимиты количества попыток дозирования EC и pH в одном цикле коррекции.
                </dd>
              </div>
              <div>
                <dt class="font-mono text-[color:var(--text-primary)]">
                  correction.prepare_recirculation_max_attempts / prepare_recirculation_max_correction_attempts
                </dt>
                <dd class="text-[color:var(--text-dim)]">
                  Лимит окон рециркуляции до terminal fail и общий лимит шагов коррекции внутри окон.
                </dd>
              </div>
              <div>
                <dt class="font-mono text-[color:var(--text-primary)]">
                  correction.ec_mix_wait_sec / ph_mix_wait_sec / stabilization_sec
                </dt>
                <dd class="text-[color:var(--text-dim)]">
                  Времена ожидания смешивания после дозирования и время стабилизации перед проверкой.
                </dd>
              </div>
              <div>
                <dt class="font-mono text-[color:var(--text-primary)]">
                  irrigation.interval_sec / duration_sec
                </dt>
                <dd class="text-[color:var(--text-dim)]">
                  Период поливов и длительность одного поливочного импульса.
                </dd>
              </div>
              <div>
                <dt class="font-mono text-[color:var(--text-primary)]">
                  climate.interval_sec / lighting.interval_sec
                </dt>
                <dd class="text-[color:var(--text-dim)]">
                  Частота пересчёта климата и частота применения правил досветки.
                </dd>
              </div>
              <div>
                <dt class="font-mono text-[color:var(--text-primary)]">
                  solution_change.interval_sec / duration_sec
                </dt>
                <dd class="text-[color:var(--text-dim)]">
                  Период и длительность цикла полной смены раствора.
                </dd>
              </div>
              <div class="md:col-span-2">
                <dt class="font-mono text-[color:var(--text-primary)]">
                  refill.required_node_types / refill.channel
                </dt>
                <dd class="text-[color:var(--text-dim)]">
                  Какие типы нод обязательны для refill и через какой канал отправлять команду refill.
                </dd>
              </div>
            </dl>
          </details>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <label class="text-xs text-[color:var(--text-muted)]">
              Диагностика
              <select
                v-model="draftWaterForm.diagnosticsEnabled"
                class="input-select mt-1 w-full"
              >
                <option :value="true">Включена</option>
                <option :value="false">Выключена</option>
              </select>
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Интервал диагностики (мин)
              <input
                v-model.number="draftWaterForm.diagnosticsIntervalMinutes"
                type="number"
                min="1"
                max="1440"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Режим диагностики (diagnostics.workflow)
              <select
                v-model="draftWaterForm.diagnosticsWorkflow"
                class="input-select mt-1 w-full"
              >
                <option value="startup">startup</option>
                <option
                  value="cycle_start"
                  :disabled="draftWaterForm.tanksCount === 2"
                >
                  cycle_start
                </option>
                <option value="diagnostics">diagnostics</option>
              </select>
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Порог полного бака (0..1)
              <input
                v-model.number="draftWaterForm.cleanTankFullThreshold"
                type="number"
                min="0.05"
                max="1"
                step="0.01"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Длительность refill (сек)
              <input
                v-model.number="draftWaterForm.refillDurationSeconds"
                type="number"
                min="1"
                max="3600"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Таймаут refill (сек)
              <input
                v-model.number="draftWaterForm.refillTimeoutSeconds"
                type="number"
                min="30"
                max="86400"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Таймаут набора чистой воды (startup.clean_fill_timeout_sec)
              <input
                v-model.number="draftWaterForm.startupCleanFillTimeoutSeconds"
                type="number"
                min="30"
                max="86400"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Таймаут набора раствора (startup.solution_fill_timeout_sec)
              <input
                v-model.number="draftWaterForm.startupSolutionFillTimeoutSeconds"
                type="number"
                min="30"
                max="86400"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Таймаут рециркуляции подготовки (startup.prepare_recirculation_timeout_sec)
              <input
                v-model.number="draftWaterForm.startupPrepareRecirculationTimeoutSeconds"
                type="number"
                min="30"
                max="86400"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Повторы clean_fill (startup.clean_fill_retry_cycles)
              <input
                v-model.number="draftWaterForm.startupCleanFillRetryCycles"
                type="number"
                min="0"
                max="20"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Лимит продолжений recovery (irrigation_recovery.max_continue_attempts)
              <input
                v-model.number="draftWaterForm.irrigationRecoveryMaxContinueAttempts"
                type="number"
                min="1"
                max="30"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Таймаут recovery (irrigation_recovery.timeout_sec)
              <input
                v-model.number="draftWaterForm.irrigationRecoveryTimeoutSeconds"
                type="number"
                min="30"
                max="86400"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Допуск EC подготовки (prepare_tolerance.ec_pct)
              <input
                v-model.number="draftWaterForm.prepareToleranceEcPct"
                type="number"
                min="0.1"
                max="100"
                step="0.1"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Допуск pH подготовки (prepare_tolerance.ph_pct)
              <input
                v-model.number="draftWaterForm.prepareTolerancePhPct"
                type="number"
                min="0.1"
                max="100"
                step="0.1"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Лимит попыток EC-коррекции (correction.max_ec_correction_attempts)
              <input
                v-model.number="draftWaterForm.correctionMaxEcCorrectionAttempts"
                type="number"
                min="1"
                max="50"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Лимит попыток pH-коррекции (correction.max_ph_correction_attempts)
              <input
                v-model.number="draftWaterForm.correctionMaxPhCorrectionAttempts"
                type="number"
                min="1"
                max="50"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Лимит окон рециркуляции (correction.prepare_recirculation_max_attempts)
              <input
                v-model.number="draftWaterForm.correctionPrepareRecirculationMaxAttempts"
                type="number"
                min="1"
                max="50"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Общий лимит correction-шагов (correction.prepare_recirculation_max_correction_attempts)
              <input
                v-model.number="draftWaterForm.correctionPrepareRecirculationMaxCorrectionAttempts"
                type="number"
                min="1"
                max="500"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Ожидание смешивания EC (correction.ec_mix_wait_sec)
              <input
                v-model.number="draftWaterForm.correctionEcMixWaitSec"
                type="number"
                min="10"
                max="3600"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Ожидание смешивания pH (correction.ph_mix_wait_sec)
              <input
                v-model.number="draftWaterForm.correctionPhMixWaitSec"
                type="number"
                min="10"
                max="3600"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Время стабилизации (correction.stabilization_sec)
              <input
                v-model.number="draftWaterForm.correctionStabilizationSec"
                type="number"
                min="0"
                max="3600"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)] md:col-span-2">
              Обязательные типы нод для refill (CSV)
              <input
                v-model="draftWaterForm.refillRequiredNodeTypes"
                type="text"
                class="input-field mt-1 w-full"
                placeholder="irrig,climate,light"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Канал refill
              <input
                v-model="draftWaterForm.refillPreferredChannel"
                type="text"
                class="input-field mt-1 w-full"
                placeholder="fill_valve"
              />
            </label>
          </div>
        </div>

        <div class="rounded-xl border border-[color:var(--border-muted)] p-3 space-y-3">
          <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
            Смена раствора
          </h4>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <label class="text-xs text-[color:var(--text-muted)]">
              Активна
              <select
                v-model="draftWaterForm.solutionChangeEnabled"
                class="input-select mt-1 w-full"
              >
                <option :value="true">Включена</option>
                <option :value="false">Выключена</option>
              </select>
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Интервал (мин)
              <input
                v-model.number="draftWaterForm.solutionChangeIntervalMinutes"
                type="number"
                min="1"
                max="1440"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Длительность (сек)
              <input
                v-model.number="draftWaterForm.solutionChangeDurationSeconds"
                type="number"
                min="1"
                max="86400"
                class="input-field mt-1 w-full"
              />
            </label>
          </div>
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
        class="space-y-4"
      >
        <div class="rounded-xl border border-[color:var(--border-muted)] p-3 space-y-3">
          <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
            Досветка
          </h4>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <label class="text-xs text-[color:var(--text-muted)]">
              Досветка
              <select
                v-model="draftLightingForm.enabled"
                class="input-select mt-1 w-full"
              >
                <option :value="true">Включена</option>
                <option :value="false">Выключена</option>
              </select>
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Освещённость днём (lux)
              <input
                v-model.number="draftLightingForm.luxDay"
                type="number"
                min="0"
                max="120000"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Освещённость ночью (lux)
              <input
                v-model.number="draftLightingForm.luxNight"
                type="number"
                min="0"
                max="120000"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Часов света
              <input
                v-model.number="draftLightingForm.hoursOn"
                type="number"
                min="0"
                max="24"
                step="0.5"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Интервал досветки (мин)
              <input
                v-model.number="draftLightingForm.intervalMinutes"
                type="number"
                min="1"
                max="1440"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Начало
              <input
                v-model="draftLightingForm.scheduleStart"
                type="time"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Конец
              <input
                v-model="draftLightingForm.scheduleEnd"
                type="time"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Интенсивность ручного режима (%)
              <input
                v-model.number="draftLightingForm.manualIntensity"
                type="number"
                min="0"
                max="100"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Ручной режим (ч)
              <input
                v-model.number="draftLightingForm.manualDurationHours"
                type="number"
                min="0.5"
                max="24"
                step="0.5"
                class="input-field mt-1 w-full"
              />
            </label>
          </div>
        </div>
      </section>

      <p
        v-if="stepError"
        class="text-xs text-red-500 mt-2"
      >
        {{ stepError }}
      </p>
    </div>

    <template #footer>
      <Button
        type="button"
        variant="outline"
        @click="resetDraft"
      >
        Сбросить к рекомендуемым
      </Button>
      <Button
        v-if="step > 1"
        type="button"
        variant="secondary"
        @click="goPrevStep"
      >
        Назад
      </Button>
      <Button
        v-if="step < 3"
        type="button"
        @click="goNextStep"
      >
        Далее
      </Button>
      <Button
        v-else
        type="button"
        :disabled="isApplying"
        @click="emitApply"
      >
        {{ isApplying ? 'Отправка...' : 'Сохранить' }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'
import { clamp, resetToRecommended as resetFormsToRecommended, syncSystemToTankLayout, validateForms } from '@/composables/zoneAutomationFormLogic'
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

interface ZoneAutomationWizardApplyPayload {
  climateForm: ClimateFormState
  waterForm: WaterFormState
  lightingForm: LightingFormState
}

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'apply', payload: ZoneAutomationWizardApplyPayload): void
}>()

const props = defineProps<Props>()

const steps = [
  { id: 1, label: 'Климат' },
  { id: 2, label: 'Водный узел' },
  { id: 3, label: 'Досветка' },
] as const

const step = ref<1 | 2 | 3>(1)
const stepError = ref<string | null>(null)
const draftClimateForm = reactive<ClimateFormState>({ ...props.climateForm })
const draftWaterForm = reactive<WaterFormState>({ ...props.waterForm })
const draftLightingForm = reactive<LightingFormState>({ ...props.lightingForm })

function normalizeWaterRuntimeFields(form: WaterFormState): void {
  form.diagnosticsWorkflow = form.diagnosticsWorkflow === 'startup' ||
    form.diagnosticsWorkflow === 'cycle_start' ||
    form.diagnosticsWorkflow === 'diagnostics'
    ? form.diagnosticsWorkflow
    : form.cycleStartWorkflowEnabled
      ? (form.tanksCount === 2 ? 'startup' : 'cycle_start')
      : 'diagnostics'

  if (form.startupCleanFillTimeoutSeconds === undefined || !Number.isFinite(Number(form.startupCleanFillTimeoutSeconds))) {
    form.startupCleanFillTimeoutSeconds = 900
  }
  if (form.startupSolutionFillTimeoutSeconds === undefined || !Number.isFinite(Number(form.startupSolutionFillTimeoutSeconds))) {
    form.startupSolutionFillTimeoutSeconds = 1350
  }
  if (
    form.startupPrepareRecirculationTimeoutSeconds === undefined ||
    !Number.isFinite(Number(form.startupPrepareRecirculationTimeoutSeconds))
  ) {
    form.startupPrepareRecirculationTimeoutSeconds = 900
  }
  if (form.startupCleanFillRetryCycles === undefined || !Number.isFinite(Number(form.startupCleanFillRetryCycles))) {
    form.startupCleanFillRetryCycles = 1
  }
  if (
    form.irrigationRecoveryMaxContinueAttempts === undefined ||
    !Number.isFinite(Number(form.irrigationRecoveryMaxContinueAttempts))
  ) {
    form.irrigationRecoveryMaxContinueAttempts = 5
  }
  if (form.irrigationRecoveryTimeoutSeconds === undefined || !Number.isFinite(Number(form.irrigationRecoveryTimeoutSeconds))) {
    form.irrigationRecoveryTimeoutSeconds = 600
  }
  if (form.prepareToleranceEcPct === undefined || !Number.isFinite(Number(form.prepareToleranceEcPct))) {
    form.prepareToleranceEcPct = 25
  }
  if (form.prepareTolerancePhPct === undefined || !Number.isFinite(Number(form.prepareTolerancePhPct))) {
    form.prepareTolerancePhPct = 15
  }
  if (form.correctionMaxEcCorrectionAttempts === undefined || !Number.isFinite(Number(form.correctionMaxEcCorrectionAttempts))) {
    form.correctionMaxEcCorrectionAttempts = 5
  }
  if (form.correctionMaxPhCorrectionAttempts === undefined || !Number.isFinite(Number(form.correctionMaxPhCorrectionAttempts))) {
    form.correctionMaxPhCorrectionAttempts = 5
  }
  if (
    form.correctionPrepareRecirculationMaxAttempts === undefined ||
    !Number.isFinite(Number(form.correctionPrepareRecirculationMaxAttempts))
  ) {
    form.correctionPrepareRecirculationMaxAttempts = 3
  }
  if (
    form.correctionPrepareRecirculationMaxCorrectionAttempts === undefined ||
    !Number.isFinite(Number(form.correctionPrepareRecirculationMaxCorrectionAttempts))
  ) {
    form.correctionPrepareRecirculationMaxCorrectionAttempts = 20
  }
  if (form.correctionEcMixWaitSec === undefined || !Number.isFinite(Number(form.correctionEcMixWaitSec))) {
    form.correctionEcMixWaitSec = 120
  }
  if (form.correctionPhMixWaitSec === undefined || !Number.isFinite(Number(form.correctionPhMixWaitSec))) {
    form.correctionPhMixWaitSec = 60
  }
  if (form.correctionStabilizationSec === undefined || !Number.isFinite(Number(form.correctionStabilizationSec))) {
    form.correctionStabilizationSec = 60
  }
  if (form.twoTankCleanFillStartSteps === undefined || !Number.isFinite(Number(form.twoTankCleanFillStartSteps))) {
    form.twoTankCleanFillStartSteps = 1
  }
  if (form.twoTankCleanFillStopSteps === undefined || !Number.isFinite(Number(form.twoTankCleanFillStopSteps))) {
    form.twoTankCleanFillStopSteps = 1
  }
  if (form.twoTankSolutionFillStartSteps === undefined || !Number.isFinite(Number(form.twoTankSolutionFillStartSteps))) {
    form.twoTankSolutionFillStartSteps = 3
  }
  if (form.twoTankSolutionFillStopSteps === undefined || !Number.isFinite(Number(form.twoTankSolutionFillStopSteps))) {
    form.twoTankSolutionFillStopSteps = 3
  }
  if (
    form.twoTankPrepareRecirculationStartSteps === undefined ||
    !Number.isFinite(Number(form.twoTankPrepareRecirculationStartSteps))
  ) {
    form.twoTankPrepareRecirculationStartSteps = 3
  }
  if (
    form.twoTankPrepareRecirculationStopSteps === undefined ||
    !Number.isFinite(Number(form.twoTankPrepareRecirculationStopSteps))
  ) {
    form.twoTankPrepareRecirculationStopSteps = 3
  }
  if (
    form.twoTankIrrigationRecoveryStartSteps === undefined ||
    !Number.isFinite(Number(form.twoTankIrrigationRecoveryStartSteps))
  ) {
    form.twoTankIrrigationRecoveryStartSteps = 4
  }
  if (
    form.twoTankIrrigationRecoveryStopSteps === undefined ||
    !Number.isFinite(Number(form.twoTankIrrigationRecoveryStopSteps))
  ) {
    form.twoTankIrrigationRecoveryStopSteps = 3
  }

  form.startupCleanFillTimeoutSeconds = clamp(Math.round(form.startupCleanFillTimeoutSeconds), 30, 86400)
  form.startupSolutionFillTimeoutSeconds = clamp(Math.round(form.startupSolutionFillTimeoutSeconds), 30, 86400)
  form.startupPrepareRecirculationTimeoutSeconds = clamp(Math.round(form.startupPrepareRecirculationTimeoutSeconds), 30, 86400)
  form.startupCleanFillRetryCycles = clamp(Math.round(form.startupCleanFillRetryCycles), 0, 20)
  form.irrigationRecoveryMaxContinueAttempts = clamp(Math.round(form.irrigationRecoveryMaxContinueAttempts), 1, 30)
  form.irrigationRecoveryTimeoutSeconds = clamp(Math.round(form.irrigationRecoveryTimeoutSeconds), 30, 86400)
  form.prepareToleranceEcPct = clamp(form.prepareToleranceEcPct, 0.1, 100)
  form.prepareTolerancePhPct = clamp(form.prepareTolerancePhPct, 0.1, 100)
  form.correctionMaxEcCorrectionAttempts = clamp(Math.round(form.correctionMaxEcCorrectionAttempts), 1, 50)
  form.correctionMaxPhCorrectionAttempts = clamp(Math.round(form.correctionMaxPhCorrectionAttempts), 1, 50)
  form.correctionPrepareRecirculationMaxAttempts = clamp(Math.round(form.correctionPrepareRecirculationMaxAttempts), 1, 50)
  form.correctionPrepareRecirculationMaxCorrectionAttempts = clamp(
    Math.round(form.correctionPrepareRecirculationMaxCorrectionAttempts),
    1,
    500
  )
  form.correctionEcMixWaitSec = clamp(Math.round(form.correctionEcMixWaitSec), 10, 3600)
  form.correctionPhMixWaitSec = clamp(Math.round(form.correctionPhMixWaitSec), 10, 3600)
  form.correctionStabilizationSec = clamp(Math.round(form.correctionStabilizationSec), 0, 3600)
  form.twoTankCleanFillStartSteps = clamp(Math.round(form.twoTankCleanFillStartSteps), 1, 12)
  form.twoTankCleanFillStopSteps = clamp(Math.round(form.twoTankCleanFillStopSteps), 1, 12)
  form.twoTankSolutionFillStartSteps = clamp(Math.round(form.twoTankSolutionFillStartSteps), 1, 12)
  form.twoTankSolutionFillStopSteps = clamp(Math.round(form.twoTankSolutionFillStopSteps), 1, 12)
  form.twoTankPrepareRecirculationStartSteps = clamp(Math.round(form.twoTankPrepareRecirculationStartSteps), 1, 12)
  form.twoTankPrepareRecirculationStopSteps = clamp(Math.round(form.twoTankPrepareRecirculationStopSteps), 1, 12)
  form.twoTankIrrigationRecoveryStartSteps = clamp(Math.round(form.twoTankIrrigationRecoveryStartSteps), 1, 12)
  form.twoTankIrrigationRecoveryStopSteps = clamp(Math.round(form.twoTankIrrigationRecoveryStopSteps), 1, 12)
}

function syncWorkflowByTopology(form: WaterFormState): void {
  if (form.tanksCount === 2 && form.diagnosticsWorkflow === 'cycle_start') {
    form.diagnosticsWorkflow = 'startup'
  } else if (form.tanksCount === 3 && form.diagnosticsWorkflow === 'startup') {
    form.diagnosticsWorkflow = 'cycle_start'
  }

  form.cycleStartWorkflowEnabled = form.diagnosticsWorkflow !== 'diagnostics'
}

function syncDraftFromProps(): void {
  Object.assign(draftClimateForm, props.climateForm)
  Object.assign(draftWaterForm, props.waterForm)
  Object.assign(draftLightingForm, props.lightingForm)
  normalizeWaterRuntimeFields(draftWaterForm)
  syncWorkflowByTopology(draftWaterForm)
}

function goPrevStep(): void {
  if (step.value === 3) {
    step.value = 2
    return
  }
  if (step.value === 2) {
    step.value = 1
  }
}

function goNextStep(): void {
  if (step.value === 1) {
    if (draftClimateForm.ventMinPercent > draftClimateForm.ventMaxPercent) {
      stepError.value = 'Минимум открытия форточек не может быть больше максимума.'
      return
    }
    stepError.value = null
    step.value = 2
    return
  }
  if (step.value === 2) {
    normalizeWaterRuntimeFields(draftWaterForm)
    syncWorkflowByTopology(draftWaterForm)

    const waterError = validateForms({ climateForm: draftClimateForm, waterForm: draftWaterForm })
    if (waterError) {
      stepError.value = waterError
      return
    }
    stepError.value = null
    step.value = 3
  }
}

function resetDraft(): void {
  resetFormsToRecommended({
    climateForm: draftClimateForm,
    waterForm: draftWaterForm,
    lightingForm: draftLightingForm,
  })
  normalizeWaterRuntimeFields(draftWaterForm)
  syncWorkflowByTopology(draftWaterForm)
  step.value = 1
  stepError.value = null
}

function emitApply(): void {
  normalizeWaterRuntimeFields(draftWaterForm)
  syncWorkflowByTopology(draftWaterForm)

  const waterFormForApply: WaterFormState = { ...draftWaterForm }
  if (waterFormForApply.systemType === 'drip') {
    waterFormForApply.tanksCount = 2
    waterFormForApply.enableDrainControl = false
  } else {
    waterFormForApply.tanksCount = waterFormForApply.tanksCount === 3 ? 3 : 2
    if (waterFormForApply.tanksCount === 2) {
      waterFormForApply.enableDrainControl = false
    }
  }

  syncWorkflowByTopology(waterFormForApply)

  emit('apply', {
    climateForm: { ...draftClimateForm },
    waterForm: waterFormForApply,
    lightingForm: { ...draftLightingForm },
  })
}

watch(
  () => draftWaterForm.systemType,
  (systemType) => {
    syncSystemToTankLayout(draftWaterForm, systemType)
    normalizeWaterRuntimeFields(draftWaterForm)
    syncWorkflowByTopology(draftWaterForm)
  },
  { immediate: true },
)

watch(
  () => draftWaterForm.tanksCount,
  (tanksCount) => {
    const normalizedTanksCount = Math.round(Number(tanksCount)) === 3 ? 3 : 2

    if (draftWaterForm.systemType === 'drip') {
      if (draftWaterForm.tanksCount !== 2) {
        draftWaterForm.tanksCount = 2
      }
      draftWaterForm.enableDrainControl = false
      syncWorkflowByTopology(draftWaterForm)
      return
    }

    if (draftWaterForm.tanksCount !== normalizedTanksCount) {
      draftWaterForm.tanksCount = normalizedTanksCount
    }
    if (normalizedTanksCount === 2) {
      draftWaterForm.enableDrainControl = false
    }
    syncWorkflowByTopology(draftWaterForm)
  },
)

watch(
  () => draftWaterForm.diagnosticsWorkflow,
  () => {
    syncWorkflowByTopology(draftWaterForm)
  },
)

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      syncDraftFromProps()
      step.value = 1
      stepError.value = null
    }
  },
)
</script>
