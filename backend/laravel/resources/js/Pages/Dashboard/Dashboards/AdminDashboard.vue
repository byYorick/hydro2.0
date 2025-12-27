<template>
  <div class="space-y-6">
    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
      <h1 class="text-lg font-semibold">Панель администратора</h1>
      <div class="flex flex-wrap gap-2">
        <Link href="/admin/users" class="flex-1 sm:flex-none min-w-[180px]">
          <Button size="sm" variant="primary" class="w-full sm:w-auto">Управление пользователями</Button>
        </Link>
        <Link href="/settings" class="flex-1 sm:flex-none min-w-[160px]">
          <Button size="sm" variant="outline" class="w-full sm:w-auto">Системные настройки</Button>
        </Link>
      </div>
    </div>

    <!-- Системная статистика -->
    <Card class="bg-[color:var(--bg-elevated)] border-[color:var(--border-muted)]">
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <div class="flex items-center gap-3">
          <div class="w-12 h-12 rounded-lg bg-[color:var(--badge-success-bg)] border border-[color:var(--badge-success-border)] flex items-center justify-center">
            <svg class="w-6 h-6 text-[color:var(--badge-success-text)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <div class="text-xs text-[color:var(--text-muted)]">Система</div>
            <div class="text-lg font-semibold text-[color:var(--accent-green)]">Онлайн</div>
          </div>
        </div>
        <div class="flex items-center gap-3" data-testid="dashboard-zones-count">
          <div class="w-12 h-12 rounded-lg bg-[color:var(--badge-info-bg)] border border-[color:var(--badge-info-border)] flex items-center justify-center">
            <svg class="w-6 h-6 text-[color:var(--badge-info-text)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
            </svg>
          </div>
          <div>
            <div class="text-xs text-[color:var(--text-muted)]">Зоны</div>
            <div class="text-lg font-semibold">
              {{ zonesStatusSummary.RUNNING || 0 }} активных
              <span v-if="zonesStatusSummary.PAUSED" class="text-[color:var(--text-muted)]">
                / {{ zonesStatusSummary.PAUSED }} на паузе
              </span>
            </div>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <div class="w-12 h-12 rounded-lg bg-[color:var(--badge-warning-bg)] border border-[color:var(--badge-warning-border)] flex items-center justify-center">
            <svg class="w-6 h-6 text-[color:var(--badge-warning-text)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m-2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
            </svg>
          </div>
          <div>
            <div class="text-xs text-[color:var(--text-muted)]">Устройства</div>
            <div class="text-lg font-semibold">
              <span class="text-[color:var(--accent-green)]">{{ nodesStatusSummary.online || 0 }} онлайн</span>
              <span v-if="nodesStatusSummary.offline" class="text-[color:var(--accent-red)] ml-2">
                / {{ nodesStatusSummary.offline }} офлайн
              </span>
            </div>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <div class="w-12 h-12 rounded-lg bg-[color:var(--badge-info-bg)] border border-[color:var(--badge-info-border)] flex items-center justify-center">
            <svg class="w-6 h-6 text-[color:var(--badge-info-text)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
          </div>
          <div>
            <div class="text-xs text-[color:var(--text-muted)]">Пользователи</div>
            <div class="text-lg font-semibold">{{ activeUsersCount }} активных</div>
          </div>
        </div>
      </div>
    </Card>

    <!-- Проблемные зоны -->
    <div v-if="problematicZones.length > 0" class="space-y-4">
      <div class="flex items-center justify-between">
        <h2 class="text-md font-semibold">Проблемные зоны</h2>
        <Link href="/zones">
          <Button size="sm" variant="outline">Все зоны</Button>
        </Link>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <Card
          v-for="zone in problematicZones"
          :key="zone.id"
          class="hover:border-[color:var(--border-strong)] transition-colors"
        >
          <div class="flex items-start justify-between mb-2">
            <div>
              <div class="text-sm font-semibold">{{ zone.name }}</div>
              <div v-if="zone.greenhouse" class="text-xs text-[color:var(--text-muted)] mt-1">
                {{ zone.greenhouse.name }}
              </div>
            </div>
            <Badge :variant="zone.status === 'ALARM' ? 'danger' : 'warning'">
              {{ translateStatus(zone.status) }}
            </Badge>
          </div>
          <div v-if="zone.alertsCount > 0" class="text-xs text-[color:var(--accent-red)] mb-2">
            Активных алертов: {{ zone.alertsCount }}
          </div>
          <div class="flex gap-2 mt-3">
            <Link :href="`/zones/${zone.id}`">
              <Button size="sm" variant="secondary">Подробнее</Button>
            </Link>
            <Button
              v-if="canCreateCommands"
              size="sm"
              variant="outline"
              :disabled="processingZones.has(zone.id)"
              @click="handleQuickAction(zone.id, zone.status === 'PAUSED' ? 'resume' : 'pause')"
            >
              {{ processingZones.has(zone.id) ? 'Обработка...' : (zone.status === 'PAUSED' ? 'Возобновить' : 'Приостановить') }}
            </Button>
          </div>
        </Card>
      </div>
    </div>

    <!-- Активность пользователей -->
    <div class="space-y-4">
      <div class="flex items-center justify-between">
        <h2 class="text-md font-semibold">Активность пользователей</h2>
        <Link href="/admin/audit">
          <Button size="sm" variant="outline">Полный аудит</Button>
        </Link>
      </div>
      <Card>
        <div v-if="recentUserActions.length > 0" class="space-y-2">
          <div
            v-for="action in recentUserActions"
            :key="action.id"
            class="flex items-center justify-between py-2 border-b border-[color:var(--border-muted)] last:border-0"
          >
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 rounded-full bg-[color:var(--bg-surface-strong)] flex items-center justify-center text-xs">
                {{ action.userName.charAt(0).toUpperCase() }}
              </div>
              <div>
                <div class="text-sm">{{ action.userName }}</div>
                <div class="text-xs text-[color:var(--text-muted)]">{{ action.description }}</div>
              </div>
            </div>
            <div class="text-xs text-[color:var(--text-dim)]">
              {{ formatTime(action.timestamp) }}
            </div>
          </div>
        </div>
        <div v-else class="text-sm text-[color:var(--text-dim)] text-center py-4">
          Нет недавних действий
        </div>
      </Card>
    </div>

    <!-- Быстрые действия -->
    <Card class="bg-[color:var(--bg-elevated)] border-[color:var(--border-muted)]">
      <h3 class="text-sm font-semibold mb-3">Быстрые действия</h3>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Link href="/admin/users">
          <Button size="sm" variant="secondary" class="w-full">Управление пользователями</Button>
        </Link>
        <Link href="/settings">
          <Button size="sm" variant="secondary" class="w-full">Системные настройки</Button>
        </Link>
        <Link href="/admin/audit">
          <Button size="sm" variant="secondary" class="w-full">Просмотр логов</Button>
        </Link>
        <Button 
          size="sm" 
          variant="outline" 
          class="w-full" 
          :disabled="exporting"
          @click="exportSystemData"
        >
          {{ exporting ? 'Экспорт...' : 'Экспорт данных' }}
        </Button>
      </div>
    </Card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Link } from '@inertiajs/vue3'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import { translateStatus } from '@/utils/i18n'
