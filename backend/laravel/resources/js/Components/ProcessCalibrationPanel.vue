<template>
  <Card
    class="process-calibration-panel"
    data-testid="process-calibration-panel"
  >
    <div class="space-y-4">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="text-sm font-semibold">
            Калибровка процесса
          </div>
          <div class="mt-1 text-xs text-[color:var(--text-dim)]">
            Настройка окна наблюдения и коэффициентов отклика для in-flow correction.
          </div>
        </div>
        <Badge :variant="selectedUsesFallback ? 'warning' : 'info'">
          {{ selectedUsesFallback ? 'Fallback на generic' : modeLabel(activeMode) }}
        </Badge>
      </div>

      <div class="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]">
        <label class="space-y-1.5">
          <span class="block text-xs font-medium text-[color:var(--text-muted)]">
            Preset runtime tuning
          </span>
          <select
            v-model="selectedPresetKey"
            class="input-select w-full"
            data-testid="process-calibration-preset-select"
            :disabled="loading || saving || presetSwitching"
            @change="applySelectedPreset"
          >
            <option
              v-for="preset in presetOptions"
              :key="preset.key"
              :value="preset.key"
            >
              {{ preset.name }}
            </option>
          </select>
          <span class="block text-[11px] text-[color:var(--text-dim)]">
            {{ selectedPresetDescription }}
          </span>
        </label>

        <div class="flex items-end">
          <Button
            size="sm"
            variant="outline"
            data-testid="process-calibration-toggle-advanced"
            :disabled="loading"
            @click="showAdvanced = !showAdvanced"
          >
            {{ showAdvanced ? 'Скрыть расширенные настройки' : 'Расширенные настройки' }}
          </Button>
        </div>
      </div>

      <div class="flex flex-wrap gap-2">
        <Button
          v-for="mode in modes"
          :key="mode.key"
          size="sm"
          :variant="activeMode === mode.key ? 'default' : 'outline'"
          :data-testid="`process-calibration-mode-${mode.key}`"
          @click="selectMode(mode.key)"
        >
          {{ mode.label }}
        </Button>
      </div>

      <div
        v-if="loading"
        class="text-sm text-[color:var(--text-dim)]"
      >
        Загрузка...
      </div>

      <div
        v-else
        class="space-y-4"
      >
        <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3 text-xs text-[color:var(--text-dim)]">
          <div class="font-medium text-[color:var(--text-primary)]">
            {{
              selectedUsesFallback
                ? `Для режима ${modeLabel(activeMode)} используется общий fallback-профиль calibration.`
                : selectedUsesSystemDefaults
                  ? `Для режима ${modeLabel(activeMode)} применён материализованный системный профиль по умолчанию.`
                  : `Режим: ${modeLabel(activeMode)}`
            }}
          </div>
          <div class="mt-1">
            {{ activeModeDescription }}
          </div>
          <div
            v-if="selectedUsesSystemDefaults"
            class="mt-1"
          >
            Это валидный bootstrap preset зоны. Его можно использовать как стартовую конфигурацию без обязательного первого сохранения.
          </div>
          <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1">
            <span>Пресет: {{ selectedPresetName }}</span>
            <span>Источник: {{ calibrationSourceLabel }}</span>
            <span>Активно с: {{ formatDateTime(effectiveCalibration?.valid_from) }}</span>
            <span>Доверие: {{ formatConfidence(displayedConfidence) }}</span>
          </div>
        </div>

        <div
          v-if="showAdvanced"
          class="grid gap-4 md:grid-cols-2 xl:grid-cols-4"
        >
          <label
            v-for="field in fields"
            :key="field.key"
            class="space-y-1.5"
          >
            <span class="block text-xs font-medium text-[color:var(--text-muted)]">
              {{ field.label }}
            </span>
            <input
              v-model="form[field.key]"
              :type="field.type"
              :data-testid="`process-calibration-input-${field.key}`"
              :step="field.step"
              :min="field.min"
              :max="field.max"
              class="input-field w-full"
              :placeholder="field.placeholder"
              :title="`${field.description} ${field.hint}`"
            />
            <span class="block text-[11px] text-[color:var(--text-dim)]">
              {{ field.description }}
            </span>
            <span class="block text-[11px] text-[color:var(--text-muted)]">
              {{ field.hint }}
            </span>
            <span
              v-if="validationErrors[field.key]"
              class="block text-[11px] text-[color:var(--badge-danger-text)]"
            >
              {{ validationErrors[field.key] }}
            </span>
          </label>
        </div>

        <div class="rounded-xl border border-[color:var(--border-muted)] p-3 text-xs text-[color:var(--text-dim)]">
          <div class="font-medium text-[color:var(--text-primary)]">
            Окно наблюдения
          </div>
          <div class="mt-1">
            `transport_delay_sec + settle_sec = {{ observationWindowLabel }}`
          </div>
          <div class="mt-2">
            Runtime сначала ждёт доставку дозы до датчика, затем добирает устойчивое окно наблюдения.
            Материализованные bootstrap defaults уже считаются валидной стартовой калибровкой.
          </div>
        </div>

        <div class="rounded-xl border border-[color:var(--border-muted)] p-3 text-xs text-[color:var(--text-dim)]">
          <div class="flex items-center justify-between gap-3">
            <div class="font-medium text-[color:var(--text-primary)]">
              История calibration
            </div>
            <span class="text-[11px] text-[color:var(--text-muted)]">
              {{ activeHistoryEvents.length }} событий
            </span>
          </div>
          <div
            v-if="historyLoading"
            class="mt-2"
          >
            Загрузка истории...
          </div>
          <div
            v-else-if="activeHistoryEvents.length === 0"
            class="mt-2"
          >
            Для режима {{ modeLabel(activeMode) }} ещё нет событий сохранения calibration.
          </div>
          <div
            v-else
            class="mt-2 space-y-2"
          >
            <div
              v-for="event in activeHistoryEvents"
              :key="event.id"
              class="rounded-lg bg-[color:var(--bg-elevated)] px-3 py-2"
            >
              <div class="font-medium text-[color:var(--text-primary)]">
                {{ event.message }}
              </div>
              <div class="mt-1 flex flex-wrap gap-x-4 gap-y-1">
                <span>Время: {{ formatDateTime(event.occurredAt) }}</span>
                <span>Источник: {{ event.source ?? 'не задан' }}</span>
                <span>Доверие: {{ formatConfidence(event.confidence) }}</span>
                <span v-if="event.observationWindowLabel">Окно: {{ event.observationWindowLabel }}</span>
              </div>
            </div>
          </div>
        </div>

        <div
          v-if="showAdvanced"
          class="flex flex-wrap items-center gap-2"
        >
          <Button
            size="sm"
            data-testid="process-calibration-save"
            :disabled="saving"
            @click="save"
          >
            {{ saving ? 'Сохранение...' : `Сохранить ${modeLabel(activeMode)}` }}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            :disabled="loading || saving"
            @click="resetForm"
          >
            Восстановить значения
          </Button>
        </div>
      </div>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import Card from '@/Components/Card.vue'
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

