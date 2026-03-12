/**
 * Composable для унификации работы с Inertia page props
 */
import { computed } from 'vue'
import { usePage } from '@inertiajs/vue3'

/**
 * Получает props из Inertia page с типизацией
 * @param propKeys - Массив ключей props для извлечения
 * @returns Объект с computed свойствами для каждого prop
 */
export function usePageProps<T extends Record<string, any>>(
  propKeys?: (keyof T)[]
): Partial<Record<keyof T, ReturnType<typeof computed>>> {
  const page = usePage<T>()
  
  if (!propKeys || propKeys.length === 0) {
    // Если ключи не указаны, возвращаем все props
    return computed(() => page.props) as any
  }
  
  // Создаем объект с computed свойствами для каждого ключа
  const result: Partial<Record<keyof T, ReturnType<typeof computed>>> = {}
  
  propKeys.forEach(key => {
    result[key] = computed(() => page.props[key as string])
  })
  
  return result
}

/**
 * Получает конкретный prop из Inertia page
 * @param key - Ключ prop
 * @returns Computed свойство для prop
 */
export function usePageProp<K extends string, T = any>(
  key: K
): ReturnType<typeof computed<T>> {
  const page = usePage()
  return computed(() => page.props[key] as T)
}

