<template>
    <div class="pc" data-testid="process-calibration-panel">
        <!-- ================== ACTION BAR ================== -->
        <div class="pc__actionbar">
            <div class="pc__actionbar-lhs">
                <span v-if="isDirty" class="pc__badge pc__badge--info">
                    <span class="pc__badge-dot" />
                    изменено в форме
                </span>
                <span class="pc__pill pc__pill--violet">
                    режим: {{ modeLabel(activeMode) }}
                </span>
                <span class="pc__pill">
                    пресет: {{ selectedPresetName }}
                </span>
                <span v-if="selectedUsesFallback" class="pc__pill pc__pill--warn">
                    запасной профиль (generic)
                </span>
                <span v-if="effectiveValidFrom" class="pc__meta">
                    активно с {{ formatDateTime(effectiveValidFrom) }}
                </span>
                <span class="pc__meta">
                    доверие {{ formatConfidence(displayedConfidence) }}
                </span>
            </div>
            <div class="pc__actionbar-rhs">
                <button
                    type="button"
                    class="pc__btn pc__btn--outline"
                    data-testid="process-calibration-history-open"
                    @click="historyOpen = true"
                >
                    История
                    <span class="pc__pill pc__pill--sm">{{ historyEvents.length }}</span>
                </button>
                <button
                    type="button"
                    class="pc__btn pc__btn--outline"
                    :disabled="loading"
                    @click="reload"
                >
                    Откатить изменения
                </button>
                <button
                    type="button"
                    class="pc__btn pc__btn--primary"
                    data-testid="process-calibration-save"
                    :disabled="saving || !isDirty"
                    @click="save"
                >
                    {{ saving ? 'Сохранение…' : `Сохранить ${modeLabel(activeMode)}` }}
                </button>
            </div>
        </div>

        <!-- ================== PRESET STRIP ================== -->
        <div class="pc__preset-strip">
            <span class="pc__preset-strip__label">Пресет</span>
            <button
                v-for="preset in presetOptions"
                :key="preset.key"
                type="button"
                class="pc__preset-pill"
                :class="{ 'pc__preset-pill--active': selectedPresetKey === preset.key }"
                :data-testid="`process-calibration-preset-${preset.key}`"
                :disabled="presetSwitching"
                @click="onPresetPillClick(preset.key)"
            >
                {{ preset.name }}
            </button>
            <span v-if="selectedPresetDescription" class="pc__preset-desc">
                · {{ selectedPresetDescription }}
            </span>
        </div>

        <!-- ================== MODE TABS ================== -->
        <div class="pc__tabs">
            <button
                v-for="mode in modes"
                :key="mode.key"
                type="button"
                class="pc__tab"
                :class="{ 'pc__tab--active': activeMode === mode.key }"
                :data-testid="`process-calibration-tab-${mode.key}`"
                @click="selectMode(mode.key)"
            >
                <span>{{ mode.label }}</span>
                <span v-if="isModeOverridden(mode.key)" class="pc__tab-badge">переопределено</span>
                <span v-else-if="mode.key !== 'generic' && !isSaved(mode.key)" class="pc__tab-badge pc__tab-badge--soft">
                    запасной
                </span>
            </button>
        </div>

        <div v-if="loading" class="pc__skeleton">Загрузка…</div>

        <template v-else>
            <!-- ================== ACTIVE MODE DESCRIPTION ================== -->
            <div class="pc__mode-info">
                <div class="pc__mode-info__title">
                    {{ modeLabel(activeMode) }}
                </div>
                <div class="pc__mode-info__desc">{{ activeModeDescription }}</div>
            </div>

            <!-- ================== SECTIONS (collapsible) ================== -->
            <details
                v-for="section in sections"
                :key="section.key"
                class="pc__section"
                :open="openSections.has(section.key)"
                @toggle="toggleSection(section.key, $event)"
            >
                <summary class="pc__section-summary">
                    <span class="pc__section-title">{{ section.title }}</span>
                    <span class="pc__section-desc">{{ section.desc }}</span>
                </summary>
                <div class="pc__section-body">
                    <label
                        v-for="field in section.fields"
                        :key="field.key"
                        class="pc__field"
                    >
                        <span class="pc__field-label">
                            {{ field.label }}
                            <span v-if="isFieldDirty(field.key)" class="pc__field-dirty">●</span>
                        </span>
                        <input
                            v-model="form[field.key]"
                            :type="field.type"
                            :data-testid="`process-calibration-input-${field.key}`"
                            :step="field.step"
                            :min="field.min"
                            :max="field.max"
                            class="pc__input"
                            :placeholder="field.placeholder"
                        />
                        <span class="pc__field-hint">{{ field.description }}</span>
                        <span v-if="field.hint" class="pc__field-range">{{ field.hint }}</span>
                        <span v-if="validationErrors[field.key]" class="pc__field-error">
                            {{ validationErrors[field.key] }}
                        </span>
                    </label>
                </div>
            </details>

            <!-- ================== PREVIEW ================== -->
            <div class="pc__preview">
                <div>
                    <span>Окно наблюдения</span>
                    <strong>{{ observationWindowLabel }}</strong>
                </div>
                <div>
                    <span>Источник</span>
                    <strong class="pc__preview-mono">{{ calibrationSourceLabel }}</strong>
                </div>
                <div>
                    <span>Доверие</span>
                    <strong>{{ formatConfidence(displayedConfidence) }}</strong>
                </div>
            </div>
        </template>

        <!-- ================== HISTORY DRAWER ================== -->
        <Teleport to="body">
            <transition name="pc-drawer">
                <div v-if="historyOpen" class="pc-drawer-overlay" @click.self="historyOpen = false">
                    <aside class="pc-drawer" role="dialog" aria-modal="true">
                        <header class="pc-drawer__header">
                            <div>
                                <div class="pc-drawer__title">История калибровок</div>
                                <div class="pc-drawer__subtitle">
                                    {{ historyEvents.length }} событий · показаны {{ activeHistoryEvents.length }} для {{ modeLabel(activeMode) }}
                                </div>
                            </div>
                            <button type="button" class="pc-drawer__close" @click="historyOpen = false">×</button>
                        </header>
                        <div class="pc-drawer__body">
                            <div v-if="historyLoading" class="pc-drawer__empty">Загрузка истории…</div>
                            <div v-else-if="activeHistoryEvents.length === 0" class="pc-drawer__empty">
                                Для режима {{ modeLabel(activeMode) }} ещё нет событий сохранения.
                            </div>
                            <ul v-else class="pc-drawer__list">
                                <li
                                    v-for="event in activeHistoryEvents"
                                    :key="event.id"
                                    class="pc-drawer__item"
                                >
                                    <div class="pc-drawer__item-title">{{ event.message }}</div>
                                    <div class="pc-drawer__item-meta">
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
.pc {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
}