const props = defineProps<{ zoneId: number }>()
const emit = defineEmits<{
  (e: 'saved', mode: ProcessCalibrationMode): void
}>()

const automationConfig = useAutomationConfig()
const { showToast } = useToast()
const processCalibrationDefaults = useProcessCalibrationDefaults()

const modes: Array<{ key: ProcessCalibrationMode; label: string; description: string }> = [
  {
    key: 'solution_fill',
    label: 'Наполнение',
    description: 'Коррекция во время набора бака. Здесь особенно важны transport delay и быстрый отклик EC.',
  },
  {
    key: 'tank_recirc',
    label: 'Рециркуляция',
    description: 'Доведение раствора в recirculation window до достижения целевых pH/EC.',
  },
  {
    key: 'irrigation',
    label: 'Полив',
    description: 'Коррекция на потоке полива. Обычно требует более осторожных gain и короткого окна ожидания.',
  },
  {
    key: 'generic',
    label: 'Общий fallback (generic)',
    description: 'Базовый fallback-профиль, если для конкретной фазы калибровка ещё не задана.',
  },
]

const fields: FieldDescriptor[] = [
  {
    key: 'transport_delay_sec',
    label: 'Транспортная задержка',
    description: 'Время до первого ожидаемого отклика после дозы.',
    hint: 'Диапазон 0..120 сек.',
    type: 'number',
    step: '1',
    min: 0,
    max: 120,
    placeholder: 'например, 20',
  },
  {
    key: 'settle_sec',
    label: 'Время стабилизации',
    description: 'Дополнительное окно для устойчивого наблюдения после transport delay.',
    hint: 'Диапазон 0..300 сек.',
    type: 'number',
    step: '1',
    min: 0,
    max: 300,
    placeholder: 'например, 45',
  },
  {
    key: 'ec_gain_per_ml',
    label: 'Коэффициент отклика EC',
    description: 'Показывает, на сколько единиц EC обычно меняется раствор после 1 мл EC-дозы.',
    hint: 'Диапазон 0.001..10.',
    type: 'number',
    step: '0.001',
    min: 0.001,
    max: 10,
    placeholder: 'например, 0.11',
  },
  {
    key: 'ph_up_gain_per_ml',
    label: 'Коэффициент pH-up',
    description: 'Насколько в среднем меняется pH после 1 мл щёлочи.',
    hint: 'Диапазон 0.001..5.',
    type: 'number',
    step: '0.001',
    min: 0.001,
    max: 5,
    placeholder: 'например, 0.08',
  },
  {
    key: 'ph_down_gain_per_ml',
    label: 'Коэффициент pH-down',
    description: 'Насколько в среднем меняется pH после 1 мл кислоты.',
    hint: 'Диапазон 0.001..5.',
    type: 'number',
    step: '0.001',
    min: 0.001,
    max: 5,
    placeholder: 'например, 0.07',
  },
  {
    key: 'ph_per_ec_ml',
    label: 'Поправка pH от EC',
    description: 'Cross-coupling коэффициент: как EC-доза косвенно влияет на pH.',
    hint: 'Диапазон -2..2.',
    type: 'number',
    step: '0.001',
    min: -2,
    max: 2,
    placeholder: 'например, -0.015',
  },
  {
    key: 'ec_per_ph_ml',
    label: 'Поправка EC от pH',
    description: 'Cross-coupling коэффициент: как pH-доза косвенно влияет на EC.',
    hint: 'Диапазон -2..2.',
    type: 'number',
    step: '0.001',
    min: -2,
    max: 2,
    placeholder: 'например, 0.020',
  },
  {
    key: 'confidence',
    label: 'Доверие к калибровке',
    description: 'Оценка качества текущей process calibration в диапазоне 0..1.',
    hint: 'Диапазон 0..1.',
    type: 'number',
    step: '0.01',
    min: 0,
    max: 1,
    placeholder: 'например, 0.91',
  },
]

