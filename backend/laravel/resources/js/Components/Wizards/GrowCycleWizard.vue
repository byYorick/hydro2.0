<template>
  <GrowthCycleWizard v-bind="$attrs" />
</template>

<script setup lang="ts">
import GrowthCycleWizard from '@/Components/GrowCycle/GrowthCycleWizard.vue'

defineOptions({ inheritAttrs: false })
</script>
