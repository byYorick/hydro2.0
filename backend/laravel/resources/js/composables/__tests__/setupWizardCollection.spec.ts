import { describe, expect, it } from 'vitest'
import { extractCollection } from '@/composables/setupWizardCollection'

describe('setupWizardCollection.extractCollection', () => {
  it('возвращает массив для прямого array payload', () => {
    expect(extractCollection<number>([1, 2, 3])).toEqual([1, 2, 3])
  })

  it('возвращает массив для стандартного API формата', () => {
    const payload = {
      status: 'ok',
      data: [
        { id: 1, name: 'A' },
        { id: 2, name: 'B' },
      ],
    }

    expect(extractCollection<{ id: number; name: string }>(payload)).toEqual(payload.data)
  })

  it('корректно извлекает массив из двойной обертки', () => {
    const payload = {
      data: {
        data: [
          { id: 10 },
          { id: 11 },
        ],
      },
    }

    expect(extractCollection<{ id: number }>(payload)).toEqual([{ id: 10 }, { id: 11 }])
  })

  it('возвращает пустой массив для неколлекционных payload', () => {
    expect(extractCollection<{ id: number }>(null)).toEqual([])
    expect(extractCollection<{ id: number }>({})).toEqual([])
    expect(extractCollection<{ id: number }>({ data: { items: [{ id: 1 }] } })).toEqual([])
    expect(extractCollection<{ id: number }>('invalid')).toEqual([])
  })
})
