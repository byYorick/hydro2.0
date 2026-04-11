<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center gap-2">
      <button
        v-for="item in automationTabs"
        :key="item.id"
        type="button"
        class="btn btn-outline h-9 px-3 text-xs"
        :class="item.id === activeTab ? 'border-[color:var(--accent-green)] text-[color:var(--text-primary)]' : ''"
        @click="activeTab = item.id"
      >
        {{ item.label }}
      </button>
    </div>

    <section
      v-if="activeTab === 1"
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
        Интервал климата (мин)
        <input
          v-model.number="climateForm.intervalMinutes"
          type="number"
          min="1"
          max="1440"
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
      v-else-if="activeTab === 2"
      class="space-y-3"
    >
      <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-4 space-y-4">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div class="text-sm font-semibold">
              Основной цикл полива, окна приготовления и рабочие объёмы контура
            </div>
            <div class="mt-1 text-xs text-[color:var(--text-muted)]">
              {{ irrigationStrategyDescription }}
            </div>
          </div>
          <div class="rounded-full border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] px-3 py-1 text-xs text-[color:var(--text-primary)]">
            {{ irrigationStrategyLabel }}
          </div>
        </div>

        <div class="grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,2fr)_minmax(260px,1fr)]">
          <div class="text-xs text-[color:var(--text-muted)]">
            <div>Режим полива</div>
            <div class="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
              <button
                type="button"
                data-testid="growth-wizard-irrigation-mode-task"
                class="rounded-lg border px-3 py-2 text-left transition-colors"
                :class="isTimedIrrigation
                  ? 'border-[color:var(--accent-green)] bg-[color:var(--badge-success-bg)] text-[color:var(--text-primary)]'
                  : 'border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] text-[color:var(--text-muted)]'"
                @click="waterForm.irrigationDecisionStrategy = 'task'"
              >
                <div class="text-sm font-semibold">
                  По времени
                </div>
                <div class="mt-1 text-xs">
                  Запуск по расписанию без оценки влажности субстрата.
                </div>
              </button>
              <button
                type="button"
                data-testid="growth-wizard-irrigation-mode-smart"
                class="rounded-lg border px-3 py-2 text-left transition-colors"
                :class="isSmartIrrigation
                  ? 'border-[color:var(--accent-green)] bg-[color:var(--badge-success-bg)] text-[color:var(--text-primary)]'
                  : 'border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] text-[color:var(--text-muted)]'"
                @click="waterForm.irrigationDecisionStrategy = 'smart_soil_v1'"
              >
                <div class="text-sm font-semibold">
                  Умный полив
                </div>
                <div class="mt-1 text-xs">
                  Перед стартом анализирует `SOIL_MOISTURE` и качество телеметрии.
                </div>
              </button>
            </div>
          </div>

          <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3">
            <div class="text-xs text-[color:var(--text-dim)]">
              Цели из рецепта
            </div>
            <div class="mt-1 text-sm font-medium text-[color:var(--text-primary)]">
              pH {{ waterForm.targetPh }}, EC {{ waterForm.targetEc }}
            </div>
            <div class="mt-1 text-xs text-[color:var(--text-muted)]">
              {{ irrigationRecipeSummary }}
            </div>
          </div>
        </div>

        <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 space-y-3">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div class="text-xs text-[color:var(--text-dim)]">
                Параметры цикла и контура
              </div>
              <div class="mt-1 text-xs text-[color:var(--text-muted)]">
                Интервал и длительность доходят в `automation profile` как `subsystems.irrigation.execution`, а объёмы и окна приготовления сохраняются в runtime-конфиге контура.
              </div>
            </div>
            <div class="rounded-full border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-3 py-1 text-xs text-[color:var(--text-muted)]">
              {{ irrigationScheduleSummary }}
            </div>
          </div>

          <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            <label class="text-xs text-[color:var(--text-muted)]">
              Тип системы
              <select
                v-model="waterForm.systemType"
                class="input-select mt-1 w-full"
              >
                <option value="drip">drip</option>
                <option value="substrate_trays">substrate_trays</option>
                <option value="nft">nft</option>
              </select>
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
              Длительность полива (сек)
              <input
                v-model.number="waterForm.durationSeconds"
                type="number"
                min="1"
                max="3600"
                class="input-field mt-1 w-full"
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
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Температура набора (°C)
              <input
                v-model.number="waterForm.fillTemperatureC"
                type="number"
                min="5"
                max="35"
                step="0.1"
                class="input-field mt-1 w-full"
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
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Окно набора воды: от
              <input
                v-model="waterForm.fillWindowStart"
                type="time"
                class="input-field mt-1 w-full"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Окно набора воды: до
              <input
                v-model="waterForm.fillWindowEnd"
                type="time"
                class="input-field mt-1 w-full"
              />
            </label>
          </div>
        </div>

        <div
          v-if="isTimedIrrigation"
          class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3"
        >
          <div class="text-xs font-semibold text-[color:var(--text-primary)]">
            Настройки полива по времени
          </div>
          <div class="mt-1 text-xs text-[color:var(--text-muted)]">
            Для режима `task` используется только основной цикл полива: интервал, длительность, рабочие объёмы и окно набора воды.
          </div>
        </div>

        <div
          v-else
          class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 space-y-4"
        >
          <div>
            <div class="text-xs font-semibold text-[color:var(--text-primary)]">
              Умный полив (decision, recovery, safety)
            </div>
            <div class="mt-1 text-xs text-[color:var(--text-muted)]">
              В режиме `smart_soil_v1` к основному циклу добавляются decision-параметры, recovery-повторы и safety-ограничения.
            </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-3 items-end">
            <label class="text-xs text-[color:var(--text-muted)]">
              Датчик влажности субстрата (канал)
              <select
                v-model.number="soilMoistureChannelId"
                class="input-select mt-1 w-full"
                data-testid="growth-wizard-soil-moisture-channel"
              >
                <option :value="null">
                  — выберите канал `soil_moisture` —
                </option>
                <option
                  v-for="item in soilMoistureChannelCandidates"
                  :key="item.id"
                  :value="item.id"
                >
                  {{ item.label }}
                </option>
              </select>
            </label>

            <Button
              size="sm"
              :disabled="soilMoistureBindingLoading || !soilMoistureChannelId"
              @click="emit('save-soil-moisture-binding')"
            >
              {{ soilMoistureBindingLoading ? 'Сохранение...' : 'Сохранить привязку' }}
            </Button>
          </div>

          <div
            v-if="soilMoistureBoundNodeChannelId"
            class="text-xs text-[color:var(--text-muted)]"
          >
            Текущая привязка (node_channel_id): <span class="font-mono">{{ soilMoistureBoundNodeChannelId }}</span>
            <span v-if="soilMoistureBindingSavedAt"> · сохранено: {{ formatDateTime(soilMoistureBindingSavedAt) }}</span>
          </div>
          <div
            v-else
            class="text-xs text-[color:var(--badge-warning-text)]"
          >
            Привязка датчика влажности ещё не задана — умный полив не сможет корректно оценивать `SOIL_MOISTURE`.
          </div>

          <div class="grid grid-cols-1 gap-4 xl:grid-cols-3">
            <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3">
              <div class="text-xs font-semibold text-[color:var(--text-primary)]">
                Decision
              </div>
              <div class="mt-3 grid grid-cols-1 gap-3">
                <label class="text-xs text-[color:var(--text-muted)]">
                  Lookback (сек)
                  <input
                    v-model.number="waterForm.irrigationDecisionLookbackSeconds"
                    type="number"
                    min="60"
                    max="86400"
                    class="input-field mt-1 w-full"
                  />
                </label>
                <label class="text-xs text-[color:var(--text-muted)]">
                  Min samples
                  <input
                    v-model.number="waterForm.irrigationDecisionMinSamples"
                    type="number"
                    min="1"
                    max="100"
                    class="input-field mt-1 w-full"
                  />
                </label>
                <label class="text-xs text-[color:var(--text-muted)]">
                  Stale after (сек)
                  <input
                    v-model.number="waterForm.irrigationDecisionStaleAfterSeconds"
                    type="number"
                    min="30"
                    max="86400"
                    class="input-field mt-1 w-full"
                  />
                </label>
                <label class="text-xs text-[color:var(--text-muted)]">
                  Hysteresis (%)
                  <input
                    v-model.number="waterForm.irrigationDecisionHysteresisPct"
                    type="number"
                    min="0"
                    max="100"
                    step="0.1"
                    class="input-field mt-1 w-full"
                  />
                </label>
                <label class="text-xs text-[color:var(--text-muted)]">
                  Spread alert (%)
                  <input
                    v-model.number="waterForm.irrigationDecisionSpreadAlertThresholdPct"
                    type="number"
                    min="0"
                    max="100"
                    step="0.1"
                    class="input-field mt-1 w-full"
                  />
                </label>
              </div>
            </div>

            <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3">
              <div class="text-xs font-semibold text-[color:var(--text-primary)]">
                Recovery
              </div>
              <div class="mt-3 grid grid-cols-1 gap-3">
                <label class="text-xs text-[color:var(--text-muted)]">
                  Автоповтор после setup
                  <select
                    v-model="waterForm.irrigationAutoReplayAfterSetup"
                    class="input-select mt-1 w-full"
                  >
                    <option :value="true">Да</option>
                    <option :value="false">Нет</option>
                  </select>
                </label>
                <label class="text-xs text-[color:var(--text-muted)]">
                  Максимум setup-replay
                  <input
                    v-model.number="waterForm.irrigationMaxSetupReplays"
                    type="number"
                    min="0"
                    max="10"
                    class="input-field mt-1 w-full"
                  />
                </label>
              </div>
            </div>

            <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3">
              <div class="text-xs font-semibold text-[color:var(--text-primary)]">
                Safety
              </div>
              <div class="mt-3 grid grid-cols-1 gap-3">
                <label class="text-xs text-[color:var(--text-muted)]">
                  Стоп по solution_min
                  <select
                    v-model="waterForm.stopOnSolutionMin"
                    class="input-select mt-1 w-full"
                  >
                    <option :value="true">Да</option>
                    <option :value="false">Нет</option>
                  </select>
                </label>
              </div>
            </div>
          </div>

          <div
            v-if="soilMoistureBindingError"
            class="text-xs text-red-500"
          >
            {{ soilMoistureBindingError }}
          </div>
        </div>
      </div>

      <details class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-4">
        <summary class="cursor-pointer list-none">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div class="text-sm font-semibold">
                Расширенные runtime-настройки
              </div>
              <div class="mt-1 text-xs text-[color:var(--text-muted)]">
                Диагностика, refill, смена раствора и low-level таймауты.
              </div>
            </div>
            <div class="text-xs text-[color:var(--text-dim)]">
              {{ waterAdvancedSummary }}
            </div>
          </div>
        </summary>

        <div class="mt-4 space-y-4">
          <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3">
            <div class="text-xs font-semibold text-[color:var(--text-primary)]">
              Контур и диагностика
            </div>
            <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
              <label class="text-xs text-[color:var(--text-muted)]">
                Баков
                <input
                  v-model.number="waterForm.tanksCount"
                  type="number"
                  min="2"
                  max="3"
                  class="input-field mt-1 w-full"
                  :disabled="waterForm.systemType === 'drip'"
                />
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
                />
              </label>
            </div>
          </div>

          <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3">
            <div class="text-xs font-semibold text-[color:var(--text-primary)]">
              {{ isTimedIrrigation ? 'Runtime временного полива' : 'Runtime умного полива' }}
            </div>
            <div class="mt-1 text-xs text-[color:var(--text-muted)]">
              {{ isTimedIrrigation ? 'Поля ниже управляют регулярным timed-cycle и связанными runtime-проверками.' : 'Поля ниже управляют decision-controller и runtime-повтором умного полива.' }}
            </div>
            <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
              <label class="text-xs text-[color:var(--text-muted)]">
                Диагностика
                <select
                  v-model="waterForm.diagnosticsEnabled"
                  class="input-select mt-1 w-full"
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
                />
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Workflow запуска
                <select
                  v-model="waterForm.diagnosticsWorkflow"
                  class="input-select mt-1 w-full"
                >
                  <option value="startup">startup</option>
                  <option
                    value="cycle_start"
                    :disabled="tanksCount === 2"
                  >
                    cycle_start
                  </option>
                  <option value="diagnostics">diagnostics</option>
                </select>
              </label>
            </div>
          </div>

          <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3">
            <div class="text-xs font-semibold text-[color:var(--text-primary)]">
              Refill и смена раствора
            </div>
            <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
              <label class="text-xs text-[color:var(--text-muted)]">
                Refill длительность (сек)
                <input
                  v-model.number="waterForm.refillDurationSeconds"
                  type="number"
                  min="1"
                  max="3600"
                  class="input-field mt-1 w-full"
                />
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Refill timeout (сек)
                <input
                  v-model.number="waterForm.refillTimeoutSeconds"
                  type="number"
                  min="30"
                  max="86400"
                  class="input-field mt-1 w-full"
                />
              </label>
              <label class="text-xs text-[color:var(--text-muted)] md:col-span-2">
                Refill обязательные типы нод (CSV)
                <input
                  v-model="waterForm.refillRequiredNodeTypes"
                  type="text"
                  class="input-field mt-1 w-full"
                  placeholder="irrig,climate,light"
                />
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Refill канал
                <input
                  v-model="waterForm.refillPreferredChannel"
                  type="text"
                  class="input-field mt-1 w-full"
                  placeholder="fill_valve"
                />
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Смена раствора
                <select
                  v-model="waterForm.solutionChangeEnabled"
                  class="input-select mt-1 w-full"
                >
                  <option :value="true">Включена</option>
                  <option :value="false">Выключена</option>
                </select>
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Интервал смены (мин)
                <input
                  v-model.number="waterForm.solutionChangeIntervalMinutes"
                  type="number"
                  min="1"
                  max="1440"
                  class="input-field mt-1 w-full"
                />
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Длительность смены (сек)
                <input
                  v-model.number="waterForm.solutionChangeDurationSeconds"
                  type="number"
                  min="1"
                  max="86400"
                  class="input-field mt-1 w-full"
                />
              </label>
            </div>
          </div>
        </div>
      </details>
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
        Интервал досветки (мин)
        <input
          v-model.number="lightingForm.intervalMinutes"
          type="number"
          min="1"
          max="1440"
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
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Button from '@/Components/Button.vue'
import type {
  ClimateFormState,
  LightingFormState,
  WaterFormState,
} from '@/composables/zoneAutomationTypes'

