<template>
  <div class="space-y-3">
    <!-- ── 1. Культура ────────────────────────────────────────── -->
    <div
      v-if="!hidePlantSelect"
      class="rounded-md border border-[color:var(--border-muted)] p-2.5 space-y-2"
    >
      <div class="text-[12px] font-bold uppercase tracking-[0.16em] text-[color:var(--text-muted)]">
        Культура
      </div>

      <div
        v-if="plantMode === 'select'"
        class="grid gap-2 md:grid-cols-[1fr_auto]"
      >
        <select
          id="recipe-plant"
          v-model.number="form.plant_id"
          class="input-field"
          :disabled="plantsLoading"
        >
          <option :value="null">
            Выберите культуру
          </option>
          <option
            v-for="plant in plants"
            :key="plant.id"
            :value="plant.id"
          >
            {{ plant.name }}
          </option>
        </select>
        <Button
          size="sm"
          variant="secondary"
          @click="plantMode = 'create'"
        >
          Создать
        </Button>
      </div>

      <div
        v-else
        class="space-y-2"
      >
        <div class="grid grid-cols-1 md:grid-cols-3 gap-2">
          <div>
            <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Название растения</label>
            <input
              v-model="newPlantName"
              class="input-field"
              placeholder="Томат Черри"
            />
          </div>
          <div>
            <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Вид (species)</label>
            <input
              v-model="newPlantSpecies"
              class="input-field"
              placeholder="Solanum lycopersicum"
            />
          </div>
          <div>
            <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Сорт (variety)</label>
            <input
              v-model="newPlantVariety"
              class="input-field"
              placeholder="Cherry"
            />
          </div>
        </div>
        <div class="flex gap-2">
          <Button
            size="sm"
            :disabled="!newPlantName.trim() || creatingPlant"
            @click="createPlant"
          >
            {{ creatingPlant ? 'Создание...' : 'Создать растение' }}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            @click="plantMode = 'select'"
          >
            Отмена
          </Button>
        </div>
      </div>
    </div>
    <div
      v-else
      class="rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-muted)] px-2.5 py-1.5 text-xs text-[color:var(--text-muted)]"
    >
      Культура: <span class="font-semibold text-[color:var(--text-primary)]">{{ lockedPlantLabel || 'Выбрана на предыдущем шаге' }}</span>
    </div>

    <!-- ── 2. Название рецепта ────────────────────────────────── -->
    <div>
      <div class="text-[12px] text-[color:var(--text-primary)] font-medium mb-1">
        Название рецепта
      </div>
      <div
        class="text-xs font-semibold text-[color:var(--text-primary)]"
        data-testid="recipe-name-display"
      >
        {{ recipeName }}
      </div>
      <input
        id="recipe-description"
        v-model="recipeLabel"
        data-testid="recipe-name-input"
        class="input-field mt-1"
        placeholder="Veg+Bloom, зима 2026..."
      />
    </div>

    <!-- ── 3. Система подготовки раствора и полива ─────────────── -->
    <div class="rounded-md border border-[color:var(--border-muted)] p-3 space-y-2">
      <div class="text-[12px] font-bold uppercase tracking-[0.16em] text-[color:var(--text-muted)]">
        Система подготовки раствора и полива
      </div>
      <div class="max-w-lg">
        <select
          v-model="recipeIrrigationMode"
          class="input-field w-full"
        >
          <option value="SUBSTRATE">
            Проточная (2 бака)
          </option>
          <option value="RECIRC">
            Рециркуляция (3 бака)
          </option>
        </select>
        <div class="mt-1.5 text-[12px] text-[color:var(--text-muted)] leading-snug space-y-0.5">
          <p v-if="recipeIrrigationMode === 'SUBSTRATE'">
            <span class="font-semibold text-[color:var(--text-primary)]">2 бака</span> — для субстратного полива (кокос, минвата, грунт):
            чистая вода → бак раствора → пролив → дренаж в слив
          </p>
          <p v-else>
            <span class="font-semibold text-[color:var(--text-primary)]">3 бака</span> — для гидропоники NFT, DWC и подобных:
            чистая вода → бак раствора → циркуляция по корням → возвратный бак → обратно в раствор
          </p>
          <p class="text-[color:var(--text-dim)]">
            Режим не меняется между фазами — это характеристика установки
          </p>
        </div>
      </div>
    </div>

    <!-- ── 4. Фазы ────────────────────────────────────────────── -->
    <div class="text-xs font-semibold">
      Фазы роста
    </div>

    <div class="space-y-3">
      <section
        v-for="(phase, index) in sortedPhases"
        :key="phase.id || index"
        :data-testid="`phase-item-${index}`"
        class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-3 space-y-2.5"
      >
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-end gap-4">
            <div>
              <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Название</label>
              <input
                v-model="phase.name"
                :data-testid="`phase-name-input-${index}`"
                class="input-field !w-40"
                placeholder="VEG / BLOOM"
              />
            </div>
            <div>
              <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Длительность (дни:часы)</label>
              <input
                :value="durationDisplay(phase)"
                :data-testid="`phase-duration-input-${index}`"
                type="text"
                placeholder="0 : 00"
                class="input-field !w-24 text-center tracking-widest"
                @change="setDurationFromString(phase, ($event.target as HTMLInputElement).value)"
              />
            </div>
            <div>
              <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Раздельно день / ночь</label>
              <label class="md-switch">
                <input
                  v-model="phase.day_night_enabled"
                  type="checkbox"
                />
                <span class="md-switch__track">
                  <span class="md-switch__thumb"></span>
                </span>
                <span class="md-switch__label">{{ phase.day_night_enabled ? 'Вкл' : 'Выкл' }}</span>
              </label>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <Button
              v-if="form.phases.length > 1"
              type="button"
              size="sm"
              variant="secondary"
              @click="$emit('remove-phase', form.phases.indexOf(phase))"
            >
              Удалить
            </Button>
            <div class="flex flex-col items-center">
              <span class="inline-flex items-center justify-center w-6 h-6 rounded-full bg-[color:var(--accent-primary)]/10 text-[11px] font-bold text-[color:var(--accent-primary)]">{{ index + 1 }}</span>
              <span class="text-[8px] text-[color:var(--text-dim)] mt-0.5">фаза</span>
            </div>
          </div>
        </div>

        <!-- Полив -->
        <div class="rounded-md border border-[color:var(--border-muted)] p-3 space-y-3">
          <div class="text-[12px] font-bold uppercase tracking-[0.16em] text-[color:var(--text-muted)]">
            Полив
          </div>
          <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Тип системы полива</label>
              <select
                v-model="phase.irrigation_system_type"
                class="input-field w-full"
              >
                <template v-if="recipeIrrigationMode === 'SUBSTRATE'">
                  <option value="drip_tape">
                    Капельная лента
                  </option>
                  <option value="drip_emitter">
                    Капельные форсунки
                  </option>
                </template>
                <template v-else>
                  <option value="nft">
                    NFT (Nutrient Film)
                  </option>
                  <option value="dwc">
                    DWC (Deep Water Culture)
                  </option>
                  <option value="ebb_flow">
                    Прилив-отлив (ebb &amp; flow)
                  </option>
                  <option value="aeroponics">
                    Аэропоника
                  </option>
                </template>
              </select>
            </div>
            <div>
              <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Субстрат</label>
              <div class="flex gap-2">
                <select
                  v-model="phase.substrate_type"
                  class="input-field flex-1 min-w-0"
                  :disabled="substrateOptions(phase).length === 0"
                >
                  <option
                    v-for="opt in substrateOptions(phase)"
                    :key="opt.value ?? 'null'"
                    :value="opt.value"
                  >
                    {{ opt.label }}
                  </option>
                </select>
                <button
                  type="button"
                  class="pill-btn"
                  title="Создать новый субстрат"
                  @click="substrateModalOpen = true"
                >
                  <svg
                    class="w-4 h-4"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  ><line
                    x1="12"
                    y1="5"
                    x2="12"
                    y2="19"
                  /><line
                    x1="5"
                    y1="12"
                    x2="19"
                    y2="12"
                  /></svg>
                </button>
              </div>
            </div>
            <!-- Влажность субстрата: одно поле или раздельные день/ночь -->
            <div v-if="recipeIrrigationMode === 'SUBSTRATE' && !phase.day_night_enabled">
              <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Влажность субстрата, %</label>
              <div class="stepper">
                <button
                  type="button"
                  class="stepper__btn"
                  @click="phase.day_night.soil_moisture.day = Math.max(0, (phase.day_night.soil_moisture.day ?? 0) - 1)"
                >
                  −
                </button>
                <input
                  v-model.number="phase.day_night.soil_moisture.day"
                  type="number"
                  step="1"
                  class="stepper__input"
                />
                <button
                  type="button"
                  class="stepper__btn"
                  @click="phase.day_night.soil_moisture.day = Math.min(100, (phase.day_night.soil_moisture.day ?? 0) + 1)"
                >
                  +
                </button>
              </div>
            </div>
            <template v-if="recipeIrrigationMode === 'SUBSTRATE' && phase.day_night_enabled">
              <div>
                <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">☀ Влажность день, %</label>
                <div class="stepper">
                  <button
                    type="button"
                    class="stepper__btn"
                    @click="phase.day_night.soil_moisture.day = Math.max(0, (phase.day_night.soil_moisture.day ?? 0) - 1)"
                  >
                    −
                  </button>
                  <input
                    v-model.number="phase.day_night.soil_moisture.day"
                    type="number"
                    step="1"
                    class="stepper__input"
                  />
                  <button
                    type="button"
                    class="stepper__btn"
                    @click="phase.day_night.soil_moisture.day = Math.min(100, (phase.day_night.soil_moisture.day ?? 0) + 1)"
                  >
                    +
                  </button>
                </div>
              </div>
              <div>
                <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">☾ Влажность ночь, %</label>
                <div class="stepper">
                  <button
                    type="button"
                    class="stepper__btn"
                    @click="phase.day_night.soil_moisture.night = Math.max(0, (phase.day_night.soil_moisture.night ?? 0) - 1)"
                  >
                    −
                  </button>
                  <input
                    v-model.number="phase.day_night.soil_moisture.night"
                    type="number"
                    step="1"
                    class="stepper__input"
                  />
                  <button
                    type="button"
                    class="stepper__btn"
                    @click="phase.day_night.soil_moisture.night = Math.min(100, (phase.day_night.soil_moisture.night ?? 0) + 1)"
                  >
                    +
                  </button>
                </div>
              </div>
            </template>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-lg">
            <div>
              <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Интервал между поливами (ЧЧ:ММ)</label>
              <input
                :value="intervalDisplay(phase)"
                type="text"
                placeholder="00 : 00"
                class="input-field !w-32 text-center tracking-widest"
                @change="setIntervalFromString(phase, ($event.target as HTMLInputElement).value)"
              />
              <p class="text-[12px] text-[color:var(--text-muted)] mt-1 leading-snug">
                Время между началами циклов полива
              </p>
            </div>
            <div>
              <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Длительность полива (ММ:СС)</label>
              <input
                :value="durationIrrigDisplay(phase)"
                type="text"
                placeholder="00 : 00"
                class="input-field !w-28 text-center tracking-widest"
                @change="setDurationIrrigFromString(phase, ($event.target as HTMLInputElement).value)"
              />
              <p class="text-[12px] text-[color:var(--text-muted)] mt-1 leading-snug">
                Сколько длится один цикл полива (подача раствора)
              </p>
            </div>
          </div>
        </div>

        <!-- Раствор (pH / EC) -->
        <div class="rounded-md border border-[color:var(--border-muted)] p-2.5 space-y-2">
          <div class="text-[12px] font-bold uppercase tracking-[0.16em] text-[color:var(--text-muted)]">
            Раствор
          </div>
          <div :class="phase.day_night_enabled ? 'space-y-3' : 'max-w-sm space-y-2'">
            <!-- pH -->
            <div>
              <div class="text-sm font-extrabold text-[color:var(--text-primary)] mb-1 tracking-widest uppercase">
                pH
              </div>
              <div class="flex flex-wrap gap-3">
                <div :class="phase.day_night_enabled ? 'flex-1 min-w-[280px] max-w-sm' : 'w-full max-w-sm'">
                  <div
                    v-if="phase.day_night_enabled"
                    class="text-[10px] text-[color:var(--text-dim)] uppercase tracking-wider mb-1"
                  >
                    ☀ день
                  </div>
                  <div class="target-row">
                    <div class="target-row__side">
                      <span class="target-row__label">мин</span><input
                        v-model.number="phase.ph_min"
                        type="number"
                        step="0.1"
                        class="target-row__input hide-spin"
                      />
                    </div>
                    <div class="target-row__center">
                      <button
                        type="button"
                        class="target-row__btn"
                        @click="phase.ph_target = +((phase.ph_target ?? 0) - 0.1).toFixed(1); onPhTargetChange(phase)"
                      >
                        &minus;
                      </button>
                      <input
                        v-model.number="phase.ph_target"
                        type="number"
                        step="0.1"
                        class="target-row__input target-row__input--main hide-spin"
                        @input="onPhTargetChange(phase)"
                      />
                      <button
                        type="button"
                        class="target-row__btn"
                        @click="phase.ph_target = +((phase.ph_target ?? 0) + 0.1).toFixed(1); onPhTargetChange(phase)"
                      >
                        +
                      </button>
                    </div>
                    <div class="target-row__side">
                      <span class="target-row__label">макс</span><input
                        v-model.number="phase.ph_max"
                        type="number"
                        step="0.1"
                        class="target-row__input hide-spin"
                      />
                    </div>
                  </div>
                </div>
                <div
                  v-if="phase.day_night_enabled"
                  class="flex-1 min-w-[280px] max-w-sm"
                >
                  <div class="text-[10px] text-[color:var(--text-dim)] uppercase tracking-wider mb-1">
                    ☾ ночь
                  </div>
                  <div class="target-row">
                    <div class="target-row__side">
                      <span class="target-row__label">мин</span><input
                        v-model.number="phase.day_night.ph.night_min"
                        type="number"
                        step="0.1"
                        class="target-row__input hide-spin"
                      />
                    </div>
                    <div class="target-row__center">
                      <button
                        type="button"
                        class="target-row__btn"
                        @click="phase.day_night.ph.night = +((phase.day_night.ph.night ?? 0) - 0.1).toFixed(1); onPhNightTargetChange(phase)"
                      >
                        &minus;
                      </button>
                      <input
                        v-model.number="phase.day_night.ph.night"
                        type="number"
                        step="0.1"
                        class="target-row__input target-row__input--main hide-spin"
                        @input="onPhNightTargetChange(phase)"
                      />
                      <button
                        type="button"
                        class="target-row__btn"
                        @click="phase.day_night.ph.night = +((phase.day_night.ph.night ?? 0) + 0.1).toFixed(1); onPhNightTargetChange(phase)"
                      >
                        +
                      </button>
                    </div>
                    <div class="target-row__side">
                      <span class="target-row__label">макс</span><input
                        v-model.number="phase.day_night.ph.night_max"
                        type="number"
                        step="0.1"
                        class="target-row__input hide-spin"
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <!-- EC -->
            <div>
              <div class="text-sm font-extrabold text-[color:var(--text-primary)] mb-1 tracking-widest uppercase">
                EC
              </div>
              <div class="flex flex-wrap gap-3">
                <div :class="phase.day_night_enabled ? 'flex-1 min-w-[280px] max-w-sm' : 'w-full max-w-sm'">
                  <div
                    v-if="phase.day_night_enabled"
                    class="text-[10px] text-[color:var(--text-dim)] uppercase tracking-wider mb-1"
                  >
                    ☀ день
                  </div>
                  <div class="target-row">
                    <div class="target-row__side">
                      <span class="target-row__label">мин</span><input
                        v-model.number="phase.ec_min"
                        type="number"
                        step="0.1"
                        class="target-row__input hide-spin"
                      />
                    </div>
                    <div class="target-row__center">
                      <button
                        type="button"
                        class="target-row__btn"
                        @click="phase.ec_target = +((phase.ec_target ?? 0) - 0.1).toFixed(1); onEcTargetChange(phase)"
                      >
                        &minus;
                      </button>
                      <input
                        v-model.number="phase.ec_target"
                        type="number"
                        step="0.1"
                        class="target-row__input target-row__input--main hide-spin"
                        @input="onEcTargetChange(phase)"
                      />
                      <button
                        type="button"
                        class="target-row__btn"
                        @click="phase.ec_target = +((phase.ec_target ?? 0) + 0.1).toFixed(1); onEcTargetChange(phase)"
                      >
                        +
                      </button>
                    </div>
                    <div class="target-row__side">
                      <span class="target-row__label">макс</span><input
                        v-model.number="phase.ec_max"
                        type="number"
                        step="0.1"
                        class="target-row__input hide-spin"
                      />
                    </div>
                  </div>
                </div>
                <div
                  v-if="phase.day_night_enabled"
                  class="flex-1 min-w-[280px] max-w-sm"
                >
                  <div class="text-[10px] text-[color:var(--text-dim)] uppercase tracking-wider mb-1">
                    ☾ ночь
                  </div>
                  <div class="target-row">
                    <div class="target-row__side">
                      <span class="target-row__label">мин</span><input
                        v-model.number="phase.day_night.ec.night_min"
                        type="number"
                        step="0.1"
                        class="target-row__input hide-spin"
                      />
                    </div>
                    <div class="target-row__center">
                      <button
                        type="button"
                        class="target-row__btn"
                        @click="phase.day_night.ec.night = +((phase.day_night.ec.night ?? 0) - 0.1).toFixed(1); onEcNightTargetChange(phase)"
                      >
                        &minus;
                      </button>
                      <input
                        v-model.number="phase.day_night.ec.night"
                        type="number"
                        step="0.1"
                        class="target-row__input target-row__input--main hide-spin"
                        @input="onEcNightTargetChange(phase)"
                      />
                      <button
                        type="button"
                        class="target-row__btn"
                        @click="phase.day_night.ec.night = +((phase.day_night.ec.night ?? 0) + 0.1).toFixed(1); onEcNightTargetChange(phase)"
                      >
                        +
                      </button>
                    </div>
                    <div class="target-row__side">
                      <span class="target-row__label">макс</span><input
                        v-model.number="phase.day_night.ec.night_max"
                        type="number"
                        step="0.1"
                        class="target-row__input hide-spin"
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Питание -->
        <div class="rounded-md border border-[color:var(--border-muted)] p-2.5 space-y-2">
          <div class="text-[12px] font-bold uppercase tracking-[0.16em] text-[color:var(--text-muted)]">
            Питание
          </div>
          <div class="flex flex-wrap gap-2">
            <div>
              <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Режим питания</label>
              <select
                v-model="phase.nutrient_mode"
                class="input-field !min-w-[200px]"
              >
                <option value="ratio_ec_pid">
                  PID по EC + доли
                </option>
                <option value="delta_ec_by_k">
                  По дельте EC (k)
                </option>
                <option value="dose_ml_l_only">
                  Фикс. доза мл/л
                </option>
              </select>
              <p class="text-[12px] text-[color:var(--text-muted)] mt-1 leading-snug">
                <template v-if="phase.nutrient_mode === 'ratio_ec_pid'">
                  PID-регулятор по EC, доза распределяется по долям компонентов
                </template>
                <template v-else-if="phase.nutrient_mode === 'delta_ec_by_k'">
                  Расчёт дозы через разницу EC, коэффициент k и объём раствора
                </template>
                <template v-else>
                  Фиксированная доза мл/л для каждого компонента, без PID
                </template>
              </p>
            </div>
            <div v-if="phase.nutrient_mode !== 'dose_ml_l_only'">
              <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Режим дозирования</label>
              <select
                v-model="phase.nutrient_ec_dosing_mode"
                class="input-field !min-w-[200px]"
              >
                <option value="sequential">
                  Последовательный
                </option>
                <option value="parallel">
                  Параллельный
                </option>
              </select>
              <p class="text-[12px] text-[color:var(--text-muted)] mt-1 leading-snug">
                <template v-if="phase.nutrient_ec_dosing_mode === 'parallel'">
                  Ca, Mg, Micro дозируются одновременно в одном окне коррекции
                </template>
                <template v-else>
                  Ca &rarr; Mg &rarr; Micro по очереди, каждый ждёт подтверждения
                </template>
              </p>
            </div>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-4 gap-2">
            <RecipeEditorProductField
              v-model:product-id="phase.nutrient_npk_product_id"
              v-model:ratio="phase.nutrient_npk_ratio_pct"
              v-model:dose="phase.nutrient_npk_dose_ml_l"
              label="NPK"
              description="Азот, фосфор, калий — основа роста"
              component="npk"
              :products="npkProducts"
              @product-created="onProductCreated"
            />
            <RecipeEditorProductField
              v-model:product-id="phase.nutrient_calcium_product_id"
              v-model:ratio="phase.nutrient_calcium_ratio_pct"
              v-model:dose="phase.nutrient_calcium_dose_ml_l"
              label="Кальций"
              description="Укрепление клеток, профилактика вершинной гнили"
              component="calcium"
              :products="calciumProducts"
              @product-created="onProductCreated"
            />
            <RecipeEditorProductField
              v-model:product-id="phase.nutrient_magnesium_product_id"
              v-model:ratio="phase.nutrient_magnesium_ratio_pct"
              v-model:dose="phase.nutrient_magnesium_dose_ml_l"
              label="Магний"
              description="Фотосинтез, хлорофилл, усвоение фосфора"
              component="magnesium"
              :products="magnesiumProducts"
              @product-created="onProductCreated"
            />
            <RecipeEditorProductField
              v-model:product-id="phase.nutrient_micro_product_id"
              v-model:ratio="phase.nutrient_micro_ratio_pct"
              v-model:dose="phase.nutrient_micro_dose_ml_l"
              label="Микро"
              description="Fe, Mn, Zn, Cu, B, Mo — ферменты и иммунитет"
              component="micro"
              :products="microProducts"
              @product-created="onProductCreated"
            />
          </div>
          <!-- Ratio + Нормализация -->
          <div class="flex flex-col items-end gap-1">
            <div class="text-right">
              <div
                class="text-sm font-bold"
                :class="Math.abs(nutrientRatioSum(phase) - 100) <= 0.01 ? 'text-[color:var(--accent-green)]' : 'text-[color:var(--badge-warning-text)]'"
              >
                {{ nutrientRatioSum(phase).toFixed(1) }}%
              </div>
              <div class="text-[11px] text-[color:var(--text-muted)]">
                сумма долей
              </div>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-[12px] text-[color:var(--text-muted)]">Привести сумму долей к 100%</span>
              <button
                type="button"
                class="soft-btn"
                @click="normalizePhaseRatios(phase)"
              >
                <svg
                  class="w-3.5 h-3.5"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2.2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                ><polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" /><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" /></svg>
                Нормализовать
              </button>
            </div>
          </div>
          <!-- EC breakdown — красивые карточки день / ночь -->
          <div
            v-if="phase.day_night_enabled ? ecBreakdownsDayNight(phase) : ecBreakdown(phase).total > 0 && ecBreakdown(phase).npkShare > 0 && ecBreakdown(phase).npkShare < 1"
            class="grid gap-3"
            :class="phase.day_night_enabled ? 'md:grid-cols-2' : 'grid-cols-1'"
          >
            <!-- Карточка день (и одиночная когда свитч выключен) -->
            <div class="ec-breakdown-card">
              <div class="ec-breakdown-card__header">
                <span class="ec-breakdown-card__title">
                  <span v-if="phase.day_night_enabled">☀ День</span>
                  <span v-else>Расход EC по компонентам</span>
                </span>
                <span class="ec-breakdown-card__total">EC {{ phase.day_night_enabled ? ecBreakdownForTarget(phase, phase.ph_target /* unused */, phase.ec_target).total : ecBreakdown(phase).total }}</span>
              </div>
              <div class="ec-breakdown-card__chips">
                <div class="ec-chip ec-chip--npk">
                  <span class="ec-chip__label">NPK</span>
                  <span class="ec-chip__value">{{ phase.day_night_enabled ? ecBreakdownForTarget(phase, 0, phase.ec_target).npk : ecBreakdown(phase).npk }}</span>
                </div>
                <div class="ec-chip ec-chip--ca">
                  <span class="ec-chip__label">Ca</span>
                  <span class="ec-chip__value">{{ phase.day_night_enabled ? ecBreakdownForTarget(phase, 0, phase.ec_target).calcium : ecBreakdown(phase).calcium }}</span>
                </div>
                <div class="ec-chip ec-chip--mg">
                  <span class="ec-chip__label">Mg</span>
                  <span class="ec-chip__value">{{ phase.day_night_enabled ? ecBreakdownForTarget(phase, 0, phase.ec_target).magnesium : ecBreakdown(phase).magnesium }}</span>
                </div>
                <div class="ec-chip ec-chip--micro">
                  <span class="ec-chip__label">Micro</span>
                  <span class="ec-chip__value">{{ phase.day_night_enabled ? ecBreakdownForTarget(phase, 0, phase.ec_target).micro : ecBreakdown(phase).micro }}</span>
                </div>
              </div>
              <div class="ec-breakdown-card__flow">
                <div class="ec-flow-stage">
                  <span class="ec-flow-stage__icon">◐</span>
                  <span class="ec-flow-stage__label">Подготовка</span>
                  <span class="ec-flow-stage__value">{{ phase.day_night_enabled ? ecBreakdownForTarget(phase, 0, phase.ec_target).npk : ecBreakdown(phase).npk }}</span>
                </div>
                <span class="ec-flow-arrow">→</span>
                <div class="ec-flow-stage">
                  <span class="ec-flow-stage__icon">●</span>
                  <span class="ec-flow-stage__label">Полив</span>
                  <span class="ec-flow-stage__value">{{ phase.day_night_enabled ? ecBreakdownForTarget(phase, 0, phase.ec_target).total : ecBreakdown(phase).total }}</span>
                </div>
              </div>
            </div>

            <!-- Карточка ночь -->
            <div
              v-if="phase.day_night_enabled"
              class="ec-breakdown-card ec-breakdown-card--night"
            >
              <div class="ec-breakdown-card__header">
                <span class="ec-breakdown-card__title">☾ Ночь</span>
                <span class="ec-breakdown-card__total">EC {{ ecBreakdownForTarget(phase, 0, phase.day_night.ec.night ?? 0).total }}</span>
              </div>
              <div class="ec-breakdown-card__chips">
                <div class="ec-chip ec-chip--npk">
                  <span class="ec-chip__label">NPK</span>
                  <span class="ec-chip__value">{{ ecBreakdownForTarget(phase, 0, phase.day_night.ec.night ?? 0).npk }}</span>
                </div>
                <div class="ec-chip ec-chip--ca">
                  <span class="ec-chip__label">Ca</span>
                  <span class="ec-chip__value">{{ ecBreakdownForTarget(phase, 0, phase.day_night.ec.night ?? 0).calcium }}</span>
                </div>
                <div class="ec-chip ec-chip--mg">
                  <span class="ec-chip__label">Mg</span>
                  <span class="ec-chip__value">{{ ecBreakdownForTarget(phase, 0, phase.day_night.ec.night ?? 0).magnesium }}</span>
                </div>
                <div class="ec-chip ec-chip--micro">
                  <span class="ec-chip__label">Micro</span>
                  <span class="ec-chip__value">{{ ecBreakdownForTarget(phase, 0, phase.day_night.ec.night ?? 0).micro }}</span>
                </div>
              </div>
              <div class="ec-breakdown-card__flow">
                <div class="ec-flow-stage">
                  <span class="ec-flow-stage__icon">◐</span>
                  <span class="ec-flow-stage__label">Подготовка</span>
                  <span class="ec-flow-stage__value">{{ ecBreakdownForTarget(phase, 0, phase.day_night.ec.night ?? 0).npk }}</span>
                </div>
                <span class="ec-flow-arrow">→</span>
                <div class="ec-flow-stage">
                  <span class="ec-flow-stage__icon">●</span>
                  <span class="ec-flow-stage__label">Полив</span>
                  <span class="ec-flow-stage__value">{{ ecBreakdownForTarget(phase, 0, phase.day_night.ec.night ?? 0).total }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Климат -->
        <div class="rounded-md border border-[color:var(--border-muted)] p-2.5 space-y-2">
          <div class="text-[12px] font-bold uppercase tracking-[0.16em] text-[color:var(--text-muted)]">
            Климат
          </div>
          <!-- Режим: одно значение на день+ночь -->
          <div
            v-if="!phase.day_night_enabled"
            class="grid grid-cols-2 gap-3 max-w-md"
          >
            <div>
              <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Температура, °C</label>
              <div class="stepper">
                <button
                  type="button"
                  class="stepper__btn"
                  @click="phase.temp_air_target = +((phase.temp_air_target ?? 0) - 0.5).toFixed(1)"
                >
                  −
                </button>
                <input
                  v-model.number="phase.temp_air_target"
                  type="number"
                  step="0.1"
                  class="stepper__input"
                />
                <button
                  type="button"
                  class="stepper__btn"
                  @click="phase.temp_air_target = +((phase.temp_air_target ?? 0) + 0.5).toFixed(1)"
                >
                  +
                </button>
              </div>
            </div>
            <div>
              <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Влажность, %</label>
              <div class="stepper">
                <button
                  type="button"
                  class="stepper__btn"
                  @click="phase.humidity_target = Math.max(0, (phase.humidity_target ?? 0) - 1)"
                >
                  −
                </button>
                <input
                  v-model.number="phase.humidity_target"
                  type="number"
                  step="1"
                  class="stepper__input"
                />
                <button
                  type="button"
                  class="stepper__btn"
                  @click="phase.humidity_target = Math.min(100, (phase.humidity_target ?? 0) + 1)"
                >
                  +
                </button>
              </div>
            </div>
          </div>
          <!-- Режим: раздельно день/ночь — таблица -->
          <div
            v-else
            class="grid grid-cols-[140px_1fr_1fr] gap-x-3 gap-y-2 items-center max-w-lg"
          >
            <div></div>
            <div class="text-[10px] text-[color:var(--text-dim)] uppercase tracking-wider text-center">
              ☀ день
            </div>
            <div class="text-[10px] text-[color:var(--text-dim)] uppercase tracking-wider text-center">
              ☾ ночь
            </div>
            <label class="text-[12px] text-[color:var(--text-primary)] font-medium">Температура, °C</label>
            <div class="stepper">
              <button
                type="button"
                class="stepper__btn"
                @click="phase.day_night.temperature.day = +((phase.day_night.temperature.day ?? 0) - 0.5).toFixed(1)"
              >
                −
              </button>
              <input
                v-model.number="phase.day_night.temperature.day"
                type="number"
                step="0.1"
                class="stepper__input"
              />
              <button
                type="button"
                class="stepper__btn"
                @click="phase.day_night.temperature.day = +((phase.day_night.temperature.day ?? 0) + 0.5).toFixed(1)"
              >
                +
              </button>
            </div>
            <div class="stepper">
              <button
                type="button"
                class="stepper__btn"
                @click="phase.day_night.temperature.night = +((phase.day_night.temperature.night ?? 0) - 0.5).toFixed(1)"
              >
                −
              </button>
              <input
                v-model.number="phase.day_night.temperature.night"
                type="number"
                step="0.1"
                class="stepper__input"
              />
              <button
                type="button"
                class="stepper__btn"
                @click="phase.day_night.temperature.night = +((phase.day_night.temperature.night ?? 0) + 0.5).toFixed(1)"
              >
                +
              </button>
            </div>
            <label class="text-[12px] text-[color:var(--text-primary)] font-medium">Влажность, %</label>
            <div class="stepper">
              <button
                type="button"
                class="stepper__btn"
                @click="phase.day_night.humidity.day = Math.max(0, (phase.day_night.humidity.day ?? 0) - 1)"
              >
                −
              </button>
              <input
                v-model.number="phase.day_night.humidity.day"
                type="number"
                step="1"
                class="stepper__input"
              />
              <button
                type="button"
                class="stepper__btn"
                @click="phase.day_night.humidity.day = Math.min(100, (phase.day_night.humidity.day ?? 0) + 1)"
              >
                +
              </button>
            </div>
            <div class="stepper">
              <button
                type="button"
                class="stepper__btn"
                @click="phase.day_night.humidity.night = Math.max(0, (phase.day_night.humidity.night ?? 0) - 1)"
              >
                −
              </button>
              <input
                v-model.number="phase.day_night.humidity.night"
                type="number"
                step="1"
                class="stepper__input"
              />
              <button
                type="button"
                class="stepper__btn"
                @click="phase.day_night.humidity.night = Math.min(100, (phase.day_night.humidity.night ?? 0) + 1)"
              >
                +
              </button>
            </div>
          </div>
        </div>

        <!-- Свет -->
        <div class="rounded-md border border-[color:var(--border-muted)] p-2.5 space-y-2">
          <div class="text-[12px] font-bold uppercase tracking-[0.16em] text-[color:var(--text-muted)]">
            Свет
          </div>
          <div class="grid grid-cols-2 md:grid-cols-2 gap-3 max-w-md">
            <div>
              <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Фотопериод, часов</label>
              <div class="stepper">
                <button
                  type="button"
                  class="stepper__btn"
                  @click="phase.lighting_photoperiod_hours = Math.max(0, (phase.lighting_photoperiod_hours ?? 0) - 1)"
                >
                  −
                </button>
                <input
                  v-model.number="phase.lighting_photoperiod_hours"
                  type="number"
                  min="0"
                  max="24"
                  class="stepper__input"
                />
                <button
                  type="button"
                  class="stepper__btn"
                  @click="phase.lighting_photoperiod_hours = Math.min(24, (phase.lighting_photoperiod_hours ?? 0) + 1)"
                >
                  +
                </button>
              </div>
            </div>
            <div>
              <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Старт дня</label>
              <input
                v-model="phase.lighting_start_time"
                type="time"
                class="input-field"
              />
            </div>
          </div>
        </div>
      </section>
    </div>

    <!-- ── Кнопки внизу ──────────────────────────────────────── -->
    <div class="flex items-center justify-between pt-2">
      <Button
        type="button"
        size="sm"
        variant="secondary"
        data-testid="add-phase-button"
        @click="$emit('add-phase')"
      >
        Добавить фазу
      </Button>
      <Button
        type="button"
        size="sm"
        data-testid="save-recipe-bottom-button"
        @click="$emit('save')"
      >
        Сохранить
      </Button>
    </div>

    <SubstrateCreateModal
      :open="substrateModalOpen"
      @close="substrateModalOpen = false"
      @created="onSubstrateCreated"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Button from '@/Components/Button.vue'
import RecipeEditorProductField from '@/Components/RecipeEditorProductField.vue'
import type { NutrientProduct } from '@/types'
import type { PlantOption, RecipeEditorFormState, RecipePhaseFormState } from '@/composables/recipeEditorShared'
import { computeEcBreakdown, normalizePhaseRatios, nutrientRatioSum } from '@/composables/recipeEditorShared'
import type { EcBreakdown } from '@/composables/recipeEditorShared'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { useToast } from '@/composables/useToast'
import { api } from '@/services/api'
import SubstrateCreateModal from '@/Components/SubstrateCreateModal.vue'
import type { Substrate } from '@/services/api/substrates'

interface Props {
  plants: PlantOption[]
  plantsLoading?: boolean
  npkProducts: NutrientProduct[]
  calciumProducts: NutrientProduct[]
  magnesiumProducts: NutrientProduct[]
  microProducts: NutrientProduct[]
  substrates?: Substrate[]
  hidePlantSelect?: boolean
  lockedPlantLabel?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  plantsLoading: false,
  substrates: () => [],
  hidePlantSelect: false,
  lockedPlantLabel: null,
})

