<template>
  <Modal
    :open="show"
    :title="wizardTitle"
    size="large"
    data-testid="growth-cycle-wizard"
    @close="handleClose"
  >
    <ErrorBoundary>
      <div class="mb-6">
        <div class="flex items-center justify-center gap-1.5">
          <div
            v-for="(step, index) in steps"
            :key="step.key"
            class="w-2.5 h-2.5 rounded-full transition-colors"
            :class="[
              index < currentStep
                ? 'bg-[color:var(--accent-green)]'
                : index === currentStep
                  ? 'bg-[color:var(--accent-cyan)] ring-2 ring-[color:var(--accent-cyan)]/30'
                  : 'bg-[color:var(--border-muted)]',
            ]"
          />
        </div>
        <p class="text-center text-sm text-[color:var(--text-muted)] mt-2">
          {{ steps[currentStep]?.label }} ({{ currentStep + 1 }} / {{ steps.length }})
        </p>
      </div>

      <div
        v-if="currentStep === 0"
        class="space-y-4"
      >
        <div v-if="zoneId">
          <div class="p-4 rounded-lg bg-[color:var(--badge-success-bg)] border border-[color:var(--badge-success-border)]">
            <div class="text-sm font-medium text-[color:var(--badge-success-text)]">
              Зона выбрана: {{ zoneName || `Зона #${zoneId}` }}
            </div>
          </div>
        </div>
        <div v-else>
          <label class="block text-sm font-medium mb-2">Выберите зону</label>
          <select
            v-model="form.zoneId"
            class="input-select w-full"
            @change="onZoneSelected"
          >
            <option :value="null">
              Выберите зону
            </option>
            <option
              v-for="zone in availableZones"
              :key="zone.id"
              :value="zone.id"
            >
              {{ zone.name }} ({{ zone.greenhouse?.name || "" }})
            </option>
          </select>
        </div>
      </div>

      <div
        v-if="currentStep === 1"
        class="space-y-4"
      >
        <div>
          <label class="block text-sm font-medium mb-2">Выберите растение</label>
          <select
            v-model="selectedPlantId"
            class="input-select w-full"
          >
            <option :value="null">
              Выберите растение
            </option>
            <option
              v-for="plant in availablePlants"
              :key="plant.id"
              :value="plant.id"
            >
              {{ plant.name }} {{ plant.variety ? `(${plant.variety})` : "" }}
            </option>
          </select>
        </div>
      </div>

      <div
        v-if="currentStep === 2"
        class="space-y-4"
      >
        <div>
          <label class="block text-sm font-medium mb-2">Выберите рецепт</label>
          <div class="flex gap-2 mb-3">
            <Button
              size="sm"
              :variant="recipeMode === 'select' ? 'primary' : 'secondary'"
              @click="recipeMode = 'select'"
            >
              Выбрать существующий
            </Button>
            <Button
              size="sm"
              :variant="recipeMode === 'create' ? 'primary' : 'secondary'"
              @click="recipeMode = 'create'"
            >
              Создать новый
            </Button>
          </div>

          <div v-if="recipeMode === 'select'">
            <select
              v-model="selectedRecipeId"
              class="input-select w-full"
              @change="onRecipeSelected"
            >
              <option :value="null">
                Выберите рецепт
              </option>
              <option
                v-for="recipe in availableRecipes"
                :key="recipe.id"
                :value="recipe.id"
              >
                {{ recipe.name }} ({{ recipe.phases_count || 0 }} фаз)
              </option>
            </select>
          </div>
          <div v-else>
            <RecipeCreateWizard
              :show="recipeMode === 'create'"
              @close="recipeMode = 'select'"
              @created="onRecipeCreated"
            />
          </div>
        </div>

        <div
          v-if="selectedRecipe"
          class="space-y-2"
        >
          <label class="block text-sm font-medium mb-2">Ревизия</label>
          <select
            v-model="selectedRevisionId"
            class="input-select w-full"
          >
            <option :value="null">
              Выберите ревизию
            </option>
            <option
              v-for="revision in availableRevisions"
              :key="revision.id"
              :value="revision.id"
            >
              {{ revision.revision_number ? `Rev ${revision.revision_number}` : 'Актуальная опубликованная ревизия' }}
              — {{ revision.description || "Без описания" }}
            </option>
          </select>
        </div>

        <div
          v-if="selectedRevision"
          class="mt-4 p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]"
        >
          <div class="text-sm font-semibold mb-2">
            {{ selectedRecipe.name }}
          </div>
          <div
            v-if="selectedRecipe.description"
            class="text-xs text-[color:var(--text-muted)] mb-3"
          >
            {{ selectedRecipe.description }}
          </div>
          <div class="text-xs font-medium mb-2">
            Фазы рецепта:
          </div>
          <div class="space-y-2">
            <div
              v-for="(phase, index) in selectedRevision.phases"
              :key="index"
              class="flex items-center justify-between p-2 rounded bg-[color:var(--bg-surface-strong)]"
            >
              <div>
                <div class="text-xs font-medium">
                  {{ phase.name || `Фаза ${index + 1}` }}
                </div>
                <div class="text-xs text-[color:var(--text-dim)]">
                  {{ phase.duration_days ?? (phase.duration_hours ? Math.round(phase.duration_hours / 24) : "-") }} дней
                </div>
              </div>
              <div class="text-xs text-[color:var(--text-muted)]">
                pH: {{ phase.ph_min ?? "-" }}–{{ phase.ph_max ?? "-" }} EC: {{ phase.ec_min ?? "-" }}–{{ phase.ec_max ?? "-" }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div
        v-if="currentStep === 3"
        class="space-y-5"
      >
        <section class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] space-y-4">
          <h3 class="text-sm font-semibold">Период цикла</h3>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <label class="text-sm">
              <span class="block font-medium mb-2">Дата начала</span>
              <input
                v-model="form.startedAt"
                type="datetime-local"
                class="input-field w-full"
                :min="minStartDate"
                required
              />
            </label>
            <label class="text-sm">
              <span class="block font-medium mb-2">Ожидаемая дата сбора (опционально)</span>
              <input
                v-model="form.expectedHarvestAt"
                type="date"
                class="input-field w-full"
                :min="form.startedAt ? form.startedAt.slice(0, 10) : undefined"
              />
            </label>
          </div>
        </section>
      </div>

      <div
        v-if="currentStep === 4"
        class="space-y-4"
      >
        <div class="flex flex-wrap items-center gap-2">
          <button
            v-for="item in automationTabs"
            :key="item.id"
            type="button"
            class="btn btn-outline h-9 px-3 text-xs"
            :class="item.id === automationTab ? 'border-[color:var(--accent-green)] text-[color:var(--text-primary)]' : ''"
            @click="automationTab = item.id"
          >
            {{ item.label }}
          </button>
        </div>

        <section
          v-if="automationTab === 1"
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
          v-else-if="automationTab === 2"
          class="space-y-3"
        >
          <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-4 space-y-4">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div class="text-sm font-semibold">Основной цикл полива, окна приготовления и рабочие объёмы контура</div>
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
                    <div class="text-sm font-semibold">По времени</div>
                    <div class="mt-1 text-xs">Запуск по расписанию без оценки влажности субстрата.</div>
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
                    <div class="text-sm font-semibold">Умный полив</div>
                    <div class="mt-1 text-xs">Перед стартом анализирует `SOIL_MOISTURE` и качество телеметрии.</div>
                  </button>
                </div>
              </div>

              <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3">
                <div class="text-xs text-[color:var(--text-dim)]">Цели из рецепта</div>
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
                  <div class="text-xs text-[color:var(--text-dim)]">Параметры цикла и контура</div>
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
                    v-model.number="soilMoistureSelectedNodeChannelId"
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
                  :disabled="soilMoistureBindingLoading || !soilMoistureSelectedNodeChannelId"
                  @click="saveSoilMoistureBinding"
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
                  <div class="text-sm font-semibold">Расширенные runtime-настройки</div>
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

              <div
                class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3"
              >
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

      <div
        v-if="currentStep === 5"
        class="space-y-4"
      >
        <div class="flex items-start justify-between gap-3">
          <div>
            <h3 class="text-sm font-semibold">Калибровка насосов</h3>
            <p class="text-xs text-[color:var(--text-muted)] mt-1">
              Используется тот же calibration flow, что и в setup wizard. Сохранённые значения берутся только из backend `pump_calibrations`.
            </p>
          </div>
          <Button
            size="sm"
            variant="primary"
            :disabled="!form.zoneId || loadingPumpCalibrationRun || loadingPumpCalibrationSave"
            @click="openPumpCalibrationModal"
          >
            Открыть калибровку насосов
          </Button>
        </div>

        <div
          v-if="isZoneDevicesLoading"
          class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] text-sm text-[color:var(--text-muted)]"
        >
          Загружаю насосы зоны...
        </div>

        <div
          v-else-if="zoneDevicesError"
          class="p-4 rounded-lg bg-[color:var(--badge-danger-bg)] border border-[color:var(--badge-danger-border)] text-sm text-[color:var(--badge-danger-text)] space-y-2"
        >
          <div>{{ zoneDevicesError }}</div>
          <Button
            size="sm"
            variant="secondary"
            @click="refreshPumpCalibrationData(true)"
          >
            Повторить
          </Button>
        </div>

        <div
          v-else-if="pumpChannels.length === 0"
          class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] text-sm text-[color:var(--text-muted)] space-y-2"
        >
          <div>В зоне не найдены дозирующие насосы для calibration flow.</div>
          <Button
            size="sm"
            variant="secondary"
            @click="refreshPumpCalibrationData(true)"
          >
            Обновить список
          </Button>
        </div>

        <div
          v-else
          class="space-y-3"
        >
          <div
            class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] space-y-3"
          >
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div class="text-sm font-medium">
                  Сохранено {{ calibratedChannels.length }} из {{ mappedPumpComponents.length }} ожидаемых pump calibration.
                </div>
                <div class="text-xs text-[color:var(--text-muted)] mt-1">
                  Launch wizard не записывает `ml/sec` локально. Сначала сохраните калибровки через общую модалку, затем readiness автоматически разрешит запуск.
                </div>
              </div>
              <Button
                size="sm"
                variant="secondary"
                :disabled="loadingPumpCalibrationRun || loadingPumpCalibrationSave"
                @click="refreshPumpCalibrationData(true)"
              >
                Обновить статус
              </Button>
            </div>

            <div class="flex flex-wrap gap-2">
              <span
                v-for="item in mappedPumpComponents"
                :key="item.component"
                class="inline-flex items-center rounded-full border px-2.5 py-1 text-xs"
                :class="item.calibrated
                  ? 'border-[color:var(--badge-success-border)] bg-[color:var(--badge-success-bg)] text-[color:var(--badge-success-text)]'
                  : 'border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] text-[color:var(--badge-warning-text)]'"
              >
                {{ item.label }}: {{ item.calibrated ? 'готово' : 'не сохранено' }}
              </span>
            </div>
          </div>

          <div
            v-if="missingPumpComponents.length > 0"
            class="p-3 rounded-lg bg-[color:var(--badge-warning-bg)] border border-[color:var(--badge-warning-border)] text-sm text-[color:var(--badge-warning-text)]"
          >
            Для correction runtime ещё не сохранены: {{ missingPumpComponents.join(', ') }}.
          </div>

          <div
            v-if="calibratedChannels.length > 0"
            class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]"
          >
            <div class="text-xs text-[color:var(--text-dim)] mb-2">Уже сохранено</div>
            <div class="space-y-1">
              <div
                v-for="channel in calibratedChannels"
                :key="channel.id"
                class="text-sm text-[color:var(--text-primary)]"
              >
                {{ channel.label }}: {{ channel.calibration?.ml_per_sec ?? '-' }} мл/сек
              </div>
            </div>
          </div>
        </div>
      </div>

      <div
        v-if="currentStep === 6"
        class="space-y-4"
      >
        <h3 class="text-sm font-semibold mb-1">Предпросмотр запуска</h3>

        <ReadinessChecklist
          :zone-id="form.zoneId"
          :readiness="zoneReadiness"
          :loading="zoneReadinessLoading"
        />

        <div class="space-y-3">
          <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
            <div class="text-xs text-[color:var(--text-dim)] mb-1">Зона</div>
            <div class="text-sm font-medium">{{ zoneName || `Зона #${form.zoneId}` }}</div>
          </div>

          <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
            <div class="text-xs text-[color:var(--text-dim)] mb-1">Рецепт</div>
            <div class="text-sm font-medium">{{ selectedRecipe?.name || "Не выбран" }}</div>
            <div
              v-if="totalDurationDays > 0"
              class="text-xs text-[color:var(--text-muted)] mt-1"
            >
              Оценочная длительность: {{ Math.round(totalDurationDays) }} дней
            </div>
          </div>

          <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
            <div class="text-xs text-[color:var(--text-dim)] mb-1">Период</div>
            <div class="text-sm font-medium">Старт: {{ formatDateTime(form.startedAt) }}</div>
            <div
              v-if="form.expectedHarvestAt"
              class="text-xs text-[color:var(--text-muted)] mt-1"
            >
              Сбор: {{ formatDate(form.expectedHarvestAt) }}
            </div>
          </div>

          <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
            <div class="text-xs text-[color:var(--text-dim)] mb-1">Автоматика</div>
            <div class="text-sm font-medium">
              Автоматика: pH {{ waterForm.targetPh }}, EC {{ waterForm.targetEc }}, система {{ waterForm.systemType }}
            </div>
          </div>

          <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
            <div class="text-xs text-[color:var(--text-dim)] mb-1">Полив</div>
            <div class="text-sm font-medium">
              {{ irrigationStrategyLabel }} · {{ waterForm.systemType }}
            </div>
            <div class="text-xs text-[color:var(--text-muted)] mt-1">
              {{ irrigationScheduleSummary }}
            </div>
            <div
              v-if="tanksCount === 2"
              class="text-xs text-[color:var(--text-muted)] mt-1"
            >
              Баки: {{ waterForm.cleanTankFillL }} / {{ waterForm.nutrientTankTargetL }} л, партия {{ waterForm.irrigationBatchL }} л
            </div>
            <div
              v-if="isSmartIrrigation"
              class="text-xs text-[color:var(--text-muted)] mt-1"
            >
              Датчик влажности: {{ soilMoistureBoundNodeChannelId ? `node_channel_id ${soilMoistureBoundNodeChannelId}` : 'не привязан' }}
            </div>
          </div>

          <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
            <div class="text-xs text-[color:var(--text-dim)] mb-1">Калибровка насосов</div>
            <div class="text-sm font-medium">
              {{ calibratedChannels.length }} сохранено, {{ missingPumpComponents.length }} требуют внимания
            </div>
          </div>

          <div
            v-if="selectedRevision"
            class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]"
          >
            <div class="text-xs text-[color:var(--text-dim)] mb-2">План фаз:</div>
            <div class="space-y-2">
              <div
                v-for="(phase, index) in selectedRevision.phases"
                :key="index"
                class="flex items-center justify-between text-xs"
              >
                <span class="font-medium">{{ phase.name || `Фаза ${index + 1}` }}</span>
                <span class="text-[color:var(--text-muted)]">{{ phase.duration_days ?? (phase.duration_hours ? Math.round(phase.duration_hours / 24) : "-") }} дней</span>
              </div>
            </div>
          </div>
        </div>

        <div
          v-if="validationErrors.length > 0"
          class="p-3 rounded-lg bg-[color:var(--badge-danger-bg)] border border-[color:var(--badge-danger-border)]"
        >
          <div class="text-sm font-medium text-[color:var(--badge-danger-text)] mb-1">
            Ошибки валидации:
          </div>
          <ul class="text-xs text-[color:var(--badge-danger-text)] list-disc list-inside">
            <li
              v-for="validationError in validationErrors"
              :key="validationError"
            >
              {{ validationError }}
            </li>
          </ul>
        </div>
      </div>

      <div
        v-if="error && validationErrors.length === 0"
        class="mt-4 p-3 rounded-lg bg-[color:var(--badge-danger-bg)] border border-[color:var(--badge-danger-border)]"
      >
        <div class="text-sm text-[color:var(--badge-danger-text)]">
          {{ error }}
        </div>
        <ul
          v-if="errorDetails.length > 0"
          class="mt-2 text-xs text-[color:var(--badge-danger-text)] list-disc list-inside space-y-1"
        >
          <li
            v-for="detail in errorDetails"
            :key="detail"
          >
            {{ detail }}
          </li>
        </ul>
      </div>
    </ErrorBoundary>

    <template #footer>
      <div class="flex items-center justify-between w-full">
        <Button
          v-if="currentStep > 0"
          variant="secondary"
          :disabled="loading"
          @click="prevStep"
        >
          Назад
        </Button>
        <div v-else></div>

        <div class="flex gap-2">
          <Button
            variant="secondary"
            :disabled="loading"
            @click="handleClose"
          >
            Отмена
          </Button>
          <Button
            v-if="currentStep < steps.length - 1"
            data-testid="growth-cycle-wizard-next"
            :disabled="loading || !canProceed"
            @click="nextStep"
          >
            Далее
          </Button>
          <Button
            v-else
            data-testid="growth-cycle-wizard-submit"
            :disabled="!canSubmit || loading"
            @click="onSubmit"
          >
            {{ loading ? "Создание..." : "Запустить цикл" }}
          </Button>
        </div>
      </div>

      <div
        v-if="nextStepBlockedReason && currentStep < steps.length - 1"
        class="mt-2 text-xs text-[color:var(--badge-danger-text)]"
      >
        {{ nextStepBlockedReason }}
      </div>
    </template>
  </Modal>

  <PumpCalibrationModal
    v-if="showPumpCalibrationModal"
    :show="showPumpCalibrationModal"
    :zone-id="form.zoneId"
    :devices="zoneDevices"
    :loading-run="loadingPumpCalibrationRun"
    :loading-save="loadingPumpCalibrationSave"
    :save-success-seq="pumpCalibrationSaveSeq"
    :run-success-seq="pumpCalibrationRunSeq"
    :last-run-token="pumpCalibrationLastRunToken"
    @close="closePumpCalibrationModal"
    @start="startPumpCalibration"
    @save="savePumpCalibration"
  />
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useApi } from "@/composables/useApi";
import { useToast } from "@/composables/useToast";
import { useZones } from "@/composables/useZones";
import Modal from "@/Components/Modal.vue";
import Button from "@/Components/Button.vue";
import ErrorBoundary from "@/Components/ErrorBoundary.vue";
import ReadinessChecklist from "@/Components/GrowCycle/ReadinessChecklist.vue";
import PumpCalibrationModal from "@/Components/PumpCalibrationModal.vue";
import RecipeCreateWizard from "@/Components/RecipeCreateWizard.vue";
import { usePumpCalibration } from "@/composables/usePumpCalibration";
import { usePumpCalibrationActions } from "@/composables/usePumpCalibrationActions";
import { useGrowthCycleWizard, type GrowthCycleWizardProps, type GrowthCycleWizardEmit } from "@/composables/useGrowthCycleWizard";
import type { PumpCalibrationComponent, PumpCalibrationRunPayload, PumpCalibrationSavePayload } from "@/types/Calibration";

