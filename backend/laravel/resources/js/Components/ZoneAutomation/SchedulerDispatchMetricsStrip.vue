<template>
  <section
    class="surface-card p-3 text-xs space-y-2"
    data-testid="scheduler-dispatch-metrics-strip"
  >
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h4 class="font-semibold">
        Диспетчер задач · вся система
      </h4>
      <Button
        size="sm"
        variant="ghost"
        :disabled="loading"
        @click="refresh"
      >
        {{ loading ? 'Обновление…' : 'Обновить данные' }}
      </Button>
    </div>
    <p
      v-if="loading && !metrics"
      role="status"
    >
      Загрузка состояния диспетчера…
    </p>
    <p
      v-if="error"
      role="alert"
      class="text-status-warning"
    >
      {{ error }} <span v-if="metrics">Ниже показаны последние полученные данные; они могут быть устаревшими.</span>
    </p>
    <template v-if="metrics">
      <p :class="snapshot?.cycle_observation === 'recent' && snapshot?.dispatch_token_configured !== false ? 'text-[color:var(--text-muted)]' : 'text-status-warning'">
        {{ observation }}
      </p>
      <dl class="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <dt>Запросов, ожидающих приёма в работу</dt><dd class="text-lg font-semibold">
            {{ metrics.pendingIntents ?? '—' }}
          </dd>
        </div>
        <div>
          <dt>Возраст самого старого запроса</dt><dd class="text-lg font-semibold">
            {{ seconds(metrics.oldestPendingAgeSec) }}
          </dd>
        </div>
        <div>
          <dt>Превышение интервала обхода (p99)</dt><dd class="text-lg font-semibold">
            {{ seconds(metrics.dispatchCycleOverrunSec) }}
          </dd>
        </div>
      </dl>
      <p class="text-[color:var(--text-muted)]">
        Ожидание запроса не подтверждает его запуск. Показатели общие для всех зон; причины конкретной задачи смотрите в её истории.
      </p>
      <p
        v-if="snapshot?.last_cycle_at"
        class="text-[color:var(--text-muted)]"
      >
        Последний записанный обход: {{ formatDateTime(snapshot.last_cycle_at) }}. Это наблюдение, а не проверка текущей связи с оборудованием.
      </p>
      <details class="text-[color:var(--text-muted)]">
        <summary>Как читать показатели</summary>
        <p>Обход — одна проверка расписаний и ожидающих задач.</p>
        <p>p99 — оценка длительности обхода, которую не превышали около 99% записанных циклов. Превышение сравнивается с заданным интервалом {{ snapshot?.dispatch_interval_sec ?? '—' }} сек; оно не является задержкой конкретной задачи.</p>
        <p>Обновлено: {{ formatDateTime(refreshedAt) }}. Нет значения — нет наблюдения; ноль — наблюдаемое нулевое значение.</p>
      </details>
    </template>
  </section>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import Button from '@/Components/Button.vue'
import { useSchedulerDispatchMetrics } from '@/composables/useSchedulerDispatchMetrics'
import { formatDateTime } from '@/utils/schedulerLabels'
const { metrics, snapshot, loading, error, refreshedAt, refresh } = useSchedulerDispatchMetrics()
const observation = computed(() => {
  if (snapshot?.value?.enabled && snapshot.value.dispatch_token_configured === false) return 'У диспетчера не настроен доступ к службе выполнения. Обратитесь к администратору.'
  const labels: Record<string, string> = {
    disabled: 'Автоматический диспетчер выключен в настройках системы.',
    not_observed: 'Записанных обходов пока нет. Проверьте запуск диспетчера и его журнал.',
    delayed: 'Нового записанного обхода нет дольше двух интервалов. Проверьте службу планировщика и журнал ошибок.',
    recent: 'Есть недавний записанный обход диспетчера.',
  }
  return labels[snapshot?.value?.cycle_observation ?? 'not_observed'] ?? 'Состояние диспетчера не распознано. Проверьте журнал.'
})
function seconds(value: number | null) { return typeof value === 'number' && Number.isFinite(value) ? `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value)} сек` : '—' }
</script>
