<template>
  <Modal
    :open="open"
    :title="`Создание продукта — ${componentLabel}`"
    size="large"
    @close="$emit('close')"
  >
    <div class="space-y-4 text-[color:var(--text-primary)]">
      <!-- Базовое -->
      <div class="rounded-md border border-[color:var(--border-muted)] p-3 space-y-3">
        <div class="text-[11px] font-semibold uppercase tracking-wide text-[color:var(--text-dim)]">
          Основное
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label class="block text-xs text-[color:var(--text-muted)] mb-1">Производитель <span class="text-red-500">*</span></label>
            <TextField
              v-model="form.manufacturer"
              placeholder="Yara, Masterblend, Haifa..."
            />
          </div>
          <div>
            <label class="block text-xs text-[color:var(--text-muted)] mb-1">Название продукта <span class="text-red-500">*</span></label>
            <TextField
              v-model="form.name"
              placeholder="Masterblend 4-18-38"
            />
          </div>
        </div>
        <div>
          <label class="block text-xs text-[color:var(--text-muted)] mb-1">Категория</label>
          <div class="rounded-md bg-[color:var(--bg-muted)] px-3 py-2 text-sm">
            <span class="font-semibold">{{ componentLabel }}</span>
            <span class="text-[color:var(--text-muted)] text-xs ml-2">— определяется автоматически по полю, где нажали «+»</span>
          </div>
        </div>
      </div>

      <!-- Химический состав -->
      <div class="rounded-md border border-[color:var(--border-muted)] p-3 space-y-3">
        <div class="text-[11px] font-semibold uppercase tracking-wide text-[color:var(--text-dim)]">
          Химический состав
        </div>
        <div>
          <label class="block text-xs text-[color:var(--text-muted)] mb-1">Состав / формула</label>
          <TextField
            v-model="form.composition"
            placeholder="N 4% · P 18% · K 38%"
          />
          <p class="text-[11px] text-[color:var(--text-muted)] mt-1">
            Указать % содержания элементов, либо химическую формулу (Ca(NO₃)₂·4H₂O)
          </p>
        </div>
      </div>

      <!-- Рекомендации -->
      <div class="rounded-md border border-[color:var(--border-muted)] p-3 space-y-3">
        <div class="text-[11px] font-semibold uppercase tracking-wide text-[color:var(--text-dim)]">
          Применение
        </div>
        <div>
          <label class="block text-xs text-[color:var(--text-muted)] mb-1">Рекомендуемые стадии роста</label>
          <TextField
            v-model="form.recommended_stage"
            placeholder="VEG, BLOOM, FRUIT"
          />
          <p class="text-[11px] text-[color:var(--text-muted)] mt-1">
            На каких стадиях применять — через запятую
          </p>
        </div>
        <div>
          <label class="block text-xs text-[color:var(--text-muted)] mb-1">Заметки</label>
          <TextField
            v-model="form.notes"
            :rows="2"
            placeholder="Например: хорошо растворим в тёплой воде; хранить в сухом месте"
            multiline
            input-class="!h-auto !py-2"
          />
        </div>
      </div>
    </div>

    <template #footer>
      <Button
        size="sm"
        :disabled="!form.manufacturer.trim() || !form.name.trim() || creating"
        @click="submit"
      >
        {{ creating ? 'Создание...' : 'Создать' }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'
import type { NutrientProduct } from '@/types'
import { api } from '@/services/api'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import TextField from '@/Components/TextField.vue'

const props = defineProps<{
  open: boolean
  component: NutrientProduct['component']
}>()

const emit = defineEmits<{
  close: []
  created: [product: NutrientProduct]
}>()

const { showToast } = useToast()

const LABELS: Record<NutrientProduct['component'], string> = {
  npk: 'NPK (азот-фосфор-калий)',
  calcium: 'Кальций',
  magnesium: 'Магний',
  micro: 'Микроэлементы',
}

const componentLabel = computed(() => LABELS[props.component])

const form = reactive({
  manufacturer: '',
  name: '',
  composition: '',
  recommended_stage: '',
  notes: '',
})

const creating = ref(false)

function resetForm(): void {
  form.manufacturer = ''
  form.name = ''
  form.composition = ''
  form.recommended_stage = ''
  form.notes = ''
}

watch(() => props.open, (open) => {
  if (!open) resetForm()
})

async function submit(): Promise<void> {
  if (!form.manufacturer.trim() || !form.name.trim()) return
  creating.value = true
  try {
    const product = await api.nutrientProducts.create({
      manufacturer: form.manufacturer.trim(),
      name: form.name.trim(),
      component: props.component,
      composition: form.composition.trim() || null,
      recommended_stage: form.recommended_stage.trim() || null,
      notes: form.notes.trim() || null,
    } as never)
    emit('created', product as NutrientProduct)
    showToast(`Продукт "${form.manufacturer} · ${form.name}" создан`, 'success', TOAST_TIMEOUT.NORMAL)
    emit('close')
  } catch (err: unknown) {
    showToast('Ошибка создания продукта', 'error', TOAST_TIMEOUT.NORMAL)
  } finally {
    creating.value = false
  }
}
</script>
