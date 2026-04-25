import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LaunchFooterNav from '../LaunchFooterNav.vue'
import type { StepCompletion } from '../types'

describe('LaunchFooterNav', () => {
  it('disables Назад on first step', () => {
    const w = mount(LaunchFooterNav, {
      props: {
        active: 0,
        total: 5,
        completion: ['current', 'todo', 'todo', 'todo', 'todo'] as StepCompletion[],
      },
    })
    const back = w.findAll('button').find((b) => b.text() === 'Назад')!
    expect(back.attributes('disabled')).toBeDefined()
  })

  it('emits next on Дальше click when not last step', async () => {
    const w = mount(LaunchFooterNav, {
      props: {
        active: 1,
        total: 5,
        completion: ['done', 'current', 'todo', 'todo', 'todo'] as StepCompletion[],
      },
    })
    const next = w.findAll('button').find((b) => b.text().includes('Дальше'))!
    await next.trigger('click')
    expect(w.emitted('next')).toBeTruthy()
  })

  it('shows Запустить on last step and emits launch', async () => {
    const w = mount(LaunchFooterNav, {
      props: {
        active: 4,
        total: 5,
        completion: ['done', 'done', 'done', 'done', 'current'] as StepCompletion[],
        canLaunch: true,
      },
    })
    const launch = w.findAll('button').find((b) => b.text().includes('Запустить'))!
    expect(launch).toBeTruthy()
    await launch.trigger('click')
    expect(w.emitted('launch')).toBeTruthy()
  })

  it('disables Запустить when canLaunch=false', () => {
    const w = mount(LaunchFooterNav, {
      props: {
        active: 4,
        total: 5,
        completion: ['done', 'done', 'done', 'done', 'current'] as StepCompletion[],
        canLaunch: false,
      },
    })
    const launch = w.findAll('button').find((b) => b.text().includes('Запустить'))!
    expect(launch.attributes('disabled')).toBeDefined()
  })

  it('shows progress count', () => {
    const w = mount(LaunchFooterNav, {
      props: {
        active: 2,
        total: 5,
        completion: ['done', 'done', 'current', 'todo', 'todo'] as StepCompletion[],
      },
    })
    expect(w.text()).toContain('2 из 5')
  })
})
