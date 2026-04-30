<template>
  <section class="flex flex-col gap-3">
    <div
      v-if="!zoneId"
      class="px-3 py-2.5 rounded-md border border-warn-soft bg-warn-soft text-warn text-sm"
    >
      Автоматика становится доступна после выбора зоны.
    </div>

    <template v-else>
      <div
        v-if="loading"
        class="px-3 py-2.5 rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)] text-[var(--text-muted)] text-sm"
      >
        Загрузка конфигурации зоны…
      </div>

      <AutomationHub
        v-else
        :zone-id="zoneId"
        :profile="state"
        :current-recipe-phase="currentRecipePhase"
        :system-type-locked="isSystemTypeLocked"
        :available-nodes="availableNodes"
        :refreshing-nodes="refreshingNodes"
        :binding-in-progress="bindingInProgress"
        :binding-node-ids="bindingNodeIds"
        :binding-failed-node-ids="bindingFailedNodeIds"
        :recipe-summary="recipeSummary"
        :workflow-phase="zoneWorkflowPhase"
        @update:water-form="(v) => (state.waterForm = v)"
        @update:lighting-form="(v) => (state.lightingForm = v)"
        @update:zone-climate-form="(v) => (state.zoneClimateForm = v)"
        @update:assignments="(v) => (state.assignments = v)"
        @bind-devices="onBindDevices"
        @bind-node="onBindNode"
        @refresh-nodes="onRefreshNodes"
        @refresh="reloadAll"
        @preset-applied="onPresetApplied"
        @preset-cleared="onPresetCleared"
      />
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import AutomationHub from '@/Components/Launch/Automation/AutomationHub.vue';
import { api } from '@/services/api';
import { useToast } from '@/composables/useToast';
import {
    automationProfileDefaults,
    type AutomationProfile,
} from '@/schemas/automationProfile';
import {
    bindingsResponseToAssignments,
    zoneLogicProfileToProfile,
} from '@/composables/automationProfileConverters';
import type { ZoneAutomationBindRole } from '@/composables/zoneAutomationTypes';
import type { AutomationNode as SetupWizardNode } from '@/types/AutomationNode';
import type { ZoneAutomationPreset } from '@/types/ZoneAutomationPreset';
import type { IrrigationSystem } from '@/composables/zoneAutomationTypes';
import { resolveRecipePhaseSystemType } from '@/composables/recipeSystemType';
import { autoSelectAssignmentsByNodeType } from '@/composables/zoneAutomationAssignmentAutoSelect';

interface RecipeSummary {
    name?: string | null;
    revisionLabel?: string | null;
    systemType?: string | null;
    targetPh?: number | null;
    targetEc?: number | null;
}

interface Props {
    zoneId?: number;
    currentRecipePhase?: unknown;
    recipeSummary?: RecipeSummary | null;
    /**
     * Если true — не эмитим `update:profile` до завершения первого `reloadAll()`
     * (нужно для модалки редактирования зоны, чтобы не затирать черновик дефолтами).
     * В мастере запуска оставляем false.
     */
    emitProfileAfterHydrate?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
    zoneId: undefined,
    currentRecipePhase: null,
    recipeSummary: null,
    emitProfileAfterHydrate: false,
});

const emit = defineEmits<{
    (event: 'update:profile', next: AutomationProfile): void;
}>();

const { showToast } = useToast();

const state = reactive<AutomationProfile>(structuredClone(automationProfileDefaults));

const profileEmitAllowed = ref(!props.emitProfileAfterHydrate);

function emitProfileFromState(): void {
    emit('update:profile', {
        waterForm: { ...state.waterForm },
        lightingForm: { ...state.lightingForm },
        zoneClimateForm: { ...state.zoneClimateForm },
        assignments: { ...state.assignments },
    });
}
const availableNodes: SetupWizardNode[] = reactive([]);

const loading = ref(false);
const refreshingNodes = ref(false);
const bindingInProgress = ref(false);
const bindingNodeIds = ref<Set<number>>(new Set());
const bindingFailedNodeIds = ref<Set<number>>(new Set());
let pendingPollHandle: ReturnType<typeof setInterval> | null = null;
let pendingPollDeadline = 0;
const PENDING_POLL_INTERVAL_MS = 2500;
/** Опрос pending + снятие лоадеров при зависании (согласовано с UI-таймаутом привязки). */
const PENDING_POLL_TIMEOUT_MS = 30_000;
/** Максимум показа лоадера «Привязать» для одной ноды до принудительного сброса. */
const BINDING_NODE_UI_TIMEOUT_MS = 30_000;