interface Props extends GrowthCycleWizardProps {
  show: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  show: false,
  zoneId: undefined,
  zoneName: "",
});

const emit = defineEmits<{
  close: [];
  submit: [
    data: {
      zoneId: number;
      cycleId?: number;
      recipeId?: number;
      recipeRevisionId?: number;
      startedAt: string;
      expectedHarvestAt?: string;
    },
  ];
}>();

const { api } = useApi();
const { showToast } = useToast();
const { fetchZones } = useZones();
const wizardEmit = emit as GrowthCycleWizardEmit;

const {
  currentStep,
  recipeMode,
  loading,
  error,
  errorDetails,
  validationErrors,
  form,
  climateForm,
  waterForm,
  lightingForm,
  availableZones,
  availablePlants,
  availableRecipes,
  selectedRecipe,
  selectedRecipeId,
  selectedRevisionId,
  selectedPlantId,
  availableRevisions,
  selectedRevision,
  steps,
  wizardTitle,
  minStartDate,
  totalDurationDays,
  tanksCount,
  canSubmit,
  canProceed,
  nextStepBlockedReason,
  zoneDevices,
  isZoneDevicesLoading,
  zoneDevicesError,
  zoneReadiness,
  zoneReadinessLoading,
  soilMoistureChannelCandidates,
  soilMoistureBindingLoading,
  soilMoistureBindingError,
  soilMoistureBindingSavedAt,
  soilMoistureSelectedNodeChannelId,
  soilMoistureBoundNodeChannelId,
  formatDateTime,
  formatDate,
  onZoneSelected,
  onRecipeSelected,
  onRecipeCreated,
  fetchZoneDevices,
  loadZoneReadiness,
  saveSoilMoistureBinding,
  nextStep,
  prevStep,
  onSubmit,
  handleClose,
} = useGrowthCycleWizard({
  props,
  emit: wizardEmit,
  api,
  showToast,
  fetchZones,
});

