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
          <Badge variant="warning">live tuning</Badge>
        </div>
        <p class="text-xs text-[color:var(--text-dim)] mt-1">
          Изменения применяются на лету через AE3 checkpoint. Только безопасные setpoint'ы — irrigation mode / phase transitions править нельзя.
        </p>
      </div>
    </header>

    <form
      class="grid grid-cols-2 md:grid-cols-3 gap-3"
      data-testid="recipe-phase-form"
      @submit.prevent="submit"
    >
      <label class="flex flex-col gap-1 text-xs">
        <span class="text-[color:var(--text-dim)]">pH target</span>
        <input
          v-model.number="form.ph_target"
          type="number"
          step="0.01"
          min="0"
          max="14"
          class="text-sm px-2 py-1 rounded border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]"
        />
      </label>
      <label class="flex flex-col gap-1 text-xs">
        <span class="text-[color:var(--text-dim)]">pH min</span>
        <input
          v-model.number="form.ph_min"
          type="number"
          step="0.01"
          min="0"
          max="14"
          class="text-sm px-2 py-1 rounded border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]"
        />
      </label>
      <label class="flex flex-col gap-1 text-xs">
        <span class="text-[color:var(--text-dim)]">pH max</span>
        <input
          v-model.number="form.ph_max"
          type="number"
          step="0.01"
          min="0"
          max="14"
          class="text-sm px-2 py-1 rounded border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]"
        />
      </label>
      <label class="flex flex-col gap-1 text-xs">
        <span class="text-[color:var(--text-dim)]">EC target</span>
        <input
          v-model.number="form.ec_target"
          type="number"
          step="0.01"
          min="0"
          max="20"
          class="text-sm px-2 py-1 rounded border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]"
        />
      </label>
      <label class="flex flex-col gap-1 text-xs">
        <span class="text-[color:var(--text-dim)]">EC min</span>
        <input
          v-model.number="form.ec_min"
          type="number"
          step="0.01"
          min="0"
          max="20"
          class="text-sm px-2 py-1 rounded border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]"
        />
      </label>
      <label class="flex flex-col gap-1 text-xs">
        <span class="text-[color:var(--text-dim)]">EC max</span>
        <input
          v-model.number="form.ec_max"
          type="number"
          step="0.01"
          min="0"
          max="20"
          class="text-sm px-2 py-1 rounded border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]"
        />
      </label>
      <label class="col-span-2 md:col-span-3 flex flex-col gap-1 text-xs">
        <span class="text-[color:var(--text-dim)]">Причина (обязательно, &ge; 3)</span>
        <input
          v-model="form.reason"
          type="text"
          minlength="3"
          maxlength="500"
          class="text-sm px-2 py-1 rounded border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]"
          data-testid="recipe-phase-reason"
        />
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
          ✓ сохранено, revision {{ lastRevision }}
        </p>
        <span v-else></span>

        <button
          type="submit"
          class="text-xs px-3 py-1 rounded bg-[color:var(--accent,#3b82f6)] text-white disabled:opacity-50"
          :disabled="!canSubmit"
          data-testid="recipe-phase-submit"
        >Применить</button>
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
    errorMessage.value = extractError(err) ?? 'Ошибка применения'
  } finally {
    saving.value = false
  }
}

function extractError(err: unknown): string | null {
  if (typeof err === 'object' && err !== null) {
    const anyErr = err as { response?: { data?: { message?: string; code?: string } } }
    return anyErr.response?.data?.message ?? anyErr.response?.data?.code ?? null
  }
  return null
}
</script>
