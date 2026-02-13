import { router, useForm } from "@inertiajs/vue3";
import { computed, ref, watch } from "vue";
import { useSimpleModal } from "@/composables/useModal";
import { usePageProps } from "@/composables/usePageProps";
import { useToast } from "@/composables/useToast";
import { formatCurrency, formatDuration, formatIrrigationInterval, formatRange, formatTargetRange, hasPhaseTargets, hasTargetValue } from "@/utils/plantDisplay";

interface EnvironmentRange {
  min?: number | string | null;
  max?: number | string | null;
}

interface RecipePhase {
  id: number;
  phase_index: number;
  name: string;
  duration_hours: number;
  targets?: {
    ph?: { min?: number; max?: number } | number | null;
    ec?: { min?: number; max?: number } | number | null;
    temp_air?: number | null;
    humidity_air?: number | null;
    light_hours?: number | null;
    irrigation_interval_sec?: number | null;
    irrigation_duration_sec?: number | null;
    [key: string]: unknown;
  };
}

interface PlantRecipe {
  id: number;
  name: string;
  description?: string;
  is_default?: boolean;
  season?: string;
  site_type?: string;
  phases?: RecipePhase[];
  phases_count?: number;
}

interface ProfitabilitySnapshot {
  plant_id: number;
  currency: string;
  total_cost: number | null;
  wholesale_price: number | null;
  retail_price: number | null;
  margin_wholesale: number | null;
  margin_retail: number | null;
  has_pricing: boolean;
}

interface PlantSummary {
  id: number;
  slug: string;
  name: string;
  species?: string | null;
  variety?: string | null;
  substrate_type?: string | null;
  growing_system?: string | null;
  photoperiod_preset?: string | null;
  seasonality?: string | null;
  description?: string | null;
  environment_requirements?: Record<string, EnvironmentRange> | null;
  growth_phases?: Array<{ name?: string; duration_days?: number }>;
  recipes?: PlantRecipe[];
  profitability?: ProfitabilitySnapshot | null;
}

interface TaxonomyOption {
  id: string;
  label: string;
}

interface PageProps {
  plant?: PlantSummary;
  taxonomies?: Record<string, TaxonomyOption[]>;
  [key: string]: unknown;
}

