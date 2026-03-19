<template>
  <div class="space-y-4">
    <section class="rounded-xl border border-[color:var(--border-muted)]">
      <details open class="group">
        <summary class="flex cursor-pointer list-none items-start justify-between gap-3 p-4">
          <div>
            <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
              Обязательные устройства
            </h4>
            <p class="mt-1 text-xs text-[color:var(--text-dim)]">
              Базовые ноды, без которых зона не сможет работать: полив, pH и EC.
            </p>
          </div>
          <span class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
            Обязательно
          </span>
        </summary>

        <div class="space-y-4 border-t border-[color:var(--border-muted)] p-4">
          <div
            v-if="showNodeBindings && assignments"
            class="grid grid-cols-1 gap-3 xl:grid-cols-3"
          >
            <div class="grid grid-cols-1 gap-2 items-end">
              <label class="text-xs text-[color:var(--text-muted)]">
                Узел полива
                <select
                  v-model.number="assignments.irrigation"
                  class="input-select mt-1 w-full"
                  :disabled="!canConfigure"
                >
                  <option :value="null">
                    Выберите узел полива
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
              <div
                v-if="showBindButtons || showRefreshButtons"
                class="flex items-center gap-2"
              >
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

            <div class="grid grid-cols-1 gap-2 items-end">
              <label class="text-xs text-[color:var(--text-muted)]">
                Узел коррекции pH
                <select
                  v-model.number="assignments.ph_correction"
                  class="input-select mt-1 w-full"
                  :disabled="!canConfigure"
                >
                  <option :value="null">
                    Выберите узел pH
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
              <div
                v-if="showBindButtons || showRefreshButtons"
                class="flex items-center gap-2"
              >
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

            <div class="grid grid-cols-1 gap-2 items-end">
              <label class="text-xs text-[color:var(--text-muted)]">
                Узел коррекции EC
                <select
                  v-model.number="assignments.ec_correction"
                  class="input-select mt-1 w-full"
                  :disabled="!canConfigure"
                >
                  <option :value="null">
                    Выберите узел EC
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
              <div
                v-if="showBindButtons || showRefreshButtons"
                class="flex items-center gap-2"
              >
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

          <div class="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)]">
            <span>
              {{ requiredDevicesSelectedCount }}/3 обязательных устройства выбрано.
            </span>
            <div
              v-if="showSectionSaveButtons"
              class="flex items-center gap-3"
            >
              <span>Сохраняет устройства и привязки этой секции.</span>
              <Button
                size="sm"
                :disabled="!canSaveRequiredDevices"
                data-test="save-section-required-devices"
                @click="emit('save-section', 'required_devices')"
              >
                {{ savingSection === 'required_devices' ? 'Сохранение...' : 'Сохранить секцию' }}
              </Button>
            </div>
          </div>
        </div>
      </details>
    </section>

    <section class="rounded-xl border border-[color:var(--border-muted)]">
      <details open class="group">
        <summary class="flex cursor-pointer list-none items-start justify-between gap-3 p-4">
          <div>
            <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
              Водный контур
            </h4>
            <p class="mt-1 text-xs text-[color:var(--text-dim)]">
              Тип системы, баковая схема и базовая гидравлическая конфигурация.
            </p>
          </div>
          <span class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
            Базовая схема
          </span>
        </summary>

        <div class="space-y-4 border-t border-[color:var(--border-muted)] p-4">
          <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
            <label class="text-xs text-[color:var(--text-muted)]">
              Тип системы
              <select
                v-model="waterForm.systemType"
                class="input-select mt-1 w-full"
                :disabled="!canConfigure || isSystemTypeLocked"
              >
                <option value="drip">drip</option>
                <option value="substrate_trays">substrate_trays</option>
                <option disabled value="nft">nft (скоро)</option>
              </select>
            </label>

            <label class="text-xs text-[color:var(--text-muted)]">
              Количество баков
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
              Цель по дренажу (%)
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

          <div
            v-if="waterForm.systemType === 'nft'"
            class="rounded-xl border border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] p-3 text-xs text-[color:var(--badge-warning-text)]"
          >
            NFT пока не включен в основной сценарий мастера. Для агронома доступны drip и substrate_trays.
          </div>

          <details class="rounded-xl border border-[color:var(--border-muted)] p-3">
            <summary class="cursor-pointer text-sm font-semibold text-[color:var(--text-primary)]">
              Расширенные настройки
            </summary>

            <div class="mt-3 space-y-4">
              <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
                <label class="text-xs text-[color:var(--text-muted)]">
                  Переключение клапанов
                  <select
                    v-model="waterForm.valveSwitching"
                    class="input-select mt-1 w-full"
                    :disabled="!canConfigure"
                  >
                    <option :value="true">Включено</option>
                    <option :value="false">Выключено</option>
                  </select>
                </label>
              </div>

              <div
                v-if="waterForm.tanksCount === 2"
                class="rounded-xl border border-[color:var(--border-muted)] p-3"
              >
                <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">
                  Relay-шаги 2-баковой схемы
                </h5>
                <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
                  <label class="text-xs text-[color:var(--text-muted)]">
                    Clean fill start steps
                    <input
                      v-model.number="waterForm.twoTankCleanFillStartSteps"
                      type="number"
                      min="1"
                      max="12"
                      class="input-field mt-1 w-full"
                      :disabled="!canConfigure"
                    />
                  </label>
                  <label class="text-xs text-[color:var(--text-muted)]">
                    Clean fill stop steps
                    <input
                      v-model.number="waterForm.twoTankCleanFillStopSteps"
                      type="number"
                      min="1"
                      max="12"
                      class="input-field mt-1 w-full"
                      :disabled="!canConfigure"
                    />
                  </label>
                  <label class="text-xs text-[color:var(--text-muted)]">
                    Solution fill start steps
                    <input
                      v-model.number="waterForm.twoTankSolutionFillStartSteps"
                      type="number"
                      min="1"
                      max="12"
                      class="input-field mt-1 w-full"
                      :disabled="!canConfigure"
                    />
                  </label>
                  <label class="text-xs text-[color:var(--text-muted)]">
                    Solution fill stop steps
                    <input
                      v-model.number="waterForm.twoTankSolutionFillStopSteps"
                      type="number"
                      min="1"
                      max="12"
                      class="input-field mt-1 w-full"
                      :disabled="!canConfigure"
                    />
                  </label>
                  <label class="text-xs text-[color:var(--text-muted)]">
                    Prepare recirculation start
                    <input
                      v-model.number="waterForm.twoTankPrepareRecirculationStartSteps"
                      type="number"
                      min="1"
                      max="12"
                      class="input-field mt-1 w-full"
                      :disabled="!canConfigure"
                    />
                  </label>
                  <label class="text-xs text-[color:var(--text-muted)]">
                    Prepare recirculation stop
                    <input
                      v-model.number="waterForm.twoTankPrepareRecirculationStopSteps"
                      type="number"
                      min="1"
                      max="12"
                      class="input-field mt-1 w-full"
                      :disabled="!canConfigure"
                    />
                  </label>
                  <label class="text-xs text-[color:var(--text-muted)]">
                    Irrigation recovery start
                    <input
                      v-model.number="waterForm.twoTankIrrigationRecoveryStartSteps"
                      type="number"
                      min="1"
                      max="12"
                      class="input-field mt-1 w-full"
                      :disabled="!canConfigure"
                    />
                  </label>
                  <label class="text-xs text-[color:var(--text-muted)]">
                    Irrigation recovery stop
                    <input
                      v-model.number="waterForm.twoTankIrrigationRecoveryStopSteps"
                      type="number"
                      min="1"
                      max="12"
                      class="input-field mt-1 w-full"
                      :disabled="!canConfigure"
                    />
                  </label>
                </div>
              </div>
            </div>
          </details>

          <div
            v-if="showSectionSaveButtons"
            class="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)]"
          >
            <span>Сохраняет изменения этой секции в общем профиле зоны.</span>
            <Button
              size="sm"
              :disabled="!canSaveContourSection"
              data-test="save-section-water-contour"
              @click="emit('save-section', 'water_contour')"
            >
              {{ savingSection === 'water_contour' ? 'Сохранение...' : 'Сохранить секцию' }}
            </Button>
          </div>
        </div>
      </details>
    </section>

    <section class="rounded-xl border border-[color:var(--border-muted)]">
      <details open class="group">
        <summary class="flex cursor-pointer list-none items-start justify-between gap-3 p-4">
          <div>
            <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
              Полив
            </h4>
            <p class="mt-1 text-xs text-[color:var(--text-dim)]">
              Рабочий цикл полива, объёмы и эксплуатационные параметры водного узла.
            </p>
          </div>
          <span class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
            Основной цикл
          </span>
        </summary>

        <div class="space-y-4 border-t border-[color:var(--border-muted)] p-4">
          <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
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
              Окно набора воды: от
              <input
                v-model="waterForm.fillWindowStart"
                type="time"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Окно набора воды: до
              <input
                v-model="waterForm.fillWindowEnd"
                type="time"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure"
              />
            </label>
          </div>

          <details class="rounded-xl border border-[color:var(--border-muted)] p-3">
            <summary class="cursor-pointer text-sm font-semibold text-[color:var(--text-primary)]">
              Расширенные настройки
            </summary>

            <div class="mt-3 space-y-4">
              <div class="rounded-xl border border-[color:var(--border-muted)] p-3">
                <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">
                  Диагностика и refill
                </h5>
                <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
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
                      <option
                        value="cycle_start"
                        :disabled="waterForm.tanksCount === 2"
                      >
                        cycle_start
                      </option>
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
                  <label class="text-xs text-[color:var(--text-muted)] md:col-span-2">
                    Обязательные типы нод для refill
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

              <div class="rounded-xl border border-[color:var(--border-muted)] p-3">
                <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">
                  Startup и recovery
                </h5>
                <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
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
                    Таймаут подготовки рециркуляции
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
                    Повторы clean fill
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
                    Лимит recovery-continue
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
                </div>
              </div>

              <div class="rounded-xl border border-[color:var(--border-muted)] p-3">
                <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">
                  Плановая смена раствора
                </h5>
                <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
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
                    Интервал смены (мин)
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
                    Длительность смены (сек)
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

          <div
            v-if="showSectionSaveButtons"
            class="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)]"
          >
            <span>Сохраняет изменения этой секции в общем профиле зоны.</span>
            <Button
              size="sm"
              :disabled="!canSaveIrrigationSection"
              data-test="save-section-irrigation"
              @click="emit('save-section', 'irrigation')"
            >
              {{ savingSection === 'irrigation' ? 'Сохранение...' : 'Сохранить секцию' }}
            </Button>
          </div>
        </div>
      </details>
    </section>

    <section class="rounded-xl border border-[color:var(--border-muted)]">
      <details open class="group">
        <summary class="flex cursor-pointer list-none items-start justify-between gap-3 p-4">
          <div>
            <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
              Раствор и коррекция
            </h4>
            <p class="mt-1 text-xs text-[color:var(--text-dim)]">
              Целевые параметры раствора и правила, по которым зона их удерживает.
            </p>
          </div>
          <span class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
            Отдельный блок
          </span>
        </summary>

        <div class="space-y-4 border-t border-[color:var(--border-muted)] p-4">
          <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
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
          </div>

          <details class="rounded-xl border border-[color:var(--border-muted)] p-3">
            <summary class="cursor-pointer text-sm font-semibold text-[color:var(--text-primary)]">
              Расширенные настройки
            </summary>

            <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
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
                Stabilization (sec)
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
          </details>

          <div
            v-if="showCorrectionCalibrationStack && zoneId && sensorCalibrationSettings"
            class="border-t border-[color:var(--border-muted)] pt-4"
          >
            <ZoneCorrectionCalibrationStack
              :zone-id="zoneId"
              :sensor-calibration-settings="sensorCalibrationSettings"
            />
          </div>

          <div
            v-if="showSectionSaveButtons"
            class="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)]"
          >
            <span>Сохраняет изменения этой секции в общем профиле зоны.</span>
            <Button
              size="sm"
              :disabled="!canSaveCorrectionSection"
              data-test="save-section-solution-correction"
              @click="emit('save-section', 'solution_correction')"
            >
              {{ savingSection === 'solution_correction' ? 'Сохранение...' : 'Сохранить секцию' }}
            </Button>
          </div>
        </div>
      </details>
    </section>

    <section class="rounded-xl border border-[color:var(--border-muted)]">
      <details :open="lightingForm.enabled" class="group">
        <summary class="flex cursor-pointer list-none items-start justify-between gap-3 p-4">
          <div>
            <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
              Освещение
            </h4>
            <p class="mt-1 text-xs text-[color:var(--text-dim)]">
              Опциональная подсистема досветки для этой зоны.
            </p>
          </div>
          <span class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
            Опционально
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
            class="grid grid-cols-1 gap-3 xl:grid-cols-2"
          >
            <div class="grid grid-cols-1 gap-2 items-end">
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
              <div
                v-if="showBindButtons || showRefreshButtons"
                class="flex items-center gap-2"
              >
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
            class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4"
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
          </div>

          <details
            v-if="lightingForm.enabled"
            class="rounded-xl border border-[color:var(--border-muted)] p-3"
          >
            <summary class="cursor-pointer text-sm font-semibold text-[color:var(--text-primary)]">
              Расширенные настройки
            </summary>

            <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
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
          </details>

          <div
            v-if="showSectionSaveButtons"
            class="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)]"
          >
            <span>Сохраняет изменения этой секции в общем профиле зоны.</span>
            <Button
              size="sm"
              :disabled="!canSaveLightingSection"
              data-test="save-section-lighting"
              @click="emit('save-section', 'lighting')"
            >
              {{ savingSection === 'lighting' ? 'Сохранение...' : 'Сохранить секцию' }}
            </Button>
          </div>
        </div>
      </details>
    </section>

    <section class="rounded-xl border border-[color:var(--border-muted)]">
      <details :open="zoneClimateForm.enabled" class="group">
        <summary class="flex cursor-pointer list-none items-start justify-between gap-3 p-4">
          <div>
            <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
              Климат зоны
            </h4>
            <p class="mt-1 text-xs text-[color:var(--text-dim)]">
              Отдельная зональная подсистема для CO2 и прикорневой вентиляции.
            </p>
          </div>
          <span class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
            Опционально
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
            class="grid grid-cols-1 gap-3 xl:grid-cols-3"
          >
            <div class="grid grid-cols-1 gap-2 items-end">
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
              <div
                v-if="showBindButtons || showRefreshButtons"
                class="flex items-center gap-2"
              >
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

            <div class="grid grid-cols-1 gap-2 items-end">
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
              <div
                v-if="showBindButtons || showRefreshButtons"
                class="flex items-center gap-2"
              >
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

            <div class="grid grid-cols-1 gap-2 items-end">
              <label class="text-xs text-[color:var(--text-muted)]">
                Прикорневая вентиляция
                <select
                  v-model.number="assignments.root_vent_actuator"
                  class="input-select mt-1 w-full"
                  :disabled="!canConfigure"
                >
                  <option :value="null">
                    Выберите ноду прикорневой вентиляции
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
              <div
                v-if="showBindButtons || showRefreshButtons"
                class="flex items-center gap-2"
              >
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

          <div
            v-if="showSectionSaveButtons"
            class="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)]"
          >
            <span>Сохраняет изменения этой секции в общем профиле зоны.</span>
            <Button
              size="sm"
              :disabled="!canSaveZoneClimateSection"
              data-test="save-section-zone-climate"
              @click="emit('save-section', 'zone_climate')"
            >
              {{ savingSection === 'zone_climate' ? 'Сохранение...' : 'Сохранить секцию' }}
            </Button>
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

