<template>
  <Modal :open="show" :title="`Редактирование конфига ноды`" @close="handleClose">
    <div v-if="loading" class="text-sm text-neutral-400">Загрузка...</div>
    <div v-else class="space-y-4">
      <div class="text-xs text-neutral-400">
        Настройте каналы (имя, тип, GPIO, описание) и отправьте конфиг на ноду.
      </div>

      <div v-if="errorMessage" class="text-xs text-amber-200 bg-amber-950/30 border border-amber-800 rounded-lg p-3">
        {{ errorMessage }}
      </div>

      <div v-if="editableChannels.length === 0" class="text-sm text-neutral-400">
        Нет каналов. Добавьте хотя бы один канал.
      </div>

      <div v-else class="space-y-3 max-h-[460px] overflow-y-auto pr-1 scrollbar-glow">
        <div
          v-for="(channel, index) in editableChannels"
          :key="index"
          class="p-3 rounded-xl border border-neutral-700 bg-neutral-925 space-y-3"
        >
          <div class="flex items-center justify-between gap-2">
            <div class="text-xs uppercase tracking-[0.2em] text-neutral-500">Канал {{ index + 1 }}</div>
            <button
              v-if="editableChannels.length > 1"
              type="button"
              class="text-xs text-rose-400 hover:text-rose-300"
              @click="removeChannel(index)"
            >
              Удалить
            </button>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-neutral-400 mb-1">Системное имя</label>
              <input
                v-model="channel.channel"
                type="text"
                placeholder="relay1"
                class="h-9 w-full rounded-lg border border-neutral-700 bg-neutral-900 px-2 text-xs focus:border-sky-500"
              />
            </div>
            <div>
              <label class="block text-xs text-neutral-400 mb-1">Отображаемое имя</label>
              <input
                v-model="channel.name"
                type="text"
                placeholder="Реле 1"
                class="h-9 w-full rounded-lg border border-neutral-700 bg-neutral-900 px-2 text-xs focus:border-sky-500"
              />
            </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label class="block text-xs text-neutral-400 mb-1">Тип</label>
              <select
                v-model="channel.type"
                class="h-9 w-full rounded-lg border border-neutral-700 bg-neutral-900 px-2 text-xs focus:border-sky-500"
              >
                <option value="ACTUATOR">ACTUATOR</option>
                <option value="SENSOR">SENSOR</option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-neutral-400 mb-1">Actuator type</label>
              <select
                v-model="channel.actuator_type"
                class="h-9 w-full rounded-lg border border-neutral-700 bg-neutral-900 px-2 text-xs focus:border-sky-500"
                :disabled="channel.type !== 'ACTUATOR'"
              >
                <option value="RELAY">RELAY</option>
                <option value="VALVE">VALVE</option>
                <option value="PUMP">PUMP</option>
                <option value="FAN">FAN</option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-neutral-400 mb-1">GPIO</label>
              <input
                v-model.number="channel.gpio"
                type="number"
                min="0"
                max="39"
                placeholder="26"
                class="h-9 w-full rounded-lg border border-neutral-700 bg-neutral-900 px-2 text-xs focus:border-sky-500"
                :disabled="channel.type !== 'ACTUATOR'"
              />
            </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-neutral-400 mb-1">Metric</label>
              <input
                v-model="channel.metric"
                type="text"
                placeholder="RELAY"
                class="h-9 w-full rounded-lg border border-neutral-700 bg-neutral-900 px-2 text-xs focus:border-sky-500"
              />
            </div>
            <div>
              <label class="block text-xs text-neutral-400 mb-1">Описание</label>
              <input
                v-model="channel.description"
                type="text"
                placeholder="Краткое описание канала"
                class="h-9 w-full rounded-lg border border-neutral-700 bg-neutral-900 px-2 text-xs focus:border-sky-500"
              />
            </div>
          </div>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-3">
        <Button size="sm" variant="secondary" @click="addChannel">Добавить канал</Button>
        <span class="text-xs text-neutral-400">Нажмите «Отправить», чтобы применить конфиг на ноду</span>
      </div>
    </div>

    <template #footer>
      <Button size="sm" variant="secondary" @click="handleClose">Отмена</Button>
      <Button size="sm" :disabled="saving || editableChannels.length === 0" @click="publishConfig">
        {{ saving ? 'Отправка...' : 'Отправить конфиг' }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'
import { useToast } from '@/composables/useToast'
import { useApi } from '@/composables/useApi'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { logger } from '@/utils/logger'

interface EditableChannel {
  name: string
  channel: string
  type: string
  actuator_type?: string
  gpio?: number | null
  metric?: string | null
  description?: string
}

const props = defineProps<{
  show: boolean
  nodeId: number
  initialChannels?: Array<Record<string, any>>
}>()

const emit = defineEmits<{
  close: []
  published: []
}>()

const { showToast } = useToast()
const { api } = useApi(showToast)

const editableChannels = ref<EditableChannel[]>([])
const loading = ref(false)
const saving = ref(false)
const errorMessage = ref('')

const normalizedInitialChannels = computed(() => {
  if (!props.initialChannels || props.initialChannels.length === 0) {
    return []
  }

  return props.initialChannels.map((ch) => normalizeChannel(ch))
})

watch(() => props.show, (value) => {
  if (value) {
    if (normalizedInitialChannels.value.length > 0) {
      editableChannels.value = [...normalizedInitialChannels.value]
    } else {
      editableChannels.value = [normalizeChannel({ type: 'ACTUATOR', actuator_type: 'RELAY', channel: 'relay1', gpio: 26, metric: 'RELAY' })]
    }
    errorMessage.value = ''
  }
}, { immediate: true })

watch(() => props.initialChannels, () => {
  if (props.show && normalizedInitialChannels.value.length > 0) {
    editableChannels.value = [...normalizedInitialChannels.value]
  }
})

function normalizeChannel(source: Record<string, any>): EditableChannel {
  const type = (source.type || 'ACTUATOR').toString().toUpperCase()
  return {
    name: source.name || source.channel || '',
    channel: source.channel || source.name || '',
    type,
    actuator_type: (source.actuator_type || source.config?.actuator_type || 'RELAY').toString().toUpperCase(),
    gpio: source.gpio ?? source.config?.gpio ?? null,
    metric: source.metric || source.config?.metric || (type === 'ACTUATOR' ? 'RELAY' : ''),
    description: source.description || source.config?.description || '',
  }
}

function addChannel() {
  editableChannels.value.push(normalizeChannel({ type: 'ACTUATOR', actuator_type: 'RELAY', channel: `relay${editableChannels.value.length + 1}`, metric: 'RELAY' }))
}

function removeChannel(index: number) {
  editableChannels.value.splice(index, 1)
}

function handleClose() {
  emit('close')
}

async function publishConfig() {
  if (!props.nodeId) return
  if (editableChannels.value.length === 0) {
    showToast('Добавьте хотя бы один канал', 'warning', TOAST_TIMEOUT.SHORT)
    return
  }

  saving.value = true
  errorMessage.value = ''

  try {
    const sanitizedChannels = editableChannels.value
      .filter(ch => (ch.channel || '').trim().length > 0)
      .map((ch) => {
        const type = (ch.type || 'ACTUATOR').toString().toUpperCase()
        const actuatorType = (ch.actuator_type || (type === 'ACTUATOR' ? 'RELAY' : '')).toString().toUpperCase()
        const gpio = type === 'ACTUATOR' ? (typeof ch.gpio === 'number' ? ch.gpio : undefined) : undefined

        return {
          name: (ch.name || ch.channel || '').trim(),
          channel: (ch.channel || ch.name || '').trim(),
          type,
          actuator_type: type === 'ACTUATOR' ? actuatorType : undefined,
          gpio,
          metric: ch.metric ? ch.metric.toString().toUpperCase() : undefined,
          description: ch.description?.trim() || undefined,
        }
      })

    const response = await api.post(`/nodes/${props.nodeId}/config/publish`, {
      config: {
        channels: sanitizedChannels,
      },
    })

    if (response.data?.status === 'ok') {
      showToast('Конфиг отправлен на ноду', 'success', TOAST_TIMEOUT.NORMAL)
      emit('published')
      emit('close')
    }
  } catch (error) {
    logger.error('[RelayConfigWizard] Failed to publish config', error)
    errorMessage.value = (error as any)?.response?.data?.message || 'Ошибка при отправке конфига'
  } finally {
    saving.value = false
  }
}
</script>
