<template>
  <Modal :open="show" :title="`Настройка узла ${node?.uid || node?.id}`" @close="handleClose">
    <div v-if="loading" class="text-sm text-[color:var(--text-muted)]">Загрузка конфигурации...</div>
    <div v-else class="space-y-4">
      <div class="text-xs text-[color:var(--text-muted)] mb-2">
        Настройте каналы узла. Конфигурация будет отправлена узлу через MQTT.
      </div>

      <div v-if="errorMessage" class="text-xs text-[color:var(--badge-warning-text)] bg-[color:var(--badge-warning-bg)] border border-[color:var(--badge-warning-border)] rounded-lg p-3">
        {{ errorMessage }}
      </div>

      <div v-if="!hasChannels && !loading" class="text-sm text-[color:var(--text-muted)]">
        У узла нет настроенных каналов
      </div>

      <div v-else class="space-y-3 max-h-[420px] overflow-y-auto pr-1 scrollbar-glow">
        <div
          v-for="(channel, index) in channels"
          :key="channel.id || index"
          class="p-3 rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] space-y-2"
        >
          <div class="flex items-center justify-between gap-2">
            <div>
              <div class="text-xs uppercase tracking-[0.2em] text-[color:var(--text-dim)]">Канал {{ index + 1 }}</div>
            </div>
            <button
              v-if="channels.length > 1"
              type="button"
              class="text-xs text-[color:var(--accent-red)] hover:text-[color:var(--badge-danger-text)]"
              @click="removeChannel(index)"
            >
              Удалить
            </button>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Channel</label>
              <input
                v-model="channel.channel"
                type="text"
                placeholder="example_channel"
                class="input-field h-9 w-full text-xs"
              />
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Type</label>
              <select
                v-model="channel.type"
                class="input-select h-9 w-full text-xs"
              >
                <option v-for="option in availableTypes" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-[color:var(--text-muted)] mb-1">Unit</label>
              <input
                v-model="channel.unit"
                type="text"
                placeholder="единицы измерения"
                class="input-field h-9 w-full text-xs"
              />
            </div>
          </div>
          <div class="grid grid-cols-2 gap-3 text-xs text-[color:var(--text-muted)]">
            <div>
              <label class="block text-[0.6rem] uppercase text-[color:var(--text-dim)]">Min</label>
              <input
                v-model.number="channel.min"
                type="number"
                step="0.01"
                class="input-field h-8 w-full text-xs"
              />
            </div>
            <div>
              <label class="block text-[0.6rem] uppercase text-[color:var(--text-dim)]">Max</label>
              <input
                v-model.number="channel.max"
                type="number"
                step="0.01"
                class="input-field h-8 w-full text-xs"
              />
            </div>
          </div>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-3">
        <Button size="sm" variant="secondary" @click="addChannel">Добавить канал</Button>
        <span class="text-xs text-[color:var(--text-muted)]">Для сохранения отправьте конфигурацию</span>
      </div>
    </div>
    
    <template #footer>
      <Button size="sm" variant="secondary" @click="handleClose">Отмена</Button>
      <Button
        size="sm"
        @click="onPublish"
        :disabled="publishing || loading || !hasChannels"
      >
        {{ publishing ? 'Отправка...' : 'Опубликовать конфигурацию' }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import Modal from './Modal.vue'
import Button from './Button.vue'
import { logger } from '@/utils/logger'
import { router } from '@inertiajs/vue3'
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

interface Channel {
  id?: string | number
  channel: string
  type: 'sensor' | 'actuator' | 'controller' | 'pump' | 'climate'
  unit?: string
  min?: number | null
  max?: number | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
  published: []
}>()

const { showToast } = useToast()
const { api } = useApi(showToast)

const loading = ref<boolean>(false)
const publishing = ref<boolean>(false)
const channels = ref<Channel[]>([])
const errorMessage = ref<string>('')

const availableTypes = [
  { value: 'sensor', label: 'Sensor' },
  { value: 'actuator', label: 'Actuator' },
  { value: 'controller', label: 'Controller' },
  { value: 'pump', label: 'Pump' },
  { value: 'climate', label: 'Climate' },
]

const hasChannels = computed(() => channels.value.length > 0)

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
  channels.value = []
  errorMessage.value = ''
  publishing.value = false
}

function normalizeChannel(source: Partial<Channel> = {}): Channel {
  return {
    id: source.id,
    channel: source.channel?.toString() || '',
    type: source.type || 'sensor',
    unit: source.unit?.toString() || '',
    min: source.min ?? null,
    max: source.max ?? null,
  }
}

async function loadNodeConfig() {
  if (!props.nodeId) {
    channels.value = []
    return
  }

  loading.value = true
  errorMessage.value = ''

  try {
    interface ConfigResponse {
      data?: {
        config?: {
          channels?: Channel[]
        }
      }
    }

    const response = await api.get<ConfigResponse>(`/nodes/${props.nodeId}/config`)

    const payload = response.data?.data?.config?.channels || []
    channels.value = Array.isArray(payload) ? payload.map(normalizeChannel) : []
  } catch (error) {
    // Ошибка уже обработана в useApi через showToast
    logger.error('Failed to load node config:', error)
    errorMessage.value = 'Не удалось загрузить каналы. Попробуйте позже.'
    channels.value = []
  } finally {
    loading.value = false
  }
}

function addChannel() {
  channels.value.push(normalizeChannel())
}

function removeChannel(index: number) {
  channels.value.splice(index, 1)
}

function handleClose() {
  emit('close')
  resetState()
}

async function onPublish() {
  if (!props.nodeId || !hasChannels.value) return

  publishing.value = true
  try {
    const sanitizedChannels = channels.value.map((channel) => ({
      channel: channel.channel.trim(),
      type: channel.type,
      unit: channel.unit?.trim() || undefined,
      min: channel.min ?? undefined,
      max: channel.max ?? undefined,
    }))

    const response = await api.post(
      `/nodes/${props.nodeId}/config/publish`,
      {
        config: {
          channels: sanitizedChannels,
        },
      }
    )

    // Обновляем устройство в store из ответа API, если он содержит данные
    try {
      const responseData = response.data?.data?.node || response.data?.data || response.data
      if (responseData?.id) {
        const { useDevicesStore } = await import('@/stores/devices')
        const devicesStore = useDevicesStore()
        devicesStore.upsert(responseData)
        logger.debug('[NodeConfigModal] Device updated in store after config publish', { deviceId: responseData.id })
      }
    } catch (storeError) {
      logger.warn('[NodeConfigModal] Failed to update device store', { error: storeError })
    }
    
    showToast('Конфигурация успешно опубликована', 'success', TOAST_TIMEOUT.NORMAL)
    emit('published')
    emit('close')
  } catch (error) {
    // Ошибка уже обработана в useApi через showToast
    logger.error('Failed to publish node config:', error)
    errorMessage.value = error.response?.data?.message || 'Ошибка при публикации конфигурации'
  } finally {
    publishing.value = false
  }
}
</script>
