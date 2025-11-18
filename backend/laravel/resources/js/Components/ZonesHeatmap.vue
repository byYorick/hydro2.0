<template>
  <Card>
    <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
      <div
        v-for="(count, status) in zonesByStatus"
        :key="status"
        class="p-4 rounded-lg border-2 transition-all hover:scale-105 cursor-pointer"
        :class="getStatusClasses(status)"
        @click="$emit('filter', status)"
      >
        <div class="text-xs text-neutral-400 mb-1">{{ translateStatus(status) }}</div>
        <div class="text-2xl font-bold">{{ count || 0 }}</div>
      </div>
    </div>
    
    <!-- Легенда -->
    <div class="mt-4 flex flex-wrap gap-4 text-xs text-neutral-400">
      <div class="flex items-center gap-2">
        <div class="w-3 h-3 rounded bg-emerald-500"></div>
        <span>Запущено</span>
      </div>
      <div class="flex items-center gap-2">
        <div class="w-3 h-3 rounded bg-neutral-500"></div>
        <span>Приостановлено</span>
      </div>
      <div class="flex items-center gap-2">
        <div class="w-3 h-3 rounded bg-amber-500"></div>
        <span>Предупреждение</span>
      </div>
      <div class="flex items-center gap-2">
        <div class="w-3 h-3 rounded bg-red-500"></div>
        <span>Тревога</span>
      </div>
    </div>
  </Card>
</template>

<script setup>
import { computed } from 'vue'
import Card from '@/Components/Card.vue'
import { translateStatus } from '@/utils/i18n'

const props = defineProps({
  zonesByStatus: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['filter'])

function getStatusClasses(status) {
  const classes = {
    'RUNNING': 'bg-emerald-500/10 border-emerald-500/50 hover:border-emerald-500',
    'PAUSED': 'bg-neutral-500/10 border-neutral-500/50 hover:border-neutral-500',
    'WARNING': 'bg-amber-500/10 border-amber-500/50 hover:border-amber-500',
    'ALARM': 'bg-red-500/10 border-red-500/50 hover:border-red-500',
  }
  return classes[status] || 'bg-neutral-800/10 border-neutral-700/50'
}
</script>

