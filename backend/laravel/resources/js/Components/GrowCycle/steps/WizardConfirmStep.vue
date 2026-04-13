<template>
  <div class="space-y-4">
    <h3 class="text-sm font-semibold mb-1">
      Предпросмотр запуска
    </h3>

    <ReadinessChecklist
      :zone-id="zoneId"
      :readiness="readiness"
      :loading="readinessLoading"
    />

    <div class="space-y-3">
      <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
        <div class="text-xs text-[color:var(--text-dim)] mb-1">
          Зона
        </div>
        <div class="text-sm font-medium">
          {{ zoneName || `Зона #${zoneId}` }}
        </div>
      </div>

      <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
        <div class="text-xs text-[color:var(--text-dim)] mb-1">
          Рецепт
        </div>
        <div class="text-sm font-medium">
          {{ recipeName || "Не выбран" }}
        </div>
        <div
          v-if="totalDurationDays > 0"
          class="text-xs text-[color:var(--text-muted)] mt-1"
        >
          Оценочная длительность: {{ Math.round(totalDurationDays) }} дней
        </div>
      </div>

      <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
        <div class="text-xs text-[color:var(--text-dim)] mb-1">
          Период
        </div>
        <div class="text-sm font-medium">
          Старт: {{ formatDateTime(startedAt) }}
        </div>
        <div
          v-if="expectedHarvestAt"
          class="text-xs text-[color:var(--text-muted)] mt-1"
        >
          Сбор: {{ formatDate(expectedHarvestAt) }}
        </div>
      </div>

      <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
        <div class="text-xs text-[color:var(--text-dim)] mb-1">
          Автоматика
        </div>
        <div class="text-sm font-medium">
          Автоматика: pH {{ waterForm.targetPh }}, EC {{ waterForm.targetEc }}, система {{ waterForm.systemType }}
        </div>
      </div>

      <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
        <div class="text-xs text-[color:var(--text-dim)] mb-1">
          Полив
        </div>
        <div class="text-sm font-medium">
          {{ irrigationStrategyLabel }} · {{ waterForm.systemType }}
        </div>
        <div class="text-xs text-[color:var(--text-muted)] mt-1">
          {{ irrigationScheduleSummary }}
        </div>
        <div
          v-if="tanksCount === 2"
          class="text-xs text-[color:var(--text-muted)] mt-1"
        >
          Баки: {{ waterForm.cleanTankFillL }} / {{ waterForm.nutrientTankTargetL }} л, партия {{ waterForm.irrigationBatchL }} л
        </div>
        <div
          v-if="isSmartIrrigation"
          class="text-xs text-[color:var(--text-muted)] mt-1"
        >
          Датчик влажности: {{ soilMoistureBoundNodeChannelId ? `node_channel_id ${soilMoistureBoundNodeChannelId}` : 'не привязан' }}
        </div>
      </div>

      <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
        <div class="text-xs text-[color:var(--text-dim)] mb-1">
          Калибровка насосов
        </div>
        <div class="text-sm font-medium">
          {{ calibratedCount }} сохранено, {{ missingPumpComponents.length }} требуют внимания
        </div>
      </div>

      <div
        v-if="recipePhases.length > 0"
        class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]"
      >
        <div class="text-xs text-[color:var(--text-dim)] mb-2">
          План фаз:
        </div>
        <div class="space-y-2">
          <div
            v-for="(phase, index) in recipePhases"
            :key="index"
            class="flex items-center justify-between text-xs"
          >
            <span class="font-medium">{{ phase.name || `Фаза ${index + 1}` }}</span>
            <span class="text-[color:var(--text-muted)]">{{ phaseDurationLabel(phase) }} дней</span>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="validationErrors.length > 0"
      class="p-3 rounded-lg bg-[color:var(--badge-danger-bg)] border border-[color:var(--badge-danger-border)]"
    >
      <div class="text-sm font-medium text-[color:var(--badge-danger-text)] mb-1">
        Ошибки валидации:
      </div>
      <ul class="text-xs text-[color:var(--badge-danger-text)] list-disc list-inside">
        <li
          v-for="validationError in validationErrors"
          :key="validationError"
        >
          {{ validationError }}
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import ReadinessChecklist from "@/Components/GrowCycle/ReadinessChecklist.vue";
import type { WaterFormState } from "@/composables/zoneAutomationTypes";
import type { ZoneLaunchReadiness } from "@/composables/useZoneReadiness";

interface RecipePhase {
  name?: string | null;
  duration_days?: number | null;
  duration_hours?: number | null;
}

interface Props {
  zoneId: number | null;
  zoneName?: string;
  readiness: ZoneLaunchReadiness | null;
  readinessLoading: boolean;
  recipeName?: string | null;
  recipePhases: RecipePhase[];
  totalDurationDays: number;
  startedAt: string;
  expectedHarvestAt?: string;
  waterForm: WaterFormState;
  tanksCount: number;
  isSmartIrrigation: boolean;
  irrigationStrategyLabel: string;
  irrigationScheduleSummary: string;
  soilMoistureBoundNodeChannelId: number | null;
  calibratedCount: number;
  missingPumpComponents: string[];
  validationErrors: string[];
  formatDateTime: (value: string) => string;
  formatDate: (value: string) => string;
}

defineProps<Props>();

function phaseDurationLabel(phase: RecipePhase): string | number {
  if (phase.duration_days != null) {
    return phase.duration_days;
  }
  if (phase.duration_hours != null) {
    return Math.round(phase.duration_hours / 24);
  }
  return "-";
}
</script>
