export interface ZoneOption {
  id: number
  name: string
}

export interface RecipeOption {
  id: number
  name: string
}

export interface AggregatePoint {
  ts: string
  avg: number
  min: number
  max: number
  median?: number
}

export interface RecipeRun {
  id: number
  zone_id?: number
  zone?: { id: number; name: string }
  start_date?: string
  end_date?: string
  efficiency_score?: number
  avg_ph_deviation?: number
  avg_ec_deviation?: number
  alerts_count?: number
  total_duration_hours?: number
}

export interface RecipeStats {
  avg_efficiency?: number
  avg_ph_deviation_overall?: number
  avg_ec_deviation_overall?: number
  avg_alerts_count?: number
  avg_duration_hours?: number
  total_runs?: number
}

export interface RecipeComparisonRow {
  recipe_id: number
  recipe?: { id: number; name: string }
  avg_efficiency?: number
  avg_ph_deviation?: number
  avg_ec_deviation?: number
  avg_alerts_count?: number
  avg_duration_hours?: number
  runs_count?: number
}

interface RecipeAnalyticsResult {
  runs: RecipeRun[]
  total: number
  perPage: number
  stats: RecipeStats | null
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : null
}

export function formatNumber(value: unknown, decimals: number): string {
  if (value === null || value === undefined) {
    return '—'
  }
  const num = typeof value === 'number' ? value : Number(value)
  if (Number.isNaN(num) || !isFinite(num)) {
    return '—'
  }
  return num.toFixed(decimals)
}

export function formatDuration(value: unknown): string {
  if (value === null || value === undefined) {
    return '—'
  }
  const num = typeof value === 'number' ? value : Number(value)
  if (Number.isNaN(num) || !isFinite(num)) {
    return '—'
  }
  if (num >= 24) {
    return `${(num / 24).toFixed(1)} дн.`
  }
  return `${num.toFixed(1)} ч`
}

export function formatDate(value?: string): string {
  if (!value) {
    return '—'
  }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString('ru-RU')
}

export function toZoneOptions(rawResponse: unknown): ZoneOption[] {
  const response = asRecord(rawResponse)
  const data = asRecord(response?.data)
  const list = data?.data
  if (!Array.isArray(list)) {
    return []
  }
  return list
    .map((zone) => {
      const zoneRecord = asRecord(zone)
      const id = zoneRecord?.id
      if (typeof id !== 'number') {
        return null
      }
      const name = typeof zoneRecord.name === 'string' && zoneRecord.name.trim() !== ''
        ? zoneRecord.name
        : `Zone #${id}`
      return { id, name }
    })
    .filter((item): item is ZoneOption => item !== null)
}

export function toRecipeOptions(rawResponse: unknown): RecipeOption[] {
  const response = asRecord(rawResponse)
  const data = asRecord(response?.data)
  const payload = data?.data
  const list = Array.isArray((payload as Record<string, unknown> | null)?.data)
    ? ((payload as Record<string, unknown>).data as unknown[])
    : Array.isArray(payload)
      ? payload
      : []

  return list
    .map((recipe) => {
      const recipeRecord = asRecord(recipe)
      const id = recipeRecord?.id
      const name = recipeRecord?.name
      if (typeof id !== 'number' || typeof name !== 'string') {
        return null
      }
      return { id, name }
    })
    .filter((item): item is RecipeOption => item !== null)
}

export function toTelemetryAggregates(rawResponse: unknown): AggregatePoint[] {
  const response = asRecord(rawResponse)
  const data = asRecord(response?.data)
  const list = data?.data
  return Array.isArray(list) ? (list as AggregatePoint[]) : []
}

export function toRecipeAnalytics(rawResponse: unknown, currentPerPage: number): RecipeAnalyticsResult {
  const response = asRecord(rawResponse)
  const data = asRecord(response?.data)
  const pageData = asRecord(data?.data)
  const pageItems = pageData?.data
  const runs = Array.isArray(pageItems) ? (pageItems as RecipeRun[]) : []

  const total = typeof pageData?.total === 'number' ? pageData.total : runs.length
  const perPage = typeof pageData?.per_page === 'number' ? pageData.per_page : currentPerPage
  const stats = asRecord(data?.stats) as RecipeStats | null

  return {
    runs,
    total,
    perPage,
    stats,
  }
}

export function toComparisonRows(rawResponse: unknown): RecipeComparisonRow[] {
  const response = asRecord(rawResponse)
  const data = asRecord(response?.data)
  const list = data?.data
  return Array.isArray(list) ? (list as RecipeComparisonRow[]) : []
}
