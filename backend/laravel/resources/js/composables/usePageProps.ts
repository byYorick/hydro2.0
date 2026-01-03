/**
 * Composable для унификации работы с Inertia page props
 */
import { computed, type ComputedRef } from 'vue'
import { usePage } from '@inertiajs/vue3'

/**
 * Получает props из Inertia page с типизацией
 * @param propKeys - Массив ключей props для извлечения
 * @returns Объект с computed свойствами для каждого prop
 */
type PagePropRefs<T extends Record<string, unknown>> = Partial<{
  [K in keyof T]: ComputedRef<T[K]>
}>

export function usePageProps<T extends Record<string, unknown>>(
  propKeys: (keyof T)[]
): PagePropRefs<T>
export function usePageProps<T extends Record<string, unknown>>(): ComputedRef<T>
export function usePageProps<T extends Record<string, unknown>>(
  propKeys?: (keyof T)[]
): PagePropRefs<T> | ComputedRef<T> {
  const page = usePage<T>()
  
  if (!propKeys || propKeys.length === 0) {
    // Если ключи не указаны, возвращаем все props
    return computed(() => page.props) as ComputedRef<T>
  }
  
  // Создаем объект с computed свойствами для каждого ключа
  const result: PagePropRefs<T> = {}
  
  propKeys.forEach(key => {
    result[key] = computed(() => page.props[key as string]) as ComputedRef<T[typeof key]>
  })
  
  return result
}

/**
 * Получает конкретный prop из Inertia page
 * @param key - Ключ prop
 * @returns Computed свойство для prop
 */
export function usePageProp<K extends string, T = unknown>(
  key: K
): ComputedRef<T> {
  const page = usePage()
  return computed(() => page.props[key] as T)
}
