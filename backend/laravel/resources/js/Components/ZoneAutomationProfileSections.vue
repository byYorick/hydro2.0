<template>
  <div class="space-y-4">
    <section class="rounded-xl border border-[color:var(--border-muted)]">
      <details open class="group">
        <summary class="flex cursor-pointer list-none items-start justify-between gap-3 p-4">
          <div>
            <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
              Полив и накопление
            </h4>
            <p class="mt-1 text-xs text-[color:var(--text-dim)]">
              Основной irrigation node, водная топология и runtime настройки полива.
            </p>
          </div>
          <span class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
            Свернуть
          </span>
        </summary>

        <div class="space-y-4 border-t border-[color:var(--border-muted)] p-4">

          <div
            v-if="showNodeBindings && assignments"
            class="grid grid-cols-1 md:grid-cols-2 gap-3"
          >
            <div class="grid grid-cols-1 md:grid-cols-[minmax(0,1fr),auto] gap-2 items-end">
              <label class="text-xs text-[color:var(--text-muted)]">
                Нода полива и накопления
                <select
                  v-model.number="assignments.irrigation"
                  class="input-select mt-1 w-full"
                  :disabled="!canConfigure"
                >
                  <option :value="null">
                    Выберите общий узел полива/накопления
                  </option>
                  <option
                    v-for="node in irrigationCandidates"
                    :key="node.id"
                    :value="node.id"
                  >
                    {{ nodeLabel(node) }}
                  </option>
                </select>
              </label>
              <div v-if="showBindButtons || showRefreshButtons" class="flex items-center gap-2">
                <Button
                  v-if="showBindButtons"
                  size="sm"
                  variant="secondary"
                  :disabled="!canBindSelected(assignments?.irrigation)"
                  @click="emit('bind-devices', ['irrigation'])"
                >
                  {{ bindingInProgress ? 'Привязка...' : 'Привязать' }}
                </Button>
                <Button
                  v-if="showRefreshButtons"
                  size="sm"
                  variant="ghost"
                  :disabled="!canRefreshNodes"
                  @click="emit('refresh-nodes')"
                >
                  {{ refreshingNodes ? 'Обновление...' : 'Обновить' }}
                </Button>
              </div>
            </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
        <label class="text-xs text-[color:var(--text-muted)]">
          Тип системы
          <select
            v-model="waterForm.systemType"
            class="input-select mt-1 w-full"
            :disabled="!canConfigure || isSystemTypeLocked"
          >
            <option value="drip">drip</option>
            <option value="substrate_trays">substrate_trays</option>
            <option value="nft">nft</option>
          </select>
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Баков
          <input
            v-model.number="waterForm.tanksCount"
            type="number"
            min="2"
            max="3"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure || isSystemTypeLocked || waterForm.systemType === 'drip'"
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
            :disabled="!canConfigure"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Длительность полива (сек)
          <input
            v-model.number="waterForm.durationSeconds"
            type="number"
            min="1"
            max="3600"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Объём чистого бака (л)
          <input
            v-model.number="waterForm.cleanTankFillL"
            type="number"
            min="10"
            max="5000"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Объём бака раствора (л)
          <input
            v-model.number="waterForm.nutrientTankTargetL"
            type="number"
            min="10"
            max="5000"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Порция полива (л)
          <input
            v-model.number="waterForm.irrigationBatchL"
            type="number"
            min="1"
            max="500"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Температура набора (°C)
          <input
            v-model.number="waterForm.fillTemperatureC"
            type="number"
            min="5"
            max="35"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Ручной полив (сек)
          <input
            v-model.number="waterForm.manualIrrigationSeconds"
            type="number"
            min="1"
            max="3600"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Окно набора от
          <input
            v-model="waterForm.fillWindowStart"
            type="time"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Окно набора до
          <input
            v-model="waterForm.fillWindowEnd"
            type="time"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Контроль дренажа
          <select
            v-model="waterForm.enableDrainControl"
            class="input-select mt-1 w-full"
            :disabled="!canConfigure || waterForm.tanksCount !== 3"
          >
            <option :value="true">Включен</option>
            <option :value="false">Выключен</option>
          </select>
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Цель дренажа (%)
          <input
            v-model.number="waterForm.drainTargetPercent"
            type="number"
            min="0"
            max="100"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure || waterForm.tanksCount !== 3 || !waterForm.enableDrainControl"
          />
        </label>
          </div>

          <details class="rounded-xl border border-[color:var(--border-muted)] p-3 space-y-3">
            <summary class="cursor-pointer text-sm font-semibold text-[color:var(--text-primary)]">
              Advanced runtime Automation Engine
            </summary>
            <div class="mt-3 space-y-4">
          <div class="rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-3 py-2 text-xs text-[color:var(--text-dim)]">
            В этом блоке только low-level runtime guards и execution limits AE. Основные цели, объёмы и интервалы остаются выше.
          </div>

          <div class="rounded-xl border border-[color:var(--border-muted)] p-3 space-y-3">
            <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">
              Startup, refill и recovery
            </h5>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
              <label class="text-xs text-[color:var(--text-muted)]">
                Диагностика
                <select
                  v-model="waterForm.diagnosticsEnabled"
                  class="input-select mt-1 w-full"
                  :disabled="!canConfigure"
                >
                  <option :value="true">Включена</option>
                  <option :value="false">Выключена</option>
                </select>
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Интервал диагностики (мин)
                <input
                  v-model.number="waterForm.diagnosticsIntervalMinutes"
                  type="number"
                  min="1"
                  max="1440"
                  class="input-field mt-1 w-full"
                  :disabled="!canConfigure"
                />
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Режим диагностики
                <select
                  v-model="waterForm.diagnosticsWorkflow"
                  class="input-select mt-1 w-full"
                  :disabled="!canConfigure"
                >
                  <option value="startup">startup</option>
                  <option value="cycle_start" :disabled="waterForm.tanksCount === 2">cycle_start</option>
                  <option value="diagnostics">diagnostics</option>
                </select>
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Порог полного бака (0..1)
                <input
                  v-model.number="waterForm.cleanTankFullThreshold"
                  type="number"
                  min="0.05"
                  max="1"
                  step="0.01"
                  class="input-field mt-1 w-full"
                  :disabled="!canConfigure"
                />
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Длительность refill (сек)
                <input
                  v-model.number="waterForm.refillDurationSeconds"
                  type="number"
                  min="1"
                  max="3600"
                  class="input-field mt-1 w-full"
                  :disabled="!canConfigure"
                />
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Таймаут refill (сек)
                <input
                  v-model.number="waterForm.refillTimeoutSeconds"
                  type="number"
                  min="30"
                  max="86400"
                  class="input-field mt-1 w-full"
                  :disabled="!canConfigure"
                />
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Таймаут набора чистой воды
                <input
                  v-model.number="waterForm.startupCleanFillTimeoutSeconds"
                  type="number"
                  min="30"
                  max="86400"
                  class="input-field mt-1 w-full"
                  :disabled="!canConfigure"
                />
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Таймаут набора раствора
                <input
                  v-model.number="waterForm.startupSolutionFillTimeoutSeconds"
                  type="number"
                  min="30"
                  max="86400"
                  class="input-field mt-1 w-full"
                  :disabled="!canConfigure"
                />
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Таймаут рециркуляции подготовки
                <input
                  v-model.number="waterForm.startupPrepareRecirculationTimeoutSeconds"
                  type="number"
                  min="30"
                  max="86400"
                  class="input-field mt-1 w-full"
                  :disabled="!canConfigure"
                />
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Повторы clean_fill
                <input
                  v-model.number="waterForm.startupCleanFillRetryCycles"
                  type="number"
                  min="0"
                  max="20"
                  class="input-field mt-1 w-full"
                  :disabled="!canConfigure"
                />
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Лимит продолжений recovery
                <input
                  v-model.number="waterForm.irrigationRecoveryMaxContinueAttempts"
                  type="number"
                  min="1"
                  max="30"
                  class="input-field mt-1 w-full"
                  :disabled="!canConfigure"
                />
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Таймаут recovery
                <input
                  v-model.number="waterForm.irrigationRecoveryTimeoutSeconds"
                  type="number"
                  min="30"
                  max="86400"
                  class="input-field mt-1 w-full"
                  :disabled="!canConfigure"
                />
              </label>
              <label class="text-xs text-[color:var(--text-muted)] md:col-span-2">
                Обязательные типы нод для refill (CSV)
                <input
                  v-model="waterForm.refillRequiredNodeTypes"
                  type="text"
                  class="input-field mt-1 w-full"
                  :disabled="!canConfigure"
                />
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Канал refill
                <input
                  v-model="waterForm.refillPreferredChannel"
                  type="text"
                  class="input-field mt-1 w-full"
                  :disabled="!canConfigure"
                />
              </label>
            </div>
          </div>

          <div class="rounded-xl border border-[color:var(--border-muted)] p-3 space-y-3">
            <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">
              Solution change
            </h5>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
              <label class="text-xs text-[color:var(--text-muted)]">
                Смена раствора
                <select
                  v-model="waterForm.solutionChangeEnabled"
                  class="input-select mt-1 w-full"
                  :disabled="!canConfigure"
                >
                  <option :value="true">Включена</option>
                  <option :value="false">Выключена</option>
                </select>
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Интервал смены раствора (мин)
                <input
                  v-model.number="waterForm.solutionChangeIntervalMinutes"
                  type="number"
                  min="1"
                  max="1440"
                  class="input-field mt-1 w-full"
                  :disabled="!canConfigure"
                />
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Длительность смены раствора (сек)
                <input
                  v-model.number="waterForm.solutionChangeDurationSeconds"
                  type="number"
                  min="1"
                  max="86400"
                  class="input-field mt-1 w-full"
                  :disabled="!canConfigure"
                />
              </label>
            </div>
          </div>
            </div>
          </details>
        </div>
      </details>
    </section>

    <section class="rounded-xl border border-[color:var(--border-muted)]">
      <details class="group">
        <summary class="flex cursor-pointer list-none items-start justify-between gap-3 p-4">
          <div>
            <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
              Коррекция
            </h4>
            <p class="mt-1 text-xs text-[color:var(--text-dim)]">
              Отдельные ноды pH и EC, целевые параметры и stage-level correction guards.
            </p>
          </div>
          <span class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
            Свернуть
          </span>
        </summary>

        <div class="space-y-4 border-t border-[color:var(--border-muted)] p-4">

          <div
            v-if="showNodeBindings && assignments"
            class="grid grid-cols-1 md:grid-cols-2 gap-3"
          >
            <div class="grid grid-cols-1 md:grid-cols-[minmax(0,1fr),auto] gap-2 items-end">
              <label class="text-xs text-[color:var(--text-muted)]">
                Нода коррекции pH
                <select
                  v-model.number="assignments.ph_correction"
                  class="input-select mt-1 w-full"
                  :disabled="!canConfigure"
                >
                  <option :value="null">
                    Выберите узел коррекции pH
                  </option>
                  <option
                    v-for="node in phCandidates"
                    :key="node.id"
                    :value="node.id"
                  >
                    {{ nodeLabel(node) }}
                  </option>
                </select>
              </label>
              <div v-if="showBindButtons || showRefreshButtons" class="flex items-center gap-2">
                <Button
                  v-if="showBindButtons"
                  size="sm"
                  variant="secondary"
                  :disabled="!canBindSelected(assignments?.ph_correction)"
                  @click="emit('bind-devices', ['ph_correction'])"
                >
                  {{ bindingInProgress ? 'Привязка...' : 'Привязать' }}
                </Button>
                <Button
                  v-if="showRefreshButtons"
                  size="sm"
                  variant="ghost"
                  :disabled="!canRefreshNodes"
                  @click="emit('refresh-nodes')"
                >
                  {{ refreshingNodes ? 'Обновление...' : 'Обновить' }}
                </Button>
              </div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-[minmax(0,1fr),auto] gap-2 items-end">
              <label class="text-xs text-[color:var(--text-muted)]">
                Нода коррекции EC
                <select
                  v-model.number="assignments.ec_correction"
                  class="input-select mt-1 w-full"
                  :disabled="!canConfigure"
                >
                  <option :value="null">
                    Выберите узел коррекции EC
                  </option>
                  <option
                    v-for="node in ecCandidates"
                    :key="node.id"
                    :value="node.id"
                  >
                    {{ nodeLabel(node) }}
                  </option>
                </select>
              </label>
              <div v-if="showBindButtons || showRefreshButtons" class="flex items-center gap-2">
                <Button
                  v-if="showBindButtons"
                  size="sm"
                  variant="secondary"
                  :disabled="!canBindSelected(assignments?.ec_correction)"
                  @click="emit('bind-devices', ['ec_correction'])"
                >
                  {{ bindingInProgress ? 'Привязка...' : 'Привязать' }}
                </Button>
                <Button
                  v-if="showRefreshButtons"
                  size="sm"
                  variant="ghost"
                  :disabled="!canRefreshNodes"
                  @click="emit('refresh-nodes')"
                >
                  {{ refreshingNodes ? 'Обновление...' : 'Обновить' }}
                </Button>
              </div>
            </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
        <label class="text-xs text-[color:var(--text-muted)]">
          Целевой pH
          <input
            v-model.number="waterForm.targetPh"
            type="number"
            min="4"
            max="9"
            step="0.1"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Целевой EC
          <input
            v-model.number="waterForm.targetEc"
            type="number"
            min="0.1"
            max="10"
            step="0.1"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Коррекция во время полива
          <select
            v-model="waterForm.correctionDuringIrrigation"
            class="input-select mt-1 w-full"
            :disabled="!canConfigure"
          >
            <option :value="true">Включена</option>
            <option :value="false">Выключена</option>
          </select>
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Допуск EC подготовки (%)
          <input
            v-model.number="waterForm.prepareToleranceEcPct"
            type="number"
            min="0.1"
            max="100"
            step="0.1"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Допуск pH подготовки (%)
          <input
            v-model.number="waterForm.prepareTolerancePhPct"
            type="number"
            min="0.1"
            max="100"
            step="0.1"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Лимит попыток EC-коррекции
          <input
            v-model.number="waterForm.correctionMaxEcCorrectionAttempts"
            type="number"
            min="1"
            max="50"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Лимит попыток pH-коррекции
          <input
            v-model.number="waterForm.correctionMaxPhCorrectionAttempts"
            type="number"
            min="1"
            max="50"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Лимит окон рециркуляции
          <input
            v-model.number="waterForm.correctionPrepareRecirculationMaxAttempts"
            type="number"
            min="1"
            max="50"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Лимит correction-шагов
          <input
            v-model.number="waterForm.correctionPrepareRecirculationMaxCorrectionAttempts"
            type="number"
            min="1"
            max="500"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Stage stabilization (sec)
          <input
            v-model.number="waterForm.correctionStabilizationSec"
            type="number"
            min="0"
            max="3600"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
          />
        </label>
          </div>

          <div
            v-if="showCorrectionCalibrationStack && zoneId && sensorCalibrationSettings"
            class="border-t border-[color:var(--border-muted)] pt-4"
          >
            <ZoneCorrectionCalibrationStack
              :zone-id="zoneId"
              :sensor-calibration-settings="sensorCalibrationSettings"
            />
          </div>
        </div>
      </details>
    </section>

    <section class="rounded-xl border border-[color:var(--border-muted)]">
      <details :open="zoneClimateForm.enabled" class="group">
        <summary class="flex cursor-pointer list-none items-start justify-between gap-3 p-4">
          <div>
            <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
              Zone climate
            </h4>
            <p class="mt-1 text-xs text-[color:var(--text-dim)]">
              Отдельный зональный climate subsystem для CO2 и прикорневой вентиляции.
            </p>
          </div>
          <span class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
            {{ zoneClimateForm.enabled ? 'Включено' : 'Выключено' }}
          </span>
        </summary>

        <div class="space-y-4 border-t border-[color:var(--border-muted)] p-4">
          <div class="flex items-center justify-end">
            <label class="inline-flex items-center gap-2 text-xs text-[color:var(--text-muted)]">
              <input
                v-model="zoneClimateForm.enabled"
                type="checkbox"
                :disabled="!canConfigure"
              />
              Управлять климатом зоны
            </label>
          </div>

          <div
            v-if="zoneClimateForm.enabled && showNodeBindings && assignments"
            class="grid grid-cols-1 md:grid-cols-3 gap-3"
          >
            <div class="grid grid-cols-1 md:grid-cols-[minmax(0,1fr),auto] gap-2 items-end">
              <label class="text-xs text-[color:var(--text-muted)]">
                Датчик CO2
                <select
                  v-model.number="assignments.co2_sensor"
                  class="input-select mt-1 w-full"
                  :disabled="!canConfigure"
                >
                  <option :value="null">
                    Выберите датчик CO2
                  </option>
                  <option
                    v-for="node in co2SensorCandidates"
                    :key="node.id"
                    :value="node.id"
                  >
                    {{ nodeLabel(node) }}
                  </option>
                </select>
              </label>
              <div v-if="showBindButtons || showRefreshButtons" class="flex items-center gap-2">
                <Button
                  v-if="showBindButtons"
                  size="sm"
                  variant="secondary"
                  :disabled="!canBindSelected(assignments?.co2_sensor)"
                  @click="emit('bind-devices', ['co2_sensor'])"
                >
                  {{ bindingInProgress ? 'Привязка...' : 'Привязать' }}
                </Button>
                <Button
                  v-if="showRefreshButtons"
                  size="sm"
                  variant="ghost"
                  :disabled="!canRefreshNodes"
                  @click="emit('refresh-nodes')"
                >
                  {{ refreshingNodes ? 'Обновление...' : 'Обновить' }}
                </Button>
              </div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-[minmax(0,1fr),auto] gap-2 items-end">
              <label class="text-xs text-[color:var(--text-muted)]">
                CO2 actuator
                <select
                  v-model.number="assignments.co2_actuator"
                  class="input-select mt-1 w-full"
                  :disabled="!canConfigure"
                >
                  <option :value="null">
                    Выберите CO2 actuator
                  </option>
                  <option
                    v-for="node in co2ActuatorCandidates"
                    :key="node.id"
                    :value="node.id"
                  >
                    {{ nodeLabel(node) }}
                  </option>
                </select>
              </label>
              <div v-if="showBindButtons || showRefreshButtons" class="flex items-center gap-2">
                <Button
                  v-if="showBindButtons"
                  size="sm"
                  variant="secondary"
                  :disabled="!canBindSelected(assignments?.co2_actuator)"
                  @click="emit('bind-devices', ['co2_actuator'])"
                >
                  {{ bindingInProgress ? 'Привязка...' : 'Привязать' }}
                </Button>
                <Button
                  v-if="showRefreshButtons"
                  size="sm"
                  variant="ghost"
                  :disabled="!canRefreshNodes"
                  @click="emit('refresh-nodes')"
                >
                  {{ refreshingNodes ? 'Обновление...' : 'Обновить' }}
                </Button>
              </div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-[minmax(0,1fr),auto] gap-2 items-end">
              <label class="text-xs text-[color:var(--text-muted)]">
                Прикорневая вентиляция
                <select
                  v-model.number="assignments.root_vent_actuator"
                  class="input-select mt-1 w-full"
                  :disabled="!canConfigure"
                >
                  <option :value="null">
                    Выберите root ventilation node
                  </option>
                  <option
                    v-for="node in rootVentCandidates"
                    :key="node.id"
                    :value="node.id"
                  >
                    {{ nodeLabel(node) }}
                  </option>
                </select>
              </label>
              <div v-if="showBindButtons || showRefreshButtons" class="flex items-center gap-2">
                <Button
                  v-if="showBindButtons"
                  size="sm"
                  variant="secondary"
                  :disabled="!canBindSelected(assignments?.root_vent_actuator)"
                  @click="emit('bind-devices', ['root_vent_actuator'])"
                >
                  {{ bindingInProgress ? 'Привязка...' : 'Привязать' }}
                </Button>
                <Button
                  v-if="showRefreshButtons"
                  size="sm"
                  variant="ghost"
                  :disabled="!canRefreshNodes"
                  @click="emit('refresh-nodes')"
                >
                  {{ refreshingNodes ? 'Обновление...' : 'Обновить' }}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </details>
    </section>

    <section class="rounded-xl border border-[color:var(--border-muted)]">
      <details :open="lightingForm.enabled" class="group">
        <summary class="flex cursor-pointer list-none items-start justify-between gap-3 p-4">
          <div>
            <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
              Свет
            </h4>
            <p class="mt-1 text-xs text-[color:var(--text-dim)]">
              Опциональная система досветки с отдельной привязкой ноды и конфигурацией.
            </p>
          </div>
          <span class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
            {{ lightingForm.enabled ? 'Включено' : 'Выключено' }}
          </span>
        </summary>

        <div class="space-y-4 border-t border-[color:var(--border-muted)] p-4">
          <div class="flex items-center justify-end">
            <label class="inline-flex items-center gap-2 text-xs text-[color:var(--text-muted)]">
              <input
                v-model="lightingForm.enabled"
                type="checkbox"
                :disabled="!canConfigure"
              />
              Управлять освещением
            </label>
          </div>

          <div
            v-if="lightingForm.enabled && showNodeBindings && assignments"
            class="grid grid-cols-1 md:grid-cols-2 gap-3"
          >
            <div class="grid grid-cols-1 md:grid-cols-[minmax(0,1fr),auto] gap-2 items-end">
              <label class="text-xs text-[color:var(--text-muted)]">
                Нода света
                <select
                  v-model.number="assignments.light"
                  class="input-select mt-1 w-full"
                  :disabled="!canConfigure"
                >
                  <option :value="null">
                    Выберите ноду освещения
                  </option>
                  <option
                    v-for="node in lightCandidates"
                    :key="node.id"
                    :value="node.id"
                  >
                    {{ nodeLabel(node) }}
                  </option>
                </select>
              </label>
              <div v-if="showBindButtons || showRefreshButtons" class="flex items-center gap-2">
                <Button
                  v-if="showBindButtons"
                  size="sm"
                  variant="secondary"
                  :disabled="!canBindSelected(assignments?.light)"
                  @click="emit('bind-devices', ['light'])"
                >
                  {{ bindingInProgress ? 'Привязка...' : 'Привязать' }}
                </Button>
                <Button
                  v-if="showRefreshButtons"
                  size="sm"
                  variant="ghost"
                  :disabled="!canRefreshNodes"
                  @click="emit('refresh-nodes')"
                >
                  {{ refreshingNodes ? 'Обновление...' : 'Обновить' }}
                </Button>
              </div>
            </div>
          </div>

          <div
            v-if="lightingForm.enabled"
            class="grid grid-cols-1 md:grid-cols-3 gap-3"
          >
        <label class="text-xs text-[color:var(--text-muted)]">
          Освещённость днём (lux)
          <input
            v-model.number="lightingForm.luxDay"
            type="number"
            min="0"
            max="120000"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Освещённость ночью (lux)
          <input
            v-model.number="lightingForm.luxNight"
            type="number"
            min="0"
            max="120000"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
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
            :disabled="!canConfigure"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Интервал досветки (мин)
          <input
            v-model.number="lightingForm.intervalMinutes"
            type="number"
            min="1"
            max="1440"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Начало
          <input
            v-model="lightingForm.scheduleStart"
            type="time"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Конец
          <input
            v-model="lightingForm.scheduleEnd"
            type="time"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Интенсивность ручного режима (%)
          <input
            v-model.number="lightingForm.manualIntensity"
            type="number"
            min="0"
            max="100"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Ручной режим (ч)
          <input
            v-model.number="lightingForm.manualDurationHours"
            type="number"
            min="0.5"
            max="24"
            step="0.5"
            class="input-field mt-1 w-full"
            :disabled="!canConfigure"
          />
        </label>
          </div>
        </div>
      </details>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Button from '@/Components/Button.vue'
