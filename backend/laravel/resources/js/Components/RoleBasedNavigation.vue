<template>
  <nav class="space-y-1">
    <NavLink
      v-for="item in navigationItems"
      :key="item.href"
      :href="item.href"
      :label="item.label"
    />
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRole } from '@/composables/useRole'
import NavLink from '@/Components/NavLink.vue'

interface NavItem {
  href: string
  label: string
  order?: number
}

const {
  isAgronomist,
  isAdmin,
  isEngineer,
  isOperator,
  isViewer,
} = useRole()

const buildRoleItems = (): Record<string, NavItem[]> => ({
  agronomist: [
    { label: 'Зоны', href: '/zones', order: 20 },
    { label: 'Рецепты', href: '/recipes', order: 21 },
    { label: 'Аналитика', href: '/analytics', order: 22 },
  ],
  admin: [
    { label: 'Зоны', href: '/zones', order: 30 },
    { label: 'Устройства', href: '/devices', order: 31 },
    { label: 'Рецепты', href: '/recipes', order: 32 },
    { label: 'Пользователи', href: '/users', order: 33 },
    { label: 'Аудит', href: '/audit', order: 34 },
  ],
  engineer: [
    { label: 'Зоны', href: '/zones', order: 40 },
    { label: 'Устройства', href: '/devices', order: 41 },
    { label: 'Система', href: '/system', order: 42 },
    { label: 'Логи', href: '/logs', order: 43 },
  ],
  operator: [
    { label: 'Зоны', href: '/zones', order: 50 },
    { label: 'Устройства', href: '/devices', order: 51 },
    { label: 'Рецепты', href: '/recipes', order: 52 },
    { label: 'Логи', href: '/logs', order: 53 },
  ],
  viewer: [
    { label: 'Зоны', href: '/zones', order: 60 },
    { label: 'Устройства', href: '/devices', order: 61 },
    { label: 'Рецепты', href: '/recipes', order: 62 },
  ],
})

const commonItems: NavItem[] = [
  { href: '/', label: 'Панель управления', order: 1 },
  { href: '/alerts', label: 'Алерты', order: 10 },
]

const settingsItem: NavItem = { href: '/settings', label: 'Настройки', order: 99 }

const navigationItems = computed(() => {
  const aggregator = new Map<string, NavItem>()
  const addItems = (items: NavItem[]) => {
    items.forEach((item) => {
      if (!aggregator.has(item.href)) {
        aggregator.set(item.href, item)
      }
    })
  }

  addItems(commonItems)

  if (isAgronomist) addItems(buildRoleItems().agronomist)
  if (isAdmin) addItems(buildRoleItems().admin)
  if (isEngineer) addItems(buildRoleItems().engineer)
  if (isOperator) addItems(buildRoleItems().operator)
  if (isViewer) addItems(buildRoleItems().viewer)

  if (!isViewer) {
    addItems([settingsItem])
  }

  return Array.from(aggregator.values()).sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
})
</script>
