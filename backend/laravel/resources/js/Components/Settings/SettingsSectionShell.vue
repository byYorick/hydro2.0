<template>
  <section
    class="settings-card"
    :data-testid="testId"
  >
    <header class="settings-card__header">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div class="flex items-start gap-3 min-w-0">
          <div
            v-if="icon"
            class="settings-nav-item__icon shrink-0"
            aria-hidden="true"
          >
            {{ icon }}
          </div>
          <div class="min-w-0">
            <h2 class="settings-card__title">
              {{ title }}
            </h2>
            <p
              v-if="description"
              class="settings-card__description"
            >
              {{ description }}
            </p>
          </div>
        </div>
        <div
          v-if="$slots.actions"
          class="flex flex-wrap items-center gap-2 shrink-0"
        >
          <slot name="actions" />
        </div>
      </div>
    </header>

    <div class="settings-card__body">
      <slot />
      <div
        v-if="$slots.footer"
        class="settings-sticky-footer"
      >
        <slot name="footer" />
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  description?: string
  icon?: string
  testId?: string
}>()
</script>
