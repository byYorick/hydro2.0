<template>
  <div
    class="flex flex-col gap-3"
    data-testid="process-calibration-panel"
  >
    <!-- ACTION BAR -->
    <div class="flex flex-wrap items-center justify-between gap-2 px-3 py-2 rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)]">
      <div class="flex flex-wrap items-center gap-1.5 min-w-0">
        <Chip
          v-if="isDirty"
          tone="brand"
        >
          <template #icon>
            <span class="inline-block w-1.5 h-1.5 rounded-full bg-brand"></span>
          </template>
          изменено в форме
        </Chip>
        <Chip tone="brand">
          режим: <span class="font-mono ml-1">{{ modeLabel(activeMode) }}</span>
        </Chip>
        <Chip tone="neutral">
          пресет: <span class="font-mono ml-1">{{ selectedPresetName }}</span>
        </Chip>
        <Chip
          v-if="selectedUsesFallback"
          tone="warn"
        >
          запасной профиль (generic)
        </Chip>
        <span
          v-if="effectiveValidFrom"
          class="text-[11px] font-mono text-[var(--text-dim)] ml-1"
        >
          активно с {{ formatDateTime(effectiveValidFrom) }}
        </span>
        <span class="text-[11px] font-mono text-[var(--text-dim)] ml-1">
          доверие {{ formatConfidence(displayedConfidence) }}
        </span>
      </div>
      <div class="flex items-center gap-1.5 flex-wrap">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          data-testid="process-calibration-history-open"
          @click="historyOpen = true"
        >
          История
          <Chip tone="neutral">
            <span class="font-mono">{{ historyEvents.length }}</span>
          </Chip>
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          :disabled="loading"
          @click="reload"
        >
          Откатить изменения
        </Button>
        <Button
          type="button"
          size="sm"
          variant="primary"
          data-testid="process-calibration-save"
          :disabled="saving || !isDirty"
          @click="save"
        >
          {{ saving ? 'Сохранение…' : `Сохранить ${modeLabel(activeMode)}` }}
        </Button>
      </div>
    </div>

    <!-- PRESET STRIP -->
    <div class="flex flex-wrap items-center gap-1.5 px-3 py-2 rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)]">
      <span class="text-[10px] uppercase tracking-wider text-[var(--text-dim)] font-semibold pr-1">
        Пресет
      </span>
      <button
        v-for="preset in presetOptions"
        :key="preset.key"
        type="button"
        :class="presetClass(preset.key)"
        :data-testid="`process-calibration-preset-${preset.key}`"
        :disabled="presetSwitching"
        @click="onPresetPillClick(preset.key)"
      >
        {{ preset.name }}
      </button>
      <span
        v-if="selectedPresetDescription"
        class="text-[11px] text-[var(--text-dim)] ml-1"
      >
        · {{ selectedPresetDescription }}
      </span>
    </div>

    <!-- MODE TABS -->
    <div class="flex flex-wrap gap-1 border-b border-[var(--border-muted)]">
      <button
        v-for="mode in modes"
        :key="mode.key"
        type="button"
        :class="tabClass(mode.key)"
        :data-testid="`process-calibration-tab-${mode.key}`"
        @click="selectMode(mode.key)"
      >
        <span>{{ mode.label }}</span>
        <Chip
          v-if="isModeOverridden(mode.key)"
          tone="growth"
        >
          переопределено
        </Chip>
        <Chip
          v-else-if="mode.key !== 'generic' && !isSaved(mode.key)"
          tone="neutral"
        >
          запасной
        </Chip>
      </button>
    </div>

    <div
      v-if="loading"
      class="text-sm text-[var(--text-dim)] py-6 text-center"
    >
      Загрузка…
    </div>

    <template v-else>
      <!-- ACTIVE MODE DESCRIPTION -->
      <div class="px-3 py-2 rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)]">
        <div class="text-sm font-semibold text-[var(--text-primary)]">
          {{ modeLabel(activeMode) }}
        </div>
        <div class="text-[12px] text-[var(--text-muted)] leading-relaxed mt-0.5">
          {{ activeModeDescription }}
        </div>
      </div>

      <!-- SECTIONS (collapsible) -->
      <details
        v-for="section in sections"
        :key="section.key"
        class="rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)] overflow-hidden"
        :open="openSections.has(section.key)"
        @toggle="toggleSection(section.key, $event)"
      >
        <summary class="flex flex-wrap items-baseline gap-2 px-3 py-2 cursor-pointer select-none hover:bg-[var(--bg-surface-strong)] transition-colors">
          <span class="text-sm font-medium text-[var(--text-primary)]">{{ section.title }}</span>
          <span class="text-[11px] text-[var(--text-muted)]">{{ section.desc }}</span>
        </summary>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 px-3 py-3 border-t border-[var(--border-muted)]">
          <Field
            v-for="field in section.fields"
            :key="field.key"
            :label="fieldLabel(field)"
            :hint="field.hint"
            :error="validationErrors[field.key]"
          >
            <input
              v-model="form[field.key]"
              :type="field.type"
              :data-testid="`process-calibration-input-${field.key}`"
              :step="field.step"
              :min="field.min"
              :max="field.max"
              :placeholder="field.placeholder"
              :class="inputCls"
            />
            <span class="text-[11px] text-[var(--text-dim)]">{{ field.description }}</span>
          </Field>
        </div>
      </details>

      <!-- PREVIEW -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3 px-3 py-2.5 rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)]">
        <Stat
          label="Окно наблюдения"
          :value="observationWindowLabel"
          mono
        />
        <Stat
          label="Источник"
          :value="calibrationSourceLabel"
          mono
        />
        <Stat
          label="Доверие"
          :value="formatConfidence(displayedConfidence)"
          mono
          tone="brand"
        />
      </div>
    </template>

    <!-- HISTORY DRAWER -->
    <Teleport to="body">
      <transition name="pc-drawer">
        <div
          v-if="historyOpen"
          class="fixed inset-0 z-50 flex justify-end bg-black/45 backdrop-blur-sm"
          @click.self="historyOpen = false"
        >
          <aside
            class="w-[min(440px,95vw)] h-screen flex flex-col bg-[var(--bg-surface-strong)] border-l border-[var(--border-muted)] shadow-2xl"
            role="dialog"
            aria-modal="true"
          >
            <header class="flex items-start justify-between gap-3 px-4 py-3 border-b border-[var(--border-muted)]">
              <div class="min-w-0">
                <div class="text-sm font-semibold text-[var(--text-primary)]">
                  История калибровок
                </div>
                <div class="text-[11px] text-[var(--text-dim)] mt-0.5">
                  {{ historyEvents.length }} событий · показаны {{ activeHistoryEvents.length }} для {{ modeLabel(activeMode) }}
                </div>
              </div>
              <button
                type="button"
                class="w-7 h-7 inline-flex items-center justify-center rounded-md text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-elevated)]"
                @click="historyOpen = false"
              >
                <Ic name="x" />
              </button>
            </header>
            <div class="flex-1 overflow-y-auto px-3 py-3">
              <div
                v-if="historyLoading"
                class="text-sm text-[var(--text-dim)] py-6 text-center"
              >
                Загрузка истории…
              </div>
              <div
                v-else-if="activeHistoryEvents.length === 0"
                class="text-sm text-[var(--text-dim)] py-6 text-center"
              >
                Для режима {{ modeLabel(activeMode) }} ещё нет событий сохранения.
              </div>
              <ul
                v-else
                class="flex flex-col gap-2"
              >
                <li
                  v-for="event in activeHistoryEvents"
                  :key="event.id"
                  class="rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)] px-3 py-2 flex flex-col gap-1"
                >
                  <div class="text-sm text-[var(--text-primary)]">
                    {{ event.message }}
                  </div>
                  <div class="text-[11px] font-mono text-[var(--text-dim)] flex flex-wrap gap-1">
                    <span>{{ formatDateTime(event.occurredAt) }}</span>
                    <span v-if="event.source">· {{ event.source }}</span>
                    <span v-if="event.observationWindowLabel">· окно {{ event.observationWindowLabel }}</span>
                    <span>· доверие {{ formatConfidence(event.confidence) }}</span>
                  </div>
                </li>
              </ul>
            </div>
          </aside>
        </div>
      </transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import Button from '@/Components/Button.vue'