const bindingNodeUiTimeoutHandles = new Map<number, ReturnType<typeof setTimeout>>();
const zoneWorkflowPhase = ref<string | null>(null);

function clearBindingUiTimeout(nodeId: number): void {
    const t = bindingNodeUiTimeoutHandles.get(nodeId);
    if (t != null) {
        clearTimeout(t);
        bindingNodeUiTimeoutHandles.delete(nodeId);
    }
}

function clearAllBindingUiTimeouts(): void {
    for (const t of bindingNodeUiTimeoutHandles.values()) {
        clearTimeout(t);
    }
    bindingNodeUiTimeoutHandles.clear();
}

function syncBindingUiTimeouts(): void {
    for (const id of [...bindingNodeUiTimeoutHandles.keys()]) {
        if (!bindingNodeIds.value.has(id)) {
            clearBindingUiTimeout(id);
        }
    }
}

function scheduleBindingUiTimeout(nodeId: number, zoneId: number): void {
    clearBindingUiTimeout(nodeId);
    const t = setTimeout(() => {
        bindingNodeUiTimeoutHandles.delete(nodeId);
        if (!bindingNodeIds.value.has(nodeId)) {
            return;
        }
        const n = availableNodes.find((x) => x.id === nodeId);
        if (n && n.zone_id === zoneId) {
            reconcileBindingSpinners(zoneId);
            return;
        }
        bindingNodeIds.value = new Set([...bindingNodeIds.value].filter((id) => id !== nodeId));
        bindingFailedNodeIds.value = new Set([...bindingFailedNodeIds.value, nodeId]);
        showToast('Таймаут привязки (30 с) — проверьте узел и повторите', 'warning');
    }, BINDING_NODE_UI_TIMEOUT_MS);
    bindingNodeUiTimeoutHandles.set(nodeId, t);
}

function applyProfile(next: AutomationProfile) {
    state.waterForm = next.waterForm;
    state.lightingForm = next.lightingForm;
    state.zoneClimateForm = next.zoneClimateForm;
    state.assignments = next.assignments;
}

const recipeSystemType = computed<IrrigationSystem | null>(() => {
    if (!props.currentRecipePhase) return null;
    return resolveRecipePhaseSystemType(
        props.currentRecipePhase as Parameters<typeof resolveRecipePhaseSystemType>[0],
        'drip',
    );
});

const isSystemTypeLocked = computed<boolean>(() => recipeSystemType.value !== null);

watch(
    recipeSystemType,
    (type) => {
        if (!type) return;
        const tanksCount = type === 'drip' ? 2 : 3;
        if (
            state.waterForm.systemType !== type ||
            state.waterForm.tanksCount !== tanksCount
        ) {
            state.waterForm = { ...state.waterForm, systemType: type, tanksCount };
        }
    },
    { immediate: true },
);

watch(
    () => state.waterForm.systemType,
    (type) => {
        const expected = type === 'drip' ? 2 : 3;
        if (state.waterForm.tanksCount !== expected) {
            state.waterForm = { ...state.waterForm, tanksCount: expected };
        }
    },
);

watch(
    () => state.assignments,
    (next) => {
        const used = new Set<number>();
        for (const v of Object.values(next)) {
            if (typeof v === 'number' && v > 0) {
                used.add(v);
            }
        }
        const failed = bindingFailedNodeIds.value;
        const pruned = new Set([...failed].filter((id) => used.has(id)));
        if (pruned.size !== failed.size) {
            bindingFailedNodeIds.value = pruned;
        }
    },
    { deep: true },
);

async function loadLogicProfile(zoneId: number) {
    try {
        const doc = await api.automationConfigs.get('zone', zoneId, 'zone.logic_profile');
        const payload = (doc as { payload?: unknown })?.payload ?? {};
        const parsed = zoneLogicProfileToProfile(payload);
        applyProfile({ ...parsed, assignments: state.assignments });
    } catch {
        // если документа ещё нет — используем defaults (уже применены)
    }
}

/**
 * Подгружает channel_bindings из ZoneController::show — теперь backend
 * возвращает их вместе с node_id, что является source-of-truth для assignments.
 */
