<template>
  <div class="zone-automation-profile-sections space-y-4">
    <section
      v-if="showRequiredDevicesSection && !isZoneBlockLayout"
      class="rounded-xl border border-[color:var(--border-muted)]"
    >
      <details
        open
        class="group"
      >
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
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('device.irrigation')"
              >
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
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('device.ph_correction')"
              >
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
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('device.ec_correction')"
              >
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

    <section
      v-if="showWaterContourSection"
      class="rounded-xl border border-[color:var(--border-muted)]"
    >
      <details
        open
        class="group"
      >
        <summary class="flex cursor-pointer list-none items-start justify-between gap-3 p-4">
          <div>
            <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
              Водный контур
            </h4>
            <p class="mt-1 text-xs text-[color:var(--text-dim)]">
              {{ isZoneBlockLayout
                ? 'Обязательные ноды зоны и вся логика water runtime: topology, irrigation и correction.'
                : 'Тип системы, баковая схема и базовая гидравлическая конфигурация.' }}
            </p>
          </div>
          <span class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
            {{ isZoneBlockLayout ? 'Основной блок' : 'Базовая схема' }}
          </span>
        </summary>

        <div class="space-y-4 border-t border-[color:var(--border-muted)] p-4">
          <div
            v-if="isZoneBlockLayout && showNodeBindings && assignments"
            class="rounded-xl border border-[color:var(--border-muted)] p-3"
          >
            <div class="mb-3 flex items-center justify-between gap-3">
              <div>
                <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">
                  Привязка обязательных нод
                </h5>
                <p class="mt-1 text-xs text-[color:var(--text-dim)]">
                  Полив, pH и EC обязательны. Без них water runtime не считается готовым.
                </p>
              </div>
              <span class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
                {{ requiredDevicesSelectedCount }}/3
              </span>
            </div>

            <div class="grid grid-cols-1 gap-3 xl:grid-cols-3">
              <div class="grid grid-cols-1 gap-2 items-end">
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('device.irrigation')"
                >
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
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('device.ph_correction')"
                >
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
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('device.ec_correction')"
                >
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
          </div>

          <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('water.systemType')"
            >
              Тип системы
              <select
                v-model="waterForm.systemType"
                class="input-select mt-1 w-full"
                :disabled="!canConfigure || isSystemTypeLocked"
              >
                <option value="drip">drip</option>
                <option value="substrate_trays">substrate_trays</option>
                <option
                  disabled
                  value="nft"
                >nft (скоро)</option>
              </select>
            </label>

            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('water.tanksCount')"
            >
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

            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('water.enableDrainControl')"
            >
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

            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('water.drainTargetPercent')"
            >
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
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('water.valveSwitching')"
                >
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
                class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-dim)]"
              >
                Low-level relay plans 2-баковой топологии больше не редактируются на фронте. Командные шаги собираются backend/compiler из authority templates или уже сохранённого custom plan зоны.
              </div>
            </div>
          </details>

          <div
            v-if="isZoneBlockLayout"
            class="rounded-xl border border-[color:var(--border-muted)] p-3"
          >
            <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">
              Полив
            </h5>
            <p class="mt-1 text-xs text-[color:var(--text-dim)]">
              Основной цикл полива, окна приготовления и рабочие объёмы контура.
            </p>

            <div class="mt-3 rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3">
              <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('water.irrigationDecisionStrategy')"
                >
                  Режим полива
                  <select
                    v-model="waterForm.irrigationDecisionStrategy"
                    data-test="irrigation-decision-strategy"
                    class="input-select mt-1 w-full"
                    :disabled="!canConfigure"
                  >
                    <option value="task">По времени</option>
                    <option value="smart_soil_v1">Умный полив</option>
                  </select>
                </label>

                <div
                  v-if="waterForm.irrigationDecisionStrategy === 'task'"
                  class="text-xs text-[color:var(--text-muted)] md:col-span-3"
                >
                  <div class="font-semibold text-[color:var(--text-primary)]">
                    Параметры из текущей recipe phase
                  </div>
                  <div class="mt-2 grid grid-cols-1 gap-2 md:grid-cols-3">
                    <div>Mode: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeIrrigationSummary.mode ?? '—' }}</span></div>
                    <div>Interval: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeIrrigationSummary.intervalSec ?? '—' }}</span> сек</div>
                    <div>Duration: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeIrrigationSummary.durationSec ?? '—' }}</span> сек</div>
                  </div>
                </div>
              </div>
            </div>

            <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('water.intervalMinutes')"
              >
                Интервал полива (мин)
                <input
                  v-model.number="waterForm.intervalMinutes"
                  type="number"
                  min="5"
                  max="1440"
                  class="input-field mt-1 w-full"
                  :disabled="!canConfigure || waterForm.irrigationDecisionStrategy === 'task'"
                />
              </label>
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('water.durationSeconds')"
              >
                Длительность полива (сек)
                <input
                  v-model.number="waterForm.durationSeconds"
                  type="number"
                  min="1"
                  max="3600"
                  class="input-field mt-1 w-full"
                  :disabled="!canConfigure || waterForm.irrigationDecisionStrategy === 'task'"
                />
              </label>
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('water.irrigationBatchL')"
              >
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
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('water.fillTemperatureC')"
              >
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
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('water.cleanTankFillL')"
              >
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
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('water.nutrientTankTargetL')"
              >
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
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('water.fillWindowStart')"
              >
                Окно набора воды: от
                <input
                  v-model="waterForm.fillWindowStart"
                  type="time"
                  class="input-field mt-1 w-full"
                  :disabled="!canConfigure"
                />
              </label>
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('water.fillWindowEnd')"
              >
                Окно набора воды: до
                <input
                  v-model="waterForm.fillWindowEnd"
                  type="time"
                  class="input-field mt-1 w-full"
                  :disabled="!canConfigure"
                />
              </label>
            </div>

            <details class="mt-3 rounded-xl border border-[color:var(--border-muted)] p-3">
              <summary class="cursor-pointer text-sm font-semibold text-[color:var(--text-primary)]">
                Умный полив (decision, recovery, safety)
              </summary>

              <p class="mt-2 text-xs text-[color:var(--text-dim)]">
                Настройки decision-controller штатного полива (`smart_soil_v1`) и recovery/safety политики. Цели влажности (day/night) задаются в фазе рецепта.
              </p>

              <div class="mt-3 rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-muted)] p-3 text-xs text-[color:var(--text-muted)]">
                <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.correctionDuringIrrigation')"
                  >
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
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.correctionStabilizationSec')"
                  >
                    Стабилизация после дозирования (сек)
                    <input
                      v-model.number="waterForm.correctionStabilizationSec"
                      type="number"
                      min="0"
                      max="3600"
                      class="input-field mt-1 w-full"
                      :disabled="!canConfigure"
                    />
                  </label>
                  <div class="md:col-span-2 xl:col-span-2">
                    <div class="font-semibold text-[color:var(--text-primary)]">
                      Inline correction состав
                    </div>
                    <div class="mt-1">
                      Во время полива automation использует `Ca/Mg/Micro + pH`. `NPK` исключён и не настраивается на фронте.
                    </div>
                  </div>
                </div>
              </div>

              <div
                v-if="waterForm.irrigationDecisionStrategy === 'smart_soil_v1' && waterForm.systemType === 'drip'"
                class="mt-3 rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-muted)] p-3 text-xs"
                data-test="smart-irrigation-recipe-targets"
              >
                <div class="flex flex-wrap items-start justify-between gap-2">
                  <div class="font-semibold text-[color:var(--text-primary)]">
                    Цели из текущей фазы (soil moisture, %)
                  </div>
                  <div class="text-[color:var(--text-dim)]">
                    read-only
                  </div>
                </div>
                <div class="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 text-[color:var(--text-muted)]">
                  <div>
                    День: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeSoilMoistureTargets.day ?? '—' }}</span>
                  </div>
                  <div>
                    Ночь: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeSoilMoistureTargets.night ?? '—' }}</span>
                  </div>
                </div>
                <p class="mt-2 text-[color:var(--text-dim)]">
                  Если значения пустые — открой рецепт и заполни «Умный полив (soil moisture target)» в фазе.
                </p>
              </div>

              <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('water.irrigationDecisionStrategy')"
                >
                  Decision strategy
                  <select
                    v-model="waterForm.irrigationDecisionStrategy"
                    data-test="irrigation-decision-strategy"
                    class="input-select mt-1 w-full"
                    :disabled="!canConfigure"
                  >
                    <option value="task">По времени</option>
                    <option value="smart_soil_v1">Умный полив</option>
                  </select>
                </label>

                <label
                  v-if="showNodeBindings && assignments"
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('device.soil_moisture_sensor')"
                >
                  Soil moisture sensor
                  <select
                    v-model.number="assignments.soil_moisture_sensor"
                    class="input-select mt-1 w-full"
                    :disabled="!canConfigure"
                    data-test="soil-moisture-sensor-select"
                  >
                    <option :value="null">
                      Выберите датчик влажности
                    </option>
                    <option
                      v-for="node in soilMoistureCandidates"
                      :key="node.id"
                      :value="node.id"
                    >
                      {{ nodeLabel(node) }}
                    </option>
                  </select>
                  <div
                    v-if="showBindButtons || showRefreshButtons"
                    class="mt-2 flex items-center gap-2"
                  >
                    <Button
                      v-if="showBindButtons"
                      size="sm"
                      variant="secondary"
                      :disabled="!canBindSelected(assignments?.soil_moisture_sensor)"
                      @click="emit('bind-devices', ['soil_moisture_sensor'])"
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
                </label>

                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('water.irrigationDecisionLookbackSeconds')"
                >
                  Lookback (сек)
                  <input
                    v-model.number="waterForm.irrigationDecisionLookbackSeconds"
                    type="number"
                    min="60"
                    max="86400"
                    class="input-field mt-1 w-full"
                    :disabled="!canConfigure"
                  />
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('water.irrigationDecisionMinSamples')"
                >
                  Min samples
                  <input
                    v-model.number="waterForm.irrigationDecisionMinSamples"
                    type="number"
                    min="1"
                    max="100"
                    class="input-field mt-1 w-full"
                    :disabled="!canConfigure"
                  />
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('water.irrigationDecisionStaleAfterSeconds')"
                >
                  Telemetry stale after (сек)
                  <input
                    v-model.number="waterForm.irrigationDecisionStaleAfterSeconds"
                    type="number"
                    min="30"
                    max="86400"
                    class="input-field mt-1 w-full"
                    :disabled="!canConfigure"
                  />
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('water.irrigationDecisionHysteresisPct')"
                >
                  Hysteresis (%)
                  <input
                    v-model.number="waterForm.irrigationDecisionHysteresisPct"
                    type="number"
                    min="0"
                    max="100"
                    step="0.1"
                    class="input-field mt-1 w-full"
                    :disabled="!canConfigure"
                  />
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('water.irrigationDecisionSpreadAlertThresholdPct')"
                >
                  Spread alert threshold (%)
                  <input
                    v-model.number="waterForm.irrigationDecisionSpreadAlertThresholdPct"
                    type="number"
                    min="0"
                    max="100"
                    step="0.1"
                    class="input-field mt-1 w-full"
                    :disabled="!canConfigure"
                  />
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('water.irrigationAutoReplayAfterSetup')"
                >
                  Auto replay after setup
                  <select
                    v-model="waterForm.irrigationAutoReplayAfterSetup"
                    class="input-select mt-1 w-full"
                    :disabled="!canConfigure"
                  >
                    <option :value="true">Включён</option>
                    <option :value="false">Выключен</option>
                  </select>
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('water.irrigationMaxSetupReplays')"
                >
                  Max setup replays
                  <input
                    v-model.number="waterForm.irrigationMaxSetupReplays"
                    type="number"
                    min="0"
                    max="10"
                    class="input-field mt-1 w-full"
                    :disabled="!canConfigure"
                  />
                </label>
                <label
                  class="text-xs text-[color:var(--text-muted)] md:col-span-2 xl:col-span-2"
                  :title="fieldHelp('water.stopOnSolutionMin')"
                >
                  Stop on solution min
                  <select
                    v-model="waterForm.stopOnSolutionMin"
                    data-test="irrigation-stop-on-solution-min"
                    class="input-select mt-1 w-full"
                    :disabled="!canConfigure"
                  >
                    <option :value="true">Fail-closed при low solution</option>
                    <option :value="false">Не останавливать irrigation workflow</option>
                  </select>
                </label>
              </div>
            </details>
          </div>

          <div
            v-if="isZoneBlockLayout"
            class="rounded-xl border border-[color:var(--border-muted)] p-3"
          >
            <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">
              Раствор и коррекция
            </h5>
            <p class="mt-1 text-xs text-[color:var(--text-dim)]">
              Целевые параметры раствора и ограничения correction runtime.
            </p>

            <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('water.targetPh')"
              >
                Целевой pH (из рецепта)
                <input
                  v-model.number="waterForm.targetPh"
                  type="number"
                  min="4"
                  max="9"
                  step="0.1"
                  class="input-field mt-1 w-full"
                  disabled
                />
              </label>
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('water.targetEc')"
              >
                Целевой EC (из рецепта)
                <input
                  v-model.number="waterForm.targetEc"
                  type="number"
                  min="0.1"
                  max="10"
                  step="0.1"
                  class="input-field mt-1 w-full"
                  disabled
                />
              </label>
              <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-muted)] p-3 text-xs text-[color:var(--text-muted)] md:col-span-2">
                <div class="font-semibold text-[color:var(--text-primary)]">
                  Recipe-derived chemistry summary
                </div>
                <div class="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
                  <div>pH window: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeChemistrySummary.phMin ?? '—' }}..{{ recipeChemistrySummary.phMax ?? '—' }}</span></div>
                  <div>EC window: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeChemistrySummary.ecMin ?? '—' }}..{{ recipeChemistrySummary.ecMax ?? '—' }}</span></div>
                  <div class="md:col-span-2">
                    EC strategy: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeChemistrySummary.nutrientMode ?? 'ratio_ec_pid' }}</span>
                  </div>
                </div>
              </div>
            </div>

            <details class="mt-3 rounded-xl border border-[color:var(--border-muted)] p-3">
              <summary class="cursor-pointer text-sm font-semibold text-[color:var(--text-primary)]">
                Расширенные настройки коррекции
              </summary>

              <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('water.correctionMaxEcCorrectionAttempts')"
                >
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
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('water.correctionMaxPhCorrectionAttempts')"
                >
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
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('water.correctionPrepareRecirculationMaxAttempts')"
                >
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
                <label
                  class="text-xs text-[color:var(--text-muted)]"
                  :title="fieldHelp('water.correctionPrepareRecirculationMaxCorrectionAttempts')"
                >
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
              </div>
            </details>
          </div>

          <div
            v-if="showSectionSaveButtons"
            class="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)]"
          >
            <span>
              {{ isZoneBlockLayout
                ? 'Сохраняет блок целиком: обязательные ноды и логику водного контура.'
                : 'Сохраняет изменения этой секции в общем профиле зоны.' }}
            </span>
            <Button
              size="sm"
              :disabled="!canSaveContourSection"
              data-test="save-section-water-contour"
              @click="emit('save-section', 'water_contour')"
            >
              {{ savingSection === 'water_contour' ? 'Сохранение...' : (isZoneBlockLayout ? 'Сохранить блок' : 'Сохранить секцию') }}
            </Button>
          </div>
        </div>
      </details>
    </section>

    <section
      v-if="showIrrigationSection && !isZoneBlockLayout"
      class="rounded-xl border border-[color:var(--border-muted)]"
    >
      <details
        open
        class="group"
      >
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
          <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3">
            <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('water.irrigationDecisionStrategy')"
              >
                Режим полива
                <select
                  v-model="waterForm.irrigationDecisionStrategy"
                  data-test="irrigation-decision-strategy"
                  class="input-select mt-1 w-full"
                  :disabled="!canConfigure"
                >
                  <option value="task">По времени</option>
                  <option value="smart_soil_v1">Умный полив</option>
                </select>
              </label>
              <div
                v-if="waterForm.irrigationDecisionStrategy === 'task'"
                class="text-xs text-[color:var(--text-muted)] md:col-span-3"
              >
                <div class="font-semibold text-[color:var(--text-primary)]">
                  Параметры из текущей recipe phase
                </div>
                <div class="mt-2 grid grid-cols-1 gap-2 md:grid-cols-3">
                  <div>Mode: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeIrrigationSummary.mode ?? '—' }}</span></div>
                  <div>Interval: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeIrrigationSummary.intervalSec ?? '—' }}</span> сек</div>
                  <div>Duration: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeIrrigationSummary.durationSec ?? '—' }}</span> сек</div>
                </div>
              </div>
            </div>
          </div>

          <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('water.intervalMinutes')"
            >
              Интервал полива (мин)
              <input
                v-model.number="waterForm.intervalMinutes"
                type="number"
                min="5"
                max="1440"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure || waterForm.irrigationDecisionStrategy === 'task'"
              />
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('water.durationSeconds')"
            >
              Длительность полива (сек)
              <input
                v-model.number="waterForm.durationSeconds"
                type="number"
                min="1"
                max="3600"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure || waterForm.irrigationDecisionStrategy === 'task'"
              />
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('water.irrigationBatchL')"
            >
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
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('water.fillTemperatureC')"
            >
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
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('water.cleanTankFillL')"
            >
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
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('water.nutrientTankTargetL')"
            >
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
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('water.fillWindowStart')"
            >
              Окно набора воды: от
              <input
                v-model="waterForm.fillWindowStart"
                type="time"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure"
              />
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('water.fillWindowEnd')"
            >
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
                  Умный полив (decision, recovery, safety)
                </h5>
                <p class="mt-1 text-xs text-[color:var(--text-dim)]">
                  Strategy обычного полива, требования к телеметрии и replay-policy после setup/recovery. Цели влажности (day/night) задаются в фазе рецепта.
                </p>

                <div class="mt-3 rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-muted)] p-3 text-xs text-[color:var(--text-muted)]">
                  <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
                    <label
                      class="text-xs text-[color:var(--text-muted)]"
                      :title="fieldHelp('water.correctionDuringIrrigation')"
                    >
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
                    <label
                      class="text-xs text-[color:var(--text-muted)]"
                      :title="fieldHelp('water.correctionStabilizationSec')"
                    >
                      Стабилизация после дозирования (сек)
                      <input
                        v-model.number="waterForm.correctionStabilizationSec"
                        type="number"
                        min="0"
                        max="3600"
                        class="input-field mt-1 w-full"
                        :disabled="!canConfigure"
                      />
                    </label>
                    <div class="md:col-span-2 xl:col-span-2">
                      <div class="font-semibold text-[color:var(--text-primary)]">
                        Inline correction состав
                      </div>
                      <div class="mt-1">
                        Во время полива automation использует `Ca/Mg/Micro + pH`. `NPK` исключён и не настраивается на фронте.
                      </div>
                    </div>
                  </div>
                </div>

                <div
                  v-if="waterForm.irrigationDecisionStrategy === 'smart_soil_v1' && waterForm.systemType === 'drip'"
                  class="mt-3 rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-muted)] p-3 text-xs"
                  data-test="smart-irrigation-recipe-targets"
                >
                  <div class="flex flex-wrap items-start justify-between gap-2">
                    <div class="font-semibold text-[color:var(--text-primary)]">
                      Цели из текущей фазы (soil moisture, %)
                    </div>
                    <div class="text-[color:var(--text-dim)]">
                      read-only
                    </div>
                  </div>
                  <div class="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 text-[color:var(--text-muted)]">
                    <div>
                      День: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeSoilMoistureTargets.day ?? '—' }}</span>
                    </div>
                    <div>
                      Ночь: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeSoilMoistureTargets.night ?? '—' }}</span>
                    </div>
                  </div>
                  <p class="mt-2 text-[color:var(--text-dim)]">
                    Если значения пустые — открой рецепт и заполни «Умный полив (soil moisture target)» в фазе.
                  </p>
                </div>
                <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.irrigationDecisionStrategy')"
                  >
                    Decision strategy
                    <select
                      v-model="waterForm.irrigationDecisionStrategy"
                      data-test="irrigation-decision-strategy"
                      class="input-select mt-1 w-full"
                      :disabled="!canConfigure"
                    >
                      <option value="task">По времени</option>
                      <option value="smart_soil_v1">Умный полив</option>
                    </select>
                  </label>
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.irrigationDecisionLookbackSeconds')"
                  >
                    Lookback (сек)
                    <input
                      v-model.number="waterForm.irrigationDecisionLookbackSeconds"
                      type="number"
                      min="60"
                      max="86400"
                      class="input-field mt-1 w-full"
                      :disabled="!canConfigure"
                    />
                  </label>
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.irrigationDecisionMinSamples')"
                  >
                    Min samples
                    <input
                      v-model.number="waterForm.irrigationDecisionMinSamples"
                      type="number"
                      min="1"
                      max="100"
                      class="input-field mt-1 w-full"
                      :disabled="!canConfigure"
                    />
                  </label>
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.irrigationDecisionStaleAfterSeconds')"
                  >
                    Telemetry stale after (сек)
                    <input
                      v-model.number="waterForm.irrigationDecisionStaleAfterSeconds"
                      type="number"
                      min="30"
                      max="86400"
                      class="input-field mt-1 w-full"
                      :disabled="!canConfigure"
                    />
                  </label>
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.irrigationDecisionHysteresisPct')"
                  >
                    Hysteresis (%)
                    <input
                      v-model.number="waterForm.irrigationDecisionHysteresisPct"
                      type="number"
                      min="0"
                      max="100"
                      step="0.1"
                      class="input-field mt-1 w-full"
                      :disabled="!canConfigure"
                    />
                  </label>
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.irrigationDecisionSpreadAlertThresholdPct')"
                  >
                    Spread alert threshold (%)
                    <input
                      v-model.number="waterForm.irrigationDecisionSpreadAlertThresholdPct"
                      type="number"
                      min="0"
                      max="100"
                      step="0.1"
                      class="input-field mt-1 w-full"
                      :disabled="!canConfigure"
                    />
                  </label>
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.irrigationAutoReplayAfterSetup')"
                  >
                    Auto replay after setup
                    <select
                      v-model="waterForm.irrigationAutoReplayAfterSetup"
                      class="input-select mt-1 w-full"
                      :disabled="!canConfigure"
                    >
                      <option :value="true">Включён</option>
                      <option :value="false">Выключен</option>
                    </select>
                  </label>
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.irrigationMaxSetupReplays')"
                  >
                    Max setup replays
                    <input
                      v-model.number="waterForm.irrigationMaxSetupReplays"
                      type="number"
                      min="0"
                      max="10"
                      class="input-field mt-1 w-full"
                      :disabled="!canConfigure"
                    />
                  </label>
                </div>
              </div>

              <div class="rounded-xl border border-[color:var(--border-muted)] p-3">
                <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">
                  Диагностика и refill
                </h5>
                <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.diagnosticsEnabled')"
                  >
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
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.diagnosticsIntervalMinutes')"
                  >
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
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.diagnosticsWorkflow')"
                  >
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
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.cleanTankFullThreshold')"
                  >
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
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.refillDurationSeconds')"
                  >
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
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.refillTimeoutSeconds')"
                  >
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
                  <label
                    class="text-xs text-[color:var(--text-muted)] md:col-span-2"
                    :title="fieldHelp('water.refillRequiredNodeTypes')"
                  >
                    Обязательные типы нод для refill
                    <input
                      v-model="waterForm.refillRequiredNodeTypes"
                      type="text"
                      class="input-field mt-1 w-full"
                      :disabled="!canConfigure"
                    />
                  </label>
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.refillPreferredChannel')"
                  >
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
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.startupCleanFillTimeoutSeconds')"
                  >
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
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.startupSolutionFillTimeoutSeconds')"
                  >
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
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.startupPrepareRecirculationTimeoutSeconds')"
                  >
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
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.startupCleanFillRetryCycles')"
                  >
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
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.irrigationRecoveryMaxContinueAttempts')"
                  >
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
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.irrigationRecoveryTimeoutSeconds')"
                  >
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
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.manualIrrigationSeconds')"
                  >
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
                  Fail-safe guards
                </h5>
                <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.cleanFillMinCheckDelayMs')"
                  >
                    Clean fill: задержка проверки min (мс)
                    <input
                      v-model.number="waterForm.cleanFillMinCheckDelayMs"
                      type="number"
                      min="0"
                      max="3600000"
                      step="10"
                      class="input-field mt-1 w-full"
                      :disabled="!canConfigure"
                    />
                  </label>
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.solutionFillCleanMinCheckDelayMs')"
                  >
                    Solution fill: задержка clean_min (мс)
                    <input
                      v-model.number="waterForm.solutionFillCleanMinCheckDelayMs"
                      type="number"
                      min="0"
                      max="3600000"
                      step="10"
                      class="input-field mt-1 w-full"
                      :disabled="!canConfigure"
                    />
                  </label>
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.solutionFillSolutionMinCheckDelayMs')"
                  >
                    Solution fill: leak-check по solution_min (мс)
                    <input
                      v-model.number="waterForm.solutionFillSolutionMinCheckDelayMs"
                      type="number"
                      min="0"
                      max="3600000"
                      step="10"
                      class="input-field mt-1 w-full"
                      :disabled="!canConfigure"
                    />
                  </label>
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.estopDebounceMs')"
                  >
                    E-stop debounce (мс)
                    <input
                      v-model.number="waterForm.estopDebounceMs"
                      type="number"
                      min="20"
                      max="5000"
                      step="10"
                      class="input-field mt-1 w-full"
                      :disabled="!canConfigure"
                    />
                  </label>
                  <label
                    class="text-xs text-[color:var(--text-muted)] md:col-span-2 xl:col-span-2"
                    :title="fieldHelp('water.recirculationStopOnSolutionMin')"
                  >
                    Recirculation: stop on solution min
                    <select
                      v-model="waterForm.recirculationStopOnSolutionMin"
                      class="input-select mt-1 w-full"
                      :disabled="!canConfigure"
                    >
                      <option :value="true">Fail-closed при low solution</option>
                      <option :value="false">Не останавливать recirculation</option>
                    </select>
                  </label>
                  <label
                    class="text-xs text-[color:var(--text-muted)] md:col-span-2 xl:col-span-2"
                    :title="fieldHelp('water.stopOnSolutionMin')"
                  >
                    Irrigation: stop on solution min
                    <select
                      v-model="waterForm.stopOnSolutionMin"
                      data-test="irrigation-stop-on-solution-min"
                      class="input-select mt-1 w-full"
                      :disabled="!canConfigure"
                    >
                      <option :value="true">Fail-closed при low solution</option>
                      <option :value="false">Не останавливать irrigation workflow</option>
                    </select>
                  </label>
                </div>
              </div>

              <div class="rounded-xl border border-[color:var(--border-muted)] p-3">
                <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">
                  Плановая смена раствора
                </h5>
                <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.solutionChangeEnabled')"
                  >
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
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.solutionChangeIntervalMinutes')"
                  >
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
                  <label
                    class="text-xs text-[color:var(--text-muted)]"
                    :title="fieldHelp('water.solutionChangeDurationSeconds')"
                  >
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

    <section
      v-if="showSolutionCorrectionSection && !isZoneBlockLayout"
      class="rounded-xl border border-[color:var(--border-muted)]"
    >
      <details
        open
        class="group"
      >
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
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('water.targetPh')"
            >
              Целевой pH (из рецепта)
              <input
                v-model.number="waterForm.targetPh"
                type="number"
                min="4"
                max="9"
                step="0.1"
                class="input-field mt-1 w-full"
                disabled
              />
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('water.targetEc')"
            >
              Целевой EC (из рецепта)
              <input
                v-model.number="waterForm.targetEc"
                type="number"
                min="0.1"
                max="10"
                step="0.1"
                class="input-field mt-1 w-full"
                disabled
              />
            </label>
            <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-muted)] p-3 text-xs text-[color:var(--text-muted)] md:col-span-2">
              <div class="font-semibold text-[color:var(--text-primary)]">
                Recipe-derived chemistry summary
              </div>
              <div class="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
                <div>pH window: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeChemistrySummary.phMin ?? '—' }}..{{ recipeChemistrySummary.phMax ?? '—' }}</span></div>
                <div>EC window: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeChemistrySummary.ecMin ?? '—' }}..{{ recipeChemistrySummary.ecMax ?? '—' }}</span></div>
                <div class="md:col-span-2">
                  EC strategy: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeChemistrySummary.nutrientMode ?? 'ratio_ec_pid' }}</span>
                </div>
              </div>
            </div>
          </div>

          <details class="rounded-xl border border-[color:var(--border-muted)] p-3">
            <summary class="cursor-pointer text-sm font-semibold text-[color:var(--text-primary)]">
              Расширенные настройки
            </summary>

            <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('water.correctionMaxEcCorrectionAttempts')"
              >
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
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('water.correctionMaxPhCorrectionAttempts')"
              >
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
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('water.correctionPrepareRecirculationMaxAttempts')"
              >
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
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('water.correctionPrepareRecirculationMaxCorrectionAttempts')"
              >
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

    <section
      v-if="showLightingSection"
      class="rounded-xl border border-[color:var(--border-muted)]"
    >
      <details
        :open="showLightingEnableToggle ? lightingForm.enabled : true"
        class="group"
      >
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
          <div
            v-if="showLightingEnableToggle"
            class="flex items-center justify-end"
          >
            <label
              class="inline-flex items-center gap-2 text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('lighting.enabled')"
            >
              <input
                v-model="lightingForm.enabled"
                type="checkbox"
                :disabled="!canConfigure"
              />
              Управлять освещением
            </label>
          </div>

          <div
            v-else-if="!lightingForm.enabled"
            class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)]"
          >
            Включите подсистему освещения, чтобы открыть привязку ноды и настройки логики для этого блока.
          </div>

          <div
            v-if="lightingForm.enabled && showNodeBindings && assignments"
            class="grid grid-cols-1 gap-3 xl:grid-cols-2"
          >
            <div class="grid grid-cols-1 gap-2 items-end">
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('device.light')"
              >
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
            v-if="lightingForm.enabled && showLightingConfigFields"
            class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4"
          >
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('lighting.luxDay')"
            >
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
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('lighting.luxNight')"
            >
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
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('lighting.hoursOn')"
            >
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
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('lighting.scheduleStart')"
            >
              Начало
              <input
                v-model="lightingForm.scheduleStart"
                type="time"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure"
              />
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('lighting.scheduleEnd')"
            >
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
            v-if="lightingForm.enabled && showLightingConfigFields"
            class="rounded-xl border border-[color:var(--border-muted)] p-3"
          >
            <summary class="cursor-pointer text-sm font-semibold text-[color:var(--text-primary)]">
              Расширенные настройки
            </summary>

            <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('lighting.intervalMinutes')"
              >
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
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('lighting.manualIntensity')"
              >
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
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('lighting.manualDurationHours')"
              >
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
            <span>
              {{ isZoneBlockLayout
                ? 'Сохраняет блок освещения: switch, привязку ноды и параметры досветки.'
                : (showLightingConfigFields
                  ? 'Сохраняет изменения этой секции в общем профиле зоны.'
                  : 'Сохраняет binding устройств для секции освещения.') }}
            </span>
            <Button
              size="sm"
              :disabled="!canSaveLightingSection"
              data-test="save-section-lighting"
              @click="emit('save-section', 'lighting')"
            >
              {{ savingSection === 'lighting' ? 'Сохранение...' : (isZoneBlockLayout ? 'Сохранить блок' : 'Сохранить секцию') }}
            </Button>
          </div>
        </div>
      </details>
    </section>

    <section
      v-if="showZoneClimateSection"
      class="rounded-xl border border-[color:var(--border-muted)]"
    >
      <details
        :open="showZoneClimateEnableToggle ? zoneClimateForm.enabled : true"
        class="group"
      >
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
          <div
            v-if="showZoneClimateEnableToggle"
            class="flex items-center justify-end"
          >
            <label
              class="inline-flex items-center gap-2 text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('zoneClimate.enabled')"
            >
              <input
                v-model="zoneClimateForm.enabled"
                type="checkbox"
                :disabled="!canConfigure"
              />
              Управлять климатом зоны
            </label>
          </div>

          <div
            v-else-if="!zoneClimateForm.enabled"
            class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)]"
          >
            Включите климат зоны, чтобы открыть привязку CO2/root-vent нод и настройки этого блока.
          </div>

          <div
            v-if="zoneClimateForm.enabled && showNodeBindings && assignments"
            class="grid grid-cols-1 gap-3 xl:grid-cols-3"
          >
            <div class="grid grid-cols-1 gap-2 items-end">
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('device.co2_sensor')"
              >
                Датчик CO2
                <select
                  v-model.number="assignments.co2_sensor"
                  class="input-select mt-1 w-full"
                  :disabled="!canConfigure"
                  data-test="co2-sensor-select"
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
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('device.co2_actuator')"
              >
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
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="fieldHelp('device.root_vent_actuator')"
              >
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
            <span>
              {{ isZoneBlockLayout
                ? 'Сохраняет блок климата зоны: switch, привязку нод и параметры подсистемы.'
                : (showZoneClimateConfigFields
                  ? 'Сохраняет изменения этой секции в общем профиле зоны.'
                  : 'Сохраняет binding устройств для секции климата зоны.') }}
            </span>
            <Button
              size="sm"
              :disabled="!canSaveZoneClimateSection"
              data-test="save-section-zone-climate"
              @click="emit('save-section', 'zone_climate')"
            >
              {{ savingSection === 'zone_climate' ? 'Сохранение...' : (isZoneBlockLayout ? 'Сохранить блок' : 'Сохранить секцию') }}
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
  soil_moisture_sensor: number | null
  co2_sensor: number | null
  co2_actuator: number | null
  root_vent_actuator: number | null
}

