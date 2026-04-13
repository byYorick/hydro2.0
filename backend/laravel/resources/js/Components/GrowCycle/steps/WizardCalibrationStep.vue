<template>
  <div class="space-y-4">
    <div class="flex items-start justify-between gap-3">
      <div>
        <h3 class="text-sm font-semibold">
          Калибровка насосов
        </h3>
        <p class="text-xs text-[color:var(--text-muted)] mt-1">
          Используется тот же calibration flow, что и в setup wizard. Сохранённые значения берутся только из backend `pump_calibrations`.
        </p>
      </div>
      <Button
        size="sm"
        variant="primary"
        :disabled="!zoneId || loadingRun || loadingSave"
        @click="$emit('open-modal')"
      >
        Открыть калибровку насосов
      </Button>
    </div>

    <div
      v-if="devicesLoading"
      class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] text-sm text-[color:var(--text-muted)]"
    >
      Загружаю насосы зоны...
    </div>

    <div
      v-else-if="devicesError"
      class="p-4 rounded-lg bg-[color:var(--badge-danger-bg)] border border-[color:var(--badge-danger-border)] text-sm text-[color:var(--badge-danger-text)] space-y-2"
    >
      <div>{{ devicesError }}</div>
      <Button
        size="sm"
        variant="secondary"
        @click="$emit('refresh')"
      >
        Повторить
      </Button>
    </div>

    <div
      v-else-if="pumpChannelsCount === 0"
      class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] text-sm text-[color:var(--text-muted)] space-y-2"
    >
      <div>В зоне не найдены дозирующие насосы для calibration flow.</div>
      <Button
        size="sm"
        variant="secondary"
        @click="$emit('refresh')"
      >
        Обновить список
      </Button>
    </div>

    <div
      v-else
      class="space-y-3"
    >
      <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] space-y-3">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div class="text-sm font-medium">
              Сохранено {{ calibratedChannels.length }} из {{ mappedPumpComponents.length }} ожидаемых pump calibration.
            </div>
            <div class="text-xs text-[color:var(--text-muted)] mt-1">
              Launch wizard не записывает `ml/sec` локально. Сначала сохраните калибровки через общую модалку, затем readiness автоматически разрешит запуск.
            </div>
          </div>
          <Button
            size="sm"
            variant="secondary"
            :disabled="loadingRun || loadingSave"
            @click="$emit('refresh')"
          >
            Обновить статус
          </Button>
        </div>

        <div class="flex flex-wrap gap-2">
          <span
            v-for="item in mappedPumpComponents"
            :key="item.component"
            class="inline-flex items-center rounded-full border px-2.5 py-1 text-xs"
            :class="item.calibrated
              ? 'border-[color:var(--badge-success-border)] bg-[color:var(--badge-success-bg)] text-[color:var(--badge-success-text)]'
              : 'border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] text-[color:var(--badge-warning-text)]'"
          >
            {{ item.label }}: {{ item.calibrated ? 'готово' : 'не сохранено' }}
          </span>
        </div>
      </div>

      <div
        v-if="missingPumpComponents.length > 0"
        class="p-3 rounded-lg bg-[color:var(--badge-warning-bg)] border border-[color:var(--badge-warning-border)] text-sm text-[color:var(--badge-warning-text)]"
      >
        Для correction runtime ещё не сохранены: {{ missingPumpComponents.join(', ') }}.
      </div>

      <div
        v-if="calibratedChannels.length > 0"
        class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]"
      >
        <div class="text-xs text-[color:var(--text-dim)] mb-2">
          Уже сохранено
        </div>
        <div class="space-y-1">
          <div
            v-for="channel in calibratedChannels"
            :key="channel.id"
            class="text-sm text-[color:var(--text-primary)]"
          >
            {{ channel.label }}: {{ channel.calibration?.ml_per_sec ?? '-' }} мл/сек
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Button from "@/Components/Button.vue";
import type { PumpCalibrationComponent } from "@/types/Calibration";

interface MappedPumpComponent {
  component: PumpCalibrationComponent;
  label: string;
  calibrated: boolean;
}

interface CalibratedChannel {
  id: number;
  label: string;
  calibration?: { ml_per_sec?: number | null } | null;
}

interface Props {
  zoneId: number | null;
  devicesLoading: boolean;
  devicesError: string | null;
  pumpChannelsCount: number;
  mappedPumpComponents: MappedPumpComponent[];
  calibratedChannels: CalibratedChannel[];
  missingPumpComponents: string[];
  loadingRun: boolean;
  loadingSave: boolean;
}

defineProps<Props>();

defineEmits<{
  'open-modal': [];
  refresh: [];
}>();
</script>