async function loadBindings(zoneId: number): Promise<void> {
    try {
        const resp = await api.zones.getById(zoneId);
        const data = resp as unknown as {
            channel_bindings?: unknown;
            workflow_phase?: unknown;
            zone_workflow_state?: { workflow_phase?: unknown } | null;
        };
        const rawWorkflowPhase =
            data.workflow_phase
            ?? data.zone_workflow_state?.workflow_phase
            ?? null;
        zoneWorkflowPhase.value = typeof rawWorkflowPhase === 'string'
            ? rawWorkflowPhase.trim().toLowerCase()
            : null;
        if (data.channel_bindings) {
            const fromApi = bindingsResponseToAssignments(data.channel_bindings);
            // Применяем поверх defaults, но не затираем уже выставленные пользователем.
            const next = { ...state.assignments };
            let changed = false;
            for (const [role, id] of Object.entries(fromApi)) {
                if (next[role as ZoneAutomationBindRole] == null && id != null) {
                    next[role as ZoneAutomationBindRole] = id;
                    changed = true;
                }
            }
            if (changed) state.assignments = next;
        }
    } catch {
        zoneWorkflowPhase.value = null;
        // keep defaults
    }
}

/**
 * Маппинг assignment_role → binding_role[] (зеркало SetupWizardController::bindingSpecs()).
 * Один assignment_role в UI может покрывать несколько binding_role на железе
 * (например, irrigation = pump_main + drain).
 */
const ROLE_BINDING_ROLES: Record<ZoneAutomationBindRole, string[]> = {
    irrigation: ['pump_main', 'drain'],
    ph_correction: ['pump_acid', 'pump_base'],
    ec_correction: ['pump_a', 'pump_b', 'pump_c', 'pump_d'],
    light: ['light_actuator'],
    soil_moisture_sensor: ['soil_moisture_sensor'],
    co2_sensor: ['co2_sensor'],
    co2_actuator: ['co2_actuator'],
    root_vent_actuator: ['root_vent_actuator'],
};

/**
 * Подтягивает assignments из реальных channel_bindings зоны.
 * Backend в NodeController отдаёт `binding_role` per channel — этого достаточно,
 * чтобы определить, какой узел уже играет роль pump_main / ph_dose / и т.д.
 */
function deriveBindingsFromNodes(zoneId: number): void {
    const next = { ...state.assignments };
    let changed = false;
    for (const role of Object.keys(ROLE_BINDING_ROLES) as ZoneAutomationBindRole[]) {
        if (next[role] != null) continue;
        const bindingRoles = ROLE_BINDING_ROLES[role];
        for (const node of availableNodes) {
            if (node.zone_id !== zoneId) continue;
            const channels = node.channels ?? [];
            const matched = channels.some(
                (ch) => typeof ch.binding_role === 'string' && bindingRoles.includes(ch.binding_role),
            );
            if (matched) {
                next[role] = node.id;
                changed = true;
                break;
            }
        }
    }
    if (changed) state.assignments = next;
}

function autoSelectAssignments(zoneId: number): void {
    const next = autoSelectAssignmentsByNodeType(
        state.assignments,
        availableNodes,
        zoneId,
    );

    const changed = JSON.stringify(next) !== JSON.stringify(state.assignments);
    if (changed) {
        state.assignments = next;
    }
}

async function loadNodes(zoneId: number) {
    try {
        const nodes = await api.nodes.list({
            zone_id: zoneId,
            include_unassigned: true,
            per_page: 100,
        });
        const list = Array.isArray(nodes)
            ? nodes
            : Array.isArray((nodes as { data?: unknown[] })?.data)
              ? ((nodes as { data: unknown[] }).data as unknown[])
              : [];
        availableNodes.splice(0, availableNodes.length, ...(list as SetupWizardNode[]));
    } catch {
        availableNodes.splice(0, availableNodes.length);
    }
}

async function reloadAll() {
    if (!props.zoneId) return;
    if (props.emitProfileAfterHydrate) {
        profileEmitAllowed.value = false;
    }
    loading.value = true;
    try {
        await Promise.all([
            loadLogicProfile(props.zoneId),
            loadBindings(props.zoneId),
            loadNodes(props.zoneId),
        ]);
        // Fallback: если в channel_bindings нет записи, но узел в зоне
        // имеет канал с подходящим binding_role — подставим его.
        deriveBindingsFromNodes(props.zoneId);
        // Автопривязка по типам/каналам: заполняем только пустые роли.
        autoSelectAssignments(props.zoneId);
    } finally {
        loading.value = false;
        if (props.emitProfileAfterHydrate) {
            profileEmitAllowed.value = true;
            emitProfileFromState();
        }
    }
}