export type ZoneAutomationBindRole =
  | 'irrigation'
  | 'ph_correction'
  | 'ec_correction'
  | 'light'
  | 'soil_moisture_sensor'
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
  currentRecipePhase?: unknown | null
  layoutMode?: 'legacy' | 'zone_blocks'
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
  showCorrectionCalibrationStack?: boolean
  zoneId?: number | null
  sensorCalibrationSettings?: SensorCalibrationSettings | null
  showSectionSaveButtons?: boolean
  saveDisabled?: boolean
  savingSection?: ZoneAutomationSectionSaveKey | null
  showRequiredDevicesSection?: boolean
  showWaterContourSection?: boolean
  showIrrigationSection?: boolean
  showSolutionCorrectionSection?: boolean
  showLightingSection?: boolean
  showLightingEnableToggle?: boolean
  showLightingConfigFields?: boolean
  showZoneClimateSection?: boolean
  showZoneClimateEnableToggle?: boolean
  showZoneClimateConfigFields?: boolean
}>(), {
  layoutMode: 'legacy',
  canConfigure: true,
  isSystemTypeLocked: false,
  currentRecipePhase: null,
  showNodeBindings: false,
  showBindButtons: false,
  showRefreshButtons: false,
  bindDisabled: false,
  bindingInProgress: false,
  refreshDisabled: false,
  refreshingNodes: false,
  availableNodes: () => [],
  showCorrectionCalibrationStack: false,
  zoneId: null,
  sensorCalibrationSettings: null,
  showSectionSaveButtons: false,
  saveDisabled: false,
  savingSection: null,
  showRequiredDevicesSection: true,
  showWaterContourSection: true,
  showIrrigationSection: true,
  showSolutionCorrectionSection: true,
  showLightingSection: true,
  showLightingEnableToggle: true,
  showLightingConfigFields: true,
  showZoneClimateSection: true,
  showZoneClimateEnableToggle: true,
  showZoneClimateConfigFields: true,
})

