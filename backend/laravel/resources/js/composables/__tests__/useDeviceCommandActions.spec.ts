import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import { useDeviceCommandActions } from '../useDeviceCommandActions'

describe('useDeviceCommandActions', () => {
  it('для level-switch irrig-ноды отправляет state в storage_state', async () => {
    const api = {
      get: vi.fn(),
      post: vi.fn().mockResolvedValue({ data: { status: 'error' } }),
    }
    const showToast = vi.fn()
    const upsertDevice = vi.fn()

    const { onTestPump } = useDeviceCommandActions({
      device: ref({
        id: 7,
        type: 'irrig',
      } as never),
      api,
      showToast,
      upsertDevice,
    })

    await onTestPump('level_clean_max', 'SENSOR')

    expect(api.post).toHaveBeenCalledWith('/nodes/7/commands', {
      type: 'state',
      channel: 'storage_state',
      params: {},
    })
  })

  it('для обычного сенсора сохраняет test_sensor на исходном канале', async () => {
    const api = {
      get: vi.fn(),
      post: vi.fn().mockResolvedValue({ data: { status: 'error' } }),
    }
    const showToast = vi.fn()
    const upsertDevice = vi.fn()

    const { onTestPump } = useDeviceCommandActions({
      device: ref({
        id: 8,
        type: 'ph',
      } as never),
      api,
      showToast,
      upsertDevice,
    })

    await onTestPump('ph_sensor', 'SENSOR')

    expect(api.post).toHaveBeenCalledWith('/nodes/8/commands', {
      type: 'test_sensor',
      channel: 'ph_sensor',
      params: {},
    })
  })

  it('для irrig actuator-канала pump_main отправляет set_relay', async () => {
    const api = {
      get: vi.fn(),
      post: vi.fn().mockResolvedValue({ data: { status: 'error' } }),
    }
    const showToast = vi.fn()
    const upsertDevice = vi.fn()

    const { onTestPump } = useDeviceCommandActions({
      device: ref({
        id: 9,
        type: 'irrig',
      } as never),
      api,
      showToast,
      upsertDevice,
    })

    await onTestPump('pump_main', 'ACTUATOR')

    expect(api.post).toHaveBeenCalledWith('/nodes/9/commands', {
      type: 'set_relay',
      channel: 'pump_main',
      params: { state: true, duration_ms: 3000 },
    })
  })

  it('для irrig valve-канала отправляет transient set_relay на 3 секунды', async () => {
    const api = {
      get: vi.fn(),
      post: vi.fn().mockResolvedValue({ data: { status: 'error' } }),
    }
    const showToast = vi.fn()
    const upsertDevice = vi.fn()

    const { onTestPump } = useDeviceCommandActions({
      device: ref({
        id: 11,
        type: 'irrig',
      } as never),
      api,
      showToast,
      upsertDevice,
    })

    await onTestPump('valve_clean_fill', 'ACTUATOR')

    expect(api.post).toHaveBeenCalledWith('/nodes/11/commands', {
      type: 'set_relay',
      channel: 'valve_clean_fill',
      params: { state: true, duration_ms: 3000 },
    })
  })

  it('для сервисного канала storage_state отправляет state без run_pump', async () => {
    const api = {
      get: vi.fn(),
      post: vi.fn().mockResolvedValue({ data: { status: 'error' } }),
    }
    const showToast = vi.fn()
    const upsertDevice = vi.fn()

    const { onTestPump } = useDeviceCommandActions({
      device: ref({
        id: 10,
        type: 'irrig',
      } as never),
      api,
      showToast,
      upsertDevice,
    })

    await onTestPump('storage_state', 'ACTUATOR')

    expect(api.post).toHaveBeenCalledWith('/nodes/10/commands', {
      type: 'state',
      channel: 'storage_state',
      params: {},
    })
  })

  it('показывает локализованную ошибку теста по human_error_message команды', async () => {
    const api = {
      get: vi.fn().mockResolvedValue({
        data: {
          status: 'ok',
          data: {
            status: 'TIMEOUT',
            error_code: 'TIMEOUT',
            error_message: 'TIMEOUT',
            human_error_message: 'Превышено время ожидания выполнения команды.',
          },
        },
      }),
      post: vi.fn().mockResolvedValue({
        data: { status: 'ok', data: { command_id: 'cmd-11' } },
      }),
    }
    const showToast = vi.fn()
    const upsertDevice = vi.fn()

    const { onTestPump } = useDeviceCommandActions({
      device: ref({
        id: 11,
        type: 'irrig',
      } as never),
      api,
      showToast,
      upsertDevice,
    })

    await onTestPump('pump_main', 'ACTUATOR')

    expect(showToast).toHaveBeenCalledWith(
      'Ошибка теста Тест главного насоса: Превышено время ожидания выполнения команды.',
      'error',
      5000,
    )
  })
})
