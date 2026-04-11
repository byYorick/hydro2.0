/**
 * Router Guards - защита от циклических перезагрузок
 * 
 * Предотвращает бесконечные циклы перезагрузок через Inertia.js router.reload() и router.visit()
 * 
 * Использование:
 *   import { setupRouterGuards } from '@/utils/routerGuards'
 *   setupRouterGuards(router)
 */
import { router } from '@inertiajs/vue3'
import { logger } from './logger'

// Маркер для определения обёрнутых методов (защита от HMR наложения обёрток)
const WRAPPER_MARKER = Symbol('routerWrapper')

type ReloadMethod = typeof router.reload
type VisitMethod = typeof router.visit
type ReloadOptions = Parameters<ReloadMethod>[0]
type VisitFirstArg = Parameters<VisitMethod>[0]
type VisitOptions = Parameters<VisitMethod>[1]

// Обёрнутые методы router помечаются Symbol-маркером; тип расширяем тут,
// чтобы читать маркер без `any`.
type MarkedRouterMethod<T extends (...args: never[]) => unknown> = T & {
  [WRAPPER_MARKER]?: true
}

interface OriginalRouterMethods {
  reload: ReloadMethod | null
  visit: VisitMethod | null
  isWrapped: boolean
}

// Храним оригинальные методы router для предотвращения наложения обёрток при HMR
const originalRouterMethods: OriginalRouterMethods = {
  reload: null,
  visit: null,
  isWrapped: false,
}

// Счётчики для отслеживания перезагрузок
let reloadCount = 0
let lastReloadTime = 0
let lastReloadUrl = ''

const MAX_RELOADS_PER_SECOND = 3
const RELOAD_WINDOW_MS = 1000

/**
 * Проверяет, нужно ли предотвратить перезагрузку на указанный URL
 */
function shouldPreventReload(url: string): boolean {
  const now = Date.now()
  // Используем полный URL включая query параметры для корректного сравнения
  // Это позволяет различать переходы на тот же путь с разными query (например, ?page=1 vs ?page=2)
  const currentUrl = url || window.location.pathname + window.location.search
  
  if (currentUrl !== lastReloadUrl) {
    reloadCount = 1
    lastReloadTime = now
    lastReloadUrl = currentUrl
    return false
  }
  
  if (now - lastReloadTime > RELOAD_WINDOW_MS) {
    reloadCount = 1
    lastReloadTime = now
    lastReloadUrl = currentUrl
    return false
  }
  
  reloadCount++
  if (reloadCount > MAX_RELOADS_PER_SECOND) {
    logger.warn('[routerGuards] Too many reloads to same URL detected, preventing reload', {
      count: reloadCount,
      window: RELOAD_WINDOW_MS,
      url: currentUrl,
    })
    return true
  }
  lastReloadTime = now
  return false
}

/**
 * Настраивает защиту от циклических перезагрузок для Inertia.js router
 */
