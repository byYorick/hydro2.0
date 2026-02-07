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

        <div v-if="showSubstrateSelector">
          <div class="flex items-center justify-between mb-1">
            <label
              for="plant-substrate"
              class="block text-xs text-[color:var(--text-muted)]"
            >Субстрат</label>
          </div>
          <div class="relative flex items-center h-9 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)]">
            <select
              id="plant-substrate"
              v-model="form.substrate_type"
              name="substrate_type"
              class="h-9 w-full bg-transparent border-none focus:ring-0 focus:outline-none appearance-none px-2 pr-11"
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
            <Button
              type="button"
              size="sm"
              variant="ghost"
              class="absolute right-1 top-1/2 h-7 w-7 -translate-y-1/2 p-0 border border-[color:var(--border-muted)] rounded-md bg-[color:var(--bg-elevated)]"
              @click="openTaxonomyWizard('substrate_type')"
            >
              <svg
                class="h-3.5 w-3.5 text-[color:var(--text-primary)]"
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
            </Button>
          </div>
        </div>

        <div>
          <div class="flex items-center justify-between mb-1">
            <label
              for="plant-system"
              class="block text-xs text-[color:var(--text-muted)]"
            >Система</label>
          </div>
          <div class="relative flex items-center h-9 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)]">
            <select
              id="plant-system"
              v-model="form.growing_system"
              name="growing_system"
              class="h-9 w-full bg-transparent border-none focus:ring-0 focus:outline-none appearance-none px-2 pr-11"
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
            <Button
              type="button"
              size="sm"
              variant="ghost"
              class="absolute right-1 top-1/2 h-7 w-7 -translate-y-1/2 p-0 border border-[color:var(--border-muted)] rounded-md bg-[color:var(--bg-elevated)]"
              @click="openTaxonomyWizard('growing_system')"
            >
              <svg
                class="h-3.5 w-3.5 text-[color:var(--text-primary)]"
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
            </Button>
          </div>
          <p
            v-if="form.growing_system && !showSubstrateSelector"
            class="mt-1 text-[11px] text-[color:var(--text-dim)]"
          >
            Для выбранной системы субстрат не используется.
          </p>
        </div>

        <div>
          <label
            for="plant-photoperiod"
            class="block text-xs text-[color:var(--text-muted)] mb-1"
          >Фотопериод</label>
          <select
            id="plant-photoperiod"
            v-model="form.photoperiod_preset"
            name="photoperiod_preset"
            class="input-select h-9 w-full"
          >
            <option value="">
              Не выбрано
            </option>
            <option
              v-for="option in taxonomyOptions.photoperiod_preset"
              :key="option.id"
              :value="option.id"
            >
              {{ option.label }}
            </option>
          </select>
        </div>

        <div>
          <div class="flex items-center justify-between mb-1">
            <label
              for="plant-seasonality"
              class="block text-xs text-[color:var(--text-muted)]"
            >Сезонность</label>
          </div>
          <div class="relative flex items-center h-9 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)]">
            <select
              id="plant-seasonality"
              v-model="form.seasonality"
              name="seasonality"
              class="h-9 w-full bg-transparent border-none focus:ring-0 focus:outline-none appearance-none px-2 pr-11"
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
            <Button
              type="button"
              size="sm"
              variant="ghost"
              class="absolute right-1 top-1/2 h-7 w-7 -translate-y-1/2 p-0 border border-[color:var(--border-muted)] rounded-md bg-[color:var(--bg-elevated)]"
              @click="openTaxonomyWizard('seasonality')"
            >
              <svg
                class="h-3.5 w-3.5 text-[color:var(--text-primary)]"
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
            </Button>
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
          <label
            for="recipe-name"
            class="block text-xs text-[color:var(--text-muted)] mb-1"
          >
            Название рецепта <span class="text-[color:var(--accent-red)]">*</span>
          </label>
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
          <label
            for="recipe-description"
            class="block text-xs text-[color:var(--text-muted)] mb-1"
          >Описание рецепта</label>
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
              <input
                v-model="phase.name"
                type="text"
                class="input-field h-9"
                placeholder="Название фазы"
              />
              <input
                v-model.number="phase.duration_days"
                type="number"
                min="1"
                class="input-field h-9"
                placeholder="Дней"
              />
              <select
                v-model="phase.day_start_time"
                class="input-field h-9"
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

            <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
              <input
                v-model.number="phase.light_hours"
                type="number"
                min="0"
                max="24"
                class="input-field h-9"
                placeholder="Свет, ч/сут"
              />
              <input
                v-model.number="phase.ph_day"
                type="number"
                step="0.1"
                class="input-field h-9"
                placeholder="pH день"
              />
              <input
                v-model.number="phase.ph_night"
                type="number"
                step="0.1"
                class="input-field h-9"
                placeholder="pH ночь"
              />
              <input
                v-model.number="phase.ec_day"
                type="number"
                step="0.1"
                class="input-field h-9"
                placeholder="EC день"
              />
            </div>

            <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
              <input
                v-model.number="phase.ec_night"
                type="number"
                step="0.1"
                class="input-field h-9"
                placeholder="EC ночь"
              />
              <input
                v-model.number="phase.temp_day"
                type="number"
                step="0.1"
                class="input-field h-9"
                placeholder="T день, °C"
              />
              <input
                v-model.number="phase.temp_night"
                type="number"
                step="0.1"
                class="input-field h-9"
                placeholder="T ночь, °C"
              />
              <input
                v-model.number="phase.humidity_day"
                type="number"
                step="1"
                class="input-field h-9"
                placeholder="Влажн. день, %"
              />
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
              <input
                v-model.number="phase.humidity_night"
                type="number"
                step="1"
                class="input-field h-9"
                placeholder="Влажн. ночь, %"
              />
              <input
                v-model.number="phase.irrigation_interval_sec"
                type="number"
                min="0"
                class="input-field h-9"
                placeholder="Интервал полива, сек"
              />
              <input
                v-model.number="phase.irrigation_duration_sec"
                type="number"
                min="0"
                class="input-field h-9"
                placeholder="Длительность полива, сек"
              />
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
