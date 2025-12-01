<template>
  <AppLayout>
    <div class="space-y-6">
      <header class="space-y-3">
        <div class="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 class="text-lg font-semibold">Журнал сервисов</h1>
            <p class="text-sm text-neutral-400 max-w-3xl">
              Отслеживайте события автоматизации, History Locker и системных процессов в едином окне.
            </p>
          </div>
          <div class="flex flex-wrap gap-2 items-center">
            <span class="text-xs uppercase text-neutral-500 tracking-[0.3em]">Фильтры</span>
            <select
              v-model="selectedService"
              class="h-9 rounded-xl border border-neutral-700 bg-neutral-900 px-3 text-sm text-neutral-100"
            >
              <option value="all">Все сервисы</option>
              <option
                v-for="option in serviceOptions"
                :key="option.key"
                :value="option.key"
              >
                {{ option.label }}
              </option>
            </select>
            <select
              v-model="selectedLevel"
              class="h-9 rounded-xl border border-neutral-700 bg-neutral-900 px-3 text-sm text-neutral-100"
            >
              <option value="">Все уровни</option>
              <option
                v-for="level in levelFilters"
                :key="level"
                :value="level"
              >
                {{ level }}
              </option>
            </select>
          </div>
        </div>
      </header>

      <div class="grid gap-4 lg:grid-cols-2">
        <Card
          v-for="service in filteredServices"
          :key="service.key"
          class="space-y-3"
        >
          <div class="flex items-center justify-between">
            <div>
              <div class="text-sm font-semibold text-neutral-100">{{ service.label }}</div>
              <p class="text-xs text-neutral-500">{{ service.description }}</p>
            </div>
            <span class="text-xs text-neutral-500">{{ service.entries.length }} записей</span>
          </div>
          <div class="space-y-2 max-h-[320px] overflow-y-auto scrollbar-glow pr-1">
            <div
              v-for="entry in entriesFor(service)"
              :key="entry.id"
              class="surface-strong rounded-2xl border border-neutral-800 p-3"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="text-sm font-semibold text-neutral-100">{{ entry.message }}</div>
                  <div class="text-xs text-neutral-500 mt-1">{{ summarizeContext(entry.context) }}</div>
                </div>
                <div class="text-right">
                  <Badge :variant="levelVariant(entry.level)" size="xs">{{ entry.level }}</Badge>
                  <div class="text-[10px] text-neutral-500 mt-1">
                    {{ formatTime(entry.created_at) }}
                  </div>
                </div>
              </div>
            </div>
            <div v-if="!entriesFor(service).length" class="text-xs text-neutral-500 text-center py-6">
              Нет событий по выбранным фильтрам
            </div>
          </div>
        </Card>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Badge from '@/Components/Badge.vue'
import { formatTime } from '@/utils/formatTime'

interface LogEntry {
  id: number
  level: string
  message: string
  context?: Record<string, any> | null
  created_at: string
}

interface ServiceLog {
  key: string
  label: string
  description: string
  entries: LogEntry[]
}

interface Props {
  serviceLogs: ServiceLog[]
  serviceOptions: Array<{ key: string; label: string }>
  levelFilters: string[]
  selectedService: string
  selectedLevel: string
}

const props = defineProps<Props>()

const selectedService = ref(props.selectedService || 'all')
const selectedLevel = ref(props.selectedLevel || '')

const filteredServices = computed(() => {
  if (selectedService.value === 'all') {
    return props.serviceLogs
  }
  return props.serviceLogs.filter((service) => service.key === selectedService.value)
})

const entriesFor = (service: ServiceLog) => {
  if (!selectedLevel.value) {
    return service.entries
  }
  return service.entries.filter((entry) => entry.level === selectedLevel.value)
}

const levelVariant = (level: string) => {
  const normalized = level?.toLowerCase()
  if (normalized.includes('error') || normalized.includes('critical')) {
    return 'danger'
  }
  if (normalized.includes('warn')) {
    return 'warning'
  }
  if (normalized.includes('debug') || normalized.includes('trace')) {
    return 'info'
  }
  return 'neutral'
}

const summarizeContext = (context?: Record<string, any> | null) => {
  if (!context) return 'Дополнительных метаданных нет'
  if (context['zone']) {
    return `Зона: ${context['zone']['name'] ?? `#${context['zone']['id'] ?? '—'}`}`
  }
  if (context['service']) {
    return `Сервис: ${context['service']}`
  }
  return Object.entries(context)
    .map(([key, value]) => `${key}: ${typeof value === 'object' ? JSON.stringify(value) : value}`)
    .join(', ')
}
</script>

<style scoped>
select option {
  background-color: rgb(23 23 23); /* neutral-900 */
  color: rgb(245 245 245); /* neutral-100 */
}
</style>
