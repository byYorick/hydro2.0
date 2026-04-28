<template>
  <Teleport to="body">
    <transition name="hf-drawer">
      <div
        v-if="show"
        class="fixed inset-0 z-50 flex justify-end bg-black/45 backdrop-blur-sm"
        @click.self="onClose"
      >
        <aside
          class="w-[min(960px,98vw)] h-screen flex flex-col bg-[var(--bg-surface-strong)] border-l border-[var(--border-muted)] shadow-2xl"
          role="dialog"
          aria-modal="true"
        >
          <header
            class="flex items-start justify-between gap-3 px-4 py-3 border-b border-[var(--border-muted)]"
          >
            <div class="min-w-0">
              <div class="text-sm font-semibold text-[var(--text-primary)]">
                Калибровка насоса
              </div>
              <div class="font-mono text-[11px] text-[var(--text-dim)] mt-0.5">
                / зона#{{ zoneId }} / насос / {{ currentComponent }}
              </div>
            </div>
            <div class="flex items-center gap-2">
              <Chip
                v-if="dirtyBadge"
                tone="warn"
              >
                {{ dirtyBadge }}
              </Chip>
              <button
                type="button"
                class="w-7 h-7 inline-flex items-center justify-center rounded-md text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-elevated)]"
                @click="onClose"
              >
                <Ic name="x" />
              </button>
            </div>
          </header>

          <div class="flex flex-1 min-h-0">
            <aside
              class="w-60 min-w-[240px] shrink-0 border-r border-[var(--border-muted)] bg-[var(--bg-surface)] p-3 flex flex-col gap-3 overflow-y-auto"
            >
              <div class="text-[10px] font-bold uppercase tracking-widest text-[var(--text-dim)]">
                этапы
              </div>
              <ol class="list-none m-0 p-0 flex flex-col gap-1.5">
                <li
                  v-for="(step, idx) in steps"
                  :key="step.id"
                  class="flex items-start gap-2 px-2 py-1.5 rounded-md"
                  :class="{
                    'bg-brand-soft text-brand-ink': currentStep === step.id,
                    'opacity-75': currentStep !== step.id && !isStepDone(step.id),
                  }"
                >
                  <span
                    :class="[
                      'inline-flex items-center justify-center w-5 h-5 rounded-full text-[11px] font-semibold border shrink-0',
                      isStepDone(step.id)
                        ? 'bg-growth text-white border-growth'
                        : currentStep === step.id
                          ? 'border-brand text-brand bg-[var(--bg-surface)] ring-2 ring-brand-soft'
                          : 'bg-[var(--bg-surface)] text-[var(--text-muted)] border-[var(--border-strong)]',
                    ]"
                  >
                    <span v-if="isStepDone(step.id)">✓</span>
                    <span
                      v-else
                      class="font-mono"
                    >{{ idx + 1 }}</span>
                  </span>
                  <span class="flex flex-col leading-tight min-w-0">
                    <span class="text-sm font-medium">{{ step.title }}</span>
                    <span class="text-[11px] text-[var(--text-dim)]">{{ step.desc }}</span>
                  </span>
                </li>
              </ol>

              <div class="text-[10px] font-bold uppercase tracking-widest text-[var(--text-dim)] mt-1">
                контекст
              </div>
              <div class="rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)] p-2.5 flex flex-col gap-2">
                <div class="flex items-center justify-between text-xs">
                  <span class="font-medium">{{ isPhComponent ? 'Контур pH' : 'Контур EC' }}</span>
                  <span class="font-mono text-[var(--text-dim)]">{{ contextDone }} / {{ contextTotal }}</span>
                </div>
                <div class="flex flex-wrap gap-1">
                  <Chip
                    v-for="p in contextPills"
                    :key="p.component"
                    :tone="p.done ? 'growth' : p.component === form.component ? 'brand' : 'neutral'"
                  >
                    <template #icon>
                      <span
                        class="inline-block w-1.5 h-1.5 rounded-full"
                        :class="p.done ? 'bg-growth' : p.component === form.component ? 'bg-brand' : 'bg-[var(--text-dim)]'"
                      />
                    </template>
                    {{ p.label }}<span v-if="p.component === form.component"> · текущий</span>
                  </Chip>
                </div>
              </div>
            </aside>

            <section class="flex-1 min-w-0 overflow-y-auto p-4 flex flex-col gap-3.5">
              <!-- STEP 1: SELECT -->
              <div
                v-if="currentStep === 'select'"
                class="flex flex-col gap-3"
              >
                <div class="flex items-baseline gap-2">
                  <span class="font-mono text-2xl font-bold text-[var(--text-dim)]">1.</span>
                  <div class="flex flex-col gap-0.5">
                    <div class="text-base font-semibold">
                      Выбор насоса
                    </div>
                    <div class="text-xs text-[var(--text-muted)]">
                      Компонент, канал и длительность тестового запуска.
                    </div>
                  </div>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <Field
                    label="Компонент"
                    required
                  >
                    <Select
                      v-model="form.component"
                      :options="componentOptions"
                      mono
                    />
                  </Field>
                  <Field
                    label="Канал насоса"
                    required
                  >
                    <Select
                      :model-value="form.node_channel_id != null ? String(form.node_channel_id) : ''"
                      :options="channelOptions"
                      placeholder="Выберите канал…"
                      mono
                      @update:model-value="(v: string) => (form.node_channel_id = v ? Number(v) : null)"
                    />
                  </Field>
                  <Field label="Длительность (сек)">
                    <input
                      v-bind="numAttrs"
                      v-model.number="form.duration_sec"
                      min="1"
                      max="60"
                    >
                  </Field>
                </div>
              </div>

              <!-- STEP 2: RUN + MEASURE -->
              <div
                v-if="currentStep === 'measure'"
                class="flex flex-col gap-3"
              >
                <div class="flex items-baseline justify-between gap-3 flex-wrap">
                  <div class="flex items-baseline gap-2">
                    <span class="font-mono text-2xl font-bold text-[var(--text-dim)]">2.</span>
                    <div class="text-base font-semibold">
                      Запуск и замер
                    </div>
                  </div>
                  <Chip
                    v-if="runToken"
                    tone="brand"
                  >
                    <span class="font-mono">токен запуска {{ runToken.slice(0, 8) }}</span>
                  </Chip>
                </div>

                <ShellCard title="Тестовый запуск">
                  <template #actions>
                    <span
                      v-if="runRecentAgo"
                      class="text-[11px] text-[var(--text-dim)]"
                    >
                      завершён {{ runRecentAgo }} назад
                    </span>
                  </template>
                  <div class="flex items-center gap-2 flex-wrap">
                    <Button
                      variant="primary"
                      size="md"
                      :disabled="loadingRun"
                      @click="runCalibration"
                    >
                      {{ loadingRun ? '▶ Запуск…' : '▶ Запустить калибровку' }}
                    </Button>
                    <span class="font-mono text-xs text-[var(--text-muted)]">
                      {{ form.duration_sec }} сек · {{ form.component.toUpperCase() }} · ch{{ form.node_channel_id }}
                    </span>
                  </div>
                </ShellCard>

                <ShellCard title="Результат замера">
                  <template #actions>
                    <Chip
                      v-if="!form.actual_ml"
                      tone="warn"
                    >
                      фактический объём обязателен
                    </Chip>
                  </template>
                  <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <Field
                      label="Фактический объём *"
                      hint="мл"
                    >
                      <input
                        v-bind="numAttrs"
                        v-model.number="form.actual_ml"
                        step="0.1"
                        min="0"
                      >
                    </Field>
                    <Field
                      label="Температура"
                      hint="°C, опц."
                    >
                      <input
                        v-bind="numAttrs"
                        v-model.number="form.temperature_c"
                        step="0.1"
                      >
                    </Field>
                    <Field
                      label="Объём теста (для k)"
                      hint="л"
                    >
                      <input
                        v-bind="numAttrs"
                        v-model.number="form.test_volume_l"
                        step="0.1"
                        min="0"
                      >
                    </Field>
                    <Field
                      label="EC до дозы"
                      hint="mS/cm"
                    >
                      <input
                        v-bind="numAttrs"
                        v-model.number="form.ec_before_ms"
                        step="0.01"
                        min="0"
                      >
                    </Field>
                    <Field
                      label="EC после дозы"
                      hint="mS/cm"
                    >
                      <input
                        v-bind="numAttrs"
                        v-model.number="form.ec_after_ms"
                        step="0.01"
                        min="0"
                      >
                    </Field>
                  </div>

                  <div
                    v-if="previewVisible"
                    class="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3 pt-3 border-t border-[var(--border-muted)]"
                  >
                    <Stat
                      label="мл/сек"
                      :value="formatFloat(previewMlPerSec, 3)"
                      mono
                      tone="brand"
                    />
                    <Stat
                      v-if="previewDeltaEc !== null"
                      label="ΔEC"
                      :value="(previewDeltaEc >= 0 ? '+' : '') + formatFloat(previewDeltaEc, 3)"
                      mono
                    />
                    <Stat
                      v-if="previewK !== null"
                      label="оценка K"
                      :value="formatFloat(previewK, 6)"
                      mono
                    />
                  </div>
                </ShellCard>

                <div
                  v-if="canSave && !savedForCurrent"
                  :class="[
                    'rounded-md border px-3 py-2 text-xs',
                    runToken
                      ? 'bg-growth-soft border-growth-soft text-growth'
                      : 'bg-warn-soft border-warn-soft text-warn',
                  ]"
                >
                  <span v-if="runToken">
                    ✓ Готов к сохранению · токен запуска
                    <span class="font-mono ml-1">{{ runToken.slice(0, 8) }}</span>
                  </span>
                  <span v-else>
                    ⚠ Запуск не выполнен — калибровка сохранится в режиме
                    <strong>ручного переопределения</strong>.
                  </span>
                </div>

                <div
                  v-if="savedForCurrent && nextUncalibrated"
                  class="rounded-md border border-brand bg-gradient-to-b from-[var(--bg-surface)] to-brand-soft p-3 flex flex-col gap-2"
                >
                  <div class="text-[11px] font-bold uppercase tracking-widest text-brand-ink">
                    ✓ {{ form.component.toUpperCase() }} сохранён · следующий некалиброванный
                  </div>
                  <div class="flex items-center justify-between gap-3 flex-wrap">
                    <div class="min-w-0">
                      <div class="text-sm font-semibold">
                        {{ nextUncalibrated.label }}
                      </div>
                      <div class="text-[11px] text-[var(--text-muted)]">
                        {{ nextUncalibrated.required ? 'обязательный' : 'опциональный' }}
                        ·
                        <span class="font-mono">
                          {{ nextUncalibrated.doneInPath }}/{{ nextUncalibrated.pathTotal }}
                        </span>
                        в контуре {{ nextUncalibrated.group === 'ec' ? 'EC' : 'pH' }}
                      </div>
                    </div>
                    <Button
                      variant="primary"
                      size="md"
                      @click="goToNext"
                    >
                      Продолжить с {{ nextUncalibrated.label }} →
                    </Button>
                  </div>
                </div>

                <div
                  v-else-if="savedForCurrent && !nextUncalibrated"
                  class="rounded-md border border-growth bg-growth-soft/40 p-3 flex flex-col gap-2"
                >
                  <div class="text-[11px] font-bold uppercase tracking-widest text-growth">
                    ✓ готово
                  </div>
                  <div class="flex items-center justify-between gap-3 flex-wrap">
                    <div class="min-w-0">
                      <div class="text-sm font-semibold">
                        Все доступные насосы откалиброваны
                      </div>
                      <div class="text-[11px] text-[var(--text-muted)]">
                        Остались только узлы без привязанного канала или опциональные.
                      </div>
                    </div>
                    <Button
                      variant="secondary"
                      size="md"
                      @click="onClose"
                    >
                      Закрыть
                    </Button>
                  </div>
                </div>
              </div>
            </section>
          </div>

          <footer
            class="flex items-center justify-between gap-3 px-4 py-3 border-t border-[var(--border-muted)] bg-[var(--bg-surface)]"
          >
            <Button
              v-if="currentStep === 'measure'"
              size="sm"
              variant="secondary"
              @click="currentStep = 'select'"
            >
              ← к выбору
            </Button>
            <Button
              v-else
              size="sm"
              variant="secondary"
              @click="onClose"
            >
              Отмена
            </Button>

            <div class="flex items-center gap-1.5">
              <template v-if="currentStep === 'select'">
                <Button
                  variant="primary"
                  size="sm"
                  :disabled="!canRun"
                  @click="goToRun"
                >
                  Далее →
                </Button>
              </template>
              <template v-else>
                <Button
                  size="sm"
                  variant="secondary"
                  :disabled="loadingRun"
                  @click="runCalibration"
                >
                  {{ runToken ? '↻ повторить запуск' : '▶ запустить' }}
                </Button>
                <Button
                  v-if="!savedForCurrent"
                  size="sm"
                  variant="primary"
                  :disabled="loadingSave || !canSave"
                  @click="saveCalibration"
                >
                  {{ loadingSave ? 'Сохранение…' : 'Сохранить' }}
                </Button>
                <Button
                  v-else-if="nextUncalibrated"
                  size="sm"
                  variant="primary"
                  @click="goToNext"
                >
                  К {{ nextUncalibrated.label }} →
                </Button>
                <Button
                  v-else
                  size="sm"
                  variant="primary"
                  @click="onClose"
                >
                  Закрыть
                </Button>
              </template>
            </div>
          </footer>
        </aside>
      </div>
    </transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import Button from '@/Components/Button.vue'
