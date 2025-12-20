<template>
  <Badge
    :variant="badgeVariant"
    :style="badgeStyle"
    class="font-semibold"
  >
    <span v-if="stageInfo?.icon" class="mr-1">{{ stageInfo.icon }}</span>
    {{ stageInfo?.label || 'Неизвестно' }}
  </Badge>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Badge from './Badge.vue'
import { getStageInfo, type GrowStage } from '@/utils/growStages'

interface Props {
  stage: GrowStage | null
  variant?: 'default' | 'outline' | 'subtle'
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'default',
})

const stageInfo = computed(() => getStageInfo(props.stage))

const badgeVariant = computed(() => {
  if (!props.stage) return 'neutral'
  
  switch (props.stage) {
    case 'planting':
      return 'info'
    case 'rooting':
      return 'info'
    case 'veg':
      return 'success'
    case 'flowering':
      return 'warning'
    case 'harvest':
      return 'danger'
    default:
      return 'neutral'
  }
})

const badgeStyle = computed(() => {
  if (props.variant === 'default' && stageInfo.value) {
    return {
      backgroundColor: `color-mix(in srgb, ${stageInfo.value.color} 15%, transparent)`,
      color: stageInfo.value.color,
      borderColor: `color-mix(in srgb, ${stageInfo.value.color} 40%, transparent)`,
    }
  }
  return {}
})
</script>
