<template>
  <nav v-if="items.length > 0" class="flex items-center gap-2 text-sm mb-4" aria-label="Breadcrumb">
    <ol class="flex items-center gap-2 flex-wrap">
      <li v-for="(item, index) in items" :key="index" class="flex items-center gap-2">
        <Link
          v-if="item.href && index < items.length - 1"
          :href="item.href"
          class="text-neutral-400 hover:text-neutral-200 transition-colors"
        >
          {{ item.label }}
        </Link>
        <span
          v-else
          class="text-neutral-200 font-medium"
          :class="{ 'text-neutral-400': index < items.length - 1 }"
        >
          {{ item.label }}
        </span>
        <svg
          v-if="index < items.length - 1"
          class="w-4 h-4 text-neutral-600 shrink-0"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
      </li>
    </ol>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Link, usePage } from '@inertiajs/vue3'

interface BreadcrumbItem {
  label: string
  href?: string
}

interface Props {
  items?: BreadcrumbItem[]
  autoGenerate?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  items: () => [],
  autoGenerate: true,
})

const page = usePage()

// Автоматическая генерация breadcrumbs на основе URL
const autoItems = computed(() => {
  if (!props.autoGenerate) return []
  
  const url = page.url
  const pathParts = url.split('/').filter(Boolean)
  
  const items: BreadcrumbItem[] = [
    { label: 'Панель управления', href: '/' }
  ]
  
  // Маппинг путей к названиям
  const pathLabels: Record<string, string> = {
    'zones': 'Зоны',
    'devices': 'Устройства',
    'recipes': 'Рецепты',
    'alerts': 'Алерты',
    'settings': 'Настройки',
    'users': 'Пользователи',
    'system': 'Система',
    'logs': 'Логи',
    'analytics': 'Аналитика',
    'audit': 'Аудит',
    'setup': 'Настройка',
    'greenhouses': 'Теплицы',
    'admin': 'Администрирование',
  }
  
  let currentPath = ''
  pathParts.forEach((part, index) => {
    currentPath += `/${part}`
    
    // Пропускаем числовые ID (детальные страницы)
    if (/^\d+$/.test(part)) {
      // Пытаемся получить имя из props страницы
      const pageProps = page.props as any
      let label = `#${part}`
      
      // Пытаемся найти имя в разных местах
      if (pageProps.zone?.name) {
        label = pageProps.zone.name
      } else if (pageProps.device?.name || pageProps.device?.uid) {
        label = pageProps.device.name || pageProps.device.uid
      } else if (pageProps.recipe?.name) {
        label = pageProps.recipe.name
      } else if (pageProps.greenhouse?.name) {
        label = pageProps.greenhouse.name
      }
      
      items.push({ label, href: currentPath })
    } else {
      const label = pathLabels[part] || part.charAt(0).toUpperCase() + part.slice(1)
      items.push({ label, href: currentPath })
    }
  })
  
  return items
})

const items = computed(() => {
  return props.items.length > 0 ? props.items : autoItems.value
})
</script>

<style scoped>
/* Дополнительные стили при необходимости */
</style>

