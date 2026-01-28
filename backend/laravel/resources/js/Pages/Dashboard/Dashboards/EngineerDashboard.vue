<template>
  <div class="space-y-6">
    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
      <h1 class="text-lg font-semibold">
        Панель инженера
      </h1>
      <div class="flex flex-wrap gap-2">
        <Link
          href="/system"
          class="flex-1 sm:flex-none min-w-[160px]"
        >
          <Button
            size="sm"
            variant="outline"
            class="w-full sm:w-auto"
          >
            Системные метрики
          </Button>
        </Link>
        <Link
          href="/logs"
          class="flex-1 sm:flex-none min-w-[120px]"
        >
          <Button
            size="sm"
            variant="outline"
            class="w-full sm:w-auto"
          >
            Логи
          </Button>
        </Link>
      </div>
    </div>

    <!-- Статус устройств -->
    <div class="space-y-4">
      <h2 class="text-md font-semibold">
        Статус устройств
      </h2>
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <Card
          v-for="device in devices"
          :key="device.id"
          class="hover:border-[color:var(--border-strong)] transition-colors"
        >
          <div class="flex items-start justify-between mb-3">
            <div>
              <div class="text-sm font-semibold">
                {{ device.uid || device.name }}
              </div>
              <div class="text-xs text-[color:var(--text-muted)] mt-1">
                {{ device.type || 'Устройство' }}
              </div>
            </div>
            <Badge :variant="(device.status as string) === 'ONLINE' || device.status === 'online' ? 'success' : 'danger'">
              {{ translateStatus(device.status) }}
            </Badge>
          </div>
          
          <div class="space-y-2 text-xs">
            <div
              v-if="device.rssi !== null && device.rssi !== undefined"
              class="flex items-center justify-between"
            >
              <span class="text-[color:var(--text-muted)]">RSSI:</span>
              <span :class="getRssiColor(device.rssi)">{{ device.rssi }} dBm</span>
            </div>
            <div
              v-if="device.firmwareVersion"
              class="flex items-center justify-between"
            >
              <span class="text-[color:var(--text-muted)]">Прошивка:</span>
              <span class="text-[color:var(--text-primary)]">{{ device.firmwareVersion }}</span>
            </div>
            <div
              v-if="device.lastSeen"
              class="flex items-center justify-between"
            >
              <span class="text-[color:var(--text-muted)]">Обновление:</span>
              <span class="text-[color:var(--text-primary)]">{{ formatTimeAgo(device.lastSeen) }}</span>
            </div>
            <div
              v-if="device.issues && device.issues.length > 0"
              class="mt-2"
            >
              <div class="text-[color:var(--accent-amber)] text-xs">
                <div
                  v-for="issue in device.issues"
                  :key="issue"
                >
                  ⚠️ {{ issue }}
                </div>
              </div>
            </div>
          </div>
          
          <div class="mt-3 flex gap-2">
            <Link :href="`/devices/${device.id}`">
              <Button
                size="sm"
                variant="secondary"
              >
                Подробнее
              </Button>
            </Link>
            <Button
              size="sm"
              variant="outline"
              :disabled="testingDevices.has(device.id)"
              @click="testDevice(device.id)"
            >
              {{ testingDevices.has(device.id) ? 'Тестирование...' : 'Тест' }}
            </Button>
          </div>
        </Card>
      </div>
    </div>

    <!-- Проблемные устройства -->
    <div
      v-if="problematicDevices.length > 0"
      class="space-y-4"
    >
      <h2 class="text-md font-semibold">
        Проблемные устройства
      </h2>
      <Card class="border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)]">
        <div class="space-y-3">
          <div
            v-for="device in problematicDevices"
            :key="device.id"
            class="flex items-center justify-between p-3 bg-[color:var(--bg-elevated)] rounded-lg"
          >
            <div>
              <div class="text-sm font-semibold">
                {{ device.uid || device.name }}
              </div>
              <div class="text-xs text-[color:var(--text-muted)] mt-1">
                {{ device.issues?.join(', ') || 'Проблема не указана' }}
              </div>
            </div>
            <div class="flex gap-2">
              <Link :href="`/devices/${device.id}`">
                <Button
                  size="sm"
                  variant="secondary"
                >
                  Открыть
                </Button>
              </Link>
              <Button
                size="sm"
                variant="outline"
                :disabled="restartingDevices.has(device.id)"
                @click="restartDevice(device.id)"
              >
                {{ restartingDevices.has(device.id) ? 'Перезапуск...' : 'Перезапустить' }}
              </Button>
            </div>
          </div>
        </div>
      </Card>
    </div>

    <!-- Системные метрики -->
    <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
      <Card>
        <div class="text-[color:var(--text-muted)] text-sm mb-1">
          Нагрузка CPU
        </div>
        <div class="text-3xl font-bold">
          {{ systemMetrics.cpu || '-' }}%
        </div>
        <div class="w-full bg-[color:var(--border-muted)] rounded-full h-2 mt-2">
          <div
            class="bg-[color:var(--accent-cyan)] h-2 rounded-full transition-all duration-300"
            :style="{ width: `${systemMetrics.cpu || 0}%` }"
          ></div>
        </div>
      </Card>
      <Card>
        <div class="text-[color:var(--text-muted)] text-sm mb-1">
          Память
        </div>
        <div class="text-3xl font-bold">
          {{ systemMetrics.memory || '-' }}%
        </div>
        <div class="w-full bg-[color:var(--border-muted)] rounded-full h-2 mt-2">
          <div
            class="bg-[color:var(--accent-green)] h-2 rounded-full transition-all duration-300"
            :style="{ width: `${systemMetrics.memory || 0}%` }"
          ></div>
        </div>
      </Card>
      <Card>
        <div class="text-[color:var(--text-muted)] text-sm mb-1">
          База данных
        </div>
        <div
          class="text-3xl font-bold"
          :class="systemMetrics.dbStatus === 'OK' ? 'text-[color:var(--accent-green)]' : 'text-[color:var(--accent-red)]'"
        >
          {{ systemMetrics.dbStatus === 'OK' ? '✅' : '❌' }}
        </div>
      </Card>
      <Card>
        <div class="text-[color:var(--text-muted)] text-sm mb-1">
          MQTT брокер
        </div>
        <div
          class="text-3xl font-bold"
          :class="systemMetrics.mqttStatus === 'OK' ? 'text-[color:var(--accent-green)]' : 'text-[color:var(--accent-red)]'"
        >
          {{ systemMetrics.mqttStatus === 'OK' ? '✅' : '❌' }}
        </div>
      </Card>
    </div>

    <ConfirmModal
      :open="restartModal.open"
      title="Перезапустить устройство"
      message="Перезапустить выбранное устройство сейчас?"
      confirm-text="Перезапустить"
      confirm-variant="warning"
      @close="restartModal = { open: false, deviceId: null }"
      @confirm="confirmRestart"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Link } from '@inertiajs/vue3'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import ConfirmModal from '@/Components/ConfirmModal.vue'
