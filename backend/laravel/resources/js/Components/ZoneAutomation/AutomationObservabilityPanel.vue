<template>
  <section
    class="rounded-xl border border-[color:var(--border-muted)]/60 bg-[color:var(--surface-card)]/50 p-3 space-y-3"
    data-testid="automation-observability-panel"
  >
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div>
        <h4 class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-dim)]">
          Состояние автоматики
        </h4>
        <p class="text-xs text-[color:var(--text-muted)] mt-0.5">
          Текущий этап, причины ожидания и действия при проблемах
        </p>
      </div>
      <Badge :variant="healthBadgeVariant">
        {{ healthLabel }}
      </Badge>
    </div>

    <p class="text-xs text-[color:var(--text-muted)]">
      Предельный срок — ограничение ожидания, а не прогноз завершения. Сведения относятся к полученному снимку.
    </p>
    <dl class="grid grid-cols-2 gap-2 text-xs">
      <div class="diag-tile">
        <dt>Этап выполнения</dt>
        <dd>{{ stageLabel }}</dd>
      </div>
      <div class="diag-tile">
        <dt>Статус задачи</dt>
        <dd>{{ taskStatusLabel }}</dd>
      </div>
      <div class="diag-tile">
        <dt>На этапе</dt>
        <dd>{{ stageElapsedLabel }}</dd>
      </div>
      <div class="diag-tile">
        <dt>До предельного срока этапа</dt>
        <dd>{{ deadlineLabel }}</dd>
      </div>
      <div
        v-if="correctionStep"
        class="diag-tile col-span-2"
      >
        <dt>Коррекция</dt>
        <dd class="font-mono text-[11px]">
          {{ correctionDosing?.corrStepLabel ?? stageDiagnosticLabel(correctionStep) }}
        </dd>
        <p class="mt-1 text-[10px] text-[color:var(--text-dim)] leading-relaxed">
          Условия завершения коррекции зависят от её режима и допусков. Готовность раствора к следующему этапу проверяется отдельно.
        </p>
      </div>
      <div
        v-if="topologyLabel"
        class="diag-tile"
      >
        <dt>Схема оборудования</dt>
        <dd class="font-mono text-[11px]">
          {{ topologyLabel }}
        </dd>
      </div>
      <div
        v-if="pendingManualStepLabel"
        class="diag-tile col-span-2"
      >
        <dt>Ручной шаг</dt>
        <dd class="font-mono text-[11px]">
          {{ pendingManualStepLabel }}
        </dd>
      </div>
    </dl>

    <div
      v-if="correctionDosing"
      class="rounded-lg border px-3 py-2.5 text-xs space-y-1.5"
      :class="correctionDosingClass"
      data-testid="automation-correction-dosing"
    >
      <p class="font-semibold text-sm">
        Коррекция / дозирование
      </p>
      <p
        v-if="correctionDosing.reason"
        class="leading-relaxed"
      >
        {{ correctionDosing.reason }}
      </p>
      <p
        v-if="correctionDosing.detail"
        class="text-[10px] opacity-85 leading-relaxed"
      >
        {{ correctionDosing.detail }}
      </p>
      <dl class="grid grid-cols-1 sm:grid-cols-2 gap-1.5 text-[10px]">
        <div
          v-if="correctionDosing.activeDoses.length > 0"
          data-testid="automation-correction-active-doses"
        >
          <dt class="uppercase tracking-wide opacity-70">
            Дозы по данным задачи
          </dt>
          <dd class="mt-0.5 font-mono">
            {{ activeDosesLabel }}
          </dd>
        </div>
        <div v-if="correctionDosing.corrStepLabel">
          <dt class="uppercase tracking-wide opacity-70">
            Шаг AE3
          </dt>
          <dd class="mt-0.5 font-mono">
            {{ correctionDosing.corrStepLabel }}
          </dd>
        </div>
        <div v-if="correctionDosing.lastDoseSummary">
          <dt class="uppercase tracking-wide opacity-70">
            Последняя доза
          </dt>
          <dd class="mt-0.5">
            {{ correctionDosing.lastDoseSummary }}
          </dd>
        </div>
        <div v-if="correctionDosing.cooldownLabel">
          <dt class="uppercase tracking-wide opacity-70">
            Ожидание до повтора
          </dt>
          <dd class="mt-0.5">
            через {{ correctionDosing.cooldownLabel }}
          </dd>
        </div>
        <div v-if="correctionDosing.targetsInTolerance !== null || correctionDosing.workflowReady !== null">
          <dt class="uppercase tracking-wide opacity-70">
            Готовность
          </dt>
          <dd class="mt-0.5">
            <span v-if="correctionDosing.targetsInTolerance !== null">
              В пределах допуска: {{ readinessBoolLabel(correctionDosing.targetsInTolerance) }}
            </span>
            <span
              v-if="correctionDosing.workflowReady !== null"
              :class="correctionDosing.targetsInTolerance !== null ? 'ml-2' : ''"
            >
              Раствор готов: {{ readinessBoolLabel(correctionDosing.workflowReady) }}
            </span>
          </dd>
        </div>
      </dl>
    </div>

    <div
      v-if="prepareBaseline || correctionPipeline"
      class="rounded-lg border border-[color:var(--border-muted)]/70 bg-[color:var(--bg-elevated)] px-3 py-2.5 text-xs space-y-2"
      data-testid="automation-prepare-baseline"
    >
      <p class="font-semibold text-sm text-[color:var(--text-primary)]">
        Исходная вода и приготовление раствора
      </p>
      <dl
        v-if="prepareBaseline"
        class="grid grid-cols-2 gap-1.5 text-[10px]"
      >
        <div>
          <dt class="uppercase tracking-wide opacity-70">
            EC и pH исходной воды
          </dt>
          <dd class="mt-0.5 font-mono">
            {{ formatNullableNumber(prepareBaseline.water_ec) }} /
            {{ formatNullableNumber(prepareBaseline.water_ph) }}
          </dd>
        </div>
        <div>
          <dt class="uppercase tracking-wide opacity-70">
            Добавка EC / целевая EC
          </dt>
          <dd class="mt-0.5 font-mono">
            {{ formatNullableNumber(prepareBaseline.nutrient_ec_budget) }} /
            {{ formatNullableNumber(prepareBaseline.target_ec) }}
          </dd>
        </div>
        <div
          v-if="ratioSummary"
          class="col-span-2"
        >
          <dt class="uppercase tracking-wide opacity-70">
            Соотношение компонентов
          </dt>
          <dd class="mt-0.5 font-mono break-all">
            {{ ratioSummary }}
          </dd>
        </div>
        <div
          v-if="targetSummary"
          class="col-span-2"
        >
          <dt class="uppercase tracking-wide opacity-70">
            Накопительные цели EC по компонентам
          </dt>
          <dd class="mt-0.5 font-mono break-all">
            {{ targetSummary }}
          </dd>
        </div>
      </dl>
      <dl
        v-if="correctionPipeline"
        class="grid grid-cols-2 gap-1.5 text-[10px] pt-1 border-t border-[color:var(--border-muted)]/50"
      >
        <div>
          <dt class="uppercase tracking-wide opacity-70">
            Этап приготовления
          </dt>
          <dd class="mt-0.5 font-mono">
            {{ stageDiagnosticLabel(correctionPipeline.pipeline_phase) }}
            <span v-if="correctionPipeline.active_component">
              · {{ processComponentLabel(correctionPipeline.active_component) }}
            </span>
          </dd>
        </div>
        <div>
          <dt class="uppercase tracking-wide opacity-70">
            Разбавление и регулятор EC
          </dt>
          <dd class="mt-0.5 font-mono">
            попыток: {{ correctionPipeline.dilute_attempts ?? '—' }}
            · регулирование EC приостановлено: {{ correctionPipeline.ec_pid_frozen == null ? 'неизвестно' : correctionPipeline.ec_pid_frozen ? 'да' : 'нет' }}
          </dd>
        </div>
      </dl>
    </div>

    <AutomationFailureDetails :diagnostics="failureDiagnostics" />

    <IrrigationDecisionCard
      :decision="automationState?.irrigation_decision ?? automationState?.decision ?? null"
      :is-stale="automationState?.state_meta?.is_stale"
    />

    <div
      v-if="causalStrip"
      class="rounded-lg border border-[color:var(--border-muted)]/70 bg-[color:var(--bg-elevated)]/55 px-3 py-2.5 text-xs space-y-2"
      data-testid="automation-causal-strip"
    >
      <div class="flex flex-wrap items-center justify-between gap-2">
        <p class="font-semibold text-sm text-[color:var(--text-primary)]">
          Цепочка процесса
        </p>
        <button
          v-if="causalStrip.taskId != null && causalStrip.zoneId != null"
          type="button"
          class="text-[10px] font-semibold uppercase tracking-wide text-[color:var(--status-info)] hover:underline"
          data-testid="automation-causal-events-link"
          @click="openTaskEvents(causalStrip.zoneId, causalStrip.taskId)"
        >
          События задачи
        </button>
      </div>
      <p class="font-mono text-[11px] text-[color:var(--text-primary)] leading-relaxed break-words">
        {{ causalStrip.summary }}
      </p>
      <details v-if="causalStrip.details.length > 0">
        <summary>Технические детали цепочки</summary>
        <ul
          class="space-y-0.5 font-mono text-[10px] text-[color:var(--text-dim)]"
        >
          <li
            v-for="line in causalStrip.details"
            :key="line"
          >
            {{ line }}
          </li>
        </ul>
      </details>
    </div>

    <div
      v-if="taskIdLabel && !failureDiagnostics && !causalStrip"
      class="diag-info-block"
    >
      <span class="font-medium text-[color:var(--text-primary)]">Задача:</span>
      {{ taskIdLabel }}
    </div>

    <div
      v-if="schedulerSummary"
      class="diag-info-block"
    >
      <span class="font-medium text-[color:var(--text-primary)]">Планировщик:</span>
      {{ schedulerSummary }}
    </div>

    <div
      v-if="offlineNodes.length > 0"
      class="rounded-lg border border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] px-3 py-2 text-xs text-[color:var(--badge-warning-text)]"
    >
      <p class="font-medium">
        Узлы без актуальной связи
      </p>
      <p class="mt-1 font-mono text-[11px] break-all">
        {{ offlineNodes.join(', ') }}
      </p>
    </div>

    <p
      v-if="dataSourceLabel"
      class="text-[10px] text-[color:var(--text-dim)]"
    >
      Источник: {{ dataSourceLabel }}
    </p>

    <details
      v-if="automationState"
      class="text-xs text-[color:var(--text-muted)]"
    >
      <summary>Данные задачи для диагностики</summary>
      <dl class="mt-2 space-y-1 break-all">
        <dt>Этап</dt><dd>{{ automationState.current_stage ?? observability?.runtime?.current_stage ?? '—' }}</dd>
        <dt>Фаза</dt><dd>{{ automationState.workflow_phase ?? observability?.runtime?.workflow_phase ?? '—' }}</dd>
        <dt>Этап приготовления</dt><dd>{{ correctionPipeline?.pipeline_phase ?? '—' }}</dd>
        <dt>Источник</dt><dd>{{ observability?.runtime?.source ?? '—' }}</dd>
      </dl>
    </details>
    <SchedulerDispatchMetricsStrip />

    <ul
      v-if="hangHints.length > 0"
      class="space-y-2"
    >
      <li
        v-for="hint in hangHints"
        :key="hint.code"
        class="rounded-lg border px-3 py-2 text-xs"
        :class="hintClass(hint.severity)"
      >
        <p class="font-semibold">
          {{ hint.message }}
        </p>
        <p
          v-if="hint.recommendation"
          class="mt-1 opacity-90"
        >
          {{ hint.recommendation }}
        </p>
        <ul
          v-if="hintDetailLines(hint).length > 0"
          class="mt-1.5 space-y-0.5 font-mono text-[10px] opacity-80"
        >
          <li
            v-for="line in hintDetailLines(hint)"
            :key="line"
          >
            {{ line }}
          </li>
        </ul>
        <p class="mt-1 font-mono text-[10px] opacity-70">
          {{ hint.code }}
        </p>
      </li>
    </ul>

    <p
      v-else-if="observability?.runtime?.task_is_active && !automationState?.state_meta?.is_stale && observability?.runtime?.source !== 'client_fallback'"
      class="text-xs text-[color:var(--text-muted)]"
    >
      В полученном снимке признаков задержки не обнаружено. Это не подтверждает текущую работу оборудования.
    </p>
  </section>
