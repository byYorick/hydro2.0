<template>
  <Modal
    :open="show"
    title="Калибровка насоса"
    placement="workspace"
    hide-default-cancel
    @close="onClose"
  >
    <div class="flex h-full min-h-0 flex-col">
      <div class="shrink-0 space-y-3 border-b border-[color:var(--border-muted)] px-4 py-3 sm:px-6">
        <div class="flex flex-wrap items-center justify-between gap-2 text-xs">
          <span class="break-words">Зона #{{ zoneId }} · {{ componentLabel(currentComponent) }} · {{ selectedChannelLabel || 'Канал не привязан' }} <span v-if="form.node_channel_id">· ch{{ form.node_channel_id }}</span></span>
          <Chip
            v-if="dirtyBadge"
            tone="warn"
          >
            {{ dirtyBadge }}
          </Chip>
        </div>
        <ol
          class="grid grid-cols-4 gap-1"
          aria-label="Этапы калибровки"
        >
          <li
            v-for="(label, index) in steps"
            :key="label"
            class="rounded-lg px-1.5 py-2 text-center text-[10px] sm:text-xs"
            :class="step === index ? 'bg-brand-soft font-semibold text-brand-ink' : 'bg-[color:var(--bg-elevated)] text-[color:var(--text-muted)]'"
            :aria-current="step === index ? 'step' : undefined"
          >
            {{ index + 1 }}. {{ label }}
          </li>
        </ol>
      </div>
      <section
        class="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4 sm:p-6"
        aria-live="polite"
      >
        <div
          v-if="pendingAction"
          ref="confirmationRef"
          tabindex="-1"
          class="space-y-4 rounded-xl border border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] p-4"
          role="alert"
        >
          <h2 class="font-semibold text-[color:var(--text-primary)]">
            {{ pendingAction === 'rerun' ? 'Начать новый замер?' : 'Закрыть окно калибровки?' }}
          </h2>
          <p>Несохранённый ввод будет отброшен. Закрытие окна не останавливает уже отправленную команду оборудования.</p>
          <div class="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              @click="pendingAction = null"
            >
              Продолжить работу
            </Button><Button
              variant="danger"
              @click="discard"
            >
              {{ pendingAction === 'rerun' ? 'Отбросить и запустить' : 'Закрыть без сохранения' }}
            </Button>
          </div>
        </div>
        <div
          v-else
          class="space-y-5"
        >
          <p
            v-if="closeBlocked"
            class="text-sm text-[color:var(--status-warning)]"
            role="status"
          >
            Идёт сохранение. Дождитесь результата запроса.
          </p>
          <template v-if="step === 0">
            <h2 class="text-lg font-semibold text-[color:var(--text-primary)]">
              Подготовьте замер
            </h2>
            <p class="text-sm">
              Проверьте выбранный насос, подготовьте мерную ёмкость и убедитесь, что тест допустим для текущего состояния зоны.
            </p>
            <div class="grid gap-4 sm:grid-cols-2">
              <Field
                label="Длительность теста, с"
                hint="От 1 до 60 секунд"
              >
                <TextField
                  v-bind="numAttrs"
                  v-model.number="form.duration_sec"
                  min="1"
                  max="60"
                  :disabled="Boolean(runToken) || form.actual_ml != null"
                />
              </Field>
              <div class="rounded-lg border border-[color:var(--border-muted)] p-3 text-xs">
                <strong>{{ isPhComponent ? 'Контур pH' : 'Контур EC' }}</strong><p class="mt-2">
                  Откалибровано {{ contextDone }} из {{ contextTotal }}
                </p><div class="mt-2 flex flex-wrap gap-1">
                  <Chip
                    v-for="pump in contextPills"
                    :key="pump.component"
                    :tone="pump.done ? 'growth' : 'neutral'"
                  >
                    {{ pump.label }}
                  </Chip>
                </div>
              </div>
            </div>
            <p
              v-if="!canRun"
              class="text-sm text-[color:var(--status-warning)]"
            >
              Нужны привязанный канал насоса и допустимая длительность теста.
            </p>
            <p class="rounded-lg bg-[color:var(--bg-elevated)] p-3 text-xs">
              Тест отправляется отдельной командой. Сохранение калибровки обновляет результат выбранного насоса; цели рецепта не меняются.
            </p>
            <Button
              variant="secondary"
              :disabled="!canRun || loadingRun || loadingSave"
              @click="useManualMeasurement"
            >
              Использовать внешний замер без запуска
            </Button>
          </template>
          <template v-else-if="step === 1">
            <h2 class="text-lg font-semibold text-[color:var(--text-primary)]">
              Введите фактический результат
            </h2>
            <p
              v-if="manualMode"
              class="rounded-lg border border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] p-3 text-sm"
            >
              Ручное переопределение: используется внешний замер за {{ form.duration_sec }} с. Команда запуска из этого окна не отправлялась.
            </p>
            <p
              v-else
              class="rounded-lg bg-[color:var(--bg-elevated)] p-3 text-sm"
            >
              {{ loadingRun ? 'Ожидается ответ на запрос запуска…' : runToken ? 'Запрос запуска принят. Это не подтверждение завершения теста.' : 'Запуск пока не подтверждён. Можно повторить запрос после проверки.' }} Вводите объём после фактической остановки насоса.
            </p>
            <div class="grid gap-4 sm:grid-cols-2">
              <Field
                label="Измеренный объём, мл"
                hint="Фактически собранный объём"
              >
                <TextField
                  v-bind="numAttrs"
                  v-model.number="form.actual_ml"
                  min="0.1"
                  step="0.1"
                  :disabled="loadingSave"
                />
              </Field>
              <Field
                label="Температура, °C"
                hint="Необязательно"
              >
                <TextField
                  v-bind="numAttrs"
                  v-model.number="form.temperature_c"
                  step="0.1"
                  :disabled="loadingSave"
                />
              </Field>
            </div>
            <details
              v-if="!isPhComponent"
              class="rounded-lg border border-[color:var(--border-muted)] p-3"
            >
              <summary class="cursor-pointer text-sm">
                Дополнительный расчёт влияния на EC
              </summary>
              <div class="mt-4 grid gap-4 sm:grid-cols-3">
                <Field label="Объём теста, л">
                  <TextField
                    v-bind="numAttrs"
                    v-model.number="form.test_volume_l"
                    min="0"
                    step="0.1"
                  />
                </Field><Field label="EC до дозы, мСм/см">
                  <TextField
                    v-bind="numAttrs"
                    v-model.number="form.ec_before_ms"
                    min="0"
                    step="0.01"
                  />
                </Field><Field label="EC после дозы, мСм/см">
                  <TextField
                    v-bind="numAttrs"
                    v-model.number="form.ec_after_ms"
                    min="0"
                    step="0.01"
                  />
                </Field>
              </div>
            </details>
            <label class="flex min-h-11 items-start gap-3 text-sm"><input
              v-model="measurementConfirmed"
              type="checkbox"
              class="mt-1"
            />Тест завершён, объём измерен за {{ form.duration_sec }} с.</label>
            <Button
              v-if="!manualMode"
              variant="secondary"
              :disabled="loadingRun || loadingSave"
              @click="runCalibration"
            >
              Повторить запуск
            </Button>
          </template>
          <template v-else-if="step === 2">
            <h2 class="text-lg font-semibold text-[color:var(--text-primary)]">
              Проверьте расчёт
            </h2>
            <div class="text-4xl font-semibold tabular-nums text-[color:var(--text-primary)]">
              {{ formatFloat(previewMlPerSec, 3) }} <span class="text-base font-normal">мл/с</span>
            </div>
            <p>{{ form.actual_ml }} мл за {{ form.duration_sec }} с · {{ componentLabel(form.component) }}</p>
            <div
              v-if="previewVisible"
              class="grid gap-3 sm:grid-cols-2"
            >
              <Stat
                v-if="previewDeltaEc !== null"
                label="ΔEC, мСм/см"
                :value="formatFloat(previewDeltaEc, 3)"
                mono
              /><Stat
                v-if="previewK !== null"
                label="Коэффициент влияния на EC"
                :value="formatFloat(previewK, 4)"
                mono
              />
            </div>
            <p class="rounded-lg bg-[color:var(--bg-elevated)] p-3 text-sm">
              Будет сохранён результат для {{ selectedChannelLabel }}. {{ manualMode ? 'Источник — ручное переопределение по внешнему замеру.' : 'Результат связан с запросом запуска.' }}
            </p>
          </template>
          <template v-else>
            <h2 class="text-lg font-semibold text-[color:var(--text-primary)]">
              {{ savedForCurrent ? 'Калибровка сохранена' : 'Сохранение результата' }}
            </h2>
            <p>{{ componentLabel(form.component) }} · {{ selectedChannelLabel }}</p>
            <div class="text-3xl font-semibold tabular-nums">
              {{ formatFloat(previewMlPerSec, 3) }} мл/с
            </div>
            <p
              v-if="savedForCurrent"
              class="text-[color:var(--status-ok)]"
            >
              Сохранение подтверждено сервером.
            </p>
            <p
              v-if="nextUncalibrated"
              class="text-sm"
            >
              Следующий доступный насос: {{ nextUncalibrated.label }}.
            </p>
          </template>
        </div>
      </section>
    </div>
    <template #footer>
      <template v-if="!pendingAction">
        <Button
          v-if="step > 0 && !savedForCurrent"
          variant="secondary"
          :disabled="loadingRun || loadingSave"
          @click="step--"
        >
          Назад
        </Button>
        <Button
          v-else
          variant="secondary"
          :disabled="loadingSave"
          @click="onClose"
        >
          Закрыть
        </Button>
        <span class="mr-auto self-center text-xs">Шаг {{ step + 1 }} из 4</span>
        <Button
          v-if="step === 0"
          :disabled="!canRun || loadingRun || loadingSave"
          @click="runCalibration"
        >
          {{ loadingRun ? 'Отправка…' : 'Запустить замер' }}
        </Button>
        <Button
          v-else-if="step === 1"
          :disabled="!canSave || loadingRun || loadingSave"
          @click="step = 2"
        >
          Проверить результат
        </Button>
        <Button
          v-else-if="step === 2"
          :disabled="!canSave || loadingRun || loadingSave"
          @click="step = 3"
        >
          К сохранению
        </Button>
        <Button
          v-else-if="!savedForCurrent"
          :disabled="!canSave || loadingRun || loadingSave"
          @click="saveCalibration"
        >
          {{ loadingSave ? 'Сохранение…' : 'Сохранить результат' }}
        </Button>
        <Button
          v-else-if="nextUncalibrated"
          @click="goToNext"
        >
          К {{ nextUncalibrated.label }} →
        </Button>
      </template>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import TextField from '@/Components/TextField.vue'

