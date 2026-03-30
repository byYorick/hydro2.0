<template>
  <div class="space-y-6">
    <section class="surface-card surface-card--elevated rounded-[1.5rem] border border-[color:var(--border-muted)] p-4 md:p-5">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-[11px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-dim)]">
              Scheduler Workspace · зона #{{ zoneId }}
            </span>
            <Badge variant="info">Live sync</Badge>
            <Badge :variant="statusVariant(activeRun ? 'running' : 'accepted')">
              {{ controlModeLabel(workspace?.control?.control_mode) }}
            </Badge>
            <Badge variant="secondary">
              {{ horizon.toUpperCase() }}
            </Badge>
          </div>
          <h3 class="mt-2 font-headline text-2xl font-bold tracking-tight text-[color:var(--text-primary)]">
            Планировщик зоны
          </h3>
          <p class="mt-1 text-sm text-[color:var(--text-dim)]">
            Краткая операторская сводка: что происходит сейчас, что требует внимания и какие окна реально исполнимы.
          </p>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            :variant="horizon === '24h' ? 'secondary' : 'outline'"
            @click="changeHorizon('24h')"
          >
            24h
          </Button>
          <Button
            size="sm"
            :variant="horizon === '7d' ? 'secondary' : 'outline'"
            @click="changeHorizon('7d')"
          >
            7d
          </Button>
          <Button
            size="sm"
            variant="outline"
            :disabled="loading"
            @click="refreshWorkspace"
          >
            {{ loading ? 'Обновляем...' : 'Обновить' }}
          </Button>
        </div>
      </div>

      <div class="mt-4 flex flex-wrap gap-2">
        <Badge variant="info">Активно {{ executionCounters.active }}</Badge>
        <Badge variant="secondary">Успешно 24ч {{ executionCounters.completed_24h }}</Badge>
        <Badge variant="danger">Ошибок 24ч {{ executionCounters.failed_24h }}</Badge>
        <Badge variant="secondary">Исполнимых окон {{ nextExecutableWindows.length }}</Badge>
      </div>

      <p
        v-if="error"
        class="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
      >
        {{ error }}
      </p>
    </section>

    <div class="grid gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
      <div class="space-y-6">
        <section class="surface-card surface-card--elevated rounded-[1.5rem] border border-[color:var(--border-muted)] p-4 md:p-5">
          <div class="flex items-center justify-between gap-3">
            <div>
              <h4 class="font-headline text-lg font-bold text-[color:var(--text-primary)]">Что происходит сейчас</h4>
              <p class="text-sm text-[color:var(--text-dim)]">
                Снимок фактического состояния зоны из canonical automation state.
              </p>
            </div>
            <div class="text-xs text-[color:var(--text-muted)]">
              Sync: {{ updatedAt ? formatDateTime(updatedAt) : '—' }}
            </div>
          </div>

          <div class="mt-4 rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/20 p-4">
            <div class="flex flex-wrap items-center gap-2">
              <Badge :variant="activeRun ? statusVariant(activeRun.status) : 'secondary'">
                {{ activeRun ? activeRun.status : 'idle' }}
              </Badge>
              <Badge variant="secondary">
                {{ controlModeLabel(automationState?.control_mode || workspace?.control?.control_mode) }}
              </Badge>
              <Badge
                v-if="automationState?.decision?.outcome"
                :variant="decisionVariant(automationState.decision.outcome, automationState.decision.degraded)"
              >
                {{ decisionLabel(automationState.decision.outcome, automationState.decision.degraded) }}
              </Badge>
            </div>

            <p class="mt-3 text-lg font-semibold text-[color:var(--text-primary)]">
              {{ automationState?.state_label || (activeRun ? laneLabel(activeRun.task_type) : 'Ожидание следующего запуска') }}
            </p>
            <p class="mt-1 text-sm text-[color:var(--text-dim)]">
              Этап: {{ automationState?.current_stage || activeRun?.current_stage || 'не передан' }}
            </p>
            <p class="mt-1 text-sm text-[color:var(--text-dim)]">
              Фаза: {{ automationState?.workflow_phase || activeRun?.workflow_phase || 'не передана' }}
            </p>
            <p
              v-if="automationState?.decision?.reason_code"
              class="mt-1 text-sm text-[color:var(--text-dim)]"
            >
              Decision: {{ automationState.decision.reason_code }}
            </p>

            <div
              v-if="activeProcessLabels.length > 0"
              class="mt-3 flex flex-wrap gap-2"
            >
              <Badge
                v-for="label in activeProcessLabels"
                :key="label"
                variant="info"
              >
                {{ label }}
              </Badge>
            </div>

            <p
              v-else
              class="mt-3 text-xs text-[color:var(--text-muted)]"
            >
              Активные подпроцессы не зафиксированы.
            </p>
          </div>
        </section>

        <section class="surface-card surface-card--elevated rounded-[1.5rem] border border-[color:var(--border-muted)] p-4 md:p-5">
          <div>
            <h4 class="font-headline text-lg font-bold text-[color:var(--text-primary)]">Требует внимания</h4>
            <p class="text-sm text-[color:var(--text-dim)]">
              Короткие сигналы для оператора без raw scheduler timeline.
            </p>
          </div>

          <div
            v-if="attentionItems.length === 0"
            class="mt-4 rounded-xl border border-dashed border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 p-4 text-sm text-[color:var(--text-dim)]"
          >
            Критичных сигналов нет.
          </div>

          <div
            v-else
            class="mt-4 space-y-3"
          >
            <article
              v-for="(item, index) in attentionItems"
              :key="`${item.title}-${index}`"
              class="rounded-2xl border px-4 py-4"
              :class="attentionCardClass(item.tone)"
            >
              <p class="text-sm font-semibold text-[color:var(--text-primary)]">
                {{ item.title }}
              </p>
              <p
                v-if="item.detail"
                class="mt-1 text-xs text-[color:var(--text-dim)]"
              >
                {{ item.detail }}
              </p>
            </article>
          </div>
        </section>

        <section class="surface-card surface-card--elevated rounded-[1.5rem] border border-[color:var(--border-muted)] p-4 md:p-5">
          <div class="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div>
              <h4 class="font-headline text-lg font-bold text-[color:var(--text-primary)]">Ближайшие исполнимые окна</h4>
              <p class="text-sm text-[color:var(--text-dim)]">
                Показываем только окна task types, которые runtime действительно умеет исполнять.
              </p>
            </div>
            <div class="text-xs text-[color:var(--text-muted)]">
              Timezone: {{ workspace?.control?.timezone || 'UTC' }}
            </div>
          </div>

          <div
            v-if="nextExecutableWindows.length === 0"
            class="mt-4 rounded-xl border border-dashed border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 p-4 text-sm text-[color:var(--text-dim)]"
          >
            На выбранном горизонте нет исполнимых окон.
          </div>

          <div
            v-else
            class="mt-4 space-y-3"
          >
            <article
              v-for="window in nextExecutableWindows"
              :key="window.plan_window_id"
              class="rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/20 px-4 py-4"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <p class="text-sm font-semibold text-[color:var(--text-primary)]">
                    {{ formatDateTime(window.trigger_at) }}
                  </p>
                  <p class="mt-1 text-xs text-[color:var(--text-dim)]">
                    {{ formatRelativeTrigger(window.trigger_at) }} · {{ laneLabel(window.task_type) }} · {{ window.mode }}
                  </p>
                </div>
                <Badge variant="success">{{ laneLabel(window.task_type) }}</Badge>
              </div>
            </article>
          </div>

          <div
            v-if="configOnlyLanes.length > 0"
            class="mt-5 rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/15 p-4"
          >
            <p class="text-sm font-semibold text-[color:var(--text-primary)]">Сконфигурировано, но не исполняется этим runtime</p>
            <div class="mt-3 flex flex-wrap gap-2">
              <Badge
                v-for="lane in configOnlyLanes"
                :key="lane.task_type"
                variant="secondary"
              >
                {{ lane.label }}
              </Badge>
            </div>
          </div>
        </section>
      </div>

      <div class="space-y-6">
        <section class="surface-card surface-card--elevated rounded-[1.5rem] border border-[color:var(--border-muted)] p-4 md:p-5">
          <div class="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
            <div>
              <h4 class="font-headline text-lg font-bold text-[color:var(--text-primary)]">Исполнения</h4>
              <p class="text-sm text-[color:var(--text-dim)]">
                Активный run и недавняя история по каноническим `ae_tasks`.
              </p>
            </div>
            <div class="text-xs text-[color:var(--text-muted)]">
              Runtime: {{ workspace?.control?.automation_runtime ?? '—' }}
            </div>
          </div>

          <div class="mt-4 grid gap-3">
            <div class="rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 p-4">
              <div class="flex flex-wrap items-center gap-2">
                <Badge :variant="activeRun ? statusVariant(activeRun.status) : 'secondary'">
                  {{ activeRun ? activeRun.status : 'idle' }}
                </Badge>
                <span class="text-sm font-semibold text-[color:var(--text-primary)]">
                  {{ activeRun ? `#${activeRun.execution_id}` : 'Активного run нет' }}
                </span>
              </div>
              <p class="mt-2 text-sm text-[color:var(--text-dim)]">
                {{ activeRun ? `${laneLabel(activeRun.task_type)} · ${activeRun.current_stage || 'stage не передан'}` : 'Ожидание следующего wake-up.' }}
              </p>
              <div
                v-if="activeRun?.decision_outcome"
                class="mt-2 flex flex-wrap gap-2"
              >
                <Badge :variant="decisionVariant(activeRun.decision_outcome, activeRun.decision_degraded)">
                  {{ decisionLabel(activeRun.decision_outcome, activeRun.decision_degraded) }}
                </Badge>
                <Badge
                  v-if="activeRun.decision_reason_code"
                  variant="secondary"
                >
                  {{ activeRun.decision_reason_code }}
                </Badge>
              </div>
              <p
                v-if="activeRun?.scheduled_for"
                class="mt-1 text-xs text-[color:var(--text-muted)]"
              >
                planned: {{ formatDateTime(activeRun.scheduled_for) }}
              </p>
            </div>

            <div class="rounded-2xl border border-[color:var(--border-muted)] p-4">
              <div class="flex items-center justify-between gap-3">
                <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">Недавние run</h5>
                <span class="text-xs text-[color:var(--text-muted)]">{{ recentRuns.length }} записей</span>
              </div>

              <div
                v-if="recentRuns.length === 0"
                class="mt-3 text-sm text-[color:var(--text-dim)]"
              >
                Исполнения ещё не зафиксированы.
              </div>

              <div
                v-else
                class="mt-3 space-y-2"
              >
                <button
                  v-for="run in recentRuns"
                  :key="run.execution_id"
                  type="button"
                  class="flex w-full items-center justify-between gap-3 rounded-xl border px-3 py-3 text-left transition-colors"
                  :class="selectedExecution?.execution_id === run.execution_id
                    ? 'border-[color:var(--accent,#0ea5e9)] bg-[color:var(--surface-card)]/55'
                    : 'border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 hover:bg-[color:var(--surface-card)]/45'"
                  @click="fetchExecution(run.execution_id)"
                >
                  <div class="min-w-0">
                    <div class="flex flex-wrap items-center gap-2">
                      <span class="font-mono text-sm font-semibold text-[color:var(--text-primary)]">#{{ run.execution_id }}</span>
                      <Badge :variant="statusVariant(run.status)">{{ run.status }}</Badge>
                      <Badge
                        v-if="run.decision_outcome"
                        :variant="decisionVariant(run.decision_outcome, run.decision_degraded)"
                      >
                        {{ decisionLabel(run.decision_outcome, run.decision_degraded) }}
                      </Badge>
                      <span class="text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-dim)]">
                        {{ laneLabel(run.task_type) }}
                      </span>
                    </div>
                    <p class="mt-1 text-xs text-[color:var(--text-muted)]">
                      {{ formatDateTime(run.updated_at || run.created_at || null) }}
                    </p>
                  </div>
                  <span class="shrink-0 text-xs text-[color:var(--text-dim)]">
                    {{ run.current_stage || run.workflow_phase || '—' }}
                  </span>
                </button>
              </div>
            </div>
          </div>
        </section>

        <section class="surface-card surface-card--elevated rounded-[1.5rem] border border-[color:var(--border-muted)] p-4 md:p-5">
          <div class="flex items-center justify-between gap-3">
            <div>
              <h4 class="font-headline text-lg font-bold text-[color:var(--text-primary)]">Детали run</h4>
              <p class="text-sm text-[color:var(--text-dim)]">
                Сжатый timeline без мусорных повторов `AE_TASK_STARTED`.
              </p>
            </div>
            <Badge :variant="selectedExecution ? statusVariant(selectedExecution.status) : 'secondary'">
              {{ selectedExecution ? selectedExecution.status : '—' }}
            </Badge>
          </div>

          <div
            v-if="detailLoading"
            class="mt-4 text-sm text-[color:var(--text-dim)]"
          >
            Загружаем детали выполнения...
          </div>

          <div
            v-else-if="!selectedExecution"
            class="mt-4 rounded-xl border border-dashed border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 p-4 text-sm text-[color:var(--text-dim)]"
          >
            Выберите run справа, чтобы посмотреть lifecycle и timeline.
          </div>

          <div
            v-else
            class="mt-4 space-y-4"
          >
            <div class="grid gap-3 md:grid-cols-2">
              <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 p-4">
                <p class="text-[10px] font-bold uppercase tracking-[0.18em] text-[color:var(--text-dim)]">Run</p>
                <p class="mt-1 text-sm font-semibold text-[color:var(--text-primary)]">#{{ selectedExecution.execution_id }}</p>
                <p class="mt-1 text-xs text-[color:var(--text-muted)]">
                  {{ laneLabel(selectedExecution.task_type) }} · {{ selectedExecution.current_stage || 'stage не передан' }}
                </p>
                <div
                  v-if="selectedExecution.decision_outcome"
                  class="mt-2 flex flex-wrap gap-2"
                >
                  <Badge :variant="decisionVariant(selectedExecution.decision_outcome, selectedExecution.decision_degraded)">
                    {{ decisionLabel(selectedExecution.decision_outcome, selectedExecution.decision_degraded) }}
                  </Badge>
                  <Badge
                    v-if="selectedExecution.decision_reason_code"
                    variant="secondary"
                  >
                    {{ selectedExecution.decision_reason_code }}
                  </Badge>
                </div>
              </div>
              <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 p-4">
                <p class="text-[10px] font-bold uppercase tracking-[0.18em] text-[color:var(--text-dim)]">Время</p>
                <p class="mt-1 text-sm font-semibold text-[color:var(--text-primary)]">
                  updated {{ formatDateTime(selectedExecution.updated_at || selectedExecution.created_at || null) }}
                </p>
                <p class="mt-1 text-xs text-[color:var(--text-muted)]">
                  planned {{ formatDateTime(selectedExecution.scheduled_for || null) }}
                </p>
                <p
                  v-if="selectedExecution.irrigation_mode || selectedExecution.decision_strategy"
                  class="mt-1 text-xs text-[color:var(--text-dim)]"
                >
                  {{ selectedExecution.irrigation_mode ? `mode ${selectedExecution.irrigation_mode}` : '' }}
                  {{ selectedExecution.irrigation_mode && selectedExecution.decision_strategy ? ' · ' : '' }}
                  {{ selectedExecution.decision_strategy ? `strategy ${selectedExecution.decision_strategy}` : '' }}
                </p>
              </div>
            </div>

            <div
              v-if="selectedExecutionErrorMessage"
              class="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
            >
              {{ selectedExecutionErrorMessage }}
            </div>

            <div
              v-if="selectedExecution.lifecycle && selectedExecution.lifecycle.length > 0"
              class="rounded-xl border border-[color:var(--border-muted)] p-4"
            >
              <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">Lifecycle</h5>
              <div class="mt-3 space-y-2">
                <div
                  v-for="(item, index) in selectedExecution.lifecycle"
                  :key="`${selectedExecution.execution_id}-lifecycle-${index}`"
                  class="flex items-center justify-between gap-3 text-sm"
                >
                  <div class="flex items-center gap-2">
                    <Badge :variant="statusVariant(item.status)">{{ item.status }}</Badge>
                    <span class="text-[color:var(--text-primary)]">{{ item.source || 'runtime' }}</span>
                  </div>
                  <span class="text-xs text-[color:var(--text-muted)]">{{ formatDateTime(item.at) }}</span>
                </div>
              </div>
            </div>

            <div class="rounded-xl border border-[color:var(--border-muted)] p-4">
              <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">Timeline</h5>
              <div
                v-if="condensedTimeline.length === 0"
                class="mt-3 text-sm text-[color:var(--text-dim)]"
              >
                Timeline для этого run пока пустой.
              </div>
              <div
                v-else
                class="mt-3 space-y-3"
              >
                <div
                  v-for="item in condensedTimeline"
                  :key="item.key"
                  class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/20 px-3 py-3"
                >
                  <div class="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <div class="flex flex-wrap items-center gap-2">
                      <Badge variant="info">{{ item.event_type }}</Badge>
                      <span class="text-sm font-medium text-[color:var(--text-primary)]">
                        {{ item.label }}
                      </span>
                      <span
                        v-if="item.grouped"
                        class="text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-muted)]"
                      >
                        grouped
                      </span>
                    </div>
                    <span class="text-xs text-[color:var(--text-muted)]">{{ formatDateTime(item.at) }}</span>
                  </div>
                  <p
                    v-if="item.detail"
                    class="mt-2 text-xs text-[color:var(--text-dim)]"
                  >
                    {{ item.detail }}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>

    <section
      v-if="canDiagnose && workspace?.capabilities?.diagnostics_available"
      class="surface-card surface-card--elevated rounded-[1.5rem] border border-[color:var(--border-muted)] p-4 md:p-5"
    >
      <div class="flex items-center justify-between gap-3">
        <div>
          <h4 class="font-headline text-lg font-bold text-[color:var(--text-primary)]">Инженерная диагностика</h4>
          <p class="text-sm text-[color:var(--text-dim)]">
            Отдельный diagnostics path для dispatcher state и `scheduler_logs`, без влияния на operator contract.
          </p>
        </div>
        <Badge variant="secondary">engineer/admin</Badge>
      </div>

      <p
        v-if="diagnosticsError"
        class="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700"
      >
        {{ diagnosticsError }}
      </p>

      <div
        v-else-if="diagnosticsLoading && !diagnostics"
        class="mt-4 text-sm text-[color:var(--text-dim)]"
      >
        Загружаем диагностику...
      </div>

      <div
        v-else-if="diagnostics"
        class="mt-4 space-y-4"
      >
        <div class="flex flex-wrap gap-2">
          <Badge variant="info">tracked {{ diagnostics.summary.tracked_tasks_total }}</Badge>
          <Badge variant="success">active {{ diagnostics.summary.active_tasks_total }}</Badge>
          <Badge variant="warning">overdue {{ diagnostics.summary.overdue_tasks_total }}</Badge>
          <Badge variant="danger">stale {{ diagnostics.summary.stale_tasks_total }}</Badge>
          <Badge variant="secondary">logs {{ diagnostics.summary.recent_logs_total }}</Badge>
        </div>

        <div class="grid gap-4 xl:grid-cols-2">
          <div class="rounded-xl border border-[color:var(--border-muted)] p-4">
            <div class="flex items-center justify-between gap-3">
              <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">Dispatcher tasks</h5>
              <span class="text-xs text-[color:var(--text-muted)]">{{ diagnostics.dispatcher_tasks.length }} записей</span>
            </div>
            <div
              v-if="diagnostics.dispatcher_tasks.length === 0"
              class="mt-3 text-sm text-[color:var(--text-dim)]"
            >
              Dispatcher state для зоны пуст.
            </div>
            <div
              v-else
              class="mt-3 space-y-2"
            >
              <div
                v-for="task in diagnostics.dispatcher_tasks"
                :key="task.task_id"
                class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/20 px-3 py-3"
              >
                <div class="flex flex-wrap items-center gap-2">
                  <span class="font-mono text-sm font-semibold text-[color:var(--text-primary)]">{{ task.task_id }}</span>
                  <Badge :variant="statusVariant(task.status)">{{ task.status || 'unknown' }}</Badge>
                  <span class="text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-dim)]">
                    {{ laneLabel(task.task_type) }}
                  </span>
                </div>
                <p class="mt-1 text-xs text-[color:var(--text-muted)]">
                  {{ task.schedule_key || 'schedule_key не передан' }}
                </p>
                <p class="mt-1 text-xs text-[color:var(--text-dim)]">
                  due {{ formatDateTime(task.due_at) }} · poll {{ formatDateTime(task.last_polled_at) }}
                </p>
              </div>
            </div>
          </div>

          <div class="rounded-xl border border-[color:var(--border-muted)] p-4">
            <div class="flex items-center justify-between gap-3">
              <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">Scheduler logs</h5>
              <span class="text-xs text-[color:var(--text-muted)]">{{ diagnostics.recent_logs.length }} записей</span>
            </div>
            <div
              v-if="diagnostics.recent_logs.length === 0"
              class="mt-3 text-sm text-[color:var(--text-dim)]"
            >
              Исторические scheduler logs для зоны не найдены.
            </div>
            <div
              v-else
              class="mt-3 space-y-2"
            >
              <div
                v-for="log in diagnostics.recent_logs"
                :key="log.log_id"
                class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/20 px-3 py-3"
              >
                <div class="flex flex-wrap items-center gap-2">
                  <span class="font-mono text-sm font-semibold text-[color:var(--text-primary)]">{{ log.task_name || 'scheduler' }}</span>
                  <Badge :variant="statusVariant(log.status)">{{ log.status || 'unknown' }}</Badge>
                </div>
                <p class="mt-1 text-xs text-[color:var(--text-dim)]">
                  {{ formatDateTime(log.created_at) }}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import { useApi } from '@/composables/useApi'
