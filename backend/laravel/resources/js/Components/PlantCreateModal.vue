<template>
  <Modal
    :open="show"
    title="Создать растение"
    size="large"
    @close="handleClose"
  >
    <form
      class="space-y-4"
      @submit.prevent="onSubmit"
    >
      <div class="flex items-center justify-between text-xs text-[color:var(--text-muted)]">
        <span>Шаг {{ currentStep }} из 2: {{ stepTitle }}</span>
        <div class="flex items-center gap-1">
          <span
            class="h-2 w-2 rounded-full"
            :class="currentStep >= 1 ? 'bg-[color:var(--accent-primary)]' : 'bg-[color:var(--border-muted)]'"
          ></span>
          <span
            class="h-2 w-2 rounded-full"
            :class="currentStep >= 2 ? 'bg-[color:var(--accent-primary)]' : 'bg-[color:var(--border-muted)]'"
          ></span>
        </div>
      </div>

      <div
        v-if="currentStep === 1"
        class="grid grid-cols-1 md:grid-cols-2 gap-4"
      >
        <div class="md:col-span-2">
          <label
            for="plant-name"
            class="block text-xs text-[color:var(--text-muted)] mb-1"
          >
            Название <span class="text-[color:var(--accent-red)]">*</span>
          </label>
          <input
            id="plant-name"
            v-model="form.name"
            name="name"
            type="text"
            required
            placeholder="Салат Айсберг"
            class="input-field h-9 w-full"
            :class="errors.name ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''"
            autocomplete="off"
          />
          <div
            v-if="errors.name"
            class="text-xs text-[color:var(--accent-red)] mt-1"
          >
            {{ errors.name }}
          </div>
        </div>

        <div>
          <label
            for="plant-species"
            class="block text-xs text-[color:var(--text-muted)] mb-1"
          >Вид</label>
          <input
            id="plant-species"
            v-model="form.species"
            name="species"
            type="text"
            placeholder="Lactuca sativa"
            class="input-field h-9 w-full"
            autocomplete="off"
          />
        </div>

        <div>
          <label
            for="plant-variety"
            class="block text-xs text-[color:var(--text-muted)] mb-1"
          >Сорт</label>
          <input
            id="plant-variety"
            v-model="form.variety"
            name="variety"
            type="text"
            placeholder="Айсберг"
            class="input-field h-9 w-full"
            autocomplete="off"
          />
        </div>

        <div>
          <div class="flex items-center justify-between mb-1">
            <label
              for="plant-system"
              class="block text-xs text-[color:var(--text-muted)]"
            >Система <span class="text-[color:var(--accent-red)]">*</span></label>
          </div>
          <div class="flex items-center gap-2">
            <div
              class="flex h-9 flex-1 items-center rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)]"
              :class="errors.growing_system ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''"
            >
              <select
                id="plant-system"
                v-model="form.growing_system"
                name="growing_system"
                class="h-9 w-full bg-transparent border-none focus:ring-0 focus:outline-none appearance-none px-2"
              >
                <option value="">
                  Не выбрано
                </option>
                <option
                  v-for="option in taxonomyOptions.growing_system"
                  :key="option.id"
                  :value="option.id"
                >
                  {{ option.label }}
                </option>
              </select>
            </div>
            <button
              type="button"
              class="h-9 w-9 shrink-0 inline-flex items-center justify-center rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-0"
              @click="openTaxonomyWizard('growing_system')"
            >
              <svg
                class="h-5 w-5 text-[color:var(--accent-primary)]"
                viewBox="0 0 20 20"
                fill="currentColor"
                aria-hidden="true"
              >
                <path
                  fill-rule="evenodd"
                  d="M10 4.75a.75.75 0 0 1 .75.75v3.75h3.75a.75.75 0 0 1 0 1.5h-3.75v3.75a.75.75 0 0 1-1.5 0v-3.75H5.5a.75.75 0 0 1 0-1.5h3.75V5.5a.75.75 0 0 1 .75-.75Z"
                  clip-rule="evenodd"
                />
              </svg>
            </button>
          </div>
          <div
            v-if="errors.growing_system"
            class="text-xs text-[color:var(--accent-red)] mt-1"
          >
            {{ errors.growing_system }}
          </div>
          <p
            v-if="form.growing_system && !showSubstrateSelector"
            class="mt-1 text-[11px] text-[color:var(--text-dim)]"
          >
            Для выбранной системы субстрат не используется.
          </p>
        </div>

        <div v-if="showSubstrateSelector">
          <div class="flex items-center justify-between mb-1">
            <label
              for="plant-substrate"
              class="block text-xs text-[color:var(--text-muted)]"
            >Субстрат</label>
          </div>
          <div class="flex items-center gap-2">
            <div class="flex h-9 flex-1 items-center rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)]">
              <select
                id="plant-substrate"
                v-model="form.substrate_type"
                name="substrate_type"
                class="h-9 w-full bg-transparent border-none focus:ring-0 focus:outline-none appearance-none px-2"
              >
                <option value="">
                  Не выбрано
                </option>
                <option
                  v-for="option in taxonomyOptions.substrate_type"
                  :key="option.id"
                  :value="option.id"
                >
                  {{ option.label }}
                </option>
              </select>
            </div>
            <button
              type="button"
              class="h-9 w-9 shrink-0 inline-flex items-center justify-center rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-0"
              @click="openTaxonomyWizard('substrate_type')"
            >
              <svg
                class="h-5 w-5 text-[color:var(--accent-primary)]"
                viewBox="0 0 20 20"
                fill="currentColor"
                aria-hidden="true"
              >
                <path
                  fill-rule="evenodd"
                  d="M10 4.75a.75.75 0 0 1 .75.75v3.75h3.75a.75.75 0 0 1 0 1.5h-3.75v3.75a.75.75 0 0 1-1.5 0v-3.75H5.5a.75.75 0 0 1 0-1.5h3.75V5.5a.75.75 0 0 1 .75-.75Z"
                  clip-rule="evenodd"
                />
              </svg>
            </button>
          </div>
        </div>

        <div>
          <div class="flex items-center justify-between mb-1">
            <label
              for="plant-seasonality"
              class="block text-xs text-[color:var(--text-muted)]"
            >Сезонность (опционально)</label>
          </div>
          <div class="flex items-center gap-2">
            <div class="flex h-9 flex-1 items-center rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)]">
              <select
                id="plant-seasonality"
                v-model="form.seasonality"
                name="seasonality"
                class="h-9 w-full bg-transparent border-none focus:ring-0 focus:outline-none appearance-none px-2"
              >
                <option value="">
                  Не выбрано
                </option>
                <option
                  v-for="option in seasonOptions"
                  :key="option.id"
                  :value="option.id"
                >
                  {{ option.label }}
                </option>
              </select>
            </div>
            <button
              type="button"
              class="h-9 w-9 shrink-0 inline-flex items-center justify-center rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-0"
              @click="openTaxonomyWizard('seasonality')"
            >
              <svg
                class="h-5 w-5 text-[color:var(--accent-primary)]"
                viewBox="0 0 20 20"
                fill="currentColor"
                aria-hidden="true"
              >
                <path
                  fill-rule="evenodd"
                  d="M10 4.75a.75.75 0 0 1 .75.75v3.75h3.75a.75.75 0 0 1 0 1.5h-3.75v3.75a.75.75 0 0 1-1.5 0v-3.75H5.5a.75.75 0 0 1 0-1.5h3.75V5.5a.75.75 0 0 1 .75-.75Z"
                  clip-rule="evenodd"
                />
              </svg>
            </button>
          </div>
        </div>

        <div class="md:col-span-2">
          <label
            for="plant-description"
            class="block text-xs text-[color:var(--text-muted)] mb-1"
          >Описание</label>
          <textarea
            id="plant-description"
            v-model="form.description"
            name="description"
            rows="3"
            placeholder="Описание растения..."
            class="input-field w-full"
            autocomplete="off"
          ></textarea>
        </div>
      </div>

      <div
        v-else
        class="space-y-4"
      >
        <div class="rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-muted)] px-3 py-2 text-xs text-[color:var(--text-muted)]">
          Растение: <span class="text-[color:var(--text-primary)] font-semibold">{{ form.name }}</span>
        </div>
        <div>
          <div class="mb-1 flex items-center gap-1">
            <label
              for="recipe-name"
              class="block text-xs text-[color:var(--text-muted)]"
            >
              Название рецепта <span class="text-[color:var(--accent-red)]">*</span>
            </label>
            <span class="group relative inline-flex cursor-help items-center">
              <span class="inline-flex h-4 w-4 items-center justify-center rounded-full border border-[color:var(--border-muted)] text-[10px] text-[color:var(--text-dim)]">i</span>
              <span class="pointer-events-none absolute left-1/2 top-full z-50 mt-1 w-56 -translate-x-1/2 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] px-2 py-1.5 text-[10px] leading-4 text-[color:var(--text-primary)] opacity-0 shadow-[var(--shadow-card)] transition-opacity group-hover:opacity-100">
                Используется в списке рецептов и при запуске цикла выращивания в зоне.
              </span>
            </span>
          </div>
          <input
            id="recipe-name"
            v-model="form.recipe_name"
            name="recipe_name"
            type="text"
            required
            placeholder="Рецепт для салата"
            class="input-field h-9 w-full"
            :class="errors.recipe_name ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''"
            autocomplete="off"
          />
          <div
            v-if="errors.recipe_name"
            class="text-xs text-[color:var(--accent-red)] mt-1"
          >
            {{ errors.recipe_name }}
          </div>
        </div>
        <div>
          <div class="mb-1 flex items-center gap-1">
            <label
              for="recipe-description"
              class="block text-xs text-[color:var(--text-muted)]"
            >Описание рецепта</label>
            <span class="group relative inline-flex cursor-help items-center">
              <span class="inline-flex h-4 w-4 items-center justify-center rounded-full border border-[color:var(--border-muted)] text-[10px] text-[color:var(--text-dim)]">i</span>
              <span class="pointer-events-none absolute left-1/2 top-full z-50 mt-1 w-56 -translate-x-1/2 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] px-2 py-1.5 text-[10px] leading-4 text-[color:var(--text-primary)] opacity-0 shadow-[var(--shadow-card)] transition-opacity group-hover:opacity-100">
                Короткая справка по рецепту: культура, цель, особенности режима.
              </span>
            </span>
          </div>
          <textarea
            id="recipe-description"
            v-model="form.recipe_description"
            name="recipe_description"
            rows="3"
            placeholder="Краткое описание рецепта..."
            class="input-field w-full"
            autocomplete="off"
          ></textarea>
        </div>

        <div class="rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-muted)] p-3 space-y-3">
          <div class="flex items-center justify-between">
            <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
              Фазы полного цикла (день/ночь)
            </h4>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              @click="addRecipePhase"
            >
              Добавить фазу
            </Button>
          </div>

          <div
            v-for="(phase, index) in form.recipe_phases"
            :key="`recipe-phase-${index}`"
            class="rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-3 space-y-3"
          >
            <div class="flex items-center justify-between">
              <span class="text-xs text-[color:var(--text-muted)]">Фаза {{ index + 1 }}</span>
              <Button
                v-if="form.recipe_phases.length > 1"
                type="button"
                size="sm"
                variant="danger"
                @click="removeRecipePhase(index)"
              >
                Удалить
              </Button>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div class="space-y-1">
                <div class="flex items-center gap-1">
                  <span class="text-xs text-[color:var(--text-muted)]">Название фазы</span>
                  <span class="group relative inline-flex cursor-help items-center">
                    <span class="inline-flex h-4 w-4 items-center justify-center rounded-full border border-[color:var(--border-muted)] text-[10px] text-[color:var(--text-dim)]">i</span>
                    <span class="pointer-events-none absolute left-1/2 top-full z-50 mt-1 w-56 -translate-x-1/2 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] px-2 py-1.5 text-[10px] leading-4 text-[color:var(--text-primary)] opacity-0 shadow-[var(--shadow-card)] transition-opacity group-hover:opacity-100">
                      Понятное название этапа: например, «Рассада», «Вегетация», «Цветение».
                    </span>
                  </span>
                </div>
                <input
                  v-model="phase.name"
                  type="text"
                  class="input-field h-9 w-full"
                  placeholder="Название фазы"
                />
              </div>
              <div class="space-y-1">
                <div class="flex items-center gap-1">
                  <span class="text-xs text-[color:var(--text-muted)]">Длительность, дни</span>
                  <span class="group relative inline-flex cursor-help items-center">
                    <span class="inline-flex h-4 w-4 items-center justify-center rounded-full border border-[color:var(--border-muted)] text-[10px] text-[color:var(--text-dim)]">i</span>
                    <span class="pointer-events-none absolute left-1/2 top-full z-50 mt-1 w-56 -translate-x-1/2 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] px-2 py-1.5 text-[10px] leading-4 text-[color:var(--text-primary)] opacity-0 shadow-[var(--shadow-card)] transition-opacity group-hover:opacity-100">
                      Сколько суток длится фаза. Используется для расчета календаря цикла.
                    </span>
                  </span>
                </div>
                <input
                  v-model.number="phase.duration_days"
                  type="number"
                  min="1"
                  class="input-field h-9 w-full"
                  placeholder="Дней"
                />
              </div>
              <div class="space-y-1">
                <div class="flex items-center gap-1">
                  <span class="text-xs text-[color:var(--text-muted)]">Начало дня</span>
                  <span class="group relative inline-flex cursor-help items-center">
                    <span class="inline-flex h-4 w-4 items-center justify-center rounded-full border border-[color:var(--border-muted)] text-[10px] text-[color:var(--text-dim)]">i</span>
                    <span class="pointer-events-none absolute left-1/2 top-full z-50 mt-1 w-56 -translate-x-1/2 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] px-2 py-1.5 text-[10px] leading-4 text-[color:var(--text-primary)] opacity-0 shadow-[var(--shadow-card)] transition-opacity group-hover:opacity-100">
                      Время начала дневного периода. От него считаются свет и параметры «день/ночь».
                    </span>
                  </span>
                </div>
                <select
                  v-model="phase.day_start_time"
                  class="input-field h-9 w-full"
                >
                  <option value="06:00:00">
                    День с 06:00
                  </option>
                  <option value="07:00:00">
                    День с 07:00
                  </option>
                  <option value="08:00:00">
                    День с 08:00
                  </option>
                </select>
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
              <div class="space-y-1">
                <div class="flex items-center gap-1">
                  <span class="text-xs text-[color:var(--text-muted)]">Свет, ч/сут</span>
                  <span class="group relative inline-flex cursor-help items-center">
                    <span class="inline-flex h-4 w-4 items-center justify-center rounded-full border border-[color:var(--border-muted)] text-[10px] text-[color:var(--text-dim)]">i</span>
                    <span class="pointer-events-none absolute left-1/2 top-full z-50 mt-1 w-56 -translate-x-1/2 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] px-2 py-1.5 text-[10px] leading-4 text-[color:var(--text-primary)] opacity-0 shadow-[var(--shadow-card)] transition-opacity group-hover:opacity-100">
                      Фотопериод: сколько часов в сутки включен свет.
                    </span>
                  </span>
                </div>
                <input
                  v-model.number="phase.light_hours"
                  type="number"
                  min="0"
                  max="24"
                  class="input-field h-9 w-full"
                  placeholder="Свет, ч/сут"
                />
              </div>
              <div class="space-y-1">
                <div class="flex items-center gap-1">
                  <span class="text-xs text-[color:var(--text-muted)]">pH (день)</span>
                  <span class="group relative inline-flex cursor-help items-center">
                    <span class="inline-flex h-4 w-4 items-center justify-center rounded-full border border-[color:var(--border-muted)] text-[10px] text-[color:var(--text-dim)]">i</span>
                    <span class="pointer-events-none absolute left-1/2 top-full z-50 mt-1 w-56 -translate-x-1/2 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] px-2 py-1.5 text-[10px] leading-4 text-[color:var(--text-primary)] opacity-0 shadow-[var(--shadow-card)] transition-opacity group-hover:opacity-100">
                      Целевой уровень pH раствора в дневной период.
                    </span>
                  </span>
                </div>
                <input
                  v-model.number="phase.ph_day"
                  type="number"
                  step="0.1"
                  class="input-field h-9 w-full"
                  placeholder="pH день"
                />
              </div>
              <div class="space-y-1">
                <div class="flex items-center gap-1">
                  <span class="text-xs text-[color:var(--text-muted)]">pH (ночь)</span>
                  <span class="group relative inline-flex cursor-help items-center">
                    <span class="inline-flex h-4 w-4 items-center justify-center rounded-full border border-[color:var(--border-muted)] text-[10px] text-[color:var(--text-dim)]">i</span>
                    <span class="pointer-events-none absolute left-1/2 top-full z-50 mt-1 w-56 -translate-x-1/2 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] px-2 py-1.5 text-[10px] leading-4 text-[color:var(--text-primary)] opacity-0 shadow-[var(--shadow-card)] transition-opacity group-hover:opacity-100">
                      Целевой уровень pH раствора в ночной период.
                    </span>
                  </span>
                </div>
                <input
                  v-model.number="phase.ph_night"
                  type="number"
                  step="0.1"
                  class="input-field h-9 w-full"
                  placeholder="pH ночь"
                />
              </div>
              <div class="space-y-1">
                <div class="flex items-center gap-1">
                  <span class="text-xs text-[color:var(--text-muted)]">EC (день)</span>
                  <span class="group relative inline-flex cursor-help items-center">
                    <span class="inline-flex h-4 w-4 items-center justify-center rounded-full border border-[color:var(--border-muted)] text-[10px] text-[color:var(--text-dim)]">i</span>
                    <span class="pointer-events-none absolute left-1/2 top-full z-50 mt-1 w-56 -translate-x-1/2 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] px-2 py-1.5 text-[10px] leading-4 text-[color:var(--text-primary)] opacity-0 shadow-[var(--shadow-card)] transition-opacity group-hover:opacity-100">
                      Электропроводность (EC) питательного раствора днем.
                    </span>
                  </span>
                </div>
                <input
                  v-model.number="phase.ec_day"
                  type="number"
                  step="0.1"
                  class="input-field h-9 w-full"
                  placeholder="EC день"
                />
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
              <div class="space-y-1">
                <div class="flex items-center gap-1">
                  <span class="text-xs text-[color:var(--text-muted)]">EC (ночь)</span>
                  <span class="group relative inline-flex cursor-help items-center">
                    <span class="inline-flex h-4 w-4 items-center justify-center rounded-full border border-[color:var(--border-muted)] text-[10px] text-[color:var(--text-dim)]">i</span>
                    <span class="pointer-events-none absolute left-1/2 top-full z-50 mt-1 w-56 -translate-x-1/2 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] px-2 py-1.5 text-[10px] leading-4 text-[color:var(--text-primary)] opacity-0 shadow-[var(--shadow-card)] transition-opacity group-hover:opacity-100">
                      Электропроводность (EC) питательного раствора ночью.
                    </span>
                  </span>
                </div>
                <input
                  v-model.number="phase.ec_night"
                  type="number"
                  step="0.1"
                  class="input-field h-9 w-full"
                  placeholder="EC ночь"
                />
              </div>
              <div class="space-y-1">
                <div class="flex items-center gap-1">
                  <span class="text-xs text-[color:var(--text-muted)]">Температура (день), °C</span>
                  <span class="group relative inline-flex cursor-help items-center">
                    <span class="inline-flex h-4 w-4 items-center justify-center rounded-full border border-[color:var(--border-muted)] text-[10px] text-[color:var(--text-dim)]">i</span>
                    <span class="pointer-events-none absolute left-1/2 top-full z-50 mt-1 w-56 -translate-x-1/2 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] px-2 py-1.5 text-[10px] leading-4 text-[color:var(--text-primary)] opacity-0 shadow-[var(--shadow-card)] transition-opacity group-hover:opacity-100">
                      Целевая температура воздуха в дневной период.
                    </span>
                  </span>
                </div>
                <input
                  v-model.number="phase.temp_day"
                  type="number"
                  step="0.1"
                  class="input-field h-9 w-full"
                  placeholder="T день, °C"
                />
              </div>
              <div class="space-y-1">
                <div class="flex items-center gap-1">
                  <span class="text-xs text-[color:var(--text-muted)]">Температура (ночь), °C</span>
                  <span class="group relative inline-flex cursor-help items-center">
                    <span class="inline-flex h-4 w-4 items-center justify-center rounded-full border border-[color:var(--border-muted)] text-[10px] text-[color:var(--text-dim)]">i</span>
                    <span class="pointer-events-none absolute left-1/2 top-full z-50 mt-1 w-56 -translate-x-1/2 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] px-2 py-1.5 text-[10px] leading-4 text-[color:var(--text-primary)] opacity-0 shadow-[var(--shadow-card)] transition-opacity group-hover:opacity-100">
                      Целевая температура воздуха в ночной период.
                    </span>
                  </span>
                </div>
                <input
                  v-model.number="phase.temp_night"
                  type="number"
                  step="0.1"
                  class="input-field h-9 w-full"
                  placeholder="T ночь, °C"
                />
              </div>
              <div class="space-y-1">
                <div class="flex items-center gap-1">
                  <span class="text-xs text-[color:var(--text-muted)]">Влажность (день), %</span>
                  <span class="group relative inline-flex cursor-help items-center">
                    <span class="inline-flex h-4 w-4 items-center justify-center rounded-full border border-[color:var(--border-muted)] text-[10px] text-[color:var(--text-dim)]">i</span>
                    <span class="pointer-events-none absolute left-1/2 top-full z-50 mt-1 w-56 -translate-x-1/2 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] px-2 py-1.5 text-[10px] leading-4 text-[color:var(--text-primary)] opacity-0 shadow-[var(--shadow-card)] transition-opacity group-hover:opacity-100">
                      Целевая относительная влажность воздуха днем.
                    </span>
                  </span>
                </div>
                <input
                  v-model.number="phase.humidity_day"
                  type="number"
                  step="1"
                  class="input-field h-9 w-full"
                  placeholder="Влажн. день, %"
                />
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div class="space-y-1">
                <div class="flex items-center gap-1">
                  <span class="text-xs text-[color:var(--text-muted)]">Влажность (ночь), %</span>
                  <span class="group relative inline-flex cursor-help items-center">
                    <span class="inline-flex h-4 w-4 items-center justify-center rounded-full border border-[color:var(--border-muted)] text-[10px] text-[color:var(--text-dim)]">i</span>
                    <span class="pointer-events-none absolute left-1/2 top-full z-50 mt-1 w-56 -translate-x-1/2 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] px-2 py-1.5 text-[10px] leading-4 text-[color:var(--text-primary)] opacity-0 shadow-[var(--shadow-card)] transition-opacity group-hover:opacity-100">
                      Целевая относительная влажность воздуха ночью.
                    </span>
                  </span>
                </div>
                <input
                  v-model.number="phase.humidity_night"
                  type="number"
                  step="1"
                  class="input-field h-9 w-full"
                  placeholder="Влажн. ночь, %"
                />
              </div>
              <div class="space-y-1">
                <div class="flex items-center gap-1">
                  <span class="text-xs text-[color:var(--text-muted)]">Интервал полива, сек</span>
                  <span class="group relative inline-flex cursor-help items-center">
                    <span class="inline-flex h-4 w-4 items-center justify-center rounded-full border border-[color:var(--border-muted)] text-[10px] text-[color:var(--text-dim)]">i</span>
                    <span class="pointer-events-none absolute left-1/2 top-full z-50 mt-1 w-56 -translate-x-1/2 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] px-2 py-1.5 text-[10px] leading-4 text-[color:var(--text-primary)] opacity-0 shadow-[var(--shadow-card)] transition-opacity group-hover:opacity-100">
                      Пауза между поливами в рамках фазы. 0 — без авто-полива по таймеру.
                    </span>
                  </span>
                </div>
                <input
                  v-model.number="phase.irrigation_interval_sec"
                  type="number"
                  min="0"
                  class="input-field h-9 w-full"
                  placeholder="Интервал полива, сек"
                />
              </div>
              <div class="space-y-1">
                <div class="flex items-center gap-1">
                  <span class="text-xs text-[color:var(--text-muted)]">Длительность полива, сек</span>
                  <span class="group relative inline-flex cursor-help items-center">
                    <span class="inline-flex h-4 w-4 items-center justify-center rounded-full border border-[color:var(--border-muted)] text-[10px] text-[color:var(--text-dim)]">i</span>
                    <span class="pointer-events-none absolute left-1/2 top-full z-50 mt-1 w-56 -translate-x-1/2 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] px-2 py-1.5 text-[10px] leading-4 text-[color:var(--text-primary)] opacity-0 shadow-[var(--shadow-card)] transition-opacity group-hover:opacity-100">
                      Сколько секунд длится один цикл полива в данной фазе.
                    </span>
                  </span>
                </div>
                <input
                  v-model.number="phase.irrigation_duration_sec"
                  type="number"
                  min="0"
                  class="input-field h-9 w-full"
                  placeholder="Длительность полива, сек"
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div
        v-if="errors.general"
        class="text-sm text-[color:var(--accent-red)]"
      >
        {{ errors.general }}
      </div>
    </form>

    <template #footer>
      <Button
        v-if="currentStep === 2 && !createdPlantId"
        type="button"
        variant="secondary"
        :disabled="loading"
        @click="goBack"
      >
        Назад
      </Button>
      <Button
        type="button"
        :disabled="loading || isPrimaryDisabled"
        @click="onSubmit"
      >
        {{ loading ? 'Создание...' : primaryLabel }}
      </Button>
    </template>
  </Modal>

  <TaxonomyWizardModal
    :show="taxonomyWizard.open"
    :title="taxonomyWizard.title"
    :taxonomy-key="taxonomyWizard.key"
    :items="taxonomyWizardItems"
    @close="closeTaxonomyWizard"
    @saved="handleTaxonomySaved"
  />
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'
import TaxonomyWizardModal from '@/Components/TaxonomyWizardModal.vue'
import { usePlantCreateModal, type TaxonomyOption } from '@/composables/usePlantCreateModal'

interface Props {
  show?: boolean
  taxonomies?: Record<string, TaxonomyOption[]>
}

const props = withDefaults(defineProps<Props>(), {
  show: false,
  taxonomies: () => ({}),
})

const emit = defineEmits<{
  close: []
  created: [plant: unknown]
}>()

const {
  loading,
  errors,
  currentStep,
  createdPlantId,
  taxonomyOptions,
  seasonOptions,
  taxonomyWizard,
  taxonomyWizardItems,
  form,
  showSubstrateSelector,
  addRecipePhase,
  removeRecipePhase,
  openTaxonomyWizard,
  closeTaxonomyWizard,
  handleTaxonomySaved,
  handleClose,
  stepTitle,
  primaryLabel,
  isPrimaryDisabled,
  goBack,
  onSubmit,
} = usePlantCreateModal({
  show: toRef(props, 'show'),
  taxonomies: toRef(props, 'taxonomies'),
  onClose: () => emit('close'),
  onCreated: (plant) => emit('created', plant),
})
</script>