import { Chip, Field, Stat } from '@/Components/Shared/Primitives'
import Ic from '@/Components/Icons/Ic.vue'
import {
  documentToZoneProcessCalibration,
  isSavedProcessCalibration,
  PROCESS_CALIBRATION_MODES,
  processCalibrationNamespace,
} from '@/composables/processCalibrationAuthority'
import { useAutomationConfig } from '@/composables/useAutomationConfig'
import { api } from '@/services/api'
import {
  createDefaultProcessCalibrationForm,
  useProcessCalibrationDefaults,
} from '@/composables/useProcessCalibrationDefaults'
import {
  normalizeRuntimeTuningBundleDocument,
  RUNTIME_TUNING_BUNDLE_NAMESPACE,
  selectedRuntimeTuningPreset,
  withProcessCalibrationOverride,
  type RuntimeTuningBundlePayload,
} from '@/composables/runtimeTuningBundle'
import { useToast } from '@/composables/useToast'
import type {
  ProcessCalibrationMode,
  ZoneProcessCalibration,
  ZoneProcessCalibrationForm,
} from '@/types/ProcessCalibration'

type FormKey = keyof ZoneProcessCalibrationForm

interface ZoneApiEvent {
  event_id?: number
  id?: number
  type?: string
  created_at?: string | null
  occurred_at?: string | null
  message?: string | null
  payload?: Record<string, unknown> | null
  details?: Record<string, unknown> | null
}