import { computed, nextTick, reactive, ref, watch } from 'vue'
import Button from '@/Components/Button.vue'
import { Chip, Field, Stat } from '@/Components/Shared/Primitives'
import Modal from '@/Components/Modal.vue'
import type { Device } from '@/types'
import type {
  PumpCalibrationComponent,
  PumpCalibrationRunPayload,
  PumpCalibrationSavePayload,
} from '@/types/Calibration'
import type { PumpCalibration } from '@/types/PidConfig'

const props = withDefaults(
  defineProps<{
    show: boolean
    zoneId: number
    devices: Device[]
    pumps: PumpCalibration[]
    loadingRun?: boolean
    loadingSave?: boolean
    runSuccessSeq?: number
    saveSuccessSeq?: number
    lastRunToken?: string | null
    initialComponent?: PumpCalibrationComponent | null
    initialNodeChannelId?: number | null
  }>(),
  {
    loadingRun: false,
    loadingSave: false,
    runSuccessSeq: 0,
    saveSuccessSeq: 0,
    lastRunToken: null,
    initialComponent: null,
    initialNodeChannelId: null,
  },
)

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'start', payload: PumpCalibrationRunPayload): void
  (e: 'save', payload: PumpCalibrationSavePayload): void
}>()

const numAttrs = { type: 'number' }

