<template>
  <AppLayout>
    <div class="max-w-4xl mx-auto">
      <div class="mb-6">
        <h1 class="text-2xl font-bold mb-2">
          Мастер запуска цикла выращивания
        </h1>
        <p class="text-sm text-[color:var(--text-muted)]">
          Пошаговая настройка цикла от посадки до сбора
        </p>
      </div>

      <GrowthCycleWizard
        :show="wizardOpen"
        @close="onClose"
        @submit="onSubmit"
      />
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import GrowthCycleWizard from '@/Components/GrowCycle/GrowthCycleWizard.vue'

const wizardOpen = ref(true)

function onClose(): void {
  wizardOpen.value = false
  router.visit('/cycles')
}

function onSubmit(payload: { zoneId: number }): void {
  wizardOpen.value = false
  router.visit(`/zones/${payload.zoneId}`)
}
</script>
