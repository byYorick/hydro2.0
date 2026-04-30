<template>
  <Modal
    :open="open"
    title="Создание субстрата"
    size="large"
    @close="$emit('close')"
  >
    <div class="space-y-4 text-[color:var(--text-primary)]">
      <!-- Основное -->
      <div class="rounded-md border border-[color:var(--border-muted)] p-3 space-y-3">
        <div class="text-[11px] font-semibold uppercase tracking-wide text-[color:var(--text-dim)]">
          Основное
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label class="block text-xs text-[color:var(--text-muted)] mb-1">Код (английский) <span class="text-red-500">*</span></label>
            <input
              v-model="form.code"
              class="input-field"
              placeholder="coco_perlite_70_30"
            />
            <p class="text-[11px] text-[color:var(--text-muted)] mt-0.5">
              Уникальный код, латиница + цифры + _
            </p>
          </div>
          <div>
            <label class="block text-xs text-[color:var(--text-muted)] mb-1">Название <span class="text-red-500">*</span></label>
            <input
              v-model="form.name"
              class="input-field"
              placeholder="Кокос + Перлит 70/30"
            />
          </div>
        </div>
      </div>

      <!-- Состав -->
      <div class="rounded-md border border-[color:var(--border-muted)] p-3 space-y-3">
        <div class="flex items-center justify-between">
          <div class="text-[11px] font-semibold uppercase tracking-wide text-[color:var(--text-dim)]">
            Состав компонентов
          </div>
          <div class="flex items-center gap-3">
            <div
              class="text-sm font-bold"
              :class="Math.abs(ratioSum - 100) <= 0.01 ? 'text-[color:var(--accent-green)]' : 'text-[color:var(--badge-warning-text)]'"
            >
              {{ ratioSum.toFixed(1) }}%
            </div>
            <button
              type="button"
              class="soft-btn"
              title="Привести сумму к 100%"
              @click="normalizeComponents"
            >
              <svg
                class="w-3.5 h-3.5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.2"
                stroke-linecap="round"
                stroke-linejoin="round"
              ><polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" /><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" /></svg>
              Нормализовать
            </button>
            <button
              type="button"
              class="soft-btn"
              title="Добавить компонент"
              @click="addComponent"
            >
              <svg
                class="w-3.5 h-3.5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              ><line
                x1="12"
                y1="5"
                x2="12"
                y2="19"
              /><line
                x1="5"
                y1="12"
                x2="19"
                y2="12"
              /></svg>
              Компонент
            </button>
          </div>
        </div>

        <div
          v-for="(comp, idx) in form.components"
          :key="idx"
          class="grid grid-cols-[1fr_1fr_80px_auto] gap-2 items-end"
        >
          <div>
            <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Код</label>
            <input
              v-model="comp.name"
              class="input-field !text-xs"
              placeholder="coco"
            />
          </div>
          <div>
            <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5">Название</label>
            <input
              v-model="comp.label"
              class="input-field !text-xs"
              placeholder="Кокос"
            />
          </div>
          <div>
            <label class="block text-[10px] text-[color:var(--text-muted)] mb-0.5 text-center">Доля, %</label>
            <input
              v-model.number="comp.ratio_pct"
              type="number"
              min="0"
              max="100"
              step="0.1"
              class="input-field hide-spin !text-xs text-center"
            />
          </div>
          <button
            v-if="form.components.length > 1"
            type="button"
            class="h-[2.6rem] px-2 text-sm text-[color:var(--text-muted)] hover:text-red-500"
            title="Удалить компонент"
            @click="removeComponent(idx)"
          >
            ✕
          </button>
          <div v-else></div>
        </div>

        <p class="text-[11px] text-[color:var(--text-muted)]">
          Сумма долей всех компонентов должна быть 100%
        </p>
      </div>

      <!-- Совместимость -->
      <div class="rounded-md border border-[color:var(--border-muted)] p-3 space-y-3">
        <div class="text-[11px] font-semibold uppercase tracking-wide text-[color:var(--text-dim)]">
          Совместимые системы полива
        </div>
        <div class="flex flex-wrap gap-2">
          <label
            v-for="sys in SYSTEM_OPTIONS"
            :key="sys.value"
            class="flex items-center gap-1.5 rounded-md border border-[color:var(--border-muted)] px-2 py-1 cursor-pointer text-xs hover:bg-[color:var(--bg-muted)]"
            :class="{ 'bg-emerald-50 dark:bg-emerald-900/20 border-[color:var(--accent-green)]': form.applicable_systems.includes(sys.value) }"
          >
            <input
              type="checkbox"
              :value="sys.value"
              :checked="form.applicable_systems.includes(sys.value)"
              class="w-3.5 h-3.5"
              @change="toggleSystem(sys.value)"
            />
            {{ sys.label }}
          </label>
        </div>
      </div>

      <!-- Заметки -->
      <div>
        <label class="block text-xs text-[color:var(--text-muted)] mb-1">Заметки</label>
        <textarea
          v-model="form.notes"
          rows="2"
          class="input-field !h-auto !py-2"
          placeholder="Например: перед посадкой замочить на 12 часов"
        ></textarea>
      </div>
    </div>

    <template #footer>
      <Button
        size="sm"
        :disabled="!canSubmit || saving"
        @click="submit"
      >
        {{ saving ? 'Создание...' : 'Создать' }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'
import { api } from '@/services/api'
import type { Substrate, SubstrateComponent } from '@/services/api/substrates'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  close: []
  created: [substrate: Substrate]
}>()