const componentOptions: Array<{ value: PumpCalibrationComponent; label: string }> = [
  { value: 'npk', label: 'NPK' },
  { value: 'calcium', label: 'Calcium' },
  { value: 'magnesium', label: 'Magnesium' },
  { value: 'micro', label: 'Micro' },
  { value: 'ph_up', label: 'pH Up' },
  { value: 'ph_down', label: 'pH Down' },
]

const steps = ['Подготовка', 'Замер', 'Проверка', 'Сохранение']
const step = ref(0)
const manualMode = ref(false)
const measurementConfirmed = ref(false)
const runRequested = ref(false)
const runSelection = ref('')
const baselineSnapshot = ref('')
const savedSnapshot = ref<string | null>(null)
const pendingAction = ref<'close' | 'rerun' | null>(null)
const closeBlocked = ref(false)
const confirmationRef = ref<HTMLElement | null>(null)
watch(pendingAction, async value => { if (value) { await nextTick(); confirmationRef.value?.focus() } })

const runToken = ref<string | null>(null)
const runFinishedAt = ref<number | null>(null)

const form = reactive<{
  component: PumpCalibrationComponent
  node_channel_id: number | null
  duration_sec: number
  actual_ml: number | null
  test_volume_l: number | null
  ec_before_ms: number | null
  ec_after_ms: number | null
  temperature_c: number | null
}>({
  component: 'npk',
  node_channel_id: null,
  duration_sec: 20,
  actual_ml: null,
  test_volume_l: null,
  ec_before_ms: null,
  ec_after_ms: null,
  temperature_c: null,
})

