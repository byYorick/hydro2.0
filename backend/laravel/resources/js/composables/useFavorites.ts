/**
 * Composable для работы с избранными зонами и устройствами
 */
import { ref, computed, watch } from 'vue'

interface FavoritesState {
  zones: number[]
  devices: number[]
}

const defaultState: FavoritesState = {
  zones: [],
  devices: []
}

const STORAGE_KEY = 'hydro-favorites'

// Функция для загрузки из localStorage
function loadFromStorage(): FavoritesState {
  if (typeof window === 'undefined') return defaultState
  
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      return JSON.parse(stored)
    }
  } catch (err) {
    console.error('[useFavorites] Failed to load from localStorage:', err)
  }
  return defaultState
}

// Функция для сохранения в localStorage
function saveToStorage(state: FavoritesState): void {
  if (typeof window === 'undefined') return
  
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch (err) {
    console.error('[useFavorites] Failed to save to localStorage:', err)
  }
}

// Реактивное состояние
const favorites = ref<FavoritesState>(loadFromStorage())

// Синхронизация с localStorage при изменениях
watch(favorites, (newValue) => {
  saveToStorage(newValue)
}, { deep: true })

export function useFavorites() {
  // Избранные зоны
  const favoriteZones = computed(() => favorites.value.zones)
  
  // Избранные устройства
  const favoriteDevices = computed(() => favorites.value.devices)

  /**
   * Проверяет, является ли зона избранной
   */
  function isZoneFavorite(zoneId: number): boolean {
    return favorites.value.zones.includes(zoneId)
  }

  /**
   * Проверяет, является ли устройство избранным
   */
  function isDeviceFavorite(deviceId: number): boolean {
    return favorites.value.devices.includes(deviceId)
  }

  /**
   * Добавляет зону в избранное
   */
  function addZoneToFavorites(zoneId: number): void {
    if (!favorites.value.zones.includes(zoneId)) {
      favorites.value.zones.push(zoneId)
    }
  }

  /**
   * Удаляет зону из избранного
   */
  function removeZoneFromFavorites(zoneId: number): void {
    const index = favorites.value.zones.indexOf(zoneId)
    if (index > -1) {
      favorites.value.zones.splice(index, 1)
    }
  }

  /**
   * Переключает статус избранного для зоны
   */
  function toggleZoneFavorite(zoneId: number): void {
    if (isZoneFavorite(zoneId)) {
      removeZoneFromFavorites(zoneId)
    } else {
      addZoneToFavorites(zoneId)
    }
  }

  /**
   * Добавляет устройство в избранное
   */
  function addDeviceToFavorites(deviceId: number): void {
    if (!favorites.value.devices.includes(deviceId)) {
      favorites.value.devices.push(deviceId)
    }
  }

  /**
   * Удаляет устройство из избранного
   */
  function removeDeviceFromFavorites(deviceId: number): void {
    const index = favorites.value.devices.indexOf(deviceId)
    if (index > -1) {
      favorites.value.devices.splice(index, 1)
    }
  }

  /**
   * Переключает статус избранного для устройства
   */
  function toggleDeviceFavorite(deviceId: number): void {
    if (isDeviceFavorite(deviceId)) {
      removeDeviceFromFavorites(deviceId)
    } else {
      addDeviceToFavorites(deviceId)
    }
  }

  /**
   * Очищает все избранное
   */
  function clearAllFavorites(): void {
    favorites.value.zones = []
    favorites.value.devices = []
  }

  /**
   * Получает количество избранных зон
   */
  const favoriteZonesCount = computed(() => favorites.value.zones.length)

  /**
   * Получает количество избранных устройств
   */
  const favoriteDevicesCount = computed(() => favorites.value.devices.length)

  return {
    favoriteZones,
    favoriteDevices,
    favoriteZonesCount,
    favoriteDevicesCount,
    isZoneFavorite,
    isDeviceFavorite,
    addZoneToFavorites,
    removeZoneFromFavorites,
    toggleZoneFavorite,
    addDeviceToFavorites,
    removeDeviceFromFavorites,
    toggleDeviceFavorite,
    clearAllFavorites,
  }
}