interface ProcessCalibrationHistoryItem {
  id: number
  mode: ProcessCalibrationMode
  message: string
  occurredAt: string | null
  source: string | null
  confidence: number | null
  observationWindowLabel: string | null
}

interface FieldDescriptor {
  key: FormKey
  label: string
  description: string
  hint: string
  type: 'number'
  step: string
  min: number
  max: number
  placeholder: string
}

interface Section {
  key: string
  title: string
  desc: string
  fields: FieldDescriptor[]
}

const props = defineProps<{ zoneId: number }>()
const emit = defineEmits<{
  (e: 'saved', mode: ProcessCalibrationMode): void
}>()

const automationConfig = useAutomationConfig()
const { showToast } = useToast()
const processCalibrationDefaults = useProcessCalibrationDefaults()

const inputCls =
  'w-full px-2.5 py-1.5 rounded-md border border-[var(--border-muted)] bg-[var(--bg-surface)] text-sm text-[var(--text-primary)] focus:outline-none focus:border-brand focus:ring-1 focus:ring-brand/40'

const modes: Array<{ key: ProcessCalibrationMode; label: string; description: string }> = [
  {
    key: 'solution_fill',
    label: 'Наполнение',
    description: 'Коррекция во время набора бака. Важны транспортная задержка и быстрый отклик EC.',
  },
  {
    key: 'tank_recirc',
    label: 'Рециркуляция',
    description: 'Доведение раствора в окне рециркуляции до целевых pH/EC.',
  },
  {
    key: 'irrigation',
    label: 'Полив',
    description: 'Коррекция на потоке полива. Требует осторожных коэффициентов и короткого окна.',
  },
  {
    key: 'generic',
    label: 'Запасной профиль',
    description: 'Базовый запасной профиль, когда конкретный режим не задан.',
  },
]

