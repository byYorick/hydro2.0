<template>
    <Teleport to="body">
        <transition name="cal-drawer">
            <div v-if="show" class="pcd-overlay" @click.self="onClose">
                <aside class="pcd" role="dialog" aria-modal="true">
                    <header class="pcd__header">
                        <div>
                            <div class="pcd__title">Калибровка насоса</div>
                            <div class="pcd__breadcrumb">
                                / зона#{{ zoneId }} / насос / {{ currentComponent }}
                            </div>
                        </div>
                        <div class="pcd__header-badges">
                            <span v-if="dirtyBadge" class="pcd__badge">{{ dirtyBadge }}</span>
                            <button type="button" class="pcd__close" @click="onClose">×</button>
                        </div>
                    </header>

                    <div class="pcd__content">
                        <aside class="pcd__nav">
                            <div class="pcd__nav-label">этапы</div>
                            <ol class="pcd__steps">
                                <li
                                    v-for="(step, idx) in steps"
                                    :key="step.id"
                                    class="pcd__step"
                                    :class="{
                                        'pcd__step--active': currentStep === step.id,
                                        'pcd__step--done': isStepDone(step.id),
                                    }"
                                >
                                    <span class="pcd__step-icon">
                                        {{ isStepDone(step.id) ? '✓' : idx + 1 }}
                                    </span>
                                    <span class="pcd__step-body">
                                        <span class="pcd__step-title">{{ step.title }}</span>
                                        <span class="pcd__step-desc">{{ step.desc }}</span>
                                    </span>
                                </li>
                            </ol>

                            <div class="pcd__nav-label">контекст</div>
                            <div class="pcd__context">
                                <div class="pcd__context-title">
                                    {{ isPhComponent ? 'Контур дозирования pH' : 'Контур дозирования EC' }}
                                    <span class="pcd__context-meta">
                                        {{ contextDone }} / {{ contextTotal }}
                                    </span>
                                </div>
                                <div class="pcd__context-pills">
                                    <span
                                        v-for="p in contextPills"
                                        :key="p.component"
                                        class="pcd__pill"
                                        :class="{
                                            'pcd__pill--done': p.done,
                                            'pcd__pill--current': p.component === form.component,
                                        }"
                                    >
                                        <span class="pcd__pill-dot" />
                                        {{ p.label }}<span v-if="p.component === form.component"> · текущий</span>
                                    </span>
                                </div>
                            </div>
                        </aside>

                        <section class="pcd__main">
                            <!-- STEP 1: SELECT -->
                            <div v-if="currentStep === 'select'" class="pcd__step-panel">
                                <div class="pcd__panel-header">
                                    <div>
                                        <div class="pcd__panel-num">1.</div>
                                        <div class="pcd__panel-title">Выбор насоса</div>
                                        <div class="pcd__panel-desc">
                                            Компонент, канал и длительность тестового запуска.
                                        </div>
                                    </div>
                                </div>

                                <div class="pcd__grid">
                                    <label class="pcd__field">
                                        <span>Компонент</span>
                                        <select v-model="form.component" class="pcd__input">
                                            <option
                                                v-for="opt in componentOptions"
                                                :key="opt.value"
                                                :value="opt.value"
                                            >
                                                {{ opt.label }}
                                            </option>
                                        </select>
                                    </label>
                                    <label class="pcd__field">
                                        <span>Канал насоса</span>
                                        <select v-model.number="form.node_channel_id" class="pcd__input">
                                            <option :value="null" disabled>Выберите канал…</option>
                                            <option
                                                v-for="ch in pumpChannels"
                                                :key="ch.id"
                                                :value="ch.id"
                                            >
                                                {{ ch.label }}
                                            </option>
                                        </select>
                                    </label>
                                    <label class="pcd__field">
                                        <span>Длительность (сек)</span>
                                        <input
                                            v-model.number="form.duration_sec"
                                            type="number"
                                            min="1"
                                            max="60"
                                            class="pcd__input"
                                        />
                                    </label>
                                </div>

                                <div class="pcd__panel-footer">
                                    <button type="button" class="pcd__btn pcd__btn--ghost" @click="onClose">
                                        Отмена
                                    </button>
                                    <button
                                        type="button"
                                        class="pcd__btn pcd__btn--primary"
                                        :disabled="!canRun"
                                        @click="goToRun"
                                    >
                                        Далее →
                                    </button>
                                </div>
                            </div>

                            <!-- STEP 2: RUN + MEASURE -->
                            <div v-if="currentStep === 'measure'" class="pcd__step-panel">
                                <div class="pcd__panel-header">
                                    <div>
                                        <div class="pcd__panel-num">2.</div>
                                        <div class="pcd__panel-title">Запуск и замер</div>
                                    </div>
                                    <div v-if="runToken" class="pcd__panel-badge">
                                        токен запуска {{ runToken.slice(0, 8) }}
                                    </div>
                                </div>

                                <div class="pcd__run-block">
                                    <div class="pcd__run-head">Тестовый запуск</div>
                                    <div class="pcd__run-actions">
                                        <button
                                            type="button"
                                            class="pcd__btn pcd__btn--primary"
                                            :disabled="loadingRun"
                                            @click="runCalibration"
                                        >
                                            {{ loadingRun ? '▶ Запуск…' : '▶ Запустить калибровку' }}
                                        </button>
                                        <span v-if="runRecentAgo" class="pcd__run-ago">
                                            завершён {{ runRecentAgo }} назад
                                        </span>
                                    </div>
                                    <div class="pcd__run-params">
                                        {{ form.duration_sec }} сек · {{ form.component.toUpperCase() }} · ch{{ form.node_channel_id }}
                                    </div>
                                </div>

                                <div class="pcd__measure-block">
                                    <div class="pcd__measure-head">
                                        <span>Результат замера</span>
                                        <span v-if="!form.actual_ml" class="pcd__measure-hint">
                                            фактический объём обязателен
                                        </span>
                                    </div>
                                    <div class="pcd__grid pcd__grid--compact">
                                        <label class="pcd__field">
                                            <span>Фактический объём *</span>
                                            <div class="pcd__input-with-suffix">
                                                <input
                                                    v-model.number="form.actual_ml"
                                                    type="number"
                                                    step="0.1"
                                                    min="0"
                                                    class="pcd__input"
                                                />
                                                <span class="pcd__input-suffix">мл</span>
                                            </div>
                                        </label>
                                        <label class="pcd__field">
                                            <span>Температура (опц.)</span>
                                            <div class="pcd__input-with-suffix">
                                                <input
                                                    v-model.number="form.temperature_c"
                                                    type="number"
                                                    step="0.1"
                                                    class="pcd__input"
                                                />
                                                <span class="pcd__input-suffix">°C</span>
                                            </div>
                                        </label>
                                        <label class="pcd__field">
                                            <span>Объём теста (для k)</span>
                                            <div class="pcd__input-with-suffix">
                                                <input
                                                    v-model.number="form.test_volume_l"
                                                    type="number"
                                                    step="0.1"
                                                    min="0"
                                                    class="pcd__input"
                                                />
                                                <span class="pcd__input-suffix">л</span>
                                            </div>
                                        </label>
                                        <label class="pcd__field">
                                            <span>EC до дозы</span>
                                            <div class="pcd__input-with-suffix">
                                                <input
                                                    v-model.number="form.ec_before_ms"
                                                    type="number"
                                                    step="0.01"
                                                    min="0"
                                                    class="pcd__input"
                                                />
                                                <span class="pcd__input-suffix">mS/cm</span>
                                            </div>
                                        </label>
                                        <label class="pcd__field">
                                            <span>EC после дозы</span>
                                            <div class="pcd__input-with-suffix">
                                                <input
                                                    v-model.number="form.ec_after_ms"
                                                    type="number"
                                                    step="0.01"
                                                    min="0"
                                                    class="pcd__input"
                                                />
                                                <span class="pcd__input-suffix">mS/cm</span>
                                            </div>
                                        </label>
                                    </div>

                                    <div v-if="previewVisible" class="pcd__preview">
                                        <div>
                                            <span>мл/сек</span>
                                            <strong>{{ formatFloat(previewMlPerSec, 3) }}</strong>
                                        </div>
                                        <div v-if="previewDeltaEc !== null">
                                            <span>ΔEC</span>
                                            <strong>{{ (previewDeltaEc >= 0 ? '+' : '') + formatFloat(previewDeltaEc, 3) }}</strong>
                                        </div>
                                        <div v-if="previewK !== null">
                                            <span>оценка K</span>
                                            <strong>{{ formatFloat(previewK, 6) }}</strong>
                                        </div>
                                    </div>
                                </div>

                                <!-- Индикатор режима сохранения (до save) -->
                                <div
                                    v-if="canSave && !savedForCurrent"
                                    class="pcd__save-mode"
                                    :class="{ 'pcd__save-mode--manual': !runToken }"
                                >
                                    <span v-if="runToken">
                                        ✓ Готов к сохранению · токен запуска {{ runToken.slice(0, 8) }}
                                    </span>
                                    <span v-else>
                                        ⚠ Запуск не выполнен — калибровка сохранится в режиме <strong>ручного переопределения</strong>.
                                    </span>
                                </div>

                                <!-- После сохранения: карточка «следующий» -->
                                <div
                                    v-if="savedForCurrent && nextUncalibrated"
                                    class="pcd__next-card"
                                >
                                    <div class="pcd__next-card__label">
                                        ✓ {{ form.component.toUpperCase() }} сохранён · следующий некалиброванный
                                    </div>
                                    <div class="pcd__next-card__body">
                                        <div>
                                            <div class="pcd__next-card__title">{{ nextUncalibrated.label }}</div>
                                            <div class="pcd__next-card__sub">
                                                {{ nextUncalibrated.required ? 'обязательный' : 'опциональный' }}
                                                · {{ nextUncalibrated.doneInPath }}/{{ nextUncalibrated.pathTotal }} в контуре {{ nextUncalibrated.group === 'ec' ? 'EC' : 'pH' }}
                                            </div>
                                        </div>
                                        <button
                                            type="button"
                                            class="pcd__btn pcd__btn--primary"
                                            @click="goToNext"
                                        >
                                            Продолжить с {{ nextUncalibrated.label }} →
                                        </button>
                                    </div>
                                </div>
                                <div
                                    v-else-if="savedForCurrent && !nextUncalibrated"
                                    class="pcd__next-card pcd__next-card--done"
                                >
                                    <div class="pcd__next-card__label">✓ готово</div>
                                    <div class="pcd__next-card__body">
                                        <div>
                                            <div class="pcd__next-card__title">Все доступные насосы откалиброваны</div>
                                            <div class="pcd__next-card__sub">
                                                Остались только узлы без привязанного канала или опциональные.
                                            </div>
                                        </div>
                                        <button
                                            type="button"
                                            class="pcd__btn pcd__btn--ghost"
                                            @click="onClose"
                                        >
                                            Закрыть
                                        </button>
                                    </div>
                                </div>
                            </div>

                            <!-- Footer (common for measure step) -->
                            <div v-if="currentStep === 'measure'" class="pcd__panel-footer">
                                <button type="button" class="pcd__btn pcd__btn--ghost" @click="currentStep = 'select'">
                                    ← к выбору
                                </button>
                                <div class="pcd__panel-footer-right">
                                    <button
                                        type="button"
                                        class="pcd__btn pcd__btn--ghost"
                                        :disabled="loadingRun"
                                        @click="runCalibration"
                                    >
                                        {{ runToken ? 'повторить запуск' : '▶ запустить' }}
                                    </button>
                                    <button
                                        v-if="!savedForCurrent"
                                        type="button"
                                        class="pcd__btn pcd__btn--primary"
                                        :disabled="loadingSave || !canSave"
                                        @click="saveCalibration"
                                    >
                                        {{ loadingSave ? 'Сохранение…' : 'Сохранить' }}
                                    </button>
                                    <button
                                        v-else-if="nextUncalibrated"
                                        type="button"
                                        class="pcd__btn pcd__btn--primary"
                                        @click="goToNext"
                                    >
                                        К {{ nextUncalibrated.label }} →
                                    </button>
                                    <button
                                        v-else
                                        type="button"
                                        class="pcd__btn pcd__btn--primary"
                                        @click="onClose"
                                    >
                                        Закрыть
                                    </button>
                                </div>
                            </div>
                        </section>
                    </div>
                </aside>
            </div>
        </transition>
    </Teleport>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import type { Device } from '@/types';
