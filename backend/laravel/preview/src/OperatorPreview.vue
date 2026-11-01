<template>
  <div class="mx-auto max-w-5xl space-y-8 p-4 md:p-6">
    <section
      data-screen="dashboard"
      class="space-y-4"
    >
      <PageHeader
        title="Сегодня"
        subtitle="Смена оператора. Живые pH, EC и климат по зонам."
        eyebrow="обзор"
      >
        <template #actions>
          <Button
            size="sm"
            variant="secondary"
          >
            Фазы и рецепты
          </Button>
          <Button size="sm">
            Запустить цикл
          </Button>
        </template>
      </PageHeader>
      <div class="ui-kpi-grid grid-cols-2 md:grid-cols-4">
        <div class="ui-kpi-card">
          <div class="ui-kpi-label">
            Зоны
          </div>
          <div class="ui-kpi-value text-status-ok">
            6<span class="text-base text-[color:var(--text-muted)]"> / 4</span>
          </div>
          <div class="ui-kpi-hint">
            Всего / в работе
          </div>
        </div>
        <div class="ui-kpi-card">
          <div class="ui-kpi-label">
            pH
          </div>
          <div class="ui-kpi-value text-status-ok">
            5.84
          </div>
          <div class="ui-kpi-hint">
            Салат A · цель 5.8–6.0
          </div>
        </div>
        <div class="ui-kpi-card">
          <div class="ui-kpi-label">
            EC
          </div>
          <div class="ui-kpi-value text-status-warning">
            1.92
          </div>
          <div class="ui-kpi-hint">
            мСм/см · близко к верхней границе
          </div>
        </div>
        <div class="ui-kpi-card border border-[color:var(--status-critical)]">
          <div class="ui-kpi-label text-status-critical">
            Тревоги
          </div>
          <div class="ui-kpi-value text-status-critical">
            2
          </div>
          <div class="ui-kpi-hint">
            1 критическая
          </div>
        </div>
      </div>
    </section>

    <section
      data-screen="zone"
      class="surface-card space-y-3 p-4"
    >
      <p class="text-xs text-[color:var(--text-muted)]">
        Блок 1 / Зоны
      </p>
      <div class="flex flex-wrap items-center gap-2">
        <h2 class="text-lg font-semibold">
          Салат A
        </h2>
        <Badge variant="ok">
          В норме
        </Badge>
        <StatusPill tone="warning">
          EC внимание
        </StatusPill>
      </div>
      <div class="grid grid-cols-3 gap-2">
        <div class="rounded-xl border border-[color:var(--border-muted)] p-3">
          <div class="text-[10px] uppercase tracking-wider text-[color:var(--text-dim)]">
            pH
          </div>
          <div class="telemetry-value text-telemetry-sm text-status-ok">
            5.84
          </div>
        </div>
        <div class="rounded-xl border border-[color:var(--border-muted)] p-3">
          <div class="text-[10px] uppercase tracking-wider text-[color:var(--text-dim)]">
            EC
          </div>
          <div class="telemetry-value text-telemetry-sm text-status-warning">
            1.92
          </div>
        </div>
        <div class="rounded-xl border border-[color:var(--border-muted)] p-3">
          <div class="text-[10px] uppercase tracking-wider text-[color:var(--text-dim)]">
            T°C
          </div>
          <div class="telemetry-value text-telemetry-sm">
            22.4
          </div>
        </div>
      </div>
    </section>

    <section
      data-screen="device"
      class="surface-card space-y-2 p-4"
    >
      <h2 class="text-lg font-semibold">
        nd-ph-01
      </h2>
      <p class="text-xs text-[color:var(--text-muted)]">
        Блок 1 / Салат A / Узлы
      </p>
      <div class="flex flex-wrap gap-2">
        <Badge variant="ok">
          онлайн
        </Badge>
        <Badge variant="offline">
          nd-ec-02 нет связи
        </Badge>
        <Badge variant="critical">
          насос ошибка
        </Badge>
      </div>
    </section>

    <section
      data-screen="alerts"
      class="surface-card p-4"
    >
      <h2 class="mb-3 text-lg font-semibold">
        Тревоги
      </h2>
      <DataTableV2
        :columns="alertColumns"
        :rows="alertRows"
      >
        <template #cell-severity="{ row }">
          <StatusPill :tone="row.tone">
            {{ row.severity }}
          </StatusPill>
        </template>
      </DataTableV2>
    </section>

    <section
      data-screen="launch"
      class="surface-card overflow-hidden"
    >
      <HStepper
        :steps="launchSteps"
        :active="1"
        :completion="launchCompletion"
      />
      <div class="space-y-3 p-4">
        <h2 class="text-lg font-semibold">
          Запуск цикла
        </h2>
        <TextField
          model-value="Салат A"
          label="Зона"
          disabled
        />
        <TextField
          model-value="5.8"
          label="Целевой pH"
          suffix="pH"
          hint="Из активной фазы рецепта"
        />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import PageHeader from '@/Components/PageHeader.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import StatusPill from '@/Components/StatusPill.vue'
import DataTableV2 from '@/Components/DataTableV2.vue'
import HStepper from '@/Components/Launch/Shell/HStepper.vue'
import TextField from '@/Components/TextField.vue'
import type { LaunchStep, StepCompletion } from '@/Components/Launch/Shell/types'

const alertColumns = [
  { key: 'severity', label: 'Критичность' },
  { key: 'zone', label: 'Зона' },
  { key: 'message', label: 'Сообщение' },
]
const alertRows = ref([
  { id: 1, tone: 'critical', severity: 'Критично', zone: 'Салат A', message: 'Уровень раствора ниже датчика' },
  { id: 2, tone: 'warning', severity: 'Внимание', zone: 'Базилик', message: 'EC выше цели' },
  { id: 3, tone: 'offline', severity: 'Нет связи', zone: 'Томат', message: 'Узел nd-ec-02 не отвечает' },
])
const launchSteps: LaunchStep[] = [
  { id: 'zone', label: 'Зона', sub: 'теплица' },
  { id: 'recipe', label: 'Рецепт', sub: 'фаза' },
  { id: 'check', label: 'Проверка', sub: 'готовность' },
]
const launchCompletion: StepCompletion[] = ['done', 'current', 'todo']
</script>
