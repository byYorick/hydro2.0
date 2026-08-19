<template>
  <nav
    v-if="items.length > 0"
    class="flex items-center gap-1.5 text-xs"
    aria-label="Breadcrumb"
  >
    <ol class="flex items-center gap-2 flex-wrap">
      <li
        v-for="(item, index) in items"
        :key="index"
        class="flex items-center gap-1.5"
      >
        <Link
          v-if="item.href && index < items.length - 1"
          :href="item.href"
          class="text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)] transition-colors"
        >
          {{ item.label }}
        </Link>
        <span
          v-else
          class="text-[color:var(--text-primary)] font-medium"
          :class="{ 'text-[color:var(--text-muted)]': index < items.length - 1 }"
        >
          {{ item.label }}
        </span>
        <svg
          v-if="index < items.length - 1"
          class="w-3 h-3 text-[color:var(--text-dim)] shrink-0"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M9 5l7 7-7 7"
          />
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

const SKIP_PATH_PARTS = new Set(['login', 'register', 'forgot-password', 'reset-password'])

function pathnameFromPageUrl(url: string): string {
  const withoutHash = url.split('#')[0] ?? url
  const pathname = withoutHash.split('?')[0] ?? withoutHash
  return pathname.startsWith('/') ? pathname : `/${pathname}`
}

function decodePathPart(part: string): string {
  try {
    return decodeURIComponent(part)
  } catch {
    return part
  }
}

// Автоматическая генерация breadcrumbs на основе URL
const autoItems = computed(() => {
  if (!props.autoGenerate) return []

  const pathname = pathnameFromPageUrl(String(page.url || '/'))
  const pathParts = pathname.split('/').filter(Boolean).map(decodePathPart)
  
  const role = (page.props.auth as { user?: { role?: string } })?.user?.role || 'viewer'
  const homeLabels: Record<string, string> = {
    operator: 'Сегодня',
    agronomist: 'Обзор',
    engineer: 'Обзор',
    admin: 'Система',
    viewer: 'Обзор',
  }

  const items: BreadcrumbItem[] = [
    { label: homeLabels[role] ?? 'Обзор', href: '/' }
  ]
  
  const pathLabels: Record<string, string> = {
    'zones': 'Зоны',
    'devices': 'Узлы',
    'recipes': 'Рецепты',
    'alerts': 'Тревоги',
    'settings': 'Настройки',
    'users': 'Пользователи',
    'system': 'Система',
    'logs': 'Логи',
    'analytics': 'Аналитика',
    'audit': 'Журнал',
    'setup': 'Настройка',
    'greenhouses': 'Теплицы',
    'admin': 'Администрирование',
    'monitoring': 'Здоровье системы',
    'launch': 'Запуск',
  }
  
  let currentPath = ''
  pathParts.forEach((part) => {
    if (SKIP_PATH_PARTS.has(part.toLowerCase())) {
      return
    }

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
