<script setup>
import AppLayout from '@/Layouts/AppLayout.vue'
import { Head } from '@inertiajs/vue3'
</script>

<template>
    <Head title="Панель управления" />

  <AppLayout>
    <div class="max-w-4xl mx-auto space-y-4">
      <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-6">
        <h2 class="text-lg font-semibold text-[color:var(--text-primary)] mb-2">Панель управления</h2>
        <p class="text-sm text-[color:var(--text-muted)]">
          Вы успешно вошли в систему. Используйте основное меню для перехода к роли-ориентированному дашборду.
        </p>
                    </div>
                </div>
  </AppLayout>
</template>
