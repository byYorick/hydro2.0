import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'

const sendNodeCommandMock = vi.hoisted(() => vi.fn())
const getStatusMock = vi.hoisted(() => vi.fn())
const detachMock = vi.hoisted(() => vi.fn())

vi.mock('@/services/api', () => ({
  api: {
    commands: {
      sendNodeCommand: sendNodeCommandMock,
      getStatus: getStatusMock,
    },
    nodes: {
      detach: detachMock,
    },
  },
}))

import { useDeviceCommandActions } from '../useDeviceCommandActions'

describe('useDeviceCommandActions', () => {
  function setupSend(): void {
    sendNodeCommandMock.mockReset().mockResolvedValue({})
    getStatusMock.mockReset().mockResolvedValue({ status: 'ERROR' })
  }

  it('для level-switch irrig-ноды отправляет state в storage_state', async () => {
    setupSend()
    const { onTestPump } = useDeviceCommandActions({
      device: ref({ id: 7, type: 'irrig' } as never),
      showToast: vi.fn(),
      upsertDevice: vi.fn(),
    })

    await onTestPump('level_clean_max', 'SENSOR')

    expect(sendNodeCommandMock).toHaveBeenCalledWith(7, {
      type: 'state',
      channel: 'storage_state',
      params: {},
    })
  })

  it('для обычного сенсора сохраняет test_sensor на исходном канале', async () => {
    setupSend()
    const { onTestPump } = useDeviceCommandActions({
      device: ref({ id: 8, type: 'ph' } as never),
      showToast: vi.fn(),
      upsertDevice: vi.fn(),
    })

    await onTestPump('ph_sensor', 'SENSOR')

    expect(sendNodeCommandMock).toHaveBeenCalledWith(8, {
      type: 'test_sensor',
      channel: 'ph_sensor',
      params: {},
    })
  })

  it('для irrig actuator-канала pump_main отправляет set_relay', async () => {
    setupSend()
    const { onTestPump } = useDeviceCommandActions({
      device: ref({ id: 9, type: 'irrig' } as never),
      showToast: vi.fn(),
      upsertDevice: vi.fn(),
    })

    await onTestPump('pump_main', 'ACTUATOR')

    expect(sendNodeCommandMock).toHaveBeenCalledWith(9, {
      type: 'set_relay',
      channel: 'pump_main',
      params: { state: true, duration_ms: 3000 },
    })
  })

  it('для irrig valve-канала отправляет transient set_relay на 3 секунды', async () => {
    setupSend()
    const { onTestPump } = useDeviceCommandActions({
      device: ref({ id: 11, type: 'irrig' } as never),
      showToast: vi.fn(),
      upsertDevice: vi.fn(),
    })

    await onTestPump('valve_clean_fill', 'ACTUATOR')

    expect(sendNodeCommandMock).toHaveBeenCalledWith(11, {
      type: 'set_relay',
      channel: 'valve_clean_fill',
      params: { state: true, duration_ms: 3000 },
    })
  })

  it('для сервисного канала storage_state отправляет state без run_pump', async () => {
    setupSend()
    const { onTestPump } = useDeviceCommandActions({
      device: ref({ id: 10, type: 'irrig' } as never),
      showToast: vi.fn(),
      upsertDevice: vi.fn(),
    })

    await onTestPump('storage_state', 'ACTUATOR')

    expect(sendNodeCommandMock).toHaveBeenCalledWith(10, {
      type: 'state',
      channel: 'storage_state',
      params: {},
    })
  })

  it('показывает локализованную ошибку теста по human_error_message команды', async () => {
    sendNodeCommandMock.mockReset().mockResolvedValue({ command_id: 'cmd-11' })
    getStatusMock.mockReset().mockResolvedValue({
      status: 'TIMEOUT',
      error_code: 'TIMEOUT',
      error_message: 'TIMEOUT',
      human_error_message: 'Превышено время ожидания выполнения команды.',
    })
    const showToast = vi.fn()

    const { onTestPump } = useDeviceCommandActions({
      device: ref({ id: 11, type: 'irrig' } as never),
      showToast,
      upsertDevice: vi.fn(),
    })

    await onTestPump('pump_main', 'ACTUATOR')

    expect(showToast).toHaveBeenCalledWith(
      'Ошибка теста Тест главного насоса: Превышено время ожидания выполнения команды.',
      'error',
      5000,
    )
  })
})