import ZoneCorrectionCalibrationStack from '@/Components/ZoneCorrectionCalibrationStack.vue'
import type { Node as SetupWizardNode } from '@/types/SetupWizard'
import type { SensorCalibrationSettings } from '@/types/SystemSettings'
import type { LightingFormState, WaterFormState } from '@/composables/zoneAutomationTypes'

export interface ZoneAutomationSectionAssignments {
  irrigation: number | null
  ph_correction: number | null
  ec_correction: number | null
  light: number | null
  co2_sensor: number | null
  co2_actuator: number | null
  root_vent_actuator: number | null
}

export type ZoneAutomationBindRole =
  | 'irrigation'
  | 'ph_correction'
  | 'ec_correction'
  | 'light'
  | 'co2_sensor'
  | 'co2_actuator'
  | 'root_vent_actuator'

export interface ZoneClimateFormState {
  enabled: boolean
}

const props = withDefaults(defineProps<{
  waterForm: WaterFormState
  lightingForm: LightingFormState
  zoneClimateForm: ZoneClimateFormState
  canConfigure?: boolean
  isSystemTypeLocked?: boolean
  showNodeBindings?: boolean
  showBindButtons?: boolean
  showRefreshButtons?: boolean
  bindDisabled?: boolean
  bindingInProgress?: boolean
  refreshDisabled?: boolean
  refreshingNodes?: boolean
  availableNodes?: SetupWizardNode[]
  assignments?: ZoneAutomationSectionAssignments | null
  showCorrectionCalibrationStack?: boolean
  zoneId?: number | null
  sensorCalibrationSettings?: SensorCalibrationSettings | null
}>(), {
  canConfigure: true,
  isSystemTypeLocked: false,
  showNodeBindings: false,
  showBindButtons: false,
  showRefreshButtons: false,
  bindDisabled: false,
  bindingInProgress: false,
  refreshDisabled: false,
  refreshingNodes: false,
  availableNodes: () => [],
  assignments: null,
  showCorrectionCalibrationStack: false,
  zoneId: null,
  sensorCalibrationSettings: null,
})