import { useRole } from '@/composables/useRole'
import { useToast } from '@/composables/useToast'
import { useZoneScheduleWorkspace } from '@/composables/useZoneScheduleWorkspace'
import { resolveHumanErrorMessage } from '@/utils/errorCatalog'
import type { ZoneAutomationTabProps } from '@/composables/zoneAutomationTypes'

const props = defineProps<ZoneAutomationTabProps>()

const { showToast } = useToast()
const { get } = useApi(showToast)
const { canDiagnose } = useRole()
const {
  horizon,
  workspace,
  automationState,
  selectedExecution,
  diagnostics,
  loading,
  detailLoading,
  diagnosticsLoading,
  error,
  diagnosticsError,
  updatedAt,
  recentRuns,
  activeRun,
  executionCounters,
  nextExecutableWindows,
  configOnlyLanes,
  activeProcessLabels,
  attentionItems,
  condensedTimeline,
  fetchWorkspace,
  fetchAutomationState,
  fetchExecution,
  fetchDiagnostics,
  setHorizon,
  clearDiagnostics,
  clearPollTimer,
  schedulePoll,
  handleVisibilityChange,
  formatDateTime,
  formatRelativeTrigger,
  statusVariant,
  controlModeLabel,
  laneLabel,
} = useZoneScheduleWorkspace(props, { get, showToast })

