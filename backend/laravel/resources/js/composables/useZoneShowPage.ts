import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { router, usePage } from "@inertiajs/vue3";
import { useHistory } from "@/composables/useHistory";
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
import { logger } from "@/utils/logger";
import { TOAST_TIMEOUT } from "@/constants/timeouts";
import { ERROR_MESSAGES } from "@/constants/messages";
import { getCycleStatusLabel, getCycleStatusVariant } from "@/utils/growCycleStatus";
import { calculateProgressBetween } from "@/utils/growCycleProgress";
import { normalizeGrowCycle } from "@/utils/normalizeGrowCycle";
import { parseZoneUpdatePayload } from "@/ws/zoneUpdatePayload";
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

interface LoadingState extends Record<string, boolean> {
  irrigate: boolean;
  nextPhase: boolean;
  cyclePause: boolean;
  cycleResume: boolean;
  cycleHarvest: boolean;
  cycleAbort: boolean;
  cycleChangeRecipe: boolean;
  pumpCalibrationRun: boolean;
  pumpCalibrationSave: boolean;
}

type PumpCalibrationComponent = "npk" | "calcium" | "micro" | "ph_up" | "ph_down";

interface PumpCalibrationRunPayload {
  node_channel_id: number;
  duration_sec: number;
  component: PumpCalibrationComponent;
}

interface PumpCalibrationSavePayload extends PumpCalibrationRunPayload {
  actual_ml: number;
  skip_run: true;
}

const zoneTabs = [
  { id: "overview", label: "Обзор" },
  { id: "telemetry", label: "Телеметрия" },
  { id: "cycle", label: "Цикл" },
  { id: "automation", label: "Автоматизация" },
  { id: "events", label: "События" },
  { id: "devices", label: "Устройства" },
];

const telemetryRanges = ["1H", "24H", "7D", "30D", "ALL"] as const;
type TelemetryRange = (typeof telemetryRanges)[number];

