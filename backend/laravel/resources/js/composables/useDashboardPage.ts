import { computed, reactive, ref, watch, type ComputedRef, type Ref } from "vue";
import { useCommands } from "@/composables/useCommands";
import { useDashboardRealtimeFeed } from "@/composables/useDashboardRealtimeFeed";
import { useTheme } from "@/composables/useTheme";
import { useToast } from "@/composables/useToast";
import { logger } from "@/utils/logger";
import type { Alert, Greenhouse, Zone } from "@/types";

export type QuickAction = "PAUSE" | "RESUME" | "FORCE_IRRIGATION";
export type TelemetryPeriod = "1h" | "24h" | "7d";

export type TelemetryZone = Pick<Zone, "id" | "name" | "status"> & {
  greenhouse?: { name?: string | null } | null;
};

export interface DashboardData {
  greenhousesCount: number;
  zonesCount: number;
  devicesCount: number;
  alertsCount: number;
  zonesByStatus?: Record<string, number>;
  nodesByStatus?: Record<string, number>;
  greenhouses?: Greenhouse[];
  problematicZones?: Zone[];
  zones?: TelemetryZone[];
  latestAlerts?: Alert[];
}

const TELEMETRY_ZONE_STORAGE_KEY = "dashboard.telemetry.zone";
const TELEMETRY_PERIOD_STORAGE_KEY = "dashboard.telemetry.period";

export const telemetryRangeOptions: Array<{ label: string; value: TelemetryPeriod }> = [
  { label: "1ч", value: "1h" },
  { label: "24ч", value: "24h" },
  { label: "7д", value: "7d" },
];

interface UseDashboardPageOptions {
  dashboard: ComputedRef<DashboardData>;
}

