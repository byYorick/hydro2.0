import { describe, expect, it } from 'vitest'

import { buildHumanErrorInputFromPayload, extractHumanErrorMessage } from '../errorMessage'

describe('errorMessage', () => {
  it('buildHumanErrorInputFromPayload читает human_error_message и code', () => {
    expect(buildHumanErrorInputFromPayload({
      status: 'error',
      code: 'not_found',
      message: 'Not found',
      human_error_message: 'Запрошенный объект не найден.',
    })).toEqual({
      code: 'not_found',
      message: 'Not found',
      humanMessage: 'Запрошенный объект не найден.',
    })
  })

  it('extractHumanErrorMessage предпочитает human_error_message', () => {
    const error = {
      response: {
        status: 404,
        data: {
          code: 'not_found',
          message: 'Not found',
          human_error_message: 'Запрошенный объект не найден.',
        },
      },
    }

    expect(extractHumanErrorMessage(error)).toBe('Запрошенный объект не найден.')
  })

  it('extractHumanErrorMessage оставляет message без перевода', () => {
    const error = {
      response: {
        status: 400,
        data: {
          code: 'unknown_xyz',
          message: 'Something went wrong',
        },
      },
    }

    expect(extractHumanErrorMessage(error)).toBe('Something went wrong')
  })
})