interface SoilMoistureChannelOption {
  id: number
  label: string
}

defineProps<{
  soilMoistureChannelCandidates: SoilMoistureChannelOption[]
  soilMoistureBindingLoading: boolean
  soilMoistureBindingError: string | null
  soilMoistureBindingSavedAt: string | null
  soilMoistureBoundNodeChannelId: number | null
  tanksCount: number
  formatDateTime: (value: string | null | undefined) => string
}>()

const emit = defineEmits<{
  'save-soil-moisture-binding': []
}>()

const climateForm = defineModel<ClimateFormState>('climateForm', { required: true })
const waterForm = defineModel<WaterFormState>('waterForm', { required: true })
const lightingForm = defineModel<LightingFormState>('lightingForm', { required: true })
const soilMoistureChannelId = defineModel<number | null>('soilMoistureChannelId', { required: true })
const activeTab = defineModel<1 | 2 | 3>('activeTab', { default: 1 })

const automationTabs = [
  { id: 1 as const, label: 'Климат' },
  { id: 2 as const, label: 'Водный узел' },
  { id: 3 as const, label: 'Досветка' },
]

const isTimedIrrigation = computed(() => waterForm.value.irrigationDecisionStrategy !== 'smart_soil_v1')
const isSmartIrrigation = computed(() => waterForm.value.irrigationDecisionStrategy === 'smart_soil_v1')