export function useDashboardPage({ dashboard }: UseDashboardPageOptions): {
  zonesStatusSummary: ComputedRef<Record<string, number>>;
  nodesStatusSummary: ComputedRef<Record<string, number>>;
  hasGreenhouses: ComputedRef<boolean>;
  hasProblematicZones: ComputedRef<boolean>;
  hasZones: ComputedRef<boolean>;
  telemetryPeriod: Ref<TelemetryPeriod>;
  selectedZoneId: Ref<number | null>;
  telemetryZones: ComputedRef<TelemetryZone[]>;
  selectedZoneLabel: ComputedRef<string>;
  telemetryPeriodLabel: ComputedRef<string>;
  hasZonesForTelemetry: ComputedRef<boolean>;
  isQuickActionLoading: (zoneId: number, action?: QuickAction) => boolean;
  eventFilter: Ref<"ALL" | "ALERT" | "WARNING" | "INFO" | "SUCCESS">;
  filteredEvents: Ref<Array<{ id: number; kind: string; message: string; occurred_at?: string; created_at?: string; zone_id?: number }>>;
  telemetryMetrics: Ref<Array<{ key: string; label: string; data: Array<{ ts: number; value?: number | null; avg?: number | null; min?: number | null; max?: number | null }>; currentValue?: number; unit: string; loading: boolean; color: string }>>;
  handleOpenDetail: (zoneId: number, metric: string) => void;
  handleQuickAction: (zone: Zone, action: QuickAction) => Promise<void>;
} {
  const { showToast } = useToast();
  const { sendZoneCommand } = useCommands(showToast);
  const { theme } = useTheme();

  const zonesStatusSummary = computed(() => dashboard.value.zonesByStatus || {});
  const nodesStatusSummary = computed(() => dashboard.value.nodesByStatus || {});
  const hasGreenhouses = computed(() => {
    const greenhouses = dashboard.value.greenhouses;
    return Array.isArray(greenhouses) && greenhouses.length > 0;
  });
  const hasProblematicZones = computed(() => {
    const zones = dashboard.value.problematicZones;
    return Array.isArray(zones) && zones.length > 0;
  });
  const hasZones = computed(() => dashboard.value.zonesCount > 0);

  const telemetryPeriod = ref<TelemetryPeriod>("24h");
  const selectedZoneId = ref<number | null>(null);

  const telemetryZones = computed<TelemetryZone[]>(() => {
    const uniqueZones = new Map<number, TelemetryZone>();
    const problemZones = Array.isArray(dashboard.value.problematicZones) ? dashboard.value.problematicZones : [];
    const payloadZones = Array.isArray(dashboard.value.zones) ? dashboard.value.zones : [];

    const pushZone = (zone: Partial<TelemetryZone> & { id?: number | string | null; greenhouse?: { name?: string | null } | null }) => {
      if (!zone?.id) {
        return;
      }

      const normalizedId = typeof zone.id === "string" ? Number.parseInt(zone.id, 10) : zone.id;
      if (!normalizedId || Number.isNaN(normalizedId) || uniqueZones.has(normalizedId)) {
        return;
      }

      uniqueZones.set(normalizedId, {
        id: normalizedId,
        name: zone.name || `Зона ${zone.id}`,
        status: zone.status,
        greenhouse: zone.greenhouse ? { name: zone.greenhouse.name } : null,
      });
    };

    problemZones.forEach(pushZone);
    payloadZones.forEach(pushZone);

    return Array.from(uniqueZones.values());
  });

  const selectedZone = computed(() => {
    if (!selectedZoneId.value) {
      return null;
    }

    return telemetryZones.value.find((zone) => zone.id === selectedZoneId.value) ?? null;
  });

  const selectedZoneLabel = computed(() => selectedZone.value?.name ?? "");
  const telemetryPeriodLabel = computed(() => telemetryRangeOptions.find((option) => option.value === telemetryPeriod.value)?.label ?? "24ч");
  const hasZonesForTelemetry = computed(() => telemetryZones.value.length > 0);

  const quickActionLoading = reactive<Record<number, QuickAction | null>>({});
  const isQuickActionLoading = (zoneId: number, action?: QuickAction): boolean => {
    const state = quickActionLoading[zoneId];
    if (!state) {
      return false;
    }

    return action ? state === action : true;
  };

  watch(
    telemetryZones,
    (zones) => {
      if (!zones.length) {
        selectedZoneId.value = null;
        return;
      }
      if (selectedZoneId.value && zones.some((zone) => zone.id === selectedZoneId.value)) {
        return;
      }

      selectedZoneId.value = zones[0].id;
    },
    { immediate: true },
  );

  watch(selectedZoneId, (zoneId) => {
    if (typeof window === "undefined") {
      return;
    }

    if (zoneId) {
      window.localStorage.setItem(TELEMETRY_ZONE_STORAGE_KEY, String(zoneId));
    } else {
      window.localStorage.removeItem(TELEMETRY_ZONE_STORAGE_KEY);
    }
  });

  watch(telemetryPeriod, (period) => {
    if (typeof window === "undefined") {
      return;
    }

    window.localStorage.setItem(TELEMETRY_PERIOD_STORAGE_KEY, period);
  });

  const latestAlerts = computed(() => dashboard.value.latestAlerts || []);
  const {
    eventFilter,
    filteredEvents,
    telemetryMetrics,
    handleOpenDetail,
    loadTelemetryMetrics,
    resetTelemetryData,
  } = useDashboardRealtimeFeed({
    theme,
    selectedZoneId,
    telemetryPeriod,
    latestAlerts,
  });

  watch([selectedZoneId, telemetryPeriod], ([zoneId]) => {
    if (!zoneId) {
      resetTelemetryData();
      return;
    }

    void loadTelemetryMetrics();
  });

  const restoreTelemetryPreferences = (): void => {
    if (typeof window === "undefined") {
      return;
    }

    const storedZoneId = window.localStorage.getItem(TELEMETRY_ZONE_STORAGE_KEY);
    if (storedZoneId) {
      const parsed = Number(storedZoneId);
      if (!Number.isNaN(parsed) && telemetryZones.value.some((zone) => zone.id === parsed)) {
        selectedZoneId.value = parsed;
      }
    } else if (selectedZoneId.value) {
      window.localStorage.setItem(TELEMETRY_ZONE_STORAGE_KEY, String(selectedZoneId.value));
    }

    const storedPeriod = window.localStorage.getItem(TELEMETRY_PERIOD_STORAGE_KEY) as TelemetryPeriod | null;
    if (storedPeriod && telemetryRangeOptions.some((option) => option.value === storedPeriod)) {
      telemetryPeriod.value = storedPeriod;
    } else {
      window.localStorage.setItem(TELEMETRY_PERIOD_STORAGE_KEY, telemetryPeriod.value);
    }
  };

  const handleQuickAction = async (zone: Zone, action: QuickAction): Promise<void> => {
    const zoneId = typeof zone.id === "string" ? Number.parseInt(zone.id, 10) : zone.id;
    if (!zoneId) {
      return;
    }

    quickActionLoading[zoneId] = action;

    try {
      if (action === "PAUSE") {
        await sendZoneCommand(zoneId, "PAUSE", {});
        showToast(`Зона "${zone.name}" приостановлена`, "success");
      } else if (action === "RESUME") {
        await sendZoneCommand(zoneId, "RESUME", {});
        showToast(`Зона "${zone.name}" запущена`, "success");
      } else {
        await sendZoneCommand(zoneId, "FORCE_IRRIGATION", {});
        showToast(`Запущен полив для зоны "${zone.name}"`, "success");
      }
    } catch (error) {
      logger.error("[Dashboard] Failed to execute quick action:", error);
      showToast(`Ошибка выполнения действия для зоны "${zone.name}"`, "error");
    } finally {
      quickActionLoading[zoneId] = null;
    }
  };

  restoreTelemetryPreferences();

  return {
    zonesStatusSummary,
    nodesStatusSummary,
    hasGreenhouses,
    hasProblematicZones,
    hasZones,
    telemetryPeriod,
    selectedZoneId,
    telemetryZones,
    selectedZoneLabel,
    telemetryPeriodLabel,
    hasZonesForTelemetry,
    isQuickActionLoading,
    eventFilter,
    filteredEvents,
    telemetryMetrics,
    handleOpenDetail,
    handleQuickAction,
  };
}