watch(
  () => props.runSuccessSeq,
  (seq, prev) => {
    if (seq !== prev && props.show && runRequested.value && runSelection.value === selectionKey()) {
      runToken.value = props.lastRunToken ?? null
      runFinishedAt.value = Date.now()
    }
  },
)

watch(
  () => props.saveSuccessSeq,
  (seq, prev) => {
    if (seq !== prev && seq > 0 && props.show) {
      savedSnapshot.value = snapshot()
      baselineSnapshot.value = snapshot()
      runToken.value = null
      runRequested.value = false
      step.value = 3
    }
  },
)

const savedForCurrent = computed(() => savedSnapshot.value !== null && savedSnapshot.value === snapshot())
const hasUnsavedChanges = computed(() => baselineSnapshot.value !== snapshot())
function snapshot(): string { return JSON.stringify(form) }
function selectionKey(): string { return `${form.component}/${form.node_channel_id}/${form.duration_sec}` }

interface PumpChannelOption {
  id: number
  label: string
}

const pumpChannels = computed<PumpChannelOption[]>(() => {
  const out: PumpChannelOption[] = []
  for (const d of props.devices) {
    const deviceLabel = d.uid ?? d.name ?? `Узел ${d.id}`
    const channels =
      (d as { channels?: Array<{ id: number; channel: string; type?: string }> }).channels ?? []
    for (const ch of channels) {
      const type = String(ch.type ?? '').toLowerCase()
      if (!type.includes('actuator')) continue
      const name = String(ch.channel ?? '')
      const lower = name.toLowerCase()
      if (lower.startsWith('valve_') || lower === 'drain_pump') continue
      out.push({ id: ch.id, label: `${deviceLabel} · ${name}` })
    }
  }
  return out
})

const currentComponent = computed(() => form.component)
const isPhComponent = computed(() => form.component === 'ph_up' || form.component === 'ph_down')

interface ContextPill {
  component: PumpCalibrationComponent
  label: string
  done: boolean
}

function roleForComponent(component: PumpCalibrationComponent): string {
  return component === 'npk'
    ? 'pump_a'
    : component === 'calcium'
      ? 'pump_b'
      : component === 'magnesium'
        ? 'pump_c'
        : component === 'micro'
          ? 'pump_d'
          : component === 'ph_up'
            ? 'pump_base'
            : 'pump_acid'
}

function pumpDoneFor(component: PumpCalibrationComponent): boolean {
  const role = roleForComponent(component)
  const pump = props.pumps.find((p) => p.role === role)
  return !!pump?.ml_per_sec && pump.ml_per_sec > 0
}

const contextPills = computed<ContextPill[]>(() => {
  const comps: PumpCalibrationComponent[] = isPhComponent.value
    ? ['ph_up', 'ph_down']
    : ['npk', 'calcium', 'magnesium', 'micro']
  return comps.map((c) => {
    const opt = componentOptions.find((o) => o.value === c)
    return {
      component: c,
      label: opt?.label ?? c,
      done: pumpDoneFor(c),
    }
  })
})

const contextDone = computed(() => contextPills.value.filter((p) => p.done).length)
const contextTotal = computed(() => contextPills.value.length)

const canRun = computed(
  () =>
    form.component != null &&
    form.node_channel_id != null &&
    Number.isInteger(form.duration_sec) && form.duration_sec >= 1 && form.duration_sec <= 60,
)

