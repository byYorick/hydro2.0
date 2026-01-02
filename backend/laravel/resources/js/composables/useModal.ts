/**
 * Composable для унификации управления модальными окнами
 */
import { ref, type Ref } from 'vue'

/**
 * Создает состояние модального окна с методами управления
 * @param initialState - Начальное состояние (может быть boolean или объект с несколькими модалками)
 * @returns Объект с методами для управления модальными окнами
 */
export function useModal<T extends boolean | Record<string, boolean>>(
  initialState: T
) {
  const isOpen = ref<T>(initialState) as Ref<T>

  /**
   * Открыть модальное окно
   * @param key - Ключ (если T - объект) или undefined (если T - boolean)
   */
  function open(key?: keyof T extends string ? keyof T : never): void {
    if (typeof isOpen.value === 'boolean') {
      isOpen.value = true as T
    } else if (key && typeof isOpen.value === 'object') {
      (isOpen.value as Record<string, boolean>)[key as string] = true
    }
  }

  /**
   * Закрыть модальное окно
   * @param key - Ключ (если T - объект) или undefined (если T - boolean)
   */
  function close(key?: keyof T extends string ? keyof T : never): void {
    if (typeof isOpen.value === 'boolean') {
      isOpen.value = false as T
    } else if (key && typeof isOpen.value === 'object') {
      (isOpen.value as Record<string, boolean>)[key as string] = false
    }
  }

  /**
   * Переключить состояние модального окна
   * @param key - Ключ (если T - объект) или undefined (если T - boolean)
   */
  function toggle(key?: keyof T extends string ? keyof T : never): void {
    if (typeof isOpen.value === 'boolean') {
      isOpen.value = !isOpen.value as T
    } else if (key && typeof isOpen.value === 'object') {
      const current = (isOpen.value as Record<string, boolean>)[key as string]
      const modalState = isOpen.value as Record<string, boolean>
      modalState[key as string] = !current
    }
  }

  /**
   * Проверить, открыто ли модальное окно
   * @param key - Опциональный ключ для проверки конкретного модального окна
   */
  function isModalOpen(key?: keyof T extends string ? keyof T : never) {
    if (typeof isOpen.value === 'boolean') {
      return isOpen.value
    } else if (key && typeof isOpen.value === 'object') {
      return (isOpen.value as Record<string, boolean>)[key as string] === true
    }
    return false
  }

  /**
   * Закрыть все модальные окна
   */
  function closeAll(): void {
    if (typeof isOpen.value === 'boolean') {
      isOpen.value = false as T
    } else if (typeof isOpen.value === 'object') {
      Object.keys(isOpen.value).forEach(key => {
        (isOpen.value as Record<string, boolean>)[key] = false
      })
    }
  }

  return {
    isOpen,
    open,
    close,
    toggle,
    isModalOpen,
    closeAll,
  }
}

/**
 * Создает простое boolean состояние модального окна
 */
export function useSimpleModal() {
  const isOpen = ref(false)
  
  function open() {
    isOpen.value = true
  }
  
  function close() {
    isOpen.value = false
  }
  
  function toggle() {
    isOpen.value = !isOpen.value
  }
  
  function isModalOpen() {
    return isOpen.value
  }
  
  function closeAll() {
    isOpen.value = false
  }
  
  return {
    isOpen,
    open,
    close,
    toggle,
    isModalOpen,
    closeAll,
  }
}