/* ============== ACTION BAR ============== */
.pc__actionbar {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 0.75rem;
    padding: 0.6rem 0.85rem;
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 0.5rem;
    flex-wrap: wrap;
}

.pc__actionbar-lhs,
.pc__actionbar-rhs {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    flex-wrap: wrap;
}

.pc__badge {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.22rem 0.6rem;
    border-radius: 9999px;
    font-size: 0.72rem;
    font-weight: 600;
}

.pc__badge--info {
    background: rgba(56, 189, 248, 0.12);
    color: rgb(125, 211, 252);
    border: 1px solid rgba(56, 189, 248, 0.35);
}

.pc__badge-dot {
    width: 6px;
    height: 6px;
    border-radius: 9999px;
    background: currentColor;
}

.pc__pill {
    padding: 0.18rem 0.55rem;
    font-size: 0.72rem;
    border-radius: 9999px;
    background: rgba(148, 163, 184, 0.1);
    border: 1px solid rgba(148, 163, 184, 0.25);
    font-family: ui-monospace, monospace;
}

.pc__pill--violet {
    background: rgba(139, 92, 246, 0.12);
    border-color: rgba(139, 92, 246, 0.35);
    color: rgb(196, 181, 253);
}

.pc__pill--warn {
    background: rgba(251, 191, 36, 0.12);
    border-color: rgba(251, 191, 36, 0.35);
    color: rgb(250, 204, 21);
}

.pc__pill--sm {
    padding: 0.05rem 0.35rem;
    margin-left: 0.3rem;
}

.pc__meta {
    font-size: 0.7rem;
    opacity: 0.65;
    font-family: ui-monospace, monospace;
}