export type ZoneAutomationSectionSaveKey =
  | 'required_devices'
  | 'water_contour'
  | 'irrigation'
  | 'solution_correction'
  | 'lighting'
  | 'zone_climate'

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
  showSectionSaveButtons?: boolean
  saveDisabled?: boolean
  savingSection?: ZoneAutomationSectionSaveKey | null
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
  showSectionSaveButtons: false,
  saveDisabled: false,
  savingSection: null,
})

const emit = defineEmits<{
  (e: 'bind-devices', roles: ZoneAutomationBindRole[]): void
  (e: 'refresh-nodes'): void
  (e: 'save-section', section: ZoneAutomationSectionSaveKey): void
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

const requiredDevicesSelectedCount = computed(() => {
  if (!props.assignments) {
    return 0
  }

  return [
    props.assignments.irrigation,
    props.assignments.ph_correction,
    props.assignments.ec_correction,
  ].filter((value): value is number => typeof value === 'number' && value > 0).length
})

const hasLightingBinding = computed(() => {
  if (!props.lightingForm.enabled) {
    return true
  }

  return typeof props.assignments?.light === 'number' && props.assignments.light > 0
})

const hasZoneClimateBinding = computed(() => {
  if (!props.zoneClimateForm.enabled) {
    return true
  }

  return [
    props.assignments?.co2_sensor,
    props.assignments?.co2_actuator,
    props.assignments?.root_vent_actuator,
  ].some((value) => typeof value === 'number' && value > 0)
})

const baseSaveAllowed = computed(() => Boolean(props.canConfigure) && !props.saveDisabled)

const canSaveRequiredDevices = computed(() => {
  return baseSaveAllowed.value && requiredDevicesSelectedCount.value === 3
})

const canSaveContourSection = computed(() => {
  return baseSaveAllowed.value
})

const canSaveIrrigationSection = computed(() => {
  return baseSaveAllowed.value
})

const canSaveCorrectionSection = computed(() => {
  return baseSaveAllowed.value
})

const canSaveLightingSection = computed(() => {
  return baseSaveAllowed.value && hasLightingBinding.value
})

const canSaveZoneClimateSection = computed(() => {
  return baseSaveAllowed.value && hasZoneClimateBinding.value
})
</script>