import type {
    PumpCalibrationComponent,
    PumpCalibrationRunPayload,
    PumpCalibrationSavePayload,
} from '@/types/Calibration';
import type { PumpCalibration } from '@/types/PidConfig';

export type PumpCalibrationStep = 'select' | 'measure';

interface Props {
    show: boolean;
    zoneId: number;
    devices: Device[];
    pumps: PumpCalibration[];
    loadingRun?: boolean;
    loadingSave?: boolean;
    runSuccessSeq?: number;
    saveSuccessSeq?: number;
    lastRunToken?: string | null;
    initialComponent?: PumpCalibrationComponent | null;
    initialNodeChannelId?: number | null;
}

const props = withDefaults(defineProps<Props>(), {
    loadingRun: false,
    loadingSave: false,
    runSuccessSeq: 0,
    saveSuccessSeq: 0,
    lastRunToken: null,
    initialComponent: null,
    initialNodeChannelId: null,
});

const emit = defineEmits<{
    (e: 'close'): void;
    (e: 'start', payload: PumpCalibrationRunPayload): void;
    (e: 'save', payload: PumpCalibrationSavePayload): void;
}>();

const componentOptions: Array<{ value: PumpCalibrationComponent; label: string }> = [
    { value: 'npk', label: 'NPK' },
    { value: 'calcium', label: 'Calcium' },
    { value: 'magnesium', label: 'Magnesium' },
    { value: 'micro', label: 'Micro' },
    { value: 'ph_up', label: 'pH Up' },
    { value: 'ph_down', label: 'pH Down' },
];

