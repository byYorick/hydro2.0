<template>
  <div
    class="min-h-screen flex flex-col bg-[var(--bg-main)] text-[var(--text-primary)] font-sans antialiased"
    :data-density="density"
    :data-stepper="stepper"
  >
    <slot name="topbar">
      <LaunchTopBar />
    </slot>
    <div
      v-if="$slots.stepper"
      class="sticky top-12 z-[15] bg-[var(--bg-surface-strong)] backdrop-blur-sm"
    >
      <slot name="stepper" />
    </div>

    <div class="flex flex-1 min-h-0">
      <slot name="rail"></slot>
      <main class="flex-1 px-5 pt-4 pb-20 min-w-0 flex flex-col gap-3.5 bg-[var(--bg-main)]">
        <slot></slot>
      </main>
    </div>

    <slot name="footer"></slot>
  </div>
</template>

<script setup lang="ts">
import LaunchTopBar from './LaunchTopBar.vue'
import { useLaunchPreferences } from '@/composables/useLaunchPreferences'

const { density, stepper } = useLaunchPreferences()
</script>