const waterForm = defineModel<WaterFormState>('waterForm', { required: true })
const lightingForm = defineModel<LightingFormState>('lightingForm', { required: true })
const zoneClimateForm = defineModel<ZoneClimateFormState>('zoneClimateForm', { required: true })
const assignments = defineModel<ZoneAutomationSectionAssignments | null>('assignments', { default: null })

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }

  return value as Record<string, unknown>
}

function toNullablePercent(value: unknown): number | null {
  if (value === null || value === undefined || value === '') {
    return null
  }
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function toNullableNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') {
    return null
  }

  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

const recipeSoilMoistureTargets = computed(() => {
  const phase = asRecord(props.currentRecipePhase)
  const extensions = asRecord(phase?.extensions)
  const dayNight = asRecord(extensions?.day_night)
  const soil = asRecord(dayNight?.soil_moisture)

  return {
    day: toNullablePercent(soil?.day),
    night: toNullablePercent(soil?.night),
  }
})

const recipeChemistrySummary = computed(() => {
  const phase = asRecord(props.currentRecipePhase)
  const targets = asRecord(phase?.targets)
  const phBand = asRecord(targets?.ph)
  const ecBand = asRecord(targets?.ec)

  return {
    phTarget: toNullableNumber(phase?.ph_target),
    phMin: toNullableNumber(phase?.ph_min ?? phBand?.min),
    phMax: toNullableNumber(phase?.ph_max ?? phBand?.max),
    ecTarget: toNullableNumber(phase?.ec_target),
    ecMin: toNullableNumber(phase?.ec_min ?? ecBand?.min),
    ecMax: toNullableNumber(phase?.ec_max ?? ecBand?.max),
    nutrientMode: typeof phase?.nutrient_mode === 'string' ? phase.nutrient_mode : null,
  }
})