const emit = defineEmits<{
  (e: 'bind-devices', roles: ZoneAutomationBindRole[]): void
  (e: 'refresh-nodes'): void
}>()

function canBindSelected(value: number | null | undefined): boolean {
  return (
    Boolean(props.canConfigure)
    && !props.bindDisabled
    && !props.bindingInProgress
    && typeof value === 'number'
    && Number.isInteger(value)
    && value > 0
  )
}

const canRefreshNodes = computed(() => {
  return Boolean(props.canConfigure) && !props.refreshDisabled && !props.bindingInProgress
})

function nodeLabel(node: SetupWizardNode): string {
  return node.name || node.uid || `Node #${node.id}`
}

function nodeChannels(node: SetupWizardNode): string[] {
  return Array.isArray(node.channels)
    ? node.channels
      .map((channel) => String(channel.channel ?? '').toLowerCase())
      .filter((channel) => channel.length > 0)
    : []
}

function matchesAnyChannel(node: SetupWizardNode, candidates: string[]): boolean {
  const channels = new Set(nodeChannels(node))
  return candidates.some((candidate) => channels.has(candidate))
}

const irrigationCandidates = computed(() => {
  return props.availableNodes.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'irrig' || matchesAnyChannel(node, [
      'pump_main',
      'main_pump',
      'pump_irrigation',
      'valve_irrigation',
      'pump_in',
    ])
  })
})

const phCandidates = computed(() => {
  return props.availableNodes.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'ph' || matchesAnyChannel(node, ['ph_sensor', 'pump_acid', 'pump_base'])
  })
})

const ecCandidates = computed(() => {
  return props.availableNodes.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'ec' || matchesAnyChannel(node, ['ec_sensor', 'pump_a', 'pump_b', 'pump_c', 'pump_d'])
  })
})

const lightCandidates = computed(() => {
  return props.availableNodes.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'light' || matchesAnyChannel(node, ['light', 'light_main', 'white_light', 'uv_light'])
  })
})

const co2SensorCandidates = computed(() => {
  return props.availableNodes.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'climate' || matchesAnyChannel(node, ['co2_ppm'])
  })
})

const co2ActuatorCandidates = computed(() => {
  return props.availableNodes.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'climate' || matchesAnyChannel(node, ['co2_inject'])
  })
})

const rootVentCandidates = computed(() => {
  return props.availableNodes.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'climate' || matchesAnyChannel(node, ['root_vent', 'fan_root'])
  })
})
</script>
