<template>
  <Modal
    :open="show"
    :title="wizardTitle"
    size="large"
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
                {{ recipe.name }} ({{ recipe.published_revisions?.[0]?.phases?.length || 0 }} фаз)
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
              Rev {{ revision.revision_number }} — {{ revision.description || "Без описания" }}
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

        <section class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] space-y-4">
          <h3 class="text-sm font-semibold">Питательный раствор</h3>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <label class="text-sm">
              <span class="flex items-center gap-2 font-medium mb-2">
                target pH
                <span
                  v-if="isLogicFieldFromRecipe('ph_target')"
                  class="px-1.5 py-0.5 rounded text-[10px] bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)]"
                >из рецепта</span>
                <span
                  v-else-if="isLogicFieldOverridden('ph_target')"
                  class="px-1.5 py-0.5 rounded text-[10px] bg-[color:var(--badge-warning-bg)] text-[color:var(--badge-warning-text)]"
                >переопределено</span>
              </span>
              <input
                v-model.number="form.logic.ph_target"
                type="number"
                min="4"
                max="9"
                step="0.1"
                class="input-field w-full"
              />
            </label>
            <label class="text-sm">
              <span class="font-medium mb-2 block">pH min</span>
              <input
                v-model.number="form.logic.ph_min"
                type="number"
                min="4"
                max="9"
                step="0.1"
                class="input-field w-full"
              />
            </label>
            <label class="text-sm">
              <span class="font-medium mb-2 block">pH max</span>
              <input
                v-model.number="form.logic.ph_max"
                type="number"
                min="4"
                max="9"
                step="0.1"
                class="input-field w-full"
              />
            </label>
            <label class="text-sm">
              <span class="flex items-center gap-2 font-medium mb-2">
                target EC
                <span
                  v-if="isLogicFieldFromRecipe('ec_target')"
                  class="px-1.5 py-0.5 rounded text-[10px] bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)]"
                >из рецепта</span>
                <span
                  v-else-if="isLogicFieldOverridden('ec_target')"
                  class="px-1.5 py-0.5 rounded text-[10px] bg-[color:var(--badge-warning-bg)] text-[color:var(--badge-warning-text)]"
                >переопределено</span>
              </span>
              <input
                v-model.number="form.logic.ec_target"
                type="number"
                min="0"
                max="10"
                step="0.01"
                class="input-field w-full"
              />
            </label>
            <label class="text-sm">
              <span class="font-medium mb-2 block">EC min</span>
              <input
                v-model.number="form.logic.ec_min"
                type="number"
                min="0"
                max="10"
                step="0.01"
                class="input-field w-full"
              />
            </label>
            <label class="text-sm">
              <span class="font-medium mb-2 block">EC max</span>
              <input
                v-model.number="form.logic.ec_max"
                type="number"
                min="0"
                max="10"
                step="0.01"
                class="input-field w-full"
              />
            </label>
          </div>
        </section>

        <section class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] space-y-4">
          <h3 class="text-sm font-semibold">Система полива</h3>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <label class="text-sm">
              <span class="flex items-center gap-2 font-medium mb-2">
                Тип системы
                <span
                  v-if="isLogicFieldFromRecipe('systemType')"
                  class="px-1.5 py-0.5 rounded text-[10px] bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)]"
                >из рецепта</span>
                <span
                  v-else-if="isLogicFieldOverridden('systemType')"
                  class="px-1.5 py-0.5 rounded text-[10px] bg-[color:var(--badge-warning-bg)] text-[color:var(--badge-warning-text)]"
                >переопределено</span>
              </span>
              <select
                v-model="form.logic.systemType"
                class="input-select w-full"
              >
                <option value="drip">drip</option>
                <option value="substrate_trays">substrate_trays</option>
                <option value="nft">nft</option>
              </select>
            </label>

            <label class="text-sm">
              <span class="font-medium mb-2 block">Количество баков</span>
              <input
                :value="tanksCount"
                type="number"
                class="input-field w-full"
                readonly
              />
            </label>

            <label class="text-sm">
              <span class="flex items-center gap-2 font-medium mb-2">
                Интервал (мин)
                <span
                  v-if="isLogicFieldFromRecipe('intervalMinutes')"
                  class="px-1.5 py-0.5 rounded text-[10px] bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)]"
                >из рецепта</span>
              </span>
              <input
                v-model.number="form.logic.intervalMinutes"
                type="number"
                min="5"
                max="1440"
                class="input-field w-full"
              />
            </label>

            <label class="text-sm">
              <span class="flex items-center gap-2 font-medium mb-2">
                Длительность (сек)
                <span
                  v-if="isLogicFieldFromRecipe('durationSeconds')"
                  class="px-1.5 py-0.5 rounded text-[10px] bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)]"
                >из рецепта</span>
              </span>
              <input
                v-model.number="form.logic.durationSeconds"
                type="number"
                min="10"
                max="3600"
                class="input-field w-full"
              />
            </label>

            <template v-if="tanksCount === 2">
              <label class="text-sm">
                <span class="font-medium mb-2 block">Объём чистого бака (л)</span>
                <input
                  v-model.number="form.logic.cleanTankFillL"
                  type="number"
                  min="1"
                  max="5000"
                  class="input-field w-full"
                />
              </label>

              <label class="text-sm">
                <span class="font-medium mb-2 block">Объём питательного бака (л)</span>
                <input
                  v-model.number="form.logic.nutrientTankTargetL"
                  type="number"
                  min="1"
                  max="5000"
                  class="input-field w-full"
                />
              </label>

              <label class="text-sm">
                <span class="font-medium mb-2 block">Объём партии полива (л)</span>
                <input
                  v-model.number="form.logic.irrigationBatchL"
                  type="number"
                  min="0.1"
                  max="500"
                  step="0.1"
                  class="input-field w-full"
                />
              </label>
            </template>
          </div>
        </section>

        <section class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] space-y-4">
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-semibold">Климат</h3>
            <label class="inline-flex items-center gap-2 text-sm">
              <input
                v-model="form.logic.climateEnabled"
                type="checkbox"
              />
              Включен
            </label>
          </div>
          <div
            v-if="form.logic.climateEnabled"
            class="grid grid-cols-1 md:grid-cols-2 gap-4"
          >
            <label class="text-sm">
              <span class="font-medium mb-2 block">Температура день (°C)</span>
              <input
                v-model.number="form.logic.dayTemp"
                type="number"
                min="10"
                max="40"
                step="0.1"
                class="input-field w-full"
              />
            </label>
            <label class="text-sm">
              <span class="font-medium mb-2 block">Температура ночь (°C)</span>
              <input
                v-model.number="form.logic.nightTemp"
                type="number"
                min="10"
                max="40"
                step="0.1"
                class="input-field w-full"
              />
            </label>
            <label class="text-sm">
              <span class="font-medium mb-2 block">Влажность день (%)</span>
              <input
                v-model.number="form.logic.dayHumidity"
                type="number"
                min="20"
                max="95"
                class="input-field w-full"
              />
            </label>
            <label class="text-sm">
              <span class="font-medium mb-2 block">Влажность ночь (%)</span>
              <input
                v-model.number="form.logic.nightHumidity"
                type="number"
                min="20"
                max="95"
                class="input-field w-full"
              />
            </label>
          </div>
        </section>

        <section class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] space-y-4">
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-semibold">Освещение</h3>
            <label class="inline-flex items-center gap-2 text-sm">
              <input
                v-model="form.logic.lightingEnabled"
                type="checkbox"
              />
              Включено
            </label>
          </div>
          <div
            v-if="form.logic.lightingEnabled"
            class="grid grid-cols-1 md:grid-cols-3 gap-4"
          >
            <label class="text-sm">
              <span class="font-medium mb-2 block">Часов света</span>
              <input
                v-model.number="form.logic.hoursOn"
                type="number"
                min="1"
                max="24"
                class="input-field w-full"
              />
            </label>
            <label class="text-sm">
              <span class="font-medium mb-2 block">Старт (HH:MM)</span>
              <input
                v-model="form.logic.scheduleStart"
                type="time"
                class="input-field w-full"
              />
            </label>
            <label class="text-sm">
              <span class="font-medium mb-2 block">Конец (HH:MM)</span>
              <input
                v-model="form.logic.scheduleEnd"
                type="time"
                class="input-field w-full"
              />
            </label>
          </div>
        </section>
      </div>

      <div
        v-if="currentStep === 4"
        class="space-y-4"
      >
        <div class="flex items-start justify-between gap-3">
          <div>
            <h3 class="text-sm font-semibold">Калибровка насосов</h3>
            <p class="text-xs text-[color:var(--text-muted)] mt-1">
              Укажите расход каждого дозирующего насоса в ml/sec.
            </p>
          </div>
          <Button
            size="sm"
            variant="secondary"
            @click="form.calibrationSkipped = !form.calibrationSkipped"
          >
            {{ form.calibrationSkipped ? "Вернуть калибровку" : "Пропустить шаг" }}
          </Button>
        </div>

        <div
          v-if="form.calibrationSkipped"
          class="p-3 rounded-lg bg-[color:var(--badge-warning-bg)] border border-[color:var(--badge-warning-border)] text-sm text-[color:var(--badge-warning-text)]"
        >
          Калибровка пропущена. Коррекция EC может работать некорректно.
        </div>

        <div
          v-if="isZoneChannelsLoading"
          class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] text-sm text-[color:var(--text-muted)]"
        >
          Загружаю каналы насосов...
        </div>

        <div
          v-else-if="zoneChannelsError"
          class="p-4 rounded-lg bg-[color:var(--badge-danger-bg)] border border-[color:var(--badge-danger-border)] text-sm text-[color:var(--badge-danger-text)] space-y-2"
        >
          <div>{{ zoneChannelsError }}</div>
          <Button
            size="sm"
            variant="secondary"
            @click="fetchZoneChannels(true)"
          >
            Повторить
          </Button>
        </div>

        <div
          v-else-if="!hasCalibrationChannels"
          class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] text-sm text-[color:var(--text-muted)] space-y-2"
        >
          <div>Насосы не найдены, настройте привязку нод.</div>
          <Button
            size="sm"
            variant="secondary"
            @click="fetchZoneChannels(true)"
          >
            Обновить список
          </Button>
        </div>

        <div
          v-else
          class="space-y-2"
        >
          <div
            v-for="entry in form.calibrations"
            :key="entry.node_channel_id"
            class="p-3 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]"
          >
            <div class="grid grid-cols-1 md:grid-cols-[1fr_160px_130px] gap-3 items-end">
              <div>
                <div class="flex items-center gap-2">
                  <span class="inline-flex items-center justify-center h-6 px-2 rounded-md bg-[color:var(--bg-surface-strong)] text-xs font-semibold">
                    {{ getCalibrationComponentLabel(entry.component) }}
                  </span>
                  <span class="text-sm font-medium">{{ entry.channel_label }}</span>
                </div>
              </div>

              <label class="text-sm">
                <span class="font-medium mb-1 block">ml/sec</span>
                <input
                  v-model.number="entry.ml_per_sec"
                  type="number"
                  min="0.01"
                  max="100"
                  step="0.01"
                  class="input-field w-full"
                  :disabled="entry.skip"
                />
              </label>

              <label class="inline-flex items-center gap-2 text-sm h-10">
                <input
                  v-model="entry.skip"
                  type="checkbox"
                />
                Пропустить насос
              </label>
            </div>
          </div>
        </div>
      </div>

      <div
        v-if="currentStep === 5"
        class="space-y-4"
      >
        <h3 class="text-sm font-semibold mb-1">Предпросмотр запуска</h3>

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
            <div class="text-xs text-[color:var(--text-dim)] mb-1">Цели раствора</div>
            <div class="text-sm font-medium">
              pH {{ form.logic.ph_target }} ({{ form.logic.ph_min }}–{{ form.logic.ph_max }}),
              EC {{ form.logic.ec_target }} ({{ form.logic.ec_min }}–{{ form.logic.ec_max }})
            </div>
          </div>

          <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
            <div class="text-xs text-[color:var(--text-dim)] mb-1">Полив</div>
            <div class="text-sm font-medium">
              {{ form.logic.systemType }}, каждые {{ form.logic.intervalMinutes }} мин, {{ form.logic.durationSeconds }} сек
            </div>
            <div
              v-if="tanksCount === 2"
              class="text-xs text-[color:var(--text-muted)] mt-1"
            >
              Баки: {{ form.logic.cleanTankFillL }} / {{ form.logic.nutrientTankTargetL }} л, партия {{ form.logic.irrigationBatchL }} л
            </div>
          </div>

          <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
            <div class="text-xs text-[color:var(--text-dim)] mb-1">Калибровка насосов</div>
            <div class="text-sm font-medium">
              <span v-if="form.calibrationSkipped">Пропущена</span>
              <span v-else>
                {{ form.calibrations.filter((entry) => !entry.skip && entry.ml_per_sec > 0).length }} насосов будет сохранено
              </span>
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
        v-if="error"
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
            :disabled="loading || !canProceed"
            @click="nextStep"
          >
            Далее
          </Button>
          <Button
            v-else
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
</template>

<script setup lang="ts">
import { useApi } from "@/composables/useApi";
import { useToast } from "@/composables/useToast";
import { useZones } from "@/composables/useZones";
import Modal from "@/Components/Modal.vue";
import Button from "@/Components/Button.vue";
import ErrorBoundary from "@/Components/ErrorBoundary.vue";
import RecipeCreateWizard from "@/Components/RecipeCreateWizard.vue";
import { useGrowthCycleWizard, type GrowthCycleWizardProps, type GrowthCycleWizardEmit } from "@/composables/useGrowthCycleWizard";

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
  isZoneChannelsLoading,
  zoneChannelsError,
  hasCalibrationChannels,
  getCalibrationComponentLabel,
  isLogicFieldOverridden,
  isLogicFieldFromRecipe,
  formatDateTime,
  formatDate,
  onZoneSelected,
  onRecipeSelected,
  onRecipeCreated,
  fetchZoneChannels,
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
</script>
