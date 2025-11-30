<template>
  <AppLayout>
    <div class="min-h-screen flex items-center justify-center bg-neutral-950 p-4">
      <Card class="max-w-md w-full">
        <div class="text-center">
          <div class="text-6xl mb-4">⚠️</div>
          <h1 class="text-2xl font-bold mb-2 text-red-400">{{ status || 'Ошибка' }}</h1>
          <p class="text-sm text-neutral-400 mb-4">{{ message || 'Произошла непредвиденная ошибка' }}</p>
          
          <div v-if="correlation_id" class="text-xs text-neutral-500 mb-4">
            ID запроса: {{ correlation_id }}
          </div>
          
          <div v-if="errors && Object.keys(errors).length > 0" class="text-left bg-neutral-900 p-3 rounded mb-4">
            <div class="text-sm font-semibold text-red-400 mb-2">Ошибки валидации:</div>
            <ul class="text-xs text-neutral-300 space-y-1">
              <li v-for="(errorMessages, field) in errors" :key="field">
                <strong>{{ field }}:</strong>
                <ul class="ml-4 mt-1">
                  <li v-for="error in errorMessages" :key="error">{{ error }}</li>
                </ul>
              </li>
            </ul>
          </div>
          
          <div v-if="isDev && exception" class="text-left bg-neutral-900 p-3 rounded mb-4 overflow-auto max-h-60">
            <div class="text-xs font-semibold text-yellow-400 mb-2">Детали ошибки (только в dev режиме):</div>
            <pre class="text-xs text-neutral-300 whitespace-pre-wrap">{{ exception }}</pre>
            <div v-if="file" class="text-xs text-neutral-500 mt-2">
              Файл: {{ file }}:{{ line }}
            </div>
          </div>
          
          <div class="flex gap-2 justify-center">
            <Button @click="goBack" variant="secondary">Назад</Button>
            <Button @click="goHome" variant="primary">На главную</Button>
            <Button v-if="status === 401" @click="goToLogin" variant="outline">Войти</Button>
          </div>
        </div>
      </Card>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'

interface Props {
  status?: number
  message?: string
  errors?: Record<string, string[]>
  correlation_id?: string
  exception?: string
  file?: string
  line?: number
}

const props = withDefaults(defineProps<Props>(), {
  status: 500,
  message: 'Произошла непредвиденная ошибка',
  errors: () => ({}),
})

const isDev = computed(() => import.meta.env.DEV)

function goBack(): void {
  window.history.back()
}

function goHome(): void {
  router.visit('/')
}

function goToLogin(): void {
  router.visit('/login')
}
</script>

