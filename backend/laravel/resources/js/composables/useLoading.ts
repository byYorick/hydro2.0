/**
 * Composable для унификации управления состоянием загрузки
 */
import { ref, type Ref } from 'vue'

/**
 * Создает состояние загрузки с возможностью управления несколькими индикаторами
 * @param initialState - Начальное состояние (может быть boolean или объект с несколькими ключами)
 * @returns Объект с методами для управления состоянием загрузки
 */
export function useLoading<T extends boolean | Record<string, boolean>>(
  initialState: T
) {
  const loading = ref<T>(initialState) as Ref<T>
  type LoadingKey = T extends boolean ? never : Extract<keyof T, string>

  /**
   * Установить состояние загрузки
   * @param key - Ключ (если T - объект) или undefined (если T - boolean)
   * @param value - Значение (для boolean режима)
   */
  function setLoading(key?: LoadingKey, value?: boolean): void {
    if (typeof loading.value === 'boolean') {
      loading.value = (value !== undefined ? value : true) as T
    } else if (key && typeof loading.value === 'object') {
      (loading.value as Record<string, boolean>)[key as string] = value !== undefined ? value : true
    }
  }

  /**
   * Начать загрузку
   * @param key - Ключ (если T - объект)
   */
  function startLoading(key?: LoadingKey): void {
    setLoading(key, true)
  }

  /**
   * Остановить загрузку
   * @param key - Ключ (если T - объект)
   */
  function stopLoading(key?: LoadingKey): void {
    setLoading(key, false)
  }

  /**
   * Сбросить все состояния загрузки
   */
  function resetLoading(): void {
    if (typeof loading.value === 'boolean') {
      loading.value = false as T
    } else if (typeof loading.value === 'object') {
      Object.keys(loading.value).forEach(key => {
        (loading.value as Record<string, boolean>)[key] = false
      })
    }
  }

  /**
   * Проверить, есть ли активная загрузка
   * @param key - Опциональный ключ для проверки конкретного состояния
   */
  function isLoading(key?: LoadingKey): boolean {
    if (typeof loading.value === 'boolean') {
      return loading.value
    } else if (key && typeof loading.value === 'object') {
      return (loading.value as Record<string, boolean>)[key as string] === true
    } else if (typeof loading.value === 'object') {
      return Object.values(loading.value as Record<string, boolean>).some(v => v === true)
    }
    return false
  }

  /**
   * Обернуть асинхронную функцию с автоматическим управлением состоянием загрузки
   * @param fn - Асинхронная функция для выполнения
   * @param key - Ключ состояния загрузки (если T - объект)
   */
  async function withLoading<R>(
    fn: () => Promise<R>,
    key?: LoadingKey
  ): Promise<R> {
    try {
      startLoading(key)
      return await fn()
    } finally {
      stopLoading(key)
    }
  }

  return {
    loading,
    setLoading,
    startLoading,
    stopLoading,
    resetLoading,
    isLoading,
    withLoading,
  }
}

/**
 * Создает простое boolean состояние загрузки
 */
export function useSimpleLoading() {
  return useLoading<boolean>(false)
}
