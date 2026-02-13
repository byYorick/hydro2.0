import { extractData } from '@/utils/apiHelpers'

export function extractCollection<T>(payload: unknown): T[] {
  const data = extractData<unknown>(payload)

  if (Array.isArray(data)) {
    return data as T[]
  }

  if (data && typeof data === 'object' && Array.isArray((data as { data?: unknown }).data)) {
    return (data as { data: T[] }).data
  }

  return []
}