const steps = [
    { id: 'select' as const, title: 'Выбор насоса', desc: 'компонент · канал · длительность' },
    { id: 'measure' as const, title: 'Запуск, замер, сохранение', desc: 'объём · мл/сек · сохранить' },
];

const currentStep = ref<PumpCalibrationStep>('select');
const runToken = ref<string | null>(null);
const runFinishedAt = ref<number | null>(null);

const form = reactive<{
    component: PumpCalibrationComponent;
    node_channel_id: number | null;
    duration_sec: number;
    actual_ml: number | null;
    test_volume_l: number | null;
    ec_before_ms: number | null;
    ec_after_ms: number | null;
    temperature_c: number | null;
}>({
    component: 'npk',
    node_channel_id: null,
    duration_sec: 20,
    actual_ml: null,
    test_volume_l: null,
    ec_before_ms: null,
    ec_after_ms: null,
    temperature_c: null,
});

watch(
    () => props.show,
    (open) => {
        if (open) {
            if (props.initialComponent) form.component = props.initialComponent;
            if (props.initialNodeChannelId) form.node_channel_id = props.initialNodeChannelId;
            currentStep.value = 'select';
            runToken.value = null;
            runFinishedAt.value = null;
            form.actual_ml = null;
            form.test_volume_l = null;
            form.ec_before_ms = null;
            form.ec_after_ms = null;
            form.temperature_c = null;
        }
    },
    { immediate: true },
);

