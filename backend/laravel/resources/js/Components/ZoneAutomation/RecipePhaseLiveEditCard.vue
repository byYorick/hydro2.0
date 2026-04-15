<template>
  <section
    class="surface-card surface-card--elevated border border-amber-300/50 dark:border-amber-700/60 rounded-2xl p-4 space-y-3 bg-amber-50/30 dark:bg-amber-950/10"
    data-testid="recipe-phase-live-edit"
  >
    <header class="flex items-center justify-between gap-2">
      <div>
        <div class="flex items-center gap-2">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            Правка активной фазы (live)
          </h3>
          <Badge variant="warning">
            режим live
          </Badge>
        </div>
        <p class="text-xs text-[color:var(--text-dim)] mt-1">
          Изменения применяются на лету через AE3 checkpoint. Здесь доступны только безопасные setpoint-поля активной recipe phase; mode switching и phase transitions отсюда не меняются.
        </p>
      </div>
    </header>

    <form
      class="grid grid-cols-2 md:grid-cols-3 gap-3"
      data-testid="recipe-phase-form"
      @submit.prevent="submit"
    >
      <p class="col-span-2 md:col-span-3 text-xs text-[color:var(--text-dim)]">
        Заполняйте только те setpoint'ы, которые хотите изменить. Пустые поля в patch не отправляются и текущие значения активной фазы не перезаписывают.
      </p>

      <label
        v-for="field in RECIPE_FIELDS"
        :key="field.key"
        class="flex flex-col gap-1 text-xs"
      >
        <span class="text-[color:var(--text-dim)]">{{ field.label }}</span>
        <input
          :value="formatNumberField(form[field.key])"
          type="number"
          :step="field.step"
          :min="field.min"
          :max="field.max"
          class="text-sm px-2 py-1 rounded border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]"
          @input="updateNumberField(field.key, $event)"
        />
        <span class="text-[11px] text-[color:var(--text-dim)]">{{ field.description }}</span>
      </label>
      <label class="col-span-2 md:col-span-3 flex flex-col gap-1 text-xs">
        <span class="text-[color:var(--text-dim)]">Причина изменения (обязательно, &ge; 3)</span>
        <input
          v-model="form.reason"
          type="text"
          minlength="3"
          maxlength="500"
          class="text-sm px-2 py-1 rounded border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]"
          data-testid="recipe-phase-reason"
        />
        <span class="text-[11px] text-[color:var(--text-dim)]">
          Это поле идёт в timeline и audit trail. Коротко опишите, зачем правите фазу прямо сейчас: например, «повышаю EC для набора массы» или «сужаю pH-диапазон после стабилизации раствора».
        </span>
      </label>
      <div class="col-span-2 md:col-span-3 flex items-center justify-between gap-2">
        <p
          v-if="errorMessage"
          class="text-xs text-rose-500 dark:text-rose-400"
          data-testid="recipe-phase-error"
        >
          {{ errorMessage }}
        </p>
        <p
          v-else-if="saving"
          class="text-xs text-[color:var(--text-dim)] animate-pulse"
        >
          Сохранение...
        </p>
        <p
          v-else-if="lastRevision !== null"
          class="text-xs text-emerald-600 dark:text-emerald-400"
          data-testid="recipe-phase-success"
        >
          ✓ сохранено, ревизия {{ lastRevision }}
        </p>
        <span v-else></span>

        <button
          type="submit"
          class="text-xs px-3 py-1 rounded bg-[color:var(--accent,#3b82f6)] text-white disabled:opacity-50"
          :disabled="!canSubmit"
          data-testid="recipe-phase-submit"
        >
          Применить
        </button>
      </div>
    </form>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import Badge from '@/Components/Badge.vue'
import {
  type PhaseConfigUpdatePayload,
  zoneConfigModeApi,
} from '@/services/api/zoneConfigMode'

interface Props {
  growCycleId: number
  /** Optional hints for populating form (pre-fill from current phase). */
  initial?: {
    ph_target?: number | null
    ph_min?: number | null
    ph_max?: number | null
    ec_target?: number | null
    ec_min?: number | null
    ec_max?: number | null
  }
}

const props = withDefaults(defineProps<Props>(), { initial: () => ({}) })
const emit = defineEmits<{
  (e: 'applied', revision: number): void
}>()

interface FormState {
  ph_target: number | null
  ph_min: number | null
  ph_max: number | null
  ec_target: number | null
  ec_min: number | null
  ec_max: number | null
  reason: string
}

type NumericFieldKey = keyof Omit<FormState, 'reason'>

