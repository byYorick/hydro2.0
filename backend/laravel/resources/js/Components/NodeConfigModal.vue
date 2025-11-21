<template>
  <Modal :open="show" :title="`Настройка узла ${node?.uid || node?.id}`" @close="$emit('close')">
    <div v-if="loading" class="text-sm text-neutral-400">Загрузка конфигурации...</div>
    <div v-else class="space-y-4">
      <div class="text-xs text-neutral-400 mb-2">
        Настройте каналы узла. Конфигурация будет отправлена узлу через MQTT.
      </div>
      
      <div v-if="channels.length === 0" class="text-sm text-neutral-400">
        У узла нет настроенных каналов
      </div>
      
      <div v-else class="space-y-2 max-h-[400px] overflow-y-auto">
        <div
          v-for="(channel, index) in channels"
          :key="index"
          class="p-3 rounded border border-neutral-700"
        >
          <div class="grid grid-cols-1 md:grid-cols-3 gap-2">
            <div>
              <label class="block text-xs text-neutral-400 mb-1">Channel</label>
              <input
                v-model="channel.channel"
                type="text"
                placeholder="ph_sensor"
                class="h-8 w-full rounded-md border px-2 text-xs border-neutral-700 bg-neutral-900"
              />
            </div>
            <div>
              <label class="block text-xs text-neutral-400 mb-1">Type</label>
              <select
                v-model="channel.type"
                class="h-8 w-full rounded-md border px-2 text-xs border-neutral-700 bg-neutral-900"
              >
                <option value="sensor">Sensor</option>
                <option value="actuator">Actuator</option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-neutral-400 mb-1">Unit</label>
              <input
                v-model="channel.unit"
                type="text"
                placeholder="pH, mS/cm, etc."
                class="h-8 w-full rounded-md border px-2 text-xs border-neutral-700 bg-neutral-900"
              />
            </div>
          </div>
        </div>
      </div>
      
      <Button size="sm" variant="secondary" @click="addChannel">Добавить канал</Button>
    </div>
    
    <template #footer>
      <Button size="sm" variant="secondary" @click="$emit('close')">Отмена</Button>
      <Button
        size="sm"
        @click="onPublish"
        :disabled="publishing"
      >
        {{ publishing ? 'Отправка...' : 'Опубликовать конфигурацию' }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import Modal from './Modal.vue'
import Button from './Button.vue'
import axios from 'axios'
import { logger } from '@/utils/logger'
import { router } from '@inertiajs/vue3'

interface Props {
  show: boolean
  nodeId: number
  node?: {
    id: number
    uid: string
  }
}

interface Channel {
  channel: string
  type: 'sensor' | 'actuator'
  unit?: string
  min?: number
  max?: number
}

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
  published: []
}>()

const loading = ref(false)
const publishing = ref(false)
const channels = ref<Channel[]>([])

watch(() => props.show, (show) => {
  if (show) {
    loadNodeConfig()
  }
})

onMounted(() => {
  if (props.show) {
    loadNodeConfig()
  }
})

async function loadNodeConfig() {
  if (!props.nodeId) return
  
  loading.value = true
  try {
    const response = await axios.get(`/api/nodes/${props.nodeId}/config`, {
      headers: {
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
      }
    })
    
    if (response.data?.data?.channels) {
      channels.value = response.data.data.channels.map((ch: any) => ({
        channel: ch.channel || '',
        type: ch.type || 'sensor',
        unit: ch.unit || '',
        min: ch.min,
        max: ch.max
      }))
    } else {
      channels.value = []
    }
  } catch (error) {
    logger.error('Failed to load node config:', error)
    channels.value = []
  } finally {
    loading.value = false
  }
}

function addChannel() {
  channels.value.push({
    channel: '',
    type: 'sensor',
    unit: ''
  })
}

async function onPublish() {
  if (!props.nodeId) return
  
  publishing.value = true
  try {
    await axios.post(`/api/nodes/${props.nodeId}/config/publish`, {
      config: {
        channels: channels.value
      }
    }, {
      headers: {
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
      }
    })
    
    emit('published')
    emit('close')
    router.reload({ only: ['devices'] })
  } catch (error: any) {
    logger.error('Failed to publish node config:', error)
    alert(error.response?.data?.message || 'Ошибка при публикации конфигурации')
  } finally {
    publishing.value = false
  }
}
</script>

