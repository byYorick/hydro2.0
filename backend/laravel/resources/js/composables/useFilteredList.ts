import { computed, type Ref } from 'vue'

/**
 * Composable для фильтрации списков
 * @param items - реактивный массив элементов
 * @param filterFn - функция фильтрации
 * @returns отфильтрованный computed массив
 */
export function useFilteredList<T>(
  items: Ref<T[]>,
  filterFn: (item: T) => boolean
) {
  return computed(() => {
    return items.value.filter(filterFn)
  })
}

