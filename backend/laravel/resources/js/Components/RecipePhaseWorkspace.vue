<template>
  <div :class="enabled ? 'recipe-phase-workspace' : 'space-y-3'">
    <nav
      v-if="enabled"
      class="flex gap-2 overflow-x-auto pb-2"
      aria-label="Выбор фазы рецепта"
    >
      <button
        v-for="(phase, index) in phases"
        :key="phase.id || index"
        type="button"
        class="btn min-h-11 shrink-0 text-xs"
        :class="selectedIndex === index ? 'btn-outline' : 'btn-ghost'"
        :aria-pressed="selectedIndex === index"
        @click="selectedIndex = index"
      >
        {{ index + 1 }}. {{ phase.name || 'Новая фаза' }} · {{ Math.round(phase.duration_hours / 24) }} дн.
      </button>
    </nav>
    <slot :is-visible="isVisible"></slot>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, type VNodeChild } from 'vue'
import type { RecipePhaseFormState } from '@/composables/recipeEditorShared'

const props = defineProps<{ phases: RecipePhaseFormState[]; enabled: boolean }>()
defineSlots<{ default(props: { isVisible: (index: number) => boolean }): VNodeChild }>()
const selectedIndex = ref(0)
watch(() => props.phases.length, (length, previous) => {
  selectedIndex.value = length > previous ? Math.max(0, length - 1) : Math.min(selectedIndex.value, Math.max(0, length - 1))
})
function isVisible(index: number): boolean {
  return !props.enabled || selectedIndex.value === index
}
</script>

<style scoped>
.recipe-phase-workspace { display: grid; gap: 1rem; min-width: 0; }
@media (min-width: 1400px) {
  .recipe-phase-workspace { grid-template-columns: 10rem minmax(0, 1fr); align-items: start; }
  .recipe-phase-workspace > nav { grid-column: 1; flex-direction: column; position: sticky; top: 1rem; }
  .recipe-phase-workspace > nav button { white-space: normal; text-align: left; justify-content: flex-start; }
  .recipe-phase-workspace > :deep(section) { grid-column: 2; grid-row: 1; min-width: 0; }
}
</style>
