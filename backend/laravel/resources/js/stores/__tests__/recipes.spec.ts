import { setActivePinia, createPinia } from 'pinia'
import { useRecipesStore } from '../recipes'
import type { Recipe } from '@/types/Recipe'

describe('recipes store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  const mockRecipe1: Recipe = {
    id: 1,
    name: 'Recipe 1',
    description: 'Test recipe 1',
    phases: [],
    phases_count: 0,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  }

  const mockRecipe2: Recipe = {
    id: 2,
    name: 'Recipe 2',
    description: 'Test recipe 2',
    phases: [],
    phases_count: 0,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  }

  it('should initialize with empty items', () => {
    const store = useRecipesStore()
    expect(store.items).toEqual({})
    expect(store.ids).toEqual([])
  })

  it('should init from props', () => {
    const store = useRecipesStore()
    store.initFromProps({ recipes: [mockRecipe1] })
    expect(store.recipesCount).toBe(1)
    expect(store.recipeById(1)).toEqual(mockRecipe1)
  })

  it('should upsert existing recipe', () => {
    const store = useRecipesStore()
    store.initFromProps({ recipes: [mockRecipe1] })
    
    const updatedRecipe = { ...mockRecipe1, name: 'Recipe 1 updated' }
    store.upsert(updatedRecipe)
    
    expect(store.recipesCount).toBe(1)
    expect(store.recipeById(1)?.name).toBe('Recipe 1 updated')
  })

  it('should add new recipe on upsert', () => {
    const store = useRecipesStore()
    store.initFromProps({ recipes: [mockRecipe1] })
    store.upsert(mockRecipe2)
    
    expect(store.recipesCount).toBe(2)
    expect(store.recipeById(2)).toEqual(mockRecipe2)
  })

  it('should remove recipe', () => {
    const store = useRecipesStore()
    store.initFromProps({ recipes: [mockRecipe1, mockRecipe2] })
    
    store.remove(1)
    
    expect(store.recipesCount).toBe(1)
    expect(store.recipeById(2)?.id).toBe(2)
  })

  it('should clear all recipes', () => {
    const store = useRecipesStore()
    store.initFromProps({ recipes: [mockRecipe1, mockRecipe2] })
    
    store.clear()
    
    expect(store.items).toEqual({})
    expect(store.ids).toEqual([])
  })

  it('should get recipe by id', () => {
    const store = useRecipesStore()
    store.initFromProps({ recipes: [mockRecipe1, mockRecipe2] })
    
    const recipe = store.recipeById(1)
    
    expect(recipe).toEqual(mockRecipe1)
  })

  it('should get all recipes as array', () => {
    const store = useRecipesStore()
    store.initFromProps({ recipes: [mockRecipe1, mockRecipe2] })
    
    const allRecipes = store.allRecipes
    
    expect(allRecipes.length).toBe(2)
    expect(allRecipes).toContainEqual(mockRecipe1)
    expect(allRecipes).toContainEqual(mockRecipe2)
  })

  it('should check if has recipes', () => {
    const store = useRecipesStore()
    
    expect(store.hasRecipes).toBe(false)
    
    store.initFromProps({ recipes: [mockRecipe1] })
    expect(store.hasRecipes).toBe(true)
  })

  it('should get recipes count', () => {
    const store = useRecipesStore()
    
    expect(store.recipesCount).toBe(0)
    
    store.initFromProps({ recipes: [mockRecipe1, mockRecipe2] })
    expect(store.recipesCount).toBe(2)
  })

  it('should track loading state', () => {
    const store = useRecipesStore()
    
    expect(store.loading).toBe(false)
    
    store.setLoading(true)
    expect(store.loading).toBe(true)
    
    store.setLoading(false)
    expect(store.loading).toBe(false)
    expect(store.lastFetch).toBeInstanceOf(Date)
  })

  it('should track error state', () => {
    const store = useRecipesStore()
    
    expect(store.error).toBe(null)
    
    store.setError('Test error')
    expect(store.error).toBe('Test error')
    
    store.setError(null)
    expect(store.error).toBe(null)
  })

  it('should invalidate cache', () => {
    const store = useRecipesStore()
    const initialVersion = store.cacheVersion
    
    store.invalidateCache()
    
    expect(store.cacheVersion).toBe(initialVersion + 1)
    expect(store.cacheInvalidatedAt).toBeInstanceOf(Date)
  })
})

