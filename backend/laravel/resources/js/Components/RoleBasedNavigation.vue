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
    { label: 'Растения', href: '/plants', order: 22 },
    { label: 'Аналитика', href: '/analytics', order: 23 },
  ],
  admin: [
    { label: 'Зоны', href: '/zones', order: 30 },
    { label: 'Устройства', href: '/devices', order: 31 },
    { label: 'Рецепты', href: '/recipes', order: 32 },
    { label: 'Растения', href: '/plants', order: 33 },
    { label: 'Пользователи', href: '/users', order: 34 },
    { label: 'Аудит', href: '/audit', order: 35 },
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
    { label: 'Растения', href: '/plants', order: 53 },
    { label: 'Логи', href: '/logs', order: 54 },
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

  if (isAgronomist.value) addItems(buildRoleItems().agronomist)
  if (isAdmin.value) addItems(buildRoleItems().admin)
  if (isEngineer.value) addItems(buildRoleItems().engineer)
  if (isOperator.value) addItems(buildRoleItems().operator)
  if (isViewer.value) addItems(buildRoleItems().viewer)

  if (!isViewer.value) {
    addItems([settingsItem])
  }

  return Array.from(aggregator.values()).sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
})
</script>
