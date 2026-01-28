import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import {
  getStageByPhaseName,
  getStageByTemplateCode,
  getStageByPhaseIndex,
  getStageForPhase,
  getStageInfo,
  getStageColor,
  getStageLabel,
  getStageOrder,
  isValidStage,
  getNextStage,
  getPrevStage,
  calculateCycleProgress,
  GROW_STAGES,
  GROW_STAGES_ORDERED,
} from '../growStages'
import type { GrowStage } from '../growStages'

describe('growStages', () => {
  describe('getStageByPhaseName', () => {
    it('should return correct stage for known phase names', () => {
      expect(getStageByPhaseName('germination')).toBe('planting')
      expect(getStageByPhaseName('vegetation')).toBe('veg')
      expect(getStageByPhaseName('flowering')).toBe('flowering')
      expect(getStageByPhaseName('harvest')).toBe('harvest')
    })

    it('should return undefined for unknown phase names', () => {
      expect(getStageByPhaseName('unknown_phase')).toBeUndefined()
    })
  })

  describe('getStageByTemplateCode', () => {
    it('should return correct stage for template codes', () => {
      expect(getStageByTemplateCode('ROOTING')).toBe('rooting')
      expect(getStageByTemplateCode('VEG')).toBe('veg')
      expect(getStageByTemplateCode('FLOWER')).toBe('flowering')
      expect(getStageByTemplateCode('FRUIT')).toBe('harvest')
      expect(getStageByTemplateCode('HARVEST')).toBe('harvest')
    })

    it('should return undefined for unknown codes', () => {
      expect(getStageByTemplateCode('UNKNOWN')).toBeUndefined()
    })
  })

  describe('getStageByPhaseIndex', () => {
    it('should return correct stage for phase index', () => {
      expect(getStageByPhaseIndex(0)).toBe('planting')
      expect(getStageByPhaseIndex(1)).toBe('veg')
      expect(getStageByPhaseIndex(2)).toBe('veg')
      expect(getStageByPhaseIndex(3)).toBe('flowering')
    })

    it('should return default stage for high index', () => {
      expect(getStageByPhaseIndex(10)).toBe('veg')
    })
  })

  describe('getStageForPhase', () => {
    it('should prioritize phase name over index', () => {
      expect(getStageForPhase('flowering', 0)).toBe('flowering')
    })

    it('should prioritize template code over name', () => {
      expect(getStageForPhase('flowering', 0, 4, 'FRUIT')).toBe('harvest')
    })

    it('should use index when name is not found', () => {
      expect(getStageForPhase('unknown', 0)).toBe('planting')
      expect(getStageForPhase('unknown', 1)).toBe('veg')
    })

    it('should return undefined when both are invalid', () => {
      expect(getStageForPhase('unknown', -1)).toBeUndefined()
    })
  })

  describe('getStageInfo', () => {
    it('should return correct stage info', () => {
      const info = getStageInfo('planting')
      expect(info).toBeDefined()
      expect(info?.id).toBe('planting')
      expect(info?.label).toBe('Посадка')
      expect(info?.color).toBe('var(--accent-lime)')
    })

    it('should return undefined for invalid stage', () => {
      expect(getStageInfo('INVALID' as GrowStage)).toBeUndefined()
    })
  })

  describe('getStageColor', () => {
    it('should return correct color for stages', () => {
      expect(getStageColor('planting')).toBe('var(--accent-lime)')
      expect(getStageColor('veg')).toBe('var(--accent-green)')
      expect(getStageColor('flowering')).toBe('var(--accent-amber)')
      expect(getStageColor('harvest')).toBe('var(--accent-red)')
    })

    it('should return undefined for invalid stage', () => {
      expect(getStageColor('INVALID' as GrowStage)).toBeUndefined()
    })
  })

  describe('getStageLabel', () => {
    it('should return correct label for stages', () => {
      expect(getStageLabel('planting')).toBe('Посадка')
      expect(getStageLabel('veg')).toBe('Вегетация')
      expect(getStageLabel('flowering')).toBe('Цветение')
      expect(getStageLabel('harvest')).toBe('Сбор урожая')
    })

    it('should return undefined for invalid stage', () => {
      expect(getStageLabel('INVALID' as GrowStage)).toBeUndefined()
    })
  })

  describe('getStageOrder', () => {
    it('should return correct order for stages', () => {
      expect(getStageOrder('planting')).toBe(0)
      expect(getStageOrder('rooting')).toBe(1)
      expect(getStageOrder('veg')).toBe(2)
      expect(getStageOrder('flowering')).toBe(3)
      expect(getStageOrder('harvest')).toBe(4)
    })

    it('should return -1 for invalid stage', () => {
      expect(getStageOrder('INVALID' as GrowStage)).toBe(-1)
    })
  })

  describe('isValidStage', () => {
    it('should return true for valid stages', () => {
      expect(isValidStage('planting')).toBe(true)
      expect(isValidStage('veg')).toBe(true)
      expect(isValidStage('flowering')).toBe(true)
    })

    it('should return false for invalid stages', () => {
      expect(isValidStage('INVALID' as GrowStage)).toBe(false)
      expect(isValidStage('' as GrowStage)).toBe(false)
    })
  })

  describe('getNextStage', () => {
    it('should return next stage', () => {
      expect(getNextStage('planting')).toBe('rooting')
      expect(getNextStage('rooting')).toBe('veg')
      expect(getNextStage('veg')).toBe('flowering')
      expect(getNextStage('flowering')).toBe('harvest')
    })

    it('should return undefined for last stage', () => {
      expect(getNextStage('harvest')).toBeUndefined()
    })

    it('should return undefined for invalid stage', () => {
      expect(getNextStage('INVALID' as GrowStage)).toBeUndefined()
    })
  })

  describe('getPrevStage', () => {
    it('should return previous stage', () => {
      expect(getPrevStage('rooting')).toBe('planting')
      expect(getPrevStage('veg')).toBe('rooting')
      expect(getPrevStage('flowering')).toBe('veg')
      expect(getPrevStage('harvest')).toBe('flowering')
    })

    it('should return undefined for first stage', () => {
      expect(getPrevStage('planting')).toBeUndefined()
    })

    it('should return undefined for invalid stage', () => {
      expect(getPrevStage('INVALID' as GrowStage)).toBeUndefined()
    })
  })

  describe('calculateCycleProgress', () => {
    const mockRecipe = {
      phases: [
        { id: 1, name: 'germination', duration_hours: 24 },
        { id: 2, name: 'vegetation', duration_hours: 336 }, // 14 days
        { id: 3, name: 'flowering', duration_hours: 240 }, // 10 days
      ],
    }

    beforeEach(() => {
      vi.useFakeTimers()
    })

    afterEach(() => {
      vi.useRealTimers()
    })

    it('should calculate progress correctly for started cycle', () => {
      const startedAt = new Date('2024-01-01T00:00:00Z')
      const now = new Date('2024-01-02T12:00:00Z') // 36 hours later
      
      vi.setSystemTime(now)

      const progress = calculateCycleProgress({
        recipe: mockRecipe,
        started_at: startedAt.toISOString(),
        current_phase_index: 0,
        phase_progress: null,
      })

      // 36 hours / 24 hours = 150% of first phase, but capped at 100% per phase
      // Then we move to phase 1, which is 12 hours / 336 hours = ~3.57%
      // Overall: (100% * 1 phase) / 3 phases + (3.57% * 1 phase) / 3 phases = ~34.5%
      expect(progress).toBeGreaterThan(30)
      expect(progress).toBeLessThan(40)
    })

    it('should return 0 for not started cycle', () => {
      const progress = calculateCycleProgress({
        recipe: mockRecipe,
        started_at: null,
        current_phase_index: null,
        phase_progress: null,
      })

      expect(progress).toBe(0)
    })

    it('should use phase_progress when provided', () => {
      const startedAt = new Date('2024-01-01T00:00:00Z')
      
      vi.setSystemTime(startedAt)

      const progress = calculateCycleProgress({
        recipe: mockRecipe,
        started_at: startedAt.toISOString(),
        current_phase_index: 1,
        phase_progress: 50, // 50% of second phase
      })

      // Phase 0: 100% (completed)
      // Phase 1: 50% (in progress)
      // Phase 2: 0% (not started)
      // Overall: (100% + 50% + 0%) / 3 = 50%
      expect(progress).toBeCloseTo(50, 1)
    })

    it('should handle cycle with single phase', () => {
      const singlePhaseRecipe = {
        phases: [{ id: 1, name: 'vegetation', duration_hours: 100 }],
      }

      const startedAt = new Date('2024-01-01T00:00:00Z')
      const now = new Date('2024-01-03T02:00:00Z') // 50 hours later
      
      vi.setSystemTime(now)

      const progress = calculateCycleProgress({
        recipe: singlePhaseRecipe,
        started_at: startedAt.toISOString(),
        current_phase_index: 0,
        phase_progress: null,
      })

      // 50 hours / 100 hours = 50%
      expect(progress).toBeCloseTo(50, 1)
    })

    it('should handle cycle without phases', () => {
      const noPhasesRecipe = {
        phases: [],
      }

      const progress = calculateCycleProgress({
        recipe: noPhasesRecipe,
        started_at: new Date().toISOString(),
        current_phase_index: null,
        phase_progress: null,
      })

      expect(progress).toBe(0)
    })
  })

  describe('GROW_STAGES_ORDERED', () => {
    it('should be ordered correctly', () => {
      expect(GROW_STAGES_ORDERED[0]).toBe('planting')
      expect(GROW_STAGES_ORDERED[1]).toBe('rooting')
      expect(GROW_STAGES_ORDERED[2]).toBe('veg')
      expect(GROW_STAGES_ORDERED[3]).toBe('flowering')
      expect(GROW_STAGES_ORDERED[4]).toBe('harvest')
    })
  })

  describe('GROW_STAGES', () => {
    it('should contain all stages', () => {
      expect(GROW_STAGES.planting).toBeDefined()
      expect(GROW_STAGES.rooting).toBeDefined()
      expect(GROW_STAGES.veg).toBeDefined()
      expect(GROW_STAGES.flowering).toBeDefined()
      expect(GROW_STAGES.harvest).toBeDefined()
    })
  })
})
