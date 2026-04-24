import { onBeforeUnmount, onMounted } from 'vue'

/**
 * Горячие клавиши Cockpit планировщика:
 * - `J` — выбрать следующий run в таблице;
 * - `K` — выбрать предыдущий;
 * - `Enter` — открыть chain для выделенного run-а;
 * - `R` — refresh workspace;
 * - `Escape` — закрыть chain panel.
 *
 * Хоткеи игнорируются, если фокус в `<input>/<textarea>/contenteditable`,
 * либо нажаты с модификатором (Ctrl/Cmd/Alt) — чтобы не ломать стандартные
 * комбинации браузера.
 */
export interface SchedulerHotkeyHandlers {
  onNext?: () => void
  onPrev?: () => void
  onOpen?: () => void
  onRefresh?: () => void
  onClose?: () => void
}

export function useSchedulerHotkeys(handlers: SchedulerHotkeyHandlers): void {
  function isEditableTarget(target: EventTarget | null): boolean {
    if (!(target instanceof HTMLElement)) return false
    const tag = target.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
    if (target.isContentEditable) return true
    return false
  }

  function handle(event: KeyboardEvent): void {
    if (event.ctrlKey || event.metaKey || event.altKey) return
    if (isEditableTarget(event.target)) return

    switch (event.key) {
      case 'j':
      case 'J':
        if (handlers.onNext) {
          event.preventDefault()
          handlers.onNext()
        }
        break
      case 'k':
      case 'K':
        if (handlers.onPrev) {
          event.preventDefault()
          handlers.onPrev()
        }
        break
      case 'Enter':
        if (handlers.onOpen) {
          event.preventDefault()
          handlers.onOpen()
        }
        break
      case 'r':
      case 'R':
        if (handlers.onRefresh) {
          event.preventDefault()
          handlers.onRefresh()
        }
        break
      case 'Escape':
        if (handlers.onClose) {
          event.preventDefault()
          handlers.onClose()
        }
        break
    }
  }

  onMounted(() => {
    if (typeof window === 'undefined') return
    window.addEventListener('keydown', handle)
  })

  onBeforeUnmount(() => {
    if (typeof window === 'undefined') return
    window.removeEventListener('keydown', handle)
  })
}