const recipeIrrigationSummary = computed(() => {
  const phase = asRecord(props.currentRecipePhase)

  return {
    mode: typeof phase?.irrigation_mode === 'string' ? phase.irrigation_mode : null,
    intervalSec: toNullableNumber(phase?.irrigation_interval_sec),
    durationSec: toNullableNumber(phase?.irrigation_duration_sec),
  }
})

const emit = defineEmits<{
  (e: 'bind-devices', roles: ZoneAutomationBindRole[]): void
  (e: 'refresh-nodes'): void
  (e: 'save-section', section: ZoneAutomationSectionSaveKey): void
}>()

const isZoneBlockLayout = computed(() => props.layoutMode === 'zone_blocks')

const FIELD_HELP: Record<string, string> = {
  'device.irrigation': 'Основная нода полива зоны. Через неё runtime ожидает каналы запуска полива и refill/flow-команды для водного узла.',
  'device.ph_correction': 'Нода pH-коррекции. Должна содержать pH sensor и/или dosing channels для кислотной или щелочной коррекции.',
  'device.ec_correction': 'Нода EC-коррекции. Используется для EC sensor и дозирующих насосов удобрений в контуре correction runtime.',
  'device.light': 'Нода освещения, к которой будут привязаны команды досветки и ручного lighting override.',
  'device.soil_moisture_sensor': 'Источник телеметрии влажности субстрата (SOIL_MOISTURE). Нужен для стратегии smart_soil_v1 (умный полив).',
  'device.co2_sensor': 'Источник телеметрии CO2 для zonal climate. От этой ноды зависит измерение ppm внутри зоны.',
  'device.co2_actuator': 'Исполнитель подачи CO2. Нужен, если zonal climate должен управлять инжекцией CO2 в этой зоне.',
  'device.root_vent_actuator': 'Исполнитель прикорневой вентиляции или локального airflow для zonal climate зоны.',
  'water.systemType': 'Базовая гидравлическая схема зоны. От system type зависят допустимые targets, tank layout и runtime command plans.',
  'water.tanksCount': 'Количество баков в контуре. 2 бака включают чистую воду и раствор, 3 бака добавляют отдельный дренажный контур.',
  'water.enableDrainControl': 'Включает контроль процента дренажа. Имеет смысл только для 3-баковой схемы с отдельным drain контуром.',
  'water.drainTargetPercent': 'Целевой процент дренажа относительно подачи. Используется как ориентир для режима с drain control.',
  'water.valveSwitching': 'Разрешает relay-командам переключать клапаны между фазами clean fill, solution fill и recirculation.',
  'water.intervalMinutes': 'Период между штатными поливами. Чем меньше интервал, тем чаще scheduler будет инициировать irrigation workflow.',
  'water.durationSeconds': 'Длительность одного поливочного окна. Это прямое время работы исполнительного контура полива.',
  'water.irrigationBatchL': 'Целевой объём одной порции полива. Используется как агрономический ориентир при настройке цикла.',
  'water.fillTemperatureC': 'Желаемая температура воды на стадии заполнения бака. Нужна как target для приготовления раствора.',
  'water.cleanTankFillL': 'Рабочий объём чистого бака, который runtime стремится набрать перед приготовлением раствора.',
  'water.nutrientTankTargetL': 'Целевой объём бака раствора после подготовки nutrient mix.',
  'water.fillWindowStart': 'Начало разрешённого окна, в которое системе можно запускать набор воды.',
  'water.fillWindowEnd': 'Конец разрешённого окна набора воды. Вне окна runtime не должен инициировать fill workflow.',
  'water.diagnosticsEnabled': 'Разрешает автоматические diagnostic/workflow проверки водного контура перед стартом или по расписанию.',
  'water.diagnosticsIntervalMinutes': 'Как часто запускать diagnostic workflow, если он разрешён для зоны.',
  'water.diagnosticsWorkflow': 'Какой режим diagnostic workflow использовать: при старте, на старте цикла или как отдельную диагностику.',
  'water.cleanTankFullThreshold': 'Порог заполнения чистого бака в долях от 0 до 1, после которого бак считается полным.',
  'water.refillDurationSeconds': 'Штатная длительность одной refill-команды, если требуется дозаполнение чистого бака.',
  'water.refillTimeoutSeconds': 'Максимальное время ожидания завершения refill workflow до признания таймаута.',
  'water.refillRequiredNodeTypes': 'CSV-список типов нод, которые обязаны быть доступны для refill workflow.',
  'water.refillPreferredChannel': 'Предпочтительный channel/alias, который runtime будет использовать для refill-команды.',
  'water.startupCleanFillTimeoutSeconds': 'Fail-closed таймаут на набор чистой воды при startup workflow.',
  'water.startupSolutionFillTimeoutSeconds': 'Fail-closed таймаут на набор раствора при startup workflow.',
  'water.startupPrepareRecirculationTimeoutSeconds': 'Максимальное время ожидания стадии prepare recirculation до аварийного завершения.',
  'water.startupCleanFillRetryCycles': 'Сколько раз startup workflow может повторить clean fill перед отказом.',
  'water.cleanFillMinCheckDelayMs': 'Через сколько миллисекунд после открытия valve_clean_fill нода проверяет level_clean_min и fail-closed останавливает набор, если источник пуст.',
  'water.solutionFillCleanMinCheckDelayMs': 'Через сколько миллисекунд после старта solution_fill нода проверяет level_clean_min и fail-closed останавливает набор при отсутствии clean source.',
  'water.solutionFillSolutionMinCheckDelayMs': 'Через сколько миллисекунд после старта solution_fill выполняется leak-check по level_solution_min.',
  'water.recirculationStopOnSolutionMin': 'Fail-closed guard: prepare recirculation должен останавливаться при lower solution level.',
  'water.estopDebounceMs': 'Debounce физической кнопки аварийной остановки. Пока кнопка нажата, node принудительно держит все актуаторы OFF.',
  'water.irrigationDecisionStrategy': 'Decision-controller штатного полива: task принудительно выполняет запуск по плану, smart_soil_v1 сначала оценивает soil moisture и качество телеметрии.',
  'water.irrigationDecisionLookbackSeconds': 'Глубина окна истории телеметрии, из которого decision-controller берёт soil moisture samples.',
  'water.irrigationDecisionMinSamples': 'Минимум samples в lookback-окне, без которого smart_soil_v1 должен деградировать или skip-нуть запуск.',
  'water.irrigationDecisionStaleAfterSeconds': 'Порог stale telemetry: если последние данные старше этого окна, decision-controller не должен считать их надёжными.',
  'water.irrigationDecisionHysteresisPct': 'Гистерезис вокруг target moisture, который уменьшает лишние запуски полива на шумных данных.',
  'water.irrigationDecisionSpreadAlertThresholdPct': 'Порог разброса датчиков влажности, после которого smart_soil_v1 должен считать зону неоднородной и поднять degraded signal.',
  'water.irrigationRecoveryMaxContinueAttempts': 'Максимум продолжений recovery-окна после полива, если targets ещё не достигнуты.',
  'water.irrigationRecoveryTimeoutSeconds': 'Общий таймаут recovery-фазы после полива.',
  'water.irrigationAutoReplayAfterSetup': 'Разрешает AE3 автоматически повторить normal irrigation после setup/recovery, если initial launch был отложен или оборван safety-path.',
  'water.irrigationMaxSetupReplays': 'Сколько раз runtime может автоматически переиграть irrigation после setup/recovery без нового operator trigger.',
  'water.stopOnSolutionMin': 'Fail-closed guard: normal irrigation должен останавливаться при low-solution signal, а не продолжать workflow вслепую.',
  'water.manualIrrigationSeconds': 'Стандартная длительность ручного полива из UI, если оператор запускает irrigation вручную.',
  'water.solutionChangeEnabled': 'Включает плановую замену раствора по расписанию, отдельную от обычного поливочного цикла.',
  'water.solutionChangeIntervalMinutes': 'Интервал между плановыми заменами раствора, если этот режим включён.',
  'water.solutionChangeDurationSeconds': 'Сколько длится одно окно плановой смены раствора.',
  'water.targetPh': 'Readonly поле. Канонический target pH берётся только из активной фазы рецепта и не сохраняется в zone logic profile.',
  'water.targetEc': 'Readonly поле. Канонический target EC берётся только из активной фазы рецепта и не сохраняется в zone logic profile.',
  'water.correctionDuringIrrigation': 'Разрешает correction runtime работать прямо во время irrigation path, а не только до него.',
  'water.correctionMaxEcCorrectionAttempts': 'Максимум dosing-попыток EC-коррекции в одном correction window.',
  'water.correctionMaxPhCorrectionAttempts': 'Максимум dosing-попыток pH-коррекции в одном correction window.',
  'water.correctionPrepareRecirculationMaxAttempts': 'Сколько recirculation-окон runtime может открыть при неуспешной коррекции.',
  'water.correctionPrepareRecirculationMaxCorrectionAttempts': 'Жёсткий лимит внутренних correction-шагов до fail-closed остановки.',
  'water.correctionStabilizationSec': 'Дополнительное время ожидания после дозы, чтобы измерения стабилизировались перед следующим решением.',
  'lighting.enabled': 'Включает подсистему досветки для зоны и делает lighting configuration частью профиля автоматики.',
  'lighting.luxDay': 'Целевая освещённость днём, которой runtime должен придерживаться в дневном окне.',
  'lighting.luxNight': 'Целевая освещённость ночью. Обычно 0, если ночью досветка не нужна.',
  'lighting.hoursOn': 'Суммарная желаемая длительность света в сутки.',
  'lighting.scheduleStart': 'Время старта дневного lighting window.',
  'lighting.scheduleEnd': 'Время завершения lighting window.',
  'lighting.intervalMinutes': 'Частота пересчёта и обновления lighting automation в минутах.',
  'lighting.manualIntensity': 'Интенсивность в процентах для ручного режима досветки.',
  'lighting.manualDurationHours': 'Длительность ручного lighting override в часах.',
  'zoneClimate.enabled': 'Включает отдельный zonal climate subsystem для CO2 и прикорневой вентиляции.',
}