.pc__btn {
    padding: 0.3rem 0.75rem;
    border-radius: 0.35rem;
    border: 1px solid transparent;
    background: transparent;
    color: inherit;
    cursor: pointer;
    font-size: 0.75rem;
    font-weight: 500;
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
}

.pc__btn:disabled {
    cursor: not-allowed;
    opacity: 0.55;
}

.pc__btn--outline {
    border-color: rgba(148, 163, 184, 0.3);
}

.pc__btn--outline:hover:not(:disabled) {
    background: rgba(148, 163, 184, 0.08);
}

.pc__btn--primary {
    background: rgb(56, 189, 248);
    color: #0f172a;
}

.pc__btn--primary:hover:not(:disabled) {
    background: rgb(14, 165, 233);
}

/* ============== PRESET STRIP ============== */
.pc__preset-strip {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.3rem;
    padding: 0.5rem 0.85rem;
    border: 1px solid rgba(148, 163, 184, 0.18);
    border-radius: 0.45rem;
}

.pc__preset-strip__label {
    font-size: 0.62rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-weight: 700;
    opacity: 0.55;
    padding-right: 0.3rem;
}

.pc__preset-pill {
    padding: 0.22rem 0.65rem;
    border-radius: 9999px;
    border: 1px solid rgba(148, 163, 184, 0.3);
    background: transparent;
    color: inherit;
    cursor: pointer;
    font-size: 0.75rem;
}

.pc__preset-pill:hover:not(:disabled) {
    background: rgba(148, 163, 184, 0.08);
}

.pc__preset-pill--active {
    background: rgba(56, 189, 248, 0.12);
    border-color: rgba(56, 189, 248, 0.55);
    color: rgb(125, 211, 252);
    font-weight: 600;
}

.pc__preset-desc {
    font-size: 0.7rem;
    opacity: 0.6;
    margin-left: 0.3rem;
}

/* ============== TABS ============== */
.pc__tabs {
    display: flex;
    gap: 0.3rem;
    flex-wrap: wrap;
    border-bottom: 1px solid rgba(148, 163, 184, 0.15);
    padding-bottom: 0.1rem;
}

.pc__tab {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.45rem 0.8rem;
    border: 1px solid transparent;
    border-bottom: none;
    background: transparent;
    color: inherit;
    cursor: pointer;
    font-size: 0.82rem;
    border-radius: 0.4rem 0.4rem 0 0;
    margin-bottom: -1px;
}

.pc__tab:hover {
    background: rgba(148, 163, 184, 0.06);
}

.pc__tab--active {
    background: rgba(56, 189, 248, 0.1);
    border-color: rgba(56, 189, 248, 0.45);
    border-bottom-color: transparent;
    color: rgb(125, 211, 252);
    font-weight: 600;
}

.pc__tab-badge {
    padding: 0.05rem 0.4rem;
    font-size: 0.62rem;
    border-radius: 9999px;
    background: rgba(139, 92, 246, 0.18);
    color: rgb(196, 181, 253);
    font-weight: 500;
    letter-spacing: 0.03em;
}

.pc__tab-badge--soft {
    background: rgba(148, 163, 184, 0.15);
    color: rgba(148, 163, 184, 0.9);
}

/* ============== MODE INFO ============== */
.pc__mode-info {
    padding: 0.55rem 0.8rem;
    border: 1px solid rgba(148, 163, 184, 0.15);
    border-radius: 0.4rem;
}

.pc__mode-info__title {
    font-weight: 700;
    font-size: 0.9rem;
    margin-bottom: 0.15rem;
}

.pc__mode-info__desc {
    font-size: 0.75rem;
    opacity: 0.7;
    line-height: 1.35;
}

/* ============== SECTIONS ============== */
.pc__section {
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 0.45rem;
    overflow: hidden;
}

.pc__section-summary {
    cursor: pointer;
    list-style: none;
    padding: 0.55rem 0.85rem;
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
}

.pc__section-summary::before {
    content: '▸ ';
    opacity: 0.55;
    margin-right: 0.25rem;
}

.pc__section[open] .pc__section-summary::before {
    content: '▾ ';
}

.pc__section-title {
    font-weight: 600;
    font-size: 0.85rem;
}

.pc__section-desc {
    font-size: 0.7rem;
    opacity: 0.6;
}

.pc__section-body {
    border-top: 1px solid rgba(148, 163, 184, 0.15);
    padding: 0.75rem 0.85rem;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 0.65rem;
}