watch(
    () => props.runSuccessSeq,
    (seq, prev) => {
        if (seq !== prev) {
            runToken.value = props.lastRunToken ?? null;
            runFinishedAt.value = Date.now();
        }
    },
);

const lastSavedAt = ref<number | null>(null);
const lastSavedComponent = ref<PumpCalibrationComponent | null>(null);

watch(
    () => props.saveSuccessSeq,
    (seq, prev) => {
        if (seq !== prev && seq > 0) {
            lastSavedAt.value = Date.now();
            lastSavedComponent.value = form.component;
        }
    },
);

// «Текущий компонент сохранён» — остаётся true пока пользователь не сменил компонент / не закрыл drawer
const savedForCurrent = computed(
    () => lastSavedComponent.value !== null && lastSavedComponent.value === form.component,
);

// Pump channels from devices
interface PumpChannelOption {
    id: number;
    label: string;
}

const pumpChannels = computed<PumpChannelOption[]>(() => {
    const out: PumpChannelOption[] = [];
    for (const d of props.devices) {
        const deviceLabel = d.uid ?? d.name ?? `Узел ${d.id}`;
        const channels = (d as { channels?: Array<{ id: number; channel: string; type?: string }> }).channels ?? [];
        for (const ch of channels) {
            const type = String(ch.type ?? '').toLowerCase();
            if (!type.includes('actuator')) continue;
            const name = String(ch.channel ?? '');
            const lower = name.toLowerCase();
            if (lower.startsWith('valve_') || lower === 'drain_pump') continue;
            out.push({ id: ch.id, label: `${deviceLabel} · ${name}` });
        }
    }
    return out;
});

const currentComponent = computed(() => form.component);
const isPhComponent = computed(() => form.component === 'ph_up' || form.component === 'ph_down');

interface ContextPill {
    component: PumpCalibrationComponent;
    label: string;
    done: boolean;
}