function fieldHelp(key: string): string {
  return FIELD_HELP[key] ?? 'Параметр профиля автоматики зоны.'
}

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

function nodeBindingRoles(node: SetupWizardNode): string[] {
  return Array.isArray(node.channels)
    ? node.channels
      .map((channel) => String(channel.binding_role ?? '').toLowerCase())
      .filter((role) => role.length > 0)
    : []
}

function matchesAnyChannel(node: SetupWizardNode, candidates: string[]): boolean {
  const channels = new Set(nodeChannels(node))
  return candidates.some((candidate) => channels.has(candidate))
}

function matchesAnyBindingRole(node: SetupWizardNode, candidates: string[]): boolean {
  const bindingRoles = new Set(nodeBindingRoles(node))
  return candidates.some((candidate) => bindingRoles.has(candidate))
}

const irrigationCandidates = computed(() => {
  return props.availableNodes.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'irrig'
      || matchesAnyBindingRole(node, ['main_pump', 'drain'])
      || matchesAnyChannel(node, [
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
    return type === 'ph'
      || matchesAnyBindingRole(node, ['ph_acid_pump', 'ph_base_pump'])
      || matchesAnyChannel(node, ['ph_sensor', 'pump_acid', 'pump_base'])
  })
})

const ecCandidates = computed(() => {
  return props.availableNodes.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'ec'
      || matchesAnyBindingRole(node, ['ec_npk_pump', 'ec_calcium_pump', 'ec_magnesium_pump', 'ec_micro_pump'])
      || matchesAnyChannel(node, ['ec_sensor', 'pump_a', 'pump_b', 'pump_c', 'pump_d'])
  })
})

