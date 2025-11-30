<template>
  <AppLayout>
    <h1 class="text-lg font-semibold mb-4">Создать теплицу</h1>
    <Card>
      <form @submit.prevent="onSubmit" class="space-y-4">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label for="greenhouse-uid" class="block text-xs text-neutral-400 mb-1">UID <span class="text-red-400">*</span></label>
            <input
              id="greenhouse-uid"
              name="uid"
              v-model="form.uid"
              type="text"
              required
              placeholder="gh-main"
              class="h-9 w-full rounded-md border px-2 text-sm"
              :class="errors.uid ? 'border-red-500 bg-red-900/20' : 'border-neutral-700 bg-neutral-900'"
            />
            <div v-if="errors.uid" class="text-xs text-red-400 mt-1">{{ errors.uid }}</div>
          </div>
          
          <div>
            <label for="greenhouse-name" class="block text-xs text-neutral-400 mb-1">Название <span class="text-red-400">*</span></label>
            <input
              id="greenhouse-name"
              name="name"
              v-model="form.name"
              type="text"
              required
              placeholder="Main Greenhouse"
              class="h-9 w-full rounded-md border px-2 text-sm"
              :class="errors.name ? 'border-red-500 bg-red-900/20' : 'border-neutral-700 bg-neutral-900'"
            />
            <div v-if="errors.name" class="text-xs text-red-400 mt-1">{{ errors.name }}</div>
          </div>
          
          <div>
            <label for="greenhouse-timezone" class="block text-xs text-neutral-400 mb-1">Часовой пояс</label>
            <input
              id="greenhouse-timezone"
              name="timezone"
              v-model="form.timezone"
              type="text"
              placeholder="Europe/Moscow"
              class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
            />
          </div>
          
          <div>
            <label for="greenhouse-type" class="block text-xs text-neutral-400 mb-1">Тип</label>
            <select
              id="greenhouse-type"
              name="type"
              v-model="form.type"
              class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
            >
              <option value="">Выберите тип</option>
              <option value="indoor">Indoor (Закрытая)</option>
              <option value="outdoor">Outdoor (Открытая)</option>
              <option value="greenhouse">Greenhouse (Теплица)</option>
            </select>
          </div>
          
          <div class="md:col-span-2">
            <label for="greenhouse-description" class="block text-xs text-neutral-400 mb-1">Описание</label>
            <textarea
              id="greenhouse-description"
              name="description"
              v-model="form.description"
              rows="3"
              placeholder="Описание теплицы..."
              class="w-full rounded-md border px-2 py-1 text-sm border-neutral-700 bg-neutral-900"
            ></textarea>
          </div>
        </div>
        
        <div class="flex justify-end gap-2">
          <Link href="/">
            <Button size="sm" variant="secondary" type="button">Отмена</Button>
          </Link>
          <Button size="sm" type="submit" :disabled="loading">
            {{ loading ? 'Создание...' : 'Создать' }}
          </Button>
        </div>
      </form>
    </Card>
  </AppLayout>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { Link, router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const { showToast } = useToast()
const { api } = useApi(showToast)

const loading = ref<boolean>(false)
const errors = reactive<Record<string, string>>({})

const form = reactive({
  uid: '',
  name: '',
  timezone: 'Europe/Moscow',
  type: '',
  coordinates: null,
  description: ''
})

async function onSubmit() {
  loading.value = true
  errors.uid = ''
  errors.name = ''
  
  try {
    const response = await api.post('/greenhouses', form)
    
    logger.info('Greenhouse created:', response.data)
    showToast('Теплица успешно создана', 'success', TOAST_TIMEOUT.NORMAL)
    router.visit('/')
  } catch (error: any) {
    // Ошибка уже обработана в useApi через showToast, но добавляем обработку ошибок валидации
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

