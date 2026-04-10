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
            type="text"
            class="input-field h-9 w-full"
            :class="errors.name ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''"
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
            type="text"
            class="input-field h-9 w-full"
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
            type="text"
            class="input-field h-9 w-full"
          />
        </div>

        <div>
          <div class="flex items-center gap-2">
            <div class="flex h-9 flex-1 items-center rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)]">
              <select
                id="plant-system"
                v-model="form.growing_system"
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
              +
            </button>
          </div>
          <div
            v-if="errors.growing_system"
            class="text-xs text-[color:var(--accent-red)] mt-1"
          >
            {{ errors.growing_system }}
          </div>
        </div>

        <div v-if="showSubstrateSelector">
          <div class="flex items-center gap-2">
            <div class="flex h-9 flex-1 items-center rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)]">
              <select
                id="plant-substrate"
                v-model="form.substrate_type"
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
              +
            </button>
          </div>
        </div>

        <div>
          <div class="flex items-center gap-2">
            <div class="flex h-9 flex-1 items-center rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)]">
              <select
                id="plant-seasonality"
                v-model="form.seasonality"
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
              +
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
            rows="3"
            class="input-field w-full"
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
        <RecipeEditor
          v-model:form="recipeForm"
          :plants="[]"
          :npk-products="npkProducts"
          :calcium-products="calciumProducts"
          :magnesium-products="magnesiumProducts"
          :micro-products="microProducts"
          :hide-plant-select="true"
          :locked-plant-label="form.name"
          @add-phase="addRecipePhase"
          @remove-phase="removeRecipePhase"
        />
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
        v-if="currentStep === 2"
        type="button"
        variant="secondary"
        :disabled="loading"
        @click="goBack"
      >
        Назад
      </Button>
      <Button
        type="button"
        :disabled="isPrimaryDisabled"
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
import RecipeEditor from '@/Components/RecipeEditor.vue'
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
  taxonomyOptions,
  seasonOptions,
  taxonomyWizard,
  taxonomyWizardItems,
  form,
  recipeForm,
  npkProducts,
  calciumProducts,
  magnesiumProducts,
  microProducts,
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
