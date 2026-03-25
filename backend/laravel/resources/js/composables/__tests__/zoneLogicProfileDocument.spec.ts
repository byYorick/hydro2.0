import { describe, expect, it } from 'vitest'
import {
  normalizeZoneLogicProfilePayload,
  upsertZoneLogicProfilePayload,
} from '../zoneLogicProfileDocument'

describe('zoneLogicProfileDocument', () => {
  it('сохраняет command_plans при нормализации payload', () => {
    const payload = normalizeZoneLogicProfilePayload({
      active_mode: 'setup',
      profiles: {
        setup: {
          mode: 'setup',
          is_active: true,
          subsystems: {
            diagnostics: { enabled: true },
          },
          command_plans: {
            schema_version: 1,
            plans: {
              diagnostics: {
                steps: [{ channel: 'valve_clean_fill', cmd: 'set_relay', params: { state: true } }],
              },
            },
          },
          updated_at: '2026-03-25T06:41:19Z',
        },
      },
    })

    expect(payload.profiles.setup?.command_plans).toEqual({
      schema_version: 1,
      plans: {
        diagnostics: {
          steps: [{ channel: 'valve_clean_fill', cmd: 'set_relay', params: { state: true } }],
        },
      },
    })
  })

  it('не теряет command_plans при merge обновлённого профиля', () => {
    const nextPayload = upsertZoneLogicProfilePayload(
      normalizeZoneLogicProfilePayload({
        active_mode: 'setup',
        profiles: {
          setup: {
            mode: 'setup',
            is_active: true,
            subsystems: {
              diagnostics: { enabled: true },
            },
            command_plans: {
              schema_version: 1,
              plans: {
                diagnostics: {
                  steps: [{ channel: 'valve_clean_fill', cmd: 'set_relay', params: { state: true } }],
                },
              },
            },
            updated_at: '2026-03-25T06:41:19Z',
          },
        },
      }),
      'setup',
      {
        diagnostics: { enabled: true, execution: { workflow: 'cycle_start' } },
      },
      true,
    )

    expect(nextPayload.profiles.setup?.command_plans).toEqual({
      schema_version: 1,
      plans: {
        diagnostics: {
          steps: [{ channel: 'valve_clean_fill', cmd: 'set_relay', params: { state: true } }],
        },
      },
    })
  })
})
