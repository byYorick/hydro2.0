<template>
  <AppLayout>
    <!-- Toast notifications -->
    <Teleport to="body">
      <div 
        class="fixed top-4 right-4 z-[10000] space-y-2 pointer-events-none"
        style="position: fixed !important; top: 1rem !important; right: 1rem !important; z-index: 10000 !important; pointer-events: none;"
      >
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="pointer-events-auto"
          style="pointer-events: auto;"
        >
          <Toast
            :message="toast.message"
            :variant="toast.variant"
            :duration="toast.duration"
            @close="removeToast(toast.id)"
          />
        </div>
      </div>
    </Teleport>
    
    <div class="flex items-center justify-between mb-3">
      <div>
        <div class="text-lg font-semibold">{{ device.uid || device.name || device.id }}</div>
        <div class="text-xs text-neutral-400">
          <span v-if="device.zone">
            <Link :href="`/zones/${device.zone.id}`" class="text-sky-400 hover:underline">Zone: {{ device.zone.name }}</Link>
          </span>
          <span v-else>Zone: -</span>
          · Type: {{ device.type || '-' }}
          <span v-if="device.fw_version"> · FW: {{ device.fw_version }}</span>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <Badge :variant="device.status === 'online' ? 'success' : device.status === 'offline' ? 'danger' : 'neutral'">
          {{ device.status?.toUpperCase() || 'UNKNOWN' }}
        </Badge>
        <Button size="sm" variant="secondary" @click="onRestart">Restart</Button>
      </div>
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-3 gap-3">
      <Card class="xl:col-span-2">
        <div class="text-sm font-semibold mb-2">Channels</div>
        <DeviceChannelsTable 
          :channels="channels" 
          :node-type="device.type"
          :testing-channels="testingChannels"
          @test="onTestPump" 
        />
      </Card>
      <Card>
        <div class="text-sm font-semibold mb-2">NodeConfig</div>
        <pre class="text-xs text-neutral-300 overflow-auto">{{ nodeConfig }}</pre>
      </Card>
    </div>
  </AppLayout>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Link, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import DeviceChannelsTable from '@/Pages/Devices/DeviceChannelsTable.vue'
import Toast from '@/Components/Toast.vue'
import axios from 'axios'

const page = usePage()
const device = computed(() => page.props.device || {})
const channels = computed(() => device.value.channels || [])
const testingChannels = ref(new Set())
const toasts = ref([])
let toastIdCounter = 0

const nodeConfig = computed(() => {
  const config = {
    id: device.value.uid || device.value.id,
    name: device.value.name,
    type: device.value.type,
    status: device.value.status,
    fw_version: device.value.fw_version,
    config: device.value.config,
    channels: channels.value.map(c => ({
      channel: c.channel,
      type: c.type,
      metric: c.metric,
      unit: c.unit,
    })),
  }
  return JSON.stringify(config, null, 2)
})

function showToast(message, variant = 'info', duration = 3000) {
  const id = ++toastIdCounter
  toasts.value.push({ id, message, variant, duration })
  return id
}

function removeToast(id) {
  const index = toasts.value.findIndex(t => t.id === id)
  if (index > -1) {
    toasts.value.splice(index, 1)
  }
}

const onRestart = async () => {
  try {
    const response = await axios.post(`/api/nodes/${device.value.id}/commands`, {
      type: 'restart',
      params: {},
    }, {
      headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    })
    
    if (response.data?.status === 'ok') {
      console.log('Device restart command sent successfully', response.data)
      // Можно добавить toast уведомление здесь
    }
  } catch (err) {
    console.error('Failed to restart device:', err)
    const errorMsg = err.response?.data?.message || err.message || 'Неизвестная ошибка'
    console.error('Error details:', errorMsg)
  }
}