/* ============== FIELDS ============== */
.pc__field {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-size: 0.8rem;
}

.pc__field-label {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.68rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    font-weight: 600;
    opacity: 0.7;
}

.pc__field-dirty {
    color: rgb(56, 189, 248);
    font-size: 0.9rem;
    line-height: 1;
}

.pc__input {
    padding: 0.42rem 0.55rem;
    border-radius: 0.35rem;
    border: 1px solid rgba(148, 163, 184, 0.3);
    background: transparent;
    color: inherit;
    font-size: 0.85rem;
}

.pc__input:focus-visible {
    outline: none;
    border-color: rgba(56, 189, 248, 0.65);
    box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.16);
}

.pc__field-hint {
    font-size: 0.68rem;
    opacity: 0.65;
    line-height: 1.3;
}

.pc__field-range {
    font-size: 0.65rem;
    opacity: 0.5;
    font-family: ui-monospace, monospace;
}

.pc__field-error {
    font-size: 0.7rem;
    color: rgb(248, 113, 113);
}

/* ============== PREVIEW ============== */
.pc__preview {
    display: flex;
    gap: 1.5rem;
    flex-wrap: wrap;
    padding: 0.6rem 0.85rem;
    border: 1px dashed rgba(56, 189, 248, 0.25);
    background: rgba(56, 189, 248, 0.04);
    border-radius: 0.4rem;
}

.pc__preview > div {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
}

.pc__preview span {
    font-size: 0.6rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    opacity: 0.6;
    font-weight: 600;
}

.pc__preview strong {
    font-size: 0.9rem;
    font-weight: 700;
    color: rgb(125, 211, 252);
}

.pc__preview-mono {
    font-family: ui-monospace, monospace;
    font-size: 0.8rem !important;
}

.pc__skeleton {
    padding: 1rem;
    opacity: 0.6;
    font-size: 0.85rem;
    text-align: center;
}

/* ============== HISTORY DRAWER ============== */
.pc-drawer-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.45);
    z-index: 50;
    display: flex;
    justify-content: flex-end;
}

.pc-drawer {
    width: min(460px, 95vw);
    height: 100vh;
    background: var(--bg-surface, #1e293b);
    border-left: 1px solid rgba(148, 163, 184, 0.25);
    box-shadow: -8px 0 24px rgba(0, 0, 0, 0.3);
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.pc-drawer__header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: 0.85rem 1rem;
    border-bottom: 1px solid rgba(148, 163, 184, 0.18);
}

.pc-drawer__title {
    font-size: 1rem;
    font-weight: 700;
}

.pc-drawer__subtitle {
    font-size: 0.72rem;
    opacity: 0.7;
    margin-top: 0.15rem;
}

.pc-drawer__close {
    background: transparent;
    border: none;
    color: inherit;
    font-size: 1.4rem;
    cursor: pointer;
    line-height: 1;
    padding: 0 0.25rem;
}

.pc-drawer__body {
    flex: 1 1 auto;
    overflow-y: auto;
    padding: 0.85rem 1rem;
}

.pc-drawer__empty {
    padding: 1.5rem 0.5rem;
    opacity: 0.6;
    text-align: center;
    font-size: 0.85rem;
}

.pc-drawer__list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
}

.pc-drawer__item {
    padding: 0.55rem 0.7rem;
    border-radius: 0.4rem;
    border: 1px solid rgba(148, 163, 184, 0.18);
    background: rgba(148, 163, 184, 0.04);
}

.pc-drawer__item-title {
    font-weight: 600;
    font-size: 0.85rem;
}

.pc-drawer__item-meta {
    font-size: 0.7rem;
    opacity: 0.65;
    display: flex;
    gap: 0.35rem;
    flex-wrap: wrap;
    margin-top: 0.2rem;
}

.pc-drawer-enter-from,
.pc-drawer-leave-to {
    opacity: 0;
}
.pc-drawer-enter-active,
.pc-drawer-leave-active {
    transition: opacity 200ms ease;
}
.pc-drawer-enter-active .pc-drawer,
.pc-drawer-leave-active .pc-drawer {
    transition: transform 220ms ease;
}
.pc-drawer-enter-from .pc-drawer,
.pc-drawer-leave-to .pc-drawer {
    transform: translateX(100%);
}
</style>