const componentToRole: Record<PumpCalibrationComponent, string> = {
    npk: 'pump_a',
    calcium: 'pump_b',
    magnesium: 'pump_c',
    micro: 'pump_d',
    ph_up: 'pump_base',
    ph_down: 'pump_acid',
};

function pumpDoneFor(component: PumpCalibrationComponent): boolean {
    const role = componentToRole[component];
    const pump = props.pumps.find((p) => p.role === role);
    return !!pump?.ml_per_sec && pump.ml_per_sec > 0;
}

const contextPills = computed<ContextPill[]>(() => {
    const comps: PumpCalibrationComponent[] = isPhComponent.value
        ? ['ph_up', 'ph_down']
        : ['npk', 'calcium', 'magnesium', 'micro'];
    return comps.map((c) => {
        const opt = componentOptions.find((o) => o.value === c);
        return {
            component: c,
            label: opt?.label ?? c,
            done: pumpDoneFor(c),
        };
    });
});

const contextDone = computed(() => contextPills.value.filter((p) => p.done).length);
const contextTotal = computed(() => contextPills.value.length);

const canRun = computed(
    () =>
        form.component != null &&
        form.node_channel_id != null &&
        form.duration_sec > 0,
);

const canSave = computed(
    () => canRun.value && typeof form.actual_ml === 'number' && form.actual_ml > 0,
);

const previewMlPerSec = computed(() => {
    if (!form.actual_ml || form.duration_sec <= 0) return null;
    return form.actual_ml / form.duration_sec;
});

const previewDeltaEc = computed(() => {
    if (typeof form.ec_before_ms !== 'number' || typeof form.ec_after_ms !== 'number') return null;
    return form.ec_after_ms - form.ec_before_ms;
});

const previewK = computed(() => {
    const delta = previewDeltaEc.value;
    const ml = form.actual_ml;
    const vol = form.test_volume_l;
    if (!delta || !ml || !vol || vol <= 0 || ml <= 0) return null;
    return (delta * vol) / ml;
});

const previewVisible = computed(
    () => previewMlPerSec.value !== null || previewDeltaEc.value !== null,
);

const dirtyBadge = computed(() => {
    if (currentStep.value === 'measure' && !form.actual_ml) {
        return 'не сохранено · объём не указан';
    }
    return '';
});

const runRecentAgo = computed(() => {
    if (!runFinishedAt.value) return '';
    const diff = Math.floor((Date.now() - runFinishedAt.value) / 1000);
    if (diff < 60) return `${diff} сек`;
    return `${Math.floor(diff / 60)} мин`;
});

function isStepDone(id: PumpCalibrationStep): boolean {
    if (id === 'select') return currentStep.value !== 'select' && canRun.value;
    if (id === 'measure') return savedForCurrent.value;
    return false;
}

function formatFloat(v: number | null, digits: number): string {
    if (v === null || !Number.isFinite(v)) return '—';
    return v.toFixed(digits);
}

function runCalibration() {
    if (!canRun.value) return;
    emit('start', {
        component: form.component,
        node_channel_id: form.node_channel_id!,
        duration_sec: form.duration_sec,
    });
}

function goToRun() {
    if (!canRun.value) return;
    currentStep.value = 'measure';
}

interface NextCandidate {
    component: PumpCalibrationComponent;
    label: string;
    role: string;
    nodeChannelId: number;
    group: 'ec' | 'ph';
    required: boolean;
    doneInPath: number;
    pathTotal: number;
}

const NEXT_ORDER: Array<{
    component: PumpCalibrationComponent;
    label: string;
    role: string;
    group: 'ec' | 'ph';
    required: boolean;
}> = [
    // Сначала EC chain, затем pH
    { component: 'npk', label: 'NPK', role: 'pump_a', group: 'ec', required: true },
    { component: 'calcium', label: 'Calcium', role: 'pump_b', group: 'ec', required: false },
    { component: 'magnesium', label: 'Magnesium', role: 'pump_c', group: 'ec', required: false },
    { component: 'micro', label: 'Micro', role: 'pump_d', group: 'ec', required: false },
    { component: 'ph_down', label: 'pH Down', role: 'pump_acid', group: 'ph', required: true },
    { component: 'ph_up', label: 'pH Up', role: 'pump_base', group: 'ph', required: true },
];