const form = defineModel<RecipeEditorFormState>('form', { required: true })

const emit = defineEmits<{
  'add-phase': []
  'remove-phase': [index: number]
  'plant-created': [plant: PlantOption]
  'product-created': [product: NutrientProduct]
  'substrate-created': [substrate: Substrate]
  'save': []
}>()

const { showToast } = useToast()

const plantMode = ref<'select' | 'create'>('select')
const newPlantName = ref('')
const newPlantSpecies = ref('')
const newPlantVariety = ref('')
const creatingPlant = ref(false)
const recipeLabel = ref(form.value.description || '')

const selectedPlantName = computed(() => {
  const plant = props.plants.find(p => p.id === form.value.plant_id)
  return plant?.name ?? ''
})

const recipeName = computed(() => {
  const plant = selectedPlantName.value
  const label = recipeLabel.value.trim()
  if (plant && label) return `${plant} ${label}`
  if (plant) return plant
  return label || ''
})

watch(recipeName, (name) => { form.value.name = name }, { immediate: true })
watch(recipeLabel, (label) => { form.value.description = label })

// Дефолтный субстрат для каждого типа полива.
const DEFAULT_SUBSTRATE_FOR: Record<string, string | null> = {
  drip_tape: 'soil',         // капельная лента → грунт
  drip_emitter: 'rockwool',  // капельные форсунки → минеральная вата
  ebb_flow: 'hydroton',      // прилив-отлив → керамзит
  nft: 'water',
  dwc: 'water',
  aeroponics: 'water',
}