const canSave = computed(
  () => canRun.value && typeof form.actual_ml === 'number' && Number.isFinite(form.actual_ml) && form.actual_ml > 0 && measurementConfirmed.value && (manualMode.value || Boolean(runToken.value && runSelection.value === selectionKey())),
)

const previewMlPerSec = computed(() => {
  if (!form.actual_ml || form.duration_sec <= 0) return null
  return form.actual_ml / form.duration_sec
})

const previewDeltaEc = computed(() => {
  if (typeof form.ec_before_ms !== 'number' || typeof form.ec_after_ms !== 'number') return null
  return form.ec_after_ms - form.ec_before_ms
})

const previewK = computed(() => {
  const delta = previewDeltaEc.value
  const ml = form.actual_ml
  const vol = form.test_volume_l
  if (!delta || !ml || !vol || vol <= 0 || ml <= 0) return null
  return (delta * vol) / ml
})

const previewVisible = computed(
  () => previewMlPerSec.value !== null || previewDeltaEc.value !== null,
)

const dirtyBadge = computed(() => hasUnsavedChanges.value ? 'Есть несохранённый замер' : '')

function formatFloat(v: number | null, digits: number): string {
  if (v === null || !Number.isFinite(v)) return '—'
  return v.toFixed(digits)
}

function runCalibration(): void {
  if (!canRun.value || props.loadingRun || props.loadingSave) return
  if (form.actual_ml != null || form.ec_before_ms != null || form.ec_after_ms != null) {
    pendingAction.value = 'rerun'
    return
  }
  performRun()
}

function clearMeasurement(): void {
  form.actual_ml = null
  form.test_volume_l = null
  form.ec_before_ms = null
  form.ec_after_ms = null
  form.temperature_c = null
  measurementConfirmed.value = false
}

function performRun(): void {
  if (!canRun.value || form.node_channel_id == null) return
  clearMeasurement()
  runToken.value = null
  savedSnapshot.value = null
  manualMode.value = false
  runRequested.value = true
  runSelection.value = selectionKey()
  step.value = 1
  emit('start', { component: form.component, node_channel_id: form.node_channel_id, duration_sec: form.duration_sec })
}

function useManualMeasurement(): void {
  if (!canRun.value || props.loadingRun || props.loadingSave) return
  manualMode.value = true
  runRequested.value = false
  runToken.value = null
  step.value = 1
}

interface NextCandidate {
  component: PumpCalibrationComponent
  label: string
  role: string
  nodeChannelId: number
  group: 'ec' | 'ph'
  required: boolean
  doneInPath: number
  pathTotal: number
}

const NEXT_ORDER: Array<{
  component: PumpCalibrationComponent
  label: string
  role: string
  group: 'ec' | 'ph'
  required: boolean
}> = [
  { component: 'npk', label: 'NPK', role: 'pump_a', group: 'ec', required: true },
  { component: 'calcium', label: 'Calcium', role: 'pump_b', group: 'ec', required: false },
  { component: 'magnesium', label: 'Magnesium', role: 'pump_c', group: 'ec', required: false },
  { component: 'micro', label: 'Micro', role: 'pump_d', group: 'ec', required: false },
  { component: 'ph_down', label: 'pH Down', role: 'pump_acid', group: 'ph', required: true },
  { component: 'ph_up', label: 'pH Up', role: 'pump_base', group: 'ph', required: true },
]

const nextUncalibrated = computed<NextCandidate | null>(() => {
  const pumpByRole = (role: string) => props.pumps.find((p) => p.role === role)
  const currentGroup: 'ec' | 'ph' = isPhComponent.value ? 'ph' : 'ec'

  const buckets: Array<NextCandidate[]> = [[], [], [], []]
  for (const desc of NEXT_ORDER) {
    if (desc.component === form.component) continue
    const pump = pumpByRole(desc.role)
    const calibrated = !!pump?.ml_per_sec && pump.ml_per_sec > 0
    const hasChannel = Boolean(pump && pump.node_channel_id > 0)
    if (!pump || calibrated || !hasChannel) continue

    const sameGroup = desc.group === currentGroup
    const bucketIdx = sameGroup
      ? desc.required
        ? 0
        : 1
      : desc.required
        ? 2
        : 3

    const pathRoles = NEXT_ORDER.filter((d) => d.group === desc.group)
    const doneInPath = pathRoles.filter((d) => {
      const p = pumpByRole(d.role)
      return !!p?.ml_per_sec && p.ml_per_sec > 0
    }).length

    buckets[bucketIdx].push({
      component: desc.component,
      label: desc.label,
      role: desc.role,
      nodeChannelId: pump.node_channel_id,
      group: desc.group,
      required: desc.required,
      doneInPath,
      pathTotal: pathRoles.length,
    })
  }

  for (const bucket of buckets) {
    if (bucket.length > 0) return bucket[0]
  }
  return null
})

