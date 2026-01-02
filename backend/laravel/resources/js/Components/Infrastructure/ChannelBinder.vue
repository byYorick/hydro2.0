<template>
  <Card data-testid="channel-binder">
    <div class="space-y-4">
      <div>
        <h3 class="text-sm font-semibold mb-2">
          Привязка каналов к ролям
        </h3>
        <p class="text-xs text-[color:var(--text-muted)] mb-4">
          Выберите ноды и назначьте роли каналам для работы оборудования
        </p>
      </div>

      <div
        v-if="!nodes || nodes.length === 0"
        class="text-sm text-[color:var(--text-muted)]"
      >
        Нет доступных нод в зоне
      </div>

      <div
        v-else
        class="space-y-4"
      >
        <div
          v-for="node in nodes"
          :key="node.id"
          :data-testid="`node-card-${node.id}`"
          class="p-4 rounded border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)]"
        >
          <div class="flex items-center justify-between mb-3">
            <div>
              <div
                class="font-medium text-sm"
                :data-testid="`node-name-${node.id}`"
              >
                {{ node.name }} ({{ node.uid }})
              </div>
              <div class="text-xs text-[color:var(--text-muted)]">
                {{ node.type }}
              </div>
            </div>
            <Badge
              :variant="node.is_online ? 'success' : 'danger'"
              size="sm"
              :data-testid="`node-status-${node.id}`"
            >
              {{ node.is_online ? 'Online' : 'Offline' }}
            </Badge>
          </div>

          <div
            v-if="node.channels && node.channels.length > 0"
            class="space-y-2"
          >
            <div
              v-for="channel in node.channels"
              :key="channel.id"
              :data-testid="`channel-item-${channel.id}`"
              class="flex items-center gap-2 p-2 rounded bg-[color:var(--bg-elevated)]"
            >
              <div class="flex-1">
                <div
                  class="text-xs font-medium"
                  :data-testid="`channel-name-${channel.id}`"
                >
                  {{ channel.channel }}
                </div>
                <div class="text-xs text-[color:var(--text-muted)]">
                  {{ channel.metric }} {{ channel.unit || '' }}
                </div>
              </div>
              <select
                :value="getBindingForChannel(channel.id)"
                :data-testid="`channel-role-select-${channel.id}`"
                class="input-select h-8 text-xs min-w-[140px]"
                @change="updateBinding(channel.id, node.id, $event.target.value)"
              >
                <option :value="null">
                  Не назначено
                </option>
                <option
                  v-for="role in availableRoles"
                  :key="role.value"
                  :value="role.value"
                >
                  {{ role.label }}
                </option>
              </select>
            </div>
          </div>
          <div
            v-else
            class="text-xs text-[color:var(--text-dim)]"
          >
            Нет доступных каналов
          </div>
        </div>
      </div>

      <div
        v-if="bindings.length > 0"
        class="mt-4 p-3 rounded border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)]"
      >
        <div class="text-xs text-[color:var(--text-muted)] mb-2">
          Привязанные каналы:
        </div>
        <div class="space-y-1">
          <div
            v-for="binding in bindings"
            :key="`${binding.node_id}-${binding.channel_id}`"
            :data-testid="`bound-channel-item-${binding.node_id}-${binding.channel_id}`"
            class="text-xs"
          >
            <span class="text-[color:var(--text-primary)]">{{ getNodeName(binding.node_id) }}</span>
            <span class="text-[color:var(--text-dim)]"> → </span>
            <span class="text-[color:var(--accent-cyan)]">{{ getRoleLabel(binding.role) }}</span>
          </div>
        </div>
      </div>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import Card from '@/Components/Card.vue'
import Badge from '@/Components/Badge.vue'

interface Channel {
  id: number
  channel: string
  type: string
  metric: string
  unit?: string
}

interface Node {
  id: number
  uid: string
  name: string
  type: string
  is_online: boolean
  channels: Channel[]
}

interface ChannelBinding {
  node_id: number
  channel_id: number
  role: string
}

interface Props {
  nodes: Node[]
  modelValue?: ChannelBinding[]
}

const props = withDefaults(defineProps<Props>(), {
  nodes: () => [],
  modelValue: () => [],
})

const emit = defineEmits<{
  'update:modelValue': [value: ChannelBinding[]]
}>()

const bindings = ref<ChannelBinding[]>(props.modelValue || [])

const availableRoles = [
  { value: 'main_pump', label: 'Основная помпа' },
  { value: 'drain', label: 'Дренаж' },
  { value: 'mist', label: 'Туман' },
  { value: 'light', label: 'Свет' },
  { value: 'vent', label: 'Вентиляция' },
  { value: 'heater', label: 'Отопление' },
]

function getBindingForChannel(channelId: number): string | null {
  const binding = bindings.value.find(b => b.channel_id === channelId)
  return binding?.role || null
}

function updateBinding(channelId: number, nodeId: number, role: string | null) {
  const index = bindings.value.findIndex(b => b.channel_id === channelId)
  
  if (role === null || role === '') {
    // Удаляем привязку
    if (index >= 0) {
      bindings.value.splice(index, 1)
    }
  } else {
    // Обновляем или создаем привязку
    if (index >= 0) {
      bindings.value[index].role = role
    } else {
      bindings.value.push({
        node_id: nodeId,
        channel_id: channelId,
        role: role,
      })
    }
  }
  
  emit('update:modelValue', bindings.value)
}

function getNodeName(nodeId: number): string {
  const node = props.nodes.find(n => n.id === nodeId)
  return node ? `${node.name} (${node.uid})` : `Node ${nodeId}`
}

function getRoleLabel(role: string): string {
  const roleObj = availableRoles.find(r => r.value === role)
  return roleObj?.label || role
}

defineExpose({
  getBindings: () => bindings.value,
})
</script>
