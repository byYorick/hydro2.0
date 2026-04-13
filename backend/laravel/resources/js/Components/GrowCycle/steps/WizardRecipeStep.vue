<template>
  <div class="space-y-4">
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
          @change="$emit('recipe-selected')"
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
          @created="(recipeId) => $emit('recipe-created', recipeId)"
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
      v-if="selectedRecipe && selectedRevision"
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
          v-for="(phase, index) in selectedRevision.phases ?? []"
          :key="index"
          class="flex items-center justify-between p-2 rounded bg-[color:var(--bg-surface-strong)]"
        >
          <div>
            <div class="text-xs font-medium">
              {{ phase.name || `Фаза ${index + 1}` }}
            </div>
            <div class="text-xs text-[color:var(--text-dim)]">
              {{ phaseDurationLabel(phase) }} дней
            </div>
          </div>
          <div class="text-xs text-[color:var(--text-muted)]">
            pH: {{ phase.ph_min ?? "-" }}–{{ phase.ph_max ?? "-" }} EC: {{ phase.ec_min ?? "-" }}–{{ phase.ec_max ?? "-" }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Button from "@/Components/Button.vue";
import RecipeCreateWizard from "@/Components/RecipeCreateWizard.vue";

interface RecipeListItem {
  id: number;
  name?: string;
  description?: string | null;
  phases_count?: number;
}

interface RecipeRevision {
  id: number;
  revision_number?: number | null;
  description?: string | null;
  phases?: RecipePhase[];
}

interface RecipePhase {
  name?: string | null;
  duration_days?: number | null;
  duration_hours?: number | null;
  ph_min?: number | null;
  ph_max?: number | null;
  ec_min?: number | null;
  ec_max?: number | null;
}

interface Props {
  availableRecipes: RecipeListItem[];
  selectedRecipe: RecipeListItem | null;
  availableRevisions: RecipeRevision[];
  selectedRevision: RecipeRevision | null;
}

defineProps<Props>();

defineEmits<{
  'recipe-selected': [];
  'recipe-created': [recipeId: number];
}>();

const recipeMode = defineModel<'select' | 'create'>('recipeMode', { required: true });
const selectedRecipeId = defineModel<number | null>('selectedRecipeId', { required: true });
const selectedRevisionId = defineModel<number | null>('selectedRevisionId', { required: true });

function phaseDurationLabel(phase: RecipePhase): string | number {
  if (phase.duration_days != null) {
    return phase.duration_days;
  }
  if (phase.duration_hours != null) {
    return Math.round(phase.duration_hours / 24);
  }
  return "-";
}
</script>