const loading = ref(true)
const historyLoading = ref(true)
const saving = ref(false)
const presetSwitching = ref(false)
const showAdvanced = ref(false)
const activeMode = ref<ProcessCalibrationMode>('solution_fill')
const calibrations = ref<Record<ProcessCalibrationMode, ZoneProcessCalibration | null>>({
  generic: null,
  solution_fill: null,
  tank_recirc: null,
  irrigation: null,
})
const form = ref<ZoneProcessCalibrationForm>(emptyForm())
const validationErrors = ref<Partial<Record<FormKey, string>>>({})
const historyEvents = ref<ProcessCalibrationHistoryItem[]>([])
const runtimeTuningBundle = ref<RuntimeTuningBundlePayload | null>(null)
const selectedPresetKey = ref('system_default')

const selectedCalibration = computed(() => calibrations.value[activeMode.value])
const genericCalibration = computed(() => calibrations.value.generic)
const selectedUsesFallback = computed(() => activeMode.value !== 'generic' && !isSavedProcessCalibration(selectedCalibration.value) && isSavedProcessCalibration(genericCalibration.value))
const selectedUsesSystemDefaults = computed(() => !isSavedProcessCalibration(selectedCalibration.value) && !selectedUsesFallback.value)
const effectiveCalibration = computed(() => selectedUsesFallback.value ? genericCalibration.value : selectedCalibration.value)
const activeModeDescription = computed(() => modes.find((item) => item.key === activeMode.value)?.description ?? '')
const calibrationSourceLabel = computed(() => {
  const selectedSource = effectiveCalibration.value?.source
  if (selectedSource === 'system_default') {
    return 'системные значения по умолчанию'
  }
  if (effectiveCalibration.value?.source) {
    return effectiveCalibration.value.source
  }
  if (selectedUsesSystemDefaults.value) {
    return 'системные значения по умолчанию'
  }

  return 'не задан'
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
  const relevantModes = selectedUsesFallback.value && activeMode.value !== 'generic'
    ? new Set<ProcessCalibrationMode>([activeMode.value, 'generic'])
    : new Set<ProcessCalibrationMode>([activeMode.value])

  return historyEvents.value
    .filter((event) => relevantModes.has(event.mode))
    .slice(0, 6)
})
const selectedPreset = computed(() => selectedRuntimeTuningPreset(runtimeTuningBundle.value))
const presetOptions = computed(() => runtimeTuningBundle.value?.presets ?? [])
const selectedPresetName = computed(() => selectedPreset.value?.name ?? 'Системный preset')
const selectedPresetDescription = computed(() => selectedPreset.value?.description ?? 'Канонические стартовые значения process calibration и PID для зоны.')
const observationWindowLabel = computed(() => {
  const transport = parseNumeric(form.value.transport_delay_sec) ?? 0
  const settle = parseNumeric(form.value.settle_sec) ?? 0
  return `${transport + settle} сек`
})