const sections: Section[] = [
  {
    key: 'window',
    title: 'Окно наблюдения',
    desc: 'Задержка до первого отклика и устойчивое окно стабилизации',
    fields: [
      {
        key: 'transport_delay_sec',
        label: 'Транспортная задержка',
        description: 'Время до первого ожидаемого отклика после дозы.',
        hint: '0..120 сек',
        type: 'number',
        step: '1',
        min: 0,
        max: 120,
        placeholder: 'например, 20',
      },
      {
        key: 'settle_sec',
        label: 'Стабилизация',
        description: 'Окно устойчивого наблюдения после transport delay.',
        hint: '0..300 сек',
        type: 'number',
        step: '1',
        min: 0,
        max: 300,
        placeholder: 'например, 45',
      },
    ],
  },
  {
    key: 'response',
    title: 'Коэффициенты отклика',
    desc: 'Сколько единиц меняется EC/pH на 1 мл дозы соответствующего насоса',
    fields: [
      {
        key: 'ec_gain_per_ml',
        label: 'Отклик EC (1/мл)',
        description: 'На сколько меняется EC после 1 мл EC-дозы.',
        hint: '0.001..10',
        type: 'number',
        step: '0.001',
        min: 0.001,
        max: 10,
        placeholder: 'например, 0.11',
      },
      {
        key: 'ph_up_gain_per_ml',
        label: 'Отклик pH Up (1/мл)',
        description: 'Насколько меняется pH после 1 мл щёлочи.',
        hint: '0.001..5',
        type: 'number',
        step: '0.001',
        min: 0.001,
        max: 5,
        placeholder: 'например, 0.08',
      },
      {
        key: 'ph_down_gain_per_ml',
        label: 'Отклик pH Down (1/мл)',
        description: 'Насколько меняется pH после 1 мл кислоты.',
        hint: '0.001..5',
        type: 'number',
        step: '0.001',
        min: 0.001,
        max: 5,
        placeholder: 'например, 0.07',
      },
    ],
  },
  {
    key: 'cross',
    title: 'Перекрёстное влияние',
    desc: 'Косвенное влияние: EC-доза на pH и pH-доза на EC',
    fields: [
      {
        key: 'ph_per_ec_ml',
        label: 'pH от EC-дозы',
        description: 'Как EC-доза косвенно влияет на pH.',
        hint: '-2..2',
        type: 'number',
        step: '0.001',
        min: -2,
        max: 2,
        placeholder: 'например, -0.015',
      },
      {
        key: 'ec_per_ph_ml',
        label: 'EC от pH-дозы',
        description: 'Как pH-доза косвенно влияет на EC.',
        hint: '-2..2',
        type: 'number',
        step: '0.001',
        min: -2,
        max: 2,
        placeholder: 'например, 0.020',
      },
    ],
  },
  {
    key: 'confidence',
    title: 'Доверие',
    desc: 'Оценка качества текущей калибровки',
    fields: [
      {
        key: 'confidence',
        label: 'Доверие 0..1',
        description: 'Оценка качества текущей калибровки процесса.',
        hint: '0..1',
        type: 'number',
        step: '0.01',
        min: 0,
        max: 1,
        placeholder: 'например, 0.91',
      },
    ],
  },
]

const loading = ref(true)
const historyLoading = ref(true)
const saving = ref(false)
const presetSwitching = ref(false)
const historyOpen = ref(false)
const activeMode = ref<ProcessCalibrationMode>('solution_fill')
const calibrations = ref<Record<ProcessCalibrationMode, ZoneProcessCalibration | null>>({
  generic: null,
  solution_fill: null,
  tank_recirc: null,
  irrigation: null,
})
const form = ref<ZoneProcessCalibrationForm>(emptyForm())
const lastSavedForm = ref<ZoneProcessCalibrationForm>(emptyForm())
const validationErrors = ref<Partial<Record<FormKey, string>>>({})
const historyEvents = ref<ProcessCalibrationHistoryItem[]>([])
const runtimeTuningBundle = ref<RuntimeTuningBundlePayload | null>(null)
const selectedPresetKey = ref('system_default')
const openSections = ref<Set<string>>(new Set(['window', 'response']))

const selectedCalibration = computed(() => calibrations.value[activeMode.value])
const genericCalibration = computed(() => calibrations.value.generic)
const selectedUsesFallback = computed(
  () =>
    activeMode.value !== 'generic' &&
    !isSavedProcessCalibration(selectedCalibration.value) &&
    isSavedProcessCalibration(genericCalibration.value),
)
const selectedUsesSystemDefaults = computed(
  () => !isSavedProcessCalibration(selectedCalibration.value) && !selectedUsesFallback.value,
)
const effectiveCalibration = computed(() =>
  selectedUsesFallback.value ? genericCalibration.value : selectedCalibration.value,
)
const effectiveValidFrom = computed(() => effectiveCalibration.value?.valid_from ?? null)
const activeModeDescription = computed(
  () => modes.find((item) => item.key === activeMode.value)?.description ?? '',
)
const calibrationSourceLabel = computed(() => {
  const src = effectiveCalibration.value?.source
  if (src === 'system_default' || (!src && selectedUsesSystemDefaults.value)) {
    return 'system_default'
  }
  return src ?? 'не задан'
})
const displayedConfidence = computed(() => {
  if (effectiveCalibration.value?.confidence !== null && effectiveCalibration.value?.confidence !== undefined) {
    return effectiveCalibration.value.confidence
  }
  if (selectedUsesSystemDefaults.value) {
    return parseNumeric(form.value.confidence)
  }
  return null
})
const activeHistoryEvents = computed(() => {
  const relevantModes =
    selectedUsesFallback.value && activeMode.value !== 'generic'
      ? new Set<ProcessCalibrationMode>([activeMode.value, 'generic'])
      : new Set<ProcessCalibrationMode>([activeMode.value])
  return historyEvents.value.filter((event) => relevantModes.has(event.mode)).slice(0, 30)
})
const selectedPreset = computed(() => selectedRuntimeTuningPreset(runtimeTuningBundle.value))
const presetOptions = computed(() => runtimeTuningBundle.value?.presets ?? [])
const selectedPresetName = computed(() => selectedPreset.value?.name ?? 'Системный пресет')
const selectedPresetDescription = computed(() => selectedPreset.value?.description ?? '')
const observationWindowLabel = computed(() => {
  const transport = parseNumeric(form.value.transport_delay_sec) ?? 0
  const settle = parseNumeric(form.value.settle_sec) ?? 0
  return `${transport} + ${settle} = ${transport + settle} сек`
})

