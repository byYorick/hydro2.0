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

    shortcuts.delete(shortcutKey)
  }

  /**
   * Обработчик нажатий клавиш
   */
  function handleKeyDown(event: KeyboardEvent): void {
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

    const handler = shortcuts.get(shortcutKey)
    if (handler) {
      event.preventDefault()
      handler(event)
    }
  }

  // Регистрируем стандартные shortcuts для навигации
  // Ctrl+Z - Zones
  registerShortcut('z', {
    ctrl: true,
    handler: () => router.visit('/zones')
  })

  // Ctrl+D - Dashboard
  registerShortcut('d', {
    ctrl: true,
    handler: () => router.visit('/')
  })

  // Ctrl+A - Alerts
  registerShortcut('a', {
    ctrl: true,
    handler: () => router.visit('/alerts')
  })

  // Ctrl+R - Recipes
  registerShortcut('r', {
    ctrl: true,
    handler: () => router.visit('/recipes')
  })

  // Shift+D - Devices (чтобы не конфликтовать с Ctrl+D)
  registerShortcut('d', {
    shift: true,
    handler: () => router.visit('/devices')
  })

  onMounted(() => {
    window.addEventListener('keydown', handleKeyDown)
  })

  onUnmounted(() => {
    window.removeEventListener('keydown', handleKeyDown)
  })

  return {
    registerShortcut,
    unregisterShortcut
  }
}