const automationTab = ref<1 | 2 | 3>(1);
const automationTabs = [
  { id: 1, label: "Климат" },
  { id: 2, label: "Водный узел" },
  { id: 3, label: "Досветка" },
] as const;

const showPumpCalibrationModal = ref(false);
const pumpCalibrationActions = usePumpCalibrationActions({
  api,
  getZoneId: () => form.value.zoneId,
  showToast,
  runSuccessMessage: "Запуск калибровки отправлен. После прогона сохраните фактический объём.",
  saveSuccessMessage: "Калибровка насоса сохранена.",
  onSaveSuccess: async () => {
    await refreshPumpCalibrationData(true);
  },
})
const loadingPumpCalibrationRun = pumpCalibrationActions.loadingRun;
const loadingPumpCalibrationSave = pumpCalibrationActions.loadingSave;
const pumpCalibrationSaveSeq = pumpCalibrationActions.saveSeq;
const pumpCalibrationRunSeq = pumpCalibrationActions.runSeq;
const pumpCalibrationLastRunToken = pumpCalibrationActions.lastRunToken;

const componentLabels: Record<PumpCalibrationComponent, string> = {
  npk: "NPK",
  calcium: "Calcium",
  magnesium: "Magnesium",
  micro: "Micro",
  ph_up: "pH Up",
  ph_down: "pH Down",
};