const isDirty = computed(() => {
  for (const section of sections) {
    for (const field of section.fields) {
      if (String(form.value[field.key] ?? '') !== String(lastSavedForm.value[field.key] ?? '')) {
        return true
      }
    }
  }
  return false
})

function isFieldDirty(key: FormKey): boolean {
  return String(form.value[key] ?? '') !== String(lastSavedForm.value[key] ?? '')
}

function fieldLabel(field: FieldDescriptor): string {
  return isFieldDirty(field.key) ? `${field.label} ●` : field.label
}

function presetClass(key: string): string {
  const active = selectedPresetKey.value === key
  return [
    'px-2.5 py-1 rounded-full border text-[12px] cursor-pointer transition-colors',
    active
      ? 'bg-brand-soft border-brand text-brand-ink font-semibold'
      : 'border-[var(--border-muted)] text-[var(--text-muted)] hover:bg-[var(--bg-surface-strong)]',
    presetSwitching.value ? 'opacity-55 cursor-not-allowed' : '',
  ].join(' ')
}

function tabClass(mode: ProcessCalibrationMode): string {
  const active = activeMode.value === mode
  return [
    'flex items-center gap-2 px-3 py-2 -mb-px text-sm font-medium border-b-2 transition-colors cursor-pointer',
    active ? 'border-brand text-brand' : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]',
  ].join(' ')
}

function isSaved(mode: ProcessCalibrationMode): boolean {
  return isSavedProcessCalibration(calibrations.value[mode])
}

function isModeOverridden(mode: ProcessCalibrationMode): boolean {
  return mode !== 'generic' && isSaved(mode)
}

function emptyForm(): ZoneProcessCalibrationForm {
  return createDefaultProcessCalibrationForm(processCalibrationDefaults.value)
}

function modeLabel(mode: ProcessCalibrationMode): string {
  return modes.find((item) => item.key === mode)?.label ?? mode
}

function parseNumeric(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) return null
  const normalized = typeof value === 'string' ? value.trim() : String(value)
  if (normalized === '') return null
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : null
}

function formatNumeric(value: number | null | undefined, step: string): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return ''
  if (step === '1') return String(Math.trunc(value))
  return String(value)
}

function hydrateForm(mode: ProcessCalibrationMode): void {
  const preview = runtimeTuningBundle.value?.resolved_preview.process_calibration?.[mode]
  const source =
    preview && Object.keys(preview).length > 0
      ? preview
      : (calibrations.value[mode] ?? (mode === 'generic' ? null : calibrations.value.generic))
  const next: ZoneProcessCalibrationForm = source
    ? {
        ec_gain_per_ml: formatNumeric(
          parseNumeric(source.ec_gain_per_ml as string | number | null | undefined),
          '0.001',
        ),
        ph_up_gain_per_ml: formatNumeric(
          parseNumeric(source.ph_up_gain_per_ml as string | number | null | undefined),
          '0.001',
        ),
        ph_down_gain_per_ml: formatNumeric(
          parseNumeric(source.ph_down_gain_per_ml as string | number | null | undefined),
          '0.001',
        ),
        ph_per_ec_ml: formatNumeric(
          parseNumeric(source.ph_per_ec_ml as string | number | null | undefined),
          '0.001',
        ),
        ec_per_ph_ml: formatNumeric(
          parseNumeric(source.ec_per_ph_ml as string | number | null | undefined),
          '0.001',
        ),
        transport_delay_sec: formatNumeric(
          parseNumeric(source.transport_delay_sec as string | number | null | undefined),
          '1',
        ),
        settle_sec: formatNumeric(
          parseNumeric(source.settle_sec as string | number | null | undefined),
          '1',
        ),
        confidence: formatNumeric(
          parseNumeric(source.confidence as string | number | null | undefined),
          '0.01',
        ),
      }
    : createDefaultProcessCalibrationForm(processCalibrationDefaults.value)

  form.value = { ...next }
  lastSavedForm.value = { ...next }
  validationErrors.value = {}
}