const nextUncalibrated = computed<NextCandidate | null>(() => {
    const pumpByRole = (role: string) => props.pumps.find((p) => p.role === role);

    // Приоритет 1: тот же dosing path, обязательные
    // Приоритет 2: тот же dosing path, любые
    // Приоритет 3: другой dosing path, обязательные
    // Приоритет 4: другой dosing path, любые
    const currentGroup: 'ec' | 'ph' = isPhComponent.value ? 'ph' : 'ec';

    const buckets: Array<NextCandidate[]> = [[], [], [], []];
    for (const desc of NEXT_ORDER) {
        if (desc.component === form.component) continue;
        const pump = pumpByRole(desc.role);
        const calibrated = !!pump?.ml_per_sec && pump.ml_per_sec > 0;
        const hasChannel = pump && pump.node_channel_id > 0;
        if (calibrated || !hasChannel) continue;

        const sameGroup = desc.group === currentGroup;
        const bucketIdx = sameGroup
            ? desc.required
                ? 0
                : 1
            : desc.required
              ? 2
              : 3;

        const pathRoles = NEXT_ORDER.filter((d) => d.group === desc.group);
        const doneInPath = pathRoles.filter((d) => {
            const p = pumpByRole(d.role);
            return !!p?.ml_per_sec && p.ml_per_sec > 0;
        }).length;

        buckets[bucketIdx].push({
            component: desc.component,
            label: desc.label,
            role: desc.role,
            nodeChannelId: pump!.node_channel_id,
            group: desc.group,
            required: desc.required,
            doneInPath,
            pathTotal: pathRoles.length,
        });
    }

    for (const bucket of buckets) {
        if (bucket.length > 0) return bucket[0];
    }
    return null;
});

function goToNext() {
    const next = nextUncalibrated.value;
    if (!next) return;
    form.component = next.component;
    form.node_channel_id = next.nodeChannelId;
    form.actual_ml = null;
    form.test_volume_l = null;
    form.ec_before_ms = null;
    form.ec_after_ms = null;
    form.temperature_c = null;
    runToken.value = null;
    runFinishedAt.value = null;
    lastSavedComponent.value = null;
    currentStep.value = 'measure';
}

function saveCalibration() {
    if (!canSave.value) return;
    const hasRunToken = runToken.value !== null && runToken.value !== '';
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
    };
    emit('save', payload);
}

function onClose() {
    emit('close');
}
</script>

<style scoped>
.pcd-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.45);
    z-index: 50;
    display: flex;
    justify-content: flex-end;
}

.pcd {
    width: min(880px, 100vw);
    height: 100vh;
    background: var(--bg-surface, #1e293b);
    border-left: 1px solid rgba(148, 163, 184, 0.25);
    box-shadow: -8px 0 24px rgba(0, 0, 0, 0.35);
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.pcd__header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.85rem 1.1rem;
    border-bottom: 1px solid rgba(148, 163, 184, 0.2);
}

.pcd__title {
    font-size: 1rem;
    font-weight: 700;
}

.pcd__breadcrumb {
    font-family: ui-monospace, monospace;
    font-size: 0.7rem;
    opacity: 0.6;
    margin-top: 0.15rem;
}

.pcd__header-badges {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.pcd__badge {
    padding: 0.2rem 0.55rem;
    border-radius: 9999px;
    background: rgba(251, 191, 36, 0.15);
    color: rgb(250, 204, 21);
    font-size: 0.72rem;
    font-weight: 500;
}

.pcd__close {
    background: transparent;
    border: none;
    color: inherit;
    font-size: 1.5rem;
    cursor: pointer;
    line-height: 1;
    padding: 0 0.25rem;
}

.pcd__content {
    flex: 1 1 auto;
    display: grid;
    grid-template-columns: minmax(220px, 260px) 1fr;
    overflow: hidden;
}

.pcd__nav {
    padding: 0.85rem 0.85rem 1rem;
    border-right: 1px solid rgba(148, 163, 184, 0.15);
    overflow-y: auto;
}

.pcd__nav-label {
    font-size: 0.62rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    font-weight: 700;
    opacity: 0.55;
    margin: 0.3rem 0 0.4rem;
}

.pcd__nav-label:first-child {
    margin-top: 0;
}

.pcd__steps {
    list-style: none;
    padding: 0;
    margin: 0 0 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
}

.pcd__step {
    display: flex;
    gap: 0.55rem;
    padding: 0.5rem 0.6rem;
    border-radius: 0.4rem;
    border: 1px solid transparent;
    align-items: flex-start;
    cursor: default;
    font-size: 0.8rem;
}

.pcd__step--active {
    border-color: rgba(56, 189, 248, 0.55);
    background: rgba(56, 189, 248, 0.08);
}

.pcd__step-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    border-radius: 0.35rem;
    background: rgba(148, 163, 184, 0.15);
    font-size: 0.72rem;
    font-weight: 700;
    flex-shrink: 0;
}

.pcd__step--active .pcd__step-icon {
    background: rgb(56, 189, 248);
    color: #0f172a;
}

.pcd__step--done .pcd__step-icon {
    background: rgba(34, 197, 94, 0.2);
    color: rgb(134, 239, 172);
}

.pcd__step-body {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    min-width: 0;
}

.pcd__step-title {
    font-weight: 600;
    line-height: 1.15;
}

.pcd__step-desc {
    font-size: 0.68rem;
    opacity: 0.6;
    font-family: ui-monospace, monospace;
}

.pcd__context {
    padding: 0.55rem 0.65rem;
    border: 1px solid rgba(148, 163, 184, 0.18);
    border-radius: 0.4rem;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
}

.pcd__context-title {
    display: flex;
    justify-content: space-between;
    font-size: 0.78rem;
    font-weight: 600;
}

.pcd__context-meta {
    font-weight: 500;
    opacity: 0.65;
    font-size: 0.7rem;
}

.pcd__context-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
}

