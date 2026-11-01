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
          <TextField
            v-model="form.manufacturer"
            label="Производитель"
            placeholder="Yara"
            :error="errors.manufacturer"
          />
          <TextField
            v-model="form.name"
            label="Название продукта"
            placeholder="YaraRega Water-Soluble NPK"
            :error="errors.name"
          />
          <SelectField
            v-model="form.component"
            label="Компонент"
            :error="errors.component"
          >
            <option value="npk">
              NPK
            </option>
            <option value="calcium">
              Кальций
            </option>
            <option value="magnesium">
              Магний
            </option>
            <option value="micro">
              Микроэлементы
            </option>
          </SelectField>
          <TextField
            v-model="form.composition"
            label="Состав"
            placeholder="NPK 18-18-18"
            :error="errors.composition"
          />
          <TextField
            v-model="form.recommended_stage"
            label="Рекомендуемые стадии"
            placeholder="ROOTING,VEG,FLOWER,FRUIT"
            :error="errors.recommended_stage"
          />
          <TextField
            v-model="form.source_url"
            type="url"
            label="Ссылка на источник"
            placeholder="example.test/product"
          />
          <TextField
            v-model="form.system_code"
            label="Код системы питания"
            class="md:col-span-2"
            placeholder="YARAREGA_CALCINIT_HAIFA_MICRO_V1"
          />
          <TextField
            v-model="form.notes"
            label="Заметки"
            class="md:col-span-2"
            multiline
            :rows="5"
            placeholder="Технологические примечания по применению..."
            :error="errors.notes"
          />
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
    <ConfirmModal
      :open="confirmOpen"
      :title="confirmTitle"
      :message="confirmMessage"
      confirm-variant="danger"
      @close="closeConfirm"
      @confirm="acceptConfirm"
    />
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { Link, router, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import ConfirmModal from '@/Components/ConfirmModal.vue'
import TextField from '@/Components/TextField.vue'
import SelectField from '@/Components/SelectField.vue'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { api } from '@/services/api'
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
const { open: confirmOpen, title: confirmTitle, message: confirmMessage, ask, close: closeConfirm, confirm: acceptConfirm } = useConfirmDialog()

const loading = ref(false)
const errors = reactive<Record<string, string>>({})

const form = reactive({
  manufacturer: nutrient.value?.manufacturer || '',
  name: nutrient.value?.name || '',
  component: (nutrient.value?.component || 'npk') as 'npk' | 'calcium' | 'magnesium' | 'micro',
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
      await api.nutrientProducts.update(nutrient.value.id, payload as never)
      showToast('Удобрение обновлено', 'success', TOAST_TIMEOUT.NORMAL)
    } else {
      await api.nutrientProducts.create(payload as never)
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

  if (!(await ask('Удалить удобрение?', 'Удалить удобрение?'))) return

  resetErrors()
  loading.value = true

  try {
    await api.nutrientProducts.delete(nutrient.value.id)
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
