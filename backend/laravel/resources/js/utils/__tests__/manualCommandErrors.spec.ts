import { describe, expect, it } from 'vitest'
import { extractHumanErrorMessage } from '@/utils/errorMessage'
import { resolveHumanErrorMessage } from '@/utils/errorCatalog'
import {
  MANUAL_COMMAND_REJECTION_CODES,
  describeManualCommandRejection,
} from '@/utils/manualCommandErrors'

describe('manualCommandErrors', () => {
  it.each(MANUAL_COMMAND_REJECTION_CODES)('переводит код %s на русский без сырого кода', (code) => {
    const message = describeManualCommandRejection(code)
    expect(message).toBeTruthy()
    expect(message).toMatch(/[А-Яа-яЁё]/u)
    expect(message).not.toContain(code)

    expect(resolveHumanErrorMessage({ code, message: code })).toBe(message)
    expect(extractHumanErrorMessage({
      response: {
        status: 409,
        data: { status: 'error', code, message: code },
      },
    })).toBe(message)
  })

  it('оставляет уже русское сообщение API', () => {
    expect(resolveHumanErrorMessage({
      code: 'estop_active',
      message: 'Аварийная остановка уже объяснена оператору.',
    })).toBe('Аварийная остановка уже объяснена оператору.')
  })
})