// Функция для теста конкретного насоса/клапана
const onTestPump = async (channelName, channelType) => {
  if (testingChannels.value.has(channelName)) return
  
  testingChannels.value.add(channelName)
  const channelLabel = getChannelLabel(channelName, channelType)
  showToast(`Запуск теста: ${channelLabel}...`, 'info', 2000)
  
  try {
    // Определяем команду в зависимости от типа канала
    let commandType = 'run_pump'
    let params = { duration_ms: 3000 } // 3 секунды
    
    // Для клапанов используем другую команду (заглушка)
    if (channelType === 'valve' || channelName.includes('valve')) {
      commandType = 'set_relay'
      params = { state: true, duration_ms: 3000 }
    }
    
    const response = await axios.post(`/api/nodes/${device.value.id}/commands`, {
      type: commandType,
      channel: channelName,
      params: params,
    }, {
      headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    })
    
    if (response.data?.status === 'ok' && response.data?.data?.command_id) {
      const cmdId = response.data.data.command_id
      // Ожидаем ответа от ноды
      const result = await checkCommandStatus(cmdId, 30) // Максимум 15 секунд
      
      if (result.success) {
        showToast(`Тест ${channelLabel} выполнен успешно!`, 'success', 5000)
      } else {
        showToast(`Ошибка теста ${channelLabel}: ${result.status}`, 'error', 5000)
      }
    } else {
      showToast(`Не удалось отправить команду для ${channelLabel}`, 'error', 5000)
    }
  } catch (err) {
    console.error(`Failed to test ${channelName}:`, err)
    const errorMsg = err.response?.data?.message || err.message || 'Неизвестная ошибка'
    showToast(`Ошибка теста ${channelLabel}: ${errorMsg}`, 'error', 5000)
  } finally {
    testingChannels.value.delete(channelName)
  }
}

// Функция для получения читаемого названия канала
function getChannelLabel(channelName, channelType) {
  const name = (channelName || '').toLowerCase()
  const nodeType = (device.value.type || '').toLowerCase()
  
  // PH нода
  if (nodeType.includes('ph')) {
    if (name.includes('acid') || name.includes('up')) return 'PH UP тест'
    if (name.includes('base') || name.includes('down')) return 'PH DOWN тест'
  }
  
  // EC нода
  if (nodeType.includes('ec')) {
    if (name.includes('nutrient_a') || name.includes('pump_a')) return 'Тест насоса A'
    if (name.includes('nutrient_b') || name.includes('pump_b')) return 'Тест насоса B'
    if (name.includes('nutrient_c') || name.includes('pump_c')) return 'Тест насоса C'
    if (name.includes('nutrient')) return 'Тест насоса питательного раствора'
  }
  
  // Pump нода
  if (nodeType.includes('pump')) {
    if (name.includes('main') || name.includes('primary')) return 'Тест главного насоса'
    if (name.includes('backup') || name.includes('reserve') || name.includes('reserve')) return 'Тест резервного насоса'
    if (name.includes('transfer') || name.includes('перекач')) return 'Тест перекачивающего насоса'
    if (name.includes('valve') || channelType === 'valve') return 'Тест клапана'
  }
  
  // Общий случай
  return channelName || 'Канал'
}

// Функция для проверки статуса команды
async function checkCommandStatus(cmdId, maxAttempts = 30) {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const response = await axios.get(`/api/commands/${cmdId}/status`, {
        headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      })
      
      if (response.data?.status === 'ok') {
        const cmdStatus = response.data.data.status
        if (cmdStatus === 'ack') {
          return { success: true, status: 'ack' }
        } else if (cmdStatus === 'failed') {
          return { success: false, status: 'failed' }
        } else if (cmdStatus === 'pending') {
          // Продолжаем ожидание
          await new Promise(resolve => setTimeout(resolve, 500))
          continue
        }
      }
    } catch (err) {
      console.error('Failed to check command status:', err)
      // Если команда не найдена, возможно она еще не создана, продолжаем ожидание
      if (err.response?.status === 404 && i < maxAttempts - 1) {
        await new Promise(resolve => setTimeout(resolve, 500))
        continue
      }
      return { success: false, status: 'error', error: err.message }
    }
  }
  return { success: false, status: 'timeout' }
}

</script>

