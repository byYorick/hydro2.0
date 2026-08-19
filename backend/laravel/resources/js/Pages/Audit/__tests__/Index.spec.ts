import { mount, flushPromises, config } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const RecycleScrollerStub = {
  name: 'RecycleScroller',
  props: {
    items: { type: Array, required: true },
    'item-size': { type: Number, default: 0 },
    itemSize: { type: Number, default: 0 },
    'key-field': { type: String, default: 'id' },
  },
  template: `
    <div class="recycle-scroller-stub">
      <template v-for="(item, index) in items" :key="item.id ?? index">
        <slot :item="item" :index="index" />
      </template>
    </div>
  `,
}

config.global.components.RecycleScroller = RecycleScrollerStub

const reloadMock = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))
const mockPage = vi.hoisted(() => vi.fn())

vi.mock('@inertiajs/vue3', () => ({
  usePage: () => mockPage(),
  router: { reload: reloadMock },
}))

vi.mock('@/Layouts/AppLayout.vue', () => ({
  default: { name: 'AppLayout', template: '<div data-testid="app-layout"><slot /></div>' },
}))

vi.mock('@/Pages/Logs/Index.vue', () => ({
  default: {
    name: 'LogsIndex',
    props: ['embedded'],
    template: '<div data-testid="embedded-logs">embedded logs</div>',
  },
}))

import AuditIndex from '../Index.vue'

function mountAudit() {
  mockPage.mockReturnValue({
    props: {
      logs: [
        {
          id: 11,
          level: 'info',
          message: 'Config applied',
          context: { zone_id: 3 },
          created_at: '2026-08-19T08:00:00Z',
        },
      ],
    },
  })

  return mount(AuditIndex)
}

describe('Audit/Index.vue', () => {
  beforeEach(() => {
    reloadMock.mockClear()
    window.history.replaceState({}, '', '/audit')
  })

  it('показывает заголовок «Журнал» и табы Аудит / Системные логи', async () => {
    const wrapper = mountAudit()
    await flushPromises()

    expect(wrapper.get('h1').text()).toBe('Журнал')
    const tabs = wrapper.find('[data-testid="journal-tabs"]')
    const labels = tabs.findAll('button[role="tab"]').map((button) => button.text())
    expect(labels).toEqual(['Аудит', 'Системные логи'])
    expect(wrapper.text()).toContain('Config applied')
    expect(wrapper.find('[data-testid="embedded-logs"]').exists()).toBe(false)

    wrapper.unmount()
  })

  it('переключает на системные логи без второго корня меню', async () => {
    const wrapper = mountAudit()
    await flushPromises()

    const logsTab = wrapper
      .find('[data-testid="journal-tabs"]')
      .findAll('button[role="tab"]')
      .find((button) => button.text() === 'Системные логи')

    await logsTab?.trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="embedded-logs"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('Config applied')

    wrapper.unmount()
  })
})
