import { describe, expect, it } from 'vitest'
import { buildAutoBreadcrumbs } from '@/utils/breadcrumbs'

describe('buildAutoBreadcrumbs', () => {
  it('не включает query string в имя зоны', () => {
    const items = buildAutoBreadcrumbs('/zones/83?tab=cycle', {
      auth: { user: { role: 'admin' } },
      zone: { name: 'E2E Automation Zone' },
    })

    expect(items.map((item) => item.label)).toEqual(['Система', 'Зоны', 'E2E Automation Zone'])
  })

  it('пропускает сегмент login', () => {
    const items = buildAutoBreadcrumbs('/login', {
      auth: { user: { role: 'admin' } },
    })

    expect(items.map((item) => item.label)).toEqual(['Система'])
  })

  it('ставит теплицу перед зоной', () => {
    const items = buildAutoBreadcrumbs('/zones/4', {
      auth: { user: { role: 'operator' } },
      zone: {
        name: 'Салат A',
        greenhouse: { id: 2, name: 'Блок 1' },
      },
    })

    expect(items.map((item) => item.label)).toEqual(['Сегодня', 'Блок 1', 'Зоны', 'Салат A'])
    expect(items[1]?.href).toBe('/greenhouses/2')
  })

  it('строит цепочку теплица → зона → узел', () => {
    const items = buildAutoBreadcrumbs('/devices/15', {
      auth: { user: { role: 'engineer' } },
      device: {
        uid: 'nd-ph-1',
        zone_id: 4,
        zone: {
          id: 4,
          name: 'Салат A',
          greenhouse: { id: 2, name: 'Блок 1' },
        },
      },
    })

    expect(items.map((item) => item.label)).toEqual(['Обзор', 'Блок 1', 'Салат A', 'Узлы', 'nd-ph-1'])
    expect(items[2]?.href).toBe('/zones/4')
    expect(items[4]?.href).toBe('/devices/15')
  })
})
