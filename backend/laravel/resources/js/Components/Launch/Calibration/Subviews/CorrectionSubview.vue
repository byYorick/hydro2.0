<template>
  <div class="flex flex-col gap-3.5">
    <CorrectionConfigForm
      :zone-id="zoneId"
      @saved="$emit('saved')"
    />
    <Hint :show="showHints">
      Authority-редактор: recipe / zone / manual. PUT
      <span class="font-mono">/api/automation-configs/zone/{'{id}'}/zone.correction</span>.
      Целевые значения targetPh/targetEc остаются read-only из активной
      фазы рецепта (см. шаг 3 Автоматика → Коррекция).
    </Hint>
  </div>
</template>

<script setup lang="ts">
import CorrectionConfigForm from '@/Components/CorrectionConfigForm.vue'
import { Hint } from '@/Components/Shared/Primitives'
import { useLaunchPreferences } from '@/composables/useLaunchPreferences'

defineProps<{ zoneId: number }>()
defineEmits<{ (e: 'saved'): void }>()

const { showHints } = useLaunchPreferences()
</script>