const lightCandidates = computed(() => {
  return props.availableNodes.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'light'
      || matchesAnyBindingRole(node, ['light'])
      || matchesAnyChannel(node, ['light', 'light_main', 'white_light', 'uv_light'])
  })
})

const soilMoistureCandidates = computed(() => {
  return props.availableNodes.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'soil'
      || type === 'substrate'
      || matchesAnyBindingRole(node, ['soil_moisture_sensor'])
      || matchesAnyChannel(node, ['soil_moisture', 'soil_moisture_pct', 'substrate_moisture'])
  })
})

const co2SensorCandidates = computed(() => {
  return props.availableNodes.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'climate'
      || matchesAnyBindingRole(node, ['co2_sensor'])
      || matchesAnyChannel(node, ['co2_ppm'])
  })
})

const co2ActuatorCandidates = computed(() => {
  return props.availableNodes.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'climate'
      || matchesAnyBindingRole(node, ['co2_actuator'])
      || matchesAnyChannel(node, ['co2_inject'])
  })
})

const rootVentCandidates = computed(() => {
  return props.availableNodes.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'climate'
      || matchesAnyBindingRole(node, ['root_vent_actuator'])
      || matchesAnyChannel(node, ['root_vent', 'fan_root'])
  })
})

const requiredDevicesSelectedCount = computed(() => {
  const current = assignments.value
  if (!current) {
    return 0
  }

  return [
    current.irrigation,
    current.ph_correction,
    current.ec_correction,
  ].filter((value): value is number => typeof value === 'number' && value > 0).length
})

