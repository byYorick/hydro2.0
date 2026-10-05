<template>
  <section
    class="rounded-xl border border-[color:var(--border-muted)]/60 bg-[color:var(--surface-card)]/50 p-3 space-y-3"
    data-testid="crop-day-section"
  >
    <div>
      <h4 class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-dim)]">
        Сутки
      </h4>
      <p class="text-xs text-[color:var(--text-muted)] mt-0.5">
        Снимок суток культуры. Числа только из состояния зоны
      </p>
    </div>

    <dl class="grid grid-cols-2 gap-2 text-xs">
      <div class="day-tile">
        <dt>Дата</dt>
        <dd data-testid="crop-day-date">
          {{ view.dateLabel }}
        </dd>
      </div>
      <div class="day-tile">
        <dt>Пояс</dt>
        <dd data-testid="crop-day-timezone">
          {{ view.timezoneLabel }}
        </dd>
      </div>
      <div class="day-tile">
        <dt>Команды полива</dt>
        <dd data-testid="crop-day-irrigation-commands">
          {{ view.irrigationCommandsLabel }}
        </dd>
      </div>
      <div class="day-tile">
        <dt>Commanded, с</dt>
        <dd data-testid="crop-day-commanded-sec">
          {{ view.commandedSecLabel }}
        </dd>
      </div>
      <div class="day-tile col-span-2">
        <dt>Commanded, мл</dt>
        <dd data-testid="crop-day-commanded-ml">
          {{ view.commandedMlLabel }}
        </dd>
      </div>
      <div class="day-tile col-span-2">
        <dt>Свет</dt>
        <dd data-testid="crop-day-light">
          <p>{{ view.lightLabel }}</p>
          <p
            v-if="view.photoperiodLabel"
            data-testid="crop-day-photoperiod"
          >
            Фотопериод: {{ view.photoperiodLabel }}
          </p>
          <p
            v-if="view.brightnessLabel"
            data-testid="crop-day-brightness"
          >
            Яркость: {{ view.brightnessLabel }}
          </p>
        </dd>
      </div>
    </dl>

    <div
      class="day-block"
      data-testid="crop-day-climate"
    >
      <p class="font-semibold text-[color:var(--text-primary)]">
        Климат
      </p>
      <p
        v-if="view.climateMissing"
        data-testid="crop-day-climate-missing"
      >
        нет снимка климата
      </p>
      <dl
        v-else
        class="grid grid-cols-1 gap-1.5"
      >
        <div>
          <dt>VPD воздуха</dt>
          <dd data-testid="crop-day-air-vpd">
            {{ view.airVpdLabel }}
          </dd>
        </div>
        <div>
          <dt>Точка росы</dt>
          <dd data-testid="crop-day-dew-point">
            {{ view.dewPointLabel }}
          </dd>
        </div>
        <div>
          <dt>Подавление влажностного открытия</dt>
          <dd data-testid="crop-day-moisture-suppressed">
            {{ view.moistureSuppressedLabel }}
          </dd>
        </div>
      </dl>
    </div>

    <div
      class="day-block"
      data-testid="crop-day-solution"
    >
      <p class="font-semibold text-[color:var(--text-primary)]">
        Раствор
      </p>
      <dl class="grid grid-cols-1 gap-1.5">
        <div>
          <dt>Температура</dt>
          <dd data-testid="crop-day-solution-temp">
            {{ view.solutionTempLabel }}
          </dd>
        </div>
        <div>
          <dt>Gate раствора</dt>
          <dd data-testid="crop-day-solution-gate">
            {{ view.solutionGateLabel }}
          </dd>
        </div>
        <div>
          <dt>Подмена</dt>
          <dd data-testid="crop-day-solution-refresh">
            {{ view.solutionRefreshLabel }}
          </dd>
        </div>
      </dl>
    </div>

    <ul
      v-if="view.hints.length > 0"
      class="space-y-2"
      data-testid="crop-day-hints"
    >
      <li
        v-for="hint in view.hints"
        :key="hint.code"
        class="rounded-lg border border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] px-3 py-2 text-xs text-[color:var(--badge-warning-text)]"
        :data-testid="`crop-day-hint-${hint.code}`"
      >
        <p v-if="hint.message">
          {{ hint.message }}
        </p>
        <p
          v-if="hint.recommendation"
          class="mt-1 opacity-90"
        >
          {{ hint.recommendation }}
        </p>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AutomationState } from '@/types/Automation'
import { resolveCropDayView } from '@/utils/cropDayView'

interface Props {
  automationState: AutomationState | null
  recipePhase?: unknown
}

const props = defineProps<Props>()

const view = computed(() => resolveCropDayView(props.automationState, props.recipePhase))
</script>

<style scoped>
.day-tile,
.day-block {
  border-radius: 0.65rem;
  border: 1px solid color-mix(in srgb, var(--border-muted) 85%, transparent);
  background: color-mix(in srgb, var(--bg-elevated) 78%, transparent);
  padding: 0.5rem 0.65rem;
}

.day-tile dt,
.day-block dt {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
}

.day-tile dd,
.day-block dd {
  margin-top: 0.15rem;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-primary);
  word-break: break-word;
}

.day-block {
  font-size: 0.75rem;
  line-height: 1.4;
}
</style>