interface SubstrateOption {
  value: string | null
  label: string
}

const substrateModalOpen = ref(false)

function substrateOptions(phase: RecipePhaseFormState): SubstrateOption[] {
  const sys = phase.irrigation_system_type
  // Фильтр по совместимости с типом полива
  const compatible = props.substrates.filter(s => !s.applicable_systems?.length || s.applicable_systems.includes(sys))
  return compatible.map(s => ({ value: s.code, label: s.name }))
}

function onSubstrateCreated(substrate: Substrate): void {
  emit('substrate-created', substrate)
  // Если в текущей фазе совместим — выбрать его
  const currentPhaseSys = form.value.phases[0]?.irrigation_system_type
  if (!substrate.applicable_systems?.length || substrate.applicable_systems.includes(currentPhaseSys)) {
    form.value.phases.forEach((phase) => {
      if (!substrate.applicable_systems?.length || substrate.applicable_systems.includes(phase.irrigation_system_type)) {
        phase.substrate_type = substrate.code
      }
    })
  }
  substrateModalOpen.value = false
}

// При смене типа полива фазы — если текущий субстрат не совместим, переставить на дефолтный для этого типа.
watch(
  () => form.value.phases.map(p => p.irrigation_system_type),
  (newTypes, oldTypes) => {
    form.value.phases.forEach((phase, idx) => {
      const opts = substrateOptions(phase)
      const valid = opts.some(o => o.value === phase.substrate_type)
      const typeChanged = oldTypes && newTypes[idx] !== oldTypes[idx]
      if (!valid || typeChanged) {
        const defaultValue = DEFAULT_SUBSTRATE_FOR[phase.irrigation_system_type]
        const defaultIsValid = opts.some(o => o.value === defaultValue)
        phase.substrate_type = defaultIsValid ? defaultValue : (opts[0]?.value ?? null)
      }
    })
  },
  { deep: true, immediate: true },
)

