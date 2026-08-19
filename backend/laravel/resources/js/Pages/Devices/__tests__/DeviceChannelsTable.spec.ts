import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import DeviceChannelsTable from '../DeviceChannelsTable.vue'

describe('DeviceChannelsTable.vue', () => {
  it('показывает русские заголовки и кнопку теста', () => {
    const wrapper = mount(DeviceChannelsTable, {
      props: {
        channels: [
          { channel: 'ph_sensor', type: 'SENSOR', metric: 'PH' },
        ],
      },
    })

    expect(wrapper.text()).toContain('Канал')
    expect(wrapper.text()).toContain('Тип')
    expect(wrapper.text()).toContain('Конфиг')
    expect(wrapper.text()).toContain('Действия')
    expect(wrapper.text()).toContain('Тест')
    expect(wrapper.text()).not.toContain('Channel')
    expect(wrapper.text()).not.toContain('Actions')
  })
})
