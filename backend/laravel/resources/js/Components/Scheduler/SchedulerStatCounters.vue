<template>
  <div class="grid grid-cols-2 gap-1.5 md:grid-cols-4">
    <!-- Активные -->
    <div
      class="ui-kpi-card transition-shadow"
      :class="active > 0 ? 'ring-1 ring-[color:var(--accent-cyan)]/30' : ''"
    >
      <div class="flex items-center gap-1 text-[10px] text-[color:var(--text-dim)]">
        <svg
          class="h-3 w-3 shrink-0"
          :class="active > 0 ? 'text-[color:var(--accent-cyan)]' : ''"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
        >
          <circle
            cx="8"
            cy="8"
            r="6.5"
          />
          <path
            d="M8 4.5V8l2.5 1.5"
            stroke-linecap="round"
          />
        </svg>
        Активные
      </div>
      <div
        class="mt-0.5 text-xl font-bold tabular-nums"
        :class="active > 0 ? 'text-[color:var(--accent-cyan)]' : 'text-[color:var(--text-primary)]'"
      >
        {{ active }}
      </div>
      <div class="text-[10px] text-[color:var(--text-muted)]">
        сейчас
      </div>
    </div>

    <!-- Успешные -->
    <div class="ui-kpi-card">
      <div class="flex items-center gap-1 text-[10px] text-[color:var(--text-dim)]">
        <svg
          class="h-3 w-3 shrink-0 text-[color:var(--accent-green)]"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
        >
          <circle
            cx="8"
            cy="8"
            r="6.5"
          />
          <path
            d="M5 8.5l2 2 4-4"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
        Успешные
      </div>
      <div class="mt-0.5 text-xl font-bold tabular-nums text-[color:var(--text-primary)]">
        {{ completed24h }}
      </div>
      <div class="text-[10px] text-[color:var(--text-muted)]">
        за 24ч
      </div>
    </div>

    <!-- Ошибки -->
    <div
      class="ui-kpi-card transition-shadow"
      :class="failed24h > 0 ? 'ring-1 ring-[color:var(--accent-red)]/30' : ''"
    >
      <div class="flex items-center gap-1 text-[10px] text-[color:var(--text-dim)]">
        <svg
          class="h-3 w-3 shrink-0"
          :class="failed24h > 0 ? 'text-[color:var(--accent-red)]' : ''"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
        >
          <circle
            cx="8"
            cy="8"
            r="6.5"
          />
          <path
            d="M8 5v4M8 11v.5"
            stroke-linecap="round"
          />
        </svg>
        Ошибки
      </div>
      <div
        class="mt-0.5 text-xl font-bold tabular-nums"
        :class="failed24h > 0 ? 'text-[color:var(--accent-red)]' : 'text-[color:var(--text-primary)]'"
      >
        {{ failed24h }}
      </div>
      <div class="text-[10px] text-[color:var(--text-muted)]">
        за 24ч
      </div>
    </div>

    <!-- Окна -->
    <div class="ui-kpi-card">
      <div class="flex items-center gap-1 text-[10px] text-[color:var(--text-dim)]">
        <svg
          class="h-3 w-3 shrink-0 text-[color:var(--accent-amber)]"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
        >
          <rect
            x="2"
            y="3"
            width="12"
            height="11"
            rx="2"
          />
          <path
            d="M2 7h12M6 1v4M10 1v4"
            stroke-linecap="round"
          />
        </svg>
        Окна
      </div>
      <div class="mt-0.5 text-xl font-bold tabular-nums text-[color:var(--text-primary)]">
        {{ executableWindows }}
      </div>
      <div class="text-[10px] text-[color:var(--text-muted)]">
        исполнимых
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
