import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import { useAutomationRuntimeMeta } from '@/composables/useAutomationRuntimeMeta'
import type { AutomationState } from '@/types/Automation'

describe('useAutomationRuntimeMeta', () => {
  it('определяет stale-снимок и timestamp', () => {
    const automationState = ref<AutomationState | null>({
      zone_id: 1,
      state: 'TANK_FILLING',
      state_label: 'Наполнение',
      state_details: {
        started_at: null,
        elapsed_sec: 0,
        progress_percent: 0,
        failed: false,
      },
      system_config: {
        tanks_count: 2,
        system_type: 'drip',
        clean_tank_capacity_l: null,
        nutrient_tank_capacity_l: null,
      },
      current_levels: {
        clean_tank_level_percent: 0,
        nutrient_tank_level_percent: 0,
        ph: null,
        ec: null,
      },
      active_processes: {
        pump_in: false,
        circulation_pump: false,
        ph_correction: false,
        ec_correction: false,
      },
      timeline: [],
      next_state: null,
      estimated_completion_sec: null,
      state_meta: {
        source: 'cache',
        is_stale: true,
        served_at: '2026-06-01T10:00:00.000Z',
      },
    })

    const meta = useAutomationRuntimeMeta(automationState)

    expect(meta.isStale.value).toBe(true)
    expect(meta.dataTimestamp.value).not.toBeNull()
  })
})