// Система подготовки раствора и полива — единая для всех фаз рецепта.
// Читаем из первой фазы, при изменении обновляем во всех фазах.
const SUBSTRATE_SYSTEM_TYPES = ['drip_tape', 'drip_emitter'] as const
const RECIRC_SYSTEM_TYPES = ['nft', 'dwc', 'ebb_flow', 'aeroponics'] as const

function validSystemTypesFor(mode: 'SUBSTRATE' | 'RECIRC'): readonly string[] {
  return mode === 'SUBSTRATE' ? SUBSTRATE_SYSTEM_TYPES : RECIRC_SYSTEM_TYPES
}

const recipeIrrigationMode = computed<'SUBSTRATE' | 'RECIRC'>({
  get: () => form.value.phases[0]?.irrigation_mode ?? 'SUBSTRATE',
  set: (value) => {
    const valid = validSystemTypesFor(value)
    const defaultSystem = valid[0] as RecipePhaseFormState['irrigation_system_type']
    form.value.phases.forEach((phase) => {
      phase.irrigation_mode = value
      if (!valid.includes(phase.irrigation_system_type)) {
        phase.irrigation_system_type = defaultSystem
      }
    })
  },
})

async function createPlant(): Promise<void> {
  const name = newPlantName.value.trim()
  if (!name) return
  creatingPlant.value = true
  try {
    const plant = await api.plants.create({
      name,
      species: newPlantSpecies.value.trim() || null,
      variety: newPlantVariety.value.trim() || null,
    })
    form.value.plant_id = plant.id
    emit('plant-created', { id: plant.id, name: plant.name })
    plantMode.value = 'select'
    newPlantName.value = ''
    newPlantSpecies.value = ''
    newPlantVariety.value = ''
    showToast(`Растение "${plant.name}" создано`, 'success', TOAST_TIMEOUT.NORMAL)
  } catch (err: unknown) {
    showToast('Ошибка создания растения', 'error', TOAST_TIMEOUT.NORMAL)
  } finally {
    creatingPlant.value = false
  }
}

