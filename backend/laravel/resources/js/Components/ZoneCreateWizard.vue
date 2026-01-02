<template>
  <Modal
    :open="show"
    title="Создать новую зону"
    @close="$emit('close')"
  >
    <div class="space-y-4">
      <!-- Шаг 1: Основная информация -->
      <div>
        <h3 class="text-sm font-semibold mb-3 text-[color:var(--text-primary)]">
          Основная информация
        </h3>
        <div class="space-y-3">
          <div>
            <label
              for="zone-name"
              class="block text-xs text-[color:var(--text-muted)] mb-1"
            >Название зоны</label>
            <input
              id="zone-name"
              v-model="form.name"
              name="name"
              type="text"
              placeholder="Например: Зона A"
              class="input-field h-9 w-full"
              autocomplete="off"
              required
            />
          </div>
          <div>
            <label
              for="zone-description"
              class="block text-xs text-[color:var(--text-muted)] mb-1"
            >Описание (опционально)</label>
            <textarea
              id="zone-description"
              v-model="form.description"
              name="description"
              placeholder="Описание зоны..."
              class="input-field w-full min-h-[60px] py-2 h-auto"
              autocomplete="off"
            ></textarea>
          </div>
          <div>
            <label
              for="zone-status"
              class="block text-xs text-[color:var(--text-muted)] mb-1"
            >Статус</label>
            <select
              id="zone-status"
              v-model="form.status"
              name="status"
              class="input-select h-9 w-full"
            >
              <option value="RUNNING">
                Запущена
              </option>
              <option value="PAUSED">
                Приостановлена
              </option>
              <option value="WARNING">
                Предупреждение
              </option>
              <option value="ALARM">
                Тревога
              </option>
            </select>
          </div>
        </div>
      </div>

      <!-- Сообщение об успехе -->
      <div
        v-if="createdZone"
        class="p-3 rounded-md bg-[color:var(--badge-success-bg)] border border-[color:var(--badge-success-border)]"
      >
        <div class="text-sm text-[color:var(--badge-success-text)]">
          ✓ Зона "{{ createdZone.name }}" успешно создана!
        </div>
      </div>

      <!-- Ошибка -->
      <div
        v-if="error"
        class="p-3 rounded-md bg-[color:var(--badge-danger-bg)] border border-[color:var(--badge-danger-border)]"
      >
        <div class="text-sm text-[color:var(--badge-danger-text)]">
          {{ error }}
        </div>
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
        :disabled="!form.name || creating"
        @click="onCreate"
      >
        {{ creating ? 'Создание...' : 'Создать зону' }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import Modal from './Modal.vue'
import Button from './Button.vue'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'

interface Props {
  show: boolean
  greenhouseId: number
}

interface Zone {
  id: number
  name: string
  description?: string
  status?: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
  created: [zone: Zone]
}>()

const { showToast } = useToast()
const { api } = useApi(showToast)

const form = reactive({
  name: '',
  description: '',
  status: 'RUNNING'
})

const creating = ref(false)
const createdZone = ref<Zone | null>(null)
const error = ref<string | null>(null)

watch(() => props.show, (show) => {
  if (show) {
    // Сброс формы при открытии
    form.name = ''
    form.description = ''
    form.status = 'RUNNING'
    createdZone.value = null
    error.value = null
  }
})

async function onCreate(): Promise<void> {
  if (!form.name.trim()) {
    error.value = 'Название зоны обязательно'
    return
  }

  creating.value = true
  error.value = null

  try {
    const response = await api.post<{ data?: Zone } | Zone>(
      '/zones',
      {
        name: form.name.trim(),
        description: form.description.trim() || null,
        status: form.status,
        greenhouse_id: props.greenhouseId
      }
    )

    const zone = (response.data as { data?: Zone })?.data || (response.data as Zone)
    createdZone.value = zone

    logger.info('Zone created:', zone)
    showToast('Зона успешно создана', 'success', TOAST_TIMEOUT.NORMAL)

    // Эмитим событие создания
    emit('created', zone)

    // Закрываем модальное окно через небольшую задержку
    setTimeout(() => {
      emit('close')
    }, 1000)
  } catch (err: any) {
    logger.error('Failed to create zone:', err)
    error.value = err.response?.data?.message || err.message || 'Ошибка при создании зоны'
  } finally {
    creating.value = false
  }
}
</script>
