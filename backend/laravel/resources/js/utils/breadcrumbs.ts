export interface BreadcrumbItem {
  label: string
  href?: string
}

const SKIP_PATH_PARTS = new Set(['login', 'register', 'forgot-password', 'reset-password'])

const PATH_LABELS: Record<string, string> = {
  zones: 'Зоны',
  devices: 'Узлы',
  nodes: 'Узлы',
  recipes: 'Рецепты',
  alerts: 'Тревоги',
  settings: 'Настройки',
  users: 'Пользователи',
  system: 'Система',
  logs: 'Логи',
  analytics: 'Аналитика',
  audit: 'Журнал',
  setup: 'Настройка',
  greenhouses: 'Теплицы',
  admin: 'Администрирование',
  monitoring: 'Здоровье системы',
  launch: 'Запуск',
  plants: 'Культуры',
  nutrients: 'Питание',
  profile: 'Профиль',
}

const HOME_LABELS: Record<string, string> = {
  operator: 'Сегодня',
  agronomist: 'Обзор',
  engineer: 'Обзор',
  admin: 'Система',
  viewer: 'Обзор',
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  return null
}

function text(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) {
    return value
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value)
  }
  return null
}

function named(record: Record<string, unknown> | null, keys: string[]): string | null {
  if (!record) {
    return null
  }
  for (const key of keys) {
    const value = text(record[key])
    if (value) {
      return value
    }
  }
  return null
}

export function pathnameFromPageUrl(url: string): string {
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

function labelForPart(part: string, previous: string | undefined, pageProps: Record<string, unknown>): string {
  if (/^\d+$/.test(part)) {
    const zone = asRecord(pageProps.zone)
    const device = asRecord(pageProps.device)
    const recipe = asRecord(pageProps.recipe)
    const greenhouse = asRecord(pageProps.greenhouse)

    if (previous === 'zones') {
      return named(zone, ['name']) ?? `#${part}`
    }
    if (previous === 'devices' || previous === 'nodes') {
      return named(device, ['name', 'uid']) ?? `#${part}`
    }
    if (previous === 'recipes') {
      return named(recipe, ['name']) ?? `#${part}`
    }
    if (previous === 'greenhouses') {
      return named(greenhouse, ['name']) ?? `#${part}`
    }

    return named(zone, ['name'])
      ?? named(device, ['name', 'uid'])
      ?? named(recipe, ['name'])
      ?? named(greenhouse, ['name'])
      ?? `#${part}`
  }

  return PATH_LABELS[part] || part.charAt(0).toUpperCase() + part.slice(1)
}

function detailIndex(pathParts: string[], parents: string[]): number {
  return pathParts.findIndex((part, index) => parents.includes(pathParts[index - 1] ?? '') && /^\d+$/.test(part))
}

function enrichHierarchy(
  items: BreadcrumbItem[],
  pathParts: string[],
  pageProps: Record<string, unknown>,
): BreadcrumbItem[] {
  const next = [...items]
  const zone = asRecord(pageProps.zone)
  const device = asRecord(pageProps.device)

  if (detailIndex(pathParts, ['zones']) >= 0) {
    const greenhouse = asRecord(zone?.greenhouse)
    const greenhouseName = named(greenhouse, ['name'])
    const greenhouseId = text(greenhouse?.id)
    if (greenhouseName && !next.some((item) => item.label === greenhouseName)) {
      const crumb: BreadcrumbItem = {
        label: greenhouseName,
        href: greenhouseId ? `/greenhouses/${greenhouseId}` : '/greenhouses',
      }
      const zonesIndex = next.findIndex((item) => item.label === 'Зоны')
      next.splice(zonesIndex >= 0 ? zonesIndex : 1, 0, crumb)
    }
  }

  if (detailIndex(pathParts, ['devices', 'nodes']) >= 0) {
    const deviceZone = asRecord(device?.zone)
    const greenhouse = asRecord(deviceZone?.greenhouse) ?? asRecord(device?.greenhouse)
    const greenhouseName = named(greenhouse, ['name'])
    const greenhouseId = text(greenhouse?.id)
    const zoneName = named(deviceZone, ['name'])
    const zoneId = text(deviceZone?.id) ?? text(device?.zone_id)
    const extra: BreadcrumbItem[] = []
    if (greenhouseName) {
      extra.push({
        label: greenhouseName,
        href: greenhouseId ? `/greenhouses/${greenhouseId}` : '/greenhouses',
      })
    }
    if (zoneName) {
      extra.push({
        label: zoneName,
        href: zoneId ? `/zones/${zoneId}` : '/zones',
      })
    }
    const insertAt = next.findIndex((item) => item.label === 'Узлы')
    if (extra.length > 0 && insertAt >= 0) {
      const existing = new Set(next.map((item) => item.label))
      next.splice(insertAt, 0, ...extra.filter((item) => !existing.has(item.label)))
    }
  }

  return next
}

export function buildAutoBreadcrumbs(url: string, pageProps: Record<string, unknown>): BreadcrumbItem[] {
  const user = asRecord(asRecord(pageProps.auth)?.user)
  const role = text(user?.role) ?? 'viewer'
  const pathParts = pathnameFromPageUrl(url).split('/').filter(Boolean).map(decodePathPart)
  const items: BreadcrumbItem[] = [
    { label: HOME_LABELS[role] ?? 'Обзор', href: '/' },
  ]

  let currentPath = ''
  pathParts.forEach((part, index) => {
    if (SKIP_PATH_PARTS.has(part.toLowerCase())) {
      return
    }
    currentPath += `/${part}`
    items.push({
      label: labelForPart(part, pathParts[index - 1], pageProps),
      href: currentPath,
    })
  })

  return enrichHierarchy(items, pathParts, pageProps)
}