function onProductCreated(product: NutrientProduct): void {
  emit('product-created', product)
}

// ── Длительность фазы (ДД:ЧЧ) ──
function durationDays(phase: RecipePhaseFormState): number {
  return Math.floor((phase.duration_hours ?? 0) / 24)
}
function durationHoursPart(phase: RecipePhaseFormState): number {
  return (phase.duration_hours ?? 0) % 24
}
function durationDisplay(phase: RecipePhaseFormState): string {
  const d = durationDays(phase)
  const h = durationHoursPart(phase)
  return `${d} : ${String(h).padStart(2, '0')}`
}
function setDurationFromString(phase: RecipePhaseFormState, value: string): void {
  const parts = value.split(':').map(s => s.trim())
  const d = Math.max(0, Number(parts[0]) || 0)
  const h = parts.length > 1 ? Math.max(0, Math.min(23, Number(parts[1]) || 0)) : 0
  phase.duration_hours = d * 24 + h
}

// ── Интервал полива (ЧЧ:ММ) ──
function intervalDisplay(phase: RecipePhaseFormState): string {
  const sec = phase.irrigation_interval_sec ?? 0
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  return `${String(h).padStart(2, '0')} : ${String(m).padStart(2, '0')}`
}
function setIntervalFromString(phase: RecipePhaseFormState, value: string): void {
  const parts = value.split(':').map(s => s.trim())
  const h = Math.max(0, Number(parts[0]) || 0)
  const m = parts.length > 1 ? Math.max(0, Math.min(59, Number(parts[1]) || 0)) : 0
  phase.irrigation_interval_sec = h * 3600 + m * 60
}

