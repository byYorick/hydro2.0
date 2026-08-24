import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ZoneAutomationBlockBanner from '@/Components/ZoneAutomationBlockBanner.vue'

const block = {
  blocked: true,
  reason_code: 'biz_ae3_task_failed',
  severity: 'critical',
  message: 'Цикл прерван',
  since: '2026-08-24T10:00:00Z',
  alert_id: 1,
  alerts_count: 1,
}

describe('ZoneAutomationBlockBanner', () => {
  it('hides unblock without permission', () => {
    const wrapper = mount(ZoneAutomationBlockBanner, {
      props: { block, canUnblock: false },
    })
    expect(wrapper.find('[data-testid="zone-automation-block-unblock"]').exists()).toBe(false)
  })

  it('emits unblock after confirm and reason', async () => {
    const wrapper = mount(ZoneAutomationBlockBanner, {
      props: { block, canUnblock: true },
    })
    await wrapper.get('[data-testid="zone-automation-block-unblock"]').trigger('click')
    await wrapper.get('[data-testid="zone-operator-unblock-reason"]').setValue('hung irrig')
    await wrapper.get('[data-testid="zone-operator-unblock-confirm"]').setValue(true)
    await wrapper.get('[data-testid="zone-operator-unblock-submit"]').trigger('click')
    expect(wrapper.emitted('unblock')?.[0]?.[0]).toEqual({
      reason: 'hung irrig',
      confirm: true,
    })
  })
})
