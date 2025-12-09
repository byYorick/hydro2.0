<template>
  <AppLayout>
    <div class="space-y-6">
      <header class="space-y-3">
        <div class="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 class="text-lg font-semibold">Журнал сервисов</h1>
            <p class="text-sm text-neutral-400 max-w-3xl">
              Отслеживайте события автоматизации, History Logger, MQTT Bridge и cron в одном окне.
            </p>
          </div>
          <div class="flex flex-wrap gap-2 items-center">
            <span class="text-xs uppercase text-neutral-500 tracking-[0.3em]">Фильтры</span>
            <select
              v-model="filters.service"
              class="h-9 rounded-xl border border-neutral-700 bg-neutral-900 px-3 text-sm text-neutral-100"
            >
              <option value="all">Все сервисы</option>
              <option
                v-for="option in serviceSelectOptions"
                :key="option.key"
                :value="option.key"
              >
                {{ option.label }}
              </option>
            </select>
            <select
              v-model="filters.level"
              class="h-9 rounded-xl border border-neutral-700 bg-neutral-900 px-3 text-sm text-neutral-100"
            >
              <option value="">Все уровни</option>
              <option
                v-for="level in levelOptions"
                :key="level"
                :value="level"
              >
                {{ level }}
              </option>
            </select>
            <input
              v-model="filters.search"
              type="search"
              placeholder="Поиск по сообщению/контексту"
              class="h-9 w-56 rounded-xl border border-neutral-700 bg-neutral-900 px-3 text-sm text-neutral-100 placeholder:text-neutral-500"
            />
            <input
              v-model="filters.from"
              type="date"
              class="h-9 rounded-xl border border-neutral-700 bg-neutral-900 px-3 text-sm text-neutral-100"
            />
            <input
              v-model="filters.to"
              type="date"
              class="h-9 rounded-xl border border-neutral-700 bg-neutral-900 px-3 text-sm text-neutral-100"
            />
            <Button
              size="sm"
              variant="outline"
              :disabled="loading"
              @click="refresh"
            >
              Обновить
            </Button>
          </div>
        </div>
      </header>

      <div v-if="error" class="text-sm text-red-400">
        {{ error }}
      </div>

      <div v-if="loading" class="text-sm text-neutral-400 text-center py-8">
        Загрузка логов...
      </div>

      <div v-else-if="!hasLogs" class="text-sm text-neutral-400 text-center py-8">
        Нет логов по выбранным фильтрам
      </div>

      <div v-else class="grid gap-4 lg:grid-cols-2">
        <Card
          v-for="service in visibleServices"
          :key="service.key"
          class="space-y-3"
        >
          <div class="flex items-center justify-between gap-4">
            <div>
              <div class="text-sm font-semibold text-neutral-100">{{ service.label }}</div>
              <p class="text-xs text-neutral-500">{{ service.description ?? 'Логи сервиса' }}</p>
            </div>
            <span class="text-xs text-neutral-500">{{ entriesFor(service.key).length }} записей</span>
          </div>
          <div class="space-y-2 max-h-[360px] overflow-y-auto scrollbar-glow pr-1">
            <div
              v-for="entry in entriesFor(service.key)"
              :key="entry.id"
              class="surface-strong rounded-2xl border border-neutral-800 p-3"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="space-y-1">
                  <div class="text-sm font-semibold text-neutral-100">{{ entry.message }}</div>
                  <div class="text-xs text-neutral-500">{{ summarizeContext(entry.context) }}</div>
                </div>
                <div class="text-right">
                  <Badge :variant="levelVariant(entry.level)" size="xs">{{ entry.level }}</Badge>
                  <div class="text-[10px] text-neutral-500 mt-1">
                    {{ formatTime(entry.created_at) }}
                  </div>
                </div>
              </div>
            </div>
            <div v-if="!entriesFor(service.key).length" class="text-xs text-neutral-500 text-center py-6">
              Нет событий по выбранным фильтрам
            </div>
          </div>
        </Card>
      </div>

      <div class="flex items-center justify-between pt-2 border-t border-neutral-800" v-if="meta.total > 0">
        <div class="text-xs text-neutral-500">
          Страница {{ meta.page }} / {{ meta.last_page }} • {{ meta.total }} записей
        </div>
        <div class="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            :disabled="meta.page <= 1 || loading"
            @click="changePage(meta.page - 1)"
          >
            Назад
          </Button>
          <Button
            size="sm"
            variant="outline"
            :disabled="meta.page >= meta.last_page || loading"
            @click="changePage(meta.page + 1)"
          >
            Вперед
          </Button>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import { formatTime } from '@/utils/formatTime'
import { useApi } from '@/composables/useApi'
import { extractData } from '@/utils/apiHelpers'
import { logger } from '@/utils/logger'

interface ServiceOption {
  key: string
  label: string
  description?: string
}

interface ServiceLog {
  id: number
  service: string
  level: string
  message: string
  context?: Record<string, any> | null
  created_at: string
}

interface ServiceLogMeta {
  page: number
  per_page: number
  total: number
  last_page: number
}

interface Props {
  serviceOptions: ServiceOption[]
  defaultService?: string
  defaultLevel?: string
  defaultSearch?: string
}

const props = defineProps<Props>()

const { get } = useApi()

const filters = reactive({
  service: props.defaultService || 'all',
  level: props.defaultLevel || '',
  search: props.defaultSearch || '',
  from: '',
  to: '',
})

