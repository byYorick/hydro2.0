import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ErrorState from '../ErrorState.vue'

describe('ErrorState', () => {
  it('показывает заголовок, описание и действие', () => {
    const wrapper = mount(ErrorState, {
      props: {
        title: 'Не удалось загрузить тревоги',
        description: 'Проверьте связь с сервером.',
      },
      slots: {
        action: '<button type="button">Повторить</button>',
      },
    })

    expect(wrapper.text()).toContain('Не удалось загрузить тревоги')
    expect(wrapper.text()).toContain('Проверьте связь с сервером.')
    expect(wrapper.get('button').text()).toBe('Повторить')
  })
})
