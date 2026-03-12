import { defineStore } from 'pinia'
import type { Recipe } from '@/types/Recipe'
import { recipeEvents } from '@/composables/useStoreEvents'

interface RecipesStoreState {
  // Нормализованная структура: Record<id, Recipe> для быстрого доступа O(1)
  items: Record<number, Recipe>
  // Массив ID для сохранения порядка
  ids: number[]
  
  // Состояние загрузки
  loading: boolean
  error: string | null
  lastFetch: Date | null
  
  // Инвалидация кеша
  cacheVersion: number
  cacheInvalidatedAt: Date | null
}

interface InertiaPageProps {
  recipes?: Recipe[]
  [key: string]: unknown
}

export const useRecipesStore = defineStore('recipes', {
  state: (): RecipesStoreState => ({
    items: {} as Record<number, Recipe>,
    ids: [] as number[],
    loading: false,
    error: null,
    lastFetch: null,
    cacheVersion: 0,
    cacheInvalidatedAt: null,
  }),
  actions: {
    initFromProps(props: InertiaPageProps): void {
      if (props?.recipes && Array.isArray(props.recipes)) {
        this.setRecipes(props.recipes)
      }
    },
    
    /**
     * Установить рецепты (нормализация в Record)
     */
    setRecipes(recipes: Recipe[]): void {
      const normalized: Record<number, Recipe> = {}
      const ids: number[] = []
      
      recipes.forEach(recipe => {
        if (recipe.id) {
          normalized[recipe.id] = recipe
          ids.push(recipe.id)
        }
      })
      
      this.items = normalized
      this.ids = ids
      this.lastFetch = new Date()
      this.cacheVersion++
    },
    
    /**
     * Добавить или обновить рецепт
     */
    upsert(recipe: Recipe): void {
      if (!recipe.id) return
      
      const exists = this.items[recipe.id]
      this.items[recipe.id] = recipe
      
      if (!exists) {
        this.ids.push(recipe.id)
        // Эмитим событие создания
        recipeEvents.created(recipe)
      } else {
        // Эмитим событие обновления
        recipeEvents.updated(recipe)
      }
      
      this.cacheVersion++
      this.cacheInvalidatedAt = new Date()
    },
    
    /**
     * Удалить рецепт
     */
    remove(recipeId: number): void {
      if (this.items[recipeId]) {
        delete this.items[recipeId]
        this.ids = this.ids.filter(id => id !== recipeId)
        
        // Эмитим событие удаления
        recipeEvents.deleted(recipeId)
        
        this.cacheVersion++
        this.cacheInvalidatedAt = new Date()
      }
    },
    
    /**
     * Очистить все рецепты
     */
    clear(): void {
      this.items = {}
      this.ids = []
      this.cacheVersion++
      this.cacheInvalidatedAt = new Date()
    },
    
    /**
     * Инвалидировать кеш (для принудительного обновления)
     */
    invalidateCache(): void {
      this.cacheVersion++
      this.cacheInvalidatedAt = new Date()
    },
    
    /**
     * Установить состояние загрузки
     */
    setLoading(loading: boolean): void {
      this.loading = loading
      if (!loading) {
        this.lastFetch = new Date()
      }
    },
    
    /**
     * Установить ошибку
     */
    setError(error: string | null): void {
      this.error = error
    },
  },
  getters: {
    /**
     * Получить рецепт по ID (O(1) вместо O(n))
     */
    recipeById: (state) => {
      return (id: number): Recipe | undefined => {
        return state.items[id]
      }
    },
    
    /**
     * Получить все рецепты как массив (в порядке ids)
     */
    allRecipes: (state): Recipe[] => {
      return state.ids.map(id => state.items[id]).filter(Boolean)
    },
    
    /**
     * Проверка, есть ли рецепты в store
     */
    hasRecipes: (state): boolean => {
      return state.ids.length > 0
    },
    
    /**
     * Количество рецептов
     */
    recipesCount: (state): number => {
      return state.ids.length
    },
  },
})

