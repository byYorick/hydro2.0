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
        v-if="bindError"
        role="alert"
        class="rounded-md border border-red-500/35 bg-red-500/10 px-3 py-2 text-sm text-red-200 dark:border-red-500/40 dark:bg-red-950/40 dark:text-red-100"
      >
        {{ bindError }}
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
import { extractHumanErrorMessage } from '@/utils/errorMessage'
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
const bindError = ref<string | null>(null)

watch(() => props.show, (show) => {
  if (show) {
    bindError.value = null
    loadAvailableNodes()
  }
})

onMounted(() => {
  if (props.show) {
    bindError.value = null
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
  bindError.value = null
  const succeededIds: number[] = []
  const failedIds: number[] = []
  const updatedDevices: Device[] = []

  try {
    for (const nodeId of selectedNodeIds.value) {
      try {
        const updated = await api.nodes.update(nodeId, { zone_id: props.zoneId }, { skipErrorToast: true })
        updatedDevices.push(updated)
        succeededIds.push(nodeId)
      } catch (error) {
        failedIds.push(nodeId)
        logger.error('Failed to attach node:', { nodeId, error })
        if (failedIds.length === 1 && succeededIds.length === 0) {
          bindError.value = extractHumanErrorMessage(
            error,
            'Не удалось привязать узел к зоне. Проверьте сообщение выше и отвяжите конфликтующее оборудование при необходимости.',
          )
        }
      }
    }

    if (succeededIds.length === 0) {
      return
    }

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

    const pendingHint = 'Ожидается config_report от узла — привязка завершится после ACK конфига.'
    if (failedIds.length === 0) {
      showToast(
        `Запрошена привязка узлов: ${succeededIds.length}. ${pendingHint}`,
        'info',
        TOAST_TIMEOUT.NORMAL,
      )
    } else {
      showToast(
        `Привязка: успешно ${succeededIds.length}, ошибок ${failedIds.length}. ${pendingHint}`,
        'warning',
        TOAST_TIMEOUT.NORMAL,
      )
    }
    emit('attached', succeededIds)
    emit('close')
  } finally {
    attaching.value = false
  }
}
</script>
