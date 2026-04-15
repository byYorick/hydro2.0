import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import ConfigChangesTimeline from '../ZoneAutomation/ConfigChangesTimeline.vue'

vi.mock('@/services/api/zoneConfigMode', () => {
  return {
    zoneConfigModeApi: {
      show: vi.fn(),
      update: vi.fn(),
      extend: vi.fn(),
      changes: vi.fn(),
      updatePhaseConfig: vi.fn(),
    },
  }
})

import { zoneConfigModeApi } from '@/services/api/zoneConfigMode'

const changes = [
  {
    id: 10,
    revision: 5,
    namespace: 'recipe.phase',
    diff: { ec_target: { before: 1.8, after: 2.0 } },
    user_id: 7,
    reason: 'flowering EC bump',
    created_at: '2026-04-15T10:00:00Z',
  },
  {
    id: 9,
    revision: 4,
    namespace: 'zone.config_mode',
    diff: { from: 'locked', to: 'live' },
    user_id: 7,
    reason: 'tuning',
    created_at: '2026-04-15T09:55:00Z',
  },
]

describe('ConfigChangesTimeline', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(zoneConfigModeApi.changes).mockResolvedValue({ zone_id: 1, changes })
  })

  it('renders list of changes', async () => {
    const w = mount(ConfigChangesTimeline, { props: { zoneId: 1 } })
    await flushPromises()
    const items = w.find('[data-testid="config-changes-list"]').findAll('li')
    expect(items.length).toBe(2)
    expect(items[0].text()).toContain('recipe.phase')
    expect(items[0].text()).toContain('flowering EC bump')
  })

  it('filters by namespace', async () => {
    const w = mount(ConfigChangesTimeline, { props: { zoneId: 1 } })
    await flushPromises()

    vi.mocked(zoneConfigModeApi.changes).mockResolvedValueOnce({
      zone_id: 1,
      changes: [changes[0]],
    })
    await w.find('[data-testid="config-changes-namespace"]').setValue('recipe.phase')
    await flushPromises()

    expect(zoneConfigModeApi.changes).toHaveBeenCalledWith(1, 'recipe.phase')
  })

  it('shows empty state', async () => {
    vi.mocked(zoneConfigModeApi.changes).mockResolvedValue({ zone_id: 1, changes: [] })
    const w = mount(ConfigChangesTimeline, { props: { zoneId: 1 } })
    await flushPromises()
    expect(w.text()).toContain('Изменений нет')
  })
})