const hasLightingBinding = computed(() => {
  if (!lightingForm.value.enabled) {
    return true
  }

  const current = assignments.value
  return typeof current?.light === 'number' && current.light > 0
})

const hasZoneClimateBinding = computed(() => {
  if (!zoneClimateForm.value.enabled) {
    return true
  }

  const current = assignments.value
  return [
    current?.co2_sensor,
    current?.co2_actuator,
    current?.root_vent_actuator,
  ].some((value) => typeof value === 'number' && value > 0)
})

const baseSaveAllowed = computed(() => Boolean(props.canConfigure) && !props.saveDisabled)

const canSaveRequiredDevices = computed(() => {
  return baseSaveAllowed.value && requiredDevicesSelectedCount.value === 3
})

const canSaveContourSection = computed(() => {
  return baseSaveAllowed.value && (!isZoneBlockLayout.value || requiredDevicesSelectedCount.value === 3)
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

<style scoped>
.zone-automation-profile-sections :deep(label.text-xs) {
  display: grid;
  gap: 0.32rem;
  line-height: 1.35;
}

.zone-automation-profile-sections :deep(.input-field),
.zone-automation-profile-sections :deep(.input-select) {
  height: 2.2rem;
  padding: 0 0.7rem;
  font-size: 0.78rem;
  border-radius: 0.72rem;
}

.zone-automation-profile-sections :deep(input[type='checkbox']) {
  width: 0.95rem;
  height: 0.95rem;
}
</style>
