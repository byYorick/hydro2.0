export interface ZoneEstopStatus {
  active: boolean
  source: string | null
  since: string | null
  node_uid: string | null
  event_id: number | null
}

export type ZoneEstopAction = 'engage' | 'release'

export type ZoneEstopResult = 'engaged' | 'already_active' | 'released' | 'already_released'

export interface ZoneEstopView {
  zone_id: number
  estop: ZoneEstopStatus
}

export interface ZoneEstopApplyResult {
  zone_id: number
  action: ZoneEstopAction
  result: ZoneEstopResult
  estop: ZoneEstopStatus
}
