/**
 * Composable для глобальных keyboard shortcuts
 */
import { onMounted, onUnmounted } from 'vue'
import { router } from '@inertiajs/vue3'

interface ShortcutOptions {
  ctrl?: boolean
  meta?: boolean
  shift?: boolean
  alt?: boolean
  handler: (event: KeyboardEvent) => void
}

// Глобальное хранилище шорткатов (singleton pattern)
const globalShortcuts = new Map<string, (event: KeyboardEvent) => void>()
let globalKeyDownHandler: ((event: KeyboardEvent) => void) | null = null
let globalListenerCount = 0

/**
 * Обработчик нажатий клавиш (глобальный, используется всеми экземплярами)
 */
function handleGlobalKeyDown(event: KeyboardEvent): void {
  // Игнорируем если фокус в input/textarea
  if (
    event.target instanceof HTMLElement &&
    (event.target.tagName === 'INPUT' ||
    event.target.tagName === 'TEXTAREA' ||
    event.target.isContentEditable)
  ) {
    // Разрешаем только Ctrl+K для Command Palette
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      // Это обрабатывается CommandPalette
      return
    }
    return
  }

  // Дополнительная защита: не перехватываем стандартные браузерные комбинации
  // Ctrl+A (Выделить всё) - не перехватываем
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'a' && !event.shiftKey) {
    return // Позволяем браузеру обработать "Выделить всё"
  }
  
  // Ctrl+Z (Undo) - не перехватываем, чтобы не конфликтовать с отменой действий в полях ввода
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z' && !event.shiftKey) {
    return // Позволяем браузеру обработать "Отменить"
  }
  
  // Alt+D (переход в адресную строку) - не перехватываем
  if (event.altKey && event.key.toLowerCase() === 'd' && !event.ctrlKey && !event.shiftKey) {
    return // Позволяем браузеру обработать переход в адресную строку
  }

  const key = event.key.toLowerCase()
  const ctrl = event.ctrlKey
  const meta = event.metaKey
  const shift = event.shiftKey
  const alt = event.altKey

  const shortcutKey = `${ctrl ? 'ctrl+' : ''}${meta ? 'meta+' : ''}${shift ? 'shift+' : ''}${alt ? 'alt+' : ''}${key}`

  const handler = globalShortcuts.get(shortcutKey)
  if (handler) {
    event.preventDefault()
    handler(event)
  }
}

// Debounce для предотвращения множественных вызовов router.visit
const visitTimers = new Map<string, ReturnType<typeof setTimeout>>()
const VISIT_DEBOUNCE_MS = 300

/**
 * Безопасный переход с проверкой текущего URL и debounce
 */
function safeVisit(url: string, options: { preserveScroll?: boolean } = {}): void {
  const currentUrl = window.location.pathname
  const targetUrl = url.startsWith('/') ? url : `/${url}`
  
  // Если уже на целевой странице, не делаем переход
  if (currentUrl === targetUrl) {
    return
  }
  
  const key = targetUrl
  
  // Очищаем предыдущий таймер для этого URL
  if (visitTimers.has(key)) {
    clearTimeout(visitTimers.get(key)!)
  }
  
  // Устанавливаем новый таймер с debounce
  visitTimers.set(key, setTimeout(() => {
    visitTimers.delete(key)
    router.visit(targetUrl, { preserveScroll: options.preserveScroll ?? true })
  }, VISIT_DEBOUNCE_MS))
}

/**
 * Инициализирует стандартные шорткаты (вызывается только один раз)
 */