const zoneId = computed(() => props.zoneId)
const selectedExecutionErrorMessage = computed(() => resolveHumanErrorMessage({
  code: selectedExecution.value?.error_code,
  message: selectedExecution.value?.error_message,
  humanMessage: selectedExecution.value?.human_error_message,
}))

function attentionCardClass(tone: 'danger' | 'warning' | 'info'): string {
  if (tone === 'danger') return 'border-red-200 bg-red-50/70'
  if (tone === 'warning') return 'border-amber-200 bg-amber-50/70'
  return 'border-sky-200 bg-sky-50/70'
}

function decisionLabel(outcome: string | null | undefined, degraded: boolean | null | undefined): string {
  const normalized = String(outcome ?? '').trim().toLowerCase()
  if (normalized === 'skip') return 'skip'
  if (normalized === 'degraded_run') return degraded ? 'degraded run' : 'run'
  if (normalized === 'run') return degraded ? 'degraded run' : 'run'
  if (normalized === 'fail') return 'decision fail'
  return normalized || 'decision'
}

function decisionVariant(
  outcome: string | null | undefined,
  degraded: boolean | null | undefined,
): 'success' | 'warning' | 'danger' | 'info' | 'secondary' {
  const normalized = String(outcome ?? '').trim().toLowerCase()
  if (normalized === 'skip') return 'secondary'
  if (normalized === 'fail') return 'danger'
  if (degraded) return 'warning'
  if (normalized === 'run' || normalized === 'degraded_run') return 'info'
  return 'secondary'
}

function changeHorizon(nextHorizon: '24h' | '7d'): void {
  if (horizon.value === nextHorizon) return
  setHorizon(nextHorizon)
  void refreshWorkspace()
}

async function refreshWorkspace(): Promise<void> {
  await Promise.all([
    fetchWorkspace(),
    fetchAutomationState({ silent: true }),
  ])

  if (canDiagnose.value && workspace.value?.capabilities?.diagnostics_available) {
    await fetchDiagnostics({ silent: true })
  } else {
    clearDiagnostics()
  }

  schedulePoll()
}

onMounted(() => {
  void refreshWorkspace()
  if (import.meta.env.MODE !== 'test' && typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', handleVisibilityChange)
  }
})

onUnmounted(() => {
  clearPollTimer()
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', handleVisibilityChange)
  }
})

watch(
  () => props.zoneId,
  () => {
    void refreshWorkspace()
  }
)
</script>
