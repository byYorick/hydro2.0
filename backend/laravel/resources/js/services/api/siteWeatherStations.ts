/**
 * Site-level weather stations API (independent of user greenhouses).
 *
 * GET    /api/site/weather-stations
 * POST   /api/site/weather-stations       { node_id }
 * DELETE /api/site/weather-stations/{id}
 */
import { apiDelete, apiGet, apiPost } from './_client'

export interface SiteWeatherStation {
  id: number
  uid: string
  name?: string | null
  type?: string | null
  status?: string | null
  zone_id?: number | null
  lifecycle_state?: string | null
  last_seen_at?: string | null
  [key: string]: unknown
}

export const siteWeatherStationsApi = {
  list(): Promise<SiteWeatherStation[]> {
    return apiGet<SiteWeatherStation[]>('/site/weather-stations')
  },

  assign(nodeId: number): Promise<SiteWeatherStation> {
    return apiPost<SiteWeatherStation>('/site/weather-stations', { node_id: nodeId })
  },

  unassign(nodeId: number): Promise<SiteWeatherStation> {
    return apiDelete<SiteWeatherStation>(`/site/weather-stations/${nodeId}`)
  },
}
