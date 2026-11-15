<template>
  <div class="space-y-3">
    <div class="flex flex-wrap items-center gap-2">
      <span class="text-xs font-semibold text-[color:var(--text-muted)]">Режим редактора</span>
      <button
        type="button"
        class="rounded-lg border px-2.5 py-1 text-[11px] font-semibold"
        :class="editorMode === 'simple'
          ? 'border-[color:var(--border-strong)] bg-[color:var(--bg-elevated)] text-[color:var(--text-primary)]'
          : 'border-[color:var(--border-muted)] text-[color:var(--text-dim)]'"
        data-testid="recipe-editor-mode-simple"
        @click="editorMode = 'simple'"
      >
        Простой
      </button>
      <button
        type="button"
        class="rounded-lg border px-2.5 py-1 text-[11px] font-semibold"
        :class="editorMode === 'advanced'
          ? 'border-[color:var(--border-strong)] bg-[color:var(--bg-elevated)] text-[color:var(--text-primary)]'
          : 'border-[color:var(--border-muted)] text-[color:var(--text-dim)]'"
        data-testid="recipe-editor-mode-advanced"
        @click="editorMode = 'advanced'"
      >
        Расширенный
      </button>
    </div>
    <RecipeEditorIdentity
      v-model:form="form"
      :plants="plants"
      :plants-loading="plantsLoading"
      :hide-plant-select="hidePlantSelect"
      :locked-plant-label="lockedPlantLabel"
      @plant-created="emit('plant-created', $event)"
    />
    <div
      v-if="isAdvanced"
      class="rounded-md border border-[color:var(--border-muted)] p-3 space-y-2"
    >
      <div class="text-[12px] font-bold uppercase tracking-[0.16em] text-[color:var(--text-muted)]">
        Система подготовки раствора и полива
      </div>
      <div class="max-w-lg">
        <SelectField
          v-model="recipeIrrigationMode"
          class="w-full"
        >
          <option value="SUBSTRATE">
            Проточная (2 бака)
          </option>
          <option value="RECIRC">
            Рециркуляция (3 бака)
          </option>
        </SelectField>
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
    <RecipeEditorPreview
      :phases="sortedPhases"
      :single-phase="singlePhase"
    />
    <div class="text-xs font-semibold">
      Фазы роста
    </div>
    <RecipePhaseWorkspace
      v-slot="{ isVisible }"
      :phases="sortedPhases"
      :enabled="singlePhase"
    >
      <RecipePhaseEditor
        v-for="(phase, index) in sortedPhases"
        v-show="isVisible(index)"
        :key="phase.id || index"
        v-model:phase="form.phases[form.phases.indexOf(phase)]"
        :index="index"
        :can-remove="form.phases.length > 1"
        :is-advanced="isAdvanced"
        :recipe-irrigation-mode="recipeIrrigationMode"
        :substrate-options="substrateOptions(phase)"
        :npk-products="npkProducts"
        :calcium-products="calciumProducts"
        :magnesium-products="magnesiumProducts"
        :micro-products="microProducts"
        @remove="emit('remove-phase', form.phases.indexOf(phase))"
        @product-created="emit('product-created', $event)"
        @create-substrate="substrateModalOpen = true"
      />
    </RecipePhaseWorkspace>
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
        {{ saveLabel }}
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
import SelectField from '@/Components/SelectField.vue'

import { computed, ref } from 'vue'
import Button from '@/Components/Button.vue'
import RecipePhaseWorkspace from '@/Components/RecipePhaseWorkspace.vue'
import RecipeEditorIdentity from '@/Components/Recipes/Editor/RecipeEditorIdentity.vue'
import RecipeEditorPreview from '@/Components/Recipes/Editor/RecipeEditorPreview.vue'
import RecipePhaseEditor from '@/Components/Recipes/Editor/RecipePhaseEditor.vue'
import SubstrateCreateModal from '@/Components/SubstrateCreateModal.vue'
import { useRecipeIrrigation } from '@/composables/useRecipeIrrigation'
import { useRole } from '@/composables/useRole'
import type { NutrientProduct } from '@/types'
import type { PlantOption, RecipeEditorFormState, RecipePhaseFormState } from '@/composables/recipeEditorShared'
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
  singlePhase?: boolean
  saveLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  plantsLoading: false,
  substrates: () => [],
  hidePlantSelect: false,
  lockedPlantLabel: null,
  singlePhase: false,
  saveLabel: 'Сохранить',
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

const { isAdmin } = useRole()
const editorMode = ref<'simple' | 'advanced'>(isAdmin.value ? 'advanced' : 'simple')
const isAdvanced = computed(() => editorMode.value === 'advanced')

const substrateModalOpen = ref(false)
const { recipeIrrigationMode, substrateOptions, applyCreatedSubstrate } = useRecipeIrrigation(form, () => props.substrates)

function onSubstrateCreated(substrate: Substrate): void {
  emit('substrate-created', substrate)
  applyCreatedSubstrate(substrate)
  substrateModalOpen.value = false
}

const sortedPhases = computed<RecipePhaseFormState[]>(() => {
  return [...form.value.phases].sort((left, right) => left.phase_index - right.phase_index)
})

</script>
