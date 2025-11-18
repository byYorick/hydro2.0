/**
 * Composable для глобальных keyboard shortcuts
 */
import { onMounted, onUnmounted } from 'vue'
import { router } from '@inertiajs/vue3'

/**
 * Composable для работы с keyboard shortcuts
 * @returns {Object} Методы для управления shortcuts
 */
export function useKeyboardShortcuts() {
  const shortcuts = new Map()

  /**
   * Регистрирует keyboard shortcut
   * @param {string} key - Клавиша (например, 'k', 'z')
   * @param {Object} options - Опции (ctrl, meta, shift, alt, handler)
   */
  function registerShortcut(key, options = {}) {
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
   * @param {string} key - Клавиша
   * @param {Object} options - Опции
   */
  function unregisterShortcut(key, options = {}) {
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
  function handleKeyDown(event) {
    // Игнорируем если фокус в input/textarea
    if (
      event.target.tagName === 'INPUT' ||
      event.target.tagName === 'TEXTAREA' ||
      event.target.isContentEditable
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

  // Регистрируем стандартные shortcuts
  registerShortcut('z', {
    ctrl: true,
    handler: () => router.visit('/zones')
  })

  registerShortcut('d', {
    ctrl: true,
    handler: () => router.visit('/')
  })

  registerShortcut('a', {
    ctrl: true,
    handler: () => router.visit('/alerts')
  })

  registerShortcut('r', {
    ctrl: true,
    handler: () => router.visit('/recipes')
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

