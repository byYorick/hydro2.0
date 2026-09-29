import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

describe('Show.vue + zones.ts E253', () => {
  it('e253 Show.vue и zones.ts не вызывают startIrrigation/startCycle/startSolutionChange', () => {
    const root = resolve(__dirname, '../../..')
    const show = readFileSync(resolve(root, 'Pages/Zones/Show.vue'), 'utf8')
    const zonesApi = readFileSync(resolve(root, 'services/api/zones.ts'), 'utf8')
    const schedulerTab = readFileSync(resolve(root, 'Pages/Zones/Tabs/ZoneSchedulerTab.vue'), 'utf8')
    const diagnostics = readFileSync(
      resolve(root, 'Components/Scheduler/SchedulerDiagnostics.vue'),
      'utf8',
    )

    expect(zonesApi).not.toMatch(/\bstartIrrigation\b/)
    expect(zonesApi).not.toMatch(/\bstartCycle\b/)
    expect(zonesApi).not.toMatch(/\bstartSolutionChange\b/)
    expect(show).not.toMatch(/start-irrigation/)
    expect(show).not.toMatch(/@water=.*START_IRRIGATION/)
    expect(diagnostics).not.toContain('Задачи диспетчера')
    expect(schedulerTab).toMatch(/scheduler-no-dispatcher-promise/)
    expect(diagnostics).not.toMatch(/окно диспетчера/i)
  })
})
