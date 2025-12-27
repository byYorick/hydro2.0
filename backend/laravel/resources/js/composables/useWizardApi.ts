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
  plant_id: number
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
    const response = await api.get('/zones', {
      params: greenhouseId ? { greenhouse_id: greenhouseId } : undefined,
    })
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
   * Если указан plantId, фильтрует рецепты по растению
   */
  const getRecipes = async (plantId?: number) => {
    const url = plantId 
      ? `/recipes?plant_id=${plantId}` // Используем query параметр вместо nested route
      : '/recipes'
    const response = await api.get(url)
    return response.data?.data || []
  }

  /**
   * Создать рецепт
   */
  const createRecipe = async (data: CreateRecipeRequest) => {
    const response = await api.post('/recipes', {
      name: data.name,
      description: data.description,
    })
    const recipe = response.data?.data
    if (!recipe?.id) {
      throw new Error('Recipe ID not found in response')
    }

    const revisionResponse = await api.post(`/recipes/${recipe.id}/revisions`, {
      description: 'Initial revision',
    })
    const revision = revisionResponse.data?.data
    if (!revision?.id) {
      throw new Error('Recipe revision ID not found in response')
    }

    for (const [index, phase] of data.phases.entries()) {
      const phTarget = typeof phase.targets?.ph === 'number' ? phase.targets.ph : null
      const phMin = typeof phase.targets?.ph?.min === 'number' ? phase.targets.ph.min : phTarget
      const phMax = typeof phase.targets?.ph?.max === 'number' ? phase.targets.ph.max : phTarget

      const ecTarget = typeof phase.targets?.ec === 'number' ? phase.targets.ec : null
      const ecMin = typeof phase.targets?.ec?.min === 'number' ? phase.targets.ec.min : ecTarget
      const ecMax = typeof phase.targets?.ec?.max === 'number' ? phase.targets.ec.max : ecTarget

      await api.post(`/recipe-revisions/${revision.id}/phases`, {
        phase_index: index,
        name: phase.name,
        duration_hours: phase.duration_hours,
        ph_target: phTarget,
        ph_min: phMin,
        ph_max: phMax,
        ec_target: ecTarget,
        ec_min: ecMin,
        ec_max: ecMax,
      })
    }

    await api.post(`/recipe-revisions/${revision.id}/publish`)

    const fullRecipeResponse = await api.get(`/recipes/${recipe.id}`)
    return fullRecipeResponse.data?.data
  }

  /**
   * Запустить цикл выращивания
   * Использует endpoint POST /api/zones/{zone_id}/grow-cycles согласно routes/api.php
   */
  const startCycle = async (data: StartCycleRequest) => {
    const recipeResponse = await api.get(`/recipes/${data.recipe_id}`)
    const recipe = recipeResponse.data?.data
    const recipeRevisionId = recipe?.latest_published_revision_id || recipe?.latest_draft_revision_id

    if (!recipeRevisionId) {
      throw new Error('Recipe revision not found for selected recipe')
    }

    const response = await api.post(`/zones/${data.zone_id}/grow-cycles`, {
      recipe_revision_id: recipeRevisionId,
      plant_id: data.plant_id,
      planting_at: data.planting_at,
      batch_label: data.batch_label,
      start_immediately: true,
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
    if (!zoneId || !recipeId || !plantId || !wizardData.plantingAt) {
      throw new Error('Недостаточно данных для запуска цикла')
    }

    const cycle = await startCycle({
      zone_id: zoneId,
      recipe_id: recipeId,
      plant_id: plantId!,
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