const { showToast } = useToast()

const SYSTEM_OPTIONS = [
  { value: 'drip_tape', label: 'Капельная лента' },
  { value: 'drip_emitter', label: 'Капельные форсунки' },
  { value: 'ebb_flow', label: 'Прилив-отлив' },
  { value: 'nft', label: 'NFT' },
  { value: 'dwc', label: 'DWC' },
  { value: 'aeroponics', label: 'Аэропоника' },
]

interface FormState {
  code: string
  name: string
  components: SubstrateComponent[]
  applicable_systems: string[]
  notes: string
}

const form = reactive<FormState>({
  code: '',
  name: '',
  components: [{ name: '', label: '', ratio_pct: 100 }],
  applicable_systems: [],
  notes: '',
})

const saving = ref(false)

const ratioSum = computed(() =>
  form.components.reduce((acc, c) => acc + (Number(c.ratio_pct) || 0), 0)
)

const canSubmit = computed(() =>
  form.code.trim().length > 0
  && form.name.trim().length > 0
  && form.components.length > 0
  && form.components.every(c => c.name.trim().length > 0)
  && Math.abs(ratioSum.value - 100) <= 0.01
)

function addComponent(): void {
  form.components.push({ name: '', label: '', ratio_pct: 0 })
}

function removeComponent(idx: number): void {
  form.components.splice(idx, 1)
}

function normalizeComponents(): void {
  const sum = form.components.reduce((acc, c) => acc + (Number(c.ratio_pct) || 0), 0)
  if (sum <= 0) {
    const even = 100 / form.components.length
    form.components.forEach(c => { c.ratio_pct = +even.toFixed(2) })
    return
  }
  form.components.forEach(c => {
    c.ratio_pct = +(((Number(c.ratio_pct) || 0) / sum) * 100).toFixed(2)
  })
  // Подгоним последний чтобы sum = 100 точно
  const newSum = form.components.reduce((a, c) => a + c.ratio_pct, 0)
  if (Math.abs(newSum - 100) > 0.01 && form.components.length > 0) {
    form.components[form.components.length - 1].ratio_pct = +(form.components[form.components.length - 1].ratio_pct + (100 - newSum)).toFixed(2)
  }
}

function toggleSystem(value: string): void {
  const idx = form.applicable_systems.indexOf(value)
  if (idx >= 0) form.applicable_systems.splice(idx, 1)
  else form.applicable_systems.push(value)
}

function resetForm(): void {
  form.code = ''
  form.name = ''
  form.components = [{ name: '', label: '', ratio_pct: 100 }]
  form.applicable_systems = []
  form.notes = ''
}

watch(() => props.open, (open) => {
  if (!open) resetForm()
})

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  saving.value = true
  try {
    const substrate = await api.substrates.create({
      code: form.code.trim(),
      name: form.name.trim(),
      components: form.components.map(c => ({
        name: c.name.trim(),
        label: c.label?.trim() || null,
        ratio_pct: Number(c.ratio_pct) || 0,
      })),
      applicable_systems: form.applicable_systems,
      notes: form.notes.trim() || null,
    })
    emit('created', substrate)
    showToast(`Субстрат "${substrate.name}" создан`, 'success', TOAST_TIMEOUT.NORMAL)
    emit('close')
  } catch (err: unknown) {
    showToast('Ошибка создания субстрата', 'error', TOAST_TIMEOUT.NORMAL)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.soft-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.35rem 0.75rem;
  border-radius: 0.55rem;
  background: color-mix(in srgb, var(--accent-green) 10%, transparent);
  color: var(--accent-green);
  font-size: 0.72rem;
  font-weight: 600;
  border: 1px solid transparent;
  cursor: pointer;
  transition: background 0.15s, transform 0.08s;
}
.soft-btn:hover {
  background: color-mix(in srgb, var(--accent-green) 18%, transparent);
}
.soft-btn:active {
  transform: scale(0.97);
}
</style>
