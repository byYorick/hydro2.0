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
        :recipe-summary="recipeSummary"
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
import type { AutomationNode as SetupWizardNode } from '@/types/AutomationNode';
import type { ZoneAutomationPreset } from '@/types/ZoneAutomationPreset';
import type { IrrigationSystem, WaterFormState } from '@/composables/zoneAutomationTypes';
import { resolveRecipePhaseSystemType } from '@/composables/recipeSystemType';

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
}

const props = withDefaults(defineProps<Props>(), {
    zoneId: undefined,
    currentRecipePhase: null,
    recipeSummary: null,
});

const emit = defineEmits<{
    (event: 'update:profile', next: AutomationProfile): void;
}>();

const { showToast } = useToast();

const state = reactive<AutomationProfile>(structuredClone(automationProfileDefaults));
const availableNodes: SetupWizardNode[] = reactive([]);

const loading = ref(false);
const refreshingNodes = ref(false);
const bindingInProgress = ref(false);
const bindingNodeIds = ref<Set<number>>(new Set());
let pendingPollHandle: ReturnType<typeof setInterval> | null = null;
let pendingPollDeadline = 0;
const PENDING_POLL_INTERVAL_MS = 2500;
const PENDING_POLL_TIMEOUT_MS = 60_000;

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

async function loadBindings(zoneId: number) {
    try {
        const resp = await api.zones.getById(zoneId);
        const data = resp as unknown as { channel_bindings?: unknown };
        if (data.channel_bindings) {
            state.assignments = bindingsResponseToAssignments(data.channel_bindings);
        }
    } catch {
        // keep defaults
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
    loading.value = true;
    try {
        await Promise.all([
            loadLogicProfile(props.zoneId),
            loadBindings(props.zoneId),
            loadNodes(props.zoneId),
        ]);
    } finally {
        loading.value = false;
    }
}

async function onRefreshNodes() {
    if (!props.zoneId) return;
    refreshingNodes.value = true;
    try {
        await loadNodes(props.zoneId);
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
        await loadBindings(props.zoneId);
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
    bindingNodeIds.value = new Set([...bindingNodeIds.value, nodeId]);
    try {
        await api.nodes.update(nodeId, { zone_id: props.zoneId });
        showToast('Привязка отправлена — ждём config_report от ноды…', 'info');
        await loadNodes(props.zoneId);
        startPendingPoll();
    } catch (error) {
        showToast((error as Error).message || 'Ошибка привязки ноды', 'error');
    } finally {
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
        const stillPending = hasPendingBindings();
        if (hadPending && !stillPending) {
            showToast('Нода подтвердила привязку (config_report получен)', 'success');
            stopPendingPoll();
            return;
        }
        if (!stillPending || Date.now() > pendingPollDeadline) {
            stopPendingPoll();
        }
    }, PENDING_POLL_INTERVAL_MS);
}

onMounted(() => {
    if (props.zoneId) reloadAll();
});

onUnmounted(() => {
    stopPendingPoll();
});

watch(
    () => props.zoneId,
    (id) => {
        if (id) reloadAll();
    },
);

watch(
    () => availableNodes.map((n) => `${n.id}:${n.zone_id ?? 0}:${n.pending_zone_id ?? 0}`).join('|'),
    () => {
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
    (next) => {
        emit('update:profile', {
            waterForm: { ...next.waterForm },
            lightingForm: { ...next.lightingForm },
            zoneClimateForm: { ...next.zoneClimateForm },
            assignments: { ...next.assignments },
        });
    },
    { deep: true, immediate: true },
);

function onWaterFormUpdate(next: WaterFormState) {
    state.waterForm = next;
}

function onPresetApplied(preset: ZoneAutomationPreset) {
    showToast(`Применён пресет «${preset.name}»`, 'success');
}

function onPresetCleared() {
    showToast('Пресет снят — используются defaults', 'info');
}
</script>