function selectMode(mode: ProcessCalibrationMode): void {
  if (isDirty.value) {
    const proceed = window.confirm('Несохранённые изменения будут потеряны. Продолжить?')
    if (!proceed) return
  }
  activeMode.value = mode
  hydrateForm(mode)
}

function toggleSection(key: string, event: ToggleEvent | Event) {
  const open = (event.target as HTMLDetailsElement).open
  const next = new Set(openSections.value)
  if (open) next.add(key)
  else next.delete(key)
  openSections.value = next
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('ru-RU')
}

function formatConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return value.toFixed(2)
}

function validateForm(): boolean {
  const nextErrors: Partial<Record<FormKey, string>> = {}
  for (const section of sections) {
    for (const field of section.fields) {
      const parsed = parseNumeric(form.value[field.key])
      if (parsed === null) continue
      if (parsed < field.min || parsed > field.max) {
        nextErrors[field.key] = `диапазон ${field.min}..${field.max}`
      }
    }
  }
  validationErrors.value = nextErrors
  return Object.keys(nextErrors).length === 0
}

async function loadCalibrations(): Promise<void> {
  loading.value = true
  try {
    const [bundleDocument, ...documents] = await Promise.all([
      automationConfig.getDocument<Record<string, unknown>>(
        'zone',
        props.zoneId,
        RUNTIME_TUNING_BUNDLE_NAMESPACE,
      ),
      ...PROCESS_CALIBRATION_MODES.map((mode) =>
        automationConfig.getDocument<Record<string, unknown>>(
          'zone',
          props.zoneId,
          processCalibrationNamespace(mode),
        ),
      ),
    ])
    runtimeTuningBundle.value = normalizeRuntimeTuningBundleDocument(bundleDocument)
    selectedPresetKey.value = runtimeTuningBundle.value.selected_preset_key
    const nextDocuments = documents as Awaited<
      ReturnType<typeof automationConfig.getDocument<Record<string, unknown>>>
    >[]
    const next: Record<ProcessCalibrationMode, ZoneProcessCalibration | null> = {
      generic: null,
      solution_fill: null,
      tank_recirc: null,
      irrigation: null,
    }
    PROCESS_CALIBRATION_MODES.forEach((mode, index) => {
      next[mode] = documentToZoneProcessCalibration(props.zoneId, mode, nextDocuments[index])
    })
    calibrations.value = next
    hydrateForm(activeMode.value)
  } finally {
    loading.value = false
  }
}

async function persistRuntimeTuningBundle(nextBundle: RuntimeTuningBundlePayload): Promise<void> {
  const document = await automationConfig.updateDocument(
    'zone',
    props.zoneId,
    RUNTIME_TUNING_BUNDLE_NAMESPACE,
    nextBundle,
  )
  runtimeTuningBundle.value = normalizeRuntimeTuningBundleDocument(document)
  selectedPresetKey.value = runtimeTuningBundle.value.selected_preset_key
}

async function onPresetPillClick(key: string): Promise<void> {
  if (!runtimeTuningBundle.value) return
  if (selectedPresetKey.value === key) return
  selectedPresetKey.value = key

  presetSwitching.value = true
  try {
    await persistRuntimeTuningBundle({
      ...runtimeTuningBundle.value,
      selected_preset_key: key,
    })
    await loadCalibrations()
    showToast(`Пресет «${selectedPresetName.value}» применён`, 'success')
  } finally {
    presetSwitching.value = false
  }
}

function toPayloadRecord(raw: unknown): Record<string, unknown> | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  return raw as Record<string, unknown>
}

function toProcessCalibrationMode(value: unknown): ProcessCalibrationMode | null {
  if (
    value === 'generic' ||
    value === 'solution_fill' ||
    value === 'tank_recirc' ||
    value === 'irrigation'
  ) {
    return value
  }
  return null
}

