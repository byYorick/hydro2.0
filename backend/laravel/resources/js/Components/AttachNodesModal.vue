<template>
  <Modal :open="show" title="Привязать узлы к зоне" @close="$emit('close')">
    <div v-if="loading" class="text-sm text-neutral-400">Загрузка...</div>
    <div v-else class="space-y-4">
      <div class="text-xs text-neutral-400 mb-2">
        Выберите узлы для привязки к зоне {{ zoneId }}
      </div>
      
      <div v-if="availableNodes.length === 0" class="text-sm text-neutral-400">
        Нет доступных узлов для привязки
      </div>
      
      <div v-else class="space-y-2 max-h-[400px] overflow-y-auto">
        <label
          v-for="node in availableNodes"
          :key="node.id"
          class="flex items-center gap-2 p-2 rounded border border-neutral-700 hover:border-neutral-600 cursor-pointer"
        >
          <input
            type="checkbox"
            :value="node.id"
            v-model="selectedNodeIds"
            class="rounded"
          />
          <div class="flex-1">
            <div class="text-sm font-semibold">{{ node.uid || node.name || `Node ${node.id}` }}</div>
            <div class="text-xs text-neutral-400">
              {{ node.type || 'unknown' }} — {{ node.status || 'offline' }}
            </div>
          </div>
        </label>
      </div>
    </div>
    
    <template #footer>
      <Button size="sm" variant="secondary" @click="$emit('close')">Отмена</Button>
      <Button
        size="sm"
        @click="onAttach"
        :disabled="selectedNodeIds.length === 0 || attaching"
      >
        {{ attaching ? 'Привязка...' : `Привязать (${selectedNodeIds.length})` }}
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
  zoneId: number
}

interface Node {
  id: number
  uid: string
  name?: string
  type?: string
  status?: string
  zone_id?: number | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
  attached: [nodeIds: number[]]
}>()

const loading = ref(false)
const attaching = ref(false)
const availableNodes = ref<Node[]>([])
const selectedNodeIds = ref<number[]>([])

watch(() => props.show, (show) => {
  if (show) {
    loadAvailableNodes()
  }
})

onMounted(() => {
  if (props.show) {
    loadAvailableNodes()
  }
})

async function loadAvailableNodes() {
  loading.value = true
  try {
    const response = await axios.get('/api/nodes?unassigned=true', {
      headers: {
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
      }
    })
    
    const data = response.data?.data
    availableNodes.value = (data?.data || (Array.isArray(data) ? data : [])) || []
  } catch (error) {
    logger.error('Failed to load available nodes:', error)
  } finally {
    loading.value = false
  }
}

async function onAttach() {
  if (selectedNodeIds.value.length === 0) return
  
  attaching.value = true
  try {
    // Привязываем каждый узел к зоне
    const promises = selectedNodeIds.value.map(nodeId =>
      axios.patch(`/api/nodes/${nodeId}`, {
        zone_id: props.zoneId
      }, {
        headers: {
          'Accept': 'application/json',
          'X-Requested-With': 'XMLHttpRequest'
        }
      })
    )
    
    await Promise.all(promises)
    
    emit('attached', selectedNodeIds.value)
    emit('close')
    router.reload({ only: ['zone', 'devices'] })
  } catch (error: any) {
    logger.error('Failed to attach nodes:', error)
    alert(error.response?.data?.message || 'Ошибка при привязке узлов')
  } finally {
    attaching.value = false
  }
}
</script>