async function onRefreshNodes() {
    if (!props.zoneId) return;
    refreshingNodes.value = true;
    try {
        await loadNodes(props.zoneId);
        deriveBindingsFromNodes(props.zoneId);
        autoSelectAssignments(props.zoneId);
        showToast('Список нод обновлён', 'success');
    } catch (error) {
        showToast((error as Error).message || 'Ошибка обновления списка нод', 'error');
    } finally {
        refreshingNodes.value = false;
    }
}

async function attachNodeToZone(nodeId: number, zoneId: number): Promise<void> {
    try {
        await api.nodes.update(nodeId, { zone_id: zoneId });
    } catch {
        // node уже привязан — игнорируем
    }
}

async function onBindDevices(roles: string[]) {
    if (!props.zoneId || bindingInProgress.value) return;

    const allAssignments: Record<string, number> = {};
    for (const [role, id] of Object.entries(state.assignments)) {
        if (typeof id === 'number' && id > 0) {
            allAssignments[role] = id;
        }
    }

    const required = ['irrigation', 'ph_correction', 'ec_correction'];
    const missing = required.filter((r) => !allAssignments[r]);
    if (missing.length > 0) {
        showToast(`Не выбраны обязательные: ${missing.join(', ')}`, 'warning');
        return;
    }

    bindingInProgress.value = true;
    try {
        // 1. Attach selected nodes to zone (если ещё не привязаны)
        const nodeIds = Array.from(new Set(Object.values(allAssignments)));
        for (const nodeId of nodeIds) {
            await attachNodeToZone(nodeId, props.zoneId);
        }

        // 2. Validate
        await api.setupWizard.validateDevices({
            zone_id: props.zoneId,
            assignments: allAssignments,
            selected_node_ids: nodeIds,
        });

        // 3. Apply bindings
        await api.setupWizard.applyDeviceBindings({
            zone_id: props.zoneId,
            assignments: allAssignments,
            selected_node_ids: nodeIds,
        });

        showToast(`Привязка выполнена (${roles.join(', ')})`, 'success');
        await loadNodes(props.zoneId);
        deriveBindingsFromNodes(props.zoneId);
        autoSelectAssignments(props.zoneId);
    } catch (error) {
        showToast((error as Error).message || 'Ошибка привязки', 'error');
    } finally {
        bindingInProgress.value = false;
    }
}

async function onBindNode(nodeId: number) {
    if (!props.zoneId || bindingNodeIds.value.has(nodeId)) return;
    const node = availableNodes.find((n) => n.id === nodeId);
    if (
        node
        && node.zone_id === props.zoneId
        && (node.pending_zone_id == null || node.pending_zone_id === props.zoneId)
    ) {
        showToast('Нода уже привязана к этой зоне', 'info');
        return;
    }
    bindingFailedNodeIds.value = new Set(
        [...bindingFailedNodeIds.value].filter((id) => id !== nodeId),
    );
    bindingNodeIds.value = new Set([...bindingNodeIds.value, nodeId]);
    scheduleBindingUiTimeout(nodeId, props.zoneId);
    try {
        await api.nodes.update(nodeId, { zone_id: props.zoneId });
        bindingFailedNodeIds.value = new Set(
            [...bindingFailedNodeIds.value].filter((id) => id !== nodeId),
        );
        showToast('Привязка отправлена — ждём config_report от ноды…', 'info');
        await loadNodes(props.zoneId);
        reconcileBindingSpinners(props.zoneId);
        startPendingPoll();
    } catch (error) {
        clearBindingUiTimeout(nodeId);
        bindingFailedNodeIds.value = new Set([...bindingFailedNodeIds.value, nodeId]);
        showToast((error as Error).message || 'Ошибка привязки ноды', 'error');
        const next = new Set(bindingNodeIds.value);
        next.delete(nodeId);
        bindingNodeIds.value = next;
    }
}

function hasPendingBindings(): boolean {
    if (!props.zoneId) return false;
    return availableNodes.some(
        (n) => n.pending_zone_id === props.zoneId && !n.zone_id,
    );
}

/**
 * Убирает node из bindingNodeIds, когда нода уже привязана к зоне (zone_id),
 * чтобы лоадер держался до config_report / промоута pending → zone.
 */