</template>

<script setup lang="ts">
import Badge from '@/Components/Badge.vue'
import IrrigationDecisionCard from './IrrigationDecisionCard.vue'
import AutomationFailureDetails from './AutomationFailureDetails.vue'
import SchedulerDispatchMetricsStrip from './SchedulerDispatchMetricsStrip.vue'
import { useAutomationObservability } from '@/composables/useAutomationObservability'
import { processStageLabel as stageDiagnosticLabel, processComponentLabel } from '@/utils/automationProcessLabels'
import type { AutomationState } from '@/types/Automation'
const props = defineProps<{ automationState: AutomationState | null }>()
const { observability, failureDiagnostics, causalStrip, hangHints, correctionDosing, activeDosesLabel, prepareBaseline, correctionPipeline, ratioSummary, targetSummary, correctionDosingClass, healthLabel, healthBadgeVariant, stageLabel, taskStatusLabel, stageElapsedLabel, deadlineLabel, correctionStep, topologyLabel, pendingManualStepLabel, taskIdLabel, offlineNodes, dataSourceLabel, schedulerSummary, openTaskEvents, formatNullableNumber, readinessBoolLabel, hintClass, hintDetailLines } = useAutomationObservability(props)
</script>

<style scoped>
.diag-tile {
  border-radius: 0.65rem;
  border: 1px solid color-mix(in srgb, var(--border-muted) 85%, transparent);
  background: color-mix(in srgb, var(--bg-elevated) 78%, transparent);
  padding: 0.5rem 0.65rem;
}

.diag-tile dt {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
}

.diag-tile dd {
  margin-top: 0.15rem;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-primary);
  word-break: break-word;
}

.diag-info-block {
  border-radius: 0.65rem;
  border: 1px solid color-mix(in srgb, var(--border-muted) 85%, transparent);
  background: color-mix(in srgb, var(--bg-elevated) 65%, transparent);
  padding: 0.5rem 0.75rem;
  font-size: 0.75rem;
  line-height: 1.4;
  color: var(--text-primary);
}
</style>
