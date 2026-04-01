<template>
  <Card>
    <div class="text-sm font-semibold mb-3">
      Циклы
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
      <CycleSubsystemCard
        v-for="cycle in cycles"
        :key="cycle.type"
        :cycle="cycle"
      />
    </div>
  </Card>
</template>

<script setup lang="ts">
import Card from '@/Components/Card.vue'
import CycleSubsystemCard from './CycleSubsystemCard.vue'
import type { SubsystemCycle } from '@/types/Cycle'

defineProps<{
  cycles: SubsystemCycle[]
}>()
</script>
