/**
 * Composable для управления пагинацией с сохранением состояния в localStorage
 */
import { ref, watch, onMounted } from 'vue'

interface PaginationState {
  currentPage: number
  perPage: number
}

interface UsePaginationOptions {
  /**
   * Ключ для сохранения в localStorage (если не указан, состояние не сохраняется)
   */
  storageKey?: string
  /**
   * Начальная страница
   */
  initialPage?: number
  /**
   * Начальное количество элементов на странице
   */
  initialPerPage?: number
  /**
   * Автоматически сбрасывать на первую страницу при изменении фильтров
   */
  resetOnFilterChange?: boolean
}

/**
 * Composable для управления пагинацией
 */
export function usePagination(options: UsePaginationOptions = {}) {
  const {
    storageKey,
    initialPage = 1,
    initialPerPage = 25,
    resetOnFilterChange = true,
  } = options

  // Загружаем состояние из localStorage или используем начальные значения
  const loadState = (): PaginationState => {
    if (!storageKey || typeof window === 'undefined') {
      return {
        currentPage: initialPage,
        perPage: initialPerPage,
      }
    }

    try {
      const saved = localStorage.getItem(storageKey)
      if (saved) {
        const parsed = JSON.parse(saved) as PaginationState
        return {
          currentPage: Math.max(1, parsed.currentPage || initialPage),
          perPage: Math.max(1, Math.min(parsed.perPage || initialPerPage, 100)),
        }
      }
    } catch (error) {
      console.warn(`[usePagination] Failed to load state from localStorage:`, error)
    }

    return {
      currentPage: initialPage,
      perPage: initialPerPage,
    }
  }

  const initialState = loadState()
  const currentPage = ref<number>(initialState.currentPage)
  const perPage = ref<number>(initialState.perPage)

  // Сохраняем состояние в localStorage
  const saveState = () => {
    if (!storageKey || typeof window === 'undefined') return

    try {
      const state: PaginationState = {
        currentPage: currentPage.value,
        perPage: perPage.value,
      }
      localStorage.setItem(storageKey, JSON.stringify(state))
    } catch (error) {
      console.warn(`[usePagination] Failed to save state to localStorage:`, error)
    }
  }

  // Сохраняем при изменении
  watch([currentPage, perPage], () => {
    saveState()
  })

  // Загружаем состояние при монтировании
  onMounted(() => {
    const saved = loadState()
    currentPage.value = saved.currentPage
    perPage.value = saved.perPage
  })

  /**
   * Сбросить на первую страницу
   */
  const reset = () => {
    currentPage.value = 1
  }

  /**
   * Сбросить на первую страницу при изменении фильтров
   */
  const resetOnFilter = () => {
    if (resetOnFilterChange) {
      reset()
    }
  }

  return {
    currentPage,
    perPage,
    reset,
    resetOnFilter,
  }
}

