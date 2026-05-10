import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nodesApi } from '../nodes'
import * as client from '../_client'

vi.mock('../_client', async () => {
  const actual = await vi.importActual<typeof import('../_client')>('../_client')
  return {
    ...actual,
    apiGet: vi.fn(),
  }
})

describe('nodesApi.list', () => {
  beforeEach(() => {
    vi.mocked(client.apiGet).mockReset()
  })

  it('разворачивает Laravel paginator после extractData', async () => {
    vi.mocked(client.apiGet).mockResolvedValue({
      current_page: 1,
      data: [{ id: 1, name: 'n1' }],
      last_page: 1,
      per_page: 25,
      total: 1,
    })

    const out = await nodesApi.list({ unassigned: true })

    expect(out).toEqual([{ id: 1, name: 'n1' }])
    expect(client.apiGet).toHaveBeenCalledWith('/nodes', { params: { unassigned: true } })
  })

  it('возвращает массив как есть', async () => {
    vi.mocked(client.apiGet).mockResolvedValue([{ id: 2 }])

    const out = await nodesApi.list()

    expect(out).toEqual([{ id: 2 }])
  })

  it('при неожиданной форме возвращает пустой массив', async () => {
    vi.mocked(client.apiGet).mockResolvedValue({ foo: 1 })

    const out = await nodesApi.list()

    expect(out).toEqual([])
  })
})