// ── Длительность полива (ММ:СС) ──
function durationIrrigDisplay(phase: RecipePhaseFormState): string {
  const sec = phase.irrigation_duration_sec ?? 0
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${String(m).padStart(2, '0')} : ${String(s).padStart(2, '0')}`
}
function setDurationIrrigFromString(phase: RecipePhaseFormState, value: string): void {
  const parts = value.split(':').map(s => s.trim())
  const m = Math.max(0, Number(parts[0]) || 0)
  const s = parts.length > 1 ? Math.max(0, Math.min(59, Number(parts[1]) || 0)) : 0
  phase.irrigation_duration_sec = m * 60 + s
}

function onPhTargetChange(phase: RecipePhaseFormState): void {
  const t = phase.ph_target ?? 0
  phase.ph_min = +(t - 0.1).toFixed(2)
  phase.ph_max = +(t + 0.1).toFixed(2)
}

function onEcTargetChange(phase: RecipePhaseFormState): void {
  const t = phase.ec_target ?? 0
  phase.ec_min = +(t - 0.1).toFixed(2)
  phase.ec_max = +(t + 0.1).toFixed(2)
}

function onPhNightTargetChange(phase: RecipePhaseFormState): void {
  const t = phase.day_night.ph.night ?? 0
  phase.day_night.ph.night_min = +(t - 0.1).toFixed(2)
  phase.day_night.ph.night_max = +(t + 0.1).toFixed(2)
}

function onEcNightTargetChange(phase: RecipePhaseFormState): void {
  const t = phase.day_night.ec.night ?? 0
  phase.day_night.ec.night_min = +(t - 0.1).toFixed(2)
  phase.day_night.ec.night_max = +(t + 0.1).toFixed(2)
}

function ecBreakdown(phase: RecipePhaseFormState): EcBreakdown {
  return computeEcBreakdown(phase)
}

// Пересчитать EC breakdown для произвольного target (day / night)
function ecBreakdownForTarget(phase: RecipePhaseFormState, _ph: number, ecTarget: number): EcBreakdown {
  return computeEcBreakdown({ ...phase, ec_target: ecTarget || 0 })
}

// Проверка: показывать ли breakdown при включенном day_night
function ecBreakdownsDayNight(phase: RecipePhaseFormState): boolean {
  const b = ecBreakdown(phase)
  return b.total > 0 && b.npkShare > 0 && b.npkShare < 1
}

const sortedPhases = computed<RecipePhaseFormState[]>(() => {
  return [...form.value.phases].sort((left, right) => left.phase_index - right.phase_index)
})
</script>

<style scoped>
.hide-spin::-webkit-outer-spin-button,
.hide-spin::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
.hide-spin {
  -moz-appearance: textfield;
}

.target-row {
  display: flex;
  align-items: stretch;
  border: 1px solid var(--border-muted);
  border-radius: 0.6rem;
  overflow: hidden;
  background: var(--bg-elevated);
}
.target-row__side {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 4.5rem;
  padding: 0.15rem 0;
}
.target-row__label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-muted);
  line-height: 1;
  letter-spacing: 0.03em;
  margin-bottom: 0.15rem;
}
.target-row__center {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border-left: 1px solid var(--border-muted);
  border-right: 1px solid var(--border-muted);
  background: color-mix(in srgb, var(--accent-green) 6%, var(--bg-elevated));
}
.target-row__input {
  width: 100%;
  height: 2.2rem;
  border: none;
  background: transparent;
  text-align: center;
  font-size: 0.8rem;
  color: var(--text-primary);
  outline: none;
}
.target-row__input:focus {
  outline: none;
  box-shadow: none;
}
.target-row__input--main {
  flex: 1;
  min-width: 0;
  font-size: 1.1rem;
  font-weight: 700;
}

/* Круглая +-кнопка рядом с select */
.pill-btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.6rem;
  height: 2.6rem;
  border-radius: 0.85rem;
  background: color-mix(in srgb, var(--accent-green) 12%, transparent);
  color: var(--accent-green);
  border: 1px solid color-mix(in srgb, var(--accent-green) 25%, transparent);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, transform 0.08s;
}
.pill-btn:hover {
  background: color-mix(in srgb, var(--accent-green) 20%, transparent);
  border-color: color-mix(in srgb, var(--accent-green) 45%, transparent);
}
.pill-btn:active {
  transform: scale(0.94);
}

/* Мягкая кнопка (normalize и подобные) с иконкой */
.soft-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.4rem 0.85rem;
  border-radius: 0.6rem;
  background: color-mix(in srgb, var(--accent-green) 8%, transparent);
  color: var(--accent-green);
  font-size: 0.75rem;
  font-weight: 600;
  border: 1px solid transparent;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, transform 0.08s;
}
.soft-btn:hover {
  background: color-mix(in srgb, var(--accent-green) 16%, transparent);
}
.soft-btn:active {
  transform: scale(0.97);
}

/* Material-style toggle switch */
.md-switch {
  display: inline-flex;
  align-items: center;
  gap: 0.55rem;
  cursor: pointer;
  user-select: none;
  height: 2.6rem;
}
.md-switch input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}
.md-switch__track {
  position: relative;
  width: 2.6rem;
  height: 1rem;
  border-radius: 0.5rem;
  background: color-mix(in srgb, var(--text-dim) 40%, transparent);
  transition: background 0.2s ease;
  flex-shrink: 0;
}
.md-switch__thumb {
  position: absolute;
  top: 50%;
  left: -0.15rem;
  transform: translateY(-50%);
  width: 1.3rem;
  height: 1.3rem;
  border-radius: 50%;
  background: #f4f4f5;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25), 0 1px 2px rgba(0, 0, 0, 0.15);
  transition: left 0.2s ease, background 0.2s ease;
}
.md-switch input:checked + .md-switch__track {
  background: color-mix(in srgb, var(--accent-green) 45%, transparent);
}
.md-switch input:checked + .md-switch__track .md-switch__thumb {
  left: calc(100% - 1.15rem);
  background: var(--accent-green);
  box-shadow: 0 1px 4px color-mix(in srgb, var(--accent-green) 40%, transparent);
}
.md-switch input:focus-visible + .md-switch__track {
  outline: 2px solid color-mix(in srgb, var(--accent-green) 40%, transparent);
  outline-offset: 2px;
}
.md-switch__label {
  font-size: 0.78rem;
  font-weight: 500;
  color: var(--text-muted);
  min-width: 2rem;
}
.md-switch input:checked ~ .md-switch__label {
  color: var(--accent-green);
}

/* EC breakdown — карточка */
.ec-breakdown-card {
  border: 1px solid var(--border-muted);
  border-radius: 0.75rem;
  padding: 0.75rem;
  background: color-mix(in srgb, var(--accent-green) 3%, var(--bg-elevated));
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.ec-breakdown-card--night {
  background: color-mix(in srgb, #1e3a5f 5%, var(--bg-elevated));
}
.ec-breakdown-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.ec-breakdown-card__title {
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.ec-breakdown-card__total {
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--accent-green);
  background: color-mix(in srgb, var(--accent-green) 12%, transparent);
  padding: 0.15rem 0.55rem;
  border-radius: 0.35rem;
}
.ec-breakdown-card__chips {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.4rem;
}
.ec-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0.35rem 0.25rem;
  border-radius: 0.5rem;
  background: var(--bg-elevated);
  border: 1px solid var(--border-muted);
}
.ec-chip__label {
  font-size: 0.65rem;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.ec-chip__value {
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}
.ec-chip--npk { border-color: color-mix(in srgb, #10b981 35%, transparent); }
.ec-chip--npk .ec-chip__label { color: #059669; }
.ec-chip--ca { border-color: color-mix(in srgb, #3b82f6 35%, transparent); }
.ec-chip--ca .ec-chip__label { color: #2563eb; }
.ec-chip--mg { border-color: color-mix(in srgb, #f59e0b 35%, transparent); }
.ec-chip--mg .ec-chip__label { color: #d97706; }
.ec-chip--micro { border-color: color-mix(in srgb, #a855f7 35%, transparent); }
.ec-chip--micro .ec-chip__label { color: #9333ea; }

.ec-breakdown-card__flow {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding-top: 0.35rem;
  border-top: 1px dashed var(--border-muted);
}
.ec-flow-stage {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.72rem;
  color: var(--text-muted);
}
.ec-flow-stage__icon {
  color: var(--accent-green);
  font-size: 0.7rem;
}
.ec-flow-stage__label {
  font-weight: 500;
}
.ec-flow-stage__value {
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}
.ec-flow-arrow {
  color: var(--text-dim);
  font-size: 0.85rem;
}

/* Stepper input — компактное поле с кнопками - / + */
.stepper {
  display: inline-flex;
  align-items: stretch;
  border: 1px solid var(--border-muted);
  border-radius: 0.6rem;
  overflow: hidden;
  background: var(--bg-elevated);
  width: 100%;
  max-width: 11rem;
  height: 2.2rem;
}
.stepper__btn {
  width: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1rem;
  font-weight: 700;
  color: var(--accent-green);
  background: color-mix(in srgb, var(--accent-green) 6%, transparent);
  border: none;
  cursor: pointer;
  transition: background 0.15s, transform 0.08s;
  user-select: none;
}
.stepper__btn:hover {
  background: color-mix(in srgb, var(--accent-green) 15%, transparent);
}
.stepper__btn:active {
  transform: scale(0.92);
}
.stepper__input {
  flex: 1;
  min-width: 0;
  border: none;
  background: transparent;
  text-align: center;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
  outline: none;
  -moz-appearance: textfield;
}
.stepper__input::-webkit-outer-spin-button,
.stepper__input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
.stepper__input:focus {
  outline: none;
  box-shadow: none;
}
.stepper__unit {
  display: flex;
  align-items: center;
  padding-right: 0.5rem;
  font-size: 0.7rem;
  color: var(--text-muted);
  pointer-events: none;
}
.target-row__btn {
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--accent-green);
  background: color-mix(in srgb, var(--accent-green) 10%, transparent);
  border: none;
  border-radius: 50%;
  margin: 0 0.15rem;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s, transform 0.1s;
}
.target-row__btn:hover {
  background: color-mix(in srgb, var(--accent-green) 20%, transparent);
}
.target-row__btn:active {
  transform: scale(0.9);
}
</style>