const levelOptions = ['ERROR', 'WARNING', 'INFO', 'DEBUG']
const logs = ref<ServiceLog[]>([])
const meta = reactive<ServiceLogMeta>({
  page: 1,
  per_page: 50,
  total: 0,
  last_page: 1,
})
const loading = ref(false)
const error = ref('')

let pollInterval: ReturnType<typeof setInterval> | null = null
let searchDebounce: ReturnType<typeof setTimeout> | null = null

const dynamicServices = computed<ServiceOption[]>(() => {
  const known = new Set(props.serviceOptions.map((s) => s.key))
  const dynamic = Array.from(new Set(logs.value.map((l) => l.service))).filter((key) => !known.has(key))
  return dynamic.map((key) => ({
    key,
    label: key,
    description: 'Логи сервиса',
  }))
})

const serviceSelectOptions = computed<ServiceOption[]>(() =>
  [...props.serviceOptions, ...dynamicServices.value].filter(
    (item, index, arr) => arr.findIndex((i) => i.key === item.key) === index
  )
)

const visibleServices = computed<ServiceOption[]>(() => {
  const baseList = filters.service === 'all'
    ? [...props.serviceOptions, ...dynamicServices.value]
    : [...props.serviceOptions, ...dynamicServices.value].filter((s) => s.key === filters.service)

  // Убираем дубликаты
  return baseList.filter((item, index, arr) => arr.findIndex((i) => i.key === item.key) === index)
})

const hasLogs = computed(() => logs.value.length > 0)

const entriesFor = (serviceKey: string) => logs.value.filter((entry) => entry.service === serviceKey)

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
  if (context['zone_id']) {
    return `Зона #${context['zone_id']}`
  }
  if (context['node_id']) {
    return `Нода #${context['node_id']}`
  }
  if (context['task_name']) {
    return `Задача: ${context['task_name']}`
  }
  if (context['service']) {
    return `Сервис: ${context['service']}`
  }
  return Object.entries(context)
    .map(([key, value]) => `${key}: ${typeof value === 'object' ? JSON.stringify(value) : value}`)
    .join(', ')
}

async function fetchLogs(page = 1) {
  loading.value = true
  error.value = ''
  meta.page = page

  try {
    const params: Record<string, any> = {
      page,
      per_page: meta.per_page,
    }

    if (filters.service && filters.service !== 'all') params.service = filters.service
    if (filters.level) params.level = filters.level
    if (filters.search.trim()) params.search = filters.search.trim()
    if (filters.from) params.from = filters.from
    if (filters.to) params.to = filters.to

    const response = await get('/logs/service', { params })
    const payload = response?.data ?? {}
    const normalized = extractData<ServiceLog[] | { data?: ServiceLog[]; meta?: ServiceLogMeta }>(payload)
    const normalizedLogs = Array.isArray(normalized) ? normalized : normalized?.data ?? []
    const metaPayload = (!Array.isArray(normalized) ? normalized?.meta : undefined) || (payload as any)?.meta

    logs.value = Array.isArray(normalizedLogs) ? normalizedLogs : []
    updateMeta(metaPayload, logs.value.length)
  } catch (err) {
    logger.error('Failed to load service logs', { err })
    error.value = 'Не удалось загрузить логи. Попробуйте обновить страницу.'
  } finally {
    loading.value = false
  }
}

function updateMeta(metaPayload?: Partial<ServiceLogMeta> | null, fallbackTotal = 0) {
  const pageValue = (metaPayload as any)?.page ?? (metaPayload as any)?.current_page
  const perPageValue = (metaPayload as any)?.per_page ?? (metaPayload as any)?.perPage
  const totalValue = (metaPayload as any)?.total ?? (metaPayload as any)?.total_count
  const lastPageValue = (metaPayload as any)?.last_page ?? (metaPayload as any)?.lastPage ?? (metaPayload as any)?.total_pages

  meta.page = pageValue ?? meta.page
  meta.per_page = perPageValue ?? meta.per_page
  meta.total = totalValue ?? fallbackTotal ?? meta.total
  meta.last_page = lastPageValue ?? meta.last_page
}

function changePage(newPage: number) {
  if (newPage < 1 || newPage > meta.last_page) return
  fetchLogs(newPage)
}

function refresh() {
  fetchLogs(meta.page)
}

function startPolling() {
  if (pollInterval) clearInterval(pollInterval)
  pollInterval = setInterval(() => fetchLogs(meta.page), 5000)
}

function stopPolling() {
  if (pollInterval) {
    clearInterval(pollInterval)
    pollInterval = null
  }
}

watch(
  () => [filters.service, filters.level, filters.from, filters.to],
  () => fetchLogs(1)
)

watch(
  () => filters.search,
  () => {
    if (searchDebounce) clearTimeout(searchDebounce)
    searchDebounce = setTimeout(() => fetchLogs(1), 400)
  }
)

onMounted(async () => {
  await fetchLogs()
  startPolling()
})

onUnmounted(() => {
  stopPolling()
  if (searchDebounce) {
    clearTimeout(searchDebounce)
    searchDebounce = null
  }
})
</script>

<style scoped>
select option {
  background-color: rgb(23 23 23); /* neutral-900 */
  color: rgb(245 245 245); /* neutral-100 */
}
</style>
