<template>
  <AppLayout>
    <div class="space-y-4">
      <div class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-3">
        <Tabs
          v-model="activeTab"
          :tabs="zoneTabs"
          aria-label="Разделы зоны"
        />
      </div>
      <ZoneOverviewTab
        v-show="activeTab === 'overview'"
        :zone="zone"
        :variant="variant"
        :active-grow-cycle="activeGrowCycle"
        :active-cycle="activeCycle"
        :loading="loading"
        :can-operate-zone="canOperateZone"
        :targets="targets"
        :telemetry="telemetry"
        :computed-phase-progress="computedPhaseProgress"
        :computed-phase-days-elapsed="computedPhaseDaysElapsed"
        :computed-phase-days-total="computedPhaseDaysTotal"
        :events="events"
        @force-irrigation="openActionModal('FORCE_IRRIGATION')"
      />
      <ZoneTelemetryTab
        v-show="activeTab === 'telemetry'"
        :zone-id="zoneId"
        :chart-time-range="chartTimeRange"
        :chart-data-ph="chartDataPh"
        :chart-data-ec="chartDataEc"
        :telemetry="telemetry"
        :targets="targets"
        @time-range-change="onChartTimeRangeChange"
      />
      <ZoneCycleTab
        v-show="activeTab === 'cycle'"
        :active-grow-cycle="activeGrowCycle"
        :current-phase="currentPhase"
        :zone-status="zone.status"
        :cycles-list="cyclesList"
        :computed-phase-progress="computedPhaseProgress"
        :computed-phase-days-elapsed="computedPhaseDaysElapsed"
        :computed-phase-days-total="computedPhaseDaysTotal"
        :cycle-status-label="cycleStatusLabel"
        :cycle-status-variant="cycleStatusVariant"
        :phase-time-left-label="phaseTimeLeftLabel"
        :can-manage-recipe="canManageRecipe"
        :can-manage-cycle="canManageCycle"
        :loading="loading"
        @run-cycle="onRunCycle"
        @change-recipe="onCycleChangeRecipe"
        @pause="onCyclePause"
        @resume="onCycleResume"
        @harvest="onCycleHarvest"
        @abort="onCycleAbort"
        @next-phase="onNextPhase"
      />
      <ZoneAutomationTab
        v-show="activeTab === 'automation'"
        :zone-id="zoneId"
        :targets="targets"
        :telemetry="telemetry"
      />
      <ZoneEventsTab
        v-show="activeTab === 'events'"
        :events="events"
        :zone-id="zoneId"
      />
      <ZoneDevicesTab
        v-show="activeTab === 'devices'"
        :zone="zone"
        :devices="devices"
        :can-manage-devices="canManageDevices"
        @attach="modals.open('attachNodes')"
        @configure="(device) => openNodeConfig(device.id, device)"
      />
    </div>
    <ZoneDetailModals
      :show-action-modal="showActionModal"
      :show-growth-cycle-modal="showGrowthCycleModal"
      :show-attach-nodes-modal="showAttachNodesModal"
      :show-node-config-modal="showNodeConfigModal"
      :zone-id="zoneId"
      :zone-name="zone.name"
      :current-phase-targets="currentPhase?.targets || null"
      :active-cycle="activeCycle"
      :growth-cycle-initial-data="growthCycleInitialData"
      :selected-node-id="selectedNodeId"
      :selected-node="selectedNode"
      :current-action-type="currentActionType"
      :harvest-modal="harvestModal"
      :abort-modal="abortModal"
      :change-recipe-modal="changeRecipeModal"
      :loading="loading"
      @close-action="modals.close('action')"
      @submit-action="onActionSubmit"
      @close-attach-nodes="modals.close('attachNodes')"
      @nodes-attached="onNodesAttached"
      @close-node-config="modals.close('nodeConfig')"
      @close-growth-cycle="modals.close('growthCycle')"
      @submit-growth-cycle="onGrowthCycleWizardSubmit"
      @close-harvest="closeHarvestModal"
      @confirm-harvest="confirmHarvest"
      @close-abort="closeAbortModal"
      @confirm-abort="confirmAbort"
      @close-change-recipe="closeChangeRecipeModal"
      @confirm-change-recipe="confirmChangeRecipe"
    />
  </AppLayout>