export function usePlantShowPage() {
  const { plant: plantProp, taxonomies: taxonomiesProp } = usePageProps<PageProps>(["plant", "taxonomies"]);
  const plant = computed(() => (plantProp.value || {}) as PlantSummary);
  const taxonomies = computed(() => {
    const taxonomyValue = taxonomiesProp.value as Record<string, TaxonomyOption[]> | undefined;
    return {
      substrate_type: taxonomyValue?.substrate_type ?? [],
      growing_system: taxonomyValue?.growing_system ?? [],
      photoperiod_preset: taxonomyValue?.photoperiod_preset ?? [],
      seasonality: taxonomyValue?.seasonality ?? [],
    };
  });

  const { showToast } = useToast();
  const { isOpen: showEditModal, open: openEditModal, close: closeEditModal } = useSimpleModal();
  const deleting = ref(false);
  const deleteModalOpen = ref(false);

  const taxonomyIndex = computed(() => {
    const map: Record<string, Record<string, string>> = {};
    Object.entries(taxonomies.value).forEach(([key, options]) => {
      map[key] = options.reduce(
        (acc, option) => {
          acc[option.id] = option.label;
          return acc;
        },
        {} as Record<string, string>,
      );
    });
    return map;
  });

  const defaultSeasonality = [
    { id: "all_year", label: "Круглый год" },
    { id: "multi_cycle", label: "Несколько циклов" },
    { id: "seasonal", label: "Сезонное выращивание" },
  ];

  const seasonOptions = computed(() => (taxonomies.value.seasonality && taxonomies.value.seasonality.length > 0 ? taxonomies.value.seasonality : defaultSeasonality));

  const rangeMetrics = [
    { key: "temperature", label: "Температура (°C)" },
    { key: "humidity", label: "Влажность (%)" },
    { key: "ph", label: "pH" },
    { key: "ec", label: "EC (мСм/см)" },
  ];

  const emptyEnvironment = () =>
    rangeMetrics.reduce(
      (acc, metric) => {
        acc[metric.key] = { min: "", max: "" };
        return acc;
      },
      {} as Record<string, EnvironmentRange>,
    );

  const form = useForm({
    name: "",
    slug: "",
    species: "",
    variety: "",
    substrate_type: "",
    growing_system: "",
    photoperiod_preset: "",
    seasonality: "",
    description: "",
    environment_requirements: emptyEnvironment(),
  });

  const hasEnvironment = computed(() => Boolean(plant.value.environment_requirements && Object.keys(plant.value.environment_requirements).length > 0));

  function taxonomyLabel(key: string, value?: string | null): string {
    if (!value) return "—";
    return taxonomyIndex.value[key]?.[value] ?? value;
  }

  function seasonalityLabel(value?: string | null): string {
    if (!value) return "—";
    const fallback = seasonOptions.value.find((option) => option.id === value);
    return taxonomyIndex.value.seasonality?.[value] ?? fallback?.label ?? value;
  }

  function metricLabel(metric: string): string {
    const metricMap: Record<string, string> = {
      temperature: "Температура (°C)",
      humidity: "Влажность (%)",
      ph: "pH",
      ec: "EC (мСм/см)",
    };
    return metricMap[metric] || metric;
  }

  function populateEnvironment(env?: Record<string, EnvironmentRange> | null): Record<string, EnvironmentRange> {
    const template = emptyEnvironment();
    if (!env) {
      return template;
    }
    Object.keys(template).forEach((key) => {
      template[key] = {
        min: env[key]?.min ?? "",
        max: env[key]?.max ?? "",
      };
    });
    return template;
  }

  watch(
    () => showEditModal.value,
    (newVal: boolean) => {
      if (newVal && plant.value) {
        form.reset({
          name: plant.value.name,
          slug: plant.value.slug,
          species: plant.value.species || "",
          variety: plant.value.variety || "",
          substrate_type: plant.value.substrate_type || "",
          growing_system: plant.value.growing_system || "",
          photoperiod_preset: plant.value.photoperiod_preset || "",
          seasonality: plant.value.seasonality || "",
          description: plant.value.description || "",
          environment_requirements: populateEnvironment(plant.value.environment_requirements),
        } as never);
        form.clearErrors();
      }
    },
  );

  function handleSubmit(): void {
    if (!plant.value?.id) return;
    form.put(`/plants/${plant.value.id}`, {
      onSuccess: () => {
        showToast("Растение обновлено", "success");
        closeEditModal();
      },
      onError: () => showToast("Не удалось обновить растение", "error"),
    });
  }

  function deletePlant(): void {
    if (!plant.value?.id) return;
    deleteModalOpen.value = true;
  }

  function confirmDeletePlant(): void {
    if (!plant.value?.id) return;
    deleting.value = true;
    router.delete(`/plants/${plant.value.id}`, {
      onSuccess: () => {
        showToast("Растение удалено", "success");
        deleteModalOpen.value = false;
        router.visit("/plants");
      },
      onError: () => {
        showToast("Ошибка при удалении растения", "error");
        deleting.value = false;
      },
    });
  }

  return {
    plant,
    taxonomies,
    showEditModal,
    openEditModal,
    closeEditModal,
    deleting,
    deleteModalOpen,
    seasonOptions,
    rangeMetrics,
    form,
    hasEnvironment,
    taxonomyLabel,
    seasonalityLabel,
    metricLabel,
    handleSubmit,
    deletePlant,
    confirmDeletePlant,
    formatCurrency,
    formatDuration,
    formatIrrigationInterval,
    formatRange,
    formatTargetRange,
    hasPhaseTargets,
    hasTargetValue,
  };
}
