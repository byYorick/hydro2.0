<template>
  <section
    class="surface-card rounded-2xl border border-[color:var(--border-muted)] p-4 md:p-5"
    data-testid="dashboard-admin-health"
  >
    <div class="space-y-4">
      <div class="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
        <h2 class="text-sm font-semibold text-[color:var(--text-primary)]">
          Здоровье сервисов
        </h2>
        <p
          class="text-sm font-medium"
          :class="okCount === totalCount && totalCount > 0
            ? 'text-[color:var(--accent-green)]'
            : 'text-[color:var(--accent-amber)]'"
          data-testid="dashboard-admin-health-count"
        >
          <template v-if="loaded">
            {{ okCount }} из {{ totalCount }} ok
          </template>
          <template v-else>
            Проверка сервисов…
          </template>
        </p>
      </div>

      <ul class="flex flex-wrap gap-2">
        <li
          v-for="service in services"
          :key="service.key"
          class="flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs"
          :class="pillClass(service.status)"
        >
          <span
            class="h-1.5 w-1.5 rounded-full"
            :class="dotClass(service.status)"
          />
          {{ service.label }}
        </li>
      </ul>

      <div
        v-if="blockedCount > 0"
        class="rounded-xl border border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)] p-3"
      >
        <div class="text-sm font-medium text-[color:var(--accent-red)]">
          Автоматика остановлена: {{ blockedCount }}
        </div>
        <p class="mt-1 text-xs text-[color:var(--text-muted)]">
          Зоны с блокировкой AE3. Снятие — только после разбора тревоги.
        </p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { systemApi, type SystemHealthPayload } from '@/services/api/system'

const HEALTH_SERVICES = [
  { key: 'app', label: 'API' },
  { key: 'db', label: 'БД' },
  { key: 'mqtt', label: 'MQTT' },
  { key: 'history_logger', label: 'history-logger' },
  { key: 'automation_engine', label: 'AE3' },
] as const

defineProps<{
  blockedCount: number
}>()

const loaded = ref(false)
const payload = ref<SystemHealthPayload | null>(null)

const services = computed(() =>
  HEALTH_SERVICES.map((item) => ({
    key: item.key,
    label: item.label,
    status: String(payload.value?.[item.key] ?? 'unknown'),
  })),
)

const totalCount = HEALTH_SERVICES.length
const okCount = computed(() =>
  services.value.filter((item) => item.status === 'ok').length,
)

onMounted(async () => {
  try {
    payload.value = await systemApi.health()
  } catch {
    payload.value = null
  } finally {
    loaded.value = true
  }
})

function pillClass(status: string): string {
  if (status === 'ok') {
    return 'border-[color:var(--badge-success-border)] bg-[color:var(--badge-success-bg)] text-[color:var(--text-primary)]'
  }
  if (status === 'fail') {
    return 'border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)] text-[color:var(--text-primary)]'
  }
  return 'border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] text-[color:var(--text-muted)]'
}

function dotClass(status: string): string {
  if (status === 'ok') {
    return 'bg-[color:var(--accent-green)]'
  }
  if (status === 'fail') {
    return 'bg-[color:var(--accent-red)]'
  }
  return 'bg-[color:var(--text-dim)]'
}
</script>
