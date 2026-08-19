import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import RecipePhotoperiodBar from '@/Components/Recipes/RecipePhotoperiodBar.vue'

describe('RecipePhotoperiodBar.vue', () => {
  it('рисует один сегмент, когда световой день не пересекает полночь', () => {
    const wrapper = mount(RecipePhotoperiodBar, {
      props: { photoperiodHours: 12, startTime: '06:00:00' },
    })

    const segments = wrapper.findAll('span.absolute')
    expect(segments).toHaveLength(1)
    expect(segments[0].attributes('style')).toContain('left: 25%')
    expect(segments[0].attributes('style')).toContain('width: 50%')
  })

  it('разбивает световой день на два сегмента при переходе через полночь', () => {
    const wrapper = mount(RecipePhotoperiodBar, {
      props: { photoperiodHours: 18, startTime: '18:00:00' },
    })

    const segments = wrapper.findAll('span.absolute')
    expect(segments).toHaveLength(2)
    expect(segments[0].attributes('style')).toContain('left: 75%')
    expect(segments[1].attributes('style')).toContain('left: 0%')
  })

  it('показывает длительность и время включения', () => {
    const wrapper = mount(RecipePhotoperiodBar, {
      props: { photoperiodHours: 16, startTime: '06:30:00' },
    })

    expect(wrapper.text()).toContain('16 ч с 06:30')
  })

  it('не рисует сегменты без фотопериода', () => {
    const wrapper = mount(RecipePhotoperiodBar, {
      props: { photoperiodHours: null, startTime: null },
    })

    expect(wrapper.findAll('span.absolute')).toHaveLength(0)
    expect(wrapper.text()).toContain('—')
  })
})
