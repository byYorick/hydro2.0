import { setActivePinia, createPinia } from 'pinia'
import { useZonesStore } from '../zones'

describe('zones store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('inits from props and upserts', () => {
    const store = useZonesStore()
    store.initFromProps({ zones: [{ id: 'z-1', name: 'Zone 1' }] })
    expect(store.items.length).toBe(1)
    store.upsert({ id: 'z-1', name: 'Zone 1 updated' })
    expect(store.items[0].name).toContain('updated')
    store.upsert({ id: 'z-2', name: 'Zone 2' })
    expect(store.items.length).toBe(2)
  })
})

