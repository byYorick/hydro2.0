/**
 * useWizardApi - API вызовы для визарда создания цикла
 * 
 * Предоставляет функции для работы с API при создании цикла выращивания:
 * - Создание/получение теплицы
 * - Создание/получение зоны
 * - Создание/получение растения
 * - Создание/получение рецепта
 * - Запуск цикла выращивания
 */
import { useApi } from './useApi'
import type { GrowCycleWizardData } from './useWizardValidation'

export interface CreateGreenhouseRequest {
  name: string
  location?: string
  description?: string
}

export interface CreateZoneRequest {
  name: string
  greenhouse_id: number
  description?: string
}

export interface CreatePlantRequest {
  name: string
  scientific_name?: string
  description?: string
}

export interface CreateRecipeRequest {
  name: string
  plant_id: number
  phases: Array<{
    name: string
    duration_hours: number
    targets?: Record<string, any>
  }>
  description?: string
}

export interface StartCycleRequest {
  zone_id: number
  recipe_id: number
  planting_at: string
  batch_label?: string
}

/**
 * Создает API функции для визарда создания цикла
 */
export function useWizardApi() {
  const { api } = useApi()

  /**
   * Получить список теплиц
   */
  const getGreenhouses = async () => {
    const response = await api.get('/greenhouses')
    return response.data?.data || []
  }

  /**
   * Создать теплицу
   */
  const createGreenhouse = async (data: CreateGreenhouseRequest) => {
    const response = await api.post('/greenhouses', data)
    return response.data?.data
  }

  /**
   * Получить список зон
   */
  const getZones = async (greenhouseId?: number) => {
    const url = greenhouseId 
      ? `/greenhouses/${greenhouseId}/zones`
      : '/zones'
    const response = await api.get(url)
    return response.data?.data || []
  }

  /**
   * Создать зону
   */
  const createZone = async (data: CreateZoneRequest) => {
    const response = await api.post('/zones', data)
    return response.data?.data
  }

  /**
   * Получить список растений
   */
  const getPlants = async () => {
    const response = await api.get('/plants')
    return response.data?.data || []
  }

  /**
   * Создать растение
   */
  const createPlant = async (data: CreatePlantRequest) => {
    const response = await api.post('/plants', data)
    return response.data?.data
  }

  /**
   * Получить список рецептов
   */
  const getRecipes = async (plantId?: number) => {
    const url = plantId 
      ? `/plants/${plantId}/recipes`
      : '/recipes'
    const response = await api.get(url)
    return response.data?.data || []
  }

  /**
   * Создать рецепт
   */
  const createRecipe = async (data: CreateRecipeRequest) => {
    const response = await api.post('/recipes', data)
    return response.data?.data
  }

  /**
   * Запустить цикл выращивания
   */
  const startCycle = async (data: StartCycleRequest) => {
    const response = await api.post(`/zones/${data.zone_id}/grow-cycle`, {
      recipe_id: data.recipe_id,
      planting_at: data.planting_at,
      batch_label: data.batch_label,
    })
    return response.data?.data
  }

  /**
   * Полный процесс создания цикла из данных визарда
   */
  const createCycleFromWizard = async (wizardData: GrowCycleWizardData) => {
    let greenhouseId = wizardData.greenhouseId
    let zoneId = wizardData.zoneId
    let plantId = wizardData.plantId
    let recipeId = wizardData.recipeId

    // 1. Создать теплицу, если нужно
    if (!greenhouseId && wizardData.greenhouse) {
      const greenhouse = await createGreenhouse({
        name: wizardData.greenhouse.name!,
      })
      greenhouseId = greenhouse.id
    }

    // 2. Создать зону, если нужно
    if (!zoneId && wizardData.zone) {
      const zone = await createZone({
        name: wizardData.zone.name!,
        greenhouse_id: greenhouseId || wizardData.zone.greenhouse_id!,
      })
      zoneId = zone.id
    }

    // 3. Создать растение, если нужно
    if (!plantId && wizardData.plant) {
      const plant = await createPlant({
        name: wizardData.plant.name!,
      })
      plantId = plant.id
    }

    // 4. Создать рецепт, если нужно
    if (!recipeId && wizardData.recipe) {
      const recipe = await createRecipe({
        name: wizardData.recipe.name!,
        plant_id: plantId!,
        phases: wizardData.recipe.phases || [],
      })
      recipeId = recipe.id
    }

    // 5. Запустить цикл
    if (!zoneId || !recipeId || !wizardData.plantingAt) {
      throw new Error('Недостаточно данных для запуска цикла')
    }

    const cycle = await startCycle({
      zone_id: zoneId,
      recipe_id: recipeId,
      planting_at: wizardData.plantingAt,
      batch_label: wizardData.batchLabel,
    })

    return cycle
  }

  return {
    getGreenhouses,
    createGreenhouse,
    getZones,
    createZone,
    getPlants,
    createPlant,
    getRecipes,
    createRecipe,
    startCycle,
    createCycleFromWizard,
  }
}