.pcd__pill {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.18rem 0.5rem;
    border-radius: 9999px;
    background: rgba(148, 163, 184, 0.08);
    border: 1px solid transparent;
    font-size: 0.7rem;
}

.pcd__pill-dot {
    width: 5px;
    height: 5px;
    border-radius: 9999px;
    background: rgba(148, 163, 184, 0.5);
}

.pcd__pill--done {
    background: rgba(34, 197, 94, 0.1);
    border-color: rgba(34, 197, 94, 0.3);
    color: rgb(134, 239, 172);
}
.pcd__pill--done .pcd__pill-dot {
    background: rgb(34, 197, 94);
}

.pcd__pill--current {
    background: rgba(56, 189, 248, 0.12);
    border-color: rgba(56, 189, 248, 0.4);
    color: rgb(125, 211, 252);
}
.pcd__pill--current .pcd__pill-dot {
    background: rgb(56, 189, 248);
}

.pcd__main {
    padding: 1rem 1.2rem;
    overflow-y: auto;
}

.pcd__step-panel {
    display: flex;
    flex-direction: column;
    gap: 0.9rem;
}

.pcd__panel-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 0.5rem;
}

.pcd__panel-num {
    font-size: 0.72rem;
    opacity: 0.55;
    font-weight: 700;
}

.pcd__panel-title {
    font-size: 1rem;
    font-weight: 700;
    margin-top: 0.1rem;
}

.pcd__panel-desc {
    font-size: 0.78rem;
    opacity: 0.7;
    margin-top: 0.2rem;
}

.pcd__panel-badge {
    padding: 0.2rem 0.55rem;
    border-radius: 9999px;
    background: rgba(148, 163, 184, 0.1);
    font-family: ui-monospace, monospace;
    font-size: 0.7rem;
}

.pcd__grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 0.6rem;
}

.pcd__grid--compact {
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
}

.pcd__field {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-size: 0.78rem;
}

.pcd__field > span {
    font-size: 0.65rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    opacity: 0.65;
    font-weight: 600;
}

.pcd__input {
    padding: 0.42rem 0.55rem;
    border-radius: 0.35rem;
    border: 1px solid rgba(148, 163, 184, 0.3);
    background: transparent;
    color: inherit;
    font-size: 0.85rem;
    min-width: 0;
}

.pcd__input:focus-visible {
    outline: none;
    border-color: rgba(56, 189, 248, 0.7);
    box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.18);
}

.pcd__input-with-suffix {
    position: relative;
    display: flex;
    align-items: center;
}

.pcd__input-with-suffix .pcd__input {
    flex: 1 1 auto;
    padding-right: 3rem;
}

.pcd__input-suffix {
    position: absolute;
    right: 0.55rem;
    font-size: 0.7rem;
    opacity: 0.55;
    pointer-events: none;
}

.pcd__run-block {
    padding: 0.75rem 0.85rem;
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 0.45rem;
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
}

.pcd__run-head {
    font-weight: 600;
    font-size: 0.85rem;
}

