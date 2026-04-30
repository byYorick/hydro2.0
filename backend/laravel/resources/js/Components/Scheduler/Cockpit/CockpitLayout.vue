<template>
  <div
    class="scheduler-cockpit-layout grid min-h-0 gap-3"
    data-testid="scheduler-cockpit-layout"
  >
    <div class="scheduler-cockpit-layout__rail flex min-h-0 flex-col gap-3">
      <slot name="left"></slot>
    </div>
    <div class="scheduler-cockpit-layout__main flex min-h-0 flex-col gap-3">
      <slot name="center"></slot>
    </div>
    <div class="scheduler-cockpit-layout__rail flex min-h-0 flex-col gap-3">
      <slot name="right"></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.scheduler-cockpit-layout {
  grid-template-columns: minmax(290px, 0.9fr) minmax(520px, 1.7fr) minmax(320px, 1fr);
  align-items: start;
}

.scheduler-cockpit-layout__rail,
.scheduler-cockpit-layout__main {
  min-width: 0;
}

@media (max-width: 1280px) {
  .scheduler-cockpit-layout {
    grid-template-columns: 1fr;
  }
}
</style>