function reconcileBindingSpinners(zoneId: number): void {
    if (bindingNodeIds.value.size === 0) {
        return;
    }
    const next = new Set(bindingNodeIds.value);
    for (const nodeId of [...bindingNodeIds.value]) {
        const n = availableNodes.find((x) => x.id === nodeId);
        if (n && n.zone_id === zoneId) {
            next.delete(nodeId);
        }
    }
    if (next.size !== bindingNodeIds.value.size) {
        bindingNodeIds.value = next;
        syncBindingUiTimeouts();
    }
}

/**
 * После дедлайна опроса: снять лоадер с нод в ожидании device, пометить ошибку.
 * (Не трогаем setTimeout из sync до обновления bindingNodeIds — иначе UI-таймаут
 * отменится без срабатывания и не будет иконки ошибки.)
 */
function clearBindingSpinnersAwaitingDevice(zoneId: number): void {
    const next = new Set(bindingNodeIds.value);
    const failedIds: number[] = [];
    for (const nodeId of [...bindingNodeIds.value]) {
        const n = availableNodes.find((x) => x.id === nodeId);
        if (!n) {
            next.delete(nodeId);
            failedIds.push(nodeId);
            continue;
        }
        if (n.zone_id === zoneId) {
            next.delete(nodeId);
            continue;
        }
        if (n.pending_zone_id === zoneId && !n.zone_id) {
            next.delete(nodeId);
            failedIds.push(nodeId);
        }
    }
    if (failedIds.length > 0) {
        bindingFailedNodeIds.value = new Set([...bindingFailedNodeIds.value, ...failedIds]);
        showToast('Таймаут ожидания config_report (30 с) — проверьте узел и повторите привязку', 'warning');
    }
    bindingNodeIds.value = next;
    syncBindingUiTimeouts();
}

function stopPendingPoll() {
    if (pendingPollHandle != null) {
        clearInterval(pendingPollHandle);
        pendingPollHandle = null;
    }
    pendingPollDeadline = 0;
}

function startPendingPoll() {
    pendingPollDeadline = Date.now() + PENDING_POLL_TIMEOUT_MS;
    if (pendingPollHandle != null) return;
    pendingPollHandle = setInterval(async () => {
        if (!props.zoneId) {
            stopPendingPoll();
            return;
        }
        const hadPending = hasPendingBindings();
        await loadNodes(props.zoneId);
        reconcileBindingSpinners(props.zoneId);
        const stillPending = hasPendingBindings();
        if (hadPending && !stillPending) {
            showToast('Нода подтвердила привязку (config_report получен)', 'success');
            stopPendingPoll();
            return;
        }
        if (!stillPending || Date.now() > pendingPollDeadline) {
            if (Date.now() > pendingPollDeadline && stillPending) {
                clearBindingSpinnersAwaitingDevice(props.zoneId);
            }
            stopPendingPoll();
        }
    }, PENDING_POLL_INTERVAL_MS);
}

onMounted(() => {
    if (props.zoneId) reloadAll();
});

onUnmounted(() => {
    stopPendingPoll();
    clearAllBindingUiTimeouts();
    bindingNodeIds.value = new Set();
    bindingFailedNodeIds.value = new Set();
});

watch(
    () => props.zoneId,
    (id) => {
        clearAllBindingUiTimeouts();
        bindingNodeIds.value = new Set();
        bindingFailedNodeIds.value = new Set();
        if (id) reloadAll();
    },
);

watch(
    () => availableNodes.map((n) => `${n.id}:${n.zone_id ?? 0}:${n.pending_zone_id ?? 0}`).join('|'),
    () => {
        if (props.zoneId) {
            reconcileBindingSpinners(props.zoneId);
        }
        if (hasPendingBindings()) startPendingPoll();
    },
);

watch(
    () => ({
        waterForm: state.waterForm,
        lightingForm: state.lightingForm,
        zoneClimateForm: state.zoneClimateForm,
        assignments: state.assignments,
    }),
    () => {
        if (props.emitProfileAfterHydrate && !profileEmitAllowed.value) {
            return;
        }
        emitProfileFromState();
    },
    { deep: true, immediate: !props.emitProfileAfterHydrate },
);

function onPresetApplied(preset: ZoneAutomationPreset) {
    showToast(`Применён пресет «${preset.name}»`, 'success');
}

function onPresetCleared() {
    showToast('Пресет снят — используются defaults', 'info');
}
</script>