import { Chip, Field, Select, Stat } from '@/Components/Shared/Primitives'
import ShellCard from '@/Components/Launch/Shell/ShellCard.vue'
import Ic from '@/Components/Icons/Ic.vue'
import type { Device } from '@/types'
import type {
  PumpCalibrationComponent,
  PumpCalibrationRunPayload,
  PumpCalibrationSavePayload,
} from '@/types/Calibration'
import type { PumpCalibration } from '@/types/PidConfig'

export type PumpCalibrationStep = 'select' | 'measure'

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

const inputCls =
  'block w-full h-8 rounded-lg border border-[var(--border-muted)] bg-[var(--bg-surface)] text-[var(--text-primary)] px-2.5 text-sm font-mono outline-none transition-[border-color,box-shadow,background-color] duration-150 focus:border-brand focus:ring-2 focus:ring-brand-soft focus-visible:border-brand focus-visible:ring-2 focus-visible:ring-brand-soft'
const numAttrs = { class: inputCls, type: 'number' }

const componentOptions: Array<{ value: PumpCalibrationComponent; label: string }> = [
  { value: 'npk', label: 'NPK' },
  { value: 'calcium', label: 'Calcium' },
  { value: 'magnesium', label: 'Magnesium' },
  { value: 'micro', label: 'Micro' },
  { value: 'ph_up', label: 'pH Up' },
  { value: 'ph_down', label: 'pH Down' },
]

