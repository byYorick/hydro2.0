<template>
  <div
    v-if="previewPhases.length > 0"
    class="rounded-md border border-[color:var(--border-muted)] p-2.5 space-y-3"
    data-testid="recipe-editor-preview"
  >
    <div class="flex items-center justify-between gap-2">
      <div class="text-[12px] font-bold uppercase tracking-[0.16em] text-[color:var(--text-muted)]">
        Превью рецепта
      </div>
      <button
        type="button"
        class="text-[11px] text-[color:var(--status-info)] hover:underline"
        data-testid="recipe-editor-preview-toggle"
        @click="previewOpen = !previewOpen"
      >
        {{ previewOpen ? 'Свернуть' : 'Развернуть' }}
      </button>
    </div>

    <template v-if="previewOpen">
      <RecipeSummaryStats :summary="previewSummary" />
      <RecipePhaseTimeline :phases="previewPhases" />
      <RecipePhaseChartsPanel :phases="previewPhases" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { RecipePhaseFormState } from '@/composables/recipeEditorShared'
import RecipePhaseChartsPanel from '@/Components/Recipes/RecipePhaseChartsPanel.vue'
import RecipePhaseTimeline from '@/Components/Recipes/RecipePhaseTimeline.vue'
import RecipeSummaryStats from '@/Components/Recipes/RecipeSummaryStats.vue'
import { buildRecipePhaseVisuals, summarizeRecipePhases } from '@/utils/recipeVisualization'
const props = defineProps<{ phases: RecipePhaseFormState[]; singlePhase: boolean }>()
const previewOpen = ref(!props.singlePhase)
const previewPhases = computed(() => buildRecipePhaseVisuals(props.phases))
const previewSummary = computed(() => summarizeRecipePhases(previewPhases.value))
</script>