function emptyForm(): ZoneProcessCalibrationForm {
  return createDefaultProcessCalibrationForm(processCalibrationDefaults.value)
}

function modeLabel(mode: ProcessCalibrationMode): string {
  return modes.find((item) => item.key === mode)?.label ?? mode
}

function parseNumeric(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) {
    return null
  }

  const normalized = typeof value === 'string' ? value.trim() : String(value)
  if (normalized === '') {
    return null
  }

  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : null
}

function formatNumeric(value: number | null | undefined, step: string): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return ''
  }
  if (step === '1') {
    return String(Math.trunc(value))
  }
  return String(value)
}

function hydrateForm(mode: ProcessCalibrationMode): void {
  const preview = runtimeTuningBundle.value?.resolved_preview.process_calibration?.[mode]
  const source = preview && Object.keys(preview).length > 0
    ? preview
    : (calibrations.value[mode] ?? (mode === 'generic' ? null : calibrations.value.generic))
  form.value = source
    ? {
      ec_gain_per_ml: formatNumeric(parseNumeric(source.ec_gain_per_ml as string | number | null | undefined), '0.001'),
      ph_up_gain_per_ml: formatNumeric(parseNumeric(source.ph_up_gain_per_ml as string | number | null | undefined), '0.001'),
      ph_down_gain_per_ml: formatNumeric(parseNumeric(source.ph_down_gain_per_ml as string | number | null | undefined), '0.001'),
      ph_per_ec_ml: formatNumeric(parseNumeric(source.ph_per_ec_ml as string | number | null | undefined), '0.001'),
      ec_per_ph_ml: formatNumeric(parseNumeric(source.ec_per_ph_ml as string | number | null | undefined), '0.001'),
      transport_delay_sec: formatNumeric(parseNumeric(source.transport_delay_sec as string | number | null | undefined), '1'),
      settle_sec: formatNumeric(parseNumeric(source.settle_sec as string | number | null | undefined), '1'),
      confidence: formatNumeric(parseNumeric(source.confidence as string | number | null | undefined), '0.01'),
    }
    : createDefaultProcessCalibrationForm(processCalibrationDefaults.value)
  validationErrors.value = {}
}

function resetForm(): void {
  hydrateForm(activeMode.value)
}

function selectMode(mode: ProcessCalibrationMode): void {
  activeMode.value = mode
  hydrateForm(mode)
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return 'не задано'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return 'не задано'
  }
  return date.toLocaleString('ru-RU')
}

function formatConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return 'не задан'
  }
  return value.toFixed(2)
}

function validateForm(): boolean {
  const nextErrors: Partial<Record<FormKey, string>> = {}

  for (const field of fields) {
    const parsed = parseNumeric(form.value[field.key])
    if (parsed === null) {
      continue
    }
    if (parsed < field.min || parsed > field.max) {
      nextErrors[field.key] = `${field.label}: диапазон ${field.min}..${field.max}`
    }
  }

  validationErrors.value = nextErrors
  return Object.keys(nextErrors).length === 0
}