const steps = [
  { id: 'select' as const, title: 'Выбор насоса', desc: 'компонент · канал · длительность' },
  { id: 'measure' as const, title: 'Запуск, замер, сохранение', desc: 'объём · мл/сек · сохранить' },
]

const currentStep = ref<PumpCalibrationStep>('select')
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
  () => props.show,
  (open) => {
    if (open) {
      if (props.initialComponent) form.component = props.initialComponent
      if (props.initialNodeChannelId) form.node_channel_id = props.initialNodeChannelId
      currentStep.value = 'select'
      runToken.value = null
      runFinishedAt.value = null
      form.actual_ml = null
      form.test_volume_l = null
      form.ec_before_ms = null
      form.ec_after_ms = null
      form.temperature_c = null
    }
  },
  { immediate: true },
)

watch(
  () => props.runSuccessSeq,
  (seq, prev) => {
    if (seq !== prev) {
      runToken.value = props.lastRunToken ?? null
      runFinishedAt.value = Date.now()
    }
  },
)

const lastSavedAt = ref<number | null>(null)
const lastSavedComponent = ref<PumpCalibrationComponent | null>(null)
void lastSavedAt

watch(
  () => props.saveSuccessSeq,
  (seq, prev) => {
    if (seq !== prev && seq > 0) {
      lastSavedAt.value = Date.now()
      lastSavedComponent.value = form.component
    }
  },
)

