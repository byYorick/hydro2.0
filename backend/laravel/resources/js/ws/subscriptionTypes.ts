import type { ToastHandler } from '@/composables/useApi'

export type ZoneCommandHandler = (event: {
  commandId: number | string
  status: string
  message?: string
  error?: string
  zoneId?: number
}) => void

export type GlobalEventHandler = (event: {
  id: number | string
  kind: string
  message: string
  zoneId?: number
  occurredAt: string
}) => void

export type ChannelKind = 'zoneCommands' | 'globalEvents'

export interface ActiveSubscription {
  id: string
  channelName: string
  kind: ChannelKind
  handler: ZoneCommandHandler | GlobalEventHandler
  componentTag: string
  showToast?: ToastHandler
  instanceId: number
}

export interface ChannelControl {
  channelName: string
  channelType: 'private' | 'public'
  kind: ChannelKind
  echoChannel: any | null
  listenerRefs: Record<string, (payload: any) => void>
}

export interface GlobalChannelRegistry {
  channelControl: ChannelControl | null
  subscriptionRefCount: number
  isAuthorized: boolean
  handlers: Set<GlobalEventHandler>
}

export interface PendingSubscription {
  id: string
  channelName: string
  kind: ChannelKind
  channelType: 'private' | 'public'
  handler: ZoneCommandHandler | GlobalEventHandler
  componentTag: string
  instanceId: number
  showToast?: ToastHandler
}