.pcd__run-actions {
    display: flex;
    gap: 0.5rem;
    align-items: center;
}

.pcd__run-ago {
    padding: 0.2rem 0.5rem;
    border-radius: 9999px;
    background: rgba(34, 197, 94, 0.12);
    color: rgb(134, 239, 172);
    font-size: 0.72rem;
}

.pcd__run-params {
    font-size: 0.72rem;
    opacity: 0.6;
    font-family: ui-monospace, monospace;
}

.pcd__measure-block {
    padding: 0.75rem 0.85rem;
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 0.45rem;
    display: flex;
    flex-direction: column;
    gap: 0.65rem;
}

.pcd__measure-head {
    display: flex;
    justify-content: space-between;
    font-weight: 600;
    font-size: 0.85rem;
}

.pcd__measure-hint {
    font-size: 0.7rem;
    opacity: 0.6;
    font-weight: 400;
}

.pcd__preview {
    display: flex;
    gap: 1.4rem;
    flex-wrap: wrap;
    padding: 0.65rem 0.85rem;
    border: 1px dashed rgba(56, 189, 248, 0.35);
    background: rgba(56, 189, 248, 0.04);
    border-radius: 0.4rem;
}

.pcd__preview--large {
    padding: 0.85rem 1.2rem;
    gap: 2rem;
}

.pcd__preview > div {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
}

.pcd__preview span {
    font-size: 0.6rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    opacity: 0.6;
    font-weight: 600;
}

.pcd__preview strong {
    font-size: 1rem;
    font-weight: 700;
    color: rgb(56, 189, 248);
    font-family: ui-monospace, monospace;
}

.pcd__panel-footer {
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
    padding-top: 0.5rem;
    border-top: 1px solid rgba(148, 163, 184, 0.12);
}

.pcd__panel-footer-right {
    display: flex;
    gap: 0.4rem;
}

.pcd__btn {
    padding: 0.45rem 0.85rem;
    border-radius: 0.35rem;
    border: 1px solid transparent;
    cursor: pointer;
    font-size: 0.8rem;
    font-weight: 500;
}

.pcd__btn:disabled {
    cursor: not-allowed;
    opacity: 0.5;
}

.pcd__btn--primary {
    background: rgb(56, 189, 248);
    color: #0f172a;
}

.pcd__btn--primary:hover:not(:disabled) {
    background: rgb(14, 165, 233);
}

.pcd__btn--ghost {
    background: transparent;
    border-color: rgba(148, 163, 184, 0.3);
    color: inherit;
}

.pcd__btn--ghost:hover:not(:disabled) {
    background: rgba(148, 163, 184, 0.08);
}

.pcd__save-mode {
    padding: 0.55rem 0.8rem;
    border-radius: 0.4rem;
    font-size: 0.78rem;
    background: rgba(34, 197, 94, 0.08);
    border: 1px solid rgba(34, 197, 94, 0.3);
    color: rgb(134, 239, 172);
}

.pcd__next-card {
    padding: 0.7rem 0.85rem;
    border-radius: 0.45rem;
    border: 1px solid rgba(56, 189, 248, 0.35);
    background: rgba(56, 189, 248, 0.06);
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
}

.pcd__next-card--done {
    border-color: rgba(34, 197, 94, 0.3);
    background: rgba(34, 197, 94, 0.06);
}

.pcd__next-card__label {
    font-size: 0.62rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-weight: 700;
    opacity: 0.65;
}

.pcd__next-card__body {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
}

.pcd__next-card__title {
    font-weight: 700;
    font-size: 0.95rem;
}

.pcd__next-card__sub {
    font-size: 0.72rem;
    opacity: 0.7;
    margin-top: 0.1rem;
}

.pcd__save-mode--manual {
    background: rgba(251, 191, 36, 0.08);
    border-color: rgba(251, 191, 36, 0.3);
    color: rgb(250, 204, 21);
}

.pcd__save-mode strong {
    font-family: ui-monospace, monospace;
}

.cal-drawer-enter-from,
.cal-drawer-leave-to {
    opacity: 0;
}
.cal-drawer-enter-active,
.cal-drawer-leave-active {
    transition: opacity 200ms ease;
}
.cal-drawer-enter-active .pcd,
.cal-drawer-leave-active .pcd {
    transition: transform 230ms ease;
}
.cal-drawer-enter-from .pcd,
.cal-drawer-leave-to .pcd {
    transform: translateX(100%);
}
</style>
