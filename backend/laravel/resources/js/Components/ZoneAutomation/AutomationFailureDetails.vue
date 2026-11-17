<template>
  <div
    v-if="diagnostics"
    class="rounded-lg border px-3 py-2.5 text-xs space-y-2"
    :class="diagnostics.isActiveFailure
      ? 'border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)] text-[color:var(--badge-danger-text)]'
      : 'border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] text-[color:var(--badge-warning-text)]'"
    data-testid="automation-fsm-failure-details"
  >
    <p class="font-semibold text-sm">
      {{ diagnostics.title }}
    </p>
    <p
      v-if="diagnostics.summary"
      class="leading-relaxed"
    >
      {{ diagnostics.summary }}
    </p>
    <dl class="grid grid-cols-1 sm:grid-cols-2 gap-2">
      <div v-if="diagnostics.errorCode">
        <dt class="text-[10px] uppercase tracking-wide opacity-75">
          Код ошибки
        </dt>
        <dd class="mt-0.5 font-mono text-[11px] break-all">
          {{ diagnostics.errorCode }}
        </dd>
      </div>
      <div v-if="diagnostics.failedStageLabel">
        <dt class="text-[10px] uppercase tracking-wide opacity-75">
          Этап сбоя
        </dt>
        <dd class="mt-0.5 font-medium">
          {{ diagnostics.failedStageLabel }}
          <span
            v-if="diagnostics.failedStage"
            class="block font-mono text-[10px] opacity-80"
          >
            {{ diagnostics.failedStage }}
          </span>
        </dd>
      </div>
      <div v-if="diagnostics.taskId">
        <dt class="text-[10px] uppercase tracking-wide opacity-75">
          Задача
        </dt>
        <dd class="mt-0.5 font-mono text-[11px]">
          #{{ diagnostics.taskId }}
        </dd>
      </div>
      <div v-if="diagnostics.failedAt">
        <dt class="text-[10px] uppercase tracking-wide opacity-75">
          Время сбоя
        </dt>
        <dd class="mt-0.5">
          {{ formatDateTime(diagnostics.failedAt) }}
        </dd>
      </div>
      <div v-if="diagnostics.workflowPhase">
        <dt class="text-[10px] uppercase tracking-wide opacity-75">
          Фаза workflow
        </dt>
        <dd class="mt-0.5 font-mono text-[11px]">
          {{ diagnostics.workflowPhase }}
        </dd>
      </div>
    </dl>
    <p
      v-if="diagnostics.technicalMessage"
      class="font-mono text-[10px] leading-relaxed opacity-85 break-words"
    >
      {{ diagnostics.technicalMessage }}
    </p>
    <p
      v-if="diagnostics.isHistoricalFailure"
      class="text-[10px] opacity-80"
    >
      Это сведения о завершившемся сбое; они не подтверждают текущую неисправность оборудования.
    </p>
  </div>
</template>
<script setup lang="ts">
import { formatDateTime } from '@/utils/simulationFormatters'
import { resolveAutomationFailureDiagnostics } from '@/utils/automationFailureDiagnostics'
defineProps<{ diagnostics: ReturnType<typeof resolveAutomationFailureDiagnostics> }>()
</script>