async function loadCalibrations(): Promise<void> {
  loading.value = true
  try {
    const [bundleDocument, ...documents] = await Promise.all(
      [
        automationConfig.getDocument<Record<string, unknown>>('zone', props.zoneId, RUNTIME_TUNING_BUNDLE_NAMESPACE),
      ].concat(
        PROCESS_CALIBRATION_MODES.map((mode) =>
          automationConfig.getDocument<Record<string, unknown>>('zone', props.zoneId, processCalibrationNamespace(mode))
        )
      )
    )
    runtimeTuningBundle.value = normalizeRuntimeTuningBundleDocument(bundleDocument)
    selectedPresetKey.value = runtimeTuningBundle.value.selected_preset_key
    const nextDocuments = documents as Awaited<ReturnType<typeof automationConfig.getDocument<Record<string, unknown>>>>[]
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
  const document = await automationConfig.updateDocument('zone', props.zoneId, RUNTIME_TUNING_BUNDLE_NAMESPACE, nextBundle)
  runtimeTuningBundle.value = normalizeRuntimeTuningBundleDocument(document)
  selectedPresetKey.value = runtimeTuningBundle.value.selected_preset_key
}

async function applySelectedPreset(): Promise<void> {
  if (!runtimeTuningBundle.value) {
    return
  }

  presetSwitching.value = true
  try {
    await persistRuntimeTuningBundle({
      ...runtimeTuningBundle.value,
      selected_preset_key: selectedPresetKey.value,
    })
    await loadCalibrations()
    showToast(`Preset "${selectedPresetName.value}" применён к runtime tuning зоны.`, 'success')
  } finally {
    presetSwitching.value = false
  }
}

function toPayloadRecord(raw: unknown): Record<string, unknown> | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return null
  }

  return raw as Record<string, unknown>
}

function toProcessCalibrationMode(value: unknown): ProcessCalibrationMode | null {
  if (value === 'generic' || value === 'solution_fill' || value === 'tank_recirc' || value === 'irrigation') {
    return value
  }

  return null
}

function toObservationWindowLabel(payload: Record<string, unknown> | null): string | null {
  const transport = parseNumeric(payload?.transport_delay_sec as string | number | null | undefined)
  const settle = parseNumeric(payload?.settle_sec as string | number | null | undefined)

  if (transport === null && settle === null) {
    return null
  }

  return `${transport ?? 0}+${settle ?? 0} сек`
}

function toHistoryItem(raw: ZoneApiEvent): ProcessCalibrationHistoryItem | null {
  if (raw.type !== 'PROCESS_CALIBRATION_SAVED') {
    return null
  }

  const payload = toPayloadRecord(raw.payload ?? raw.details)
  const mode = toProcessCalibrationMode(payload?.mode)
  const id = Number(raw.event_id ?? raw.id)

  if (!mode || !Number.isInteger(id) || id <= 0) {
    return null
  }

  return {
    id,
    mode,
    message: typeof raw.message === 'string' && raw.message.trim() !== '' ? raw.message : 'Process calibration обновлена',
    occurredAt: raw.occurred_at ?? raw.created_at ?? null,
    source: typeof payload?.source === 'string' ? payload.source : null,
    confidence: parseNumeric(payload?.confidence as string | number | null | undefined),
    observationWindowLabel: toObservationWindowLabel(payload),
  }
}

async function loadHistory(): Promise<void> {
  historyLoading.value = true
  try {
    const response = await api.zones.events(props.zoneId, { limit: 80 }) as ZoneApiEvent[] | { data?: ZoneApiEvent[] }
    const items: ZoneApiEvent[] = Array.isArray(response)
      ? response
      : (Array.isArray(response?.data) ? response.data : [])

    historyEvents.value = items
      .map((item) => toHistoryItem(item))
      .filter((item): item is ProcessCalibrationHistoryItem => item !== null)
      .sort((left, right) => right.id - left.id)
  } finally {
    historyLoading.value = false
  }
}

async function save(): Promise<void> {
  if (!validateForm()) {
    showToast('Проверь диапазоны process calibration.', 'warning')
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
    showToast('Runtime tuning bundle зоны ещё не загружен.', 'warning')
    return
  }

  saving.value = true
  try {
    await persistRuntimeTuningBundle(withProcessCalibrationOverride(runtimeTuningBundle.value, activeMode.value, payload))
    showToast(`Калибровка процесса для режима "${modeLabel(activeMode.value)}" сохранена.`, 'success')
    await Promise.all([loadCalibrations(), loadHistory()])
    emit('saved', activeMode.value)
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void Promise.all([loadCalibrations(), loadHistory()])
})
</script>

<style scoped>
.process-calibration-panel :deep(.input-field) {
  height: 2.2rem;
  padding: 0 0.7rem;
  font-size: 0.78rem;
  border-radius: 0.72rem;
}
</style>
