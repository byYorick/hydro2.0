<template>
  <div
    class="scheduler-cockpit-layout grid min-h-0 gap-3"
    data-testid="scheduler-cockpit-layout"
  >
    <div class="scheduler-cockpit-layout__rail scheduler-cockpit-layout__left flex min-h-0 flex-col gap-3">
      <slot name="left"></slot>
    </div>
    <div class="scheduler-cockpit-layout__main flex min-h-0 flex-col gap-3">
      <slot name="center"></slot>
    </div>
    <div class="scheduler-cockpit-layout__rail scheduler-cockpit-layout__details flex min-h-0 flex-col gap-3">
      <slot name="right"></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.scheduler-cockpit-layout {
  grid-template-columns: minmax(240px, 0.7fr) minmax(0, 2fr);
  grid-template-areas: 'status content' 'details details';
  align-items: start;
}

.scheduler-cockpit-layout__rail,
.scheduler-cockpit-layout__main {
  min-width: 0;
}
.scheduler-cockpit-layout__left { grid-area: status; }
.scheduler-cockpit-layout__main { grid-area: content; }
.scheduler-cockpit-layout__details { grid-area: details; }

@media (max-width: 767px) {
  .scheduler-cockpit-layout {
    grid-template-columns: 1fr;
    grid-template-areas: 'status' 'content' 'details';
  }
}
</style>