interface RecipeFieldDescriptor {
  key: NumericFieldKey
  label: string
  description: string
  step: string
  min: number
  max: number
}

const RECIPE_FIELDS: RecipeFieldDescriptor[] = [
  {
    key: 'ph_target',
    label: 'Целевой pH',
    description: 'Основная цель pH для активной фазы. По этому значению runtime оценивает, нужна ли pH-коррекция и достигнут ли рабочий режим.',
    step: '0.01',
    min: 0,
    max: 14,
  },
  {
    key: 'ph_min',
    label: 'Минимум pH',
    description: 'Нижняя граница допустимого диапазона pH. Если указана, `workflow_ready` ориентируется уже на явную нижнюю границу, а не только на процентный допуск.',
    step: '0.01',
    min: 0,
    max: 14,
  },
  {
    key: 'ph_max',
    label: 'Максимум pH',
    description: 'Верхняя граница допустимого диапазона pH. Помогает жёстко ограничить перерегулирование и зафиксировать рабочее окно фазы.',
    step: '0.01',
    min: 0,
    max: 14,
  },
  {
    key: 'ec_target',
    label: 'Целевой EC',
    description: 'Основная цель EC для активной фазы. По ней correction planner понимает, насколько нужно доводить концентрацию раствора.',
    step: '0.01',
    min: 0,
    max: 20,
  },
  {
    key: 'ec_min',
    label: 'Минимум EC',
    description: 'Нижняя граница рабочего окна EC. Если поле заполнено, runtime проверяет готовность фазы по явному нижнему порогу.',
    step: '0.01',
    min: 0,
    max: 20,
  },
  {
    key: 'ec_max',
    label: 'Максимум EC',
    description: 'Верхняя граница рабочего окна EC. Поле помогает ограничить слишком концентрированный раствор и быстрее ловить перерегулирование.',
    step: '0.01',
    min: 0,
    max: 20,
  },
]

const form = reactive<FormState>({
  ph_target: props.initial?.ph_target ?? null,
  ph_min: props.initial?.ph_min ?? null,
  ph_max: props.initial?.ph_max ?? null,
  ec_target: props.initial?.ec_target ?? null,
  ec_min: props.initial?.ec_min ?? null,
  ec_max: props.initial?.ec_max ?? null,
  reason: '',
})

const saving = ref(false)
const errorMessage = ref<string | null>(null)
const lastRevision = ref<number | null>(null)

const hasAnyField = computed(() => {
  const isNum = (v: unknown): boolean => typeof v === 'number' && Number.isFinite(v)
  return isNum(form.ph_target)
    || isNum(form.ph_min)
    || isNum(form.ph_max)
    || isNum(form.ec_target)
    || isNum(form.ec_min)
    || isNum(form.ec_max)
})

const canSubmit = computed(() =>
  !saving.value && hasAnyField.value && form.reason.length >= 3,
)

async function submit() {
  if (!canSubmit.value) return
  errorMessage.value = null
  lastRevision.value = null
  saving.value = true

  const payload: PhaseConfigUpdatePayload = { reason: form.reason }
  const fields: Array<keyof Omit<FormState, 'reason'>> = [
    'ph_target', 'ph_min', 'ph_max', 'ec_target', 'ec_min', 'ec_max',
  ]
  const payloadAny = payload as unknown as Record<string, unknown>
  for (const f of fields) {
    const v = form[f]
    if (typeof v === 'number' && Number.isFinite(v)) {
      payloadAny[f] = v
    }
  }

  try {
    const res = await zoneConfigModeApi.updatePhaseConfig(props.growCycleId, payload)
    lastRevision.value = res.config_revision
    form.reason = ''
    emit('applied', res.config_revision)
  } catch (err: unknown) {
    errorMessage.value = extractError(err) ?? 'Не удалось применить live-правку фазы.'
  } finally {
    saving.value = false
  }
}

function updateNumberField(field: NumericFieldKey, event: Event): void {
  const value = (event.target as HTMLInputElement).value
  if (value.trim() === '') {
    form[field] = null
    return
  }

  const numeric = Number(value)
  form[field] = Number.isFinite(numeric) ? numeric : null
}

function formatNumberField(value: number | null): string {
  return typeof value === 'number' && Number.isFinite(value) ? String(value) : ''
}

function extractError(err: unknown): string | null {
  if (typeof err === 'object' && err !== null) {
    const anyErr = err as { response?: { data?: { message?: string; code?: string } } }
    return anyErr.response?.data?.message ?? anyErr.response?.data?.code ?? null
  }
  return null
}
</script>
