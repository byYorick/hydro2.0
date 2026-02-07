<template>
  <AppLayout>
    <h1 class="text-lg font-semibold mb-4">
      {{ isEditMode ? 'Редактировать удобрение' : 'Добавить удобрение' }}
    </h1>

    <Card>
      <form
        class="space-y-4"
        @submit.prevent="onSave"
      >
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label class="block text-xs text-[color:var(--text-muted)] mb-1">Производитель</label>
            <input
              v-model="form.manufacturer"
              type="text"
              class="input-field"
              placeholder="Yara"
            />
            <p
              v-if="errors.manufacturer"
              class="text-xs text-[color:var(--badge-danger-text)] mt-1"
            >
              {{ errors.manufacturer }}
            </p>
          </div>

          <div>
            <label class="block text-xs text-[color:var(--text-muted)] mb-1">Название продукта</label>
            <input
              v-model="form.name"
              type="text"
              class="input-field"
              placeholder="YaraRega Water-Soluble NPK"
            />
            <p
              v-if="errors.name"
              class="text-xs text-[color:var(--badge-danger-text)] mt-1"
            >
              {{ errors.name }}
            </p>
          </div>

          <div>
            <label class="block text-xs text-[color:var(--text-muted)] mb-1">Компонент</label>
            <select
              v-model="form.component"
              class="input-select"
            >
              <option value="npk">
                NPK
              </option>
              <option value="calcium">
                Кальций
              </option>
              <option value="micro">
                Микроэлементы
              </option>
            </select>
            <p
              v-if="errors.component"
              class="text-xs text-[color:var(--badge-danger-text)] mt-1"
            >
              {{ errors.component }}
            </p>
          </div>

          <div>
            <label class="block text-xs text-[color:var(--text-muted)] mb-1">Состав</label>
            <input
              v-model="form.composition"
              type="text"
              class="input-field"
              placeholder="NPK 18-18-18"
            />
            <p
              v-if="errors.composition"
              class="text-xs text-[color:var(--badge-danger-text)] mt-1"
            >
              {{ errors.composition }}
            </p>
          </div>

          <div>
            <label class="block text-xs text-[color:var(--text-muted)] mb-1">Рекомендуемые стадии</label>
            <input
              v-model="form.recommended_stage"
              type="text"
              class="input-field"
              placeholder="ROOTING,VEG,FLOWER,FRUIT"
            />
            <p
              v-if="errors.recommended_stage"
              class="text-xs text-[color:var(--badge-danger-text)] mt-1"
            >
              {{ errors.recommended_stage }}
            </p>
          </div>

          <div>
            <label class="block text-xs text-[color:var(--text-muted)] mb-1">Ссылка на источник</label>
            <input
              v-model="form.source_url"
              type="url"
              class="input-field"
              placeholder="https://..."
            />
          </div>

          <div class="md:col-span-2">
            <label class="block text-xs text-[color:var(--text-muted)] mb-1">Код системы питания</label>
            <input
              v-model="form.system_code"
              type="text"
              class="input-field"
              placeholder="YARAREGA_CALCINIT_HAIFA_MICRO_V1"
            />
          </div>

          <div class="md:col-span-2">
            <label class="block text-xs text-[color:var(--text-muted)] mb-1">Заметки</label>
            <textarea
              v-model="form.notes"
              rows="5"
              class="input-field h-auto"
              placeholder="Технологические примечания по применению..."
            ></textarea>
            <p
              v-if="errors.notes"
              class="text-xs text-[color:var(--badge-danger-text)] mt-1"
            >
              {{ errors.notes }}
            </p>
          </div>
        </div>

        <div
          v-if="errors.general"
          class="text-xs text-[color:var(--badge-danger-text)]"
        >
          {{ errors.general }}
        </div>

        <div class="flex justify-between gap-2 flex-wrap">
          <div>
            <Button
              v-if="isEditMode"
              size="sm"
              variant="danger"
              type="button"
              :disabled="loading"
              @click="onDelete"
            >
              Удалить
            </Button>
          </div>

          <div class="flex gap-2">
            <Link href="/nutrients">
              <Button
                size="sm"
                variant="secondary"
                type="button"
                :disabled="loading"
              >
                Отмена
              </Button>
            </Link>
            <Button
              size="sm"
              type="submit"
              :disabled="loading"
            >
              {{ loading ? 'Сохранение...' : 'Сохранить' }}
            </Button>
          </div>
        </div>
      </form>
    </Card>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { Link, router, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { logger } from '@/utils/logger'
import type { NutrientProduct } from '@/types'

interface PageProps {
  nutrient?: NutrientProduct | null
  [key: string]: any
}

const page = usePage<PageProps>()
const nutrient = computed(() => (page.props.nutrient || null) as NutrientProduct | null)
const isEditMode = computed(() => Boolean(nutrient.value?.id))

const { showToast } = useToast()
const { api } = useApi(showToast)

const loading = ref(false)
const errors = reactive<Record<string, string>>({})

const form = reactive({
  manufacturer: nutrient.value?.manufacturer || '',
  name: nutrient.value?.name || '',
  component: (nutrient.value?.component || 'npk') as 'npk' | 'calcium' | 'micro',
  composition: nutrient.value?.composition || '',
  recommended_stage: nutrient.value?.recommended_stage || '',
  notes: nutrient.value?.notes || '',
  source_url: getMetadataString(nutrient.value, 'source_url'),
  system_code: getMetadataString(nutrient.value, 'system_code'),
})

function getMetadataString(item: NutrientProduct | null, key: string): string {
  const value = item?.metadata?.[key]
  return typeof value === 'string' ? value : ''
}

function resetErrors(): void {
  Object.keys(errors).forEach((key) => {
    errors[key] = ''
  })
}

function buildPayload(): Record<string, any> {
  const metadata: Record<string, string> = {}
  if (form.source_url.trim().length > 0) {
    metadata.source_url = form.source_url.trim()
  }
  if (form.system_code.trim().length > 0) {
    metadata.system_code = form.system_code.trim()
  }

  return {
    manufacturer: form.manufacturer.trim(),
    name: form.name.trim(),
    component: form.component,
    composition: form.composition.trim() || null,
    recommended_stage: form.recommended_stage.trim() || null,
    notes: form.notes.trim() || null,
    metadata: Object.keys(metadata).length > 0 ? metadata : null,
  }
}

function applyValidationErrors(payload: any): void {
  const responseErrors = payload?.response?.data?.errors
  if (!responseErrors || typeof responseErrors !== 'object') {
    errors.general = payload?.response?.data?.message || 'Не удалось сохранить удобрение'
    return
  }

  Object.entries(responseErrors).forEach(([field, messages]) => {
    const list = Array.isArray(messages) ? messages : [messages]
    errors[field] = String(list[0] || '')
  })
}

async function onSave(): Promise<void> {
  resetErrors()
  loading.value = true

  try {
    const payload = buildPayload()

    if (isEditMode.value && nutrient.value?.id) {
      await api.patch(`/nutrient-products/${nutrient.value.id}`, payload)
      showToast('Удобрение обновлено', 'success', TOAST_TIMEOUT.NORMAL)
    } else {
      await api.post('/nutrient-products', payload)
      showToast('Удобрение добавлено', 'success', TOAST_TIMEOUT.NORMAL)
    }

    router.visit('/nutrients')
  } catch (error: any) {
    logger.error('Failed to save nutrient product:', error)
    applyValidationErrors(error)
    if (!error?.response) {
      showToast('Ошибка сети при сохранении удобрения', 'error', TOAST_TIMEOUT.NORMAL)
    }
  } finally {
    loading.value = false
  }
}

async function onDelete(): Promise<void> {
  if (!nutrient.value?.id) {
    return
  }

  if (!window.confirm('Удалить удобрение?')) {
    return
  }

  resetErrors()
  loading.value = true

  try {
    await api.delete(`/nutrient-products/${nutrient.value.id}`)
    showToast('Удобрение удалено', 'success', TOAST_TIMEOUT.NORMAL)
    router.visit('/nutrients')
  } catch (error: any) {
    logger.error('Failed to delete nutrient product:', error)
    errors.general = error?.response?.data?.message || 'Не удалось удалить удобрение'
    if (!error?.response) {
      showToast('Ошибка сети при удалении удобрения', 'error', TOAST_TIMEOUT.NORMAL)
    }
  } finally {
    loading.value = false
  }
}
</script>
