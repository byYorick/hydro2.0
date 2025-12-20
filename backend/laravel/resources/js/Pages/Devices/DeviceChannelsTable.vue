<template>
  <div class="rounded-xl border border-[color:var(--border-muted)] overflow-hidden">
    <table class="min-w-full text-sm">
      <thead class="bg-[color:var(--bg-elevated)] text-[color:var(--text-muted)]">
        <tr>
          <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]">Channel</th>
          <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]">Type</th>
          <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]">Config</th>
          <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]">Actions</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(channel, idx) in (paginatedChannels || [])" :key="idx" class="odd:bg-[color:var(--bg-surface-strong)] even:bg-[color:var(--bg-surface)]">
          <td class="px-3 py-2 border-b border-[color:var(--border-muted)]">{{ channel.channel || channel.name || '-' }}</td>
          <td class="px-3 py-2 border-b border-[color:var(--border-muted)] uppercase">{{ channel.type || '-' }}</td>
          <td class="px-3 py-2 border-b border-[color:var(--border-muted)]">
            <div class="text-xs text-[color:var(--text-primary)]">
              <span v-if="renderConfig(channel)">{{ renderConfig(channel) }}</span>
              <span v-else>-</span>
            </div>
            <div v-if="channel.description || channel.config?.description" class="text-[11px] text-[color:var(--text-dim)]">
              {{ channel.description || channel.config?.description }}
            </div>
          </td>
          <td class="px-3 py-2 border-b border-[color:var(--border-muted)]">
            <div class="flex gap-2">
              <Button 
                v-if="isPumpOrValve(channel)"
                size="sm" 
                variant="primary" 
                @click="$emit('test', channel.channel || channel.name, channel.type)"
                :disabled="testingChannels && testingChannels.has(channel.channel || channel.name)"
              >
                <span v-if="testingChannels && testingChannels.has(channel.channel || channel.name)">Тестирование...</span>
                <span v-else>{{ getTestButtonLabel(channel.channel || channel.name, channel.type) }}</span>
              </Button>
              <Button 
                v-else
                size="sm" 
                variant="secondary" 
                @click="$emit('test', channel.channel || channel.name, channel.type)"
              >
                Test
              </Button>
            </div>
          </td>
        </tr>
        <tr v-if="!paginatedChannels || paginatedChannels.length === 0">
          <td colspan="4" class="px-3 py-4 text-center text-[color:var(--text-dim)]">Нет каналов</td>
        </tr>
      </tbody>
    </table>
    <Pagination
      v-if="channels && channels.length > perPage"
      v-model:current-page="currentPage"
      v-model:per-page="perPage"
      :total="channels ? channels.length : 0"
    />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import Button from '@/Components/Button.vue'
import Pagination from '@/Components/Pagination.vue'

const props = defineProps({
  channels: { type: Array, default: () => [] }, // [{channel,type,metric,unit}]
  nodeType: { type: String, default: '' }, // Тип ноды: ph_node, ec_node, pump_node
  testingChannels: { type: Set, default: () => new Set() }, // Множество каналов, которые сейчас тестируются
})

const currentPage = ref(1)
const perPage = ref(10)

const paginatedChannels = computed(() => {
  // Защита от undefined/null
  if (!props.channels || !Array.isArray(props.channels)) {
    return []
  }
  
  const total = props.channels.length
  if (total === 0) return []
  
  // Защита от некорректных значений
  const maxPage = Math.ceil(total / perPage.value) || 1
  const validPage = Math.min(currentPage.value, maxPage)
  if (validPage !== currentPage.value) {
    currentPage.value = validPage
  }
  
  const start = (validPage - 1) * perPage.value
  const end = start + perPage.value
  return props.channels.slice(start, end)
})

// Проверка, является ли канал насосом или клапаном
function isPumpOrValve(channel) {
  if (!channel) return false
  const name = ((channel.channel || channel.name || '') + '').toLowerCase()
  const type = ((channel.type || '') + '').toLowerCase()
  return name.includes('pump') || name.includes('насос') || name.includes('valve') || name.includes('клапан') || type === 'actuator' || type === 'ACTUATOR'
}

// Получение названия кнопки теста в зависимости от типа ноды и канала
function getTestButtonLabel(channelName, channelType) {
  if (!channelName) return 'Test'
  const name = (channelName + '').toLowerCase()
  const nodeType = ((props.nodeType || '') + '').toLowerCase()
  
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
    if (name.includes('nutrient')) return 'Тест насоса'
  }
  
  // Pump нода
  if (nodeType.includes('pump')) {
    if (name.includes('main') || name.includes('primary') || name.includes('главн')) return 'Тест главного насоса'
    if (name.includes('backup') || name.includes('reserve') || name.includes('резерв')) return 'Тест резервного насоса'
    if (name.includes('transfer') || name.includes('перекач')) return 'Тест перекачивающего насоса'
    if (name.includes('valve') || (channelType && (channelType + '').toLowerCase() === 'valve') || name.includes('клапан')) return 'Тест клапана'
  }
  
  // Общий случай для насосов
  if (name.includes('pump') || name.includes('насос')) {
    return 'Тест насоса'
  }
  
  // Для клапанов
  if (name.includes('valve') || name.includes('клапан')) {
    return 'Тест клапана'
  }
  
  return 'Test'
}

function renderConfig(channel) {
  if (!channel) return ''

  const cfg = channel.config || {}
  const metric = channel.metric || cfg.metric
  const actuatorType = channel.actuator_type || cfg.actuator_type
  const parts = []

  if (metric) {
    parts.push(metric)
  }

  if (actuatorType) {
    parts.push(actuatorType)
  }

  if (parts.length === 0 && channel.unit) {
    parts.push(channel.unit)
  }

  return parts.join(' · ')
}
</script>