function initializeDefaultShortcuts(): void {
  // Проверяем, не инициализированы ли уже стандартные шорткаты
  if (globalShortcuts.has('ctrl+shift+z') || globalShortcuts.has('ctrl+shift+d')) {
    return // Уже инициализированы
  }

  // Регистрируем стандартные shortcuts для навигации с безопасным переходом
  // Ctrl+Shift+Z - Zones (изменено с Ctrl+Z, чтобы не конфликтовать с Undo)
  globalShortcuts.set('ctrl+shift+z', () => safeVisit('/zones', { preserveScroll: true }))

  // Ctrl+Shift+D - Dashboard (изменено с Alt+D, чтобы не конфликтовать с переходом в адресную строку)
  globalShortcuts.set('ctrl+shift+d', () => safeVisit('/', { preserveScroll: true }))

  // Ctrl+Shift+A - Alerts (изменено с Ctrl+A, чтобы не конфликтовать с "Выделить всё")
  globalShortcuts.set('ctrl+shift+a', () => safeVisit('/alerts', { preserveScroll: true }))

  // Alt+R - Recipes (изменено с Ctrl+R, чтобы не конфликтовать с перезагрузкой страницы)
  globalShortcuts.set('alt+r', () => safeVisit('/recipes', { preserveScroll: true }))

  // Shift+D - Devices (чтобы не конфликтовать с Ctrl+D)
  globalShortcuts.set('shift+d', () => safeVisit('/devices', { preserveScroll: true }))
}

/**
 * Composable для работы с keyboard shortcuts
 */
export function useKeyboardShortcuts() {
  const shortcuts = new Map<string, (event: KeyboardEvent) => void>()

  /**
   * Регистрирует keyboard shortcut
   */
  function registerShortcut(key: string, options: ShortcutOptions = {} as ShortcutOptions): void {
    const {
      ctrl = false,
      meta = false,
      shift = false,
      alt = false,
      handler
    } = options

    const shortcutKey = `${ctrl ? 'ctrl+' : ''}${meta ? 'meta+' : ''}${shift ? 'shift+' : ''}${alt ? 'alt+' : ''}${key.toLowerCase()}`

    // Регистрируем в глобальном хранилище
    globalShortcuts.set(shortcutKey, handler)
    // Также сохраняем в локальном хранилище для отслеживания
    shortcuts.set(shortcutKey, handler)
  }

  /**
   * Удаляет keyboard shortcut
   */
  function unregisterShortcut(key: string, options: ShortcutOptions = {} as ShortcutOptions): void {
    const {
      ctrl = false,
      meta = false,
      shift = false,
      alt = false
    } = options

    const shortcutKey = `${ctrl ? 'ctrl+' : ''}${meta ? 'meta+' : ''}${shift ? 'shift+' : ''}${alt ? 'alt+' : ''}${key.toLowerCase()}`

    // Удаляем из глобального хранилища
    globalShortcuts.delete(shortcutKey)
    // Удаляем из локального хранилища
    shortcuts.delete(shortcutKey)
  }

  // Инициализируем стандартные шорткаты только один раз
  initializeDefaultShortcuts()

  onMounted(() => {
    // Увеличиваем счетчик активных экземпляров
    globalListenerCount++
    
    // Добавляем глобальный слушатель только один раз
    if (globalListenerCount === 1 && !globalKeyDownHandler) {
      globalKeyDownHandler = handleGlobalKeyDown
      window.addEventListener('keydown', globalKeyDownHandler)
    }
  })

  onUnmounted(() => {
    // Уменьшаем счетчик активных экземпляров
    globalListenerCount--
    
    // Удаляем пользовательские шорткаты, зарегистрированные этим экземпляром
    for (const [key] of shortcuts) {
      globalShortcuts.delete(key)
    }
    shortcuts.clear()
    
    // Удаляем глобальный слушатель только если больше нет активных экземпляров
    if (globalListenerCount === 0 && globalKeyDownHandler) {
      window.removeEventListener('keydown', globalKeyDownHandler)
      globalKeyDownHandler = null
    }
  })

  return {
    registerShortcut,
    unregisterShortcut
  }
}

// HMR cleanup: удаляем глобальный слушатель при перезагрузке модуля
if (typeof import.meta !== 'undefined' && import.meta.hot) {
  import.meta.hot.dispose(() => {
    // Удаляем глобальный слушатель перед перезагрузкой модуля
    if (globalKeyDownHandler) {
      window.removeEventListener('keydown', globalKeyDownHandler)
      globalKeyDownHandler = null
    }
    // Сбрасываем счетчик, чтобы новый модуль мог правильно инициализироваться
    globalListenerCount = 0
    // Очищаем шорткаты (они будут переинициализированы при следующем вызове)
    globalShortcuts.clear()
  })
}