const {
  componentOptions,
  pumpChannels,
  calibratedChannels,
  autoComponentMap,
  channelById,
  refreshDbCalibrations,
} = usePumpCalibration({
  get show() {
    return showPumpCalibrationModal.value;
  },
  get zoneId() {
    return form.value.zoneId;
  },
  get devices() {
    return zoneDevices.value;
  },
  get saveSuccessSeq() {
    return pumpCalibrationSaveSeq.value;
  },
  get runSuccessSeq() {
    return pumpCalibrationRunSeq.value;
  },
  get lastRunToken() {
    return pumpCalibrationLastRunToken.value;
  },
});

const mappedPumpComponents = computed(() => {
  return componentOptions
    .map((option) => {
      const channelId = autoComponentMap.value[option.value];
      const channel = channelId ? channelById.value.get(channelId) || null : null;
      const calibrated = Number(channel?.calibration?.ml_per_sec ?? 0) > 0;

      return {
        component: option.value,
        label: componentLabels[option.value],
        calibrated,
      };
    })
    .filter((item) => Boolean(autoComponentMap.value[item.component]));
});

const missingPumpComponents = computed(() => {
  return mappedPumpComponents.value
    .filter((item) => !item.calibrated)
    .map((item) => item.label);
});

const isTimedIrrigation = computed(() => waterForm.value.irrigationDecisionStrategy !== "smart_soil_v1");
const isSmartIrrigation = computed(() => waterForm.value.irrigationDecisionStrategy === "smart_soil_v1");
const irrigationStrategyLabel = computed(() => {
  return isSmartIrrigation.value ? "Умный полив по SOIL_MOISTURE" : "Полив по расписанию";
});
const irrigationStrategyDescription = computed(() => {
  return isSmartIrrigation.value
    ? "Перед стартом оценивается влажность субстрата и качество телеметрии; без привязки датчика стратегия не сработает корректно."
    : "Полив стартует по временным окнам цикла без предварительной оценки влажности субстрата.";
});
const irrigationRecipeSummary = computed(() => {
  return `Рецепт задаёт базовые launch-targets: pH ${waterForm.value.targetPh}, EC ${waterForm.value.targetEc}.`;
});
const irrigationScheduleSummary = computed(() => {
  return `Стартовая схема полива: каждые ${waterForm.value.intervalMinutes} мин на ${waterForm.value.durationSeconds} сек.`;
});
const waterAdvancedSummary = computed(() => {
  const diagnosticsState = waterForm.value.diagnosticsEnabled ? "диагностика включена" : "диагностика выключена";
  const refillState = `${waterForm.value.refillDurationSeconds}с / timeout ${waterForm.value.refillTimeoutSeconds}с`;
  const solutionChangeState = waterForm.value.solutionChangeEnabled
    ? `смена раствора каждые ${waterForm.value.solutionChangeIntervalMinutes} мин`
    : "смена раствора отключена";

  return `${diagnosticsState}, refill ${refillState}, ${solutionChangeState}.`;
});

async function refreshPumpCalibrationData(force = false): Promise<void> {
  await fetchZoneDevices(force);
  await refreshDbCalibrations();
  if (form.value.zoneId) {
    await loadZoneReadiness(form.value.zoneId);
  }
}

function openPumpCalibrationModal(): void {
  if (!form.value.zoneId) {
    showToast("Сначала выберите зону.", "warning");
    return;
  }

  showPumpCalibrationModal.value = true;
}

function closePumpCalibrationModal(): void {
  showPumpCalibrationModal.value = false;
}

async function startPumpCalibration(payload: PumpCalibrationRunPayload): Promise<void> {
  await pumpCalibrationActions.startPumpCalibration(payload);
}

async function savePumpCalibration(payload: PumpCalibrationSavePayload): Promise<void> {
  await pumpCalibrationActions.savePumpCalibration(payload);
}

watch(
  () => [props.show, currentStep.value, form.value.zoneId],
  ([isOpen, step, zoneId]) => {
    if (!isOpen || !zoneId || (step !== 5 && step !== 6)) {
      return;
    }

    void refreshPumpCalibrationData(step === 6);
  },
  { immediate: true },
);
</script>