const irrigationStrategyLabel = computed(() =>
  isSmartIrrigation.value ? 'Умный полив по SOIL_MOISTURE' : 'Полив по расписанию'
)

const irrigationStrategyDescription = computed(() =>
  isSmartIrrigation.value
    ? 'Перед стартом оценивается влажность субстрата и качество телеметрии; без привязки датчика стратегия не сработает корректно.'
    : 'Полив стартует по временным окнам цикла без предварительной оценки влажности субстрата.'
)

const irrigationRecipeSummary = computed(() =>
  `Рецепт задаёт базовые launch-targets: pH ${waterForm.value.targetPh}, EC ${waterForm.value.targetEc}.`
)

const irrigationScheduleSummary = computed(() =>
  `Стартовая схема полива: каждые ${waterForm.value.intervalMinutes} мин на ${waterForm.value.durationSeconds} сек.`
)

const waterAdvancedSummary = computed(() => {
  const diagnosticsState = waterForm.value.diagnosticsEnabled ? 'диагностика включена' : 'диагностика выключена'
  const refillState = `${waterForm.value.refillDurationSeconds}с / timeout ${waterForm.value.refillTimeoutSeconds}с`
  const solutionChangeState = waterForm.value.solutionChangeEnabled
    ? `смена раствора каждые ${waterForm.value.solutionChangeIntervalMinutes} мин`
    : 'смена раствора отключена'

  return `${diagnosticsState}, refill ${refillState}, ${solutionChangeState}.`
})
</script>
