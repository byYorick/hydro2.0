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

/**
 * Инициализирует стандартные шорткаты (вызывается только один раз)
 */
function initializeDefaultShortcuts(): void {
  // Проверяем, не инициализированы ли уже стандартные шорткаты
  if (globalShortcuts.has('ctrl+z') || globalShortcuts.has('alt+d')) {
    return // Уже инициализированы
  }

  // Регистрируем стандартные shortcuts для навигации
  // Ctrl+Z - Zones
  globalShortcuts.set('ctrl+z', () => router.visit('/zones', { preserveScroll: true }))

  // Alt+D - Dashboard (изменено с Ctrl+D, чтобы не конфликтовать с закладками браузера)
  globalShortcuts.set('alt+d', () => router.visit('/', { preserveScroll: true }))

  // Ctrl+A - Alerts
  globalShortcuts.set('ctrl+a', () => router.visit('/alerts', { preserveScroll: true }))

  // Alt+R - Recipes (изменено с Ctrl+R, чтобы не конфликтовать с перезагрузкой страницы)
  globalShortcuts.set('alt+r', () => router.visit('/recipes', { preserveScroll: true }))

  // Shift+D - Devices (чтобы не конфликтовать с Ctrl+D)
  globalShortcuts.set('shift+d', () => router.visit('/devices', { preserveScroll: true }))
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

