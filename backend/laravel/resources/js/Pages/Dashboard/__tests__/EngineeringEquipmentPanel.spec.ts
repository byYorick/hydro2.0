import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { UnifiedZone } from '@/composables/useUnifiedDashboard'
const list = vi.hoisted(() => vi.fn())
vi.mock('@/services/api', () => ({ api: { nodes: { list } } }))
vi.mock('@inertiajs/vue3', () => ({ Link: { props: ['href'], template: '<a :href="href"><slot /></a>' } }))
import EngineeringEquipmentPanel from '../EngineeringEquipmentPanel.vue'

const now = Date.now()
const zones = [1, 2].map(id => ({
  id, name: `Зона ${id}`, status: 'RUNNING', greenhouse: null, recipe: null, plant: null, crop: null, cycle: null, alerts_count: 0, alerts_preview: [],
  devices: { total: 1, online: id === 1 ? 0 : 1 }, telemetry: { ph: 5.8, ec: 1.6, temperature: 22, humidity: 60, co2: null, updated_at: new Date(now).toISOString() },
  targets: { ph: { min: 5.5, max: 6.5 }, ec: { min: 1.2, max: 1.8 }, temperature: null },
})) as UnifiedZone[]
const devices = [
  { id: 11, uid: 'offline-11', status: 'offline', zone_id: 1, last_seen_at: new Date(now - 300_000).toISOString(), channels: [] },
  { id: 22, uid: 'online-22', status: 'online', zone_id: 2, last_seen_at: new Date(now).toISOString(), channels: [{ channel: 'pump_acid', type: 'ACTUATOR', binding_role: 'pump_acid', pump_calibration: null }] },
  { id: 33, uid: 'healthy-33', status: 'online', zone_id: 2, channels: [] },
]
const wrappers: ReturnType<typeof mount>[] = []
function render() { const wrapper = mount(EngineeringEquipmentPanel, { props: { zones, now } }); wrappers.push(wrapper); return wrapper }
beforeEach(() => { window.history.replaceState({}, '', '/'); list.mockReset().mockResolvedValue(devices) })
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()) })

describe('Инженерное оборудование', () => {
  it('показывает конкретные узлы для проверки и приводит к их карточкам', async () => {
    const wrapper = render()
    await flushPromises()
    expect(wrapper.findAll('.equipment-row')).toHaveLength(2)
    expect(wrapper.get('a[href="/devices/11"]').text()).toBe('offline-11')
    expect(wrapper.text()).toContain('Без калибровки насосов: 1')
    expect(wrapper.find('a[href="/devices/33"]').exists()).toBe(false)
  })
  it('сохраняет контекст зоны из перехода «Диагностика»', async () => {
    window.history.replaceState({}, '', '/?nodeZone=1&nodes=all')
    const wrapper = render()
    await flushPromises()
    expect(wrapper.findAll('.equipment-row')).toHaveLength(1)
    expect(wrapper.text()).toContain('offline-11')
    expect(wrapper.text()).not.toContain('online-22')
  })
  it('не выдаёт ошибку запроса за отсутствие проблем и позволяет повторить загрузку', async () => {
    list.mockRejectedValueOnce(new Error('offline'))
    const wrapper = render()
    await flushPromises()
    expect(wrapper.text()).toContain('Не удалось загрузить оборудование')
    expect(wrapper.text()).not.toContain('Нет оборудования по выбранным условиям')
    await wrapper.findAll('button').find(button => button.text() === 'Повторить')!.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.equipment-row')).toHaveLength(2)
  })
})