</template>
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { usePage } from "@inertiajs/vue3";
import AppLayout from "@/Layouts/AppLayout.vue";
import Tabs from "@/Components/Tabs.vue";
import ZoneAutomationTab from "@/Pages/Zones/Tabs/ZoneAutomationTab.vue";
import ZoneCycleTab from "@/Pages/Zones/Tabs/ZoneCycleTab.vue";
import ZoneDevicesTab from "@/Pages/Zones/Tabs/ZoneDevicesTab.vue";
import ZoneEventsTab from "@/Pages/Zones/Tabs/ZoneEventsTab.vue";
import ZoneOverviewTab from "@/Pages/Zones/Tabs/ZoneOverviewTab.vue";
import ZoneTelemetryTab from "@/Pages/Zones/Tabs/ZoneTelemetryTab.vue";
import ZoneDetailModals from "@/Pages/Zones/ZoneDetailModals.vue";
import { useHistory } from "@/composables/useHistory";
import { logger } from "@/utils/logger";
import { useCommands } from "@/composables/useCommands";
import { useTelemetry } from "@/composables/useTelemetry";
import { useZones } from "@/composables/useZones";
import { useApi } from "@/composables/useApi";
import { useWebSocket } from "@/composables/useWebSocket";
import { useErrorHandler } from "@/composables/useErrorHandler";
import { useZonesStore } from "@/stores/zones";
import { useTelemetryBatch } from "@/composables/useOptimizedUpdates";
import { useToast } from "@/composables/useToast";
import { useModal } from "@/composables/useModal";
import { useLoading } from "@/composables/useLoading";
import { useUrlState } from "@/composables/useUrlState";
import { usePageProps } from "@/composables/usePageProps";
import { useZoneCycleActions } from "@/composables/useZoneCycleActions";
import { TOAST_TIMEOUT } from "@/constants/timeouts";
import { ERROR_MESSAGES } from "@/constants/messages";
import { getCycleStatusLabel, getCycleStatusVariant } from "@/utils/growCycleStatus";
import { calculateProgressBetween } from "@/utils/growCycleProgress";
import { normalizeGrowCycle } from "@/utils/normalizeGrowCycle";
import type { BadgeVariant } from "@/Components/Badge.vue";
import type { Zone, Device, ZoneTelemetry, ZoneTargets as ZoneTargetsType, Cycle, CommandType } from "@/types";
import type { ZoneEvent } from "@/types/ZoneEvent";
interface PageProps {
    zone?: Zone;
    zoneId?: number;
    telemetry?: ZoneTelemetry;
    targets?: ZoneTargetsType;
    devices?: Device[];
    events?: ZoneEvent[];
    cycles?: Record<string, Cycle>;
    current_phase?: any;
    active_cycle?: any;
    active_grow_cycle?: any;
    auth?: {
        user?: {
            role?: string;
        };
    };
    [key: string]: any;
}
const page = usePage<PageProps>();
const zoneTabs = [
    { id: "overview", label: "Обзор" },
    { id: "telemetry", label: "Телеметрия" },
    { id: "cycle", label: "Цикл" },
    { id: "automation", label: "Автоматизация" },
    { id: "events", label: "События" },
    { id: "devices", label: "Устройства" },
];
const activeTab = useUrlState<string>({
    key: "tab",
    defaultValue: zoneTabs[0].id,
    parse: (value) => {
        if (!value) return zoneTabs[0].id;
        return zoneTabs.some((tab) => tab.id === value) ? value : zoneTabs[0].id;
    },
    serialize: (value) => value,
});
const modals = useModal<{
    action: boolean;
    growthCycle: boolean;
    attachNodes: boolean;
    nodeConfig: boolean;
}>({
    action: false,
    growthCycle: false,
    attachNodes: false,
    nodeConfig: false,
});
const showActionModal = computed(() => modals.isModalOpen("action"));
const showGrowthCycleModal = computed(() => modals.isModalOpen("growthCycle"));
const showAttachNodesModal = computed(() => modals.isModalOpen("attachNodes"));
const showNodeConfigModal = computed(() => modals.isModalOpen("nodeConfig"));
const currentActionType = ref<CommandType>("FORCE_IRRIGATION");
const selectedNodeId = ref<number | null>(null);
const selectedNode = ref<any>(null);
const growthCycleInitialData = ref<{
    recipeId?: number | null;
    recipeRevisionId?: number | null;
    plantId?: number | null;
    startedAt?: string | null;
    expectedHarvestAt?: string | null;
} | null>(null);
interface LoadingState extends Record<string, boolean> {
    irrigate: boolean;
    nextPhase: boolean;
    cyclePause: boolean;
    cycleResume: boolean;
    cycleHarvest: boolean;
    cycleAbort: boolean;
    cycleChangeRecipe: boolean;
}
const { loading, setLoading } = useLoading<LoadingState>({
    irrigate: false,
    nextPhase: false,
    cyclePause: false,
    cycleResume: false,
    cycleHarvest: false,
    cycleAbort: false,
    cycleChangeRecipe: false,
});
const { showToast } = useToast();
const { sendZoneCommand, reloadZoneAfterCommand, updateCommandStatus } = useCommands(showToast);
const { fetchHistory } = useTelemetry(showToast);
const { reloadZone } = useZones(showToast);
const { api } = useApi(showToast);
const { subscribeToZoneCommands } = useWebSocket(showToast);
const { handleError } = useErrorHandler(showToast);
const zonesStore = useZonesStore();
const zoneId = computed(() => {
    if (page.props.zoneId) {
        const id = page.props.zoneId;
        return typeof id === "string" ? parseInt(id) : id;
    }
    if (page.props.zone?.id) {
        const id = page.props.zone.id;
        return typeof id === "string" ? parseInt(id) : id;
    }
    const pathMatch = window.location.pathname.match(/\/zones\/(\d+)/);
    if (pathMatch && pathMatch[1]) {
        return parseInt(pathMatch[1]);
    }
    return undefined;
});
const zone = computed<Zone>(() => {
    const zoneIdValue = zoneId.value;
    if (zoneIdValue) {
        const storeZone = zonesStore.zoneById(zoneIdValue);
        if (storeZone && storeZone.id) {
            return storeZone;
        }
    }
    const rawZoneData = (page.props.zone || {}) as any;
    const zoneData = { ...rawZoneData };
    if (!zoneData.id && zoneIdValue) {
        zoneData.id = zoneIdValue;
    }
    if (!zoneData.id) {
        return {
            id: zoneIdValue || undefined,
        } as Zone;
    }
    return zoneData as Zone;
});
const { addToHistory } = useHistory();
watch(
    zone,
    (newZone) => {
        if (newZone?.id) {
            addToHistory({
                id: newZone.id,
                type: "zone",
                name: newZone.name || `Зона ${newZone.id}`,
                url: `/zones/${newZone.id}`,
            });
        }
    },
    { immediate: true },
);
const telemetryRef = ref<ZoneTelemetry>(page.props.telemetry || ({ ph: null, ec: null, temperature: null, humidity: null } as ZoneTelemetry));
const { addUpdate, flush } = useTelemetryBatch((updates) => {
    const currentZoneId = zoneId.value;
    updates.forEach((metrics, zoneIdStr) => {
        if (zoneIdStr === String(currentZoneId)) {
            const current = { ...telemetryRef.value };
            metrics.forEach((value, metric) => {
                switch (metric) {
                    case "ph":
                        current.ph = value;
                        break;
                    case "ec":
                        current.ec = value;
                        break;
                    case "temperature":
                        current.temperature = value;
                        break;
                    case "humidity":
                        current.humidity = value;
                        break;
                }
            });
            telemetryRef.value = current;
        }
    });
}); // Использует DEBOUNCE_DELAY.NORMAL по умолчанию
const telemetry = computed(() => telemetryRef.value);
const { targets: targetsProp, devices: devicesProp, events: eventsProp, cycles: cyclesProp, current_phase: currentPhaseProp, active_cycle: activeCycleProp, active_grow_cycle: activeGrowCycleProp } = usePageProps<PageProps>(["targets", "devices", "events", "cycles", "current_phase", "active_cycle", "active_grow_cycle"]);
const targets = computed(() => (targetsProp.value || {}) as ZoneTargetsType);
const currentPhase = computed(() => {
    if (currentPhaseProp.value) {
        return currentPhaseProp.value as any;
    }
    return null;
});
const activeCycle = computed(() => {
    return (activeCycleProp.value || (zone.value as any)?.active_cycle || (zone.value as any)?.activeCycle || null) as any;
});
const rawActiveGrowCycle = computed(() => {
    return zone.value?.activeGrowCycle || (zone.value as any)?.active_grow_cycle || activeCycle.value || activeGrowCycleProp.value || null;
});
const activeGrowCycle = computed(() => normalizeGrowCycle(rawActiveGrowCycle.value) as any);
const devices = computed(() => (devicesProp.value || []) as Device[]);
const events = computed(() => (eventsProp.value || []) as ZoneEvent[]);
const cycles = computed(() => (cyclesProp.value || {}) as Record<string, Cycle>);
const userRole = computed(() => page.props.auth?.user?.role || "viewer");
const isAgronomist = computed(() => userRole.value === "agronomist");
const canOperateZone = computed(() => ["admin", "operator", "agronomist", "engineer"].includes(userRole.value));
const canManageDevices = computed(() => ["admin", "agronomist"].includes(userRole.value));
const canManageRecipe = computed(() => isAgronomist.value || userRole.value === "admin");
const canManageCycle = computed(() => ["admin", "agronomist", "operator"].includes(userRole.value));
const computedPhaseProgress = computed(() => {
    const phase = currentPhase.value;
    if (!phase) {
        logger.debug("[Zones/Show] computedPhaseProgress: phase is null");
        return null;
    }
    if (!phase.phase_started_at || !phase.phase_ends_at) {
        logger.debug("[Zones/Show] computedPhaseProgress: missing dates", {
            phase_started_at: phase.phase_started_at,
            phase_ends_at: phase.phase_ends_at,
        });
        return null;
    }
    const progress = calculateProgressBetween(phase.phase_started_at, phase.phase_ends_at);
    if (progress === null) {
        logger.debug("[Zones/Show] computedPhaseProgress: unable to calculate", {
            phase_started_at: phase.phase_started_at,
            phase_ends_at: phase.phase_ends_at,
        });
        return null;
    }
    return progress;
});
const computedPhaseDaysElapsed = computed(() => {
    const phase = currentPhase.value;
    if (!phase || !phase.phase_started_at) return null;
    const now = new Date();
    const phaseStart = new Date(phase.phase_started_at);
    if (isNaN(phaseStart.getTime())) {
        return null;
    }
    const elapsedMs = now.getTime() - phaseStart.getTime();
    if (elapsedMs <= 0) return 0;
    const elapsedDays = elapsedMs / (1000 * 60 * 60 * 24);
    return Math.floor(elapsedDays);
});
const computedPhaseDaysTotal = computed(() => {
    const phase = currentPhase.value;
    if (!phase || !phase.duration_hours) return null;
    return Math.ceil(phase.duration_hours / 24);
});
const cycleStatusLabel = computed(() => {
    if (activeGrowCycle.value) {
        return getCycleStatusLabel(activeGrowCycle.value.status, "sentence");
    }
    if (activeCycle.value) {
        return "Цикл активен";
    }
    return "Цикл не запущен";
});
const cycleStatusVariant = computed<BadgeVariant>(() => {
    if (activeGrowCycle.value) {
        return getCycleStatusVariant(activeGrowCycle.value.status);
    }
    if (activeCycle.value) {
        return "success";
    }
    return "neutral";
});
const phaseTimeLeftLabel = computed(() => {
    const phase = currentPhase.value;
    if (!phase || !phase.phase_ends_at) {
        return "";
    }
    const now = new Date();
    const endsAt = new Date(phase.phase_ends_at);
    if (isNaN(endsAt.getTime())) {
        return "";
    }
    const diffMs = endsAt.getTime() - now.getTime();
    if (diffMs <= 0) {
        return "Фаза завершена";
    }
    const minutes = Math.floor(diffMs / 60000);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    if (days > 0) {
        return `До конца фазы: ${days} дн.`;
    }
    if (hours > 0) {
        return `До конца фазы: ${hours} ч`;
    }
    return `До конца фазы: ${minutes} мин`;
});
const cyclesList = computed(() => {
    const phaseTargets = (currentPhase.value?.targets || {}) as any;
    const active = (activeCycle.value?.subsystems || {}) as any;
    const serverCycles = cycles.value || {};
    const base = [
        {
            key: "ph",
            type: "PH_CONTROL",
            required: true,
            recipeTargets: phaseTargets.ph || null,
            activeTargets: active.ph?.targets || null,
            enabled: active.ph?.enabled ?? true,
            strategy: serverCycles.PH_CONTROL?.strategy || "periodic",
            interval: serverCycles.PH_CONTROL?.interval ?? 300,
            last_run: serverCycles.PH_CONTROL?.last_run || null,
            next_run: serverCycles.PH_CONTROL?.next_run || null,
        },
        {
            key: "ec",
            type: "EC_CONTROL",
            required: true,
            recipeTargets: phaseTargets.ec || null,
            activeTargets: active.ec?.targets || null,
            enabled: active.ec?.enabled ?? true,
            strategy: serverCycles.EC_CONTROL?.strategy || "periodic",
            interval: serverCycles.EC_CONTROL?.interval ?? 300,
            last_run: serverCycles.EC_CONTROL?.last_run || null,
            next_run: serverCycles.EC_CONTROL?.next_run || null,
        },
        {
            key: "irrigation",
            type: "IRRIGATION",
            required: true,
            recipeTargets: phaseTargets.irrigation || null,
            activeTargets: active.irrigation?.targets || null,
            enabled: active.irrigation?.enabled ?? true,
            strategy: serverCycles.IRRIGATION?.strategy || "periodic",
            interval: serverCycles.IRRIGATION?.interval ?? null,
            last_run: serverCycles.IRRIGATION?.last_run || null,
            next_run: serverCycles.IRRIGATION?.next_run || null,
        },
        {
            key: "lighting",
            type: "LIGHTING",
            required: false,
            recipeTargets: phaseTargets.lighting || null,
            activeTargets: active.lighting?.targets || null,
            enabled: active.lighting?.enabled ?? false,
            strategy: serverCycles.LIGHTING?.strategy || "periodic",
            interval: serverCycles.LIGHTING?.interval ?? null,
            last_run: serverCycles.LIGHTING?.last_run || null,
            next_run: serverCycles.LIGHTING?.next_run || null,
        },
        {
            key: "climate",
            type: "CLIMATE",
            required: false,
            recipeTargets: phaseTargets.climate || null,
            activeTargets: active.climate?.targets || null,
            enabled: active.climate?.enabled ?? false,
            strategy: serverCycles.CLIMATE?.strategy || "periodic",
            interval: serverCycles.CLIMATE?.interval ?? 300,
            last_run: serverCycles.CLIMATE?.last_run || null,
            next_run: serverCycles.CLIMATE?.next_run || null,
        },
    ];
    return base as Array<
        {
            key: string;
            type: string;
            required: boolean;
            recipeTargets: any;
            activeTargets: any;
            enabled: boolean;
        } & Cycle & {
                last_run?: string | null;
                next_run?: string | null;
                interval?: number | null;
            }
    >;
});
const telemetryRanges = ["1H", "24H", "7D", "30D", "ALL"] as const;
type TelemetryRange = (typeof telemetryRanges)[number];
const chartTimeRange = ref<TelemetryRange>("24H");
const chartDataPh = ref<Array<{ ts: number; value: number }>>([]);
const chartDataEc = ref<Array<{ ts: number; value: number }>>([]);
const telemetryRangeKey = computed(() => {
    return zoneId.value ? `zone:${zoneId.value}:telemetryRange` : null;
});
const getStoredTelemetryRange = (): TelemetryRange | null => {
    if (typeof window === "undefined") return null;
    const key = telemetryRangeKey.value;
    if (!key) return null;
    const stored = window.localStorage.getItem(key);
    return telemetryRanges.includes(stored as TelemetryRange) ? (stored as TelemetryRange) : null;
};
async function loadChartData(metric: "PH" | "EC", timeRange: TelemetryRange): Promise<Array<{ ts: number; value: number }>> {
    if (!zoneId.value) return [];
    const now = new Date();
    let from: Date | null = null;
    switch (timeRange) {
        case "1H":
            from = new Date(now.getTime() - 60 * 60 * 1000);
            break;
        case "24H":
            from = new Date(now.getTime() - 24 * 60 * 60 * 1000);
            break;
        case "7D":
            from = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
            break;
        case "30D":
            from = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
            break;
        case "ALL":
            from = null;
            break;
    }
    try {
        const params: { from?: string; to: string } = { to: now.toISOString() };
        if (from) params.from = from.toISOString();
        return await fetchHistory(zoneId.value, metric, params);
    } catch (err) {
        logger.error(`Failed to load ${metric} history:`, err);
        return [];
    }
}
async function onChartTimeRangeChange(newRange: TelemetryRange): Promise<void> {
    if (chartTimeRange.value === newRange) return;
    chartTimeRange.value = newRange;
    chartDataPh.value = await loadChartData("PH", newRange);
    chartDataEc.value = await loadChartData("EC", newRange);
}
watch(chartTimeRange, (value) => {
    if (typeof window === "undefined") return;
    const key = telemetryRangeKey.value;
    if (!key) return;
    window.localStorage.setItem(key, value);
});
let unsubscribeZoneCommands: (() => void) | null = null;
onUnmounted(() => {
    if (unsubscribeZoneCommands) {
        unsubscribeZoneCommands();
        unsubscribeZoneCommands = null;
    }
    flush();
});
onMounted(async () => {
    logger.info("[Show.vue] Компонент смонтирован", { zoneId: zoneId.value });
    if (zoneId.value && zone.value?.id) {
        zonesStore.upsert(zone.value, true); // silent: true, так как это начальная инициализация
        logger.debug("[Zones/Show] Zone initialized in store from props", { zoneId: zoneId.value });
    }
    const params = new URLSearchParams(window.location.search);
    const parseQueryNumber = (key: string): number | null => {
        const value = params.get(key);
        if (!value) return null;
        const parsed = Number(value);
        return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
    };
    const startedAt = params.get("started_at");
    const expectedHarvestAt = params.get("expected_harvest_at");
    growthCycleInitialData.value = {
        recipeId: parseQueryNumber("recipe_id"),
        recipeRevisionId: parseQueryNumber("recipe_revision_id"),
        plantId: parseQueryNumber("plant_id"),
        startedAt: startedAt || null,
        expectedHarvestAt: expectedHarvestAt || null,
    };
    if (params.get("start_cycle") === "1") {
        modals.open("growthCycle");
    }
    const storedRange = getStoredTelemetryRange();
    if (storedRange) {
        chartTimeRange.value = storedRange;
    }
    chartDataPh.value = await loadChartData("PH", chartTimeRange.value);
    chartDataEc.value = await loadChartData("EC", chartTimeRange.value);
    if (zoneId.value) {
        unsubscribeZoneCommands = subscribeToZoneCommands(zoneId.value, (commandEvent) => {
            updateCommandStatus(commandEvent.commandId, commandEvent.status as any, commandEvent.message);
            const finalStatuses = ["DONE", "NO_EFFECT", "ERROR", "INVALID", "BUSY", "TIMEOUT", "SEND_FAILED"];
            if (finalStatuses.includes(commandEvent.status)) {
                if (zoneId.value) {
                    reloadZoneAfterCommand(zoneId.value, ["zone", "cycles"]);
                }
            }
        });
        const echo = window.Echo;
        if (echo) {
            const channel = echo.private(`hydro.zones.${zoneId.value}`);
            channel.listen(".App\\Events\\GrowCycleUpdated", (event: any) => {
                logger.info("[Zones/Show] GrowCycleUpdated event received", event);
                reloadZone(zoneId.value, ["zone", "active_grow_cycle"]);
            });
            const originalUnsubscribe = unsubscribeZoneCommands;
            unsubscribeZoneCommands = () => {
                if (originalUnsubscribe) originalUnsubscribe();
                channel.stopListening(".App\\Events\\GrowCycleUpdated");
            };
        }
    }
    const { useStoreEvents } = await import("@/composables/useStoreEvents");
    const { subscribeWithCleanup } = useStoreEvents();
    subscribeWithCleanup("zone:updated", (updatedZone: any) => {
        if (updatedZone.id === zoneId.value) {
            if (updatedZone.telemetry) {
                const tel = updatedZone.telemetry;
                if (tel.ph !== null && tel.ph !== undefined) {
                    addUpdate(String(zoneId.value), "ph", tel.ph);
                }
                if (tel.ec !== null && tel.ec !== undefined) {
                    addUpdate(String(zoneId.value), "ec", tel.ec);
                }
                if (tel.temperature !== null && tel.temperature !== undefined) {
                    addUpdate(String(zoneId.value), "temperature", tel.temperature);
                }
                if (tel.humidity !== null && tel.humidity !== undefined) {
                    addUpdate(String(zoneId.value), "humidity", tel.humidity);
                }
            } else {
                reloadZone(zoneId.value, ["zone"]);
            }
        }
    });
});
async function onRunCycle(): Promise<void> {
    if (!zoneId.value) {
        logger.warn("[onRunCycle] zoneId is missing");
        showToast("Ошибка: зона не найдена", "error", TOAST_TIMEOUT.NORMAL);
        return;
    }
    modals.open("growthCycle");
}
const variant = computed<"success" | "neutral" | "warning" | "danger">(() => {
    switch (zone.value.status) {
        case "RUNNING":
            return "success";
        case "PAUSED":
            return "neutral";
        case "WARNING":
            return "warning";
        case "ALARM":
            return "danger";
        default:
            return "neutral";
    }
});
function openActionModal(actionType: CommandType): void {
    currentActionType.value = actionType;
    modals.open("action");
}
async function onActionSubmit({ actionType, params }: { actionType: CommandType; params: Record<string, unknown> }): Promise<void> {
    if (!zoneId.value) return;
    setLoading("irrigate", true);
    const actionNames: Record<CommandType, string> = {
        FORCE_IRRIGATION: "Полив",
        FORCE_PH_CONTROL: "Коррекция pH",
        FORCE_EC_CONTROL: "Коррекция EC",
        FORCE_CLIMATE: "Управление климатом",
        FORCE_LIGHTING: "Управление освещением",
    } as Record<CommandType, string>;
    try {
        await sendZoneCommand(zoneId.value, actionType, params);
        const actionName = actionNames[actionType] || "Действие";
        showToast(`${actionName} запущено успешно`, "success", TOAST_TIMEOUT.NORMAL);
        if (zoneId.value) {
            reloadZoneAfterCommand(zoneId.value, ["zone", "cycles"]);
        }
    } catch (err) {
        logger.error(`Failed to execute ${actionType}:`, err);
        let errorMessage: string = ERROR_MESSAGES.UNKNOWN;
        if (err && typeof err === "object" && "message" in err) errorMessage = String(err.message);
        const actionName = actionNames[actionType] || "Действие";
        showToast(`Ошибка при выполнении "${actionName}": ${errorMessage}`, "error", TOAST_TIMEOUT.LONG);
    } finally {
        setLoading("irrigate", false);
    }
}
async function onGrowthCycleWizardSubmit({ zoneId, recipeId: _recipeId, startedAt: _startedAt, expectedHarvestAt: _expectedHarvestAt }: { zoneId: number; recipeId?: number; startedAt: string; expectedHarvestAt?: string }): Promise<void> {
    if (zoneId) {
        reloadZoneAfterCommand(zoneId, ["zone", "cycles", "active_grow_cycle", "active_cycle"]);
    }
}
function openNodeConfig(nodeId: number, node: any): void {
    selectedNodeId.value = nodeId;
    selectedNode.value = node;
    modals.open("nodeConfig");
}
async function onNodesAttached(_nodeIds: number[]): Promise<void> {
    if (!zoneId.value) return;
    try {
        const { fetchZone } = useZones(showToast);
        const updatedZone = await fetchZone(zoneId.value, true); // forceRefresh = true
        if (updatedZone?.id) {
            zonesStore.upsert(updatedZone);
            logger.debug("[Zones/Show] Zone updated in store after nodes attachment", { zoneId: updatedZone.id });
        }
    } catch (error) {
        logger.error("[Zones/Show] Failed to update zone after nodes attachment, falling back to reload", { zoneId: zoneId.value, error });
        reloadZone(zoneId.value, ["zone", "devices"]);
    }
}
const { harvestModal, abortModal, changeRecipeModal, closeHarvestModal, closeAbortModal, closeChangeRecipeModal, onNextPhase, onCyclePause, onCycleResume, onCycleHarvest, confirmHarvest, onCycleAbort, confirmAbort, onCycleChangeRecipe, confirmChangeRecipe } = useZoneCycleActions({
    activeGrowCycle,
    zoneId,
    api,
    reloadZone,
    showToast,
    setLoading,
    handleError,
});
</script>
