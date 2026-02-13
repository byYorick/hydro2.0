<template>
  <Modal
    :open="show"
    :title="title"
    size="large"
    @close="handleClose"
  >
    <div class="space-y-4">
      <div
        class="grid grid-cols-1 gap-2 items-end"
        :class="isGrowingSystem ? 'md:grid-cols-[1fr_160px_170px_auto]' : 'md:grid-cols-[1fr_160px_auto]'"
      >
        <div>
          <label class="block text-xs text-[color:var(--text-muted)] mb-1">Название</label>
          <input
            v-model="newItem.label"
            type="text"
            class="input-field h-9 w-full"
            placeholder="Например: Кокосовый субстрат"
            :disabled="loading"
            autocomplete="off"
          />
        </div>
        <div>
          <label class="block text-xs text-[color:var(--text-muted)] mb-1">ID</label>
          <input
            v-model="newItem.id"
            type="text"
            class="input-field h-9 w-full"
            placeholder="Например: coco"
            :disabled="loading"
            autocomplete="off"
          />
        </div>
        <div v-if="isGrowingSystem">
          <label class="block text-xs text-[color:var(--text-muted)] mb-1">Субстрат</label>
          <select
            v-model="newItem.uses_substrate"
            class="input-field h-9 w-full"
            :disabled="loading"
          >
            <option :value="true">
              С субстратом
            </option>
            <option :value="false">
              Без субстрата
            </option>
          </select>
        </div>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          class="h-9 px-4"
          :disabled="loading"
          @click="addItem"
        >
          Добавить
        </Button>
      </div>

      <div class="space-y-2">
        <div
          v-if="localItems.length === 0"
          class="text-xs text-[color:var(--text-muted)]"
        >
          Нет элементов. Добавьте первый вариант.
        </div>
        <div
          v-for="(item, index) in localItems"
          :key="`${item.id}-${index}`"
          class="grid grid-cols-1 gap-2 items-center"
          :class="isGrowingSystem ? 'md:grid-cols-[1fr_160px_170px_auto]' : 'md:grid-cols-[1fr_160px_auto]'"
        >
          <input
            v-model="item.label"
            type="text"
            class="input-field h-9 w-full"
            :disabled="loading"
          />
          <input
            v-model="item.id"
            type="text"
            class="input-field h-9 w-full"
            :disabled="loading || item.locked"
          />
          <select
            v-if="isGrowingSystem"
            v-model="item.uses_substrate"
            class="input-field h-9 w-full"
            :disabled="loading"
          >
            <option :value="true">
              С субстратом
            </option>
            <option :value="false">
              Без субстрата
            </option>
          </select>
          <Button
            type="button"
            size="sm"
            variant="danger"
            class="h-9 px-3"
            :disabled="loading"
            @click="removeItem(index)"
          >
            Удалить
          </Button>
        </div>
      </div>

      <div
        v-if="error"
        class="text-xs text-[color:var(--accent-red)]"
      >
        {{ error }}
      </div>
    </div>

    <template #footer>
      <Button
        type="button"
        :disabled="loading"
        @click="save"
      >
        {{ loading ? 'Сохранение...' : 'Сохранить' }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'

interface TaxonomyOption {
  id: string
  label: string
  uses_substrate?: boolean
}

interface TaxonomyItem extends TaxonomyOption {
  locked?: boolean
}

interface Props {
  show: boolean
  title: string
  taxonomyKey: string
  items: TaxonomyOption[]
}

const props = defineProps<Props>()

const emit = defineEmits<{
  close: []
  saved: [payload: { key: string; items: TaxonomyOption[] }]
}>()

const { showToast } = useToast()
const { api } = useApi(showToast)

const localItems = ref<TaxonomyItem[]>([])
const newItem = reactive({
  id: '',
  label: '',
  uses_substrate: false,
})
const error = ref<string | null>(null)
const loading = ref(false)
const isGrowingSystem = computed(() => props.taxonomyKey === 'growing_system')

watch(
  () => props.show,
  (value) => {
    if (value) {
      resetState()
    }
  }
)

watch(
  () => props.items,
  () => {
    if (props.show) {
      resetState()
    }
  }
)

function resetState(): void {
  localItems.value = props.items.map((item) => ({
    id: item.id,
    label: item.label,
    uses_substrate: isGrowingSystem.value ? Boolean(item.uses_substrate) : undefined,
    locked: true,
  }))
  newItem.id = ''
  newItem.label = ''
  newItem.uses_substrate = false
  error.value = null
}

function handleClose(): void {
  if (loading.value) return
  emit('close')
}

function buildId(source: string): string {
  return source
    .toLowerCase()
    .trim()
    .replace(/\s+/g, '_')
    .replace(/[^a-z0-9_-]/g, '')
}

function addItem(): void {
  error.value = null
  const label = newItem.label.trim()
  let id = newItem.id.trim()

  if (!label) {
    error.value = 'Введите название'
    return
  }

  if (!id) {
    id = buildId(label)
  }

  if (!id) {
    error.value = 'Введите ID'
    return
  }

  if (localItems.value.some((item) => item.id === id)) {
    error.value = 'Такой ID уже существует'
    return
  }

  localItems.value.push({
    id,
    label,
    uses_substrate: isGrowingSystem.value ? newItem.uses_substrate : undefined,
    locked: false,
  })
  newItem.id = ''
  newItem.label = ''
  newItem.uses_substrate = false
}

function removeItem(index: number): void {
  localItems.value.splice(index, 1)
}

async function save(): Promise<void> {
  error.value = null

  const normalized = localItems.value
    .map((item) => ({
      id: item.id.trim(),
      label: item.label.trim(),
      uses_substrate: isGrowingSystem.value ? Boolean(item.uses_substrate) : undefined,
    }))

  if (normalized.some((item) => !item.id || !item.label)) {
    error.value = 'Заполните ID и название для всех элементов'
    return
  }

  const ids = normalized.map((item) => item.id)
  if (new Set(ids).size !== ids.length) {
    error.value = 'ID должны быть уникальными'
    return
  }

  loading.value = true

  try {
    const response = await api.put(`/plant-taxonomies/${props.taxonomyKey}`, {
      items: normalized,
    })

    const items = (response.data as any)?.data?.items ?? normalized

    showToast('Справочник обновлен', 'success', TOAST_TIMEOUT.NORMAL)
    emit('saved', { key: props.taxonomyKey, items })
    emit('close')
  } catch (err: any) {
    error.value = err?.response?.data?.message || 'Не удалось сохранить справочник'
  } finally {
    loading.value = false
  }
}
</script>