export function setupRouterGuards(): void {
  // Проверяем, не обёрнуты ли уже методы (защита от HMR наложения обёрток)
  const reloadRef = router.reload as MarkedRouterMethod<ReloadMethod>
  const visitRef = router.visit as MarkedRouterMethod<VisitMethod>
  const isReloadWrapped = Boolean(reloadRef && reloadRef[WRAPPER_MARKER])
  const isVisitWrapped = Boolean(visitRef && visitRef[WRAPPER_MARKER])

  if (isReloadWrapped || isVisitWrapped) {
    // Методы уже обёрнуты, восстанавливаем оригинальные перед повторной обёрткой
    logger.debug('[routerGuards] Router methods already wrapped, restoring originals before re-wrap', {
      isReloadWrapped,
      isVisitWrapped,
    })

    if (originalRouterMethods.reload) {
      router.reload = originalRouterMethods.reload
    }
    if (originalRouterMethods.visit) {
      router.visit = originalRouterMethods.visit
    }
  }

  // Сохраняем оригинальные методы (если ещё не сохранены или были восстановлены)
  if (!originalRouterMethods.reload || (originalRouterMethods.reload as MarkedRouterMethod<ReloadMethod>)[WRAPPER_MARKER]) {
    originalRouterMethods.reload = router.reload.bind(router)
  }
  if (!originalRouterMethods.visit || (originalRouterMethods.visit as MarkedRouterMethod<VisitMethod>)[WRAPPER_MARKER]) {
    originalRouterMethods.visit = router.visit.bind(router)
  }

  // Перехватываем все вызовы router.reload() и router.visit() для предотвращения циклов
  const wrappedReload = function (options?: ReloadOptions) {
    // Проверяем только reload() на текущий URL (включая query параметры)
    const currentUrl = window.location.pathname + window.location.search
    if (shouldPreventReload(currentUrl)) {
      logger.warn('[routerGuards] Prevented router.reload() due to reload limit', {
        options,
        currentUrl: currentUrl,
      })
      return Promise.resolve()
    }
    logger.debug('[routerGuards] router.reload() called', {
      options,
      currentUrl: currentUrl,
      stack: new Error().stack,
    })
    return originalRouterMethods.reload ? originalRouterMethods.reload(options) : Promise.resolve()
  } as MarkedRouterMethod<ReloadMethod>

  // Помечаем обёрнутый метод маркером
  wrappedReload[WRAPPER_MARKER] = true
  router.reload = wrappedReload

  const wrappedVisit = function (url: VisitFirstArg, options?: VisitOptions) {
    // Блокируем только visit() на тот же URL (включая query параметры), легитимная навигация разрешена
    // Если URL отличается, это нормальная навигация, не блокируем
    const targetUrl = typeof url === 'string'
      ? url
      : ((url as { url?: string })?.url ?? window.location.pathname)
    const currentUrl = window.location.pathname + window.location.search

    // Логируем все вызовы router.visit() для отладки автоматических переходов
    logger.debug('[routerGuards] router.visit() called', {
      url: targetUrl,
      currentUrl: currentUrl,
      options,
      stack: new Error().stack,
    })

    // Сравниваем полные URL включая query параметры
    if (shouldPreventReload(targetUrl) && targetUrl === currentUrl) {
      logger.warn('[routerGuards] Prevented router.visit() to same URL due to reload limit', {
        url: targetUrl,
        currentUrl: currentUrl,
        options,
      })
      return Promise.resolve()
    }
    return originalRouterMethods.visit ? originalRouterMethods.visit(url, options) : Promise.resolve()
  } as MarkedRouterMethod<VisitMethod>

  // Помечаем обёрнутый метод маркером
  wrappedVisit[WRAPPER_MARKER] = true
  router.visit = wrappedVisit

  // Помечаем, что методы обёрнуты
  originalRouterMethods.isWrapped = true
}

/**
 * Восстанавливает оригинальные методы router (для HMR cleanup)
 */
export function restoreRouterMethods(): void {
  const currentReload = router.reload as MarkedRouterMethod<ReloadMethod>
  const currentVisit = router.visit as MarkedRouterMethod<VisitMethod>
  if (originalRouterMethods.reload && currentReload && currentReload[WRAPPER_MARKER]) {
    router.reload = originalRouterMethods.reload
    logger.debug('[routerGuards] HMR: Restored original router.reload')
  }
  if (originalRouterMethods.visit && currentVisit && currentVisit[WRAPPER_MARKER]) {
    router.visit = originalRouterMethods.visit
    logger.debug('[routerGuards] HMR: Restored original router.visit')
  }
  
  // Сбрасываем флаг обёртки, чтобы при следующей инициализации методы были восстановлены
  originalRouterMethods.isWrapped = false
  // Очищаем счётчики reload для предотвращения ложных блокировок
  reloadCount = 0
  lastReloadTime = 0
  lastReloadUrl = ''
}

// HMR cleanup: восстанавливаем оригинальные методы router при перезагрузке модуля
if (typeof import.meta !== 'undefined' && import.meta.hot) {
  import.meta.hot.dispose(() => {
    restoreRouterMethods()
  })
}
