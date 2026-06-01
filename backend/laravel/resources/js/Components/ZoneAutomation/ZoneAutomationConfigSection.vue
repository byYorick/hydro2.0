<template>
  <section
    class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 md:p-5 space-y-4"
    aria-labelledby="zone-automation-config-title"
  >
    <header>
      <h2
        id="zone-automation-config-title"
        class="text-sm font-semibold text-[color:var(--text-primary)]"
      >
        Конфигурация в runtime
      </h2>
      <p class="text-xs text-[color:var(--text-muted)] mt-0.5">
        Режим locked/live, точечные правки фазы и журнал изменений
      </p>
    </header>

    <slot />
  </section>
</template>

<script setup lang="ts">
</script>
