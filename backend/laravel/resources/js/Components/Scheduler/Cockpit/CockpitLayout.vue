<template>
  <div
    class="scheduler-cockpit-layout grid gap-2.5 min-h-0"
    data-testid="scheduler-cockpit-layout"
  >
    <div class="flex min-h-0 flex-col gap-2.5">
      <slot name="left"></slot>
    </div>
    <div class="flex min-h-0 flex-col gap-2.5">
      <slot name="center"></slot>
    </div>
    <div class="flex min-h-0 flex-col gap-2.5">
      <slot name="right"></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.scheduler-cockpit-layout {
  grid-template-columns: 340px minmax(0, 1fr) 360px;
}

@media (max-width: 1280px) {
  .scheduler-cockpit-layout {
    grid-template-columns: 1fr;
  }
}
</style>
