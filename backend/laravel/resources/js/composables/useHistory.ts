/**
 * Composable для работы с историей просмотров зон и устройств
 */
import { ref, computed, watch } from 'vue'
import { logger } from '@/utils/logger'

interface HistoryItem {
  id: number
  type: 'zone' | 'device'
  name: string
  url: string
  timestamp: number
}

const STORAGE_KEY = 'hydro-view-history'
const MAX_HISTORY_ITEMS = 20

// Функция для загрузки из localStorage
function loadFromStorage(): HistoryItem[] {
  if (typeof window === 'undefined') return []
  
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      return JSON.parse(stored)
    }
  } catch (err) {
    logger.error('[useHistory] Failed to load from localStorage:', err)
  }
  return []
}

// Функция для сохранения в localStorage
function saveToStorage(items: HistoryItem[]): void {
  if (typeof window === 'undefined') return
  
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items))
  } catch (err) {
    logger.error('[useHistory] Failed to save to localStorage:', err)
  }
}

// Реактивное состояние
const history = ref<HistoryItem[]>(loadFromStorage())

// Синхронизация с localStorage при изменениях
watch(history, (newValue) => {
  saveToStorage(newValue)
}, { deep: true })

export function useHistory() {
  /**
   * Добавляет элемент в историю просмотров
   */
  function addToHistory(item: Omit<HistoryItem, 'timestamp'>): void {
    const historyItem: HistoryItem = {
      ...item,
      timestamp: Date.now()
    }
    
    // Удаляем дубликаты (если элемент уже есть в истории)
    const filtered = history.value.filter(h => 
      !(h.id === historyItem.id && h.type === historyItem.type)
    )
    
    // Добавляем в начало
    filtered.unshift(historyItem)
    
    // Ограничиваем количество элементов
    history.value = filtered.slice(0, MAX_HISTORY_ITEMS)
  }

  /**
   * Удаляет элемент из истории
   */
  function removeFromHistory(id: number, type: 'zone' | 'device'): void {
    history.value = history.value.filter(h => 
      !(h.id === id && h.type === type)
    )
  }

  /**
   * Очищает всю историю
   */
  function clearHistory(): void {
    history.value = []
  }

  /**
   * Получает историю просмотров зон
   */
  const zoneHistory = computed(() => 
    history.value.filter(h => h.type === 'zone')
  )

  /**
   * Получает историю просмотров устройств
   */
  const deviceHistory = computed(() => 
    history.value.filter(h => h.type === 'device')
  )

  /**
   * Получает последние N элементов истории
   */
  function getRecentHistory(limit: number = 10): HistoryItem[] {
    return history.value.slice(0, limit)
  }

  /**
   * Проверяет, есть ли элемент в истории
   */
  function isInHistory(id: number, type: 'zone' | 'device'): boolean {
    return history.value.some(h => h.id === id && h.type === type)
  }

  return {
    history: computed(() => [...history.value]),
    zoneHistory,
    deviceHistory,
    addToHistory,
    removeFromHistory,
    clearHistory,
    getRecentHistory,
    isInHistory,
  }
}