const savedForCurrent = computed(
  () => lastSavedComponent.value !== null && lastSavedComponent.value === form.component,
)

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

const channelOptions = computed(() =>
  pumpChannels.value.map((c) => ({ value: String(c.id), label: c.label })),
)

const currentComponent = computed(() => form.component)
const isPhComponent = computed(() => form.component === 'ph_up' || form.component === 'ph_down')

interface ContextPill {
  component: PumpCalibrationComponent
  label: string
  done: boolean
}

const componentToRole: Record<PumpCalibrationComponent, string> = {
  npk: 'pump_a',
  calcium: 'pump_b',
  magnesium: 'pump_c',
  micro: 'pump_d',
  ph_up: 'pump_base',
  ph_down: 'pump_acid',
}

function pumpDoneFor(component: PumpCalibrationComponent): boolean {
  const role = componentToRole[component]
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
    form.duration_sec > 0,
)

const canSave = computed(
  () => canRun.value && typeof form.actual_ml === 'number' && form.actual_ml > 0,
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

const dirtyBadge = computed(() => {
  if (currentStep.value === 'measure' && !form.actual_ml) {
    return 'не сохранено · объём не указан'
  }
  return ''
})

const runRecentAgo = computed(() => {
  if (!runFinishedAt.value) return ''
  const diff = Math.floor((Date.now() - runFinishedAt.value) / 1000)
  if (diff < 60) return `${diff} сек`
  return `${Math.floor(diff / 60)} мин`
})

function isStepDone(id: PumpCalibrationStep): boolean {
  if (id === 'select') return currentStep.value !== 'select' && canRun.value
  if (id === 'measure') return savedForCurrent.value
  return false
}

function formatFloat(v: number | null, digits: number): string {
  if (v === null || !Number.isFinite(v)) return '—'
  return v.toFixed(digits)
}

function runCalibration() {
  if (!canRun.value) return
  emit('start', {
    component: form.component,
    node_channel_id: form.node_channel_id!,
    duration_sec: form.duration_sec,
  })
}

function goToRun() {
  if (!canRun.value) return
  currentStep.value = 'measure'
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
    const hasChannel = pump && pump.node_channel_id > 0
    if (calibrated || !hasChannel) continue

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
      nodeChannelId: pump!.node_channel_id,
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
  lastSavedComponent.value = null
  currentStep.value = 'measure'
}

function saveCalibration() {
  if (!canSave.value) return
  const hasRunToken = runToken.value !== null && runToken.value !== ''
  const payload = {
    component: form.component,
    node_channel_id: form.node_channel_id!,
    duration_sec: form.duration_sec,
    actual_ml: form.actual_ml!,
    skip_run: true as const,
    test_volume_l: form.test_volume_l ?? undefined,
    ec_before_ms: form.ec_before_ms ?? undefined,
    ec_after_ms: form.ec_after_ms ?? undefined,
    temperature_c: form.temperature_c ?? undefined,
    ...(hasRunToken
      ? { run_token: runToken.value! }
      : { manual_override: true as const }),
  }
  emit('save', payload)
}

function onClose() {
  emit('close')
}
</script>

<style scoped>
.hf-drawer-enter-active,
.hf-drawer-leave-active {
  transition: opacity 180ms ease;
}
.hf-drawer-enter-from,
.hf-drawer-leave-to {
  opacity: 0;
}
.hf-drawer-enter-active aside,
.hf-drawer-leave-active aside {
  transition: transform 200ms ease;
}
.hf-drawer-enter-from aside,
.hf-drawer-leave-to aside {
  transform: translateX(8px);
}
</style>
