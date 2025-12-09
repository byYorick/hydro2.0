<template>
  <div class="rounded-xl border border-neutral-800 overflow-hidden">
    <table class="min-w-full text-sm">
      <thead class="bg-neutral-900 text-neutral-300">
        <tr>
          <th class="px-3 py-2 text-left font-medium border-b border-neutral-800">Channel</th>
          <th class="px-3 py-2 text-left font-medium border-b border-neutral-800">Type</th>
          <th class="px-3 py-2 text-left font-medium border-b border-neutral-800">Config</th>
          <th class="px-3 py-2 text-left font-medium border-b border-neutral-800">Actions</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(channel, idx) in channels" :key="idx" class="odd:bg-neutral-950 even:bg-neutral-925">
          <td class="px-3 py-2 border-b border-neutral-900">{{ channel.channel || channel.name || '-' }}</td>
          <td class="px-3 py-2 border-b border-neutral-900 uppercase">{{ channel.type || '-' }}</td>
          <td class="px-3 py-2 border-b border-neutral-900">
            <div class="text-xs text-neutral-200">
              <span v-if="renderConfig(channel)">{{ renderConfig(channel) }}</span>
              <span v-else>-</span>
            </div>
            <div v-if="channel.description || channel.config?.description" class="text-[11px] text-neutral-500">
              {{ channel.description || channel.config?.description }}
            </div>
          </td>
          <td class="px-3 py-2 border-b border-neutral-900">
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
        <tr v-if="channels.length === 0">
          <td colspan="4" class="px-3 py-4 text-center text-neutral-400">Нет каналов</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import Button from '@/Components/Button.vue'

const props = defineProps({
  channels: { type: Array, default: () => [] }, // [{channel,type,metric,unit}]
  nodeType: { type: String, default: '' }, // Тип ноды: ph_node, ec_node, pump_node
  testingChannels: { type: Set, default: () => new Set() }, // Множество каналов, которые сейчас тестируются
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
