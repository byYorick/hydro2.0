import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { ref } from 'vue'
import { useWizardValidation, validateGreenhouseStep, validateZoneStep, validatePlantStep, validateRecipeStep, validateStartCycleStep } from '../useWizardValidation'
import { useWizardState } from '../useWizardState'
import type { GrowCycleWizardData } from '../useWizardValidation'

describe('useWizardValidation', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  describe('validateGreenhouseStep', () => {
    it('should return empty array when greenhouseId is provided', () => {
      const data: GrowCycleWizardData = {
        greenhouseId: 1,
      }
      expect(validateGreenhouseStep(data)).toEqual([])
    })

    it('should return empty array when greenhouse object is provided', () => {
      const data: GrowCycleWizardData = {
        greenhouse: {
          id: 1,
          name: 'Test Greenhouse',
        },
      }
      expect(validateGreenhouseStep(data)).toEqual([])
    })

    it('should return error when neither greenhouseId nor greenhouse is provided', () => {
      const data: GrowCycleWizardData = {}
      const errors = validateGreenhouseStep(data)
      expect(errors.length).toBeGreaterThan(0)
      expect(errors[0]).toContain('теплиц')
    })
  })

  describe('validateZoneStep', () => {
    it('should return empty array when zoneId is provided', () => {
      const data: GrowCycleWizardData = {
        zoneId: 1,
      }
      expect(validateZoneStep(data)).toEqual([])
    })

    it('should return empty array when zone object is provided', () => {
      const data: GrowCycleWizardData = {
        zone: {
          id: 1,
          name: 'Test Zone',
          greenhouse_id: 1,
        },
      }
      expect(validateZoneStep(data)).toEqual([])
    })

    it('should return error when neither zoneId nor zone is provided', () => {
      const data: GrowCycleWizardData = {}
      const errors = validateZoneStep(data)
      expect(errors.length).toBeGreaterThan(0)
      expect(errors[0]).toContain('зон')
    })
  })

  describe('validatePlantStep', () => {
    it('should return empty array when plantId is provided', () => {
      const data: GrowCycleWizardData = {
        plantId: 1,
      }
      expect(validatePlantStep(data)).toEqual([])
    })

    it('should return empty array when plant object is provided', () => {
      const data: GrowCycleWizardData = {
        plant: {
          id: 1,
          name: 'Test Plant',
        },
      }
      expect(validatePlantStep(data)).toEqual([])
    })

    it('should return error when neither plantId nor plant is provided', () => {
      const data: GrowCycleWizardData = {}
      const errors = validatePlantStep(data)
      expect(errors.length).toBeGreaterThan(0)
      expect(errors[0]).toContain('растени')
    })
  })

  describe('validateRecipeStep', () => {
    it('should return empty array when recipeId is provided', () => {
      const data: GrowCycleWizardData = {
        recipeId: 1,
      }
      expect(validateRecipeStep(data)).toEqual([])
    })

    it('should return empty array when recipe object is provided', () => {
      const data: GrowCycleWizardData = {
        recipe: {
          id: 1,
          name: 'Test Recipe',
          phases: [
            { name: 'Phase 1', duration_hours: 24 },
          ],
        },
      }
      expect(validateRecipeStep(data)).toEqual([])
    })

    it('should return error when neither recipeId nor recipe is provided', () => {
      const data: GrowCycleWizardData = {}
      const errors = validateRecipeStep(data)
      expect(errors.length).toBeGreaterThan(0)
      expect(errors[0]).toContain('рецепт')
    })

    it('should return error when recipe has no phases', () => {
      const data: GrowCycleWizardData = {
        recipe: {
          id: 1,
          name: 'Test Recipe',
          phases: [],
        },
      }
      const errors = validateRecipeStep(data)
      expect(errors.length).toBeGreaterThan(0)
      expect(errors[0]).toContain('фаз')
    })
  })

  describe('validateStartCycleStep', () => {
    it('should return empty array when all required fields are provided', () => {
      const data: GrowCycleWizardData = {
        zoneId: 1,
        recipeId: 1,
        plantingAt: '2024-01-01T00:00:00Z',
      }
      expect(validateStartCycleStep(data)).toEqual([])
    })

    it('should return error when zoneId is missing', () => {
      const data: GrowCycleWizardData = {
        recipeId: 1,
        plantingAt: '2024-01-01T00:00:00Z',
      }
      const errors = validateStartCycleStep(data)
      expect(errors.length).toBeGreaterThan(0)
      expect(errors[0]).toContain('зон')
    })

    it('should return error when recipeId is missing', () => {
      const data: GrowCycleWizardData = {
        zoneId: 1,
        plantingAt: '2024-01-01T00:00:00Z',
      }
      const errors = validateStartCycleStep(data)
      expect(errors.length).toBeGreaterThan(0)
      expect(errors[0]).toContain('рецепт')
    })

    it('should return error when plantingAt is missing', () => {
      const data: GrowCycleWizardData = {
        zoneId: 1,
        recipeId: 1,
      }
      const errors = validateStartCycleStep(data)
      expect(errors.length).toBeGreaterThan(0)
      expect(errors[0]).toContain('дату')
    })
  })

  describe('useWizardValidation', () => {
    it('should validate step correctly', async () => {
      const steps = [
        { id: 'greenhouse', title: 'Greenhouse' },
        { id: 'zone', title: 'Zone' },
        { id: 'plant', title: 'Plant' },
        { id: 'recipe', title: 'Recipe' },
        { id: 'start', title: 'Start' },
      ]

      const wizardState = useWizardState<GrowCycleWizardData>(steps, {})
      const { validateStep } = useWizardValidation(wizardState)

      // Валидация шага 0 (greenhouse) без данных должна вернуть false
      const isValid = await validateStep(0)
      expect(isValid).toBe(false)
      expect(wizardState.errors.value['step_0']).toBeDefined()

      // Добавляем данные и валидируем снова
      wizardState.formData.value.greenhouseId = 1
      const isValidAfter = await validateStep(0)
      expect(isValidAfter).toBe(true)
      expect(wizardState.errors.value['step_0']).toBeUndefined()
    })

    it('should validate all steps', () => {
      const steps = [
        { id: 'greenhouse', title: 'Greenhouse' },
        { id: 'zone', title: 'Zone' },
        { id: 'plant', title: 'Plant' },
        { id: 'recipe', title: 'Recipe' },
        { id: 'start', title: 'Start' },
      ]

      const wizardState = useWizardState<GrowCycleWizardData>(steps, {})
      const { validateAll } = useWizardValidation(wizardState)

      // Валидация без данных должна вернуть false
      const isValid = validateAll()
      expect(isValid).toBe(false)

      // Добавляем все необходимые данные
      wizardState.formData.value = {
        greenhouseId: 1,
        zoneId: 1,
        plantId: 1,
        recipeId: 1,
        plantingAt: '2024-01-01T00:00:00Z',
      }

      const isValidAfter = validateAll()
      expect(isValidAfter).toBe(true)
    })
  })
})


