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
    <Card class="bg-neutral-900 border-neutral-800">
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <div class="flex items-center gap-3">
          <div class="w-12 h-12 rounded-lg bg-emerald-900/30 border border-emerald-700 flex items-center justify-center">
            <svg class="w-6 h-6 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <div class="text-xs text-neutral-400">Система</div>
            <div class="text-lg font-semibold text-emerald-400">Онлайн</div>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <div class="w-12 h-12 rounded-lg bg-sky-900/30 border border-sky-700 flex items-center justify-center">
            <svg class="w-6 h-6 text-sky-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
            </svg>
          </div>
          <div>
            <div class="text-xs text-neutral-400">Зоны</div>
            <div class="text-lg font-semibold">
              {{ zonesStatusSummary.RUNNING || 0 }} активных
              <span v-if="zonesStatusSummary.PAUSED" class="text-neutral-400">
                / {{ zonesStatusSummary.PAUSED }} на паузе
              </span>
            </div>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <div class="w-12 h-12 rounded-lg bg-amber-900/30 border border-amber-700 flex items-center justify-center">
            <svg class="w-6 h-6 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m-2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
            </svg>
          </div>
          <div>
            <div class="text-xs text-neutral-400">Устройства</div>
            <div class="text-lg font-semibold">
              <span class="text-emerald-400">{{ nodesStatusSummary.online || 0 }} онлайн</span>
              <span v-if="nodesStatusSummary.offline" class="text-red-400 ml-2">
                / {{ nodesStatusSummary.offline }} офлайн
              </span>
            </div>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <div class="w-12 h-12 rounded-lg bg-purple-900/30 border border-purple-700 flex items-center justify-center">
            <svg class="w-6 h-6 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
          </div>
          <div>
            <div class="text-xs text-neutral-400">Пользователи</div>
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
          class="hover:border-neutral-700 transition-colors"
        >
          <div class="flex items-start justify-between mb-2">
            <div>
              <div class="text-sm font-semibold">{{ zone.name }}</div>
              <div v-if="zone.greenhouse" class="text-xs text-neutral-400 mt-1">
                {{ zone.greenhouse.name }}
              </div>
            </div>
            <Badge :variant="zone.status === 'ALARM' ? 'danger' : 'warning'">
              {{ translateStatus(zone.status) }}
            </Badge>
          </div>
          <div v-if="zone.alertsCount > 0" class="text-xs text-red-400 mb-2">
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
              @click="handleQuickAction(zone.id, 'pause')"
            >
              {{ zone.status === 'PAUSED' ? 'Возобновить' : 'Приостановить' }}
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
            class="flex items-center justify-between py-2 border-b border-neutral-800 last:border-0"
          >
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 rounded-full bg-neutral-800 flex items-center justify-center text-xs">
                {{ action.userName.charAt(0).toUpperCase() }}
              </div>
              <div>
                <div class="text-sm">{{ action.userName }}</div>
                <div class="text-xs text-neutral-400">{{ action.description }}</div>
              </div>
            </div>
            <div class="text-xs text-neutral-500">
              {{ formatTime(action.timestamp) }}
            </div>
          </div>
        </div>
        <div v-else class="text-sm text-neutral-400 text-center py-4">
          Нет недавних действий
        </div>
      </Card>
    </div>

    <!-- Быстрые действия -->
    <Card class="bg-neutral-900 border-neutral-800">
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
        <Button size="sm" variant="outline" class="w-full" @click="exportSystemData">
          Экспорт данных
        </Button>
      </div>
    </Card>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Link } from '@inertiajs/vue3'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import { translateStatus } from '@/utils/i18n'
import { formatTime } from '@/utils/formatTime'
import { useRole } from '@/composables/useRole'
import { useApi } from '@/composables/useApi'
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

const zonesStatusSummary = computed(() => props.dashboard.zonesByStatus || {})
const nodesStatusSummary = computed(() => props.dashboard.nodesByStatus || {})
const problematicZones = computed(() => props.dashboard.problematicZones || [])
const activeUsersCount = computed(() => props.dashboard.activeUsersCount || 0)
const recentUserActions = computed(() => props.dashboard.recentUserActions || [])

function handleQuickAction(zoneId: number, action: string) {
  // TODO: Реализовать быстрые действия
  console.log('Quick action:', action, 'for zone:', zoneId)
}

function exportSystemData() {
  // TODO: Реализовать экспорт данных
  console.log('Export system data')
}
</script>

