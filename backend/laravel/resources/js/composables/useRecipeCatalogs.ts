import { computed, ref, type Ref } from 'vue'
import type { NutrientProduct } from '@/types'
import type { PlantOption } from '@/composables/recipeEditorShared'
import { filterProductsByComponent } from '@/composables/recipeEditorShared'
import { api } from '@/services/api'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { logger } from '@/utils/logger'

/** Catalog/loading ownership; recipe and revision persistence are separate. */
export function useRecipeCatalogs(plantId: Ref<number | null>) {
  const { showToast } = useToast()
  const plants = ref<PlantOption[]>([])
  const plantsLoading = ref(false)
  const nutrientProducts = ref<NutrientProduct[]>([])
  const nutrientProductsLoading = ref(false)
  const substrates = ref<import('@/services/api/substrates').Substrate[]>([])
  const substratesLoading = ref(false)

  const npkProducts = computed<NutrientProduct[]>(() => filterProductsByComponent(nutrientProducts.value, 'npk'))
  const calciumProducts = computed<NutrientProduct[]>(() => filterProductsByComponent(nutrientProducts.value, 'calcium'))
  const magnesiumProducts = computed<NutrientProduct[]>(() => filterProductsByComponent(nutrientProducts.value, 'magnesium'))
  const microProducts = computed<NutrientProduct[]>(() => filterProductsByComponent(nutrientProducts.value, 'micro'))

  async function loadPlants(): Promise<void> {
    try {
      plantsLoading.value = true
      const payload = await api.plants.list()
      plants.value = payload
        .map((plant) => ({
          id: typeof plant.id === 'number' ? plant.id : 0,
          name: String(plant.name ?? ''),
        }))
        .filter((plant) => plant.id > 0 && plant.name.trim().length > 0)

      if (!plantId.value && plants.value.length === 1) {
        plantId.value = plants.value[0].id
      }
    } catch (error) {
      logger.error('Failed to load plants', { error })
      showToast('Не удалось загрузить список культур', 'error', TOAST_TIMEOUT.NORMAL)
    } finally {
      plantsLoading.value = false
    }
  }

  async function loadNutrientProducts(): Promise<void> {
    try {
      nutrientProductsLoading.value = true
      nutrientProducts.value = await api.nutrientProducts.list()
    } catch (error) {
      logger.error('Failed to load nutrient products', { error })
      showToast('Не удалось загрузить список удобрений', 'error', TOAST_TIMEOUT.NORMAL)
    } finally {
      nutrientProductsLoading.value = false
    }
  }

  async function loadSubstrates(): Promise<void> {
    try {
      substratesLoading.value = true
      substrates.value = await api.substrates.list()
    } catch (error) {
      logger.error('Failed to load substrates', { error })
      showToast('Не удалось загрузить список субстратов', 'error', TOAST_TIMEOUT.NORMAL)
    } finally {
      substratesLoading.value = false
    }
  }
  return { plants, plantsLoading, nutrientProducts, nutrientProductsLoading, substrates, substratesLoading, npkProducts, calciumProducts, magnesiumProducts, microProducts, loadPlants, loadNutrientProducts, loadSubstrates }
}
