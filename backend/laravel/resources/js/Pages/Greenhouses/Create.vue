<template>
  <AppLayout>
    <h1 class="text-lg font-semibold mb-4">
      Создать теплицу
    </h1>
    <Card>
      <form
        class="space-y-4"
        @submit.prevent="onSubmit"
      >
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label
              for="greenhouse-name"
              class="block text-xs text-[color:var(--text-muted)] mb-1"
            >Название <span class="text-[color:var(--accent-red)]">*</span></label>
            <input
              id="greenhouse-name"
              v-model="form.name"
              name="name"
              type="text"
              required
              placeholder="Main Greenhouse"
              class="input-field"
              :class="errors.name ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''"
            />
            <div
              v-if="errors.name"
              class="text-xs text-[color:var(--badge-danger-text)] mt-1"
            >
              {{ errors.name }}
            </div>
            <div class="text-xs text-[color:var(--text-dim)] mt-1">
              UID будет сгенерирован автоматически: <span class="text-[color:var(--text-muted)]">{{ generatedUid }}</span>
            </div>
          </div>
          
          <div>
            <label
              for="greenhouse-timezone"
              class="block text-xs text-[color:var(--text-muted)] mb-1"
            >Часовой пояс</label>
            <input
              id="greenhouse-timezone"
              v-model="form.timezone"
              name="timezone"
              type="text"
              placeholder="Europe/Moscow"
              class="input-field"
            />
          </div>
          
          <div>
            <label
              for="greenhouse-type"
              class="block text-xs text-[color:var(--text-muted)] mb-1"
            >Тип</label>
            <select
              id="greenhouse-type"
              v-model="form.type"
              name="type"
              class="input-select"
            >
              <option value="">
                Выберите тип
              </option>
              <option value="indoor">
                Indoor (Закрытая)
              </option>
              <option value="outdoor">
                Outdoor (Открытая)
              </option>
              <option value="greenhouse">
                Greenhouse (Теплица)
              </option>
            </select>
          </div>
          
          <div class="md:col-span-2">
            <label
              for="greenhouse-description"
              class="block text-xs text-[color:var(--text-muted)] mb-1"
            >Описание</label>
            <textarea
              id="greenhouse-description"
              v-model="form.description"
              name="description"
              rows="3"
              placeholder="Описание теплицы..."
              class="w-full rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-2 py-1 text-sm text-[color:var(--text-primary)] focus:border-[color:var(--accent-green)] focus:outline-none"
            ></textarea>
          </div>
        </div>
        
        <div class="flex justify-end gap-2">
          <Link href="/">
            <Button
              size="sm"
              variant="secondary"
              type="button"
            >
              Отмена
            </Button>
          </Link>
          <Button
            size="sm"
            type="submit"
            :disabled="loading"
          >
            {{ loading ? 'Создание...' : 'Создать' }}
          </Button>
        </div>
      </form>
    </Card>
  </AppLayout>
</template>

<script setup lang="ts">
import { reactive, ref, computed } from 'vue'
import { Link, router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { generateUid } from '@/utils/transliterate'

const { showToast } = useToast()
const { api } = useApi(showToast)

const loading = ref<boolean>(false)
const errors = reactive<Record<string, string>>({})

const form = reactive({
  name: '',
  timezone: 'Europe/Moscow',
  type: '',
  coordinates: null,
  description: ''
})

const generatedUid = computed(() => {
  if (!form.name || !form.name.trim()) {
    return 'gh-...'
  }
  return generateUid(form.name, 'gh-')
})

async function onSubmit() {
  errors.name = ''
  errors.general = ''

  if (!form.name || !form.name.trim()) {
    errors.name = 'Название обязательно'
    showToast('Введите название теплицы', 'error', TOAST_TIMEOUT.NORMAL)
    return
  }

  loading.value = true
  
  try {
    const uid = generatedUid.value
    
    const response = await api.post('/greenhouses', {
      ...form,
      uid: uid
    })
    
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
