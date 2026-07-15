import { describe, expect, it } from 'vitest'
import {
  allowedManualStepsForStage,
  resolveAllowedManualSteps,
} from '@/composables/zoneAutomationUtils'

describe('zoneAutomationUtils manual steps', () => {
  it('возвращает start-кнопки для startup', () => {
    expect(allowedManualStepsForStage('startup')).toEqual([
      'clean_fill_start',
      'solution_fill_start',
      'force_solution_fill_start',
    ])
  })

  it('возвращает stop и abort на command-stage clean_fill_start', () => {
    expect(allowedManualStepsForStage('clean_fill_start')).toEqual([
      'clean_fill_stop',
      'solution_change_abort',
    ])
  })

  it('derive из current_stage если API вернул пустой список в manual', () => {
    expect(resolveAllowedManualSteps('manual', 'startup', [])).toEqual([
      'clean_fill_start',
      'solution_fill_start',
      'force_solution_fill_start',
    ])
  })

  it('не derive в auto', () => {
    expect(resolveAllowedManualSteps('auto', 'startup', [])).toEqual([])
  })

  it('предпочитает непустой список из API', () => {
    expect(resolveAllowedManualSteps('manual', 'startup', ['irrigation_stop'])).toEqual([
      'irrigation_stop',
    ])
  })
})