import { formatTime } from '@/utils/formatTime'
import { useRole } from '@/composables/useRole'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { logger } from '@/utils/logger'
import type { Zone } from '@/types'

interface Props {
  dashboard: {
    zonesByStatus?: Record<string, number>
    nodesByStatus?: Record<string, number>
    problematicZones?: Zone[]
    activeUsersCount?: number
    recentUserActions?: Array<{
      id: number
      userName: string
      description: string
      timestamp: string
    }>
  }
}

const props = defineProps<Props>()

const { canCreateCommands } = useRole()
const { api } = useApi()
const { showToast } = useToast()

const processingZones = ref<Set<number>>(new Set())
const exporting = ref(false)

const zonesStatusSummary = computed(() => props.dashboard.zonesByStatus || {})
const nodesStatusSummary = computed(() => props.dashboard.nodesByStatus || {})
const problematicZones = computed(() => props.dashboard.problematicZones || [])
const activeUsersCount = computed(() => props.dashboard.activeUsersCount || 0)
const recentUserActions = computed(() => props.dashboard.recentUserActions || [])

async function handleQuickAction(zoneId: number, action: string) {
  if (processingZones.value.has(zoneId)) {
    return
  }

  processingZones.value.add(zoneId)

  try {
    let endpoint = ''
    let method: 'post' | 'put' | 'patch' = 'post'
    const payload: any = {}

    switch (action) {
      case 'pause':
        endpoint = 'pause'
        break
      case 'resume':
        endpoint = 'resume'
        break
      case 'nextPhase':
        endpoint = 'advance'
        break
      default:
        showToast(`Неизвестное действие: ${action}`, 'error', TOAST_TIMEOUT.NORMAL)
        return
    }

    const cycleResponse = await api.get(`/zones/${zoneId}/grow-cycle`)
    const growCycleId = cycleResponse.data?.data?.id
    if (!growCycleId) {
      showToast('В зоне нет активного цикла', 'warning', TOAST_TIMEOUT.NORMAL)
      return
    }

    const actionEndpoint = endpoint === 'advance'
      ? `/grow-cycles/${growCycleId}/advance-phase`
      : `/grow-cycles/${growCycleId}/${endpoint}`

    const response = await api[method]<{ status: string; data?: Zone }>(actionEndpoint, payload)

    if (response.data?.status === 'ok') {
      const actionNames: Record<string, string> = {
        pause: 'приостановлена',
        resume: 'возобновлена',
        nextPhase: 'переведена на следующую фазу',
      }
      showToast(`Зона ${actionNames[action] || 'обновлена'}`, 'success', TOAST_TIMEOUT.NORMAL)
      logger.debug('[AdminDashboard] Quick action successful:', action, 'for zone:', zoneId)
      
      // Обновляем страницу для получения актуальных данных
      window.location.reload()
    }
  } catch (err) {
    logger.error('[AdminDashboard] Failed to execute quick action:', err)
    showToast('Не удалось выполнить действие', 'error', TOAST_TIMEOUT.LONG)
  } finally {
    processingZones.value.delete(zoneId)
  }
}

async function exportSystemData() {
  if (exporting.value) {
    return
  }

  exporting.value = true

  try {
    // Создаем данные для экспорта
    const exportData = {
      timestamp: new Date().toISOString(),
      zones: props.dashboard.problematicZones || [],
      zonesByStatus: props.dashboard.zonesByStatus || {},
      nodesByStatus: props.dashboard.nodesByStatus || {},
      activeUsersCount: props.dashboard.activeUsersCount || 0,
      recentUserActions: props.dashboard.recentUserActions || [],
    }

    // Создаем JSON файл
    const json = JSON.stringify(exportData, null, 2)
    const blob = new Blob([json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `hydro-system-export-${new Date().toISOString().split('T')[0]}.json`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)

    showToast('Данные экспортированы', 'success', TOAST_TIMEOUT.NORMAL)
    logger.debug('[AdminDashboard] System data exported successfully')
  } catch (err) {
    logger.error('[AdminDashboard] Failed to export system data:', err)
    showToast('Не удалось экспортировать данные', 'error', TOAST_TIMEOUT.LONG)
  } finally {
    exporting.value = false
  }
}
</script>
