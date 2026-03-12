<template>
  <Modal :open="show" title="Создать новую зону" @close="$emit('close')">
    <div class="space-y-4">
      <!-- Шаг 1: Основная информация -->
      <div>
        <h3 class="text-sm font-semibold mb-3 text-neutral-200">Основная информация</h3>
        <div class="space-y-3">
          <div>
            <label for="zone-name" class="block text-xs text-neutral-400 mb-1">Название зоны</label>
            <input
              id="zone-name"
              name="name"
              v-model="form.name"
              type="text"
              placeholder="Например: Зона A"
              class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
              autocomplete="off"
              required
            />
          </div>
          <div>
            <label for="zone-description" class="block text-xs text-neutral-400 mb-1">Описание (опционально)</label>
            <textarea
              id="zone-description"
              name="description"
              v-model="form.description"
              placeholder="Описание зоны..."
              class="w-full rounded-md border px-2 py-2 text-sm border-neutral-700 bg-neutral-900 min-h-[60px]"
              autocomplete="off"
            />
          </div>
          <div>
            <label for="zone-status" class="block text-xs text-neutral-400 mb-1">Статус</label>
            <select
              id="zone-status"
              name="status"
              v-model="form.status"
              class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
            >
              <option value="RUNNING">Запущена</option>
              <option value="PAUSED">Приостановлена</option>
              <option value="WARNING">Предупреждение</option>
              <option value="ALARM">Тревога</option>
            </select>
          </div>
        </div>
      </div>

      <!-- Сообщение об успехе -->
      <div v-if="createdZone" class="p-3 rounded-md bg-emerald-900/30 border border-emerald-700">
        <div class="text-sm text-emerald-400">
          ✓ Зона "{{ createdZone.name }}" успешно создана!
        </div>
      </div>

      <!-- Ошибка -->
      <div v-if="error" class="p-3 rounded-md bg-red-900/30 border border-red-700">
        <div class="text-sm text-red-400">{{ error }}</div>
      </div>
    </div>

    <template #footer>
      <Button size="sm" variant="secondary" @click="$emit('close')">Отмена</Button>
      <Button
        size="sm"
        @click="onCreate"
        :disabled="!form.name || creating"
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