function toObservationWindowLabel(payload: Record<string, unknown> | null): string | null {
  const transport = parseNumeric(payload?.transport_delay_sec as string | number | null | undefined)
  const settle = parseNumeric(payload?.settle_sec as string | number | null | undefined)
  if (transport === null && settle === null) return null
  return `${transport ?? 0}+${settle ?? 0} сек`
}

function toHistoryItem(raw: ZoneApiEvent): ProcessCalibrationHistoryItem | null {
  if (raw.type !== 'PROCESS_CALIBRATION_SAVED') return null
  const payload = toPayloadRecord(raw.payload ?? raw.details)
  const mode = toProcessCalibrationMode(payload?.mode)
  const id = Number(raw.event_id ?? raw.id)
  if (!mode || !Number.isInteger(id) || id <= 0) return null
  return {
    id,
    mode,
    message:
      typeof raw.message === 'string' && raw.message.trim() !== ''
        ? raw.message
        : 'Калибровка процесса обновлена',
    occurredAt: raw.occurred_at ?? raw.created_at ?? null,
    source: typeof payload?.source === 'string' ? payload.source : null,
    confidence: parseNumeric(payload?.confidence as string | number | null | undefined),
    observationWindowLabel: toObservationWindowLabel(payload),
  }
}

async function loadHistory(): Promise<void> {
  historyLoading.value = true
  try {
    const response = (await api.zones.events(props.zoneId, { limit: 80 })) as
      | ZoneApiEvent[]
      | { data?: ZoneApiEvent[] }
    const items: ZoneApiEvent[] = Array.isArray(response)
      ? response
      : Array.isArray(response?.data)
        ? response.data
        : []
    historyEvents.value = items
      .map((item) => toHistoryItem(item))
      .filter((item): item is ProcessCalibrationHistoryItem => item !== null)
      .sort((left, right) => right.id - left.id)
  } finally {
    historyLoading.value = false
  }
}

async function reload(): Promise<void> {
  await Promise.all([loadCalibrations(), loadHistory()])
}

async function save(): Promise<void> {
  if (!validateForm()) {
    showToast('Проверьте диапазоны калибровки процесса.', 'warning')
    return
  }

  const payload = {
    mode: activeMode.value,
    ec_gain_per_ml: parseNumeric(form.value.ec_gain_per_ml),
    ph_up_gain_per_ml: parseNumeric(form.value.ph_up_gain_per_ml),
    ph_down_gain_per_ml: parseNumeric(form.value.ph_down_gain_per_ml),
    ph_per_ec_ml: parseNumeric(form.value.ph_per_ec_ml),
    ec_per_ph_ml: parseNumeric(form.value.ec_per_ph_ml),
    transport_delay_sec: parseNumeric(form.value.transport_delay_sec),
    settle_sec: parseNumeric(form.value.settle_sec),
    confidence: parseNumeric(form.value.confidence),
    source: 'manual',
    valid_from: new Date().toISOString(),
    valid_to: null,
    is_active: true,
    meta: {
      ...(selectedCalibration.value?.meta ?? {}),
    },
  }

  if (!runtimeTuningBundle.value) {
    showToast('Настройки runtime-тюнинга зоны ещё не загружены.', 'warning')
    return
  }

  saving.value = true
  try {
    await persistRuntimeTuningBundle(
      withProcessCalibrationOverride(runtimeTuningBundle.value, activeMode.value, payload),
    )
    showToast(`Калибровка «${modeLabel(activeMode.value)}» сохранена.`, 'success')
    await Promise.all([loadCalibrations(), loadHistory()])
    emit('saved', activeMode.value)
  } finally {
    saving.value = false
  }
}

watch(
  () => props.zoneId,
  () => {
    void reload()
  },
)

onMounted(() => {
  void reload()
})
</script>

<style scoped>
.pc-drawer-enter-active,
.pc-drawer-leave-active {
  transition: opacity 180ms ease;
}
.pc-drawer-enter-from,
.pc-drawer-leave-to {
  opacity: 0;
}
.pc-drawer-enter-active aside,
.pc-drawer-leave-active aside {
  transition: transform 200ms ease;
}
.pc-drawer-enter-from aside,
.pc-drawer-leave-to aside {
  transform: translateX(8px);
}
</style>
