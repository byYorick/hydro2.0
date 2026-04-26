import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import HStepper from '../HStepper.vue'
import type { LaunchStep, StepCompletion } from '../types'

const steps: LaunchStep[] = [
  { id: 'zone', label: 'Зона', sub: 'теплица' },
  { id: 'recipe', label: 'Рецепт', sub: 'фазы' },
  { id: 'preview', label: 'Подтверждение', sub: 'запуск' },
]

describe('HStepper', () => {
  it('renders all steps with labels and subs', () => {
    const w = mount(HStepper, {
      props: {
        steps,
        active: 0,
        completion: ['current', 'todo', 'todo'] as StepCompletion[],
      },
    })
    expect(w.text()).toContain('Зона')
    expect(w.text()).toContain('теплица')
    expect(w.text()).toContain('Рецепт')
    expect(w.text()).toContain('Подтверждение')
  })

  it('emits select(index) on bullet click', async () => {
    const w = mount(HStepper, {
      props: {
        steps,
        active: 0,
        completion: ['current', 'todo', 'todo'] as StepCompletion[],
      },
    })
    await w.findAll('button')[2].trigger('click')
    expect(w.emitted('select')).toBeTruthy()
    expect(w.emitted('select')![0]).toEqual([2])
  })

  it('marks active step with aria-current="step"', () => {
    const w = mount(HStepper, {
      props: {
        steps,
        active: 1,
        completion: ['done', 'current', 'todo'] as StepCompletion[],
      },
    })
    const buttons = w.findAll('button')
    expect(buttons[0].attributes('aria-current')).toBeUndefined()
    expect(buttons[1].attributes('aria-current')).toBe('step')
  })

  it('shows ✓ for done steps, ! for warn', () => {
    const w = mount(HStepper, {
      props: {
        steps,
        active: 2,
        completion: ['done', 'warn', 'current'] as StepCompletion[],
      },
    })
    const buttons = w.findAll('button')
    expect(buttons[0].text()).toContain('✓')
    expect(buttons[1].text()).toContain('!')
  })
})
