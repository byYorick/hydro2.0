<template>
  <section
    v-if="decision"
    class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-3 py-3 text-xs space-y-3"
    data-testid="automation-decision-card"
  >
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h4 class="font-semibold text-sm text-[color:var(--text-primary)]">
        Последнее решение о поливе
      </h4>
      <Badge :variant="variant">
        {{ irrigationOutcomeLabel(decision.outcome) }}
      </Badge>
    </div>
    <p class="text-[color:var(--text-muted)]">
      {{ irrigationStrategyLabel(decision.strategy) }}
      <span v-if="decision.evaluated_at"> · {{ formatDateTime(decision.evaluated_at) }}</span>
    </p>
    <p>{{ reason.explanation }}</p>
    <p
      v-if="reason.action"
      class="font-medium"
    >
      Что сделать: {{ reason.action }}
    </p>
    <p
      v-if="decision.degraded || decision.outcome === 'degraded_run'"
      class="text-status-warning"
    >
      Пониженная достоверность данных. Решение принято, но измерения или настройки требуют внимания.
    </p>
    <p
      v-if="details.insufficient_samples === true"
      class="text-status-warning"
    >
      Измерений меньше желаемого числа. По текущей политике это не запрещает полив.
    </p>
    <p
      v-if="details.spread_alert === true"
      class="text-status-warning"
    >
      Датчики показывают разную влажность. Проверьте их размещение и калибровку.
    </p>
    <p
      v-if="details.schedule_invalid === true"
      class="text-status-warning"
    >
      Не удалось однозначно выбрать дневную или ночную цель. Проверьте расписание в рецепте.
    </p>
    <p
      v-if="thresholdNeverRuns"
      class="text-status-warning"
    >
      С заданным запасом порог полива равен 0% или ниже. Полив по влажности при таком пороге не разрешится; проверьте цель и запас.
    </p>
    <div
      v-if="temperatureReason"
      class="text-status-warning"
    >
      <p>{{ temperatureReason.explanation }}</p>
      <p v-if="temperatureReason.action">
        Что сделать: {{ temperatureReason.action }}
      </p>
    </div>
    <p
      v-if="facts.length"
      class="text-[color:var(--text-muted)]"
    >
      Данные и пороги на момент принятия решения:
    </p>
    <dl
      v-if="facts.length"
      class="grid grid-cols-1 sm:grid-cols-2 gap-2"
    >
      <div
        v-for="fact in facts"
        :key="fact.label"
      >
        <dt class="text-[color:var(--text-dim)]">
          {{ fact.label }}
        </dt>
        <dd class="font-medium tabular-nums">
          {{ fact.value }}
        </dd>
      </div>
    </dl>
    <p
      v-else
      class="text-[color:var(--text-muted)]"
    >
      {{ decision.outcome ? 'Подробные измерения для этого решения не сохранены.' : 'Задача ожидает проверки условий.' }}
    </p>
    <p class="text-[color:var(--text-muted)]">
      Разрешение полива не подтверждает подачу воды. Ход выполнения и ответы оборудования показаны в текущем процессе и журнале событий.
    </p>
    <p
      v-if="isStale"
      class="text-status-warning"
    >
      Состояние автоматики из кэша. Последнее решение не подтверждает текущее состояние оборудования.
    </p>
    <details class="text-[color:var(--text-dim)]">
      <summary class="cursor-pointer">
        Технические данные решения
      </summary>
      <div class="mt-2 space-y-1 font-mono break-all">
        <div v-if="decision.task_id">
          Задача: {{ decision.task_id }} · {{ decision.task_status }}
        </div>
        <div>Результат: {{ decision.outcome ?? '—' }}</div>
        <div>Стратегия: {{ decision.strategy ?? '—' }}</div>
        <div>Код причины: {{ decision.reason_code ?? '—' }}</div>
        <div>Пониженная достоверность (degraded): {{ decision.degraded == null ? 'неизвестно' : decision.degraded ? 'да' : 'нет' }}</div>
        <div v-if="decision.bundle_revision">
          Версия настроек: {{ decision.bundle_revision }}
        </div>
        <div v-if="decision.config">
          Настройки задачи: {{ decision.config }}
        </div>
      </div>
    </details>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/Components/Badge.vue'
import type { IrrigationDecisionEvidence } from '@/types/Automation'
import { formatDateTime } from '@/utils/simulationFormatters'
import { decisionNumber, irrigationDecisionFacts, irrigationOutcomeLabel, irrigationReasonPresentation, irrigationStrategyLabel } from '@/utils/irrigationDecisionView'

const props = defineProps<{ decision: IrrigationDecisionEvidence | null; isStale?: boolean }>()
const details = computed(() => props.decision?.details ?? {})
const reason = computed(() => irrigationReasonPresentation(props.decision?.reason_code))
const facts = computed(() => props.decision ? irrigationDecisionFacts(props.decision) : [])
const thresholdNeverRuns = computed(() => {
  const threshold = decisionNumber(details.value.run_below_pct)
  return threshold !== null && threshold <= 0
})
const temperatureReason = computed(() => {
  const temp = details.value.solution_temp
  return temp && typeof temp === 'object' && 'reason_code' in temp
    ? irrigationReasonPresentation(temp.reason_code) : null
})
const variant = computed(() => props.decision?.outcome === 'fail' || props.decision?.reason_code === 'solution_temp_hot_stop' ? 'danger'
  : props.decision?.degraded || props.decision?.outcome === 'degraded_run' ? 'warning' : props.decision?.outcome === 'run' ? 'info' : 'neutral')
</script>
