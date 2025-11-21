<template>
  <Badge 
    :variant="variant"
    :title="tooltip"
  >
    {{ label }}
  </Badge>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Badge from './Badge.vue'
import type { NodeLifecycleState } from '@/types/Device'

type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

interface Props {
  lifecycleState?: NodeLifecycleState | null
}

const props = defineProps<Props>()

/**
 * Получить человекочитаемую метку состояния
 */
const label = computed(() => {
  if (!props.lifecycleState) return 'Неизвестно'
  
  const labels: Record<NodeLifecycleState, string> = {
    MANUFACTURED: 'Произведён',
    UNPROVISIONED: 'Не настроен',
    PROVISIONED_WIFI: 'Wi-Fi настроен',
    REGISTERED_BACKEND: 'Зарегистрирован',
    ASSIGNED_TO_ZONE: 'Привязан к зоне',
    ACTIVE: 'Активен',
    DEGRADED: 'С проблемами',
    MAINTENANCE: 'Обслуживание',
    DECOMMISSIONED: 'Списан',
  }
  
  return labels[props.lifecycleState] || props.lifecycleState
})

/**
 * Получить вариант Badge в зависимости от состояния
 */
const variant = computed<BadgeVariant>(() => {
  if (!props.lifecycleState) return 'neutral'
  
  switch (props.lifecycleState) {
    case 'ACTIVE':
      return 'success'
    case 'REGISTERED_BACKEND':
    case 'ASSIGNED_TO_ZONE':
      return 'info'
    case 'DEGRADED':
    case 'MAINTENANCE':
      return 'warning'
    case 'DECOMMISSIONED':
      return 'danger'
    default:
      return 'neutral'
  }
})

/**
 * Tooltip с дополнительной информацией
 */
const tooltip = computed(() => {
  if (!props.lifecycleState) return ''
  
  const descriptions: Record<NodeLifecycleState, string> = {
    MANUFACTURED: 'Узел произведён, но ещё не настроен',
    UNPROVISIONED: 'Узел не настроен (Wi-Fi, конфигурация)',
    PROVISIONED_WIFI: 'Wi-Fi настроен, ожидает регистрации',
    REGISTERED_BACKEND: 'Узел зарегистрирован в системе, готов к присвоению',
    ASSIGNED_TO_ZONE: 'Узел привязан к зоне, ожидает активации',
    ACTIVE: 'Узел активен и работает нормально',
    DEGRADED: 'Узел работает, но есть проблемы',
    MAINTENANCE: 'Узел на обслуживании',
    DECOMMISSIONED: 'Узел списан и больше не используется',
  }
  
  return descriptions[props.lifecycleState] || ''
})
</script>

