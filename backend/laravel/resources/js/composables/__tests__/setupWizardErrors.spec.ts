import { describe, expect, it } from 'vitest'
import { extractSetupWizardErrorMessage } from '@/composables/setupWizardErrors'

describe('setupWizardErrors.extractSetupWizardErrorMessage', () => {
  it('возвращает первое сообщение валидации', () => {
    const error = {
      response: {
        data: {
          errors: {
            name: ['Поле name обязательно'],
          },
        },
      },
    }

    expect(extractSetupWizardErrorMessage(error, 'fallback')).toBe('Поле name обязательно')
  })

  it('возвращает message из response.data', () => {
    const error = {
      response: {
        data: {
          message: 'Validation failed',
        },
      },
    }

    expect(extractSetupWizardErrorMessage(error, 'fallback')).toBe('Validation failed')
  })

  it('использует fallback при неизвестной ошибке', () => {
    expect(extractSetupWizardErrorMessage(null, 'fallback')).toBe('fallback')
  })
})