import { translateStatus } from '@/utils/i18n'
import { useApi } from '@/composables/useApi'
import { useFilteredList } from '@/composables/useFilteredList'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { logger } from '@/utils/logger'
import type { Device } from '@/types'

interface Props {
  dashboard: {
    devices?: Array<Device & {
      rssi?: number | null
      firmwareVersion?: string
      lastSeen?: string
      issues?: string[]
    }>
    systemMetrics?: {
      cpu?: number
      memory?: number
      dbStatus?: 'OK' | 'FAIL'
      mqttStatus?: 'OK' | 'FAIL'
    }
  }
}

const props = defineProps<Props>()

const { api } = useApi()
const { showToast } = useToast()

const testingDevices = ref<Set<number>>(new Set())
const restartingDevices = ref<Set<number>>(new Set())
const restartModal = ref<{ open: boolean; deviceId: number | null }>({ open: false, deviceId: null })

const devices = computed(() => props.dashboard.devices || [])

const problematicDevices = useFilteredList(devices, (d) => 
  ((d.status as string) !== 'ONLINE' && d.status !== 'online') || 
  (d.issues && d.issues.length > 0) ||
  (d.rssi !== null && d.rssi !== undefined && d.rssi < -80)
)

const systemMetrics = computed(() => props.dashboard.systemMetrics || {
  cpu: null,
  memory: null,
  dbStatus: 'OK',
  mqttStatus: 'OK'
})

function getRssiColor(rssi: number): string {
  if (rssi >= -50) return 'text-[color:var(--accent-green)]'
  if (rssi >= -70) return 'text-[color:var(--accent-amber)]'
  return 'text-[color:var(--accent-red)]'
}

function formatTimeAgo(timestamp: string | Date): string {
  const now = new Date()
  const time = new Date(timestamp)
  const diff = now.getTime() - time.getTime()
  const seconds = Math.floor(diff / 1000)
  
  if (seconds < 60) return `${seconds} сек назад`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} мин назад`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} ч назад`
  const days = Math.floor(hours / 24)
  return `${days} дн назад`
}

async function testDevice(deviceId: number) {
  if (testingDevices.value.has(deviceId)) {
    return
  }

  testingDevices.value.add(deviceId)
  
  try {
    const response = await api.post<{ status: string; data?: { command_id: string } }>(
      `/nodes/${deviceId}/commands`,
      {
        cmd: 'MEASURE_NOW',
        params: {},
      }
    )
    
    if (response.data?.status === 'ok') {
      logger.debug('[EngineerDashboard] Test command sent successfully', response.data)
      showToast('Команда тестирования отправлена устройству', 'success', TOAST_TIMEOUT.NORMAL)
    }
  } catch (err) {
    logger.error('[EngineerDashboard] Failed to send test command:', err)
    showToast('Не удалось отправить команду тестирования', 'error', TOAST_TIMEOUT.LONG)
  } finally {
    testingDevices.value.delete(deviceId)
  }
}

async function restartDevice(deviceId: number) {
  if (restartingDevices.value.has(deviceId)) {
    return
  }

  restartModal.value = { open: true, deviceId }
}

async function confirmRestart(): Promise<void> {
  const deviceId = restartModal.value.deviceId
  if (!deviceId) {
    return
  }

  restartingDevices.value.add(deviceId)
  
  try {
    const response = await api.post<{ status: string; data?: { command_id: string } }>(
      `/nodes/${deviceId}/commands`,
      {
        cmd: 'REBOOT',
        params: {},
      }
    )
    
    if (response.data?.status === 'ok') {
      logger.debug('[EngineerDashboard] Restart command sent successfully', response.data)
      showToast('Команда перезапуска отправлена устройству', 'success', TOAST_TIMEOUT.NORMAL)
    }
  } catch (err) {
    logger.error('[EngineerDashboard] Failed to send restart command:', err)
    showToast('Не удалось отправить команду перезапуска', 'error', TOAST_TIMEOUT.LONG)
  } finally {
    restartingDevices.value.delete(deviceId)
    restartModal.value = { open: false, deviceId: null }
  }
}
</script>
