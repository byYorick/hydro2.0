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
          :for="`attach-node-${node.id}`"
          class="flex items-center gap-2 p-2 rounded border border-neutral-700 hover:border-neutral-600 cursor-pointer"
        >
          <input
            :id="`attach-node-${node.id}`"
            :name="`node_${node.id}`"
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
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import type { Device } from '@/types'

const { showToast } = useToast()
const { api } = useApi(showToast)

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

const loading = ref<boolean>(false)
const attaching = ref<boolean>(false)
const availableNodes = ref<Device[]>([])
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

async function loadAvailableNodes(): Promise<void> {
  loading.value = true
  try {
    const response = await api.get<{ data?: Device[] } | Device[]>(
      '/nodes',
      { params: { unassigned: true } }
    )
    
    const data = (response.data as { data?: Device[] })?.data || (response.data as Device[])
    availableNodes.value = Array.isArray(data) ? data : []
  } catch (error) {
    // Ошибка уже обработана в useApi через showToast
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
      api.patch(`/nodes/${nodeId}`, {
        zone_id: props.zoneId
      })
    )
    
    const responses = await Promise.all(promises)
    
    // Обновляем устройства в store из ответов API
    try {
      const { useDevicesStore } = await import('@/stores/devices')
      const devicesStore = useDevicesStore()
      
      // Извлекаем обновленные устройства из ответов
      for (const response of responses) {
        const updatedDevice = response.data?.data || response.data
        if (updatedDevice?.id) {
          devicesStore.upsert(updatedDevice)
          logger.debug('[AttachNodesModal] Device updated in store', { deviceId: updatedDevice.id })
        }
      }
    } catch (storeError) {
      logger.warn('[AttachNodesModal] Failed to update devices store', { error: storeError })
    }
    
    showToast(`Успешно привязано узлов: ${selectedNodeIds.value.length}`, 'success', TOAST_TIMEOUT.NORMAL)
    emit('attached', selectedNodeIds.value)
    emit('close')
  } catch (error) {
    // Ошибка уже обработана в useApi через showToast
    logger.error('Failed to attach nodes:', error)
  } finally {
    attaching.value = false
  }
}
</script>

