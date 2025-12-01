<template>
  <Card>
    <div class="space-y-4">
      <div class="flex items-center gap-2 border-b border-neutral-800">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          @click="activeTab = tab.id"
          :class="[
            'px-4 py-2 text-sm font-medium transition-colors border-b-2',
            activeTab === tab.id
              ? 'border-sky-500 text-sky-400'
              : 'border-transparent text-neutral-400 hover:text-neutral-300'
          ]"
        >
          {{ tab.label }}
        </button>
      </div>

      <div v-if="activeTab === 'settings'">
        <PidConfigForm :zone-id="zoneId" @saved="onConfigSaved" />
      </div>

      <div v-if="activeTab === 'logs'">
        <PidLogsTable :zone-id="zoneId" />
      </div>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import Card from './Card.vue'
import PidConfigForm from './PidConfigForm.vue'
import PidLogsTable from './PidLogsTable.vue'
import type { PidConfigWithMeta } from '@/types/PidConfig'

interface Props {
  zoneId: number
}

const props = defineProps<Props>()

const activeTab = ref<'settings' | 'logs'>('settings')

const tabs = [
  { id: 'settings' as const, label: 'PID Settings' },
  { id: 'logs' as const, label: 'PID Logs' },
]

function onConfigSaved(config: PidConfigWithMeta) {
  // Можно добавить уведомление об успешном сохранении
  logger.info('PID config saved:', { config })
}
</script>

