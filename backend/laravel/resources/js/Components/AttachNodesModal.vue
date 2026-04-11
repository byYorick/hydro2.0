<template>
  <Modal
    :open="show"
    title="Привязать узлы к зоне"
    @close="$emit('close')"
  >
    <div
      v-if="loading"
      class="text-sm text-[color:var(--text-muted)]"
    >
      Загрузка...
    </div>
    <div
      v-else
      class="space-y-4"
    >
      <div class="text-xs text-[color:var(--text-muted)] mb-2">
        Выберите узлы для привязки к зоне {{ zoneId }}
      </div>
      
      <div
        v-if="availableNodes.length === 0"
        class="text-sm text-[color:var(--text-muted)]"
      >
        Нет доступных узлов для привязки
      </div>
      
      <div
        v-else
        class="space-y-2 max-h-[400px] overflow-y-auto"
      >
        <label
          v-for="node in availableNodes"
          :key="node.id"
          :for="`attach-node-${node.id}`"
          class="flex items-center gap-2 p-2 rounded border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] hover:border-[color:var(--border-strong)] cursor-pointer"
        >
          <input
            :id="`attach-node-${node.id}`"
            v-model="selectedNodeIds"
            :name="`node_${node.id}`"
            type="checkbox"
            :value="node.id"
            class="h-4 w-4 rounded border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] text-[color:var(--accent-green)] focus:outline-none focus:ring-2 focus:ring-[color:var(--focus-ring)]"
          />
          <div class="flex-1">
            <div class="text-sm font-semibold">{{ node.uid || node.name || `Node ${node.id}` }}</div>
            <div class="text-xs text-[color:var(--text-muted)]">
              {{ node.type || 'unknown' }} — {{ node.status || 'offline' }}
            </div>
          </div>
        </label>
      </div>
    </div>
    
    <template #footer>
      <Button
        size="sm"
        variant="secondary"
        @click="$emit('close')"
      >
        Отмена
      </Button>
      <Button
        size="sm"
        :disabled="selectedNodeIds.length === 0 || attaching"
        @click="onAttach"
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
import { api } from '@/services/api'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import type { Device } from '@/types'

const { showToast } = useToast()

interface Props {
  show: boolean
  zoneId: number
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
    availableNodes.value = await api.nodes.list({ unassigned: true })
  } catch (error) {
    // Ошибка уже обработана в apiClient через глобальный showToast
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
    const updatedDevices = await Promise.all(
      selectedNodeIds.value.map((nodeId) => api.nodes.update(nodeId, { zone_id: props.zoneId })),
    )

    // Обновляем устройства в store из ответов API
    try {
      const { useDevicesStore } = await import('@/stores/devices')
      const devicesStore = useDevicesStore()

      for (const updatedDevice of updatedDevices) {
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
    // Ошибка уже обработана в apiClient через глобальный showToast
    logger.error('Failed to attach nodes:', error)
  } finally {
    attaching.value = false
  }
}
</script>