function goToNext() {
  const next = nextUncalibrated.value
  if (!next) return
  form.component = next.component
  form.node_channel_id = next.nodeChannelId
  form.actual_ml = null
  form.test_volume_l = null
  form.ec_before_ms = null
  form.ec_after_ms = null
  form.temperature_c = null
  runToken.value = null
  runFinishedAt.value = null
  savedSnapshot.value = null
  step.value = 0
  manualMode.value = false
  measurementConfirmed.value = false
  runRequested.value = false
  baselineSnapshot.value = snapshot()
}

const selectedChannelLabel = computed(() => {
  if (!form.node_channel_id) return ''
  return pumpChannels.value.find((c) => c.id === form.node_channel_id)?.label ?? ''
})

function componentLabel(component: PumpCalibrationComponent): string {
  return componentOptions.find((o) => o.value === component)?.label ?? component
}

function setInitialPumpSelection(): void {
  if (props.initialComponent) {
    form.component = props.initialComponent
  }
  if (props.initialNodeChannelId) {
    form.node_channel_id = props.initialNodeChannelId
  }

  if (!form.node_channel_id && props.initialComponent) {
    const initialRole = roleForComponent(props.initialComponent)
    const initialPump = props.pumps.find((p) => p.role === initialRole && p.node_channel_id > 0)
    if (initialPump) {
      form.node_channel_id = initialPump.node_channel_id
      return
    }
  }

  if (!form.node_channel_id) {
    const next = nextUncalibrated.value
    if (next) {
      form.component = next.component
      form.node_channel_id = next.nodeChannelId
      return
    }

    const fallback = props.pumps.find((p) => p.node_channel_id > 0)
    if (fallback) {
      const fallbackComponent = NEXT_ORDER.find((item) => item.role === fallback.role)?.component
      if (fallbackComponent) {
        form.component = fallbackComponent
      }
      form.node_channel_id = fallback.node_channel_id
    }
  }
}

function saveCalibration() {
  if (!canSave.value || props.loadingRun || props.loadingSave || savedForCurrent.value) return
  const nodeChannelId = form.node_channel_id
  const actualMl = form.actual_ml
  if (nodeChannelId == null || actualMl == null) return

  const token = runToken.value
  const hasRunToken = token !== null && token !== ''

  const payload = {
    component: form.component,
    node_channel_id: nodeChannelId,
    duration_sec: form.duration_sec,
    actual_ml: actualMl,
    skip_run: true as const,
    test_volume_l: form.test_volume_l ?? undefined,
    ec_before_ms: form.ec_before_ms ?? undefined,
    ec_after_ms: form.ec_after_ms ?? undefined,
    temperature_c: form.temperature_c ?? undefined,
    ...(hasRunToken
      ? { run_token: token }
      : { manual_override: true as const }),
  }
  emit('save', payload)
}

function onClose(): void {
  if (pendingAction.value) { pendingAction.value = null; return }
  closeBlocked.value = false
  if (props.loadingSave) { closeBlocked.value = true; return }
  if (hasUnsavedChanges.value || runRequested.value || props.loadingRun) { pendingAction.value = 'close'; return }
  emit('close')
}

function discard(): void {
  const action = pendingAction.value
  pendingAction.value = null
  if (action === 'rerun') performRun()
  else emit('close')
}

watch(
  () => props.show,
  (open) => {
    pendingAction.value = null
    closeBlocked.value = false
    if (!open) return
    form.component = props.initialComponent ?? 'npk'
    form.node_channel_id = null
    form.duration_sec = 20
    clearMeasurement()
    setInitialPumpSelection()
    runToken.value = null
    runFinishedAt.value = null
    savedSnapshot.value = null
    step.value = 0
    manualMode.value = false
    runRequested.value = false
    baselineSnapshot.value = snapshot()
  },
  { immediate: true },
)
</script>