export function useZoneShowPage() {
  const page = usePage<PageProps>();
  const activeTab = useUrlState<string>({
    key: "tab",
    defaultValue: zoneTabs[0].id,
    parse: (value) => {
      if (!value) {
        return zoneTabs[0].id;
      }
      return zoneTabs.some((tab) => tab.id === value) ? value : zoneTabs[0].id;
    },
    serialize: (value) => value,
  });

  const modals = useModal<{
    action: boolean;
    growthCycle: boolean;
    pumpCalibration: boolean;
    attachNodes: boolean;
    nodeConfig: boolean;
  }>({
    action: false,
    growthCycle: false,
    pumpCalibration: false,
    attachNodes: false,
    nodeConfig: false,
  });

  const showActionModal = computed(() => modals.isModalOpen("action"));
  const showGrowthCycleModal = computed(() => modals.isModalOpen("growthCycle"));
  const showPumpCalibrationModal = computed(() => modals.isModalOpen("pumpCalibration"));
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
  const pumpCalibrationSaveSeq = ref(0);

  const { loading, setLoading } = useLoading<LoadingState>({
    irrigate: false,
    nextPhase: false,
    cyclePause: false,
    cycleResume: false,
    cycleHarvest: false,
    cycleAbort: false,
    cycleChangeRecipe: false,
    pumpCalibrationRun: false,
    pumpCalibrationSave: false,
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
      return typeof id === "string" ? Number.parseInt(id, 10) : id;
    }

    if (page.props.zone?.id) {
      const id = page.props.zone.id;
      return typeof id === "string" ? Number.parseInt(id, 10) : id;
    }

    const pathMatch = window.location.pathname.match(/\/zones\/(\d+)/);
    if (pathMatch && pathMatch[1]) {
      return Number.parseInt(pathMatch[1], 10);
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

  const telemetryRef = ref<ZoneTelemetry>(
    page.props.telemetry || ({ ph: null, ec: null, temperature: null, humidity: null } as ZoneTelemetry),
  );

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
  });

  const telemetry = computed(() => telemetryRef.value);

  const {
    targets: targetsProp,
    devices: devicesProp,
    events: eventsProp,
    cycles: cyclesProp,
    current_phase: currentPhaseProp,
    active_cycle: activeCycleProp,
    active_grow_cycle: activeGrowCycleProp,
  } = usePageProps<PageProps>([
    "targets",
    "devices",
    "events",
    "cycles",
    "current_phase",
    "active_cycle",
    "active_grow_cycle",
  ]);

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
    if (!phase || !phase.phase_started_at) {
      return null;
    }

    const now = new Date();
    const phaseStart = new Date(phase.phase_started_at);
    if (Number.isNaN(phaseStart.getTime())) {
      return null;
    }

    const elapsedMs = now.getTime() - phaseStart.getTime();
    if (elapsedMs <= 0) {
      return 0;
    }

    const elapsedDays = elapsedMs / (1000 * 60 * 60 * 24);
    return Math.floor(elapsedDays);
  });

  const computedPhaseDaysTotal = computed(() => {
    const phase = currentPhase.value;
    if (!phase || !phase.duration_hours) {
      return null;
    }

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
    if (Number.isNaN(endsAt.getTime())) {
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

  const chartTimeRange = ref<TelemetryRange>("24H");
  const chartDataPh = ref<Array<{ ts: number; value: number }>>([]);
  const chartDataEc = ref<Array<{ ts: number; value: number }>>([]);

  const telemetryRangeKey = computed(() => {
    return zoneId.value ? `zone:${zoneId.value}:telemetryRange` : null;
  });

  const getStoredTelemetryRange = (): TelemetryRange | null => {
    if (typeof window === "undefined") {
      return null;
    }
    const key = telemetryRangeKey.value;
    if (!key) {
      return null;
    }

    const stored = window.localStorage.getItem(key);
    return telemetryRanges.includes(stored as TelemetryRange) ? (stored as TelemetryRange) : null;
  };

  const loadChartData = async (metric: "PH" | "EC", timeRange: TelemetryRange): Promise<Array<{ ts: number; value: number }>> => {
    if (!zoneId.value) {
      return [];
    }

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
      if (from) {
        params.from = from.toISOString();
      }
      return await fetchHistory(zoneId.value, metric, params);
    } catch (err) {
      logger.error(`Failed to load ${metric} history:`, err);
      return [];
    }
  };

  const onChartTimeRangeChange = async (newRange: TelemetryRange): Promise<void> => {
    if (chartTimeRange.value === newRange) {
      return;
    }

    chartTimeRange.value = newRange;
    chartDataPh.value = await loadChartData("PH", newRange);
    chartDataEc.value = await loadChartData("EC", newRange);
  };

  watch(chartTimeRange, (value) => {
    if (typeof window === "undefined") {
      return;
    }

    const key = telemetryRangeKey.value;
    if (!key) {
      return;
    }

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
      zonesStore.upsert(zone.value, true);
      logger.debug("[Zones/Show] Zone initialized in store from props", { zoneId: zoneId.value });
    }

    const params = new URLSearchParams(window.location.search);
    const parseQueryNumber = (key: string): number | null => {
      const value = params.get(key);
      if (!value) {
        return null;
      }

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
        updateCommandStatus(commandEvent.commandId, commandEvent.status, commandEvent.message);
        const finalStatuses = ["DONE", "NO_EFFECT", "ERROR", "INVALID", "BUSY", "TIMEOUT", "SEND_FAILED"];
        if (finalStatuses.includes(commandEvent.status) && zoneId.value) {
          reloadZoneAfterCommand(zoneId.value, ["zone", "cycles"]);
        }
      });

      const echo = window.Echo;
      if (echo) {
        const currentZoneId = zoneId.value;
        const channel = echo.private(`hydro.zones.${currentZoneId}`);
        channel.listen(".App\\Events\\GrowCycleUpdated", (event: any) => {
          logger.info("[Zones/Show] GrowCycleUpdated event received", event);
          if (currentZoneId) {
            reloadZone(currentZoneId, ["zone", "active_grow_cycle"]);
          }
        });

        const originalUnsubscribe = unsubscribeZoneCommands;
        unsubscribeZoneCommands = () => {
          if (originalUnsubscribe) {
            originalUnsubscribe();
          }
          channel.stopListening(".App\\Events\\GrowCycleUpdated");
        };
      }
    }

    const { useStoreEvents } = await import("@/composables/useStoreEvents");
    const { subscribeWithCleanup } = useStoreEvents();
    subscribeWithCleanup("zone:updated", (updatedZone: unknown) => {
      const parsed = parseZoneUpdatePayload(updatedZone);
      if (parsed.zoneId !== zoneId.value) {
        return;
      }

      if (parsed.telemetry) {
        if (parsed.telemetry.ph !== undefined) {
          addUpdate(String(zoneId.value), "ph", parsed.telemetry.ph);
        }
        if (parsed.telemetry.ec !== undefined) {
          addUpdate(String(zoneId.value), "ec", parsed.telemetry.ec);
        }
        if (parsed.telemetry.temperature !== undefined) {
          addUpdate(String(zoneId.value), "temperature", parsed.telemetry.temperature);
        }
        if (parsed.telemetry.humidity !== undefined) {
          addUpdate(String(zoneId.value), "humidity", parsed.telemetry.humidity);
        }
        return;
      }

      reloadZone(zoneId.value, ["zone"]);
    });
  });

  const onRunCycle = async (): Promise<void> => {
    if (!zoneId.value) {
      logger.warn("[onRunCycle] zoneId is missing");
      showToast("Ошибка: зона не найдена", "error", TOAST_TIMEOUT.NORMAL);
      return;
    }

    modals.open("growthCycle");
  };

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

  const openActionModal = (actionType: CommandType): void => {
    currentActionType.value = actionType;
    modals.open("action");
  };

  const openPumpCalibrationModal = (): void => {
    modals.open("pumpCalibration");
  };

  const onActionSubmit = async ({
    actionType,
    params,
  }: {
    actionType: CommandType;
    params: Record<string, unknown>;
  }): Promise<void> => {
    if (!zoneId.value) {
      return;
    }

    setLoading("irrigate", true);
    const actionNames: Record<CommandType, string> = {
      FORCE_IRRIGATION: "Полив",
      FORCE_PH_CONTROL: "Коррекция pH",
      FORCE_EC_CONTROL: "Коррекция EC",
      FORCE_CLIMATE: "Управление климатом",
      FORCE_LIGHTING: "Управление освещением",
    };

    try {
      await sendZoneCommand(zoneId.value, actionType, params);
      const actionName = actionNames[actionType] || "Действие";
      showToast(`${actionName} запущено успешно`, "success", TOAST_TIMEOUT.NORMAL);
      reloadZoneAfterCommand(zoneId.value, ["zone", "cycles"]);
    } catch (err) {
      logger.error(`Failed to execute ${actionType}:`, err);
      let errorMessage: string = ERROR_MESSAGES.UNKNOWN;
      if (err && typeof err === "object" && "message" in err) {
        errorMessage = String(err.message);
      }
      const actionName = actionNames[actionType] || "Действие";
      showToast(`Ошибка при выполнении "${actionName}": ${errorMessage}`, "error", TOAST_TIMEOUT.LONG);
    } finally {
      setLoading("irrigate", false);
    }
  };

  const onPumpCalibrationRun = async (payload: PumpCalibrationRunPayload): Promise<void> => {
    if (!zoneId.value) {
      return;
    }

    setLoading("pumpCalibrationRun", true);
    try {
      await api.post(`/api/zones/${zoneId.value}/calibrate-pump`, payload);
      showToast(
        "Запуск калибровки отправлен. После завершения введите фактический объём и сохраните.",
        "success",
        TOAST_TIMEOUT.NORMAL,
      );
    } catch (error) {
      handleError(error, {
        component: "useZoneShowPage",
        action: "pumpCalibrationRun",
        zoneId: zoneId.value,
      });
    } finally {
      setLoading("pumpCalibrationRun", false);
    }
  };

  const onPumpCalibrationSave = async (payload: PumpCalibrationSavePayload): Promise<void> => {
    if (!zoneId.value) {
      return;
    }

    setLoading("pumpCalibrationSave", true);
    try {
      await api.post(`/api/zones/${zoneId.value}/calibrate-pump`, {
        ...payload,
        skip_run: true,
      });
      showToast("Калибровка сохранена в конфигурации канала.", "success", TOAST_TIMEOUT.NORMAL);
      pumpCalibrationSaveSeq.value += 1;
    } catch (error) {
      handleError(error, {
        component: "useZoneShowPage",
        action: "pumpCalibrationSave",
        zoneId: zoneId.value,
      });
    } finally {
      setLoading("pumpCalibrationSave", false);
    }
  };

  const onGrowthCycleWizardSubmit = async ({ zoneId: emittedZoneId }: {
    zoneId: number;
    recipeId?: number;
    startedAt: string;
    expectedHarvestAt?: string;
  }): Promise<void> => {
    if (emittedZoneId) {
      reloadZoneAfterCommand(emittedZoneId, ["zone", "cycles", "active_grow_cycle", "active_cycle"]);
    }
  };

  const openNodeConfig = (nodeId: number, node: any): void => {
    selectedNodeId.value = nodeId;
    selectedNode.value = node;
    modals.open("nodeConfig");
  };

  const onNodesAttached = async (_nodeIds: number[]): Promise<void> => {
    if (!zoneId.value) {
      return;
    }

    router.reload({
      only: ["zone", "devices"],
      preserveScroll: true,
      preserveState: true,
    });
  };

  const {
    harvestModal,
    abortModal,
    changeRecipeModal,
    closeHarvestModal,
    closeAbortModal,
    closeChangeRecipeModal,
    onNextPhase,
    onCyclePause,
    onCycleResume,
    onCycleHarvest,
    confirmHarvest,
    onCycleAbort,
    confirmAbort,
    onCycleChangeRecipe,
    confirmChangeRecipe,
  } = useZoneCycleActions({
    activeGrowCycle,
    zoneId,
    api,
    reloadZone,
    showToast,
    setLoading,
    handleError,
  });

  return {
    zoneTabs,
    activeTab,
    modals,
    showActionModal,
    showGrowthCycleModal,
    showPumpCalibrationModal,
    showAttachNodesModal,
    showNodeConfigModal,
    currentActionType,
    selectedNodeId,
    selectedNode,
    growthCycleInitialData,
    pumpCalibrationSaveSeq,
    loading,
    zoneId,
    zone,
    telemetry,
    targets,
    currentPhase,
    activeCycle,
    activeGrowCycle,
    devices,
    events,
    canOperateZone,
    canManageDevices,
    canManageRecipe,
    canManageCycle,
    computedPhaseProgress,
    computedPhaseDaysElapsed,
    computedPhaseDaysTotal,
    cycleStatusLabel,
    cycleStatusVariant,
    phaseTimeLeftLabel,
    cyclesList,
    chartTimeRange,
    chartDataPh,
    chartDataEc,
    onChartTimeRangeChange,
    onRunCycle,
    variant,
    openActionModal,
    openPumpCalibrationModal,
    onActionSubmit,
    onPumpCalibrationRun,
    onPumpCalibrationSave,
    onGrowthCycleWizardSubmit,
    openNodeConfig,
    onNodesAttached,
    harvestModal,
    abortModal,
    changeRecipeModal,
    closeHarvestModal,
    closeAbortModal,
    closeChangeRecipeModal,
    onNextPhase,
    onCyclePause,
    onCycleResume,
    onCycleHarvest,
    confirmHarvest,
    onCycleAbort,
    confirmAbort,
    onCycleChangeRecipe,
    confirmChangeRecipe,
  };
}
