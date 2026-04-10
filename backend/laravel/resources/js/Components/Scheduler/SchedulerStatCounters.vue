<template>
  <div class="ui-kpi-grid grid-cols-2 md:grid-cols-4">
    <div class="ui-kpi-card">
      <div class="flex items-center justify-between gap-3">
        <div class="ui-kpi-label">
          Активные
        </div>
        <span
          class="ui-state-dot"
          :class="active > 0 ? 'text-[color:var(--accent-cyan)]' : 'text-[color:var(--text-dim)]'"
          :title="active > 0 ? 'Есть активные исполнения' : 'Активных исполнений нет'"
        ></span>
      </div>
      <div class="ui-kpi-value">
        {{ active }}
      </div>
      <div class="ui-kpi-hint">
        Сейчас в работе
      </div>
    </div>

    <div class="ui-kpi-card">
      <div class="flex items-center justify-between gap-3">
        <div class="ui-kpi-label">
          Успешные
        </div>
        <span
          class="ui-state-dot text-[color:var(--accent-green)]"
          title="Завершено успешно за 24 часа"
        ></span>
      </div>
      <div class="ui-kpi-value">
        {{ completed24h }}
      </div>
      <div class="ui-kpi-hint">
        За 24 часа
      </div>
    </div>

    <div class="ui-kpi-card">
      <div class="flex items-center justify-between gap-3">
        <div class="ui-kpi-label">
          Ошибки
        </div>
        <span
          class="ui-state-dot"
          :class="failed24h > 0 ? 'text-[color:var(--accent-red)]' : 'text-[color:var(--text-dim)]'"
          :title="failed24h > 0 ? 'Есть ошибки за 24 часа' : 'Ошибок за 24 часа нет'"
        ></span>
      </div>
      <div class="ui-kpi-value">
        {{ failed24h }}
      </div>
      <div class="ui-kpi-hint">
        За 24 часа
      </div>
    </div>

    <div class="ui-kpi-card">
      <div class="flex items-center justify-between gap-3">
        <div class="ui-kpi-label">
          Окна
        </div>
        <span
          class="ui-state-dot text-[color:var(--accent-amber)]"
          title="Исполнимые окна на горизонте"
        ></span>
      </div>
      <div class="ui-kpi-value">
        {{ executableWindows }}
      </div>
      <div class="ui-kpi-hint">
        Исполнимые на горизонте
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  active: number
  completed24h: number
  failed24h: number
  executableWindows: number
}>()
</script>

