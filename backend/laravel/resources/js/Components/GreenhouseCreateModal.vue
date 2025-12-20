<template>
  <Modal :open="show" title="Создать теплицу" @close="handleClose" size="large">
    <form @submit.prevent="onSubmit" class="space-y-4">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div class="md:col-span-2">
          <label for="greenhouse-name" class="block text-xs text-[color:var(--text-muted)] mb-1">
            Название <span class="text-[color:var(--accent-red)]">*</span>
          </label>
          <input
            id="greenhouse-name"
            name="name"
            v-model="form.name"
            type="text"
            required
            placeholder="Main Greenhouse"
            class="input-field h-9 w-full"
            :class="errors.name ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''"
            autocomplete="off"
          />
          <div v-if="errors.name" class="text-xs text-[color:var(--accent-red)] mt-1">{{ errors.name }}</div>
          <div class="text-xs text-[color:var(--text-dim)] mt-1">
            UID будет сгенерирован автоматически: <span class="text-[color:var(--text-muted)]">{{ generatedUid }}</span>
          </div>
        </div>

        <div>
          <label for="greenhouse-width" class="block text-xs text-[color:var(--text-muted)] mb-1">Ширина (м)</label>
          <input
            id="greenhouse-width"
            name="width"
            v-model.number="form.width"
            type="number"
            step="0.1"
            min="0"
            placeholder="10.0"
            class="input-field h-9 w-full"
            autocomplete="off"
          />
        </div>

        <div>
          <label for="greenhouse-length" class="block text-xs text-[color:var(--text-muted)] mb-1">Длина (м)</label>
          <input
            id="greenhouse-length"
            name="length"
            v-model.number="form.length"
            type="number"
            step="0.1"
            min="0"
            placeholder="20.0"
            class="input-field h-9 w-full"
            autocomplete="off"
          />
        </div>

        <div>
          <label for="greenhouse-height" class="block text-xs text-[color:var(--text-muted)] mb-1">Высота (м)</label>
          <input
            id="greenhouse-height"
            name="height"
            v-model.number="form.height"
            type="number"
            step="0.1"
            min="0"
            placeholder="3.0"
            class="input-field h-9 w-full"
            autocomplete="off"
          />
        </div>

        <div>
          <label for="greenhouse-type" class="block text-xs text-[color:var(--text-muted)] mb-1">Тип теплицы</label>
          <select
            id="greenhouse-type"
            name="type"
            v-model="form.type"
            class="input-select h-9 w-full"
          >
            <option value="">Выберите тип</option>
            <option value="outdoor">Открытая</option>
            <option value="greenhouse">Теплица</option>
            <option value="indoor">Помещение</option>
          </select>
        </div>

        <div>
          <label for="greenhouse-location" class="block text-xs text-[color:var(--text-muted)] mb-1">Расположение</label>
          <input
            id="greenhouse-location"
            name="location"
            v-model="form.location"
            type="text"
            placeholder="Москва, ул. Примерная, д. 1"
            class="input-field h-9 w-full"
            autocomplete="off"
          />
        </div>

        <div class="md:col-span-2">
          <label for="greenhouse-description" class="block text-xs text-[color:var(--text-muted)] mb-1">Описание</label>
          <textarea
            id="greenhouse-description"
            name="description"
            v-model="form.description"
            rows="3"
            placeholder="Описание теплицы..."
            class="input-field w-full py-2 h-auto"
            autocomplete="off"
          ></textarea>
        </div>
      </div>

      <div v-if="errors.general" class="text-sm text-[color:var(--accent-red)]">{{ errors.general }}</div>
    </form>

    <template #footer>
      <Button type="button" @click="onSubmit" :disabled="loading || !form.name.trim()">
        {{ loading ? 'Создание...' : 'Создать' }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { reactive, ref, computed, watch } from 'vue'
import { router } from '@inertiajs/vue3'
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { generateUid } from '@/utils/transliterate'

interface Props {
  show?: boolean
}

interface Greenhouse {
  id: number
  uid: string
  name: string
  description?: string
  coordinates?: any
}

const props = withDefaults(defineProps<Props>(), {
  show: false
})

const emit = defineEmits<{
  close: []
  created: [greenhouse: Greenhouse]
}>()

const { showToast } = useToast()
const { api } = useApi(showToast)

const loading = ref<boolean>(false)
const errors = reactive<Record<string, string>>({})

const form = reactive({
  name: '',
  type: '',
  width: null as number | null,
  length: null as number | null,
  height: null as number | null,
  location: '',
  description: ''
})

// Вычисляемый UID на основе названия
const generatedUid = computed(() => {
  if (!form.name || !form.name.trim()) {
    return 'gh-...'
  }
  return generateUid(form.name, 'gh-')
})

// Сброс формы при открытии модального окна
watch(() => props.show, (newVal: boolean) => {
  if (newVal) {
    resetForm()
  }
})

function resetForm() {
  form.name = ''
  form.type = ''
  form.width = null
  form.length = null
  form.height = null
  form.location = ''
  form.description = ''
  Object.keys(errors).forEach(key => delete errors[key])
}

function handleClose() {
  resetForm()
  emit('close')
}

async function onSubmit() {
  if (!form.name || !form.name.trim()) {
    showToast('Введите название теплицы', 'error', TOAST_TIMEOUT.NORMAL)
    return
  }

  loading.value = true
  errors.name = ''
  errors.general = ''
  
  try {
    // Генерируем UID автоматически на основе названия
    const uid = generateUid(form.name, 'gh-')
    
    // Формируем coordinates с размерами и расположением
    const coordinates: any = {}
    
    if (form.width !== null || form.length !== null || form.height !== null) {
      coordinates.dimensions = {}
      if (form.width !== null) coordinates.dimensions.width = form.width
      if (form.length !== null) coordinates.dimensions.length = form.length
      if (form.height !== null) coordinates.dimensions.height = form.height
    }
    
    if (form.location) {
      coordinates.location = form.location
    }
    
    const payload: any = {
      uid: uid,
      name: form.name,
      type: form.type || null,
      description: form.description || null
    }
    
    // Добавляем coordinates только если есть данные
    if (Object.keys(coordinates).length > 0) {
      payload.coordinates = coordinates
    }
    
    const response = await api.post('/greenhouses', payload)
    
    logger.info('Greenhouse created:', response.data)
    showToast('Теплица успешно создана', 'success', TOAST_TIMEOUT.NORMAL)
    
    const greenhouse = (response.data as any)?.data || response.data
    emit('created', greenhouse)
    handleClose()
    
    // Обновляем страницу для отображения новой теплицы
    router.reload({ only: ['greenhouses'] })
  } catch (error: any) {
    logger.error('Failed to create greenhouse:', error)
    
    // Обработка ошибок валидации (422)
    if (error.response?.data?.errors) {
      Object.keys(error.response.data.errors).forEach(key => {
        errors[key] = error.response.data.errors[key][0]
      })
    } else if (error.response?.data?.message) {
      errors.general = error.response.data.message
    }
  } finally {
    loading.value = false
  }
}
</script>
