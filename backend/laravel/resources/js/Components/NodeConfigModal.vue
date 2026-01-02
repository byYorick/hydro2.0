<template>
  <Modal
    :open="show"
    :title="`Конфигурация узла ${node?.uid || node?.id}`"
    @close="handleClose"
  >
    <div class="space-y-4">
      <div class="text-xs text-[color:var(--text-muted)]">
        Конфиг приходит от ноды через config_report. Редактирование отключено; изменения вносятся в прошивке или локальном provisioning.
      </div>

      <div
        v-if="errorMessage"
        class="text-xs text-[color:var(--badge-warning-text)] bg-[color:var(--badge-warning-bg)] border border-[color:var(--badge-warning-border)] rounded-lg p-3"
      >
        {{ errorMessage }}
      </div>

      <div
        v-if="loading"
        class="text-sm text-[color:var(--text-muted)]"
      >
        Загрузка конфигурации...
      </div>

      <div
        v-else
        class="space-y-3"
      >
        <div
          v-if="channels.length === 0"
          class="text-sm text-[color:var(--text-muted)]"
        >
          Нет данных по каналам
        </div>
        <div
          v-else
          class="rounded-lg border border-[color:var(--border-muted)] overflow-hidden"
        >
          <table class="min-w-full text-xs">
            <thead class="bg-[color:var(--bg-elevated)] text-[color:var(--text-muted)]">
              <tr>
                <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]">
                  Channel
                </th>
                <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]">
                  Type
                </th>
                <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]">
                  Metric
                </th>
                <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]">
                  Actuator
                </th>
                <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]">
                  Unit
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(channel, index) in channels"
                :key="`${channel.name}-${index}`"
                class="odd:bg-[color:var(--bg-surface-strong)] even:bg-[color:var(--bg-surface)]"
              >
                <td class="px-3 py-2 border-b border-[color:var(--border-muted)]">
                  {{ channel.name }}
                </td>
                <td class="px-3 py-2 border-b border-[color:var(--border-muted)] uppercase">
                  {{ channel.type }}
                </td>
                <td class="px-3 py-2 border-b border-[color:var(--border-muted)]">
                  {{ channel.metric || '-' }}
                </td>
                <td class="px-3 py-2 border-b border-[color:var(--border-muted)]">
                  {{ channel.actuator_type || '-' }}
                </td>
                <td class="px-3 py-2 border-b border-[color:var(--border-muted)]">
                  {{ channel.unit || '-' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="space-y-2">
          <div class="text-xs text-[color:var(--text-dim)]">
            Полный JSON
          </div>
          <pre class="text-xs text-[color:var(--text-muted)] overflow-auto">{{ prettyConfig }}</pre>
        </div>
      </div>
    </div>

    <template #footer>
      <Button
        size="sm"
        variant="secondary"
        @click="handleClose"
      >
        Закрыть
      </Button>
      <Button
        size="sm"
        variant="outline"
        :disabled="loading"
        @click="loadNodeConfig"
      >
        {{ loading ? 'Обновление...' : 'Обновить' }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import Modal from './Modal.vue'
import Button from './Button.vue'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

interface Props {
  show: boolean
  nodeId: number
  node?: {
    id: number
    uid: string
  }
}

interface ChannelView {
  name: string
  type: string
  metric?: string | null
  actuator_type?: string | null
  unit?: string | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
}>()

const { showToast } = useToast()
const { api } = useApi(showToast)

const loading = ref<boolean>(false)
const nodeConfigData = ref<Record<string, any> | null>(null)
const errorMessage = ref<string>('')

const channels = computed<ChannelView[]>(() => {
  const list = nodeConfigData.value?.channels
  if (!Array.isArray(list)) return []

  return list.map((entry: any) => ({
    name: String(entry?.name || entry?.channel || '-'),
    type: String(entry?.type || entry?.channel_type || '-').toUpperCase(),
    metric: entry?.metric || entry?.metrics || null,
    actuator_type: entry?.actuator_type || null,
    unit: entry?.unit || null,
  }))
})

const prettyConfig = computed(() => {
  if (!nodeConfigData.value) return ''
  return JSON.stringify(nodeConfigData.value, null, 2)
})

watch(() => props.show, (show) => {
  if (show) {
    loadNodeConfig()
  } else {
    resetState()
  }
}, { immediate: true })

watch(() => props.nodeId, (nodeId, prev) => {
  if (props.show && nodeId && nodeId !== prev) {
    loadNodeConfig()
  }
})

function resetState() {
  nodeConfigData.value = null
  errorMessage.value = ''
}

function handleClose() {
  emit('close')
  resetState()
}

async function loadNodeConfig() {
  if (!props.nodeId) {
    nodeConfigData.value = null
    return
  }

  loading.value = true
  errorMessage.value = ''

  try {
    const response = await api.get<{ data?: Record<string, unknown> }>(`/nodes/${props.nodeId}/config`)
    const payload = response.data?.data
    nodeConfigData.value = payload && typeof payload === 'object' && !Array.isArray(payload) ? payload : null
  } catch (error) {
    // Ошибка уже обработана в useApi через showToast
    logger.error('Failed to load node config:', error)
    errorMessage.value = 'Не удалось загрузить конфигурацию. Попробуйте позже.'
    nodeConfigData.value = null
  } finally {
    loading.value = false
  }
}
</script>
