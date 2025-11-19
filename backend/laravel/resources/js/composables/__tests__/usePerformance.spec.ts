import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useMemoizedFilter, useLowercaseQuery, useMultiFilter } from '../usePerformance'

describe('usePerformance (P3-4)', () => {
  describe('useMemoizedFilter', () => {
    it('should filter items correctly', () => {
      const items = ref([1, 2, 3, 4, 5])
      const filterFn = (item: number) => item > 3
      
      const filtered = useMemoizedFilter(items, filterFn)

      expect(filtered.value).toEqual([4, 5])
    })

    it('should update when items change', () => {
      const items = ref([1, 2, 3])
      const filterFn = (item: number) => item > 1
      
      const filtered = useMemoizedFilter(items, filterFn)

      expect(filtered.value).toEqual([2, 3])

      items.value = [4, 5, 6]
      expect(filtered.value).toEqual([5, 6])
    })

    it('should work with computed items', () => {
      const source = ref([1, 2, 3, 4, 5])
      const items = computed(() => source.value)
      const filterFn = (item: number) => item % 2 === 0
      
      const filtered = useMemoizedFilter(items, filterFn)

      expect(filtered.value).toEqual([2, 4])
    })
  })

  describe('useLowercaseQuery', () => {
    it('should convert query to lowercase', () => {
      const query = ref('TEST QUERY')
      const lowercase = useLowercaseQuery(query)

      expect(lowercase.value).toBe('test query')
    })

    it('should update when query changes', () => {
      const query = ref('FIRST')
      const lowercase = useLowercaseQuery(query)

      expect(lowercase.value).toBe('first')

      query.value = 'SECOND'
      expect(lowercase.value).toBe('second')
    })

    it('should handle empty string', () => {
      const query = ref('')
      const lowercase = useLowercaseQuery(query)

      expect(lowercase.value).toBe('')
    })
  })

  describe('useMultiFilter', () => {
    interface TestItem {
      name: string
      type: string
      status: string
    }

    it('should filter with multiple conditions', () => {
      const items = ref<TestItem[]>([
        { name: 'Item 1', type: 'A', status: 'active' },
        { name: 'Item 2', type: 'B', status: 'active' },
        { name: 'Item 3', type: 'A', status: 'inactive' }
      ])

      const typeFilter = ref('')
      const statusFilter = ref('active')

      const filtered = useMultiFilter(
        items,
        { type: typeFilter, status: statusFilter },
        (item, filters) => {
          const typeMatch = !filters.type || item.type === filters.type
          const statusMatch = !filters.status || item.status === filters.status
          return typeMatch && statusMatch
        }
      )

      expect(filtered.value).toEqual([
        { name: 'Item 1', type: 'A', status: 'active' },
        { name: 'Item 2', type: 'B', status: 'active' }
      ])
    })

    it('should return all items when no filters are active', () => {
      const items = ref<TestItem[]>([
        { name: 'Item 1', type: 'A', status: 'active' },
        { name: 'Item 2', type: 'B', status: 'inactive' }
      ])

      const typeFilter = ref('')
      const statusFilter = ref('')

      const filtered = useMultiFilter(
        items,
        { type: typeFilter, status: statusFilter },
        (item, filters) => true
      )

      expect(filtered.value).toEqual(items.value)
    })

    it('should update when filters change', () => {
      const items = ref<TestItem[]>([
        { name: 'Item 1', type: 'A', status: 'active' },
        { name: 'Item 2', type: 'B', status: 'active' }
      ])

      const typeFilter = ref('')
      const statusFilter = ref('active')

      const filtered = useMultiFilter(
        items,
        { type: typeFilter, status: statusFilter },
        (item, filters) => {
          const typeMatch = !filters.type || item.type === filters.type
          const statusMatch = !filters.status || item.status === filters.status
          return typeMatch && statusMatch
        }
      )

      expect(filtered.value.length).toBe(2)

      typeFilter.value = 'A'
      expect(filtered.value.length).toBe(1)
      expect(filtered.value[0].type).toBe('A')
    })
  })
})

